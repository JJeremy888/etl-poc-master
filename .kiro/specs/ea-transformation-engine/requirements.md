> **SUPPLEMENTARY SPEC** — subordinate to option-b-config-driven-engine, which is the authoritative top-level specification. This spec describes transformation-layer internals in more granular detail. Requirements 24-26 here are equivalent to Requirements 23-24/22 in option-b-config-driven-engine — do not implement both independently.

# Requirements Document

## Introduction

This document specifies the requirements for a metadata-driven transformation layer that extends the existing Policy Loader ETL Validation Pipeline. The transformation layer consumes validated source records (CLEAN and WARNING rows from CNT, CVG, ROL, ADD tables), applies transformation rules loaded from `rules/POC_Transformation_Mapping.csv`, and generates a fixed-width positional flat file (`ea_transaction.txt`), an intermediate columnar output (`transformed_dataframe.csv`), and a per-field audit log (`transformation_audit_log.csv`).

This feature runs AFTER the existing business validation phase. It does not modify, replace, or re-implement any existing validation components.

## Glossary

- **Transformation_Engine**: The orchestration module (`transformation_engine.py`) that iterates transformation mappings in sequence order, dispatches to handlers by Transformation Type, and assembles transformed records.
- **Mapping_Loader**: The module (`mapping_loader.py`) responsible for reading, validating, filtering, and returning structured transformation mappings from the Transformation_Mapping_CSV.
- **Flat_File_Builder**: The module (`flat_file_builder.py`) that concatenates transformed field values in mapping sequence order to produce a fixed-width positional flat file.
- **Transformation_Mapping_CSV**: The file `rules/POC_Transformation_Mapping.csv` containing all field-level transformation rules, target formats, padding rules, and source-to-target mappings.
- **EA_Transaction**: The fixed-width positional flat file (`ea_transaction.txt`) produced as the primary output of the transformation layer, intended for the End-state Administration system.
- **Transformed_DataFrame**: The intermediate columnar CSV output (`transformed_dataframe.csv`) containing one row per eligible record with target field names as column headers.
- **Audit_Log**: The per-field-per-record CSV log (`transformation_audit_log.csv`) recording the processing status of every transformation applied.
- **POC_Scope**: A column in the Transformation_Mapping_CSV indicating whether a mapping row is in scope for this POC. Values "Yes" and "Yes - Default/System" are in scope.
- **Mapping_Status**: A column in the Transformation_Mapping_CSV indicating review state. Only rows with status "Confirmed for POC Review" or "System Generated" are processed. Rows with status "Open - Clarification Needed", "Review Required", "Out of Scope", or "Not Used" are excluded.
- **DIRECT_SOURCE**: A Transformation Type that copies a source field value directly to the target field, applying formatting and padding.
- **DATE_SPLIT**: A Transformation Type that splits a YYYYMMDD date string into year (4 chars), month (2 chars), or day (2 chars) components based on Target Length and target field naming convention.
- **CONSTANT**: A Transformation Type that fills the target field with a fixed value specified in the "Default / Constant Value" column.
- **INITIALIZE_SPACES**: A Transformation Type that fills the target field entirely with space characters to the specified Target Length.
- **INITIALIZE_NUMERIC_OR_DATE**: A Transformation Type that fills the target field with zeroes or a configured default value to the specified Target Length.
- **SYSTEM_GENERATED**: A Transformation Type indicating the field value is determined at runtime by the EA system. For the POC, these fields are initialized based on Target Data Type and logged as deferred.
- **CONDITIONAL_OR_DERIVED**: A Transformation Type where the target value is computed from one or more source fields using conditional logic described in the Transformation Rule column.
- **GROUP_OR_PARENT**: A structural grouping row in the Transformation_Mapping_CSV that does not represent a processable field and is excluded from transformation processing.
- **Eligible_Record**: A source record whose ROW_SEVERITY is CLEAN or WARNING after business validation. SEVERE records are excluded from transformation.
- **Target_Length**: The number of characters the transformed field value must occupy in the positional flat file, as specified in the Transformation_Mapping_CSV.
- **Padding_Rule**: The rule governing how field values shorter than Target Length are padded. CHAR fields are right-padded with spaces. NUMERIC fields are left-padded with zeroes.
- **COMP_3**: COBOL packed decimal format (PIC S9(n)V9(m) COMP-3). For the POC, COMP-3 fields are represented as zero-padded numeric strings. Actual packed encoding is documented as a POC limitation.
- **Pipeline (extended)**: The overall ETL process, now consisting of an existing business validation phase followed by an optional transformation phase triggered by the `--run-transformation` CLI flag.

