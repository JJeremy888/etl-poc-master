# Steering: ETL Engineering Standards
## Option B — Config-Driven PySpark Engine

---

## Purpose of This File

This file tells Kiro the engineering standards to follow when generating any code within the Option B engine (`option_b/`). These standards ensure the engine is simple, consistent, testable, and easy to extend.

Software engineers own this file. Changes to code structure, patterns, or testing standards are agreed here first.

---

## 1. Core Principle — Keep It Simple

This is a config-driven interpreter engine. Simplicity means:

- One fixed engine codebase that interprets all rules — no generated code, no per-table modules
- All business logic lives in template CSVs, not in Python
- The engine is table-agnostic — it processes any table that has template entries
- Prefer PySpark DataFrame operations over custom Python logic
- A new team member must be able to understand any module within 10 minutes
- Adding a new table = adding rows to CSV files, not writing code

---

## 2. Module Responsibilities

Each module has exactly one job. It does not reach into another module's concerns.

### `main.py` — CLI Entry Point
```python
# Responsibility: Parse CLI arguments, initialize SparkSession, wire components, run pipeline.
# Accepts: --validate, --transform, --output, --revalidate, --record-key, --table
# Does not contain: any validation logic, rule interpretation, or output formatting

def main():
    spark = SparkSession.builder.master("local[*]").appName("option_b").getOrCreate()
    template = template_loader.load_template(template_dir, spark)
    validated_dfs = validation_orchestrator.run_validation(spark, template, staging_reader)
    transformed_df = transformation_executor.transform(template, validated_dfs)
    adapter_registry.deliver(template, transformed_df)
```

### `config/template_loader.py` — Config Layer
```python
# Responsibility: Load, schema-validate, and return parsed Template data.
# Returns: dict with validation_rules, transformation_mappings, output_config, table_dependencies, version
# Must raise: ValueError on schema violation with descriptive message
# Must raise: FileNotFoundError if template directory/files missing
# Is the ONLY module that opens template CSV files.

def load_template(template_dir: str, spark: SparkSession) -> dict:
    """Load all template sections, validate schemas, return parsed template dict."""

def validate_schema(section_df, section_name: str, schema: dict) -> None:
    """Validate a template section DataFrame against its published schema."""
```

### `config/template_versioner.py` — Version Tracking
```python
# Responsibility: Track, compare, and retrieve template versions.
# Returns: version info, diffs between versions
# Must ensure: previous versions are stored immutably

def get_active_version(template_dir: str) -> str:
    """Return the currently active template version identifier."""

def compare_versions(v1: str, v2: str, template_dir: str) -> dict:
    """Compare two template versions and return a diff summary."""
```

### `input/staging_reader.py` — Input Layer
```python
# Responsibility: Read staging tables into Spark DataFrames.
# Returns: a Spark DataFrame for the requested table
# POC: reads from local Parquet/CSV files in staging_data/
# Production: reads from Glue Catalog / JDBC
# Must log: clear diagnostic if table missing or empty (does not crash)

def read_staging_table(spark: SparkSession, table_name: str, config: dict) -> DataFrame:
    """Read a staging table. Config determines source type (local vs JDBC)."""
```

### `engine/validation_orchestrator.py` — Core Orchestration
```python
# Responsibility: Orchestrate validation across all staging tables in dependency order.
# Determines processing order from table_dependencies.
# Calls rule_compiler, applies expressions, classifies severity, logs errors.
# Returns: dict of {table_name: validated_DataFrame_with_severity}

def run_validation(spark: SparkSession, template: dict, staging_reader) -> dict[str, DataFrame]:
    """Execute full validation pass across all tables."""

def determine_table_order(dependencies: list[dict]) -> list[str]:
    """Topological sort of table dependencies. Raises ValueError on cycles."""
```

### `engine/rule_compiler.py` — Rule Interpretation Core
```python
# Responsibility: Translate Template validation rules into PySpark Column expressions.
# No hardcoded field names. All behavior driven by template metadata.
# This module IS the interpreter — it reads rule definitions and produces Spark Columns.

def compile_rule(rule: dict) -> Column:
    """Translate a single validation rule dict into a PySpark Column expression."""

def compile_all_rules(rules: list[dict], table_name: str) -> list[tuple[str, Column]]:
    """Compile all rules for a given table into (column_name, expression) pairs."""
```

