# Classification Learning System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a system that learns from user corrections to improve classification accuracy over time.

**Architecture:** Correction logger → Pattern detector → Rule generator → Review queue → Rule engine that applies learned rules before default classification.

**Tech Stack:** Python 3.9+, FastAPI, SQLite, Vanilla JS

---

## File Structure

**Create:**
- `app/database.py` - Add `learned_rules` and `correction_log` tables
- `app/services/learning_engine.py` - Pattern detection, rule generation
- `app/routers/learning.py` - Learning queue API endpoints
- `tests/test_learning_engine.py` - Learning system tests
- `app/static/learning-queue.html` - Learning Queue UI (new tab)

**Modify:**
- `app/services/classification.py` - Apply learned rules before default logic
- `app/routers/uploads.py` - Log corrections when user updates model_type
- `app/static/index.html` - Add Learning Queue tab
- `app/static/app.js` - Learning queue display logic

---

### Task 1: Database Schema Migration

**Files:**
- Modify: `app/database.py:1-100`
- Create: `tests/test_learning_schema.py`

- [ ] **Step 1: Write schema test**

```python
# tests/test_learning_schema.py
import pytest
from app.database import init_db
from app.config import get_settings
import sqlite3

def test_learned_rules_table_exists():
    """Test that learned_rules table is created."""
    settings = get_settings()
    init_db(settings)
    
    conn = sqlite3.connect(settings.database_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='learned_rules'
    """)
    result = cursor.fetchone()
    
    assert result is not None, "learned_rules table should exist"

def test_correction_log_table_exists():
    """Test that correction_log table is created."""
    settings = get_settings()
    init_db(settings)
    
    conn = sqlite3.connect(settings.database_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='correction_log'
    """)
    result = cursor.fetchone()
    
    assert result is not None, "correction_log table should exist"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_learning_schema.py::test_learned_rules_table_exists -v
```
Expected: FAIL - tables don't exist yet

- [ ] **Step 3: Add learned_rules table to database.py**

```python
# app/database.py - Add after existing table creation
def create_learning_tables(conn: sqlite3.Connection):
    """Create tables for classification learning system."""
    cursor = conn.cursor()
    
    # Learned Rules table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS learned_rules (
            id TEXT PRIMARY KEY,
            rule_type TEXT NOT NULL CHECK (rule_type IN ('pattern', 'threshold_adjustment')),
            pattern TEXT,
            pattern_type TEXT CHECK (pattern_type IN ('substring', 'regex', 'prefix', 'suffix')),
            condition_json TEXT,
            target_model_type TEXT NOT NULL,
            confidence_level TEXT NOT NULL CHECK (confidence_level IN ('high', 'medium', 'low')),
            corrections_count INTEGER DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'active', 'rejected', 'archived')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            approved_at TIMESTAMP,
            last_applied_at TIMESTAMP,
            notes TEXT
        )
    """)
    
    # Correction Log table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS correction_log (
            id TEXT PRIMARY KEY,
            file_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            original_model_type TEXT,
            corrected_model_type TEXT NOT NULL,
            original_confidence TEXT,
            dimensions_json TEXT,
            volume_ml REAL,
            fill_ratio REAL,
            thickness_p50 REAL,
            thin_fraction_under_5mm REAL,
            corrected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            applied_rule_id TEXT,
            FOREIGN KEY (applied_rule_id) REFERENCES learned_rules(id)
        )
    """)
    
    # Create indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_rules_status ON learned_rules(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_rules_pattern ON learned_rules(pattern) WHERE pattern IS NOT NULL")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_corrections_file ON correction_log(file_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_corrections_corrected_at ON correction_log(corrected_at)")
    
    conn.commit()
```

- [ ] **Step 4: Call create_learning_tables in init_db**

```python
# app/database.py - In init_db function
def init_db(settings: Settings):
    """Initialize database and create tables."""
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(settings.database_path)
    
    try:
        create_tables(conn)  # Existing table creation
        create_learning_tables(conn)  # ADD THIS LINE
    finally:
        conn.close()
```

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/test_learning_schema.py -v
```
Expected: PASS (2/2 tests)

- [ ] **Step 6: Commit**

```bash
git add app/database.py tests/test_learning_schema.py
git commit -m "feat: add learning system database schema"
```

---

### Task 2: Correction Logger Service

**Files:**
- Create: `app/services/correction_logger.py`
- Test: `tests/test_correction_logger.py`

- [ ] **Step 1: Write correction logger test**

```python
# tests/test_correction_logger.py
import pytest
from app.services.correction_logger import log_correction, get_corrections_since
from app.database import init_db
from app.config import get_settings
from datetime import datetime, timedelta