## Requirements

### Requirement 1: Mapping Loader

**User Story:** As a pipeline operator, I want transformation mappings loaded and validated from a single CSV file, so that all transformation rules are centrally managed and consistently applied.

#### Acceptance Criteria

1. WHEN the pipeline starts with the `--run-transformation` flag, THE Mapping_Loader SHALL read the Transformation_Mapping_CSV from the configured file path.
2. WHEN the Transformation_Mapping_CSV is loaded, THE Mapping_Loader SHALL validate that all expected columns are present: POC Scope, Target Section, Target Field, Target Level, Target PIC Format, Target Length, Target Data Type, Source Table(s), Source Field(s), Transformation Type, Transformation Rule, Default / Constant Value, Date Handling, Padding Rule, Truncation Rule, Dependency Table, Validation Required Before Transform, Mapping Status, Open Question / Comment, Original Sheet Row, Screen, Definition, Allowable Values.
3. WHEN filtering mappings, THE Mapping_Loader SHALL include only rows where POC Scope equals "Yes" or "Yes - Default/System".
4. WHEN filtering mappings, THE Mapping_Loader SHALL exclude rows where Transformation Type equals "GROUP_OR_PARENT".
5. WHEN filtering mappings, THE Mapping_Loader SHALL exclude rows where Mapping Status equals "Open - Clarification Needed", "Review Required", "Out of Scope", or "Not Used".
6. THE Mapping_Loader SHALL preserve field sequence order using the Original Sheet Row column for deterministic output ordering.
7. WHEN rows are excluded during filtering, THE Mapping_Loader SHALL log each exclusion with the target field name, exclusion reason, and Original Sheet Row using the `[TRANSFORM]` prefix.
8. THE Mapping_Loader SHALL be the only module that reads the Transformation_Mapping_CSV file.

### Requirement 2: Transformation Engine Orchestration

**User Story:** As a software engineer, I want a metadata-driven transformation engine with no hardcoded field mappings, so that new fields and transformation rules can be added without code changes to the engine.

#### Acceptance Criteria

1. THE Transformation_Engine SHALL iterate transformation mappings in the sequence order determined by Original Sheet Row.
2. WHEN processing a mapping row, THE Transformation_Engine SHALL dispatch to the appropriate handler function based on the Transformation Type column value.
3. THE Transformation_Engine SHALL contain no hardcoded field names, source column references, or target column references.
4. THE Transformation_Engine SHALL process only Eligible_Records (ROW_SEVERITY = CLEAN or WARNING).
5. WHEN a field-level transformation fails for a record, THE Transformation_Engine SHALL log the error, apply a default fill value for that field, and continue processing remaining fields for that record.
6. WHEN all fields for a record have been processed, THE Transformation_Engine SHALL log a per-record summary including the count of successful, skipped, and failed fields using the `[TRANSFORM]` prefix.
7. THE Transformation_Engine dispatcher SHALL be implemented as a registry (dictionary) mapping Transformation Type string values to handler functions. Adding a new Transformation Type SHALL require only registering a new handler function in the registry, with no modification to existing dispatcher logic.

### Requirement 3: DIRECT_SOURCE Transformation

**User Story:** As a data engineer, I want source field values copied directly to target fields with correct formatting, so that simple field mappings are applied consistently.

#### Acceptance Criteria

1. WHEN a mapping has Transformation Type "DIRECT_SOURCE", THE Transformation_Engine SHALL read the value from the source field specified in the Source Field(s) column of the source table specified in Source Table(s).
2. WHEN the source value is present, THE Transformation_Engine SHALL format the value to exactly Target Length characters using the applicable Padding_Rule.
3. WHEN the Target Data Type is CHAR, THE Transformation_Engine SHALL right-pad the value with spaces to Target Length.
4. WHEN the Target Data Type is NUMERIC, THE Transformation_Engine SHALL left-pad the value with zeroes to Target Length.
5. WHEN the source value is blank or missing, THE Transformation_Engine SHALL initialize the target field with spaces for CHAR types or zeroes for NUMERIC types to Target Length.
6. WHEN the formatted value exceeds Target Length, THE Transformation_Engine SHALL truncate to Target Length and log a warning.

