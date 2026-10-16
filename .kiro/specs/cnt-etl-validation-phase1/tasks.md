# Implementation Plan: CNT ETL Validation Pipeline — Phase 1

## Overview

Build the `src/` directory from scratch using Python 3.12 and Pandas. The pipeline is structured as four independent layers (input → rules → engine → output) wired together by a CLI entry point. Implementation proceeds layer by layer, with validation utilities built first since all other layers depend on them.

---

## Tasks

- [x] 1. Scaffold project structure and shared utilities
  - Create directory layout: `src/` with `tests/`, `scripts/`, and `sample_data/` at workspace root
  - Create `requirements.txt` pinning `pandas>=2.2.0`, `pytest>=8.0.0`, `hypothesis>=6.0.0`
  - Create `validation_utils.py` with all eight helper functions: `is_not_blank`, `is_exact_length`, `is_max_length`, `is_in_allowed_values`, `is_valid_date`, `is_numeric`, `is_date_greater_than`, `is_date_lte`
  - Every function must accept a `pd.Series`, return a boolean `pd.Series`, use vectorised Pandas operations only, and include a one-line docstring
  - Add module-level docstring to `validation_utils.py` stating its single responsibility
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.10, 8.11_

  - [ ]* 1.1 Write property tests for validation_utils
    - **Property 9: Validation_Utils correctness across all inputs**
    - Use Hypothesis to generate diverse Series inputs for each of the eight functions
    - Verify: `is_not_blank` — True iff non-null, non-whitespace; `is_exact_length` — True iff trimmed length == n; `is_max_length` — True iff length <= n; `is_in_allowed_values` — True iff value in list; `is_valid_date` — True iff valid YYYYMMDD calendar date; `is_numeric` — True iff float-convertible; `is_date_greater_than` — True iff a > b; `is_date_lte` — True iff a <= b
    - Tag: `Feature: cnt-etl-validation-phase1, Property 9`
    - **Validates: Requirements 8.1–8.8**

  - [ ]* 1.2 Write unit tests for validation_utils edge cases
    - Test boundary lengths (exact length at n, n-1, n+1)
    - Test invalid dates: `20260231` (Feb 31), `00000000`, `99999999`, non-numeric strings
    - Test whitespace-only strings for `is_not_blank`
    - Test empty list for `is_in_allowed_values`
    - _Requirements: 8.1–8.8_

- [x] 2. Implement the Rule Loader
  - Create `rule_loader.py` with module-level docstring
  - Define `RULES_FILE_PATH = Path("rules") / "DB_Section_Contract.csv"` as a named constant at module top
  - Implement `load(table: str) -> dict` that reads `DB_Section_Contract.csv` using `pd.read_csv()` and returns a structured rules dict keyed by field name
  - Each rules entry must include: `rule_type`, `severity`, `length`, `allowed_values`, `ref_field`
  - Return cross-field rules as a separate list alongside the field rules dict
  - Raise `FileNotFoundError` (with path in message) if the rules file is missing
  - Log `[RULES] Loaded N field rules and M cross-field rules for CNT` on success
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [ ]* 2.1 Write unit tests for rule_loader
    - Verify `load("CNT")` returns entries for all 32 CNT field names
    - Verify all nine rule types appear in the returned rules dict
    - Verify missing file raises `FileNotFoundError` with file path in message
    - Verify `RULES_FILE_PATH` constant is defined at module top (not inside a function)
    - _Requirements: 3.1, 3.2, 3.3, 3.6_