### `engine/transformation_executor.py` — Transformation
```python
# Responsibility: Apply transformation mappings to eligible records via PySpark operations.
# All mappings are template-driven. No hardcoded field references.
# Filters to CLEAN + WARNING only. Applies mappings in sequence order.

def transform(template: dict, validated_dfs: dict[str, DataFrame]) -> DataFrame:
    """Apply all transformation mappings to CLEAN+WARNING records."""
```

### `output/flat_file_adapter.py` — Positional Output
```python
# Responsibility: Build fixed-width positional records from transformed DataFrame.
# Concatenates fields in sequence order. No delimiters. Verifies record length.
# Implements the OutputAdapter interface.

class FlatFileAdapter(OutputAdapter):
    def format_and_deliver(self, transformed_df: DataFrame, output_config: dict) -> str:
        """Format and write positional flat file."""
```

### `error/error_logger.py` — Error Persistence
```python
# Responsibility: Persist Error_Records with full diagnostic detail.
# Writes to local Parquet (POC) or database (production).
# Must include: table, field, rule_id, severity, failing_value, reference details.

def log_errors(validated_dfs: dict[str, DataFrame], template: dict, batch_run_id: str) -> int:
    """Extract and persist all Error_Records. Returns count logged."""
```

### `error/targeted_revalidation.py` — Scoped Re-Check
```python
# Responsibility: Re-validate corrected records + dependents only.
# Uses dependency graph to determine minimal re-check scope.
# Refuses if graph is stale (template version mismatch).

def revalidate(spark, template, staging_reader, record_key: str, table: str) -> dict:
    """Targeted revalidation of corrected record + dependents."""
```

### `engine/dependency_graph.py` — Dependency Tracking
```python
# Responsibility: Build and persist dependency links during cross-reference validation.
# Enables targeted revalidation by tracking which records depend on which references.
# Detects staleness by comparing stored template_version with active version.

def build_graph(cross_ref_results: DataFrame, rule: dict, batch_run_id: str) -> list[dict]:
    """Build dependency links from cross-reference evaluation results."""

def is_stale(graph_version: str, active_version: str) -> bool:
    """Check if dependency graph is stale relative to active template."""
```

---

## 3. ETL Pipeline Flow

The pipeline runs as a structured sequence with dependency-ordered table processing:

```
main.py (CLI)
  │
  ├─► template_loader.load_template()
  │     └─ Reads CSVs from templates/v<N>/
  │     └─ Validates all sections against published schemas
  │     └─ Resolves active version from versions.json
  │     └─ Returns structured template dict
  │
  ├─► validation_orchestrator.determine_table_order()
  │     └─ Reads table_dependencies from template
  │     └─ Topological sort (parents first)
  │     └─ Detects cycles → reject with clear error
  │     └─ Result: [CNT, CVG, ROL, ADD]
  │
  ├─► staging_reader.read_staging_table() [per table]
  │     └─ Reads each staging table into Spark DataFrame
  │     └─ Missing/empty table → log warning, skip
  │
  ├─► validation_orchestrator.run_validation()
  │     └─ For each table in order:
  │         ├─ rule_compiler.compile_all_rules() → Column expressions
  │         ├─ Apply presence/format rules via withColumn()
  │         ├─ Apply range rules via withColumn()
  │         ├─ Apply cross-reference rules via DataFrame joins
  │         ├─ Apply conditional rules (precondition filter → dependent)
  │         ├─ dependency_graph.build_graph() for cross-ref rules
  │         └─ severity_classifier.classify_severity()
  │
  ├─► error_logger.log_errors()
  │     └─ Extract failing records from VAL_ columns
  │     └─ Build Error_Records with full diagnostics
  │     └─ Persist to local Parquet (POC)
  │
  ├─► transformation_executor.transform()
  │     └─ Filters to CLEAN + WARNING records
  │     └─ Applies mappings in template sequence order
  │     └─ Formats fields (padding, truncation per mapping spec)
  │
  ├─► adapter_registry → flat_file_adapter.format_and_deliver()
  │     └─ Concatenates fields in sequence (no delimiters)
  │     └─ Verifies record length = sum(target_lengths)
  │     └─ Excludes records with length mismatch
  │     └─ Writes ea_transaction.txt
  │
  └─► execution_audit.write_audit_trail()
        └─ Template version, tables processed, record counts
        └─ Outputs produced, exit code
```

---

## 4. Error Handling Standards

Every function that touches a file or external resource must use try/except.