### Requirement 4: DATE_SPLIT Transformation

**User Story:** As a data engineer, I want YYYYMMDD date values split into separate year, month, and day components, so that the EA system receives dates in its required positional format.

#### Acceptance Criteria

1. WHEN a mapping has Transformation Type "DATE_SPLIT", THE Transformation_Engine SHALL use the "Date Handling" column of the Transformation_Mapping_CSV as the primary source for determining which date component to extract (year, month, or day).
2. WHEN the "Date Handling" column is populated and describes the component (e.g., "Split YYYYMMDD into YY/MM/DD components"), THE Transformation_Engine SHALL parse that instruction to determine component extraction positions.
3. WHEN the "Date Handling" column is blank or does not clearly specify the component, THE Transformation_Engine SHALL fall back to determining the component from Target Length and target field naming convention: 4 characters = year (positions 0-3), 2 characters with "MM" or "MO" in the name = month (positions 4-5), 2 characters with "DD" or "DA" in the name = day (positions 6-7).
4. WHEN the source date value is blank, missing, or shorter than 8 characters, THE Transformation_Engine SHALL fill the target field with zeroes to Target Length and log the issue.
5. THE Transformation_Engine SHALL implement DATE_SPLIT as a single reusable function invoked by all date-split mappings.

### Requirement 5: CONSTANT Transformation

**User Story:** As a data engineer, I want constant values inserted into target fields as specified in the mapping, so that static configuration values are correctly placed in the output.

#### Acceptance Criteria

1. WHEN a mapping has Transformation Type "CONSTANT", THE Transformation_Engine SHALL use the value from the "Default / Constant Value" column as the target field value.
2. WHEN the constant value is shorter than Target Length, THE Transformation_Engine SHALL pad the value using the applicable Padding_Rule for the Target Data Type.
3. WHEN the constant value contains the token `<spaces>`, THE Transformation_Engine SHALL interpret the token as an instruction to fill the target field with space characters to Target Length.

### Requirement 6: INITIALIZE_SPACES Transformation

**User Story:** As a data engineer, I want target fields initialized with spaces when no source data is applicable, so that the positional flat file maintains correct field widths.

#### Acceptance Criteria

1. WHEN a mapping has Transformation Type "INITIALIZE_SPACES", THE Transformation_Engine SHALL fill the target field with space characters to exactly Target Length.
2. THE Transformation_Engine SHALL ignore any value in the Source Field(s) column for INITIALIZE_SPACES mappings.
3. WHEN the Default / Constant Value column contains a non-space value for an INITIALIZE_SPACES mapping, THE Transformation_Engine SHALL use that value (formatted to Target Length) instead of spaces.

### Requirement 7: INITIALIZE_NUMERIC_OR_DATE Transformation

**User Story:** As a data engineer, I want numeric and date placeholder fields initialized with zeroes or a configured default, so that downstream systems receive valid numeric placeholders.

#### Acceptance Criteria

1. WHEN a mapping has Transformation Type "INITIALIZE_NUMERIC_OR_DATE", THE Transformation_Engine SHALL fill the target field with zeroes to exactly Target Length.
2. WHEN the Default / Constant Value column contains a non-empty value, THE Transformation_Engine SHALL use that value (left-padded with zeroes to Target Length) instead of the default zero fill.
3. THE Transformation_Engine SHALL format the output to exactly Target Length characters.

### Requirement 8: SYSTEM_GENERATED Transformation

**User Story:** As a data engineer, I want system-generated fields initialized with appropriate defaults for the POC, so that the flat file structure is complete even when runtime values are unavailable.

#### Acceptance Criteria

1. WHEN a mapping has Transformation Type "SYSTEM_GENERATED", THE Transformation_Engine SHALL initialize the target field based on Target Data Type: spaces for CHAR, zeroes for NUMERIC and PACKED_DECIMAL.
2. WHEN the Default / Constant Value column contains a non-empty value for a SYSTEM_GENERATED mapping, THE Transformation_Engine SHALL use that value formatted to Target Length.
3. WHEN processing a SYSTEM_GENERATED field, THE Transformation_Engine SHALL record the field in the Audit_Log as a placeholder whose runtime value is determined by the EA production system.

### Requirement 9: CONDITIONAL_OR_DERIVED Transformation

