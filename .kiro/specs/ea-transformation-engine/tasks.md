# Implementation Plan: EA Transformation Engine

## Overview

Build a metadata-driven transformation layer (Layer 5) as new modules added to the existing Policy Loader ETL Validation Pipeline. The transformation engine consumes validated in-memory DataFrames (CLEAN and WARNING rows from CNT, CVG, ROL, ADD), applies transformation rules loaded from `rules/POC_Transformation_Mapping.csv`, and produces three outputs: a fixed-width positional flat file (`ea_transaction.txt`), an intermediate columnar CSV (`transformed_dataframe.csv`), and a per-field audit log (`transformation_audit_log.csv`).

Implementation proceeds foundation-first: shared utilities → mapping loader → transformation engine with handler registry → flat file builder → integration with main.py → comprehensive testing.

**Key constraint:** This feature is implemented as new modules only. No modifications to existing validation modules. All 141 existing tests must remain passing.

---

## Tasks

- [x] 1. Create transformation_utils.py with shared helper functions
  - [x] 1.1 Implement transformation_utils.py
    - Create `src/transformation_utils.py` with module-level docstring
    - Implement `format_field(value, target_length, data_type, padding_rule="")` — format value to exactly target_length; CHAR right-pads with spaces, NUMERIC/PACKED_DECIMAL left-pads with zeroes; truncates CHAR only, raises ValueError for NUMERIC overflow
    - Implement `split_date(date_value, target_length, target_field, date_handling="")` — extract year/month/day from YYYYMMDD; primary: parse Date Handling column; fallback: 4 chars = year (0:4), 2 chars + MM/MO = month (4:6), 2 chars + DD/DA = day (6:8); return zeroes if blank or < 8 chars
    - Implement `pad_char(value, length)` — right-pad with spaces, truncate if longer
    - Implement `pad_numeric(value, length)` — left-pad with zeroes, raise ValueError if longer
    - Implement `initialize_field(data_type, length)` — spaces for CHAR, zeroes for NUMERIC/PACKED_DECIMAL
    - All functions must be pure (no side effects, no file I/O, no state)
    - Every function must have a one-line docstring
    - _Requirements: 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 4.4, 4.5, 10.1, 10.2, 10.3, 10.4, 10.5_

  - [ ]* 1.2 Write property tests for transformation_utils
    - **Property 5: Every Transformed Field Is Exactly Target Length**
    - Use Hypothesis to generate random values, target_lengths (1-50), and data types (CHAR, NUMERIC, PACKED_DECIMAL); verify `format_field` always returns exactly target_length characters for valid inputs
    - **Property 6: DATE_SPLIT Component Extraction**
    - Use Hypothesis to generate valid YYYYMMDD strings; verify year = positions 0:4, month = positions 4:6, day = positions 6:8
    - Verify `pad_char` always returns exactly `length` characters
    - Verify `pad_numeric` always returns exactly `length` characters for values that fit
    - Verify `initialize_field` returns correct fill character (spaces for CHAR, zeroes for NUMERIC)
    - Tag: `Feature: ea-transformation-engine, Property 5, Property 6`
    - **Validates: Requirements 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 10.1, 10.2, 10.3**

  - [ ]* 1.3 Write unit tests for transformation_utils edge cases
    - Test `format_field` with empty string, string longer than target_length (CHAR → truncate, NUMERIC → ValueError)
    - Test `split_date` with blank value → zeroes, value shorter than 8 chars → zeroes, valid date → correct component
    - Test `pad_char` at boundary (exact length, shorter, longer)
    - Test `pad_numeric` at boundary (exact length, shorter, longer → ValueError)
    - Test `initialize_field` for each data type
    - _Requirements: 3.2, 3.5, 4.4, 10.5, 10.6_

