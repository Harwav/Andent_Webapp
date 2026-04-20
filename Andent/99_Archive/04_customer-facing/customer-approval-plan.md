# Customer Discussion Plan: Standardizing Dental STL File Naming and File IDs

## Summary
- We reviewed the files in `20260409_Andent_Matt` and found that the folder already follows a partially structured naming system.
- The strongest stable identifier across nearly all files is a `7-8` digit numeric `case_id`.
- The rest of each filename mixes clinic name, patient name, restoration/work-type tags, shade/material tags, and artifact type, but the formatting is inconsistent.
- Recommendation: standardize filenames around `case_id` plus normalized artifact and tooth/jaw information, while preserving clinic and patient text for human handling.

## Findings From The Current Folder
- Current file families observed:
  - `YYYYMMDD_CASEID_...`
  - `YYYY-MM-DD_BATCH-SEQ-CASEID_...`
  - `CASEID_YYYY-MM-DD_...` for splints
  - `CASEID_...` legacy short form
- Current artifact classes observed:
  - Upper jaw model
  - Lower jaw model
  - Antagonist
  - Tooth artifact
  - Model base
  - Model die
  - Splint
- Current naming quality:
  - The numeric `case_id` is the most reliable workflow anchor.
  - Clinic/patient segments are inconsistent in separators and formatting.
  - Some files use full words such as `UnsectionedModel_UpperJaw`; others use short legacy forms such as `U`, `L`, `UPPER`, `LOWER`.
  - Tags such as `UT`, `MT`, `DD`, `pfm`, `OPAQUE`, `A3`, `C2`, `D2` appear meaningful and should be preserved until business rules define them.

## How Categorization Was Inferred
- Primary categorization was based on filename patterns:
  - `Tooth_46` => tooth artifact
  - `Antag` => antagonist
  - `UnsectionedModel_UpperJaw` / `LowerJaw` => jaw models
  - `modelbase` => model base
  - `modeldie` => model die
  - `bitesplint_cad` => splint
- Bounding box size was used as a secondary validation signal, not the primary classifier:
  - Tooth artifact and model die files are small and compact
  - Splints are full-arch but thinner
  - Model base files are full-arch and taller
  - Models and antagonists are full-arch with medium height
- Recommendation: use filename-driven classification first, then use bounding box as a fallback confidence check for misnamed or incomplete files.

## Options For The Standard
- Option 1: Minimal standard
  - Keep existing filenames.
  - Extract `case_id`, artifact class, jaw, tooth, and tags into a side manifest only.
  - Lowest disruption, but weaker long-term consistency.
- Option 2: Canonical filename standard
  - Rename files into one strict format.
  - Best for downstream routing, search, dedupe, and staff consistency.
  - Recommended option.
- Option 3: Hybrid standard
  - Keep a readable filename plus a separate canonical machine ID.
  - Good compromise, but introduces two naming systems.

## Recommended Standard
- Use `case_id` as the primary file ID for every dental STL.
- Use this canonical filename format:
  - `{case_id}__{artifact}__{arch_role}__{tooth_spec}__{export_date}__{clinic}__{patient}__{tags}.stl`
- Field definitions:
  - `artifact`: `model`, `antagonist`, `tooth-artifact`, `model-base`, `model-die`, `splint`
  - `arch_role`: `upper`, `lower`, `opposing`, `mixed`, `na`
  - `tooth_spec`: FDI tooth code or ordered list such as `46`, `25-26`, `11-21`, or `na`
  - `export_date`: normalized to `YYYYMMDD`
  - `clinic`: normalized clinic/lab text
  - `patient`: normalized patient text
  - `tags`: preserved remaining tokens such as `ut-a3`, `dd-a3`, `pfm`, `opaque`, `01635-642`
- Example outputs:
  - `8425405__tooth-artifact__lower__46__20260407__hobsons__julie__mt-a3.stl`
  - `8425405__model__lower__na__20260407__hobsons__julie__mt-a3.stl`
  - `8424555__splint__upper__17-16-15-14-13-12-11-21-22-23-24-25-26-27__20260402__unknown__unknown__01635-642.stl`

## Classification Rules
- Extract `case_id` from the first valid numeric job token in these priority patterns:
  - `YYYYMMDD_CASEID_`
  - `YYYY-MM-DD_BATCH-SEQ-CASEID_`
  - `CASEID_YYYY-MM-DD_`
  - `CASEID_`
- Detect artifact type from filename suffix:
  - `_UnsectionedModel_UpperJaw`, `_Model_UpperJaw`, `_UPPER`, `_U` => upper model
  - `_UnsectionedModel_LowerJaw`, `_Model_LowerJaw`, `_LOWER`, `_L` => lower model
  - `_Antag` => antagonist
  - `_Tooth_##` or `_Tooth_##-##` => tooth artifact
  - `-modelbase` => model base
  - `-modeldie` => model die
  - `-bitesplint_cad` or files in `Splints/` => splint
- Use mesh size only as a fallback validation layer, especially for legacy or malformed filenames.

## Customer Decisions Needed
- Approve `case_id` as the primary workflow ID.
- Approve full filename standardization rather than manifest-only extraction.
- Confirm that clinic and patient text should remain in canonical filenames.
- Confirm that ambiguous tags should be preserved as metadata tags rather than reinterpreted immediately.
- Confirm whether any additional artifact classes exist outside the current sample set.

## Acceptance Criteria
- Every STL receives a valid normalized `case_id`.
- Every STL is assigned one artifact class.
- Legacy short-form files are normalized into the same standard as modern files.
- Same-case related files remain visibly grouped by filename.
- The standard supports later routing decisions for models, tooth artifacts, splints, and downstream processing.

## Assumptions
- The `7-8` digit numeric token is the true case/job identifier.
- Tooth notation follows FDI numbering.
- Clinic and patient text remain in the canonical filename because manual handling is still important.
- Tokens such as `UT`, `MT`, `DD`, `pfm`, `OPAQUE`, and shade codes should be retained as tags until business rules define them more precisely.