**User Story:** As a data engineer, I want conditional business logic applied to derive target field values from multiple source fields, so that complex EA system requirements are met.

#### Acceptance Criteria

1. WHEN a mapping has Transformation Type "CONDITIONAL_OR_DERIVED" and the Transformation Rule column contains clearly described logic, THE Transformation_Engine SHALL implement that logic in a named reusable function.
2. WHEN a mapping has Transformation Type "CONDITIONAL_OR_DERIVED" and the Transformation Rule column contains ambiguous or incomplete logic, THE Transformation_Engine SHALL skip the field, initialize with the appropriate default for the Target Data Type, and log the skip reason in the Audit_Log.
3. THE Transformation_Engine SHALL support adding new CONDITIONAL_OR_DERIVED rule functions without modifying the core engine dispatch logic.
4. WHEN the derived value is computed, THE Transformation_Engine SHALL format it to exactly Target Length using the applicable Padding_Rule.

### Requirement 10: Field Formatting and Padding

**User Story:** As a data engineer, I want all transformed field values to be exactly the specified target length with correct padding, so that the positional flat file has valid fixed-width records.

#### Acceptance Criteria

1. WHEN the Target Data Type is CHAR, THE Transformation_Engine SHALL right-pad the value with spaces to exactly Target Length.
2. WHEN the Target Data Type is NUMERIC, THE Transformation_Engine SHALL left-pad the value with zeroes to exactly Target Length.
3. WHEN the Target Data Type is PACKED_DECIMAL, THE Transformation_Engine SHALL represent the value as a zero-padded numeric string of exactly Target Length and document actual COMP-3 encoding as a POC limitation.
4. THE Transformation_Engine SHALL verify that every transformed field value is exactly Target Length characters after formatting.
5. IF a CHAR field value exceeds Target Length after formatting, THEN THE Transformation_Engine SHALL truncate to Target Length and log a warning in the Audit_Log.
6. IF a NUMERIC, PACKED_DECIMAL, or key identifier field value exceeds Target Length after formatting, THEN THE Transformation_Engine SHALL NOT truncate. Instead, it SHALL flag the field as an error, exclude the record from the flat file output, and record the length mismatch in the Audit_Log with processing_status "ERROR".

> **R4 Decision (July 2026):** Over-length NUMERIC/PACKED_DECIMAL fields are kept and force-fitted (left-truncated to Target Length) with an audit ERROR entry. Records are NOT excluded for single-field numeric overflow. This is a POC pragmatic decision — production may revert to exclusion after BA review.

### Requirement 11: Positional Flat-File Builder

**User Story:** As a pipeline operator, I want a fixed-width positional flat file generated from transformed records, so that the EA system can consume the output in its expected format.

#### Acceptance Criteria

1. THE Flat_File_Builder SHALL concatenate all transformed target field values in the sequence order determined by Original Sheet Row.
2. THE Flat_File_Builder SHALL produce one output line per Eligible_Record with no delimiters between fields.
3. WHEN all fields are concatenated for a record, THE Flat_File_Builder SHALL verify the total record length equals the sum of all Target Lengths from the active mapping set.
4. IF the total record length for any record does not equal the expected sum, THEN THE Flat_File_Builder SHALL log an error, exclude that record from the output file, record the exclusion in the Audit_Log with processing_status "ERROR", and include the excluded record in the pipeline completion summary count.
5. THE Flat_File_Builder SHALL write the output to `ea_transaction.txt` in the configured output directory.

### Requirement 12: Intermediate Columnar Output

**User Story:** As a data analyst, I want a CSV file with transformed values in named columns, so that I can inspect and validate individual field transformations.

#### Acceptance Criteria

1. THE Transformation_Engine SHALL produce a CSV file named `transformed_dataframe.csv` in the configured output directory.
2. THE Transformation_Engine SHALL use target field names from the Transformation_Mapping_CSV as column headers.
3. THE Transformation_Engine SHALL write one row per Eligible_Record.
4. THE Transformation_Engine SHALL preserve the mapping sequence order for column ordering.

### Requirement 13: Transformation Audit Log

**User Story:** As a pipeline operator, I want a detailed per-field audit log of every transformation applied, so that I can trace data lineage and diagnose issues without re-running the pipeline.

#### Acceptance Criteria