@pytest.fixture
def test_db():
    settings = get_settings()
    init_db(settings)
    return settings.database_path

def test_log_correction_creates_record(test_db):
    """Test that logging a correction creates a database record."""
    # Log a correction
    log_correction(
        file_name="test.stl",
        file_path="/path/to/test.stl",
        original_model_type="Ortho - Solid",
        corrected_model_type="Ortho - Hollow",
        original_confidence="medium",
        dimensions={"x_mm": 50.0, "y_mm": 40.0, "z_mm": 30.0},
        volume_ml=35.5,
        fill_ratio=0.30,
        thickness_p50=4.5
    )
    
    # Verify it was logged
    corrections = get_corrections_since(hours=1)
    
    assert len(corrections) == 1
    assert corrections[0].file_name == "test.stl"
    assert corrections[0].corrected_model_type == "Ortho - Hollow"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_correction_logger.py::test_log_correction_creates_record -v
```
Expected: FAIL - module doesn't exist

- [ ] **Step 3: Create correction logger service**

```python
# app/services/correction_logger.py
"""
Correction Logger - Captures user corrections for learning.

Logs every classification correction with metrics snapshot.
"""
import sqlite3
import json
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from ..config import get_settings


@dataclass
class Correction:
    """Represents a classification correction."""
    id: str
    file_name: str
    file_path: str
    original_model_type: Optional[str]
    corrected_model_type: str
    original_confidence: Optional[str]
    dimensions: Optional[Dict[str, float]]
    volume_ml: Optional[float]
    fill_ratio: Optional[float]
    thickness_p50: Optional[float]
    thin_fraction_under_5mm: Optional[float]
    corrected_at: datetime
    applied_rule_id: Optional[str]


