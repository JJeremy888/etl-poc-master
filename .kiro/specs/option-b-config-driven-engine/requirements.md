# Requirements Document

## Introduction

This document specifies the requirements for Option B: a config-driven ETL engine that replaces the current code-generation approach (Option A) with a single, fixed interpreter engine. Rules and mappings are stored as versioned structured configuration ("templates"). The engine reads the active template at runtime and interprets rules directly against records in a staging database — no code is generated at any point.

The engine is implemented in PySpark for set-based parallel processing. For the POC, PySpark runs locally in standalone mode (via `pip install pyspark`). The intended production target is AWS Glue, which uses Spark internally — but neither Glue nor a distributed cluster is required to prove the logic works in the POC.

This spec is a complete architectural replacement of the current pipeline. It does NOT modify or extend the existing Option A codebase — it defines a parallel, independent system.

## Glossary

- **Config_Engine**: The single, fixed PySpark-based engine that interprets validation and mapping rules at runtime without generating code.
- **Template**: A versioned collection of structured configuration files (rules and mappings) that define all validation logic, transformation logic, and output formatting for a specific client or product. The template's structure is fixed (schema enforced by the engine); its content is editable by BAs.
- **Template_Version**: A specific immutable snapshot of a Template, identified by a version identifier, stored with full history so that any prior version can be retrieved and compared.
- **Staging_Database**: The set of already-existing staging tables (CNT, CVG, ROL, ADD, and future tables like PRM) where incoming policy data lands after passing a structural/file-level scan. The engine operates on records in this database, not raw files.
- **Structural_Scan**: The pre-existing process that loads raw incoming files into the Staging_Database after verifying file-level structure (correct delimiters, expected column count, encoding). This is upstream of the Config_Engine and out of scope for this spec.
- **Validation_Rule**: A single declarative rule entry in the Template that specifies a check to apply to one or more fields. Types include: presence/format, range, cross-reference (lookup/join), and conditional (if-then).
- **Presence_Format_Rule**: A Validation_Rule that checks whether a field is populated and conforms to a specified format (e.g., not blank, exact length, date format, numeric, allowed values).
- **Range_Rule**: A Validation_Rule that checks whether a field value falls within specified bounds (e.g., date comparisons, numeric min/max).
- **Cross_Reference_Rule**: A Validation_Rule that verifies a field value exists in or matches a value from another staging table, implemented as a join or lookup against the Staging_Database.
- **Conditional_Rule**: A Validation_Rule with an IF-THEN structure: if a precondition on one or more fields is true, then a dependent check must also be satisfied.
- **Error_Record**: A record that failed one or more Validation_Rules, captured with full diagnostic detail (table, field, rule identifier, failing value, and referenced value where applicable).
- **Error_Dashboard**: A BA-facing view of Error_Records with sufficient detail to identify, understand, and correct data issues without developer involvement.
- **Targeted_Revalidation**: The process of re-checking only a corrected record plus any other records that depended on the same corrected reference value, rather than re-running the entire batch.
- **Output_Adapter**: A pluggable component responsible for formatting validated/transformed records into a specific output format (e.g., positional flat file) and delivering them via a specific mechanism (e.g., S3, REST API).
- **Rule_Type**: A category of validation or transformation logic (e.g., not_blank, exact_length, cross_reference_exists). The set of supported Rule_Types is defined in the engine code. Adding a genuinely new Rule_Type requires a developer.
- **Transformation_Type**: A category of mapping/transformation operation (e.g., direct_copy, date_split, constant_fill). The set of supported Transformation_Types is defined in the engine code.
- **Delivery_Mechanism**: A method for transmitting output to a target system (e.g., S3 upload, REST API POST, SFTP). The set of supported Delivery_Mechanisms is defined in the engine code.
- **Run_Trigger**: The mechanism that initiates an engine execution (e.g., event-based trigger when all staging tables are loaded, a cron schedule, or a manual invocation). This is an open design question.
- **PySpark**: The Python API for Apache Spark, used for set-based parallel processing of records. For the POC, runs in local standalone mode.
- **AWS_Glue**: The intended production runtime environment that uses Spark internally and provides managed infrastructure for running PySpark jobs at scale.

## Requirements

### Requirement 1: Versioned Configuration Storage

**User Story:** As a business analyst, I want validation rules and transformation mappings stored as versioned configuration with a fixed schema, so that I can modify rule content without developer involvement and can trace what rules were active for any past execution.

