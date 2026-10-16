# Requirements Document

## Introduction

This document specifies Phase 1 of the Policy Loader ETL Validation Pipeline. The pipeline replaces the legacy KNIME-based batch tool with a lightweight, Python-based system that reads Contract (CNT) table data from a CSV file, applies business validation rules loaded at runtime from `DB_Section_Contract.csv`, classifies each row as CLEAN, WARNING, or SEVERE, and writes results to three separate output CSV files plus a human-readable summary report.

The pipeline is designed to be table-agnostic so that Phase 2 (PRM), Phase 3 (FIN/NFN), and Phase 4 (AWS deployment) can be added with minimal changes to the core engine.

---

## Glossary

- **Pipeline**: The end-to-end Python validation workflow from CSV input to classified output files.
- **Input_Reader**: The module (`input_reader.py`) responsible for reading the input CSV file into a Pandas DataFrame.
- **Rule_Loader**: The module (`rule_loader.py`) responsible for reading `DB_Section_Contract.csv` and returning a structured rules dictionary. It is the only module aware of the CSV rules file format.
- **Validation_Engine**: The module (`validation_engine.py`) responsible for applying rules to the DataFrame, writing `VAL_*` columns, and assigning `ROW_SEVERITY`.
- **Classifier**: The logic within `validation_engine.py` (function `classify_severity`) that assigns a `ROW_SEVERITY` value to each row.
- **Output_Writer**: The module (`output_writer.py`) responsible for splitting the validated DataFrame and writing output files.
- **Validation_Utils**: The shared helper module (`validation_utils.py`) containing pure, side-effect-free validation functions.
- **Main**: The CLI entry point script (`run_local.py`) that wires all four layers together.
- **VAL_Column**: A result column named `VAL_` followed by the exact field name (e.g., `VAL_CNT_ISSUE_DATE`). A `None` value means the field passed; any other value is the failure message.
- **ROW_SEVERITY**: The row-level classification column. Exactly one of: `CLEAN`, `WARNING`, `SEVERE`.
- **Rules_File**: The CSV file `DB_Section_Contract.csv` located in the `rules/` folder.
- **CNT**: The Contract table. The only table in scope for Phase 1.
- **Primary_Key**: The composite key `CNT_COMPANY_CODE` + `CNT_POLICY_NUMBER` that uniquely identifies a contract row.
- **Cross_Field_Rule**: A validation rule that compares two or more fields within the same row.
- **YYYYMMDD**: The required 8-character date format for all CNT date fields (e.g., `20260101`).
- **SEVERE**: A severity level indicating a critical data error. Rows with at least one SEVERE result are written to `cnt_severe.csv`.
- **WARNING**: A severity level indicating a data quality issue that does not block processing. Rows with at least one WARNING and no SEVERE are written to `cnt_warning.csv`.
- **CLEAN**: A row classification indicating all field validations passed. Written to `cnt_clean.csv`.
- **Test_Data_Generator**: The script (`generate_test_data.py`) that produces a realistic 200-row sample CSV covering all three severity outcomes.
- **Field_Validator**: The shared field validation engine module (`field_validator.py`) that provides `apply_field_rules()` and `classify_severity()` functions used by all table modules. It contains no table-specific logic.
- **Hybrid_Pattern**: The architectural pattern where field-level rules are handled by the shared `field_validator.py` engine, while cross-field and cross-table rules remain in table-specific modules (`validate_cvg.py`, `validate_rol.py`, `validate_add.py`, `validation_engine.py`).

---

## Requirements

### Requirement 1: Pipeline Orchestration

**User Story:** As an ETL engineer, I want a single command to run the full validation pipeline, so that I can validate a CNT CSV file without understanding the internal module structure.

#### Acceptance Criteria

1. WHEN the pipeline is invoked with `--input <csv_path>`, `--spec <rules_csv_path>`, and `--output <dir>` arguments, THE Main SHALL execute Input_Reader, Rule_Loader, Validation_Engine, and Output_Writer in sequence.
2. WHEN any layer raises an unhandled exception, THE Main SHALL print a clear error message identifying the failed layer and the cause, then exit with a non-zero status code.
3. THE Main SHALL print a console summary matching the format defined in the ETL Engineering Standards steering file upon successful completion.
4. WHEN the `--output` directory does not exist, THE Main SHALL create it automatically before writing any output files.
5. THE Main SHALL log a timestamped progress message to the console at the start of each pipeline layer (INPUT, RULES, ENGINE, OUTPUT).

