# Implementation Plan: Option B — Config-Driven PySpark Validation & Transformation Engine

## Overview

This plan implements a PySpark-based config-driven engine that interprets validation rules and transformation mappings from versioned Template CSV files at runtime. The engine operates on staging data (simulated locally as Parquet/CSV), validates records using set-based DataFrame operations, classifies severity, logs errors with full diagnostics, builds a dependency graph for targeted revalidation, transforms eligible records, and outputs positional flat files via pluggable adapters. No code is generated at any point.

All code lives under `option_b/` as a parallel, independent system. The four `.kiro/hooks/` are already updated to reference `templates/v1/`, `option_b/tests/`, and `option_b/main.py`.

## Tasks

- [ ] 1. Build Template CSV files from finalized sources
  - [x] 1.1 Create `templates/v1/validation_rules.csv` from the rule sources
    - **SUPERSEDED:** the original 4-file merge (`DB_Section_*`) has been replaced by the single master workbook `rules/Validation_Rules_Master.xlsx` + `scripts/generate_config_from_master.py` (see Task 10). The current `validation_rules.csv` (261 field rules) and `cross_references.csv` (164 cross-reference rules) are generated from that workbook.
    - _Requirements: 1.1, 1.2, 10.1, 10.2, 21.1_
  - [x] 1.2 Create `templates/v1/transformation_mappings.csv` from POC_Transformation_Mapping_scoped.csv
    - Transform the 400-row `rules/POC_Transformation_Mapping_scoped.csv` into the template schema (mapping_id, source_table, source_field, target_field, transformation_type, target_length, target_data_type, padding_rule, default_value, date_handling, truncation_rule, sequence, description)
    - Exclude the 15 deferred rows (JIRA 107, JIRA 416, JIRA 403, translation table lookups, Nancy's co-owner sample-dataset) — mark them as Phase 2 in comments
    - _Requirements: 10.3, 18.1, 18.2_
  - [x] 1.3 Create `templates/v1/table_dependencies.csv`
    - Declare CVG→CNT, ROL→CNT, ADD→CNT with compound join keys (COMPANY_CODE + POLICY_NUMBER)
    - _Requirements: 11.2, 11.4, 14.1_
  - [x] 1.4 Create `templates/v1/output_config.csv`
    - Define the EA positional flat file output adapter entry (adapter_type=positional_flat_file, delivery_mechanism=local_filesystem, delivery_target=output/ea_transaction.txt, include_severity=CLEAN|WARNING)
    - _Requirements: 6.2, 6.4, 15.1_
  - [x] 1.5 Create `templates/versions.json` and template schema JSON files
    - Create `templates/versions.json` with initial version v1 entry and timestamp
    - Create schema JSON files in `templates/schema/` for each template section (validation_rules_schema.json, transformation_mappings_schema.json, output_config_schema.json, table_dependencies_schema.json) defining required columns, data types, and valid values
    - _Requirements: 1.3, 1.5, 10.4, 10.5_

- [x] 2. Set up project structure and core interfaces
  - [x] 2.1 Create `option_b/` directory structure with all `__init__.py` files
    - Create directories: option_b/, option_b/config/, option_b/input/, option_b/engine/, option_b/error/, option_b/output/, option_b/audit/, option_b/tests/
    - Create `__init__.py` in each package directory
    - Create `staging_data/` directory for POC Parquet files
    - _Requirements: 16.1, 16.2_
  - [x] 2.2 Create `option_b/config/schema_definitions.py` with fixed schema constants
    - Define VALIDATION_RULES_SCHEMA, TRANSFORMATION_MAPPINGS_SCHEMA, OUTPUT_CONFIG_SCHEMA, TABLE_DEPENDENCIES_SCHEMA as dicts specifying required columns, data types, and valid enum values for each template section
    - Define REGISTERED_RULE_TYPES and REGISTERED_TRANSFORMATION_TYPES as sets of known type strings
    - _Requirements: 1.2, 8.7, 10.5_

- [x] 3. Checkpoint — Verify templates and project structure
  - Ensure all template CSV files are well-formed and schema JSONs match the defined schema constants. Ask the user if questions arise.

- [x] 4. Implement Template Loading and Schema Validation
  - [x] 4.1 Implement `option_b/config/template_loader.py`
    - `load_template(template_dir, spark)` — read all 4 CSV files into Spark DataFrames, validate each against its schema, check that all rule_type and transformation_type values are registered, return parsed template dict
    - `validate_schema(section_df, section_name, schema)` — verify required columns exist, data types match, enum fields contain valid values; raise ValueError with descriptive message on violation
    - Reject templates that reference unregistered Rule_Types or Transformation_Types with clear error messages
    - _Requirements: 1.1, 1.2, 1.6, 3.5, 8.7, 10.5_
  - [x] 4.2 Implement `option_b/config/template_versioner.py`
    - `get_current_version(template_dir)` — read versions.json, return active version info
    - `create_version(template_dir, description)` — snapshot current template files, assign new version ID and timestamp, update versions.json
    - `compare_versions(template_dir, v1_id, v2_id)` — diff two versions, return list of changes
    - `retrieve_version(template_dir, version_id)` — load a specific historical version
    - _Requirements: 1.3, 1.4, 1.5_
  - [ ]* 4.3 Write unit tests for template_loader
    - Test valid template loads successfully
    - Test missing required column raises ValueError
    - Test invalid rule_type logged as warning and skipped
    - Test unregistered transformation_type raises rejection error
    - **Property 1: Template Schema Rejection**
    - **Validates: Requirements 1.2, 1.6, 3.5, 8.7, 10.5**
  - [ ]* 4.4 Write unit tests for template_versioner
    - Test version creation increments version ID and stores timestamp
    - Test comparison returns correct diff
    - Test retrieval of historical version
    - _Requirements: 1.3, 1.4, 1.5_

- [x] 5. Implement Staging Reader
  - [x] 5.1 Implement `option_b/input/staging_reader.py`
    - `read_staging_table(spark, table_name, config)` — read from Parquet (POC) or JDBC (production) based on config; return DataFrame
    - `read_all_staging_tables(spark, table_names, config)` — read all required tables, return dict[str, DataFrame]; log diagnostic and return empty DataFrame for missing/empty tables
    - Abstracted behind config so switching from local Parquet to Glue Data Catalog is configuration-only
    - _Requirements: 2.1, 2.2, 2.3, 2.5, 16.2, 16.4_
  - [x] 5.2 Create POC staging data in `staging_data/` as Parquet files
    - Convert sample_cnt.csv (200 rows), sample_cvg.csv (150 rows), sample_rol.csv (150 rows), sample_add.csv (150 rows) to Parquet format for the POC staging database
    - _Requirements: 16.2_
  - [ ]* 5.3 Write unit tests for staging_reader
    - Test successful read of existing Parquet file
    - Test missing table returns empty DataFrame with diagnostic log
    - Test empty table returns empty DataFrame with diagnostic log
    - **Property 7: Missing Table Graceful Skip**
    - **Validates: Requirements 2.5, 9.3, 11.5**

- [ ] 6. Implement Rule Expression Compiler
  - [x] 6.1 Implement `option_b/engine/presence_format_rules.py`
    - Compile not_blank, exact_length, max_length, allowed_values, valid_date, numeric into PySpark Column expressions
    - Each function takes a rule dict, returns a Column that evaluates to None (pass) or severity-prefixed error message (fail)
    - _Requirements: 3.1, 4.1, 4.3, 19.2_
  - [x] 6.2 Implement `option_b/engine/range_rules.py`
    - Compile date_greater_than, date_lte, numeric_min, numeric_max into PySpark Column expressions
    - Each function takes a rule dict, returns a Column that evaluates to None (pass) or severity-prefixed error message (fail)
    - _Requirements: 3.2, 4.1_
  - [x] 6.3 Implement `option_b/engine/cross_reference_rules.py`
    - `apply_cross_reference(child_df, parent_df, rule)` — implement as left anti-join on join keys (including multi-field compound keys), mark VAL_ column with error for non-matching records
    - Record DependencyLink entries for each cross-reference evaluation (pass or fail)
    - _Requirements: 3.3, 4.6, 11.1, 11.4, 13.1_
  - [x] 6.4 Implement `option_b/engine/conditional_rules.py`
    - `apply_conditional_rule(df, rule)` — evaluate precondition (eq, neq, in, not_in, blank, not_blank), apply dependent check only when precondition is true, skip (None) when false
    - Support dependent checks of any registered Rule_Type
    - _Requirements: 3.4, 12.1, 12.2, 12.3, 12.4, 12.5_
  - [x] 6.5 Implement `option_b/engine/rule_compiler.py`
    - `compile_rule(rule)` — dispatch to appropriate rule type handler based on rule["rule_type"]
    - `compile_all_rules(rules, table_name)` — compile all rules for a table into (VAL_column_name, Column) pairs
    - Handle unrecognized rule_types by logging a warning and skipping
    - _Requirements: 3.5, 3.6, 19.2_
  - [ ]* 6.6 Write property tests for rule compiler
    - **Property 2: Presence/Format Rule Correctness**
    - **Validates: Requirements 3.1, 17.4**
  - [ ]* 6.7 Write property tests for range rules
    - **Property 3: Range Rule Correctness**
    - **Validates: Requirements 3.2**
  - [ ]* 6.8 Write property tests for cross-reference rules
    - **Property 4: Cross-Reference Join Correctness**
    - **Validates: Requirements 3.3, 11.1, 11.4**
  - [ ]* 6.9 Write property tests for conditional rules
    - **Property 5: Conditional Rule Evaluation**
    - **Validates: Requirements 3.4, 12.1, 12.2, 12.3, 12.4**

- [x] 7. Implement Severity Classification
  - [x] 7.1 Implement `option_b/engine/severity_classifier.py`
    - `classify_severity(df)` — scan all VAL_ columns; assign ROW_SEVERITY = SEVERE if any starts with "SEVERE:", WARNING if any starts with "WARNING:" and none start with "SEVERE:", CLEAN if all are None
    - Uses only PySpark column expressions, no Python row iteration
    - _Requirements: 17.1, 17.4, 4.1, 4.3_
  - [ ]* 7.2 Write property tests for severity classification
    - **Property 14: Severity Classification**
    - **Validates: Requirements 17.1, 17.4**

- [x] 8. Implement Error Logging
  - [x] 8.1 Implement `option_b/error/error_logger.py`
    - `log_errors(validated_df, batch_run_id, template_version)` — extract all non-None VAL_ columns, create Error_Record dicts with full diagnostics (table_name, field_name, rule_id, rule_type, severity, failing_value, referenced_table/field/value for cross-refs, precondition for conditional failures)
    - `persist_errors(error_records, output_dir)` — write to Parquet (POC) or database (production)
    - `query_errors(filters, output_dir)` — filter errors by table, field, rule, severity, batch
    - _Requirements: 5.1, 5.2, 5.3, 17.5_
  - [ ]* 8.2 Write property tests for error logging
    - **Property 8: Error Record Diagnostic Completeness**
    - **Validates: Requirements 5.1, 11.3, 12.5**

- [x] 9. Checkpoint — Verify rules compile and classify correctly
  - Ensure all tests pass for template loading, rule compilation, severity classification, and error logging. Ask the user if questions arise.

- [x] 10. Implement Dependency Graph
  - [x] 10.1 Implement `option_b/engine/dependency_graph.py`
    - `build_dependency_graph(cross_ref_results, batch_run_id, template_version)` — collect all DependencyLink records from cross-reference evaluations
    - `persist_graph(links, output_dir)` — write to Parquet (POC)
    - `load_graph(output_dir)` — read existing dependency graph
    - `check_staleness(graph_template_version, active_template_version)` — detect version mismatch
    - `find_affected_records(graph, corrected_table, corrected_record_key)` — forward lookup: find all child records depending on the corrected reference
    - _Requirements: 13.1, 13.4, 13.5_
  - [ ]* 10.2 Write property tests for dependency graph
    - **Property 11: Dependency Link Completeness**
    - **Validates: Requirements 13.1**
    - **Property 10: Staleness Detection**
    - **Validates: Requirements 13.5**

- [x] 11. Implement Validation Orchestrator
  - [x] 11.1 Implement `option_b/engine/validation_orchestrator.py`
    - `determine_table_order(dependencies)` — topological sort of table dependencies; raise ValueError on cycle detection with clear message identifying tables involved
    - `run_validation(spark, template, staging_reader)` — orchestrate full validation: determine order, read tables, compile rules, apply rules per table (parents first), apply cross-reference joins, classify severity, log errors, build dependency graph. Return dict[table_name, validated_DataFrame_with_severity]
    - Ensure all N applicable rules evaluated per record (no short-circuiting)
    - _Requirements: 3.6, 4.1, 4.3, 14.1, 14.2, 14.3, 14.4_
  - [ ]* 11.2 Write property tests for validation orchestrator
    - **Property 6: Complete Rule Evaluation**
    - **Validates: Requirements 3.6**
    - **Property 12: Topological Table Order**
    - **Validates: Requirements 14.1, 14.2**
    - **Property 13: Circular Dependency Detection**
    - **Validates: Requirements 14.4**

- [x] 12. Implement Targeted Revalidation
  - [x] 12.1 Implement `option_b/error/targeted_revalidation.py`
    - `revalidate(spark, template, staging_reader, corrected_table, corrected_record_key, graph_dir)` — check staleness, load dependency graph, identify affected records, re-read affected records from staging, re-apply relevant rules, update error store (clear resolved, add new), update dependency graph links
    - Reject if graph template version doesn't match active template version
    - _Requirements: 5.4, 5.5, 5.6, 13.2, 13.3, 13.5_
  - [ ]* 12.2 Write property tests for targeted revalidation
    - **Property 9: Targeted Revalidation Scope**
    - **Validates: Requirements 5.4, 5.5, 13.2, 13.3**

- [x] 13. Implement Transformation Executor
  - [x] 13.1 Implement `option_b/engine/transformation_executor.py`
    - `transform(template, validated_dfs)` — filter to CLEAN+WARNING records only (exclude SEVERE), apply all transformation mappings in sequence order as PySpark column expressions
    - Support transformation types: direct_copy, date_split_year, date_split_month, date_split_day, constant, space_fill, zero_fill, conditional_derived
    - Apply padding (right_space for CHAR, left_zero for NUMERIC) and truncation per field to exact target_length
    - On field failure: log error, apply default fill for data type, continue remaining fields
    - _Requirements: 17.2, 17.3, 18.1, 18.2, 18.3, 18.4, 18.5, 4.2_
  - [ ]* 13.2 Write property tests for transformation
    - **Property 15: Eligibility Filter**
    - **Validates: Requirements 17.2, 17.3**
    - **Property 16: Field Formatting Invariant**
    - **Validates: Requirements 15.5, 18.4**
    - **Property 19: Transformation Failure Recovery**
    - **Validates: Requirements 18.5**

- [x] 14. Implement Output Adapter
  - [x] 14.1 Implement `option_b/output/base_adapter.py` and `option_b/output/adapter_registry.py`
    - Define abstract OutputAdapter base class with `format_and_deliver(transformed_df, output_config) -> str`
    - Implement ADAPTER_REGISTRY and DELIVERY_REGISTRY dicts
    - `get_adapter(adapter_type)` — lookup adapter by type string, raise KeyError if unregistered
    - `deliver(mechanism, payload, target)` — deliver via specified mechanism
    - _Requirements: 6.1, 6.3, 6.5, 6.6_
  - [x] 14.2 Implement `option_b/output/flat_file_adapter.py`
    - Concatenate transformed fields in template sequence order, no delimiters, one record per line
    - Verify total record length = sum(target_lengths); exclude records with length mismatch (log error)
    - Apply padding rules (right-pad spaces for CHAR, left-pad zeroes for NUMERIC)
    - Deliver to local filesystem (POC) — write the ea_transaction.txt file
    - _Requirements: 6.2, 15.1, 15.2, 15.3, 15.4, 15.5_
  - [ ]* 14.3 Write property tests for flat file adapter
    - **Property 17: Flat File Record Length Invariant**
    - **Validates: Requirements 15.1, 15.2, 15.3**

- [x] 15. Checkpoint — Verify transformation and output pipeline
  - Ensure all tests pass for transformation executor, output adapter, and flat file formatting. Ask the user if questions arise.

- [x] 16. Implement Execution Audit Trail
  - [x] 16.1 Implement `option_b/audit/execution_audit.py`
    - `record_audit_trail(run_id, template_version, trigger_type, tables_processed, record_counts, outputs_produced)` — write audit trail as JSON (POC) with template version, table counts, severity counts, outputs
    - `query_record_trace(record_key, table_name, audit_dir)` — return per-record trace showing each rule applied, pass/fail, and actual values evaluated
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_
  - [ ]* 16.2 Write property tests for audit trail
    - **Property 18: Deterministic Reproducibility**
    - **Validates: Requirements 7.2, 7.5**
    - **Property 20: Per-Record Audit Trace**
    - **Validates: Requirements 7.4**

- [x] 17. Implement CLI Entry Point
  - [x] 17.1 Implement `option_b/main.py` with CLI argument parsing
    - Support three run modes:
      - `python -m option_b.main --validate --transform --output` — full pipeline (validate + transform + output)
      - `python -m option_b.main --validate` — validation only (no transform/output)
      - `python -m option_b.main --revalidate --record-key <KEY> --table <TABLE>` — targeted revalidation
    - Initialize SparkSession (local[*] for POC), load template, verify staging tables present, execute requested pipeline stages, write audit trail
    - Exit code 0 on success, 1 on fatal error
    - _Requirements: 9.1, 9.2, 9.3, 9.5, 16.1, 16.5_

- [x] 18. Checkpoint — Verify CLI runs end-to-end
  - Ensure all tests pass and the CLI can be invoked in all three modes against sample staging data. Ask the user if questions arise.

- [ ] 19. End-to-end integration testing against all four tables
  - [x] 19.1 Write end-to-end test: full pipeline with sample data
    - Run the engine against ALL FOUR staging tables (CNT, CVG, ROL, ADD) using the v1 template
    - Verify CNT results: 100 CLEAN, 50 WARNING, 50 SEVERE (matching sample_cnt.csv structure)
    - Verify cross-reference results per child table: exactly 6 rows PASS cross-reference (matching real CNT records) and 144 rows FAIL cross-reference (non-matching policy numbers)
    - Verify the 6-pass/144-fail split is consistent across CVG, ROL, and ADD tables
    - Verify SEVERE records excluded from transformation output
    - Verify ea_transaction.txt produced with correct record count and line lengths
    - _Requirements: 2.3, 3.3, 4.5, 7.2, 11.1, 14.2, 15.3, 17.1_
  - [x] 19.2 Write end-to-end test: validate-only mode
    - Run with `--validate` only, confirm no transformation output produced, confirm error records written
    - _Requirements: 9.2, 16.5_
  - [x] 19.3 Write end-to-end test: targeted revalidation
    - Seed a known cross-reference failure, correct the staging data, run revalidation, verify only affected records re-checked and error store updated
    - _Requirements: 5.4, 5.5, 5.6, 13.2, 13.3_
  - [x] 19.4 Write end-to-end test: deterministic reproducibility
    - Run the engine twice with identical inputs, verify byte-identical output file and logically identical error records
    - _Requirements: 7.2, 7.5, 19.1, 19.2, 19.3, 19.4, 19.5_

- [x] 20. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 21. Documentation: Known Gaps — Deferred to Phase 2
  - [~] 21.1 Create `option_b/PHASE2_DEFERRED.md`
    - Document the 15 deferred transformation mapping rows from POC_Transformation_Mapping_scoped.csv:
      - JIRA 107: [describe affected mappings]
      - JIRA 416: [describe affected mappings]
      - JIRA 403: [describe affected mappings]
      - Translation table lookups: mappings requiring external lookup tables not yet available
      - Nancy's co-owner sample-dataset: mappings requiring additional sample data for co-owner scenarios
    - For each gap: state the mapping IDs, source fields, reason deferred, and what is needed to unblock
    - _Requirements: 8.1, 8.2 (BA can add these later as template edits once unblocked)_

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The 6-pass/144-fail cross-reference split per child table is the critical acceptance metric for end-to-end correctness
- The four `.kiro/hooks/` are already updated — no hook tasks needed
- All PySpark code uses DataFrame operations only (no Python row iteration) per Requirement 4.3
- The implementation language is Python (PySpark) as specified in the design document

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "1.4", "1.5", "2.1", "2.2"] },
    { "id": 1, "tasks": ["4.1", "4.2", "5.1", "5.2"] },
    { "id": 2, "tasks": ["4.3", "4.4", "5.3", "6.1", "6.2", "6.3", "6.4", "6.5"] },
    { "id": 3, "tasks": ["6.6", "6.7", "6.8", "6.9", "7.1"] },
    { "id": 4, "tasks": ["7.2", "8.1"] },
    { "id": 5, "tasks": ["8.2", "10.1", "11.1"] },
    { "id": 6, "tasks": ["10.2", "11.2", "12.1"] },
    { "id": 7, "tasks": ["12.2", "13.1"] },
    { "id": 8, "tasks": ["13.2", "14.1"] },
    { "id": 9, "tasks": ["14.2"] },
    { "id": 10, "tasks": ["14.3", "16.1"] },
    { "id": 11, "tasks": ["16.2", "17.1"] },
    { "id": 12, "tasks": ["19.1", "19.2", "19.3", "19.4"] },
    { "id": 13, "tasks": ["21.1"] }
  ]
}
```


---

## Phase 3: Excel-Based Source Migration (Requirements 21–24)

These tasks implement the migration from hardcoded/CSV-based validation and transformation sources to the authoritative Excel workbooks. Each task is independently implementable and verifiable.

> **Note:** Task 11 from the original plan (Migrate validation engine to consume generated config) has been removed — option_b/'s engine already reads from templates/v1/validation_rules.csv exclusively with no hardcoded dicts. Only the template generation step (Task 10) is needed.

- [x] 10. Build the master-workbook validation rule adapter
  - [x] 10.1 Implement scripts/generate_config_from_master.py
    - Read `rules/Validation_Rules_Master.xlsx` (5 tabs: Contract, Address, Roles, Coverage table tabs + Cross_References) using openpyxl
    - Locate columns by header text match. Read the explicit `Rule Type` and `Severity` columns verbatim — NO prose parsing / rule-type inference
    - Map tab names to table codes (Contract→CNT, Address→ADD, Roles→ROL, Coverage→CVG); one output row per (field, rule)
    - Derive length/precision params from the dedicated `Length`/`Precision` columns; `allowed_values` from `Allowable Codes`
    - Normalize the Cross_References tab into `cross_references.csv` (table/compare-table names → codes, split join fields, active→Y/N)
    - Output: `templates/v1/validation_rules.csv`, `templates/v1/cross_references.csv`, `templates/v1/table_dependencies.csv`, and `templates/v1/_reconciliation_report.txt`
    - Any rule_type not registered in the engine → still written to CSV and flagged in the reconciliation report (carried, not lost)
    - _Requirements: 21.1, 21.2, 21.3, 21.4, 21.5_
  - [x] 10.2 Verify generated CSVs
    - Confirm `template_loader.load_template("templates/v1")` loads cleanly (schema + type validation)
    - Review `_reconciliation_report.txt`: per-table counts and no unexpected unregistered/unevaluated types
    - Result: 261 field rules + 164 cross-reference rules; all types registered
    - _Requirements: 21.5, 20.10_

- [ ] 11. Build Sample_*_Data.xlsx reader
  - [ ] 11.1 Implement scripts/export_sample_data.py
    - Read each Sample_*_Data.xlsx from staging_data/ using pandas read_excel(dtype=str)
    - Write to staging_data/<table>.csv (cnt.csv, cvg.csv, rol.csv, add.csv) preserving all values as text
    - No value modification, no date reformatting, no numeric reinterpretation
    - Handle CVG_SEQUENCE_NUMBER and CVG_PERSON_SEQ stored as int → convert to str without loss
    - _Requirements: 22.1, 22.2, 22.3, 22.4_
  - [ ] 11.2 Verify exported CSVs against Excel source
    - Confirm row count matches (Contract=120, Coverage=250, Roles=360, Address=360)
    - Confirm column count matches Excel header count per file
    - Confirm all column names from Excel header appear in CSV header — no additions, no renames
    - Spot-check 5 cells per file for value preservation (especially date fields, leading-zero codes)
    - _Requirements: 22.2, 22.3_
  - [ ] 11.3 Delete scripts/generate_sample_data.py if it still exists
    - Confirm file is removed (it was deleted earlier this session, but verify)
    - _Requirements: 22.1_

- [ ] 12. Build EA_Transaction_Mapping.xlsx reader
  - [ ] 12.1 Implement scripts/generate_transformation_mappings.py
    - Read rules/EA_Transaction_Mapping.xlsx, sheet "Trx Mapping" only (skip Sheet1 entirely)
    - Parse target_field from Col A: strip leading COBOL level number + whitespace
    - Parse source_field from Col I ("Policy Data Loader Mapping") as-is
    - Infer source_table from Col I prefix (CNT_/CVG_/ROL_/ADD_ → table name; blank/"System generated" → empty)
    - Parse PIC clause from Col C using EXACT rules: PIC X(n)→CHAR/n, PIC 9(n)→NUMERIC/n, PIC 99→NUMERIC/2, PIC S9(n) COMP→BINARY/n, PIC S9(n)V9(m) COMP-3→PACKED_DECIMAL/n+m
    - Determine transformation_type using bounded inference (in order): GROUP_OR_PARENT, SYSTEM_GENERATED, INITIALIZE_SPACES, DIRECT_SOURCE/DATE_SPLIT, CONDITIONAL_OR_DERIVED
    - Derive padding_rule from data_type only (CHAR→right_space, else→left_zero)
    - Leave default_value and truncation_rule blank unless Col G/K/L has explicit value
    - Generate mapping_id sequentially (MAP_001, MAP_002, ...)
    - Output: templates/v1/transformation_mappings.csv
    - Any row where parsing fails → output to templates/v1/transformation_mappings_needs_review.csv with row number, raw Col A, raw Col C, raw Col I, and the specific failure reason
    - _Requirements: 23.1–23.10_
  - [ ] 12.2 Verify generated transformation_mappings.csv
    - Confirm total row count matches "Trx Mapping" sheet data rows (minus group/parent rows if excluded, or including them with GROUP_OR_PARENT type)
    - Run scripts/verify_field_names.py to check all source_field values against DB_Section Column A
    - Review transformation_mappings_needs_review.csv — document count of unparseable rows
    - Confirm no mapping_id duplicates
    - _Requirements: 23.10, 20.10_
  - [ ] 12.3 Verify transformation engine accepts new mappings
    - Run pipeline with --run-transformation using the new generated transformation_mappings.csv
    - Confirm no new ERROR entries in transformation_audit_log.csv beyond expected CONDITIONAL_OR_DERIVED skips
    - Confirm ea_transaction.txt is produced with expected record count
    - _Requirements: 23.6_

- [ ] 13. Add dual CSV output to transformation step
  - [ ] 13.1 Update flat_file_builder.py or main.py transformation section
    - After building the positional flat file from the transformed DataFrame, write a CSV version of the same data
    - CSV uses the same computed field values (no recomputation) — just writes the transformed_df with proper column headers
    - Column headers = actual target field names from the mappings (e.g., "COMPANY-CODE", "MASTER-ID") — not positional offsets
    - Output file: output/ea_transaction.csv (alongside existing ea_transaction.txt)
    - Note: transformed_dataframe.csv already exists and may serve this purpose — verify whether it already satisfies the requirement or needs adjustment
    - _Requirements: 24.1, 24.2, 24.3, 24.4, 24.5_
  - [ ] 13.2 Verify dual output
    - Confirm ea_transaction.txt and ea_transaction.csv are produced in the same run
    - Confirm CSV row count = flat file line count
    - Confirm CSV column count = number of non-GROUP_OR_PARENT mappings
    - Confirm a spot-check of 3 fields × 3 rows shows identical values between CSV and corresponding flat-file positions
    - _Requirements: 24.1, 24.3_

- [ ] 14. Verification tooling
  - [x] 14.1 Reconciliation report replaces the standalone field-name verifier
    - `scripts/generate_config_from_master.py` emits `_reconciliation_report.txt` on every run: per-table rule counts, any field-level rule_type not in the engine registry, and any cross-reference type the engine cannot evaluate yet
    - The obsolete `scripts/verify_field_names.py` (which read the deleted DB_Section CSVs) has been removed
    - _Requirements: 20.10, 21.5_
  - [ ] 14.2 (Transformation phase) Verify EA mapping field names
    - When the transformation phase resumes, add a check that every `source_field` in `transformation_mappings.csv` traces to a `Field Name` in the master workbook (with known open questions as exceptions)
    - _Requirements: 20.10, 23.10_
