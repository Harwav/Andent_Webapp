# Classification Learning System Design

**Date:** 2026-04-20  
**Status:** Approved  
**Phase:** Phase 1 (Post-Classification Optimization)

---

## Overview

A learning system that captures user corrections to classification results and automatically generates improvement rules. The system learns from human expertise to reduce manual review over time.

**Goal:** Achieve 95%+ auto-classification accuracy by learning from the 5% that require human review.

---

## Problem Statement

**Current State:**
- When users manually correct classifications (e.g., "Ortho - Solid" → "Ortho - Hollow"), the correction is lost
- System makes the same "mistake" on similar files in the future
- No mechanism to capture institutional knowledge

**Desired State:**
- System learns from every correction
- Pattern-based rules for clear cases (filename patterns)
- Threshold adjustments for borderline cases (fill_ratio, thickness)
- User maintains control via review queue approval

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Classification Pipeline (Existing)                         │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │ File Upload │→ │ Classify     │→ │ Return Result│       │
│  └─────────────┘  └──────────────┘  └──────────────┘       │
│                          ↓                                  │
│                   ┌──────────────┐                          │
│                   │ Apply Learned│                          │
│                   │ Rules        │                          │
│                   └──────────────┘                          │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  Learning Engine (NEW)                                      │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │ Correction  │→ │ Pattern      │→ │ Rule         │       │
│  │ Logger      │  │ Detector     │  │ Generator    │       │
│  └─────────────┘  └──────────────┘  └──────────────┘       │
│                          ↓                                  │
│                   ┌──────────────┐                          │
│                   │ Review Queue │                          │
│                   │ (Pending     │                          │
│                   │  Approval)   │                          │
│                   └──────────────┘                          │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  Rule Storage (SQLite)                                      │
│  - learned_rules table                                      │
│  - correction_log table                                     │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **User corrects classification** → Logged to `correction_log` with metrics snapshot
2. **Pattern detector runs** (nightly or on-demand) → Finds common patterns in corrections
3. **Rule generator creates draft rules** → Added to `learned_rules` with status='pending'
4. **User reviews/approves rules** in Learning Queue UI → Status changed to 'active'
5. **Next classification** → Applies active learned rules BEFORE default logic

---

## Rule Types

### Type A: Pattern-Based Rules

**Use Case:** Filename patterns that clearly indicate model type

**Example:**
- User corrects: "CASE123_Antag.stl" → "Antagonist - Hollow"
- System learns: Files with "antag" in name → Antagonist - Hollow

**Detection Algorithm:**
```python
def extract_patterns(filename: str) -> List[Dict]:
    """Extract candidate patterns from filename."""
    patterns = []
    
    # Substring patterns (3+ chars)
    for i in range(len(filename) - 2):
        for j in range(i + 3, min(i + 15, len(filename))):
            substring = filename[i:j].lower()
            if substring.isalnum() or '_' in substring:
                patterns.append({
                    "pattern": substring,
                    "pattern_type": "substring"
                })
    
    # Regex patterns
    patterns.extend([
        {"pattern": r"CASE\d+", "pattern_type": "regex"},
        {"pattern": r"Antag\w*", "pattern_type": "regex"},
        {"pattern": r"UpperJaw", "pattern_type": "regex"},
        {"pattern": r"LowerJaw", "pattern_type": "regex"},
    ])
    
    return patterns
```

**Rule Format:**
```json
{
  "rule_id": "rule_001",
  "type": "pattern",
  "pattern": "antag",
  "pattern_type": "substring",
  "target_model_type": "Antagonist - Hollow",
  "confidence_level": "high",
  "corrections_count": 3,
  "status": "active",
  "created_at": "2026-04-20T10:30:00Z",
  "approved_at": "2026-04-20T14:15:00Z"
}
```

### Type B: Threshold Adjustment Rules

**Use Case:** Borderline metric ranges that consistently need the same correction

**Example:**
- User corrects 8 files with fill_ratio 0.28-0.32 from "Review" → "Solid"
- System learns: Unsectioned models in this range default to Solid

**Detection Algorithm:**
```python
def detect_threshold_clusters(corrections: List[Correction]) -> List[Dict]:
    """Find clusters of corrections in metric space."""
    # Group by artifact_type and original_decision
    groups = group_by(corrections, ['artifact_type', 'original_model_type'])
    
    clusters = []
    for group in groups:
        if len(group) < 3:  # Need minimum 3 corrections
            continue
        
        # Find common metric ranges
        fill_ratios = [c.fill_ratio for c in group if c.fill_ratio]
        thickness_p50 = [c.thickness_p50 for c in group if c.thickness_p50]
        
        if fill_ratios and thickness_p50:
            clusters.append({
                "artifact_type": group[0].artifact_type,
                "fill_ratio_range": (min(fill_ratios), max(fill_ratios)),
                "thickness_p50_range": (min(thickness_p50), max(thickness_p50)),
                "corrected_model_type": group[0].corrected_model_type,
                "corrections_count": len(group)
            })
    
    return clusters
```