- [x] 2. Create mapping_loader.py
  - [x] 2.1 Implement mapping_loader.py
    - Create `src/mapping_loader.py` with module-level docstring
    - Define `MAPPING_FILE_PATH = Path("rules") / "POC_Transformation_Mapping.csv"` as named constant at module top
    - Define `REQUIRED_COLUMNS` list with all 23 expected columns
    - Define `EXCLUDED_STATUSES` frozenset with: "Open - Clarification Needed", "Review Required", "Out of Scope", "Not Used"
    - Implement `load(mapping_path=None) -> list[dict]` — read CSV, validate columns, filter POC scope, filter mapping status, filter GROUP_OR_PARENT, filter unavailable source tables (PRM, FIN, NFN), sort by Original Sheet Row, convert to list of mapping dicts
    - Implement `_validate_columns(df)` — raise ValueError listing missing columns if any of 23 required columns are absent
    - Implement `_filter_poc_scope(df)` — keep only "Yes" or "Yes - Default/System"
    - Implement `_filter_mapping_status(df)` — exclude EXCLUDED_STATUSES
    - Implement `_filter_transformation_type(df)` — exclude GROUP_OR_PARENT rows
    - Implement `_filter_source_tables(df)` — exclude rows requiring PRM, FIN, NFN source tables
    - Implement `_to_mapping_dicts(df)` — convert to list of dicts sorted by Original Sheet Row; parse semicolon-separated Source Table(s) and Source Field(s) into lists
    - Log each exclusion: `[TRANSFORM] Excluded: <target_field> — reason: <reason> (row <N>)`
    - Log summary: `[TRANSFORM] Loaded N mappings from M total rows`
    - This must be the ONLY module that reads the Transformation_Mapping_CSV
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8_

  - [ ]* 2.2 Write property tests for mapping_loader
    - **Property 1: Mapping Filter Correctness**
    - Use Hypothesis to generate DataFrames with random POC Scope, Transformation Type, and Mapping Status values; verify filtered result contains only valid combinations
    - **Property 2: Mapping Sequence Ordering**
    - Use Hypothesis to generate mapping rows with random Original Sheet Row values; verify output is sorted ascending
    - **Property 3: Column Validation Rejects Incomplete Schemas**
    - Use Hypothesis to generate random subsets of the 23 required columns to remove; verify ValueError is raised listing all missing columns
    - Tag: `Feature: ea-transformation-engine, Property 1, Property 2, Property 3`
    - **Validates: Requirements 1.2, 1.3, 1.4, 1.5, 1.6**

  - [ ]* 2.3 Write unit tests for mapping_loader
    - Test `load()` with actual `rules/POC_Transformation_Mapping.csv` — verify returns non-empty list of dicts
    - Test column validation with missing columns → ValueError listing missing names
    - Test POC Scope filtering: "Yes" included, "No" excluded, "Yes - Default/System" included
    - Test GROUP_OR_PARENT excluded from results
    - Test EXCLUDED_STATUSES rows are removed
    - Test output is sorted by Original Sheet Row (ascending)
    - Test `MAPPING_FILE_PATH` constant is defined at module top
    - Test missing file → FileNotFoundError with path in message
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