```python
# Good — clear, actionable error message
try:
    template = load_template(template_dir, spark)
except FileNotFoundError:
    raise FileNotFoundError(
        f"Template directory not found at: {template_dir}\n"
        f"Please ensure templates/v<N>/ exists with all required CSV files."
    )

# Bad — silent failure or generic message
try:
    template = load_template(template_dir, spark)
except Exception as e:
    print("Error")
```

- Never swallow exceptions silently
- Always include the file path, table name, or rule_id in the error message
- FATAL errors (template missing, schema violation, circular dep) → abort immediately
- Record-level errors → log Error_Record, continue processing
- Field-level transformation errors → default fill, log, continue record

### No Silent Skips for Uninterpretable Rules

An Active rule the engine cannot interpret MUST NOT be silently skipped or turned
into a no-op — that creates false confidence that a check ran when it did not.

- A rule-compiling handler that cannot parse its inputs (e.g. `compile_value_compare`
  given an `expected_result` it cannot interpret) RAISES `ValueError` with the
  `xref_id` and the raw value — it does NOT `return None`/no-op to hide the rule.
- The orchestrator catches that error and emits an explicit SEVERE
  `UNINTERPRETABLE_RULE <xref_id>: <reason>` value on every row (a `VAL_XREF_<id>`
  column) and logs `[VALIDATE] ERROR ...`. The rule surfaces in results and the
  error report; one bad rule does not abort the whole run.
- Distinguish this from "not applicable in scope" (a rule referencing a
  table/field not loaded for the active table set) — those are logged as visible
  `SKIP` messages, which is acceptable because they are out of scope, not
  engine failures.
- See `validation-principles.md` Principle 4 for the full policy.

---

## 5. Performance Standards — PySpark Set-Based Operations

### 5.1 DataFrame Column Expressions for Validation
All validation rules must be expressed as PySpark Column expressions applied via `withColumn()`:

```python
# Good — PySpark column expression (set-based, parallelized by Spark)
df = df.withColumn(
    "VAL_CNT_ISSUE_SYSTEM",
    F.when(
        F.length(F.trim(F.col("CNT_ISSUE_SYSTEM"))) != F.lit(2),
        F.lit("SEVERE: CNT_ISSUE_SYSTEM must be exactly 2 characters")
    ).otherwise(F.lit(None).cast(StringType()))
)

# Bad — row-by-row Python loop (defeats Spark parallelism)
for row in df.collect():
    if len(str(row["CNT_ISSUE_SYSTEM"]).strip()) != 2:
        # ...
```

### 5.2 DataFrame Joins for Cross-Reference Checks
Cross-reference validation must use DataFrame joins, not iterative lookups:

```python
# Good — anti-join to find missing references
missing = child_df.join(parent_df, join_condition, "left_anti")

# Bad — row-level lookup
for row in child_df.collect():
    if row["CVG_POLICY_NUMBER"] not in parent_values:
        # ...
```

### 5.3 Targeted Revalidation via Dependency Graph
When a record is corrected:
- Re-validate ONLY the corrected record + records identified by the dependency graph
- Do NOT re-run the full batch
- Detect graph staleness before allowing targeted revalidation

### 5.4 Spark Configuration
- POC: `local[*]` (uses all available cores on the local machine)
- Production: Distributed Spark via AWS Glue (cluster mode)
- Tests: `local[2]` (2 threads to catch parallelism bugs)

### 5.5 Bound the Logical Plan — Checkpoint Long withColumn/Join Chains

**Problem:** Applying many rules to one DataFrame as sequential `withColumn` / join
calls grows Spark's *logical plan* without bound. A single table can carry 60+
field rules and 100+ cross-reference rules; chained onto one un-materialized
DataFrame, the Catalyst analyzer slows sharply or fails (symptom: a massive
nested `Project [...]` plan, or a spurious `UNRESOLVED_COLUMN`). This is the same
class of issue documented for the transformation side ("Catalyst plan explosion").

**Standard:** When a loop applies more than ~25 sequential column/join operations
to one DataFrame, truncate the plan periodically by materializing:

```python
CHECKPOINT_INTERVAL = 25

def _truncate_plan(df):
    # localCheckpoint truncates lineage without needing a checkpoint dir and
    # keeps processing inside Spark (no collect-to-pandas).
    return df.localCheckpoint(eager=True)
```

- `validation_orchestrator.run_validation` (field-rule loop) and
  `apply_cross_references_for_table` (cross-ref loop) both call `_truncate_plan`
  every `CHECKPOINT_INTERVAL` applied operations.