---

### Requirement 2: Input Reading

**User Story:** As an ETL engineer, I want the pipeline to read a CNT CSV file reliably, so that I can be confident the data is fully loaded and structurally correct before validation begins.

#### Acceptance Criteria

1. WHEN a valid CSV file path is provided, THE Input_Reader SHALL read the file into a Pandas DataFrame using chunked reads of 10,000 rows per chunk.
2. WHEN the CSV file is missing or inaccessible, THE Input_Reader SHALL raise a `FileNotFoundError` with a message that includes the full file path.
3. WHEN the CSV file is loaded, THE Input_Reader SHALL verify that all 32 expected CNT field names are present as column headers.
4. IF any expected CNT column is absent from the CSV, THEN THE Input_Reader SHALL raise a `ValueError` listing every missing column name.
5. WHEN reading completes successfully, THE Input_Reader SHALL log the row count and column count to the console using the `[INPUT]` prefix.

---

### Requirement 3: Rule Loading

**User Story:** As a business analyst, I want validation rules to be read from `DB_Section_Contract.csv` at runtime, so that I can update field rules without touching Python code.

#### Acceptance Criteria

1. WHEN the pipeline starts, THE Rule_Loader SHALL read validation rules from the CSV file located at the path defined by the `RULES_FILE_PATH` constant in `rule_loader.py`.
2. WHEN the Rules_File is missing, THE Rule_Loader SHALL raise a `FileNotFoundError` with a message identifying the expected file path.
3. WHEN the Rules_File is present, THE Rule_Loader SHALL parse it and return a structured rules dictionary containing, for each CNT field: field name, data type, length, severity, rule type, and any additional rule parameters (allowable values, referenced fields).
4. THE Rule_Loader SHALL be the only module that reads or parses the Rules_File. No other module SHALL open or parse `DB_Section_Contract.csv` directly.
5. WHEN rule loading completes successfully, THE Rule_Loader SHALL log the count of field rules and cross-field rules loaded to the console using the `[RULES]` prefix.
6. THE Rule_Loader SHALL support all nine rule types defined in Section 5.2 of the source requirements without requiring code changes when rule values in `DB_Section_Contract.csv` are updated.

---

### Requirement 4: Single-Field Validation

**User Story:** As a data quality analyst, I want each CNT field validated against its specification, so that every data defect is detected and recorded in the output.

#### Acceptance Criteria

1. WHEN the Validation_Engine runs, THE Validation_Engine SHALL apply the rule loaded for each of the 32 CNT fields to the corresponding DataFrame column.
2. WHEN a field passes all applicable rules, THE Validation_Engine SHALL set the corresponding `VAL_Column` to `None`.
3. WHEN a field fails a rule with SEVERE severity, THE Validation_Engine SHALL set the corresponding `VAL_Column` to a message starting with `SEVERE:` followed by a description of the failure.
4. WHEN a field fails a rule with WARNING severity, THE Validation_Engine SHALL set the corresponding `VAL_Column` to a message starting with `WARNING:` followed by a description of the failure.
5. WHEN `CNT_BASE_PLAN_CODE` is blank, THE Validation_Engine SHALL first set its value to the value of `CNT_POLICY_PLAN_CODE` in the same row, then set the `VAL_CNT_BASE_PLAN_CODE` column to a WARNING message.
6. THE Validation_Engine SHALL use Validation_Utils helper functions for all single-field checks and SHALL NOT implement validation logic inline in `validation_engine.py`.
7. WHEN a field has a rule of type "allowable values", THE Validation_Engine SHALL reject any value not present in the defined list and apply the field's configured severity.
8. WHEN a field has a rule of type "valid date", THE Validation_Engine SHALL reject any value that is not a valid calendar date in `YYYYMMDD` format and apply SEVERE severity.
9. WHEN a field has a rule of type "not blank", THE Validation_Engine SHALL reject any value that is null, empty, or composed entirely of whitespace and apply the field's configured severity.
10. WHEN a field has a rule of type "exact length", THE Validation_Engine SHALL reject any value whose trimmed length does not equal the specified character count and apply the field's configured severity.
11. WHEN a field has a rule of type "maximum length", THE Validation_Engine SHALL reject any value whose length exceeds the specified maximum and apply the field's configured severity.
12. WHEN a field has a rule of type "numeric", THE Validation_Engine SHALL reject any non-numeric value and apply the field's configured severity.