1. THE Transformation_Engine SHALL produce a CSV file named `transformation_audit_log.csv` in the configured output directory.
2. THE Audit_Log SHALL contain one row per field per record with columns: record_id, source_table, source_field, target_field, transformation_type, mapping_status, processing_status, output_value_length, error_or_skip_reason.
3. THE Audit_Log SHALL use processing_status values: "SUCCESS" when the transformation completed normally, "SKIPPED" when the field was intentionally bypassed, "ERROR" when the transformation failed.
4. WHEN a transformation fails or is skipped, THE Audit_Log SHALL include a descriptive reason in the error_or_skip_reason column.
5. THE Transformation_Engine SHALL not silently discard any field processing result without an Audit_Log entry.

### Requirement 14: Integration with Existing Validation Output

**User Story:** As a pipeline operator, I want the transformation phase to run only when explicitly requested and to consume validation results without modifying the validation pipeline, so that existing behavior is preserved.

#### Acceptance Criteria

1. WHEN the `--run-transformation` flag is provided on the command line, THE Pipeline SHALL execute the transformation phase after business validation completes.
2. WHEN the `--run-transformation` flag is not provided, THE Pipeline SHALL produce only validation outputs with no transformation processing.
3. THE Transformation_Engine SHALL consume only Eligible_Records (ROW_SEVERITY = CLEAN or WARNING) from each validated table DataFrame.
4. THE Transformation_Engine SHALL exclude all records with ROW_SEVERITY = SEVERE from transformation processing.
5. THE Pipeline SHALL not modify any existing validation output files when the `--run-transformation` flag is present.

### Requirement 15: Multi-Table Record Assembly

**User Story:** As a data engineer, I want records assembled from multiple source tables joined by policy identifier, so that target fields sourced from different tables are correctly populated.

#### Acceptance Criteria

1. WHEN a mapping row specifies multiple source tables separated by semicolons in the Source Table(s) column, THE Transformation_Engine SHALL join records from those tables using the policy identifier (CNT_POLICY_NUMBER) as the primary join key.
2. WHEN a child table (CVG, ROL, ADD) requires additional join identifiers beyond policy number (such as PERSON_SEQUENCE or coverage sequence), THE Transformation_Engine SHALL derive those identifiers from the Transformation_Mapping_CSV metadata (Dependency Table, Transformation Rule, or Source Field(s) columns) or from a dedicated join configuration file. Join keys SHALL NOT be hardcoded in the Transformation_Engine.
3. WHEN a child table (CVG, ROL, ADD) has no matching record for a given policy identifier and applicable secondary keys, THE Transformation_Engine SHALL initialize the affected target fields with the appropriate default for their Target Data Type and log the missing join.
4. THE Transformation_Engine SHALL support source table combinations including: CNT alone, CVG alone, ROL alone, ADD alone, ADD;ROL, CNT;CVG, and any other semicolon-separated combination of CNT, CVG, ROL, and ADD present in the Transformation_Mapping_CSV.

### Requirement 16: Architecture Preservation

**User Story:** As a software architect, I want the transformation layer implemented as new modules only, so that existing validation code and tests remain unchanged.

#### Acceptance Criteria

1. THE transformation feature SHALL be implemented in new modules only: `src/mapping_loader.py`, `src/transformation_engine.py`, `src/flat_file_builder.py`, `src/transformation_utils.py`.
2. THE transformation feature SHALL not modify `src/rule_loader.py`, `src/validation_engine.py`, `src/field_validator.py`, `src/validation_utils.py`, `src/input_reader.py`, `src/output_writer.py`, `src/validate_cvg.py`, `src/validate_rol.py`, or `src/validate_add.py`.
3. THE transformation feature SHALL extend `src/main.py` only to add the `--run-transformation` CLI flag and invoke the transformation phase after validation.
4. THE transformation feature SHALL not cause any existing test to fail.

### Requirement 17: Testing

**User Story:** As a quality engineer, I want comprehensive tests for the transformation layer, so that correctness is verified for each transformation type and the end-to-end flow.

#### Acceptance Criteria