- [x] 3. Checkpoint — Verify foundation modules
  - Run `pytest tests/test_transformation_utils.py tests/test_mapping_loader.py -v`
  - Verify all existing 141 tests still pass: `pytest tests/ -v`
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Create transformation_engine.py with handler registry and orchestration
  - [x] 4.1 Implement transformation_engine.py core structure
    - Create `src/transformation_engine.py` with module-level docstring
    - Define `HANDLER_REGISTRY` dict mapping Transformation Type strings to handler functions
    - Implement `transform(mappings, cnt_df, cvg_df=None, rol_df=None, add_df=None) -> tuple[pd.DataFrame, list[dict]]` — orchestrate all transformations, return (transformed_df, audit_entries)
    - Implement `_get_eligible_records(df)` — filter to ROW_SEVERITY in {CLEAN, WARNING} only
    - Implement `_resolve_source_value(mapping, record, source_dfs)` — look up source field value from appropriate source table using CNT_POLICY_NUMBER as primary join key
    - Implement `_apply_single_mapping(mapping, record, source_dfs)` — dispatch to handler, return (value, audit_entry)
    - Per-record iteration: for each eligible CNT record, iterate all mappings in sequence order, apply each handler, collect results into transformed row and audit entries
    - Log per-record summary: `[TRANSFORM] Record <policy_number>: <N> success, <M> skipped, <P> error`
    - Log transform summary: `[TRANSFORM] Transformed <N> records from <M> eligible`
    - Engine must contain NO hardcoded field names or source column references
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 14.3, 14.4, 22.1, 22.2, 22.3_

  - [x] 4.2 Implement DIRECT_SOURCE handler
    - Implement `_handle_direct_source(mapping, source_value)` in transformation_engine.py
    - Read source value → apply `format_field()` from transformation_utils
    - CHAR: right-pad with spaces to Target Length
    - NUMERIC: left-pad with zeroes to Target Length
    - Blank source → initialize with default for Target Data Type
    - Value exceeds Target Length → truncate CHAR (log warning), error for NUMERIC (exclude record)
    - Return formatted value at exactly Target Length
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 10.5, 10.6_

  - [x] 4.3 Implement DATE_SPLIT handler
    - Implement `_handle_date_split(mapping, source_value)` in transformation_engine.py
    - Call `split_date()` from transformation_utils
    - Primary: use Date Handling column instruction from mapping
    - Fallback: determine component from Target Length and target field name convention
    - Blank/short date → zeroes to Target Length
    - Return extracted component at exactly Target Length
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x] 4.4 Implement CONSTANT, INITIALIZE_SPACES, INITIALIZE_NUMERIC_OR_DATE, SYSTEM_GENERATED handlers
    - Implement `_handle_constant(mapping)` — return Default/Constant Value formatted to Target Length; handle `<spaces>` token
    - Implement `_handle_initialize_spaces(mapping)` — return spaces × Target Length; if Default/Constant Value is non-space, use that instead
    - Implement `_handle_initialize_numeric(mapping)` — return zeroes × Target Length; if Default/Constant Value populated, use that left-padded
    - Implement `_handle_system_generated(mapping)` — initialize by Target Data Type (spaces for CHAR, zeroes for NUMERIC/PACKED_DECIMAL); use Default/Constant Value if populated; log as placeholder in audit
    - All handlers return exactly Target Length characters
    - _Requirements: 5.1, 5.2, 5.3, 6.1, 6.2, 6.3, 7.1, 7.2, 7.3, 8.1, 8.2, 8.3_

  - [x] 4.5 Implement CONDITIONAL_OR_DERIVED handler
    - Implement `_handle_conditional(mapping, source_value, record)` in transformation_engine.py
    - When Transformation Rule contains clearly described logic → implement as named rule function
    - Implement named rules for known POC conditions: PRODUCT-CODE derivation, NON-FORFEIT-OVERRIDE-IND, DIVIDEND-OPT-CODE, and any other clearly specified rules in the mapping CSV
    - When rule is ambiguous or incomplete → skip field, initialize with default for Target Data Type, log skip reason
    - Format derived value to exactly Target Length using applicable Padding_Rule
    - New conditional rules added by creating a new named function and registering it — no changes to core dispatch
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

  - [x] 4.6 Implement multi-table join logic
    - In `_resolve_source_value`, join child tables (CVG, ROL, ADD) to CNT using CNT_POLICY_NUMBER as primary key
    - Parse Source Table(s) semicolon-separated list to determine which tables to query
    - When child record exists → return source field value
    - When no matching child record → initialize affected fields with defaults for Target Data Type, log as SKIPPED in audit
    - Support all combinations: CNT alone, CVG alone, ROL alone, ADD alone, ADD;ROL, CNT;CVG, etc.
    - Secondary key disambiguation documented as POC limitation (Phase 2 enhancement)
    - _Requirements: 15.1, 15.2, 15.3, 15.4_

- [x] 5. Create flat_file_builder.py
  - [x] 5.1 Implement flat_file_builder.py
    - Create `src/flat_file_builder.py` with module-level docstring
    - Implement `build(transformed_df, mappings) -> list[str]` — concatenate field values in mapping sequence order, one record string per eligible row
    - Implement `write(records, output_path)` — write records to ea_transaction.txt, one per line, newline-terminated
    - Implement `_calculate_expected_length(mappings)` — sum all Target Lengths from active mapping set
    - Implement `_verify_record_length(record, expected_length, record_id)` — verify record is exactly expected_length; log error and exclude record if mismatch
    - No delimiters between fields — pure concatenation
    - Exclude records that fail length verification
    - Log: `[TRANSFORM] Built <N> records, <M> excluded (length mismatch)`
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

  - [ ]* 5.2 Write property tests for flat_file_builder
    - **Property 8: Flat File Record Length Invariant**
    - Use Hypothesis to generate transformed DataFrames with fields exactly at Target Length; verify every record in output is exactly sum(Target Lengths) characters
    - Verify no delimiter characters between fields
    - Tag: `Feature: ea-transformation-engine, Property 8`
    - **Validates: Requirements 11.1, 11.2, 11.3**

  - [ ]* 5.3 Write unit tests for flat_file_builder
    - Test `build` with known field values → correct concatenation order and length
    - Test record with incorrect total length → excluded from output
    - Test `write` creates file with correct content
    - Test `_calculate_expected_length` sums Target Lengths correctly
    - Test empty DataFrame → empty records list
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