---

### Requirement 5: Cross-Field Validation

**User Story:** As a data quality analyst, I want cross-field rules enforced after single-field checks, so that inter-field consistency errors are also detected and classified.

#### Acceptance Criteria

1. WHEN all single-field validations for a row are complete, THE Validation_Engine SHALL apply cross-field rules to that row.
2. WHEN `CNT_SEX_CODE` equals `B` and `CNT_JOINT_LIFE_INDICATOR` does not equal `F`, THE Validation_Engine SHALL set `VAL_CNT_JOINT_LIFE_INDICATOR` to a `SEVERE:` message.
3. WHEN `CNT_SEX_CODE` equals `J` and `CNT_JOINT_LIFE_INDICATOR` does not equal `J`, THE Validation_Engine SHALL set `VAL_CNT_JOINT_LIFE_INDICATOR` to a `SEVERE:` message.
4. WHEN `CNT_PRODUCT_TYPE` is in `{K, J, Z}` and `CNT_JOINT_LIFE_INDICATOR` is not `F` or `J`, THE Validation_Engine SHALL set `VAL_CNT_JOINT_LIFE_INDICATOR` to a `SEVERE:` message.
5. WHEN `CNT_PRODUCT_TYPE` equals `E` and `CNT_JOINT_LIFE_INDICATOR` is not in `{F, J, N}`, THE Validation_Engine SHALL set `VAL_CNT_JOINT_LIFE_INDICATOR` to a `SEVERE:` message.
6. WHEN `CNT_JOINT_LIFE_INDICATOR` is `F` or `N` and `CNT_JOINT_RATE_AGE` is not `0`, THE Validation_Engine SHALL set `VAL_CNT_JOINT_RATE_AGE` to a `SEVERE:` message.
7. WHEN `CNT_JOINT_LIFE_INDICATOR` is `N` and `CNT_JOINT_RATE_AGE_REASON_CODE` is not blank, THE Validation_Engine SHALL set `VAL_CNT_JOINT_RATE_AGE_REASON_CODE` to a `SEVERE:` message.
8. WHEN `CNT_JOINT_LIFE_INDICATOR` is `F` and `CNT_JOINT_RATE_AGE_REASON_CODE` is not in `{F, G, P}`, THE Validation_Engine SHALL set `VAL_CNT_JOINT_RATE_AGE_REASON_CODE` to a `SEVERE:` message.
9. WHEN `CNT_JOINT_LIFE_INDICATOR` is `J` and `CNT_JOINT_RATE_AGE_REASON_CODE` is not in `{A, B, C, D}`, THE Validation_Engine SHALL set `VAL_CNT_JOINT_RATE_AGE_REASON_CODE` to a `SEVERE:` message.
10. WHEN `CNT_JOINT_NUMBER_OF_LIVES` equals `1` and `CNT_JOINT_RATE_AGE_REASON_CODE` does not equal `G`, THE Validation_Engine SHALL set `VAL_CNT_JOINT_RATE_AGE_REASON_CODE` to a `WARNING:` message.
11. WHEN `CNT_MATURE_EXPIRE_DATE` is not greater than `CNT_ISSUE_DATE`, THE Validation_Engine SHALL set `VAL_CNT_MATURE_EXPIRE_DATE` to a `SEVERE:` message.
12. WHEN `CNT_APPLICATION_DATE` is not less than or equal to `CNT_ISSUE_DATE`, THE Validation_Engine SHALL set `VAL_CNT_APPLICATION_DATE` to a `SEVERE:` message.
13. WHEN `CNT_PAYUP_DATE` is not less than or equal to `CNT_MATURE_EXPIRE_DATE`, THE Validation_Engine SHALL set `VAL_CNT_PAYUP_DATE` to a `SEVERE:` message.
14. WHEN `CNT_QUALIFICATION_CODE` is in `{Q, K, I, T, P, R, U}` and `CNT_PRODUCT_TYPE` is not in `{A, W, B}`, THE Validation_Engine SHALL set `VAL_CNT_QUALIFICATION_CODE` to a `SEVERE:` message.
15. WHEN `CNT_PRODUCT_TYPE` is not in `{T, K, L, D}` and `CNT_PARTICIPATION_STATUS` does not equal `N`, THE Validation_Engine SHALL set `VAL_CNT_PARTICIPATION_STATUS` to a `WARNING:` message.
16. WHEN `CNT_PRODUCT_TYPE` is in `{A, W, B, H}` and `CNT_PLAN_OPTION_ORIGINAL` is not blank, THE Validation_Engine SHALL set `VAL_CNT_PLAN_OPTION_ORIGINAL` to a `SEVERE:` message.
17. WHEN `CNT_PRODUCT_TYPE` is in `{W, B, H}` and `CNT_GRACE_EXPIRY_DATE` is not blank, THE Validation_Engine SHALL set `VAL_CNT_GRACE_EXPIRY_DATE` to a `SEVERE:` message.
18. THE Validation_Engine SHALL implement each cross-field rule as a named function clearly separated from single-field validation functions.