#### Acceptance Criteria

1. THE Config_Engine SHALL load all Validation_Rules and Transformation_Types from structured Template files at runtime rather than from generated code.
2. THE Template SHALL enforce a fixed schema (column names, data types, required fields) that the Config_Engine validates on load. Content within that schema SHALL be editable without code changes.
3. WHEN a Template is modified, THE system SHALL store the previous version as an immutable Template_Version with a unique version identifier and a timestamp.
4. WHEN the Config_Engine executes, THE system SHALL record which Template_Version was used, so that any execution can be audited against the exact rules that were active.
5. THE system SHALL provide a mechanism to retrieve and compare any two Template_Versions to identify what rules changed between them.
6. IF a Template fails schema validation on load, THEN THE Config_Engine SHALL reject the Template, log a descriptive error identifying the schema violation, and refuse to proceed with execution.

### Requirement 2: Staging Database Input

**User Story:** As a data engineer, I want the engine to validate and map records directly from the staging database, so that it operates on structurally verified data that has already passed file-level ingestion checks.

#### Acceptance Criteria

1. THE Config_Engine SHALL read input records from the Staging_Database tables (CNT, CVG, ROL, ADD, and future tables) rather than from raw CSV files.
2. WHEN records are present in the Staging_Database, THE Config_Engine SHALL treat the Staging_Database as its sole input source for validation and transformation.
3. THE Config_Engine SHALL support reading from multiple staging tables within a single execution run to enable Cross_Reference_Rules between tables.
4. THE Config_Engine SHALL NOT perform any Structural_Scan responsibilities (file-level parsing, delimiter validation, column-count verification). The Config_Engine assumes records in the Staging_Database have already passed structural checks.
5. WHEN a staging table referenced by the Template does not exist or is empty, THE Config_Engine SHALL log a clear diagnostic message identifying the missing table and skip rules that depend on it rather than failing the entire run.

### Requirement 3: Validation Rule Types

**User Story:** As a business analyst, I want a comprehensive set of declarative validation rule types available in the Template, so that I can express presence checks, format checks, range checks, cross-reference lookups, and conditional logic without writing code.

#### Acceptance Criteria

1. THE Config_Engine SHALL support Presence_Format_Rules including: not_blank, exact_length, max_length, allowed_values, valid_date (YYYYMMDD), and numeric checks.
2. THE Config_Engine SHALL support Range_Rules including: numeric minimum/maximum bounds and date comparisons (greater than, less than or equal to) between two fields in the same record.
3. THE Config_Engine SHALL support Cross_Reference_Rules that verify a field value exists in a specified column of another staging table, implemented as a join or lookup against the Staging_Database.
4. THE Config_Engine SHALL support Conditional_Rules with IF-THEN structure: when a precondition expression evaluates to true on one or more fields, a dependent validation check SHALL be applied.
5. WHEN a Validation_Rule in the Template references a Rule_Type not recognized by the Config_Engine, THE Config_Engine SHALL log a warning identifying the unrecognized Rule_Type and the affected field, skip that rule, and continue processing.
6. THE Config_Engine SHALL evaluate all applicable Validation_Rules for a record before classifying its overall status, so that a single record can accumulate multiple independent validation failures.

### Requirement 4: PySpark Set-Based Processing

**User Story:** As a data engineer, I want validation and mapping executed as PySpark DataFrame operations, so that processing scales horizontally and runs as set-based operations across records rather than one-at-a-time application code.

#### Acceptance Criteria

1. THE Config_Engine SHALL implement all Validation_Rules as PySpark DataFrame column expressions or DataFrame transformations operating across all records simultaneously.
2. THE Config_Engine SHALL implement all transformation/mapping operations as PySpark DataFrame column expressions or DataFrame transformations operating across all records simultaneously.
3. THE Config_Engine SHALL NOT iterate over individual rows in Python application code for validation or transformation logic. All row-level processing SHALL be expressed as Spark operations that Spark parallelizes automatically.
4. WHEN running in POC mode, THE Config_Engine SHALL execute PySpark in local standalone mode (single-machine Spark session via `pip install pyspark`) without requiring AWS Glue, a Hadoop cluster, or any cloud infrastructure.
5. THE Config_Engine SHALL produce identical logical results regardless of whether it runs in local standalone mode or on a distributed Spark cluster (e.g., AWS Glue), so that the same PySpark code is portable between environments.
6. WHEN processing Cross_Reference_Rules, THE Config_Engine SHALL implement them as Spark DataFrame joins between staging tables rather than row-level lookups.