def log_correction(
    file_name: str,
    file_path: str,
    original_model_type: Optional[str],
    corrected_model_type: str,
    original_confidence: Optional[str],
    dimensions: Optional[Dict[str, float]] = None,
    volume_ml: Optional[float] = None,
    fill_ratio: Optional[float] = None,
    thickness_p50: Optional[float] = None,
    thin_fraction_under_5mm: Optional[float] = None,
    applied_rule_id: Optional[str] = None,
) -> str:
    """
    Log a classification correction.
    
    Args:
        file_name: Original filename
        file_path: Full path to stored file
        original_model_type: Original classification (before correction)
        corrected_model_type: New classification (after correction)
        original_confidence: Original confidence level
        dimensions: Bounding box dimensions snapshot
        volume_ml: Volume in mL
        fill_ratio: Fill ratio at time of correction
        thickness_p50: Thickness P50 at time of correction
        applied_rule_id: If correction was due to learned rule
    """
    settings = get_settings()
    conn = sqlite3.connect(settings.database_path)
    
    try:
        cursor = conn.cursor()
        
        correction_id = str(uuid.uuid4())
        
        cursor.execute("""
            INSERT INTO correction_log (
                id, file_name, file_path, original_model_type,
                corrected_model_type, original_confidence,
                dimensions_json, volume_ml, fill_ratio,
                thickness_p50, thin_fraction_under_5mm,
                applied_rule_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            correction_id,
            file_name,
            file_path,
            original_model_type,
            corrected_model_type,
            original_confidence,
            json.dumps(dimensions) if dimensions else None,
            volume_ml,
            fill_ratio,
            thickness_p50,
            thin_fraction_under_5mm,
            applied_rule_id,
        ))
        
        conn.commit()
        return correction_id
        
    finally:
        conn.close()


def get_corrections_since(hours: int = 24) -> List[Correction]:
    """
    Get corrections from the last N hours.
    
    Args:
        hours: Number of hours to look back
        
    Returns:
        List of Correction objects
    """
    settings = get_settings()
    conn = sqlite3.connect(settings.database_path)
    
    try:
        cursor = conn.cursor()
        
        cutoff = datetime.now() - timedelta(hours=hours)
        
        cursor.execute("""
            SELECT 
                id, file_name, file_path, original_model_type,
                corrected_model_type, original_confidence,
                dimensions_json, volume_ml, fill_ratio,
                thickness_p50, thin_fraction_under_5mm,
                corrected_at, applied_rule_id
            FROM correction_log
            WHERE corrected_at >= ?
            ORDER BY corrected_at DESC
        """, (cutoff.isoformat(),))
        
        corrections = []
        for row in cursor.fetchall():
            corrections.append(Correction(
                id=row[0],
                file_name=row[1],
                file_path=row[2],
                original_model_type=row[3],
                corrected_model_type=row[4],
                original_confidence=row[5],
                dimensions=json.loads(row[6]) if row[6] else None,
                volume_ml=row[7],
                fill_ratio=row[8],
                thickness_p50=row[9],
                thin_fraction_under_5mm=row[10],
                corrected_at=datetime.fromisoformat(row[11]),
                applied_rule_id=row[12],
            ))
        
        return corrections
        
    finally:
        conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_correction_logger.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/correction_logger.py tests/test_correction_logger.py
git commit -m "feat: add correction logging service"
```

---

### Task 3: Pattern Detection Algorithm

**Files:**
- Create: `app/services/pattern_detector.py`
- Test: `tests/test_pattern_detector.py`

- [ ] **Step 1: Write pattern detection test**

```python
# tests/test_pattern_detector.py
import pytest
from app.services.pattern_detector import (
    extract_filename_patterns,
    detect_pattern_rules,
    detect_threshold_rules,
)
from app.services.correction_logger import Correction
from datetime import datetime

def test_extract_filename_patterns():
    """Test filename pattern extraction."""
    patterns = extract_filename_patterns("CASE123_Antag_UpperJaw.stl")
    
    # Should find common patterns
    assert any(p['pattern'] == 'antag' for p in patterns)
    assert any(p['pattern'] == 'upperjaw' for p in patterns)
    assert any(p['pattern_type'] == 'regex' for p in patterns)

def test_detect_pattern_rules():
    """Test pattern rule detection from corrections."""
    corrections = [
        Correction(
            id=str(i),
            file_name=f"test_antag_{i}.stl",
            file_path="/path/to/file.stl",
            original_model_type="Ortho - Hollow",
            corrected_model_type="Antagonist - Hollow",
            original_confidence="medium",
            dimensions=None,
            volume_ml=None,
            fill_ratio=None,
            thickness_p50=None,
            thin_fraction_under_5mm=None,
            corrected_at=datetime.now(),
            applied_rule_id=None,
        )
        for i in range(5)
    ]
    
    rules = detect_pattern_rules(corrections)
    
    assert len(rules) > 0
    assert any('antag' in str(r.get('pattern', '')).lower() for r in rules)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_pattern_detector.py -v
```
Expected: FAIL - module doesn't exist

- [ ] **Step 3: Create pattern detector service**

```python
# app/services/pattern_detector.py
"""
Pattern Detector - Finds patterns in corrections for rule generation.

Extracts filename patterns and metric clusters from correction history.
"""
import re
from typing import List, Dict, Any, Optional
from collections import defaultdict
from .correction_logger import Correction


def extract_filename_patterns(filename: str) -> List[Dict[str, str]]:
    """
    Extract candidate patterns from filename.
    
    Args:
        filename: STL filename to analyze
        
    Returns:
        List of pattern dictionaries with 'pattern' and 'pattern_type' keys
    """
    patterns = []
    name_lower = filename.lower()
    
    # Substring patterns (3-15 chars)
    for i in range(len(name_lower) - 2):
        for j in range(i + 3, min(i + 15, len(name_lower))):
            substring = name_lower[i:j]
            # Skip if contains non-alphanumeric (except underscore)
            if all(c.isalnum() or c == '_' for c in substring):
                patterns.append({
                    "pattern": substring,
                    "pattern_type": "substring"
                })
    
    # Common regex patterns for dental files
    regex_patterns = [
        r"CASE\d+",
        r"Antag\w*",
        r"UpperJaw",
        r"LowerJaw",
        r"Tooth_\d+",
        r"UnsectionedModel",
        r"Splint",
        r"Die",
    ]
    
    for regex in regex_patterns:
        if re.search(regex, filename, re.IGNORECASE):
            patterns.append({
                "pattern": regex,
                "pattern_type": "regex"
            })
    
    return patterns


def detect_pattern_rules(corrections: List[Correction]) -> List[Dict[str, Any]]:
    """
    Detect pattern-based rules from corrections.
    
    Args:
        corrections: List of corrections to analyze
        
    Returns:
        List of rule dictionaries ready for database insertion
    """
    # Group corrections by corrected_model_type
    by_model_type = defaultdict(list)
    for correction in corrections:
        by_model_type[correction.corrected_model_type].append(correction)
    
    rules = []
    
    for model_type, group in by_model_type.items():
        if len(group) < 3:  # Need minimum 3 corrections
            continue
        
        # Count pattern occurrences
        pattern_counts = defaultdict(int)
        
        for correction in group:
            patterns = extract_filename_patterns(correction.file_name)
            for pattern in patterns:
                key = f"{pattern['pattern']}::{pattern['pattern_type']}"
                pattern_counts[key] += 1
        
        # Create rules for patterns that appear in ≥60% of corrections
        for pattern_key, count in pattern_counts.items():
            if count >= 3 and count / len(group) >= 0.60:
                pattern, pattern_type = pattern_key.split('::')
                
                rules.append({
                    "type": "pattern",
                    "pattern": pattern,
                    "pattern_type": pattern_type,
                    "target_model_type": model_type,
                    "corrections_count": count,
                    "total_occurrences": len(group),
                    "success_rate": count / len(group),
                })
    
    return rules


def detect_threshold_rules(corrections: List[Correction]) -> List[Dict[str, Any]]:
    """
    Detect threshold adjustment rules from corrections.
    
    Finds clusters of corrections in metric space.
    
    Args:
        corrections: List of corrections to analyze
        
    Returns:
        List of rule dictionaries
    """
    # Group by artifact type and original decision
    groups = defaultdict(list)
    for correction in corrections:
        key = (correction.original_model_type, correction.corrected_model_type)
        groups[key].append(correction)
    
    rules = []
    
    for (original_type, corrected_type), group in groups.items():
        if len(group) < 3:
            continue
        
        # Collect metrics
        fill_ratios = [c.fill_ratio for c in group if c.fill_ratio is not None]
        thickness_p50 = [c.thickness_p50 for c in group if c.thickness_p50 is not None]
        
        if not fill_ratios or not thickness_p50:
            continue
        
        # Create threshold rule
        rules.append({
            "type": "threshold_adjustment",
            "condition": {
                "fill_ratio": {
                    "min": min(fill_ratios),
                    "max": max(fill_ratios)
                },
                "thickness_p50": {
                    "min": min(thickness_p50),
                    "max": max(thickness_p50)
                }
            },
            "target_model_type": corrected_type,
            "corrections_count": len(group),
            "total_occurrences": len(group),
            "success_rate": 1.0,  # All were corrections to same type
        })
    
    return rules
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_pattern_detector.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/pattern_detector.py tests/test_pattern_detector.py
git commit -m "feat: add pattern detection algorithm"
```

---

### Task 4: Rule Generator & Learning Engine

**Files:**
- Create: `app/services/learning_engine.py`
- Test: `tests/test_learning_engine.py`

- [ ] **Step 1: Write learning engine test**

```python
# tests/test_learning_engine.py
import pytest
from app.services.learning_engine import (
    run_pattern_detection,
    create_learned_rule,
    get_pending_rules,
    approve_rule,
    reject_rule,
)
from app.database import init_db
from app.config import get_settings

@pytest.fixture
def test_db():
    settings = get_settings()
    init_db(settings)
    return settings.database_path

def test_create_learned_rule(test_db):
    """Test creating a learned rule."""
    rule_id = create_learned_rule(
        rule_type="pattern",
        pattern="antag",
        pattern_type="substring",
        target_model_type="Antagonist - Hollow",
        confidence_level="high",
        corrections_count=5,
    )
    
    assert rule_id is not None
    
    # Verify rule is in pending status
    pending = get_pending_rules()
    assert any(r.id == rule_id for r in pending)

def test_approve_rule(test_db):
    """Test approving a learned rule."""
    rule_id = create_learned_rule(
        rule_type="pattern",
        pattern="test",
        pattern_type="substring",
        target_model_type="Ortho - Solid",
        confidence_level="medium",
        corrections_count=3,
    )
    
    # Approve the rule
    approve_rule(rule_id)
    
    # Verify status changed to active
    pending = get_pending_rules()
    assert not any(r.id == rule_id for r in pending)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_learning_engine.py -v
```
Expected: FAIL

- [ ] **Step 3: Create learning engine service**

```python
# app/services/learning_engine.py
"""
Learning Engine - Main orchestrator for classification learning.

Coordinates pattern detection, rule generation, and rule application.
"""
import uuid
import json
from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from ..database import get_db_connection
from .correction_logger import get_corrections_since, Correction
from .pattern_detector import detect_pattern_rules, detect_threshold_rules


@dataclass
class LearnedRule:
    """Represents a learned classification rule."""
    id: str
    rule_type: str
    pattern: Optional[str]
    pattern_type: Optional[str]
    condition_json: Optional[str]
    target_model_type: str
    confidence_level: str
    corrections_count: int
    status: str
    created_at: datetime
    approved_at: Optional[datetime]


def compute_confidence_level(corrections_count: int, success_rate: float) -> str:
    """
    Compute confidence level from corrections and success rate.
    
    Args:
        corrections_count: Number of corrections supporting this rule
        success_rate: Success rate (0.0 to 1.0)
        
    Returns:
        Confidence level: 'high', 'medium', or 'low'
    """
    if corrections_count >= 5 and success_rate >= 0.80:
        return "high"
    elif corrections_count >= 3 and success_rate >= 0.60:
        return "medium"
    else:
        return "low"


def create_learned_rule(
    rule_type: str,
    target_model_type: str,
    pattern: Optional[str] = None,
    pattern_type: Optional[str] = None,
    condition: Optional[Dict[str, Any]] = None,
    confidence_level: str = "low",
    corrections_count: int = 0,
) -> str:
    """
    Create a new learned rule.
    
    Args:
        rule_type: 'pattern' or 'threshold_adjustment'
        target_model_type: Model type to classify as
        pattern: Pattern string (for pattern rules)
        pattern_type: Pattern type (substring, regex, prefix, suffix)
        condition: Condition dict (for threshold rules)
        confidence_level: 'high', 'medium', or 'low'
        corrections_count: Number of corrections supporting this rule
        
    Returns:
        Rule ID
    """
    conn = get_db_connection()
    
    try:
        cursor = conn.cursor()
        
        rule_id = str(uuid.uuid4())
        
        cursor.execute("""
            INSERT INTO learned_rules (
                id, rule_type, pattern, pattern_type,
                condition_json, target_model_type,
                confidence_level, corrections_count, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')
        """, (
            rule_id,
            rule_type,
            pattern,
            pattern_type,
            json.dumps(condition) if condition else None,
            target_model_type,
            confidence_level,
            corrections_count,
        ))
        
        conn.commit()
        return rule_id
        
    finally:
        conn.close()


def get_pending_rules() -> List[LearnedRule]:
    """Get all pending rules awaiting approval."""
    conn = get_db_connection()
    
    try:
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, rule_type, pattern, pattern_type,
                   condition_json, target_model_type,
                   confidence_level, corrections_count,
                   status, created_at, approved_at
            FROM learned_rules
            WHERE status = 'pending'
            ORDER BY corrections_count DESC, created_at DESC
        """)
        
        rules = []
        for row in cursor.fetchall():
            rules.append(LearnedRule(
                id=row[0],
                rule_type=row[1],
                pattern=row[2],
                pattern_type=row[3],
                condition_json=row[4],
                target_model_type=row[5],
                confidence_level=row[6],
                corrections_count=row[7],
                status=row[8],
                created_at=datetime.fromisoformat(row[9]) if row[9] else None,
                approved_at=datetime.fromisoformat(row[10]) if row[10] else None,
            ))
        
        return rules
        
    finally:
        conn.close()


def approve_rule(rule_id: str) -> bool:
    """
    Approve a learned rule (activate it).
    
    Args:
        rule_id: Rule ID to approve
        
    Returns:
        True if approved successfully
    """
    conn = get_db_connection()
    
    try:
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE learned_rules
            SET status = 'active', approved_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status = 'pending'
        """, (rule_id,))
        
        conn.commit()
        return cursor.rowcount > 0
        
    finally:
        conn.close()


def reject_rule(rule_id: str) -> bool:
    """
    Reject a learned rule.
    
    Args:
        rule_id: Rule ID to reject
        
    Returns:
        True if rejected successfully
    """
    conn = get_db_connection()
    
    try:
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE learned_rules
            SET status = 'rejected'
            WHERE id = ? AND status = 'pending'
        """, (rule_id,))
        
        conn.commit()
        return cursor.rowcount > 0
        
    finally:
        conn.close()