- [x] 3. Implement the Input Reader
  - Create `input_reader.py` with module-level docstring
  - Define `EXPECTED_COLUMNS` list containing all 32 CNT field names
  - Implement `read(file_path: Path, chunksize: int = 10_000) -> pd.DataFrame` using `pd.read_csv(chunksize=...)` and `pd.concat()`
  - After loading, verify all 32 expected columns are present; raise `ValueError` listing all missing column names if any are absent
  - Raise `FileNotFoundError` (with path in message) if the input file is missing
  - Log `[INPUT] Reading CNT data from: <path>` before reading; log `[INPUT] Loaded N rows, 32 columns` after
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 10.2_

  - [ ]* 3.1 Write property tests for input_reader
    - **Property 1: Input round-trip preserves row count and columns**
    - Use Hypothesis to generate random DataFrames with all 32 CNT columns; write to temp CSV; verify `read()` returns same shape
    - Tag: `Feature: cnt-etl-validation-phase1, Property 1`
    - **Property 2: Missing columns are fully reported**
    - Use Hypothesis to generate random subsets of the 32 columns to remove; verify all missing names appear in the `ValueError` message
    - Tag: `Feature: cnt-etl-validation-phase1, Property 2`
    - **Validates: Requirements 2.1, 2.3, 2.4**

  - [ ]* 3.2 Write unit tests for input_reader
    - Test valid CSV file with all 32 columns → correct DataFrame shape
    - Test missing file → `FileNotFoundError` with path
    - Test CSV missing 3 specific columns → `ValueError` listing all 3 column names
    - _Requirements: 2.2, 2.3, 2.4_

- [x] 4. Implement single-field validation in the Validation Engine
  - Create `validation_engine.py` with module-level docstring
  - Implement `_apply_field_rules(df, rules) -> pd.DataFrame` that iterates over the rules dict and dispatches to `validation_utils` helpers
  - For each field, write the result to a `VAL_<FIELD_NAME>` column: `None` for pass, severity-prefixed string for failure
  - Implement the default-then-warn logic for `CNT_BASE_PLAN_CODE`: replace blank values with `CNT_POLICY_PLAN_CODE` value from same row, then set `VAL_CNT_BASE_PLAN_CODE` to a WARNING message
  - Use vectorised Pandas operations throughout; no `iterrows()` or row-by-row loops
  - The engine must not open any files
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 4.11, 4.12, 10.3_

  - [ ]* 4.1 Write property tests for single-field validation
    - **Property 3: Valid field values produce no validation message**
    - Use Hypothesis to generate valid values for each rule type; verify VAL_* = None
    - Tag: `Feature: cnt-etl-validation-phase1, Property 3`
    - **Property 4: Invalid field values produce correctly prefixed messages**
    - Use Hypothesis to generate invalid values; verify VAL_* starts with correct severity prefix
    - Tag: `Feature: cnt-etl-validation-phase1, Property 4`
    - **Property 5: Default-then-warn transformation is consistent**
    - Generate rows with blank CNT_BASE_PLAN_CODE; verify CNT_BASE_PLAN_CODE = CNT_POLICY_PLAN_CODE and VAL_ starts with "WARNING:"
    - Tag: `Feature: cnt-etl-validation-phase1, Property 5`
    - **Validates: Requirements 4.1–4.12**

  - [ ]* 4.2 Write unit tests for single-field validation
    - All-valid 32-field row → all VAL_* = None, ROW_SEVERITY = CLEAN
    - CNT_ISSUE_SYSTEM = "" → VAL_CNT_ISSUE_SYSTEM starts with "SEVERE:"
    - CNT_ISSUE_SYSTEM = "ABC" (3 chars) → VAL_CNT_ISSUE_SYSTEM starts with "SEVERE:"
    - CNT_PRODUCT_TYPE = "X" (not in allowed list) → VAL_CNT_PRODUCT_TYPE starts with "SEVERE:"
    - CNT_ISSUE_DATE = "20261301" (month 13) → VAL_CNT_ISSUE_DATE starts with "SEVERE:"
    - CNT_SERV_AGENT = "" → VAL_CNT_SERV_AGENT starts with "WARNING:"
    - CNT_BASE_PLAN_CODE = "" with CNT_POLICY_PLAN_CODE = "PLAN001   " → base plan defaulted and WARNING set
    - _Requirements: 4.1–4.12_