**Rule Format:**
```json
{
  "rule_id": "rule_002",
  "type": "threshold_adjustment",
  "condition_json": {
    "artifact_type": "model",
    "fill_ratio": {"min": 0.28, "max": 0.32},
    "thickness_p50": {"min": 4.0, "max": 5.0}
  },
  "target_model_type": "Ortho - Solid",
  "confidence_level": "medium",
  "corrections_count": 8,
  "status": "active"
}
```

---

## Confidence Levels

| Level | Requirements | Behavior |
|-------|--------------|----------|
| **High** | ≥5 corrections, ≥80% success rate | Applied automatically, shown as "Learned Rule" |
| **Medium** | 3-4 corrections, ≥60% success rate | Applied as suggestion (user can override) |
| **Low** | <3 corrections | Review queue only (not applied) |

**Success Rate Calculation:**
```
success_rate = corrections_to_same_model_type / total_applications_of_rule
```

---

## Database Schema

### learned_rules Table

```sql
CREATE TABLE learned_rules (
    id TEXT PRIMARY KEY,
    rule_type TEXT NOT NULL CHECK (rule_type IN ('pattern', 'threshold_adjustment')),
    pattern TEXT,                     -- For pattern rules: "antag", "CASE\d+", etc.
    pattern_type TEXT CHECK (pattern_type IN ('substring', 'regex', 'prefix', 'suffix')),
    condition_json TEXT,              -- For threshold rules: {"fill_ratio": {"min": 0.28, "max": 0.32}}
    target_model_type TEXT NOT NULL,
    confidence_level TEXT NOT NULL CHECK (confidence_level IN ('high', 'medium', 'low')),
    corrections_count INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'active', 'rejected', 'archived')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    approved_at TIMESTAMP,
    last_applied_at TIMESTAMP,
    notes TEXT
);

CREATE INDEX idx_rules_status ON learned_rules(status);
CREATE INDEX idx_rules_pattern ON learned_rules(pattern) WHERE pattern IS NOT NULL;
```

### correction_log Table

```sql
CREATE TABLE correction_log (
    id TEXT PRIMARY KEY,
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    original_model_type TEXT,
    corrected_model_type TEXT NOT NULL,
    original_confidence TEXT,
    dimensions_json TEXT,             -- Snapshot: {"x_mm": 50.0, "y_mm": 40.0, "z_mm": 30.0}
    volume_ml REAL,
    fill_ratio REAL,
    thickness_p50 REAL,
    thin_fraction_under_5mm REAL,
    corrected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    applied_rule_id TEXT,             -- If correction was due to a learned rule (for tracking)
    FOREIGN KEY (applied_rule_id) REFERENCES learned_rules(id)
);

CREATE INDEX idx_corrections_file ON correction_log(file_name);
CREATE INDEX idx_corrections_corrected_at ON correction_log(corrected_at);
CREATE INDEX idx_corrections_rule ON correction_log(applied_rule_id) WHERE applied_rule_id IS NOT NULL;
```

---

## Runtime Behavior

### Classification Pipeline Modification

```python
def classify_saved_upload(stored_path: Path, original_filename: str) -> ClassificationRow:
    """
    Enhanced classification with learned rules.
    
    Rule application order:
    1. High-confidence learned rules (auto-apply)
    2. Default classification logic
    3. Medium-confidence learned rules (as suggestions)
    """
    # Step 1: Check learned rules (highest priority)
    learned_rule = get_matching_learned_rule(original_filename, stored_path)
    
    if learned_rule and learned_rule.confidence_level == "high":
        # Auto-apply high-confidence rules
        result = apply_learned_rule(stored_path, original_filename, learned_rule)
        result.classification_reason = f"Learned rule: {learned_rule.id}"
        log_rule_application(learned_rule.id, original_filename, result.model_type)
        return result
    
    # Step 2: Run default classification logic
    result = default_classification_logic(stored_path, original_filename)
    
    # Step 3: Apply medium-confidence rules as suggestions
    if learned_rule and learned_rule.confidence_level == "medium":
        result.suggested_model_type = learned_rule.target_model_type
        result.suggestion_reason = f"Learned from {learned_rule.corrections_count} corrections"
    
    return result
```