def run_pattern_detection() -> List[str]:
    """
    Run pattern detection on recent corrections.
    
    Creates draft rules for patterns found in last 24 hours.
    
    Returns:
        List of created rule IDs
    """
    # Get corrections from last 24 hours
    corrections = get_corrections_since(hours=24)
    
    if len(corrections) < 3:
        return []  # Not enough data
    
    created_rule_ids = []
    
    # Detect pattern rules
    pattern_rules = detect_pattern_rules(corrections)
    
    for rule_data in pattern_rules:
        confidence = compute_confidence_level(
            rule_data['corrections_count'],
            rule_data['success_rate']
        )
        
        rule_id = create_learned_rule(
            rule_type="pattern",
            pattern=rule_data['pattern'],
            pattern_type=rule_data['pattern_type'],
            target_model_type=rule_data['target_model_type'],
            confidence_level=confidence,
            corrections_count=rule_data['corrections_count'],
        )
        
        created_rule_ids.append(rule_id)
    
    # Detect threshold rules
    threshold_rules = detect_threshold_rules(corrections)
    
    for rule_data in threshold_rules:
        confidence = compute_confidence_level(
            rule_data['corrections_count'],
            rule_data['success_rate']
        )
        
        rule_id = create_learned_rule(
            rule_type="threshold_adjustment",
            condition=rule_data['condition'],
            target_model_type=rule_data['target_model_type'],
            confidence_level=confidence,
            corrections_count=rule_data['corrections_count'],
        )
        
        created_rule_ids.append(rule_id)
    
    return created_rule_ids
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_learning_engine.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/learning_engine.py tests/test_learning_engine.py
git commit -m "feat: add learning engine and rule management"
```

---

### Task 5: Apply Learned Rules in Classification

**Files:**
- Modify: `app/services/classification.py:1-100`
- Test: `tests/test_learned_rules.py`

- [ ] **Step 1: Write test for learned rule application**

```python
# tests/test_learned_rules.py
import pytest
from app.services.classification import (
    classify_saved_upload,
    get_matching_learned_rule,
    apply_learned_rule,
)
from app.services.learning_engine import create_learned_rule
from app.database import init_db
from app.config import get_settings
from pathlib import Path