1. THE test suite SHALL include unit tests for each transformation handler: DIRECT_SOURCE, DATE_SPLIT, CONSTANT, INITIALIZE_SPACES, INITIALIZE_NUMERIC_OR_DATE, SYSTEM_GENERATED, CONDITIONAL_OR_DERIVED.
2. THE test suite SHALL include unit tests for the Mapping_Loader covering: column validation, POC Scope filtering, GROUP_OR_PARENT exclusion, Mapping Status exclusion, and sequence ordering.
3. THE test suite SHALL include unit tests for the Flat_File_Builder covering: correct concatenation order, record length verification, and output file writing.
4. THE test suite SHALL include a regression test confirming that all existing validation tests continue to pass unchanged. The baseline test count SHALL be captured in the Design phase.
5. THE test suite SHALL include an end-to-end test exercising the full flow: validate source data, transform eligible records, produce flat file, produce columnar CSV, and produce audit log.
6. THE total test count SHALL increase beyond the existing validation baseline after transformation tests are added.

### Requirement 18: Error Handling

**User Story:** As a pipeline operator, I want clear error behavior for each failure mode, so that I can diagnose and resolve issues without ambiguity.

#### Acceptance Criteria

1. IF the Transformation_Mapping_CSV file is missing or unreadable, THEN THE Pipeline SHALL log an error message and exit with code 1.
2. WHEN a field-level transformation fails for a record, THE Transformation_Engine SHALL log the error, fill the field with the appropriate default value for its Target Data Type, and continue processing remaining fields.
3. WHEN all fields fail for a single record, THE Transformation_Engine SHALL exclude that record from the flat file output and log the exclusion.
4. IF the output directory is unwritable or a file write fails, THEN THE Pipeline SHALL log an error message and exit with code 1.
5. WHEN the transformation phase completes with partial success (some records transformed, some excluded), THE Pipeline SHALL exit with code 0 and log a summary of records processed, succeeded, and excluded.

### Requirement 19: Configuration and Extensibility

**User Story:** As a software engineer, I want the transformation layer designed for easy extension, so that new source tables and transformation types can be added with minimal code changes.

#### Acceptance Criteria

1. THE Transformation_Engine SHALL support adding a new source table by providing its validated DataFrame to the transformation phase and adding corresponding rows to the Transformation_Mapping_CSV, with no changes to existing transformation modules.
2. THE Transformation_Engine SHALL support adding a new Transformation Type by implementing a new handler function and registering it in the dispatcher, with no changes to existing handler functions.
3. THE Mapping_Loader SHALL expose the Transformation_Mapping_CSV file path as a configurable constant that can be overridden without modifying function internals.

### Requirement 20: Default and System Mappings Without Source Data

**User Story:** As a data engineer, I want default and system-generated mappings processed independently of source table data, so that fields marked "Yes - Default/System" are populated even when no source field lookup is required.

#### Acceptance Criteria

1. THE Transformation_Engine SHALL correctly process mappings where POC Scope equals "Yes - Default/System" regardless of whether the Source Field(s) column is populated.
2. WHEN a "Yes - Default/System" mapping has an empty or blank Source Field(s) value, THE Transformation_Engine SHALL NOT attempt a source table lookup and SHALL apply the transformation using only the Default / Constant Value, Target Data Type, and Target Length metadata.
3. WHEN a "Yes - Default/System" mapping references a source table not available in the current pipeline execution (e.g., PRM, FIN), THE Transformation_Engine SHALL treat it as a no-source mapping and apply the default initialization for the Target Data Type.

### Requirement 21: Output Reproducibility

**User Story:** As a quality engineer, I want identical outputs from identical inputs, so that test results are deterministic and regressions are detectable by file comparison.

#### Acceptance Criteria

1. GIVEN the same input data files and the same Transformation_Mapping_CSV, THE Pipeline SHALL produce byte-identical `ea_transaction.txt` and `transformed_dataframe.csv` on repeated runs.
2. THE `transformation_audit_log.csv` SHALL be logically identical on repeated runs. Any run-time timestamps included in the audit log SHALL be clearly identified in a dedicated column and excluded from byte-comparison checks in regression tests.
3. THE Transformation_Engine SHALL NOT introduce any non-deterministic elements (random values, process IDs) into the `ea_transaction.txt` or `transformed_dataframe.csv` output files.
4. THE Audit_Log record ordering SHALL be deterministic: sorted by record sequence then by field sequence (Original Sheet Row).

### Requirement 22: Consumption of Validated In-Memory DataFrames

**User Story:** As a software architect, I want the transformation engine to consume validated DataFrames directly from the pipeline's in-memory state, so that there is no I/O overhead or dependency on intermediate validation output files.

#### Acceptance Criteria