---

### Requirement 6: Row Severity Classification

**User Story:** As a data quality analyst, I want each row assigned a single severity level after all validations run, so that the output files clearly separate clean, warning, and severe records.

#### Acceptance Criteria

1. WHEN all field and cross-field validations for a row are complete, THE Classifier SHALL assign `ROW_SEVERITY` to that row.
2. WHEN all `VAL_*` columns for a row are `None`, THE Classifier SHALL set `ROW_SEVERITY` to `CLEAN`.
3. WHEN at least one `VAL_*` column for a row starts with `WARNING:` and no `VAL_*` column starts with `SEVERE:`, THE Classifier SHALL set `ROW_SEVERITY` to `WARNING`.
4. WHEN at least one `VAL_*` column for a row starts with `SEVERE:`, THE Classifier SHALL set `ROW_SEVERITY` to `SEVERE`, regardless of any WARNING values on the same row.
5. THE Classifier SHALL use exactly the values `CLEAN`, `WARNING`, and `SEVERE` in the `ROW_SEVERITY` column — no variations, no lowercase.

---

### Requirement 7: Output Writing

**User Story:** As a data quality analyst, I want the validated data written to separate output files by severity, so that downstream teams can immediately work with clean records and review problematic ones.

#### Acceptance Criteria

1. WHEN validation and classification are complete, THE Output_Writer SHALL write all rows with `ROW_SEVERITY = CLEAN` to `output/cnt_clean.csv`.
2. WHEN validation and classification are complete, THE Output_Writer SHALL write all rows with `ROW_SEVERITY = WARNING` to `output/cnt_warning.csv`.
3. WHEN validation and classification are complete, THE Output_Writer SHALL write all rows with `ROW_SEVERITY = SEVERE` to `output/cnt_severe.csv`.
4. THE Output_Writer SHALL write a summary report to `output/cnt_summary.txt` in the format specified in the ETL Engineering Standards steering file, including run date, input file name, total row count, per-severity counts and percentages, and the top failure reasons by field.
5. THE Output_Writer SHALL NOT contain any validation logic — its only responsibility is splitting the DataFrame and writing files.
6. WHEN writing output files, THE Output_Writer SHALL create the `output/` directory if it does not already exist.
7. WHEN output writing completes, THE Output_Writer SHALL log the row count and destination path for each output file to the console using the `[OUTPUT]` prefix.

---

### Requirement 8: Validation Utility Functions

**User Story:** As a software engineer, I want all field-level validation logic in a single shared utilities module, so that the same logic is reused across all rule types and future tables.

#### Acceptance Criteria

1. THE Validation_Utils SHALL implement `is_not_blank(series)` that returns a boolean Series — `True` where the value is non-null and non-whitespace, `False` otherwise.
2. THE Validation_Utils SHALL implement `is_exact_length(series, n)` that returns a boolean Series — `True` where the trimmed string length equals `n`.
3. THE Validation_Utils SHALL implement `is_max_length(series, n)` that returns a boolean Series — `True` where the string length is less than or equal to `n`.
4. THE Validation_Utils SHALL implement `is_in_allowed_values(series, values)` that returns a boolean Series — `True` where the value appears in the provided list.
5. THE Validation_Utils SHALL implement `is_valid_date(series)` that returns a boolean Series — `True` where the value is a valid calendar date in `YYYYMMDD` format.
6. THE Validation_Utils SHALL implement `is_numeric(series)` that returns a boolean Series — `True` where the value can be converted to a numeric type.
7. THE Validation_Utils SHALL implement `is_date_greater_than(series_a, series_b)` that returns a boolean Series — `True` where `series_a` represents a date strictly after `series_b`, both in `YYYYMMDD` format.
8. THE Validation_Utils SHALL implement `is_date_lte(series_a, series_b)` that returns a boolean Series — `True` where `series_a` represents a date on or before `series_b`, both in `YYYYMMDD` format.
9. EVERY function in Validation_Utils SHALL accept a Pandas Series as its primary argument and return a Pandas Series of boolean values.
10. EVERY function in Validation_Utils SHALL use Pandas vectorised operations and SHALL NOT iterate over rows with `iterrows()` or equivalent row-by-row loops.
11. EVERY function in Validation_Utils SHALL include a one-line docstring.