@pytest.fixture
def test_db():
    settings = get_settings()
    init_db(settings)
    return settings

def test_pattern_rule_applied(test_db):
    """Test that pattern rules are applied before default logic."""
    # Create a learned rule
    create_learned_rule(
        rule_type="pattern",
        pattern="antag",
        pattern_type="substring",
        target_model_type="Antagonist - Hollow",
        confidence_level="high",
        corrections_count=5,
    )
    
    # Create a test STL file
    test_stl = test_db.uploads_dir / "test_antag.stl"
    test_stl.write_bytes(b"solid test\nendsolid")
    
    # Classify - should match learned rule
    result = classify_saved_upload(test_stl, "test_antag.stl")
    
    assert result.model_type == "Antagonist - Hollow"
    assert "Learned rule" in result.classification_reason
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_learned_rules.py::test_pattern_rule_applied -v
```
Expected: FAIL - functions don't exist yet

- [ ] **Step 3: Add learned rule matching to classification.py**

```python
# app/services/classification.py - Add imports at top
from .learning_engine import get_active_learned_rules, LearnedRule

# Add new functions before classify_saved_upload
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
    import re
    
    if rule.pattern_type == "substring":
        return rule.pattern.lower() in filename.lower()
    elif rule.pattern_type == "regex":
        return bool(re.search(rule.pattern, filename, re.IGNORECASE))
    elif rule.pattern_type == "prefix":
        return filename.lower().startswith(rule.pattern.lower())
    elif rule.pattern_type == "suffix":
        return filename.lower().endswith(rule.pattern.lower())
    return False