1. THE Transformation_Engine SHALL accept validated in-memory Pandas DataFrames (CNT, CVG, ROL, ADD) as input parameters, produced by the existing validation phase within the same pipeline execution.
2. THE Transformation_Engine SHALL NOT read validation output CSV files (cnt_clean.csv, cnt_warning.csv, cvg_clean.csv, etc.) from disk as its source of validated data during a normal pipeline run.
3. THE Pipeline SHALL pass the validated DataFrames directly from the validation phase to the transformation phase within the same process invocation.
4. A standalone testing mode MAY load previously-written validated CSV files from disk to enable isolated transformation testing, but this SHALL NOT be the default pipeline behavior.


### Requirement 23: Field Name Authority and Traceability

**User Story:** As a project lead, I want all source field names consumed by the transformation layer to trace directly to Nancy's authoritative DB_Section sheets, so that no fabricated, abbreviated, or guessed field names enter transformation_mappings.csv and cause silent mismatches between the staging schema, validation rules, and transformation output.

#### Acceptance Criteria

1. ALL source field names referenced in the Source Field(s) column of the Transformation_Mapping_CSV SHALL come directly from the "Field name" column (Column A) of the DB_Section_*.csv sheets (Contract, Coverage, Roles, Address), which reflect Nancy's authoritative field definitions.
2. NO field name SHALL be invented, abbreviated, renamed, or guessed at — even temporarily or as a placeholder — at any point in the Transformation_Mapping_CSV or the transformation modules.
3. IF a transformation mapping references a source field that does not appear in any DB_Section sheet, THAT field SHALL be flagged as an open question for BA confirmation in the BA Validation Report's Questions section. The system SHALL NOT assume or fabricate a name to fill the gap.
4. WHEN the Copybook Field column (Column C) of a DB_Section sheet provides an alternative name, THE project SHALL use the "Field name" column (Column A) as the canonical source field name in the Transformation_Mapping_CSV. The Copybook Field name SHALL only appear in the Definition or Notes columns for traceability to the legacy system.
5. THE Mapping_Loader SHALL log a warning for any Source Field(s) value that does not match a known DB_Section Column A entry, so that unverified field names are surfaced during pipeline execution rather than silently accepted.
6. WHEN a mismatch is discovered between a source field name used in the Transformation_Mapping_CSV and the DB_Section sheet's "Field name" column, THE correction SHALL rename the mapping's usage to match the sheet — never the other way around.
7. FOR THE CURRENT POC PHASE, the "Field name" column (Column A) of the DB_Section_*.csv sheets IS the staging schema — no separate staging database file exists or is needed. The Mapping_Loader SHALL treat these four sheets as the complete and sufficient reference for all source field names.
8. WHEN this project moves beyond POC into full development against a provisioned, live staging database, THIS requirement SHALL be revisited and explicitly updated to point to that live schema as the new source of truth — since a real database may enforce constraints (length limits, reserved words, naming conventions) that cause its column names to diverge from Column A. Until that update happens, Column A remains authoritative.
9. BEFORE creating or modifying transformation_mappings.csv, the DB_Section_*.csv sheets SHALL be read in that same working session, and every source field name used SHALL be verified against them before the file is written — not after.
10. THE verification script (scripts/verify_field_names.py) SHALL check every Source Field(s) value in the Transformation_Mapping_CSV against the DB_Section sheets' "Field name" column, and report any name not found there. This check SHALL be run and shown clean before transformation_mappings.csv is considered complete.
11. WHEN a Source Field's value is missing or blank AND no default or fallback rule is explicitly stated in DB_Section_*.csv or Transformation_Mapping_CSV, THEN the Mapping_Loader SHALL NOT apply an invented default value, and SHALL instead flag the field as an open question for BA confirmation.

### Requirement 24: EA Transaction Mapping Source of Truth

**User Story:** As a data engineer, I want transformation_mappings.csv generated mechanically from rules/EA_Transaction_Mapping.xlsx using explicit, bounded parsing rules, so that every mapping entry traces directly to a business-provided row and no mapping is invented or inferred beyond what the source states.

#### Acceptance Criteria