---

### Requirement 9: Test Data Generation

**User Story:** As a software engineer, I want a script that generates a realistic sample CNT CSV file, so that the pipeline can be demonstrated and tested without relying on real production data.

#### Acceptance Criteria

1. THE Test_Data_Generator SHALL produce a CSV file with approximately 200 rows at `sample_data/sample_cnt.csv`.
2. THE Test_Data_Generator SHALL generate approximately 100 CLEAN rows where all 32 CNT fields satisfy every applicable single-field and cross-field rule.
3. THE Test_Data_Generator SHALL generate approximately 50 WARNING rows that trigger at least one of: blank `CNT_SERV_AGENT`, blank `CNT_SERV_AGENCY`, `CNT_BASE_PLAN_CODE` left blank (triggering default + WARNING), or `CNT_JOINT_NUMBER_OF_LIVES = 1` without matching `CNT_JOINT_RATE_AGE_REASON_CODE = G`.
4. THE Test_Data_Generator SHALL generate approximately 50 SEVERE rows that trigger at least one of: invalid `CNT_ISSUE_DATE` format, `CNT_MATURE_EXPIRE_DATE <= CNT_ISSUE_DATE`, `CNT_PRODUCT_TYPE` not in the allowable list, blank `CNT_COMPANY_CODE`, `CNT_SEX_CODE = B` with `CNT_JOINT_LIFE_INDICATOR != F`, or `CNT_QUALIFICATION_CODE` in `{Q, K, I, T, P, R, U}` with `CNT_PRODUCT_TYPE` not in `{A, W, B}`.
5. WHEN generating WARNING or SEVERE rows, THE Test_Data_Generator SHALL populate a `TEST_EXPECTED_ISSUE` column with a human-readable description of the expected failure for each row.
6. THE Test_Data_Generator SHALL generate values for all 32 CNT fields in every row.

---

### Requirement 10: PDL/PL Engine Integration

**User Story:** As a PDL/PL engine operator, I want the pipeline to be invocable via a shell command with runtime parameters and return standard exit codes, so that the engine can trigger validation automatically and act on the result without manual intervention.

#### Acceptance Criteria

1. THE Pipeline SHALL be invocable by the PDL/PL engine via a shell command (e.g., `python -m cnt_etl_validation --input-file <path> --output-dir <path>`). No manual user interaction is required at runtime.
2. THE Pipeline SHALL accept `--input-file` (full path to the input CSV) and `--output-dir` (full path to the output directory) as command-line arguments supplied by the PDL/PL engine.
3. WHEN the pipeline completes successfully (all outputs written), THE Pipeline SHALL exit with code `0`.
4. WHEN the pipeline fails (missing file, unhandled exception, or any fatal error), THE Pipeline SHALL exit with code `1`.
5. THE PDL/PL engine SHALL use these exit codes to decide whether to proceed with downstream processing (exit 0) or halt and report an error (exit 1).
6. NO paths SHALL be hardcoded in the pipeline; it SHALL use only the values supplied at invocation.

---

### Requirement 11: KNIME Replacement Advantages

**User Story:** As a project stakeholder, I want the pipeline to deliver clear advantages over the legacy KNIME workflow, so that the technology shift is justified and sustainable.

#### Acceptance Criteria