def matches_threshold_rule(file_path: Path, rule: LearnedRule) -> bool:
    """Check if file metrics match threshold rule."""
    import json
    from core.batch_optimizer import get_stl_dimensions, get_stl_volume_ml
    
    if not rule.condition_json:
        return False
    
    condition = json.loads(rule.condition_json)
    
    # Get file metrics
    dims = get_stl_dimensions(str(file_path))
    volume_ml = get_stl_volume_ml(str(file_path))
    
    if not dims or volume_ml is None:
        return False
    
    # Calculate fill ratio
    bbox_volume = (dims.x_mm * dims.y_mm * dims.z_mm) / 1000.0
    fill_ratio = volume_ml / bbox_volume if bbox_volume > 0 else 0
    
    # Check if metrics fall within rule conditions
    if "fill_ratio" in condition:
        fr = condition["fill_ratio"]
        if not (fr.get("min", 0) <= fill_ratio <= fr.get("max", 1)):
            return False
    
    # Add thickness checks when implemented
    
    return True


def apply_learned_rule(
    stored_path: Path,
    original_filename: str,
    rule: LearnedRule,
) -> ClassificationRow:
    """Apply a learned rule and return classification result."""
    # Create basic classification from rule
    return ClassificationRow(
        file_name=original_filename,
        case_id=None,  # Will be extracted separately
        model_type=rule.target_model_type,
        preset=rule.target_model_type,
        confidence=rule.confidence_level,
        status="Ready" if rule.confidence_level == "high" else "Check",
        review_required=(rule.confidence_level != "high"),
        review_reason=f"Learned rule: {rule.id}",
        classification_reason=f"Learned rule: {rule.id}",
    )