- [x] 5. Implement cross-field validation and row classification
  - Add `_apply_cross_field_rules(df) -> pd.DataFrame` to `validation_engine.py`
  - Implement all 17 cross-field rules as named functions (see design doc for function names)
  - Rules must run after single-field validation; each rule writes to the dependent field's `VAL_*` column
  - Implement `classify_severity(df) -> pd.DataFrame` that scans all `VAL_*` columns and sets `ROW_SEVERITY` to `CLEAN`, `WARNING`, or `SEVERE` using exact values only
  - Implement `run(df, rules) -> pd.DataFrame` as the public entry point that calls `_apply_field_rules`, `_apply_cross_field_rules`, and `classify_severity` in sequence
  - _Requirements: 5.1–5.18, 6.1–6.5_

  - [ ]* 5.1 Write property tests for cross-field validation and classification
    - **Property 6: Cross-field rule violations produce SEVERE messages**
    - Use Hypothesis to generate rows satisfying each trigger condition with an invalid dependent value; verify SEVERE message set
    - Cover all 17 cross-field rules; each violation independently verified
    - Tag: `Feature: cnt-etl-validation-phase1, Property 6`
    - **Property 7: Row classification is determined solely by VAL_* column patterns**
    - Use Hypothesis to generate arbitrary sets of None / "WARNING:..." / "SEVERE:..." VAL_* values; verify ROW_SEVERITY classification is always correct
    - Tag: `Feature: cnt-etl-validation-phase1, Property 7`
    - **Validates: Requirements 5.1–5.18, 6.1–6.5**

  - [ ]* 5.2 Write unit tests for cross-field rules
    - CNT_SEX_CODE = B, CNT_JOINT_LIFE_INDICATOR = N → SEVERE on VAL_CNT_JOINT_LIFE_INDICATOR
    - CNT_SEX_CODE = B, CNT_JOINT_LIFE_INDICATOR = F → no cross-field error
    - CNT_PRODUCT_TYPE = K, CNT_JOINT_LIFE_INDICATOR = N → SEVERE
    - CNT_JOINT_LIFE_INDICATOR = F, CNT_JOINT_RATE_AGE = 5 → SEVERE on VAL_CNT_JOINT_RATE_AGE
    - CNT_JOINT_LIFE_INDICATOR = N, CNT_JOINT_RATE_AGE_REASON_CODE = "F" → SEVERE
    - CNT_MATURE_EXPIRE_DATE <= CNT_ISSUE_DATE → SEVERE on VAL_CNT_MATURE_EXPIRE_DATE
    - CNT_APPLICATION_DATE > CNT_ISSUE_DATE → SEVERE on VAL_CNT_APPLICATION_DATE
    - CNT_QUALIFICATION_CODE = Q, CNT_PRODUCT_TYPE = T → SEVERE on VAL_CNT_QUALIFICATION_CODE
    - Row with one WARNING and no SEVERE → ROW_SEVERITY = WARNING
    - Row with WARNING and SEVERE → ROW_SEVERITY = SEVERE
    - _Requirements: 5.2–5.17, 6.2–6.4_

- [x] 6. Implement shared field validation engine (field_validator.py)
  - Created `src/field_validator.py` as the shared field-level validation engine
  - Exposes two public functions: `apply_field_rules(df, rules_dict, table_name="")` and `classify_severity(df)`
  - Contains no table-specific logic or field names
  - Implements all rule types: not_blank, exact_length, max_length, allowed_values, valid_date, numeric, default_then_warn
  - Severity flows from BA rule sheet → rule_loader → rules dict → apply_field_rules → classify_severity (no hardcoding)
  - _Requirements: 13.7, 13.8_

- [x] 7. Migrate CVG, ROL, ADD to hybrid pattern
  - Updated `validate_cvg.py`, `validate_rol.py`, `validate_add.py` to delegate field-level rules to `field_validator.py`
  - Each module retains only its rules dictionary and cross-table validation function
  - _Requirements: 13.7_

- [x] 8. Migrate CNT to hybrid pattern
  - Updated `validation_engine.py` to delegate all 32 field-level rules to `field_validator.py` via thin wrapper
  - Wrapper: `def _apply_field_rules(df, rules): return apply_field_rules(df, rules, table_name="CNT")`
  - Public function signatures in `validation_engine.py` unchanged
  - 16 cross-field rules remain in `validation_engine.py`
  - _Requirements: 13.7, 13.8_

- [x] 9. Add exact_length and default_then_warn rule types
  - `exact_length` validates a field is exactly N characters; blank values fail this check
  - `default_then_warn` defaults a blank field to a reference field value and emits WARNING as audit trail
  - `default_then_warn` is the only rule type that writes to the DataFrame; must be backed by a BA steering file rule before use
  - _Requirements: 4.5, 4.10_