1. THE Pipeline SHALL process large files significantly faster than the equivalent KNIME workflow by leveraging native Python/Pandas vectorised operations.
2. THE Pipeline codebase SHALL reside in a standard Git repository, providing full change history, branching, and code review capability — capabilities absent in KNIME's node-based workflow files.
3. THE Pipeline SHALL be extensible via code: adding new tables and rule types requires only writing Python functions, not editing visual node graphs.
4. THE Pipeline SHALL be portable — runnable anywhere Python 3.12 is installed, with no platform-specific IDE or runtime required.
5. THE Pipeline SHALL rely only on open-source packages, incurring no commercial licence costs (unlike KNIME commercial extensions).

---

### Requirement 12: Performance and Portability

**User Story:** As an ETL engineer, I want the pipeline to process large files efficiently on a standard laptop without environment-specific configuration, so that any team member can run it on any machine.

#### Acceptance Criteria

1. WHEN processing a CSV file of up to 100,000 rows, THE Pipeline SHALL complete within 5 minutes on a standard laptop.
2. THE Input_Reader SHALL read CSV files in chunks of 10,000 rows to maintain stable memory usage across files of varying size.
3. THE Validation_Engine SHALL use Pandas vectorised operations for all field validations and SHALL NOT iterate over rows with `iterrows()` or equivalent row-by-row loops.
4. THE Pipeline SHALL run on any machine with Python 3.12 and the packages listed in `requirements.txt` installed.
5. ALL file paths within the pipeline SHALL be constructed using `pathlib.Path` and SHALL NOT contain hardcoded path separators or machine-specific strings.
6. THE Rule_Loader SHALL define the Rules_File path as a named constant (`RULES_FILE_PATH`) at the top of `rule_loader.py`, and no other module SHALL reference this path.

---

### Requirement 13: Code Quality and Maintainability

**User Story:** As a software engineer on the team, I want the codebase to follow consistent standards and structural rules, so that any team member can understand and extend any module within 10 minutes.

#### Acceptance Criteria

1. EVERY Python module SHALL include a module-level docstring stating its single responsibility.
2. EVERY function in every module SHALL include a one-line docstring.
3. THE Validation_Engine SHALL NOT open any files. THE Rule_Loader SHALL NOT access the data DataFrame. THE Output_Writer SHALL NOT contain any validation logic.
4. NO module SHALL import from a module above it in the four-layer architecture (Input → Rules → Engine → Output).
5. WHERE a module exceeds 200 lines, THE module SHALL be refactored to extract responsibilities into a helper or sub-module rather than adding more lines inline.
6. THE Pipeline's `requirements.txt` SHALL pin `pandas` to `>=2.2.0` and `pytest` to `>=8.0.0` and SHALL NOT include any packages not required for Phase 1.
7. WHEN a new table is added to the pipeline, THE developer SHALL create a `validate_<table>.py` module containing a rules dictionary and a cross-table validation function. Zero changes to `field_validator.py` or `validation_engine.py` SHALL be required.
8. WHEN a bug is found in field-level validation logic, THE fix SHALL be made once in `field_validator.py` and SHALL propagate to all tables automatically without any changes to table-specific modules.

---

### Requirement 14: Unit Testing

**User Story:** As a software engineer, I want comprehensive unit tests for all validation logic, so that regressions are caught immediately and each rule can be verified in isolation.

#### Acceptance Criteria

1. EVERY Validation_Utils function SHALL have at least one test that verifies a valid input returns a passing result and at least one test that verifies an invalid input returns a failing result.
2. WHEN testing the Validation_Engine, THE test suite SHALL include at least one test covering an all-valid row (expecting `CLEAN`), at least one test covering a SEVERE trigger, at least one test covering a WARNING trigger, and at least two tests covering cross-field rule triggers.
3. WHEN testing the Classifier, THE test suite SHALL verify that a row with only `None` VAL_ values produces `ROW_SEVERITY = CLEAN`, a row with at least one WARNING and no SEVERE produces `ROW_SEVERITY = WARNING`, and a row with at least one SEVERE produces `ROW_SEVERITY = SEVERE`.
4. WHEN testing the Output_Writer, THE test suite SHALL verify that CLEAN, WARNING, and SEVERE rows are written to the correct output files.
5. THE test suite SHALL use `pytest` and SHALL be runnable with the command `pytest tests/` from the workspace root directory.
6. ALL tests SHALL pass before the pipeline is considered complete.
7. THE test suite SHALL maintain a minimum baseline of 124 passing tests, including 19 tests in `test_field_validator.py` that cover the shared field validation engine directly and independently of any table module.