### Requirement 5: Error Logging and Targeted Revalidation

**User Story:** As a business analyst, I want failed records logged with full diagnostic detail and the ability to re-validate only corrected records and their dependents, so that I can identify issues from a dashboard and trigger efficient re-checks without re-running the entire batch.

#### Acceptance Criteria

1. WHEN a record fails a Validation_Rule, THE Config_Engine SHALL create an Error_Record containing: staging table name, field name, rule identifier, the failing value, and (for Cross_Reference_Rules) the referenced table, referenced field, and expected reference value.
2. THE Config_Engine SHALL persist all Error_Records in a structure suitable for querying by the Error_Dashboard, including filtering by table, field, rule, severity, and batch run.
3. THE Error_Dashboard SHALL present Error_Records with sufficient detail for a BA to identify what is wrong, which record is affected, and what value caused the failure — without requiring developer assistance or access to logs.
4. WHEN a BA corrects a record in the Staging_Database and triggers Targeted_Revalidation, THE Config_Engine SHALL re-validate only the corrected record plus any other records whose validation outcome depended on the same corrected reference value (e.g., records that failed a Cross_Reference_Rule against the corrected value).
5. WHEN performing Targeted_Revalidation, THE Config_Engine SHALL NOT re-run validation on records that are independent of the correction. The scope of re-validation SHALL be derived from the dependency graph of Cross_Reference_Rules.
6. WHEN Targeted_Revalidation completes, THE Config_Engine SHALL update the Error_Record store — clearing resolved errors and adding any newly discovered errors — so that the Error_Dashboard reflects the current state.

### Requirement 6: Pluggable Output and Delivery

**User Story:** As a system integrator, I want output formatting and delivery implemented as pluggable adapters, so that the same validated data can be delivered in different formats to different target systems without modifying the core engine.

#### Acceptance Criteria

1. THE Config_Engine SHALL separate output formatting from the core validation and transformation logic by delegating output production to Output_Adapter components.
2. THE Config_Engine SHALL support a positional fixed-width flat file Output_Adapter as the primary format for the POC (producing the EA transaction file).
3. THE Config_Engine SHALL support multiple Output_Adapters active simultaneously for a single execution run, so that the same validated data can be delivered in multiple formats if the Template specifies them.
4. THE Config_Engine SHALL support multiple Delivery_Mechanisms per Output_Adapter (e.g., write to local filesystem, upload to S3, POST to a REST API), configurable in the Template without code changes.
5. WHEN a new output format or Delivery_Mechanism is required that does not match any existing Output_Adapter or Delivery_Mechanism, THE system SHALL require a developer to implement and register the new adapter or mechanism — this is the only scenario requiring developer involvement for output changes.
6. THE Output_Adapter interface SHALL be defined such that adding a new adapter requires implementing a defined contract (input: transformed DataFrame + formatting metadata; output: formatted payload delivered to target) with no modifications to existing adapters or the core engine.

### Requirement 7: Deterministic and Auditable Execution

**User Story:** As a compliance officer, I want all rule evaluation to be deterministic and fully auditable with no AI or machine-learning involvement at runtime, so that every validation decision can be traced to a specific rule in the Template and reproduced exactly.

#### Acceptance Criteria

1. THE Config_Engine SHALL NOT invoke any AI model, LLM, or machine-learning inference at runtime for rule evaluation, data transformation, or decision-making.
2. GIVEN the same input records and the same Template_Version, THE Config_Engine SHALL produce identical validation results, error classifications, and transformed output on every execution.
3. THE Config_Engine SHALL log an execution audit trail that records: the Template_Version used, the set of staging tables read, the count of records processed per table, the count of records passing and failing, and the output artifacts produced.
4. WHEN an auditor or BA queries a specific record's validation outcome, THE system SHALL provide a trace showing each Validation_Rule that was applied to that record, whether it passed or failed, and the actual values evaluated.
5. THE Config_Engine SHALL NOT introduce any non-deterministic elements (random values, model predictions, probabilistic thresholds) into validation decisions or output data.

### Requirement 8: Minimal Developer Involvement

**User Story:** As a project manager, I want routine rule changes and standard client onboarding handled entirely through Template edits by BAs, so that developers are only needed for genuinely new capabilities.

#### Acceptance Criteria