- [x] 10. Add structured logging to field_validator.py
  - Start log: `[FIELD_VAL] Processing <TABLE> — <N> rules loaded`
  - Per-rule log (DEBUG only, gated behind `verbose=False`): `[FIELD_VAL] <FIELD> | <RULE_TYPE> | severity: <SEVERITY> — <N> violation(s)`
  - End log: `[FIELD_VAL] <TABLE> complete — CLEAN: <N>, WARNING: <N>, SEVERE: <N>`
  - _Requirements: 1.5, 13.1_

- [x] 11. Write unit tests for shared field validation engine
  - Created `tests/test_field_validator.py` with 19 tests
  - Tests cover the shared engine directly and independently of any table module
  - Total test suite now 124 tests (up from 105), all passing
  - _Requirements: 14.7_

- [x] 12. Document BA severity flow and default_then_warn mutation
  - Confirmed severity flows from BA rule sheet → rule_loader.py → rules dict → apply_field_rules() → classify_severity()
  - No severity values hardcoded in field_validator.py
  - Documented that default_then_warn is the only write rule type in the module docstring
  - _Requirements: 13.8_

- [ ] 13. Checkpoint — validate all engine tests pass
  - Run `pytest tests/test_validation_utils.py tests/test_validation_engine.py -v`
  - All tests must pass before proceeding
  - Ask the user if questions arise.

- [ ] 14. Implement the Output Writer
  - Create `output_writer.py` with module-level docstring
  - Implement `write(df, output_dir) -> None` that creates `output_dir` if absent, then uses boolean masks to split the DataFrame into CLEAN/WARNING/SEVERE subsets and writes each to its named CSV file
  - Implement `_write_summary(df, output_dir, input_file) -> None` that produces `cnt_summary.txt` in the format from ETL Engineering Standards steering file (run date, input file, total rows, per-severity counts and percentages, top 5 SEVERE and top 3 WARNING failure reasons by field name)
  - Log `[OUTPUT] N rows → output/cnt_<severity>.csv` for each file; log `[OUTPUT] Summary → output/cnt_summary.txt`
  - Output writer must contain no validation logic
  - _Requirements: 7.1–7.7_

  - [ ]* 14.1 Write property tests for output_writer
    - **Property 8: Output partitions the input without overlap or loss**
    - Use Hypothesis to generate validated DataFrames with random ROW_SEVERITY distributions; verify count(CLEAN) + count(WARNING) + count(SEVERE) = total, and no primary key appears in more than one output
    - Tag: `Feature: cnt-etl-validation-phase1, Property 8`
    - **Validates: Requirements 7.1, 7.2, 7.3**

  - [ ]* 14.2 Write unit tests for output_writer
    - Verify cnt_clean.csv contains only CLEAN rows
    - Verify cnt_warning.csv contains only WARNING rows
    - Verify cnt_severe.csv contains only SEVERE rows
    - Verify output directory is created if absent
    - Verify cnt_summary.txt is created and contains total row count
    - _Requirements: 7.1–7.7_

- [ ] 15. Implement the CLI entry point (PDL/PL Engine Integration)
  - Create `run_local.py` with module-level docstring
  - Use `argparse` to accept `--input-file` (full path to input CSV) and `--output-dir` (full path to output directory) as the primary arguments supplied by the PDL/PL engine
  - Also accept legacy aliases `--input`, `--spec`, and `--output` for backward compatibility with direct use
  - Wire the four layers in order: `input_reader.read()` → `rule_loader.load("CNT")` → `validation_engine.run()` → `output_writer.write()`
  - Wrap each layer call in `try/except`; on exception print `[ERROR] Layer failed: <message>` and call `sys.exit(1)`
  - On successful completion, call `sys.exit(0)` — the PDL/PL engine uses exit code 0 to continue downstream processing and exit code 1 to halt and report error
  - No hardcoded paths — use only values supplied at invocation
  - No interactive prompts — the pipeline runs unattended when triggered by the PDL/PL engine
  - Print final console summary showing total rows, CLEAN/WARNING/SEVERE counts and percentages
  - Log elapsed time at the end using `[DONE] Pipeline completed in X.X seconds`
  - Add the AWS execution recommendation comment (comparing Glue Python Shell vs Batch vs Step Functions vs ECS Fargate based on expected data volume and memory profile)
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

  - [ ]* 15.1 Write integration test for run_local
    - Run full pipeline end-to-end using `sample_data/sample_cnt.csv` as input
    - Verify all four output files are created
    - Verify `cnt_clean.csv`, `cnt_warning.csv`, `cnt_severe.csv` are non-empty
    - Verify exit code is 0 on success
    - Verify exit code is 1 when input file does not exist
    - Verify `--input-file` and `--output-dir` arguments are accepted correctly
    - _Requirements: 1.1, 1.3, 10.1, 10.2, 10.3, 10.4_