- [x] 6. Implement intermediate outputs
  - [x] 6.1 Implement transformed_dataframe.csv output
    - In `transformation_engine.py`, after all records are transformed, write `transformed_dataframe.csv` to output directory
    - Column headers = target field names in mapping sequence order
    - One row per eligible record (excluding error-excluded records)
    - Standard CSV format with pandas `to_csv(index=False)`
    - _Requirements: 12.1, 12.2, 12.3, 12.4_

  - [x] 6.2 Implement transformation_audit_log.csv output
    - In `transformation_engine.py`, collect all audit entries during transformation
    - Write `transformation_audit_log.csv` with columns: record_id, source_table, source_field, target_field, transformation_type, mapping_status, processing_status, output_value_length, error_or_skip_reason
    - processing_status values: SUCCESS, SKIPPED, ERROR
    - SKIPPED/ERROR entries must have non-empty error_or_skip_reason
    - One row per field per record (N records × M mappings = N×M audit entries)
    - Ordering: sorted by record sequence then by field sequence (Original Sheet Row)
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 21.4_

- [x] 7. Checkpoint — Verify transformation engine and outputs
  - Run `pytest tests/test_transformation_engine.py tests/test_flat_file_builder.py -v`
  - Verify all existing 141 tests still pass: `pytest tests/ -v`
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Extend main.py with --run-transformation flag
  - [x] 8.1 Wire transformation phase into main.py
    - Add `--run-transformation` argument (action="store_true", default=False) to argparse
    - After all table validation and output writing, check `args.run_transformation`
    - If True: import mapping_loader, transformation_engine, flat_file_builder
    - Load mappings via `mapping_loader.load()`
    - Call `transform(mappings, validated_cnt, cvg_df, rol_df, add_df)` — note: persist cvg_df, rol_df, add_df from validation blocks into function-level scope
    - Call `build(transformed_df, mappings)` and `write(records, output_dir / "ea_transaction.txt")`
    - Write `transformed_dataframe.csv` and `transformation_audit_log.csv` to output_dir
    - Print transformation summary using `[TRANSFORM]` prefix
    - If False: pipeline exits after validation as before (no change to existing behavior)
    - Handle errors: mapping file missing → exit 1; output write failure → exit 1; partial transformation success → exit 0 with summary
    - _Requirements: 14.1, 14.2, 14.5, 16.1, 16.2, 16.3, 16.4, 18.1, 18.4, 18.5, 22.1, 22.2, 22.3_