```

- [ ] **Step 4: Modify classify_saved_upload to use learned rules**

```python
# app/services/classification.py - In classify_saved_upload function
def classify_saved_upload(stored_path: Path, original_filename: str) -> ClassificationRow:
    """
    Classify a saved STL file.
    
    Enhanced to apply learned rules before default logic.
    """
    validation = validate_stl_file(str(stored_path))
    if not validation.is_valid:
        raise ValueError(validation.message)

    # Step 1: Check learned rules (highest priority)
    learned_rule = get_matching_learned_rule(original_filename, stored_path)
    
    if learned_rule and learned_rule.confidence_level == "high":
        # Auto-apply high-confidence rules
        result = apply_learned_rule(stored_path, original_filename, learned_rule)
        log_rule_application(learned_rule.id, original_filename, result.model_type)
        return result

    # Step 2: Run default classification logic
    dimensions = get_stl_dimensions(str(stored_path))
    volume_ml = get_stl_volume_ml(str(stored_path))
    artifact = classify_artifact(original_filename, dims=dimensions)
    thickness_stats = measure_mesh_thickness_stats(str(stored_path))
    structure = resolve_ortho_structure(
        artifact,
        dims=dimensions,
        volume_ml=volume_ml,
        thickness_stats=thickness_stats,
    )
    model_type = infer_phase0_model_type(original_filename, artifact, structure)
    preset = default_preset(model_type)
    review_required = bool(artifact.review_required or artifact.review_reason or model_type is None)
    confidence = derive_confidence(
        model_type,
        artifact.confidence,
        artifact.case_id,
        upstream_review_required=review_required,
    )

    # ... rest of existing function ...
```

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/test_learned_rules.py -v
```
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/classification.py tests/test_learned_rules.py
git commit -m "feat: apply learned rules in classification pipeline"
```

---

### Task 6: Learning Queue API Endpoints

**Files:**
- Create: `app/routers/learning.py`
- Test: `tests/test_learning_router.py`

- [ ] **Step 1: Write router test**

```python
# tests/test_learning_router.py
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.services.learning_engine import create_learned_rule

@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)

def test_list_pending_rules(client):
    """Test listing pending learned rules."""
    # Create a test rule
    create_learned_rule(
        rule_type="pattern",
        pattern="test",
        pattern_type="substring",
        target_model_type="Ortho - Solid",
        confidence_level="medium",
        corrections_count=3,
    )
    
    response = client.get("/api/learning/pending-rules")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0