1. WHEN a BA adds, modifies, or removes a Validation_Rule using existing Rule_Types, THE system SHALL require only a Template edit and no code changes.
2. WHEN a BA adds, modifies, or removes a transformation mapping using existing Transformation_Types, THE system SHALL require only a Template edit and no code changes.
3. WHEN a new client is onboarded with the same table structures and rule types as existing clients, THE system SHALL require only a new Template (or Template_Version) and no code changes.
4. WHEN a genuinely new Rule_Type is required (a validation pattern not supported by any existing Rule_Type), THE system SHALL require a developer to implement the new Rule_Type in the engine and register it, after which BAs can use it in Templates without further developer involvement.
5. WHEN a genuinely new Transformation_Type is required, THE system SHALL require a developer to implement and register it, after which BAs can reference it in Templates without further developer involvement.
6. WHEN a genuinely new Delivery_Mechanism is required, THE system SHALL require a developer to implement and register it, after which it can be configured in Templates without further developer involvement.
7. THE Config_Engine SHALL validate that all Rule_Types, Transformation_Types, and Delivery_Mechanisms referenced in a Template are registered in the engine, and SHALL reject a Template that references unregistered types with a clear error message.

### Requirement 9: Run Trigger Mechanism (Open Design Question)

**User Story:** As a pipeline operator, I want a clearly defined mechanism that initiates an engine run, so that processing begins at the right time and the team can evaluate trigger options during design.

#### Acceptance Criteria

1. THE system SHALL define an explicit Run_Trigger interface that the Config_Engine listens to or polls for execution signals.
2. THE system SHALL support at minimum one of the following Run_Trigger options for the POC: manual CLI invocation, a schedule-based trigger, or an event-based trigger fired when all required staging tables for a batch are loaded.
3. WHEN the Run_Trigger fires, THE Config_Engine SHALL verify that all staging tables referenced by the active Template are present and contain records before beginning validation. IF any required table is missing or empty, THE Config_Engine SHALL log a diagnostic and defer execution.
4. THE design document SHALL enumerate the candidate Run_Trigger mechanisms (event-driven, schedule-based, manual, or hybrid), evaluate trade-offs, and recommend one for the POC — without hard-coding the final decision in requirements.
5. THE Run_Trigger mechanism SHALL be replaceable without modifying the Config_Engine's core validation or transformation logic.

### Requirement 10: Template Schema and Structure

**User Story:** As a BA, I want a well-defined Template schema that separates rule definitions from engine code, so that I can understand and edit rules using familiar spreadsheet or structured-file tools.

#### Acceptance Criteria

1. THE Template SHALL contain separate sections for: validation rules, transformation mappings, output format definitions, and delivery configuration.
2. WHEN defining a Validation_Rule in the Template, THE BA SHALL specify: target table, target field, Rule_Type, severity (SEVERE or WARNING), parameters (e.g., allowed values list, comparison field, length), and an optional human-readable description.
3. WHEN defining a transformation mapping in the Template, THE BA SHALL specify: source table, source field, target field, Transformation_Type, target length, target data type, padding rule, and default/constant value where applicable.
4. THE Template schema SHALL be documented with field-level descriptions, valid value ranges, and examples for each section so that a BA can author rules without developer guidance.
5. THE Config_Engine SHALL validate the loaded Template against the published schema before execution and SHALL reject Templates with missing required fields, invalid Rule_Type references, or malformed parameters.

### Requirement 11: Cross-Reference Validation via Staging Joins

**User Story:** As a data engineer, I want cross-reference checks implemented as joins against other staging tables, so that referential integrity between tables (e.g., child records referencing parent records) is validated efficiently at scale.

#### Acceptance Criteria

1. WHEN a Cross_Reference_Rule specifies that a field value must exist in another staging table, THE Config_Engine SHALL implement the check as a PySpark DataFrame join (left anti-join to find non-matching records) rather than a row-level lookup.
2. THE Config_Engine SHALL support cross-reference checks across all staging table combinations present in the Staging_Database (e.g., CVG referencing CNT, ROL referencing CNT, ADD referencing CNT, CVG referencing ROL).
3. WHEN a cross-reference check fails for a record, THE Error_Record SHALL include the referenced table name, the referenced field name, and the value that was not found, so that the BA can identify the missing reference.
4. THE Config_Engine SHALL support multi-field join keys for Cross_Reference_Rules (e.g., compound keys like COMPANY_CODE + POLICY_NUMBER) as specified in the Template.
5. WHEN the referenced staging table is empty or unavailable, THE Config_Engine SHALL treat all cross-reference checks against that table as skipped (not failed), log a warning, and continue processing other rules.