- [x] 9. Checkpoint — Full pipeline integration
  - Run full pipeline: `python src/main.py --input-file sample_data/sample_cnt.csv --output-dir output/ --run-transformation`
  - Verify 3 new output files created: `ea_transaction.txt`, `transformed_dataframe.csv`, `transformation_audit_log.csv`
  - Verify pipeline exits with code 0
  - Run without flag: `python src/main.py --input-file sample_data/sample_cnt.csv --output-dir output/`
  - Verify NO transformation output files created (existing behavior preserved)
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Write unit tests for transformation_engine.py
  - [ ]* 10.1 Write property tests for transformation_engine
    - **Property 4: Only Eligible Records Are Transformed**
    - Use Hypothesis to generate DataFrames with mixed ROW_SEVERITY (CLEAN, WARNING, SEVERE); verify no SEVERE record appears in output
    - **Property 9: Audit Completeness**
    - Use Hypothesis to generate N eligible records with M mappings; verify audit log has exactly N×M entries
    - **Property 10: Audit Status Constraint**
    - Verify processing_status in {SUCCESS, SKIPPED, ERROR}; verify SKIPPED/ERROR have non-empty reason
    - **Property 12: Multi-Table Join by Policy Number**
    - Generate CNT + child DataFrames with known policy numbers; verify correct join behavior
    - **Property 13: Error Recovery Continues Processing**
    - Inject a failure in one field; verify remaining fields still processed and audit entry recorded
    - **Property 14: Handler Dispatch Correctness**
    - For each Transformation Type in registry, verify correct handler is invoked
    - Tag: `Feature: ea-transformation-engine, Property 4, Property 9, Property 10, Property 12, Property 13, Property 14`
    - **Validates: Requirements 2.2, 2.4, 2.5, 2.7, 13.2, 13.3, 13.4, 13.5, 15.1, 15.3**

  - [ ]* 10.2 Write unit tests for DIRECT_SOURCE handler
    - Test source value present → formatted to Target Length
    - Test CHAR padding (right-pad spaces)
    - Test NUMERIC padding (left-pad zeroes)
    - Test blank source → default initialization
    - Test CHAR value exceeds length → truncated with warning
    - Test NUMERIC value exceeds length → error, record excluded
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 10.5, 10.6_

  - [ ]* 10.3 Write unit tests for DATE_SPLIT handler
    - Test valid YYYYMMDD → correct year (4 chars), month (2 chars), day (2 chars)
    - Test Date Handling column populated → follows instruction
    - Test Date Handling blank → falls back to target field naming convention
    - Test blank date → zeroes
    - Test short date (< 8 chars) → zeroes
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [ ]* 10.4 Write unit tests for CONSTANT, INITIALIZE, SYSTEM_GENERATED handlers
    - Test CONSTANT with value shorter than Target Length → padded correctly
    - Test CONSTANT with `<spaces>` token → space-filled
    - Test INITIALIZE_SPACES → all spaces at Target Length
    - Test INITIALIZE_SPACES with non-space Default → uses default
    - Test INITIALIZE_NUMERIC_OR_DATE → zeroes at Target Length
    - Test INITIALIZE_NUMERIC_OR_DATE with Default → uses default left-padded
    - Test SYSTEM_GENERATED CHAR → spaces
    - Test SYSTEM_GENERATED NUMERIC → zeroes
    - Test SYSTEM_GENERATED with Default value → uses default
    - _Requirements: 5.1, 5.2, 5.3, 6.1, 6.2, 6.3, 7.1, 7.2, 7.3, 8.1, 8.2, 8.3_

  - [ ]* 10.5 Write unit tests for CONDITIONAL_OR_DERIVED handler
    - Test clearly described rule → derived value computed correctly
    - Test ambiguous rule → skipped, default fill, audit SKIPPED
    - Test derived value formatted to Target Length
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

  - [ ]* 10.6 Write unit tests for multi-table join
    - Test CNT-only mapping → reads from CNT record directly
    - Test CVG mapping → joins on CNT_POLICY_NUMBER, returns CVG field
    - Test ROL mapping → joins on CNT_POLICY_NUMBER, returns ROL field
    - Test ADD mapping → joins on CNT_POLICY_NUMBER, returns ADD field
    - Test missing child record → default initialization, audit SKIPPED
    - Test ADD;ROL combination → resolves from both tables
    - _Requirements: 15.1, 15.3, 15.4_

- [x] 11. Write end-to-end integration test
  - [ ]* 11.1 Write end-to-end transformation test
    - Create `tests/test_e2e_transformation.py`
    - **Property 11: Output Reproducibility**
    - Run full pipeline twice with same inputs; verify byte-identical ea_transaction.txt and transformed_dataframe.csv
    - **Property 15: Columnar Output Structure**
    - Verify transformed_dataframe.csv columns match target field names in mapping sequence order
    - Verify row count matches eligible record count
    - Test full flow: validate → transform → verify all 3 output files exist and are non-empty
    - Verify ea_transaction.txt record length matches sum of Target Lengths
    - Verify audit log has expected number of entries
    - Verify no SEVERE records appear in transformation output
    - Tag: `Feature: ea-transformation-engine, Property 11, Property 15`
    - **Validates: Requirements 12.2, 12.3, 12.4, 14.1, 14.3, 21.1, 21.2, 21.3, 21.4**