### Rule Matching Logic

```python
def get_matching_learned_rule(filename: str, file_path: Path) -> Optional[LearnedRule]:
    """Find the best matching active learned rule."""
    active_rules = get_active_learned_rules()
    
    for rule in active_rules:
        if rule.rule_type == "pattern":
            if matches_pattern_rule(filename, rule):
                return rule
        elif rule.rule_type == "threshold_adjustment":
            if matches_threshold_rule(file_path, rule):
                return rule
    
    return None

def matches_pattern_rule(filename: str, rule: LearnedRule) -> bool:
    """Check if filename matches pattern rule."""
    if rule.pattern_type == "substring":
        return rule.pattern.lower() in filename.lower()
    elif rule.pattern_type == "regex":
        return bool(re.search(rule.pattern, filename, re.IGNORECASE))
    elif rule.pattern_type == "prefix":
        return filename.lower().startswith(rule.pattern.lower())
    elif rule.pattern_type == "suffix":
        return filename.lower().endswith(rule.pattern.lower())
    return False
```

---

## User Interface

### Learning Queue Tab

**Location:** Main UI, alongside "Active" and "Processed" tabs

**Features:**
- List of pending rule suggestions
- Evidence summary (corrections count, sample files)
- Approve/Reject/Edit actions
- Filter by rule type (pattern/threshold)
- Sort by confidence level, corrections count

**Mockup:**
```
┌─────────────────────────────────────────────────────────────────┐
│  Learning Queue                                    [Refresh]    │
├─────────────────────────────────────────────────────────────────┤
│  Filter: [All ▼]  Sort by: [Corrections ▼]                     │
│                                                                 │
│  📋 Pending Suggestions (3)                                     │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ ✅ SUGGESTION #1                                          │ │
│  │ Pattern Rule • High Confidence                            │ │
│  │                                                           │ │
│  │ Files with "antag" in name → Antagonist - Hollow         │ │
│  │                                                           │ │
│  │ Evidence: 3 corrections, 5 total applications (60%)      │ │
│  │                                                           │ │
│  │ Sample files:                                             │ │
│  │ • 20260408_10936643_SCDL_10936643_DDA3_Antag.stl         │ │
│  │ • 20260408_10936926__SCDL__DD__A2_Antag.stl              │ │
│  │                                                           │ │
│  │ [✅ Approve]  [❌ Reject]  [📝 Edit Rule]                 │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ ✅ SUGGESTION #2                                          │ │
│  │ Threshold Adjustment • Medium Confidence                  │ │
│  │                                                           │ │
│  │ Unsectioned models with fill_ratio 0.28-0.32             │ │
│  │ Default to: Ortho - Solid (instead of Review)            │ │
│  │                                                           │ │
│  │ Evidence: 8 corrections, 10 total (80%)                  │ │
│  │                                                           │ │
│  │ [✅ Approve]  [❌ Reject]  [📝 Edit Rule]                 │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Correction Tracking (Backend)

**Trigger:** When user updates classification via PATCH endpoint

```python
@router.patch("/api/uploads/rows/{row_id}")
async def update_classification_row(
    row_id: str,
    request: UpdateClassificationRowRequest,
) -> ClassificationRow:
    """Update classification and log correction if model_type changed."""
    # Get original row
    original_row = get_upload_row_by_id(row_id)
    
    # Update the row
    updated_row = update_upload_row(row_id, request)
    
    # Log correction if model_type changed
    if original_row.model_type != updated_row.model_type:
        log_correction(
            file_name=original_row.file_name,
            file_path=get_stored_file_path(row_id),
            original_model_type=original_row.model_type,
            corrected_model_type=updated_row.model_type,
            original_confidence=original_row.confidence,
            dimensions=original_row.dimensions,
            volume_ml=original_row.volume_ml,
            fill_ratio=original_row.structure_metrics.get("fill_ratio") if original_row.structure_metrics else None,
            thickness_p50=original_row.structure_metrics.get("thickness_p50") if original_row.structure_metrics else None,
            applied_rule_id=original_row.classification_reason  # If originally classified by learned rule
        )
    
    return updated_row