1. THE file rules/EA_Transaction_Mapping.xlsx, sheet "Trx Mapping", SHALL be the sole authoritative source for generating the Transformation_Mapping_CSV. Sheet1 (scratch notes) SHALL be excluded from generation entirely.
2. THE target_field SHALL be parsed from Column A ("agent") by stripping the leading COBOL level number and whitespace (e.g., "15  COMPANY-CODE" → "COMPANY-CODE").
3. THE source_field SHALL be taken from Column I ("Policy Data Loader Mapping") as-is.
4. THE source_table SHALL be inferred ONLY from the prefix of the value in Column I (CNT_ → CNT, CVG_ → CVG, ROL_ → ROL, ADD_ → ADD). If Column I is blank or says "System generated", source_table is not applicable.
5. THE target_length and target_data_type SHALL be parsed from the PIC clause in Column C ("Field Format") using these EXACT rules only: PIC X(n) → CHAR length n; PIC 9(n) → NUMERIC length n; PIC 99 → NUMERIC length 2; PIC S9(n) COMP → BINARY length n; PIC S9(n)V9(m) COMP-3 → PACKED_DECIMAL length n+m. Any PIC clause not matching one of these exact patterns SHALL be flagged as "PIC clause not recognized — needs manual review" — not guessed at.
6. THE transformation_type SHALL be determined by these bounded inference rules ONLY, applied in this exact order (first match wins): (a) No PIC clause in Col C (group/parent row) → GROUP_OR_PARENT; (b) Col I = "System generated" → SYSTEM_GENERATED; (c) Col I blank AND Col G or K contains "Move spaces" → INITIALIZE_SPACES; (d) Col I has exactly one non-blank value AND no other rule above applies → DIRECT_SOURCE, UNLESS the target field name matches a YY/MM/DD date-component pattern shared with adjacent rows referencing the same source field → DATE_SPLIT; (e) Anything not matching (a)-(d) → CONDITIONAL_OR_DERIVED, flagged as "transformation type inferred with low confidence — needs manual review".
7. THE Mapping_Loader SHALL derive padding_rule mechanically from data_type only: CHAR → right_space; NUMERIC/BINARY/PACKED_DECIMAL → left_zero. No other inference permitted.
8. THE default_value and truncation_rule SHALL be left blank UNLESS Column G, K, or L contains an explicit stated value or instruction. No inference.
9. THE mapping_id SHALL be generated sequentially (MAP_001, MAP_002, ...) in row order. THE sequence column SHALL use row number to preserve original order.
10. ANY row where required parsing fails (PIC clause unrecognized, target field name cannot be extracted, source field ambiguous) SHALL be output to a separate "needs review" list — not included in the Transformation_Mapping_CSV with a guessed value, and not silently dropped.

### Requirement 25: Dual Output Format

**User Story:** As a BA, I want both a positional flat file and a CSV equivalent produced from a single transformation pass, so that downstream systems receive the fixed-width format they require while I can review the same data in a human-readable columnar format without any recomputation.

#### Acceptance Criteria

1. THE Transformation_Engine SHALL produce both output formats from a single transformation pass using existing logic — no duplicate processing or additional transformation load.
2. THE positional flat file (ea_transaction.txt) SHALL be retained for any downstream system requiring the fixed-width format.
3. A CSV equivalent SHALL be produced using the same computed field values, reformatted only at the final write step — not recomputed.
4. THE CSV output SHALL include readable column headers using actual target field names (e.g., "COMPANY-CODE"), not positional offsets.
5. THE CSV output is the BA-facing review deliverable; the flat file remains the system-of-record format for downstream consumers that need it.

### Requirement 26: Excel-Based Sample Data

**User Story:** As a project lead, I want the pipeline to consume business-provided sample data directly from the Sample_*_Data.xlsx workbooks, so that test data exactly matches what the BA team prepared and no synthetic generator can introduce fabricated values or field names.

#### Acceptance Criteria

1. THE 4 Sample_*_Data.xlsx files in staging_data/ (Contract, Coverage, Roles, Address) SHALL replace any former synthetic data generator entirely. No synthetic data generator SHALL exist in this project.
2. WHEN reading Sample_*_Data.xlsx files, THE reader SHALL use dtype=str (or equivalent text-mode reading) to prevent numeric reinterpretation — specifically: CVG_SEQUENCE_NUMBER and CVG_PERSON_SEQ are stored as integers in the source and must not lose leading zeros if real data ever contains them.
3. THE reader SHALL write the Excel data to CSV format for pipeline consumption, preserving all cell values exactly as text with no reformatting, rounding, or date conversion applied.
4. THE Pipeline SHALL NOT modify, append to, or reinterpret any value from the Sample_*_Data.xlsx source during the read/write process.