- [x] 12. Write regression test
  - [ ]* 12.1 Verify existing 141 validation tests pass
    - Create `tests/test_regression_transformation.py`
    - Run all existing validation tests programmatically
    - Verify test count >= 141 (existing baseline)
    - Verify all pass with zero failures
    - Verify no existing test file was modified by transformation feature
    - _Requirements: 16.4, 17.4_

- [x] 13. Final checkpoint — Full test suite and pipeline verification
  - Run `pytest tests/ -v` — all tests must pass (existing 141 + new transformation tests)
  - Run full pipeline with `--run-transformation`: `python src/main.py --input-file sample_data/sample_cnt.csv --output-dir output/ --run-transformation`
  - Verify all 3 transformation output files exist: `ea_transaction.txt`, `transformed_dataframe.csv`, `transformation_audit_log.csv`
  - Run pipeline without flag — verify ONLY validation outputs produced (no transformation files)
  - Verify total test count has increased beyond 141 baseline
  - Ensure all tests pass, ask the user if questions arise.

---

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Property tests use Hypothesis and must be tagged with `Feature: ea-transformation-engine, Property N`
- All paths use `pathlib.Path` — no hardcoded `\` or `/` separators
- The transformation engine contains NO hardcoded field names — all behavior is metadata-driven from the mapping CSV
- New modules only: `mapping_loader.py`, `transformation_engine.py`, `flat_file_builder.py`, `transformation_utils.py`
- `main.py` is extended minimally with `--run-transformation` flag only
- Existing validation modules remain completely unchanged
- COMP-3 (PACKED_DECIMAL) is represented as zero-padded numeric strings (POC limitation)
- Secondary join key disambiguation is documented as Phase 2 enhancement
- Ambiguous CONDITIONAL_OR_DERIVED rules are skipped and logged, not implemented

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3"] },
    { "id": 3, "tasks": ["4.1"] },
    { "id": 4, "tasks": ["4.2", "4.3", "4.4"] },
    { "id": 5, "tasks": ["4.5", "4.6", "5.1"] },
    { "id": 6, "tasks": ["5.2", "5.3", "6.1", "6.2"] },
    { "id": 7, "tasks": ["8.1"] },
    { "id": 8, "tasks": ["10.1", "10.2", "10.3", "10.4", "10.5", "10.6"] },
    { "id": 9, "tasks": ["11.1", "12.1"] }
  ]
}
```


---

## Phase 2: Excel-Based Source Migration (Requirements 24–26)

These tasks implement the migration from the manually-authored transformation_mappings.csv to mechanically-generated config from the authoritative Excel workbook. Each task is independently implementable and verifiable.

- [ ] 8. Build EA_Transaction_Mapping.xlsx reader
  - [ ] 8.1 Implement scripts/generate_transformation_mappings.py
    - Read rules/EA_Transaction_Mapping.xlsx, sheet "Trx Mapping" only (skip Sheet1 entirely)
    - Parse target_field from Col A: strip leading COBOL level number + whitespace (e.g., "15  COMPANY-CODE" → "COMPANY-CODE")
    - Parse source_field from Col I ("Policy Data Loader Mapping") as-is
    - Infer source_table from Col I prefix (CNT_/CVG_/ROL_/ADD_ → table name; blank/"System generated" → empty)
    - Parse PIC clause from Col C using EXACT rules only:
      - PIC X(n) → CHAR, length n
      - PIC 9(n) → NUMERIC, length n
      - PIC 99 → NUMERIC, length 2
      - PIC S9(n) COMP → BINARY, length n
      - PIC S9(n)V9(m) COMP-3 → PACKED_DECIMAL, length n+m
    - Determine transformation_type using bounded inference (first match wins):
      (a) No PIC clause → GROUP_OR_PARENT
      (b) Col I = "System generated" → SYSTEM_GENERATED
      (c) Col I blank AND Col G or K contains "Move spaces" → INITIALIZE_SPACES
      (d) Col I has exactly one non-blank value → DIRECT_SOURCE, unless YY/MM/DD date pattern → DATE_SPLIT
      (e) Anything else → CONDITIONAL_OR_DERIVED (flagged as "low confidence — needs manual review")
    - Derive padding_rule from data_type only (CHAR → right_space; NUMERIC/BINARY/PACKED_DECIMAL → left_zero)
    - Leave default_value and truncation_rule blank unless Col G/K/L has explicit value
    - Generate mapping_id sequentially (MAP_001, MAP_002, ...) in row order
    - Output: templates/v1/transformation_mappings.csv
    - Any row where parsing fails → templates/v1/transformation_mappings_needs_review.csv with row number, raw Col A, raw Col C, raw Col I, and specific failure reason
    - _Requirements: 24.1–24.10_
  - [ ] 8.2 Verify generated transformation_mappings.csv
    - Confirm total row count aligns with "Trx Mapping" sheet (745 rows minus header = 744 data rows, some of which are GROUP_OR_PARENT)
    - Run scripts/verify_field_names.py to check all source_field values against DB_Section Column A
    - Review transformation_mappings_needs_review.csv — document count and categories of unparseable rows
    - Confirm no mapping_id duplicates
    - _Requirements: 24.10, 23.10_
  - [ ] 8.3 Verify Transformation_Engine accepts new mappings
    - Run pipeline with --run-transformation using the new generated transformation_mappings.csv
    - Confirm no new ERROR entries in transformation_audit_log.csv beyond expected CONDITIONAL_OR_DERIVED skips
    - Confirm ea_transaction.txt is produced with expected record count
    - Compare field values for 5 known DIRECT_SOURCE mappings against source data to confirm correctness
    - _Requirements: 24.6_