### Requirement 12: Conditional (If-Then) Validation Rules

**User Story:** As a BA, I want to define conditional validation rules in the Template where a check applies only when a precondition is met, so that business rules like "if PRODUCT_TYPE = K then JOINT_LIFE_INDICATOR must be F or J" can be expressed declaratively.

#### Acceptance Criteria

1. WHEN a Conditional_Rule is defined in the Template, THE Config_Engine SHALL evaluate the precondition expression first. Only when the precondition evaluates to true SHALL the dependent validation check be applied.
2. THE Template SHALL support precondition expressions that reference one or more fields in the same record, using operators: equals, not_equals, in_list, not_in_list, is_blank, is_not_blank.
3. THE Template SHALL support dependent checks that are any supported Rule_Type (presence, format, range, allowed_values, cross-reference).
4. WHEN a Conditional_Rule's precondition evaluates to false, THE Config_Engine SHALL skip the dependent check for that record and SHALL NOT generate an Error_Record for the skipped check.
5. WHEN a Conditional_Rule's precondition evaluates to true and the dependent check fails, THE Config_Engine SHALL generate an Error_Record that includes both the precondition expression and the dependent check failure detail.

### Requirement 13: Record Dependency Graph for Targeted Revalidation

**User Story:** As a data engineer, I want the engine to track which records depend on which reference values, so that targeted revalidation can efficiently determine the minimal set of records to re-check after a correction.

#### Acceptance Criteria

1. WHEN evaluating Cross_Reference_Rules, THE Config_Engine SHALL record a dependency link between each validated record and the specific reference value(s) it was checked against.
2. WHEN a BA corrects a reference value (e.g., adds a missing parent record), THE Targeted_Revalidation process SHALL use the dependency graph to identify all records that previously failed due to that missing reference.
3. THE Targeted_Revalidation process SHALL re-validate the corrected record itself plus all records identified by the dependency graph, and SHALL NOT re-validate records with no dependency on the corrected value.
4. THE dependency graph SHALL be persisted between executions so that Targeted_Revalidation can operate without re-running the full initial validation pass.
5. WHEN the dependency graph grows stale (e.g., Template rules have changed since it was built), THE Config_Engine SHALL detect the version mismatch and require a full validation run to rebuild the dependency graph before allowing Targeted_Revalidation.

### Requirement 14: Multi-Table Processing Order

**User Story:** As a data engineer, I want the engine to process parent tables before child tables, so that cross-reference checks have the parent data available when validating child records.

#### Acceptance Criteria

1. THE Config_Engine SHALL determine table processing order from the Template's cross-reference dependency declarations, processing referenced (parent) tables before referencing (child) tables.
2. WHEN the Template declares that CVG, ROL, and ADD reference CNT, THE Config_Engine SHALL validate CNT records before validating CVG, ROL, or ADD records.
3. WHEN two tables have no cross-reference dependency between them, THE Config_Engine MAY process them in parallel (Spark handles this internally).
4. IF the Template contains a circular cross-reference dependency, THEN THE Config_Engine SHALL detect the cycle, log a clear error identifying the tables involved, and reject the Template.

### Requirement 15: Output Adapter — Positional Flat File

**User Story:** As a data engineer, I want a positional flat-file Output_Adapter that produces the EA transaction file in the same fixed-width format as the current system, so that downstream EA systems receive data in their expected format.

#### Acceptance Criteria

1. THE positional flat-file Output_Adapter SHALL concatenate transformed field values in the sequence order specified by the Template's transformation mappings.
2. THE positional flat-file Output_Adapter SHALL produce one output line per valid record with no delimiters between fields.
3. WHEN all fields are concatenated for a record, THE Output_Adapter SHALL verify that the total record length equals the sum of all target lengths defined in the Template's transformation mappings.
4. IF a record's total length does not match the expected sum, THEN THE Output_Adapter SHALL exclude that record, log an error with the record identifier and length mismatch details, and continue processing remaining records.
5. THE Output_Adapter SHALL apply padding rules (right-pad with spaces for CHAR, left-pad with zeroes for NUMERIC) as specified per field in the Template.

### Requirement 16: POC Scope and Local Execution

**User Story:** As a developer, I want the POC to run entirely on a local development machine with PySpark in standalone mode, so that the architecture can be proven without cloud infrastructure costs or dependencies.

#### Acceptance Criteria