- [ ] 16. Implement the test data generator
  - Create `generate_test_data.py` with module-level docstring and the three generator functions: `generate_clean_rows(n)`, `generate_warning_rows(n)`, `generate_severe_rows(n)`
  - CLEAN rows: all 32 fields valid, all single-field and cross-field rules satisfied
  - WARNING rows: introduce at least one of: blank CNT_SERV_AGENT, blank CNT_SERV_AGENCY, blank CNT_BASE_PLAN_CODE, CNT_JOINT_NUMBER_OF_LIVES = 1 without REASON_CODE = G
  - SEVERE rows: spread across at least six distinct SEVERE triggers as specified in Requirements 9.4
  - Every WARNING and SEVERE row must include a `TEST_EXPECTED_ISSUE` column describing the expected failure
  - Output to `sample_data/sample_cnt.csv` using `Path("sample_data").mkdir(exist_ok=True)`
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

  - [ ]* 16.1 Write property tests for test data generator
    - **Property 10: Generated test rows are classified correctly by the pipeline**
    - Run `generate_clean_rows(20)` through the full pipeline; verify all produce ROW_SEVERITY = CLEAN
    - Run `generate_warning_rows(20)` through the full pipeline; verify all produce ROW_SEVERITY = WARNING
    - Run `generate_severe_rows(20)` through the full pipeline; verify all produce ROW_SEVERITY = SEVERE
    - Tag: `Feature: cnt-etl-validation-phase1, Property 10`
    - **Validates: Requirements 9.1–9.4**

- [ ] 17. Final checkpoint — full test suite and pipeline smoke test
  - Run `pytest tests/ -v` — all tests must pass
  - Run `python generate_test_data.py` to produce `sample_data/sample_cnt.csv`
  - Run `python run_local.py --input-file sample_data/sample_cnt.csv --output-dir output/` and verify all four output files are produced
  - Verify `output/cnt_summary.txt` is readable and contains correct counts
  - Ask the user if questions arise.

---

## Task Dependency Graph

The following dependencies must be respected when executing or extending tasks:

- CNT field validation (validation_engine.py) depends on field_validator.py being stable and tested.
- CVG, ROL, ADD field validation depends on field_validator.py being stable and tested.
- Cross-table validation for CVG, ROL, ADD depends on CNT validation completing first.
- Any new table module depends on field_validator.py and rule_loader.py.
- Output writing depends on all validation and classification steps completing for that table.

Execution order: CNT → CVG, ROL, ADD (parallel) → output

```json
{
  "waves": [
    {
      "wave": 1,
      "description": "Foundation — shared utilities and config",
      "tasks": [1, 2, 3]
    },
    {
      "wave": 2,
      "description": "CNT validation — must complete before child tables can run",
      "tasks": [4, 5, 6, 7, 8, 9, 10, 11, 12, 13]
    },
    {
      "wave": 3,
      "description": "CVG, ROL, ADD validation — parallel, all depend on CNT completing",
      "tasks": [14, 15]
    },
    {
      "wave": 4,
      "description": "Output writing and reporting — depends on all validation completing",
      "tasks": [16, 17]
    }
  ]
}
```

---

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP; all property and unit test sub-tasks are optional
- Each task references specific requirements for traceability
- Property tests use Hypothesis and must be tagged with `Feature: cnt-etl-validation-phase1, Property N`
- All paths use `pathlib.Path` — no hardcoded `\` or `/` separators
- The engine must never open files; the rule loader must never touch the data DataFrame; the output writer must contain no validation logic
- `run_local.py` must include the AWS execution recommendation comment per the architecture steering file