```

---

## Pattern Detection Job

### Nightly Batch Process

**Schedule:** Runs daily at 2 AM (configurable)

**Steps:**
1. Fetch corrections from last 24 hours
2. Group by corrected_model_type
3. For each group:
   - Extract filename patterns
   - Find metric clusters (for threshold rules)
4. Generate draft rules
5. Add to `learned_rules` with status='pending'
6. Send notification if high-priority rules detected

**Implementation:**
```python
async def run_pattern_detection():
    """Nightly job to detect patterns in recent corrections."""
    # Get corrections from last 24 hours
    recent_corrections = get_corrections_since(hours=24)
    
    if len(recent_corrections) < 3:
        return  # Not enough data
    
    # Group by corrected model type
    groups = group_by(recent_corrections, 'corrected_model_type')
    
    for model_type, corrections in groups.items():
        # Detect pattern rules
        pattern_rules = detect_pattern_rules(corrections)
        
        # Detect threshold rules
        threshold_rules = detect_threshold_rules(corrections)
        
        # Create draft rules
        for rule_data in pattern_rules + threshold_rules:
            if rule_data['corrections_count'] >= 3:  # Minimum threshold
                create_learned_rule(
                    rule_type=rule_data['type'],
                    pattern=rule_data.get('pattern'),
                    condition_json=rule_data.get('condition'),
                    target_model_type=model_type,
                    confidence_level=compute_confidence_level(rule_data),
                    corrections_count=rule_data['corrections_count'],
                    status='pending'
                )
```

---

## Success Metrics

### Key Performance Indicators

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Auto-classification rate** | 95%+ | % of files classified without review |
| **Rule approval rate** | 70%+ | % of suggested rules approved by user |
| **Correction reduction** | 50%+ in 30 days | Corrections/week trending down |
| **Rule application success** | 80%+ | % of rule applications not corrected |

### Monitoring Queries

```sql
-- Auto-classification rate over time
SELECT 
    DATE(corrected_at) as date,
    COUNT(*) as total_corrections,
    COUNT(*) * 100.0 / (SELECT COUNT(*) FROM uploads WHERE DATE(created_at) = DATE(c.corrected_at)) as correction_rate
FROM correction_log c
GROUP BY DATE(corrected_at)
ORDER BY date DESC;

-- Rule effectiveness
SELECT 
    r.id,
    r.pattern,
    r.target_model_type,
    r.corrections_count,
    COUNT(a.id) as applications,
    SUM(CASE WHEN a.was_correction_needed THEN 1 ELSE 0 END) as corrections_after_application,
    (1.0 - SUM(CASE WHEN a.was_correction_needed THEN 1 ELSE 0 END) / COUNT(a.id)) * 100 as success_rate
FROM learned_rules r
LEFT JOIN rule_application_log a ON r.id = a.rule_id
WHERE r.status = 'active'
GROUP BY r.id;
```

---

## Implementation Phases

### Phase 1A: Foundation (Week 1)
- [ ] Database schema migration
- [ ] Correction logging (backend)
- [ ] Basic learned_rules table CRUD

### Phase 1B: Pattern Detection (Week 2)
- [ ] Pattern extraction algorithm
- [ ] Threshold cluster detection
- [ ] Rule generation logic

### Phase 1C: Review Queue UI (Week 3)
- [ ] Learning Queue tab
- [ ] Rule approval/rejection UI
- [ ] Rule editing interface

### Phase 1D: Runtime Integration (Week 4)
- [ ] Apply learned rules in classification pipeline
- [ ] Nightly pattern detection job
- [ ] Monitoring and metrics

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Overfitting to small samples** | Rules created from 3 corrections may not generalize | Require minimum 3 corrections, show confidence levels |
| **Conflicting rules** | Multiple rules match same file | Priority: high confidence > medium > low, then most recent |
| **Performance degradation** | Rule matching slows classification | Index rules table, cache active rules, limit rule count |
| **User ignores review queue** | Rules pile up unapproved | Weekly email digest of pending rules, auto-archive after 30 days |

---

## Future Enhancements (Phase 2)

1. **Case-Level Learning**
   - Learn from case history: "CASE123 typically has Antagonist files"
   - Use case context to inform classification

2. **ML-Based Classification**
   - Train model on historical corrections
   - Predict model_type from filename + metrics

3. **Bulk Rule Management**
   - Export/import learned rules between environments
   - Rule templates for common patterns

4. **A/B Testing**
   - Test rule effectiveness before full deployment
   - Gradual rollout of new rules

---

## References

- Classification Algorithm: `core/andent_classification.py`
- Classification Service: `app/services/classification.py`
- Performance Optimization Plan: `Andent/02_planning/06_Future/performance-optimization-summary.md`

---

**Approvals:**
- [x] Design approved by user (2026-04-20)
- [ ] Implementation plan created
- [ ] Ready for Phase 1A development