1. THE POC SHALL execute using PySpark in local standalone mode, installable via `pip install pyspark`, with no dependency on AWS Glue, Hadoop, or any external cluster.
2. THE POC SHALL use local files or a local database (e.g., SQLite, local PostgreSQL, or Spark-readable local storage) to simulate the Staging_Database, so that the same read patterns work locally and in production.
3. THE POC SHALL demonstrate all nine requirement areas (versioned config, staging input, validation types, PySpark processing, error logging with targeted revalidation, pluggable output, deterministic execution, minimal developer involvement, and run trigger) using local resources only.
4. THE Config_Engine's PySpark code SHALL be written such that switching from local standalone mode to AWS Glue requires only changing the Spark session initialization and data source connection parameters — no changes to validation, transformation, or output logic.
5. WHEN running in POC mode, THE system SHALL accept a CLI invocation as the Run_Trigger (the simplest viable trigger for local demonstration).

### Requirement 17: Error Severity Classification

**User Story:** As a BA, I want records classified by severity (SEVERE, WARNING, CLEAN) based on validation outcomes, so that I can prioritize corrections and understand which records are blocked versus which have minor issues.

#### Acceptance Criteria

1. THE Config_Engine SHALL classify each record after all Validation_Rules have been evaluated, using the same severity hierarchy as the current system: SEVERE if any SEVERE rule fails, WARNING if any WARNING rule fails but no SEVERE rule fails, CLEAN if all rules pass.
2. WHEN a record is classified as SEVERE, THE Config_Engine SHALL exclude it from transformation and output processing.
3. WHEN a record is classified as WARNING, THE Config_Engine SHALL include it in transformation and output processing (same behavior as the current system).
4. THE Template SHALL specify the severity (SEVERE or WARNING) for each Validation_Rule. THE Config_Engine SHALL use the Template-specified severity and SHALL NOT infer or override severity levels.
5. THE Error_Dashboard SHALL allow filtering Error_Records by severity level, so that BAs can focus on SEVERE errors first.

### Requirement 18: Transformation via Template Configuration

**User Story:** As a BA, I want transformation and mapping rules defined in the Template using the same declarative approach as validation, so that I can control how validated records are mapped to output format without code changes.

#### Acceptance Criteria

1. THE Config_Engine SHALL support transformation operations defined in the Template including: direct source copy, date splitting, constant fill, space initialization, numeric/date initialization, and conditional/derived computations.
2. THE Config_Engine SHALL execute transformation mappings in the sequence order specified by the Template.
3. WHEN a new transformation mapping is added to the Template using an existing Transformation_Type, THE system SHALL require no code changes to process it.
4. THE Config_Engine SHALL apply formatting (padding, truncation) to each transformed field value as specified in the Template, ensuring exact target length compliance.
5. WHEN a transformation fails for a specific field on a specific record, THE Config_Engine SHALL log the failure, apply a default value for that field's data type, and continue processing remaining fields for that record.

### Requirement 19: No Code Generation

**User Story:** As an architect, I want to confirm that no part of the system generates Python, PySpark, SQL, or any other executable code from rules at any point, so that the system remains a pure interpreter of declarative configuration.

#### Acceptance Criteria

1. THE Config_Engine SHALL NOT generate Python source files, PySpark scripts, SQL statements, or any other form of executable code from Template content at any point during execution.
2. THE Config_Engine SHALL interpret Template rules at runtime by translating them into PySpark DataFrame operations directly within the engine's fixed code — the engine code is the interpreter, not a code generator.
3. WHEN a BA modifies the Template, THE system SHALL NOT produce any new code artifacts. The only artifacts produced SHALL be execution outputs (validated records, error logs, transformed data, output files).
4. THE system SHALL NOT maintain a "generated code" directory, build step, or compilation phase for rule-derived code.
5. IF a requirement arises that cannot be expressed within existing Rule_Types or Transformation_Types, THE resolution SHALL be a developer adding a new type to the engine's interpreter — NOT generating custom code from the Template.


### Requirement 20: Field Name Authority and Traceability

**User Story:** As a project lead, I want all field names used anywhere in this project to trace directly to the authoritative master rule workbook, so that no fabricated, abbreviated, or guessed field names enter the system and cause silent mismatches between the staging schema, validation rules, and transformation mappings.

#### Acceptance Criteria