def test_approve_rule(client):
    """Test approving a learned rule."""
    # Create a test rule
    rule_id = create_learned_rule(
        rule_type="pattern",
        pattern="test",
        pattern_type="substring",
        target_model_type="Ortho - Solid",
        confidence_level="medium",
        corrections_count=3,
    )
    
    response = client.post(f"/api/learning/rules/{rule_id}/approve")
    
    assert response.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_learning_router.py -v
```
Expected: FAIL

- [ ] **Step 3: Create learning router**

```python
# app/routers/learning.py
"""
Learning Queue API - Endpoints for managing learned rules.
"""
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any

from ..services.learning_engine import (
    get_pending_rules,
    get_active_learned_rules,
    approve_rule,
    reject_rule,
    run_pattern_detection,
    LearnedRule,
)

router = APIRouter(prefix="/api/learning", tags=["learning"])


@router.get("/pending-rules")
async def list_pending_rules() -> List[Dict[str, Any]]:
    """Get all pending learned rules awaiting approval."""
    rules = get_pending_rules()
    
    return [
        {
            "id": rule.id,
            "rule_type": rule.rule_type,
            "pattern": rule.pattern,
            "pattern_type": rule.pattern_type,
            "target_model_type": rule.target_model_type,
            "confidence_level": rule.confidence_level,
            "corrections_count": rule.corrections_count,
            "created_at": rule.created_at.isoformat() if rule.created_at else None,
        }
        for rule in rules
    ]


@router.get("/active-rules")
async def list_active_rules() -> List[Dict[str, Any]]:
    """Get all active learned rules."""
    rules = get_active_learned_rules()
    
    return [
        {
            "id": rule.id,
            "rule_type": rule.rule_type,
            "pattern": rule.pattern,
            "target_model_type": rule.target_model_type,
            "confidence_level": rule.confidence_level,
            "corrections_count": rule.corrections_count,
            "last_applied_at": rule.last_applied_at.isoformat() if rule.last_applied_at else None,
        }
        for rule in rules
    ]


@router.post("/rules/{rule_id}/approve")
async def approve_learned_rule(rule_id: str) -> Dict[str, str]:
    """Approve a learned rule (activate it)."""
    success = approve_rule(rule_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Rule not found or already processed")
    
    return {"status": "approved", "rule_id": rule_id}


@router.post("/rules/{rule_id}/reject")
async def reject_learned_rule(rule_id: str) -> Dict[str, str]:
    """Reject a learned rule."""
    success = reject_rule(rule_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Rule not found or already processed")
    
    return {"status": "rejected", "rule_id": rule_id}


@router.post("/detect-patterns")
async def trigger_pattern_detection() -> Dict[str, Any]:
    """Manually trigger pattern detection on recent corrections."""
    created_rule_ids = run_pattern_detection()
    
    return {
        "status": "completed",
        "rules_created": len(created_rule_ids),
        "rule_ids": created_rule_ids,
    }
```

- [ ] **Step 4: Register router in main.py**

```python
# app/main.py - Add import
from .routers.learning import router as learning_router

# Add router registration in create_app()
def create_app(settings: Settings | None = None) -> FastAPI:
    # ... existing code ...
    
    app.include_router(uploads_router)
    app.include_router(metrics_router)
    app.include_router(learning_router)  # ADD THIS
    
    # ... rest of code ...
```

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/test_learning_router.py -v
```
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/routers/learning.py tests/test_learning_router.py app/main.py
git commit -m "feat: add learning queue API endpoints"
```

---

## Verification Checklist

After completing all tasks, verify:

- [ ] **Database schema**: `learned_rules` and `correction_log` tables exist
- [ ] **Correction logging**: User corrections are logged with metrics snapshot
- [ ] **Pattern detection**: Nightly job detects patterns from corrections
- [ ] **Rule approval**: Pending rules visible in API, can approve/reject
- [ ] **Rule application**: Learned rules applied before default classification
- [ ] **All tests pass**: Run `pytest tests/test_learning*.py` - expect 100% pass rate
- [ ] **Server starts**: Run `uvicorn app.main:app --reload` - no import errors

---

## Execution Handoff

**Plan complete and saved to `Andent/02_planning/plans/2026-04-20-classification-learning-system-plan.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
