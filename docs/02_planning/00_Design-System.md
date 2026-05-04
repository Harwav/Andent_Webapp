# Andent Webapp Design System

**Version:** 1.0.0
**Last Updated:** 2026-04-21
**Scope:** Phase 0-1 UI/UX Consistency

---

## Table of Contents

1. [Design Tokens](#design-tokens)
2. [Component Patterns](#component-patterns)
3. [Status & Colors Mapping](#status--colors-mapping)
4. [Layout Patterns](#layout-patterns)
5. [Anti-Patterns](#anti-patterns)
6. [File Organization](#file-organization)

---

## Design Tokens

### CSS Variables

All design tokens are defined in `:root` at the top of `styles.css`:

```css
:root {
    --bg: #fefdf9;
    --surface: #ffffff;
    --surface-soft: #faf7f1;
    --ink: #111110;
    --muted: #706e6b;
    --line: #e8e5e0;
    --accent: #ff5a00;
    --accent-dark: #ca4700;
    --accent-soft: #fff3eb;
    --clear: #0c8d3a;
    --clear-soft: #edf9f0;
    --warn: #af6a00;
    --warn-soft: #fff6e7;
    --danger: #c63520;
    --danger-soft: #fff1ee;
    --info: #0864c7;
    --info-soft: #eff6ff;
    --shadow: 0 1px 3px rgba(0, 0, 0, 0.08), 0 8px 24px rgba(0, 0, 0, 0.06);
    --font-display: "Playfair Display", Georgia, serif;
    --font-ui: "Inter", "Helvetica Neue", sans-serif;
    --font-body: "Roboto", Arial, sans-serif;
}
```

### Color Palette

#### Background Colors

| Token | Hex | Usage |
|-------|-----|-------|
| `--bg` | `#fefdf9` | Page background, warm off-white |
| `--surface` | `#ffffff` | Cards, panels, modals |
| `--surface-soft` | `#faf7f1` | Subtle backgrounds, placeholders |

#### Text Colors

| Token | Hex | Usage |
|-------|-----|-------|
| `--ink` | `#111110` | Primary text, headings |
| `--muted` | `#706e6b` | Secondary text, labels, hints |

#### Border Colors

| Token | Hex | Usage |
|-------|-----|-------|
| `--line` | `#e8e5e0` | Borders, dividers, table lines |

#### Semantic Colors

| Token | Hex | Soft Variant | Usage |
|-------|-----|--------------|-------|
| `--accent` | `#ff5a00` | `--accent-soft` | Primary actions, brand color |
| `--accent-dark` | `#ca4700` | - | Hover states |
| `--clear` | `#0c8d3a` | `--clear-soft` | Success, ready states |
| `--warn` | `#af6a00` | `--warn-soft` | Warnings, attention needed |
| `--danger` | `#c63520` | `--danger-soft` | Errors, destructive actions |
| `--info` | `#0864c7` | `--info-soft` | Information, queued states |

### Typography

#### Font Families

| Token | Stack | Usage |
|-------|-------|-------|
| `--font-display` | `"Playfair Display", Georgia, serif` | Hero headings (H1) |
| `--font-ui` | `"Inter", "Helvetica Neue", sans-serif` | UI elements, buttons, labels |
| `--font-body` | `"Roboto", Arial, sans-serif` | Body text, paragraphs |

#### Type Scale

| Element | Font | Size | Weight | Line Height | Letter Spacing |
|---------|------|------|--------|-------------|----------------|
| H1 (Hero) | `--font-display` | `clamp(2.2rem, 4vw, 3.5rem)` | 400 (normal) | 1.08 | -0.02em |
| H2 (Section) | `--font-ui` | `1.35rem` | 700 | normal | -0.01em |
| Eyebrow | `--font-ui` | `0.75rem` | 700 | normal | 0.12em |
| Body | `--font-body` | `1rem` | 400 | 1.65 | normal |
| Lede | `--font-body` | `1rem` | 400 | 1.65 | normal |
| UI Label | `--font-ui` | `0.72rem` | 700 | normal | 0.1em |
| Button | `--font-ui` | `0.86rem` | 700 | normal | normal |
| Table Header | `--font-ui` | `0.72rem` | 700 | normal | 0.1em |
| Table Cell | `--font-body` | `0.88rem` | 400 | normal | normal |
| Status Chip | `--font-ui` | `0.78rem` | 700 | normal | normal |

#### Text Transform Patterns

- **Uppercase with letter-spacing:** Eyebrows, table headers, breadcrumbs (`text-transform: uppercase; letter-spacing: 0.1em`)
- **Normal case:** Body text, headings, buttons

### Spacing Scale

| Token | Value | Usage |
|-------|-------|-------|
| `--space-xs` | `4px` | Tight gaps, inline spacing |
| `--space-sm` | `6px` | Compact padding |
| `--space-md` | `8px` | Small gaps, icon spacing |
| `--space-lg` | `10px` | Form padding, cell padding |
| `--space-xl` | `12px` | Component gaps |
| `--space-2xl` | `14px` | Section margins |
| `--space-3xl` | `16px` | Card padding, button padding |
| `--space-4xl` | `18px` | Panel padding (mobile) |
| `--space-5xl` | `20px` | Panel margins |
| `--space-6xl` | `24px` | Header padding, panel padding |
| `--space-7xl` | `28px` | Hero margins |
| `--space-8xl` | `30px` | Empty state padding |
| `--space-9xl` | `32px` | Shell padding (mobile) |
| `--space-10xl` | `40px` | Dropzone padding, modal margin |
| `--space-11xl` | `56px` | Header height |
| `--space-12xl` | `72px` | Shell bottom padding |

### Shadows

| Token | Value | Usage |
|-------|-------|-------|
| `--shadow` | `0 1px 3px rgba(0,0,0,0.08), 0 8px 24px rgba(0,0,0,0.06)` | Panels, cards, modals |
| Hover shadow | `0 2px 6px rgba(255,90,0,0.08), 0 12px 32px rgba(0,0,0,0.08)` | Job card hover |
| Modal backdrop | `rgba(17,17,16,0.55)` | Modal overlay |

### Border Radius Scale

| Token | Value | Usage |
|-------|-------|-------|
| `--radius-sm` | `8px` | Buttons, inputs, selects |
| `--radius-md` | `10px` | Panels, tables |
| `--radius-lg` | `12px` | Dropzone, job cards |
| `--radius-xl` | `14px` | Preview viewers |
| `--radius-2xl` | `16px` | Modal cards |
| `--radius-full` | `999px` | Pills, chips, circular buttons |

---

## Component Patterns

### Buttons

#### Primary Button

```css
.primary-button {
    background: var(--accent);
    color: #fff;
    border-radius: 8px;
    padding: 10px 16px;
    font-size: 0.86rem;
    font-weight: 700;
    font-family: var(--font-ui);
    border: none;
    cursor: pointer;
}

.primary-button:hover:not(:disabled) {
    background: var(--accent-dark);
}
```

**Usage:** Main call-to-action actions ("Select Folder", "Send to Print")

#### Secondary Button

```css
.secondary-button {
    background: var(--accent-soft);
    color: var(--accent-dark);
    border-radius: 8px;
    padding: 10px 16px;
    font-size: 0.86rem;
    font-weight: 700;
    font-family: var(--font-ui);
    border: none;
    cursor: pointer;
}
```

**Usage:** Alternative actions, bulk operations ("Change Model Type", "Undo Delete")

#### Ghost Button

```css
.ghost-button {
    background: #f4f1eb;
    color: var(--ink);
    border-radius: 8px;
    padding: 10px 16px;
    font-size: 0.86rem;
    font-weight: 700;
    font-family: var(--font-ui);
    border: none;
    cursor: pointer;
}
```

**Usage:** Cancel actions, pagination, low-priority actions

#### Tab Button

```css
.tab-button {
    background: #f4f1eb;
    color: var(--ink);
    border-radius: 8px;
    padding: 10px 16px;
    font-size: 0.86rem;
    font-weight: 700;
    font-family: var(--font-ui);
    border: none;
    cursor: pointer;
}

.tab-button-active {
    background: var(--ink);
    color: #fff;
}
```

**Usage:** Navigation tabs (Active, Processed, Print Queue)

### Tables

#### Data Table

```css
.data-table {
    width: 100%;
    border-collapse: collapse;
    table-layout: fixed;
}

.data-table th,
.data-table td {
    padding: 12px 10px;
    border-bottom: 1px solid var(--line);
    text-align: left;
    vertical-align: top;
    font-size: 0.88rem;
}

.data-table th {
    color: var(--muted);
    font-family: var(--font-ui);
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
}

.data-table tbody tr:hover td {
    background: #fcfaf6;
}
```

**Table Variants:**
- `.active-table` - 10 columns with specific widths
- `.processed-table` - 9 columns with specific widths

### Panels

```css
.panel {
    margin-top: 20px;
    padding: 24px;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 10px;
    box-shadow: var(--shadow);
}
```

**Usage:** Content containers, form sections, results areas

### Modals

#### Modal Container

```css
.modal {
    position: fixed;
    inset: 0;
    z-index: 50;
}

.modal-backdrop {
    position: absolute;
    inset: 0;
    background: rgba(17, 17, 16, 0.55);
}

.modal-card {
    position: relative;
    width: min(960px, calc(100vw - 32px));
    margin: 40px auto;
    padding: 24px;
    border-radius: 16px;
    background: var(--surface);
    box-shadow: var(--shadow);
}

.modal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 16px;
}
```

**Modal Variants:**
- `.screenshot-modal-card` - Max-width 720px for screenshot previews

### Form Elements

#### Select Dropdown

```css
select {
    width: 100%;
    min-width: 0;
    padding: 8px 10px;
    border: 1px solid var(--line);
    border-radius: 8px;
    background: #fff;
    color: var(--ink);
    font-family: var(--font-body);
    font-size: 0.88rem;
}

select:focus {
    outline: 2px solid rgba(255, 90, 0, 0.18);
    border-color: var(--accent);
}
```

**Usage:** Model type selection, preset selection, bulk operations

### Status Chips

```css
.status-chip {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 92px;
    padding: 6px 10px;
    border-radius: 999px;
    font-family: var(--font-ui);
    font-size: 0.78rem;
    font-weight: 700;
}
```

**Status Variants:**

```css
/* Ready, Submitted */
.status-ready,
.status-submitted {
    background: var(--clear-soft);
    color: var(--clear);
}

/* Check, Analyzing, Uploading */
.status-check,
.status-analyzing,
.status-uploading {
    background: var(--warn-soft);
    color: var(--warn);
}

/* Needs Review, Duplicate, Locked */
.status-needs-review,
.status-duplicate,
.status-locked {
    background: var(--danger-soft);
    color: var(--danger);
}

/* Queued */
.status-queued {
    background: var(--info-soft);
    color: var(--info);
}
```

### Cards

#### Job Card (Phase 1)

```css
.job-card {
    display: flex;
    gap: 16px;
    padding: 16px;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 12px;
    box-shadow: var(--shadow);
    transition: border-color 160ms ease, box-shadow 160ms ease;
}

.job-card:hover {
    border-color: var(--accent);
    box-shadow: 0 2px 6px rgba(255, 90, 0, 0.08), 0 12px 32px rgba(0, 0, 0, 0.08);
}
```

**Card Structure:**
- `.job-screenshot` - Thumbnail area
- `.job-info` - Content area
- `.job-header` - Title and status
- `.job-cases` - Expandable case list
- `.job-details` - Metadata grid

### Thumbnails

```css
.thumbnail-button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 64px;
    height: 64px;
    padding: 0;
    overflow: hidden;
    border-radius: 12px;
    background: var(--surface-soft);
    border: 1px solid var(--line);
}

.thumbnail-placeholder {
    display: grid;
    place-items: center;
    width: 100%;
    height: 100%;
    padding: 6px;
    color: var(--muted);
    font-family: var(--font-ui);
    font-size: 0.72rem;
    text-align: center;
}
```

### Dropzone

```css
.dropzone {
    padding: 40px 24px;
    text-align: center;
    border: 2px dashed #d9d2c7;
    border-radius: 12px;
    background: linear-gradient(180deg, #fbf8f2 0%, #f8f4ec 100%);
    cursor: pointer;
    transition: border-color 160ms ease, background 160ms ease, transform 160ms ease;
}

.dropzone:hover,
.dropzone-active {
    border-color: var(--accent);
    background: linear-gradient(180deg, #fff7f1 0%, #fff2ea 100%);
}
```

### Empty State

```css
.empty-state {
    padding: 30px;
    text-align: center;
    border: 1px dashed var(--line);
    border-radius: 10px;
    background: var(--surface-soft);
    color: var(--muted);
}
```

---

## Status & Colors Mapping

### Active Queue Statuses

| Status | Color Token | CSS Class | Semantic Meaning |
|--------|-------------|-----------|------------------|
| Ready | `--clear` | `.status-ready` | File is ready for print submission |
| Check | `--warn` | `.status-check` | Needs manual review before proceeding |
| Needs Review | `--danger` | `.status-needs-review` | Classification failed or uncertain |
| Submitted | `--clear` | `.status-submitted` | Successfully sent to print queue |
| Duplicate | `--danger` | `.status-duplicate` | Potential duplicate file detected |
| Queued | `--info` | `.status-queued` | Waiting for upload processing |
| Uploading | `--warn` | `.status-uploading` | Currently uploading to server |
| Analyzing | `--warn` | `.status-analyzing` | STL analysis in progress |
| Locked | `--danger` | `.status-locked` | Row is locked for editing |

### Print Queue Job Statuses

| Status | Color Token | CSS Class | Semantic Meaning |
|--------|-------------|-----------|------------------|
| Queued | `--info` | `.job-status-queued` | Job waiting to print |
| Printing | `--warn` | `.job-status-printing` | Currently printing |
| Failed | `--danger` | `.job-status-failed` | Print job failed |
| Paused | `--muted` | `.job-status-paused` | Print job paused |
| Completed | `--clear` | `.job-status-completed` | Print job finished successfully |

### Color Usage Guidelines

- **Green (`--clear`)**: Success, completion, ready states
- **Yellow (`--warn`)**: In-progress, attention needed, warnings
- **Red (`--danger`)**: Errors, failures, blocks, destructive actions
- **Blue (`--info`)**: Informational, queued, neutral progress
- **Gray (`--muted`)**: Paused, inactive, placeholder states

---

## Layout Patterns

### Container System

#### Shell (Main Container)

```css
.shell {
    max-width: 1400px;
    margin: 0 auto;
    padding: 40px 24px 72px;
}
```

**Usage:** Wraps all main content, provides consistent horizontal padding

#### Site Header

```css
.site-header {
    position: sticky;
    top: 0;
    z-index: 10;
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 56px;
    padding: 0 24px;
    background: var(--bg);
    border-bottom: 1px solid var(--line);
}
```

### Grid System

#### Job Cards Grid

```css
.job-cards-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: 16px;
    margin-top: 14px;
}
```

**Behavior:** Responsive grid that fills available space with minimum 320px columns

#### Job Details Grid

```css
.job-details {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
}
```

### Flex Patterns

#### Toolbar Pattern

```css
.toolbar {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
    justify-content: space-between;
    margin-top: 16px;
}
```

#### Actions Pattern

```css
.actions {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
    justify-content: space-between;
    margin-top: 16px;
}
```

### Responsive Breakpoints

| Breakpoint | Width | Behavior |
|------------|-------|----------|
| Desktop | > 1100px | Full layout, multi-column tables |
| Tablet | 720px - 1100px | Reduced padding, adjusted grids |
| Mobile | < 720px | Single column, stacked layouts |

#### Mobile Adaptations (max-width: 1100px)

```css
@media (max-width: 1100px) {
    .shell {
        padding: 32px 16px 56px;
    }

    .panel {
        padding: 18px;
    }

    /* Tables become cards */
    .data-table,
    .data-table thead,
    .data-table tbody,
    .data-table tr,
    .data-table th,
    .data-table td {
        display: block;
        width: 100% !important;
    }

    .data-table thead {
        display: none;
    }

    /* Job cards stack */
    .job-cards-grid {
        grid-template-columns: 1fr;
    }

    .job-card {
        flex-direction: column;
    }
}
```

### Z-Index Scale

| Element | Z-Index |
|---------|---------|
| Site header | 10 |
| Modal | 50 |

---

## Anti-Patterns

### Colors

**DON'T:** Use hardcoded hex values in new components

```css
/* WRONG */
.my-component {
    background: #ff5a00;
    color: #111110;
}

/* RIGHT */
.my-component {
    background: var(--accent);
    color: var(--ink);
}
```

**DON'T:** Create new status colors without documenting them

If a new status requires a color not in the palette, add it to the design system first.

**DON'T:** Use semantic colors for non-semantic purposes

```css
/* WRONG - using danger red for branding */
.logo {
    color: var(--danger);
}

/* RIGHT - use accent for branding */
.logo {
    color: var(--accent);
}
```

### Components

**DON'T:** Modify existing component classes directly

```css
/* WRONG - modifying .primary-button globally */
.primary-button {
    padding: 20px; /* This affects all primary buttons */
}

/* RIGHT - extend with a modifier class */
.primary-button-large {
    padding: 20px;
}
```

**DON'T:** Create one-off component styles

```css
/* WRONG - inline styles or one-off classes */
<div style="padding: 15px; background: #fff;">

/* RIGHT - use existing panel component */
<div class="panel">
```

**DON'T:** Override component styles with high-specificity selectors

```css
/* WRONG - hard to maintain */
body > main > section > .panel {
    padding: 50px;
}

/* RIGHT - use modifier class */
.panel-large {
    padding: 32px;
}
```

### Layout

**DON'T:** Use magic numbers for spacing

```css
/* WRONG */
.my-element {
    margin-top: 17px;
}

/* RIGHT - use consistent spacing */
.my-element {
    margin-top: 16px;
}
```

**DON'T:** Break the container system

```css
/* WRONG */
.full-bleed {
    width: 100vw;
    margin-left: calc(-50vw + 50%);
}

/* RIGHT - work within shell constraints */
.shell {
    max-width: 1400px;
}
```

---

## File Organization

### CSS Organization Rules

1. **Design tokens first:** All CSS variables in `:root` at the top
2. **Base styles next:** Reset, body, typography
3. **Layout components:** Header, shell, containers
4. **UI components:** Buttons, forms, tables, cards
5. **Page-specific:** Modals, dropzone, print queue
6. **Responsive last:** Media queries at the bottom

### Naming Conventions

#### BEM-like Structure

```css
/* Block */
.panel { }

/* Block with modifier */
.panel-large { }

/* Element */
.panel-header { }

/* Element with modifier */
.panel-header-sticky { }
```

#### Prefix Conventions

| Prefix | Usage | Example |
|--------|-------|---------|
| `site-` | Global/site-wide components | `.site-header`, `.site-logo` |
| `job-` | Job-specific components | `.job-card`, `.job-status` |
| `status-` | Status indicators | `.status-chip`, `.status-ready` |
| `data-` | Data display components | `.data-table` |
| `modal-` | Modal components | `.modal-card`, `.modal-backdrop` |

#### State Classes

| Pattern | Usage | Example |
|---------|-------|---------|
| `-active` | Active/selected state | `.tab-button-active` |
| `-hidden` | Visibility toggle | `.hidden` |
| `-pending` | Temporary state | `.row-pending-delete` |
| `-empty` | Empty state | `.preview-empty` |

### File Structure

```
app/static/
├── index.html          # Main application HTML
├── app.js             # Application logic
├── styles.css         # All styles (single file)
└── metrics.html       # Metrics dashboard
```

**Note:** This project uses a single CSS file approach. All styles live in `styles.css`.

### Adding New Styles

When adding new components:

1. Check if an existing component can be extended
2. Follow the naming convention (BEM-like)
3. Use CSS variables for all colors, spacing, shadows
4. Add responsive styles in the media query section
5. Document the component in this design system

---

## Quick Reference

### Common Patterns

**Centered container with max-width:**
```css
.shell {
    max-width: 1400px;
    margin: 0 auto;
    padding: 40px 24px;
}
```

**Flex row with gap:**
```css
display: flex;
align-items: center;
gap: 12px;
```

**Status chip:**
```css
<span class="status-chip status-ready">Ready</span>
```

**Panel with shadow:**
```css
<div class="panel">
    <!-- Content -->
</div>
```

**Primary button:**
```css
<button type="button" class="primary-button">Action</button>
```

### Transition Defaults

```css
transition: border-color 160ms ease, box-shadow 160ms ease;
```

### Focus Ring

```css
outline: 2px solid rgba(255, 90, 0, 0.18);
border-color: var(--accent);
```

---

*End of Design System Documentation*