- [ ] 9. Build Sample_*_Data.xlsx reader
  - [ ] 9.1 Implement scripts/export_sample_data.py
    - Read each Sample_*_Data.xlsx from staging_data/ using pandas read_excel(dtype=str)
    - Write to staging_data/<table>.csv (cnt.csv, cvg.csv, rol.csv, add.csv) preserving all values as text
    - No value modification, no date reformatting, no numeric reinterpretation
    - Handle CVG_SEQUENCE_NUMBER and CVG_PERSON_SEQ stored as int → convert to str without loss
    - _Requirements: 26.1, 26.2, 26.3, 26.4_
  - [ ] 9.2 Verify exported CSVs against Excel source
    - Confirm row count matches (Contract=120, Coverage=250, Roles=360, Address=360)
    - Confirm column count matches Excel header count per file
    - Confirm all column names from Excel header appear in CSV header — no additions, no renames
    - Spot-check 5 cells per file for value preservation (especially date fields, leading-zero codes)
    - _Requirements: 26.2, 26.3_

- [ ] 10. Add dual CSV output to transformation step
  - [ ] 10.1 Update Flat_File_Builder or main.py transformation section
    - After building the positional flat file from the transformed DataFrame, write a CSV version of the same data
    - CSV uses the same computed field values (no recomputation) — just writes the transformed_df with proper column headers
    - Column headers = actual target field names from the mappings (e.g., "COMPANY-CODE", "MASTER-ID") — not positional offsets
    - Output file: output/ea_transaction.csv (alongside existing ea_transaction.txt)
    - Note: transformed_dataframe.csv already exists — verify whether it already satisfies Requirement 25 or needs column header adjustment
    - _Requirements: 25.1, 25.2, 25.3, 25.4, 25.5_
  - [ ] 10.2 Verify dual output
    - Confirm ea_transaction.txt and ea_transaction.csv are produced in the same run
    - Confirm CSV row count = flat file line count
    - Confirm CSV column count = number of non-GROUP_OR_PARENT mappings
    - Confirm a spot-check of 3 fields × 3 rows shows identical values between CSV and flat-file positions
    - _Requirements: 25.1, 25.3_

- [ ] 11. Update verification tooling
  - [ ] 11.1 Extend scripts/verify_field_names.py
    - Add check: every source_field in the GENERATED transformation_mappings.csv traces to DB_Section Column A (with known open questions as exceptions)
    - Add check: every column header in staging_data/*.csv matches a DB_Section Column A entry
    - Report "needs review" items (from transformation_mappings_needs_review.csv) separately from errors
    - _Requirements: 23.10, 24.10_
  - [ ] 11.2 Run full verification suite and confirm clean
    - Run verify_field_names.py against all generated artifacts
    - Confirm: 0 errors in staging CSVs, document needs-review count for transformation mappings
    - _Requirements: 23.10_