1. ALL field names used in the staging schema, validation_rules.csv, cross_references.csv, transformation_mappings.csv, and generated sample data SHALL come directly from the `Field Name` column of the table tabs (Contract, Address, Roles, Coverage) in `rules/Validation_Rules_Master.xlsx`.
2. NO field name SHALL be invented, abbreviated, renamed, or guessed at — even temporarily or as a placeholder — at any point in the project.
3. IF a transformation mapping or validation rule needs a field that does not appear in the master workbook, THAT field SHALL be flagged as an open question for BA confirmation in the BA Validation Report's Questions section. The system SHALL NOT assume or fabricate a name to fill the gap.
4. WHERE a legacy copybook name is recorded (in the `Description / Notes` column), THE project SHALL use the `Field Name` column as the canonical name. The copybook name SHALL only be referenced in documentation for traceability to the legacy system.
5. THE scripts/export_sample_data.py generator SHALL use only field names that exist in the master workbook. Any staging column that is not in the workbook SHALL be explicitly documented with the reason and flagged for BA confirmation.
6. WHEN a mismatch is discovered between a field name used in the project and the master workbook's `Field Name` column, THE correction SHALL rename the project's usage to match the workbook — never the other way around.
7. FOR THE CURRENT POC PHASE, the `Field Name` column of the master workbook's table tabs IS the staging schema — no separate staging database file exists or is needed. Kiro SHALL treat the workbook as the complete and sufficient reference for all field names.
8. WHEN this project moves beyond POC into full development against a provisioned, live staging database, THIS requirement SHALL be revisited and explicitly updated to point to that live schema as the new source of truth. Until that update happens, the master workbook's `Field Name` column remains authoritative.
9. BEFORE creating or modifying any file that references field names (validation_rules.csv, cross_references.csv, transformation_mappings.csv, or any staging schema), the relevant tab(s) of the master workbook SHALL be read in that same working session, and every field name used SHALL be verified against them before the file is written — not after.
10. The input adapter's `_reconciliation_report.txt` SHALL report the rules generated per table and flag any rule_type not recognized by the engine, providing the traceability check before the generated CSVs are considered complete.
11. WHEN a field's source value is missing or blank AND no default or fallback rule is explicitly stated in the master workbook or transformation_mappings.csv, THEN the system SHALL NOT apply an invented default value, and SHALL instead flag the field as an open question for BA confirmation.

### Requirement 21: Excel-Based Validation Source of Truth

**User Story:** As a data engineer, I want validation rules derived exclusively from the single master workbook `rules/Validation_Rules_Master.xlsx`, so that all validation logic traces directly to authoritative field definitions and no hardcoded dicts or drifting intermediaries can get out of sync.

#### Acceptance Criteria

1. THE `rules/Validation_Rules_Master.xlsx` workbook SHALL be the sole authoritative source for all validation rule definitions. No hardcoded Python dict and no manually-authored validation_rules.csv/cross_references.csv SHALL serve as a runtime source of truth; the CSVs SHALL always be regenerated from the workbook.
2. THE input adapter SHALL read the workbook's explicit columns (`Field Name`, `Rule Type`, `Severity`, `Allowable Codes`, `Length`, `Precision`, and the Cross_References columns) verbatim, locating columns by header text. Rule type and severity SHALL NOT be inferred from prose.
3. THE adapter SHALL read the four table tabs (Contract, Address, Roles, Coverage) for field-level rules and the `Cross_References` tab for cross-reference rules, treating one row per (field, rule).
4. ALL runtime rule interpretation SHALL be driven by the generated `validation_rules.csv` and `cross_references.csv` — the engine SHALL contain no hardcoded field names or rule logic.
5. WHEN a rule_type in the workbook is not registered in the engine, THE adapter SHALL still write the row to the CSV and flag it in `_reconciliation_report.txt` as unrecognized (carried, will be skipped at runtime) rather than guessing or silently dropping it.

### Requirement 22: Excel-Based Sample Data

**User Story:** As a project lead, I want the pipeline to consume business-provided sample data directly from the Sample_*_Data.xlsx workbooks, so that test data exactly matches what the BA team prepared and no synthetic generator can introduce fabricated values or field names.

#### Acceptance Criteria