- Prefer `localCheckpoint(eager=True)`; fall back to `cache()` + `count()` only if
  checkpointing is unavailable.
- This keeps runtime roughly linear in rule count regardless of data volume and
  is REQUIRED before onboarding additional tables (PRM/FIN/NFN/…). Do not remove
  it to "simplify" a loop.

### 5.6 Cross-Table Join Column Aliasing

When a handler joins a child to a parent/compare table, build the slim parent
projection in ONE explicit `select(F.col(pf).alias(alias))` pass — never a chain
of `withColumnRenamed` calls. Chained renames break when the compare field is
also a join key, or when parent and child are the same table (self-referential
rule), producing `UNRESOLVED_COLUMN` on a `_parent_cmp_*` alias. After building a
precondition flag from joined parent fields, drop those bare parent columns so a
later join does not create ambiguous duplicate lineage.

---

## 6. Naming Conventions

| Item | Convention | Example |
|---|---|---|
| Python files | lowercase_underscore | `rule_compiler.py` |
| Functions | lowercase_underscore | `compile_rule()` |
| Constants | UPPER_SNAKE_CASE | `ADAPTER_REGISTRY` |
| Variables | lowercase_underscore | `validated_dfs` |
| Output CSV files | lowercase_with_prefix | `cnt_clean.csv` |
| VAL columns | VAL_ + exact field name | `VAL_CNT_ISSUE_DATE` |
| Test functions | test_ + what it tests | `test_compile_exact_length_passes_valid()` |
| Template columns | lowercase_underscore | `rule_type`, `target_field` |
| Rule IDs | TABLE_NNN format | `CNT_001`, `CVG_015` |

---

## 7. Testing Standards

Every module must have a corresponding test file in `option_b/tests/`.

### Required test scenarios for every rule type compiler:
1. Valid input → expect `None` (pass)
2. Invalid input → expect severity-prefixed error message
3. Blank/null input → expect appropriate behavior per rule type
4. Edge cases (boundary lengths, boundary dates, empty allowed_values list)

### Required test scenarios for cross-reference rules:
1. All child references exist in parent → no errors
2. Some child references missing from parent → correct Error_Records generated
3. Parent table empty → all cross-ref rules SKIPPED (not FAILED)

### Required test scenarios for conditional rules:
1. Precondition FALSE → no error regardless of dependent check
2. Precondition TRUE + dependent passes → no error
3. Precondition TRUE + dependent fails → correct error message

### Validation engine immutability standard

The engine code must not contain any hardcoded business rules, field names, or table-specific logic. All behavior is driven by template content. If a test reveals behavior that requires hardcoded field knowledge, the design must be reconsidered.

---

## 7a. Targeted Revalidation Standards

### Dependency Graph Approach
During cross-reference validation, the engine builds a dependency graph recording which child records depend on which parent reference values. This graph enables targeted revalidation.

### Staleness Detection
Before targeted revalidation:
1. Compare the dependency graph's `template_version` with the active template version
2. If they differ → reject revalidation, require full run to rebuild the graph
3. Log: "Dependency graph built with template vX; current is vY. Full validation required."

### Scope Limitation Algorithm
```
GIVEN: corrected_record_key, corrected_table
1. Load dependency graph for current template version
2. Find all DependencyLinks where referenced_record_key = corrected_record_key
3. Collect source_record_keys from those links → affected set
4. Re-validate: corrected record + all affected records
5. Update Error_Record store (clear resolved, add new)
6. Update dependency graph links
```

Records with no dependency on the corrected value are NEVER re-validated.

---

## 7b. PySpark Testing Standards

### SparkSession Management
- Use a **session-scoped** SparkSession fixture shared across all tests in a session
- Spark master: `local[2]` (2 threads catches parallelism issues)
- App name: `"option_b_tests"`

```python
@pytest.fixture(scope="session")
def spark():
    session = SparkSession.builder.master("local[2]").appName("option_b_tests").getOrCreate()
    yield session
    session.stop()
```

### DataFrame Construction for Tests
- Keep test DataFrames small: 5-50 rows for unit tests, 100-500 for integration
- Construct DataFrames programmatically (no file I/O in unit tests)
- Use `spark.createDataFrame()` with explicit schemas

