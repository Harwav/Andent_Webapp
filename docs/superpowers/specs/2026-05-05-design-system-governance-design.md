# design.md — Full Component System Audit & Governance

**Date:** 2026-05-05
**Status:** Approved

---

## Context

The existing design system at `docs/02_planning/00_Design-System.md` is comprehensive but not consistently followed. Violations exist throughout the codebase (hardcoded hex values, inline styles, one-off classes). This feature: (1) audits all violations, (2) enhances the design doc with governance rules and enforcement checklists, (3) annotates CSS with design doc references.

---

## Changes

### Phase 1 — Full Codebase Audit

Scan all source files for violations:

**app/static/styles.css**
- Hardcoded hex outside `:root` (e.g., `#d9d2c7` in dropzone, gradient colors)
- Verify all colors reference CSS variables

**app/static/app.js**
- Inline style assignments (`.style.foo`)
- Hardcoded color values in JS
- One-off class creations not in design system

**app/static/index.html**
- Inline `style=` attributes
- One-off class names not in design system

**app/**/*.py** (if any inline styles or HTML templates)
- Jinja templates with hardcoded styles

**Output:** A list of violations with file paths and line numbers, filed as GitHub issues.

### Phase 2 — Enhance Design System Doc

Update `docs/02_planning/00_Design-System.md` with:

**A. Row/Table Governance Rules**
- When to use `.active-table` vs `.processed-table` vs other variants
- Column usage per context (which columns appear where)
- No ad-hoc column additions without design doc update

**B. "When to Use Which Component" Decision Tree**
```
Need a button? → Primary CTA → .primary-button
              → Secondary action → .secondary-button
              → Low priority / cancel → .ghost-button
              → Navigation tabs → .tab-button / .tab-button-active

Need a status indicator? → Use status chip variants
  Ready/Submitted → .status-ready
  Check/Analyzing → .status-check
  Needs Review/Duplicate → .status-needs-review
  Queued/Info → .status-queued

Need a card? → Job card → .job-card with .job-screenshot, .job-info, .job-details
Need a table? → Use .data-table with defined column classes
Need a panel? → .panel
```

**C. Anti-Patterns (expanded)**
- No hardcoded hex colors — all must reference CSS variables
- No inline `style=` attributes in HTML
- No `.style.foo` assignments in JS for structural styling (use CSS classes)
- No one-off CSS classes — extend existing components with modifier classes
- No magic numbers for spacing — use spacing scale tokens

**D. Enforcement Checklist**
```
Before merging any PR, reviewer checks:
□ No hardcoded hex colors (use CSS variables)
□ No inline style= attributes in HTML
□ No .style assignments for colors/borders/margins in JS
□ New components follow existing patterns (BEM prefix rules)
□ Spacing uses CSS variable tokens (--space-*)
□ Colors use semantic CSS variables (--accent, --clear, etc.)
□ No one-off classes — use modifier pattern
□ Responsive behavior follows breakpoints
□ Transitions use 160ms ease default or design doc values
```

**E. New Feature Checklist**
```
Adding a new component? Check:
□ Design token exists for color/spacing — if not, add to :root first
□ Component follows BEM naming with correct prefix
□ Status colors use semantic variables
□ Spacing uses --space-* tokens
□ Hover/focus states defined
□ Responsive styles at breakpoints
□ Documented in design system
```

### Phase 3 — CSS Annotation

Add section marker comments to `styles.css` referencing design doc sections:

```css
/* ============================================
   Design System: Component Patterns
   See: docs/02_planning/00_Design-System.md#component-patterns
   ============================================ */
```

Sections to annotate:
- Buttons
- Tables
- Panels
- Modals
- Form Elements
- Status Chips
- Cards
- Thumbnails
- Dropzone
- Empty States

---

## GitHub Issues to Create

1. **Audit report** — one issue listing all violations found (file:line:description)
2. **Design system update** — issue for enhancing the design doc with governance rules
3. **CSS annotation** — issue for adding design doc references to styles.css

---

## Files to Modify

| File | Change |
|------|--------|
| `docs/02_planning/00_Design-System.md` | Major update — governance rules, decision tree, checklists |
| `app/static/styles.css` | Add section marker comments referencing design doc |

---

## Outcome

- Full violation report (GitHub issue with checklist)
- Enhanced design system doc that serves as both reference AND enforcement guide
- CSS annotated so future contributors know which doc section governs each style block