1. THE 4 Sample_*_Data.xlsx files in staging_data/ (Contract, Coverage, Roles, Address) SHALL replace the former scripts/generate_sample_data.py entirely. No synthetic data generator SHALL exist in this project.
2. WHEN reading Sample_*_Data.xlsx files, THE reader SHALL use dtype=str (or equivalent text-mode reading) to prevent numeric reinterpretation of fields — specifically: CVG_SEQUENCE_NUMBER and CVG_PERSON_SEQ are stored as integers in the source and must not lose leading zeros if real data ever contains them.
3. THE reader SHALL write the Excel data to CSV format for pipeline consumption, preserving all cell values exactly as text with no reformatting, rounding, or date conversion applied.
4. THE pipeline SHALL NOT modify, append to, or reinterpret any value from the Sample_*_Data.xlsx source during the read/write process.

### Requirement 23: EA Transaction Mapping Source of Truth

**User Story:** As a data engineer, I want transformation_mappings.csv generated mechanically from rules/EA_Transaction_Mapping.xlsx using explicit, bounded parsing rules, so that every mapping entry traces directly to a business-provided row and no mapping is invented or inferred beyond what the source states.

#### Acceptance Criteria

1. THE file rules/EA_Transaction_Mapping.xlsx, sheet "Trx Mapping", SHALL be the sole authoritative source for generating templates/v1/transformation_mappings.csv. Sheet1 (scratch notes) SHALL be excluded from generation entirely.
2. THE target_field SHALL be parsed from Column A ("agent") by stripping the leading COBOL level number and whitespace (e.g., "15  COMPANY-CODE" → "COMPANY-CODE").
3. THE source_field SHALL be taken from Column I ("Policy Data Loader Mapping") as-is.
4. THE source_table SHALL be inferred ONLY from the prefix of the value in Column I (CNT_ → CNT, CVG_ → CVG, ROL_ → ROL, ADD_ → ADD). If Column I is blank or says "System generated", source_table is not applicable.
5. THE target_length and target_data_type SHALL be parsed from the PIC clause in Column C ("Field Format") using these EXACT rules only: PIC X(n) → CHAR length n; PIC 9(n) → NUMERIC length n; PIC 99 → NUMERIC length 2; PIC S9(n) COMP → BINARY length n; PIC S9(n)V9(m) COMP-3 → PACKED_DECIMAL length n+m. Any PIC clause not matching one of these exact patterns SHALL be flagged as "PIC clause not recognized — needs manual review" — not guessed at.
6. THE transformation_type SHALL be determined by these bounded inference rules ONLY, applied in this exact order (first match wins): (a) No PIC clause in Col C (group/parent row) → GROUP_OR_PARENT; (b) Col I = "System generated" → SYSTEM_GENERATED; (c) Col I blank AND Col G or K contains "Move spaces" → INITIALIZE_SPACES; (d) Col I has exactly one non-blank value AND no other rule above applies → DIRECT_SOURCE, UNLESS the target field name matches a YY/MM/DD date-component pattern shared with adjacent rows referencing the same source field → DATE_SPLIT; (e) Anything not matching (a)-(d) → CONDITIONAL_OR_DERIVED, flagged as "transformation type inferred with low confidence — needs manual review".
7. THE padding_rule SHALL be derived mechanically from data_type only: CHAR → right_space; NUMERIC/BINARY/PACKED_DECIMAL → left_zero. No other inference permitted.
8. THE default_value and truncation_rule SHALL be left blank UNLESS Column G, K, or L contains an explicit stated value or instruction. No inference.
9. THE mapping_id SHALL be generated sequentially (MAP_001, MAP_002, ...) in row order. THE sequence column SHALL use row number to preserve original order.
10. ANY row where required parsing fails (PIC clause unrecognized, target field name cannot be extracted, source field ambiguous) SHALL be output to a separate "needs review" list — not included in transformation_mappings.csv with a guessed value, and not silently dropped.

### Requirement 24: Dual Output Format

**User Story:** As a BA, I want both a positional flat file and a CSV equivalent produced from a single transformation pass, so that downstream systems receive the fixed-width format they require while I can review the same data in a human-readable columnar format without any recomputation.

#### Acceptance Criteria

1. THE transformation engine SHALL produce both output formats from a single transformation pass using existing logic — no duplicate processing or additional transformation load.
2. THE positional flat file (ea_transaction.txt) SHALL be retained for any downstream system requiring the fixed-width format.
3. A CSV equivalent SHALL be produced using the same computed field values, reformatted only at the final write step — not recomputed.
4. THE CSV output SHALL include readable column headers using actual target field names (e.g., "COMPANY-CODE"), not positional offsets.
5. THE CSV output is the BA-facing review deliverable; the flat file remains the system-of-record format for downstream consumers that need it.