### Property-Based Testing with PySpark
- Use Hypothesis to generate random but constrained rule configurations and field values
- Generate small DataFrames (10-20 rows) per property test iteration for speed
- Minimum 100 iterations per property test
- Tag format: `# Feature: option-b-config-driven-engine, Property N: <description>`

### Test Isolation
- Each test function gets a fresh DataFrame (no shared mutable state)
- Tests must not depend on execution order
- Tests must not write to shared locations (use temp directories)

---

## 8. Logging and Output Standards

### Console output during pipeline run:
```
[TEMPLATE]  Loading template from: templates/v1/
[TEMPLATE]  Schema validation passed — 87 validation rules, 42 transformation mappings
[TEMPLATE]  Active version: v1 (2026-07-15T10:30:00Z)
[STAGING]   Reading CNT from staging_data/cnt.parquet — 10,000 records
[STAGING]   Reading CVG from staging_data/cvg.parquet — 25,000 records
[STAGING]   Reading ROL from staging_data/rol.parquet — 8,500 records
[STAGING]   Reading ADD from staging_data/add.parquet — 12,000 records
[VALIDATE]  Processing CNT — 32 field rules, 16 conditional rules
[VALIDATE]  Processing CVG — 15 field rules, 1 cross-reference rule
[VALIDATE]  Processing ROL — 12 field rules, 1 cross-reference rule
[VALIDATE]  Processing ADD — 12 field rules, 1 cross-reference rule
[VALIDATE]  CNT: CLEAN=8450, WARNING=930, SEVERE=620
[VALIDATE]  CVG: CLEAN=23100, WARNING=1200, SEVERE=700
[TRANSFORM] Transforming 33,680 eligible records (42 mappings)
[OUTPUT]    ea_transaction.txt — 33,680 records written
[AUDIT]     Execution audit trail → output/audit_trail.json
[DONE]      Pipeline completed in 45.2 seconds
```

### Log Prefixes

| PREFIX | LEVEL | MEANING |
|--------|-------|---------|
| `TEMPLATE` | INFO | Template loading, version, schema validation |
| `STAGING` | INFO | Staging table reads, row counts |
| `VALIDATE` | INFO | Validation progress per table, rule counts |
| `VALIDATE` | WARNING | Skipped rules — out of scope for active table set (missing table/field). Logged as `SKIP`, visible, not hidden. |
| `VALIDATE` | ERROR | Uninterpretable Active rule — `UNINTERPRETABLE_RULE <id>`. Emitted as SEVERE on affected rows; never silently dropped. |
| `TRANSFORM` | INFO | Transformation progress, record counts |
| `OUTPUT` | INFO | Output files produced, record counts |
| `REVAL` | INFO | Targeted revalidation scope, results |
| `AUDIT` | INFO | Execution audit trail written |
| `ENGINE` | FATAL | Unrecoverable errors causing abort |
| `DONE` | INFO | Pipeline complete, elapsed time |

**Rules:**
- No new prefixes may be introduced without updating this table.
- All prefixes are uppercase and enclosed in square brackets.

---

## 9. Dependencies

```
# requirements.txt (Option B)
pyspark>=3.5.0
pytest>=8.0.0
hypothesis>=6.100.0
```

No other dependencies are permitted without team agreement. The engine must run with only PySpark + standard library for production logic. Hypothesis is test-only.

---

## 10. Staging Data Preparation

For Option B, staging data CSVs are exported from the business-provided Sample_*_Data.xlsx workbooks in staging_data/ via scripts/export_sample_data.py. The export uses dtype=str to preserve all values as text. No synthetic data generator exists in this project — all test data comes directly from the BA-provided Excel workbooks.

---

## 11. Shell Execution Standards

### Shell type
The shell is **pwsh** (PowerShell Core), not `powershell.exe`. All `execute_pwsh` calls must use pwsh-compatible syntax.

### Working directory
Always set the working directory as the very first command in every `execute_pwsh` call:
```powershell
Set-Location "C:\POC\Git Version\assure-aat-etl-poc-kiro"
```

### Python executable
Always use the full Python executable path:
```
C:\Users\vvenugopal23\AppData\Local\Python\pythoncore-3.14-64\python.exe
```

### Example verified command
```powershell
Set-Location "C:\POC\Git Version\assure-aat-etl-poc-kiro"
C:\Users\vvenugopal23\AppData\Local\Python\pythoncore-3.14-64\python.exe -m pytest option_b/tests/ -v
```

---

*Steering file version: Option B*
*Owner: Software Engineering Team*
*Last updated: July 2026*
