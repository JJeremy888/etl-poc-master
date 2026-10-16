# Assure AAT ETL POC — Config-Driven Validation & Transformation Engine

A PySpark-based, config-driven ETL engine for DXC insurance data conversion. The engine reads business validation rules and transformation mappings from versioned CSV templates at runtime, validates staging data record-by-record, and produces a positional flat file output for the End-state Administration (EA) system.

This is **Option B** — the engine interprets rules as data (no code generation). Business Analysts maintain the template CSVs; the engine behavior changes without any code modifications.

---

## What This Engine Does

1. **Loads templates** — Reads validation rules, cross-reference rules, transformation mappings, table dependencies, and output config from versioned CSV files
2. **Validates staging data** — Applies field-level rules (not_blank, exact_length, allowed_values, numeric_range, date comparisons, etc.) plus cross-reference rules (cross-table match, conditional, occurrence checks) against all records across 4 tables (CNT, CVG, ROL, ADD). The current master workbook yields 261 field-level rules and 164 cross-reference rules.
3. **Classifies records** — Each row is classified as CLEAN, WARNING, or SEVERE based on rule failures
4. **Transforms eligible records** — Maps source fields to target fields using 399+ transformation mappings (direct_copy, date_split, constant, space/zero fill, conditional_derived, etc.)
5. **Produces output** — Generates a fixed-width positional flat file (`ea_transaction.txt`) for the EA system

Only CLEAN and WARNING records proceed to transformation. SEVERE records are excluded from output and logged for remediation.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         AWS Glue (Production)                       │
│                    or CLI: python -m option_b.main (Local)          │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Template Loader (config/template_loader.py)                        │
│  Reads: templates/v1/validation_rules.csv                           │
│         templates/v1/cross_references.csv                           │
│         templates/v1/transformation_mappings.csv                    │
│         templates/v1/table_dependencies.csv                         │
│         templates/v1/output_config.csv                              │
│  (CSVs generated from rules/Validation_Rules_Master.xlsx by         │
│   scripts/generate_config_from_master.py)                           │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Validation Orchestrator (engine/validation_orchestrator.py)        │
│  - Topological sort: CNT → CVG, ROL, ADD                           │
│  - Rule Compiler: interprets rules into PySpark Column expressions  │
│  - Cross-reference checks (child→parent joins)                      │
│  - Severity classification per row                                  │
│  - Error logging                                                    │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Transformation Executor (engine/transformation_executor.py)        │
│  - Filters to CLEAN + WARNING records                               │
│  - Applies 399 field mappings (sorted by sequence)                  │
│  - Builds OUT_ columns with padding to target_length                │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Output Adapter (output/flat_file_adapter.py)                       │
│  - Concatenates OUT_ columns into positional fixed-width records    │
│  - Writes ea_transaction.txt (one line per record)                  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

### Required Software

| Software | Version | Purpose |
|----------|---------|---------|
| Python | 3.10+ | Runtime language |
| Java (JDK) | 8, 11, or 17 | PySpark requires a JVM — Spark engine runs on Java |
| pip | Latest | Python package manager |

### Environment Variables (Windows)

| Variable | Example | Purpose |
|----------|---------|---------|
| `JAVA_HOME` | `C:\Program Files\Java\jdk-17` | Points PySpark to the Java installation |
| `PATH` | Include `%JAVA_HOME%\bin` | Makes `java.exe` discoverable |

### Python Dependencies (from `requirements.txt`)

| Package | Version | Purpose |
|---------|---------|---------|
| pyspark | >=3.5.0, <4.0.0 | Spark engine — validation and transformation processing |
| pandas | >=2.2.0 | Data conversion (Spark DataFrame ↔ pandas) |
| pyyaml | >=6.0.0 | Configuration file parsing |
| pytest | >=8.0.0 | Test framework |
| hypothesis | >=6.0.0 | Property-based testing |
| ruff | >=0.1.0 | Linting |

### What is NOT Needed for the POC

- No Hadoop installation (PySpark bundles a minimal Hadoop client)
- No Spark cluster (runs in local mode on a single machine)
- No AWS account or Glue setup (that is the production target, not the POC)
- No database server (staging data is read from local CSV files)

---

## Folder Structure

```
assure-aat-etl-poc-kiro/
├── README.md                               # This file
├── CONTRIBUTING.md                         # Contribution guidelines
├── requirements.txt                        # Python dependencies
│
├── option_b/                               # *** Config-Driven Engine (Option B) ***
│   ├── main.py                             # CLI entry point
│   ├── config/
│   │   ├── template_loader.py              # Loads & validates template CSVs
│   │   ├── template_versioner.py           # Template version management
│   │   └── schema_definitions.py           # Schema constants & registered types
│   ├── engine/
│   │   ├── rule_compiler.py                # Interprets rules → PySpark Column exprs
│   │   ├── validation_orchestrator.py      # Orchestrates validation across tables
│   │   ├── transformation_executor.py      # Applies mappings to build output fields
│   │   ├── presence_format_rules.py        # Handlers: not_blank, exact_length, etc.
│   │   ├── range_rules.py                  # Handlers: date_greater_than, date_lte, date_less_than_equal
│   │   ├── conditional_rules.py            # Handlers: conditional rules
│   │   ├── cross_reference_rules.py        # Cross-reference handlers (Column + join)
│   │   ├── severity_classifier.py          # Row-level CLEAN/WARNING/SEVERE
│   │   └── dependency_graph.py             # Table dependency tracking
│   ├── input/
│   │   └── staging_reader.py               # Reads staging CSVs into Spark DataFrames
│   ├── output/
│   │   ├── base_adapter.py                 # Abstract output adapter
│   │   ├── adapter_registry.py             # Adapter plugin registry
│   │   └── flat_file_adapter.py            # Positional flat file writer
│   ├── error/
│   │   ├── error_logger.py                 # Validation error logging
│   │   └── targeted_revalidation.py        # Re-validate specific records
│   ├── audit/
│   │   └── execution_audit.py              # Run audit trail
│   └── tests/
│       ├── conftest.py                     # Shared test fixtures (SparkSession)
│       ├── test_rule_compiler.py
│       ├── test_template_loader.py
│       ├── test_template_versioner.py
│       ├── test_conditional_rules.py
│       ├── test_cross_reference_rules.py
│       ├── test_range_rules.py
│       ├── test_staging_reader.py
│       └── test_e2e_pipeline.py
│
├── templates/                              # *** Business Rule Templates ***
│   ├── versions.json                       # Active version tracker
│   └── v1/                                 # Version 1 templates (generated from the master workbook)
│       ├── validation_rules.csv            # 261 field-level validation rules
│       ├── cross_references.csv            # 164 cross-reference / conditional rules
│       ├── transformation_mappings.csv     # 399 transformation mappings
│       ├── table_dependencies.csv          # Table relationships (parent/child)
│       ├── output_config.csv               # Output format configuration
│       └── _reconciliation_report.txt      # Adapter run report (counts + review flags)
│
├── rules/                                  # Business-authored sources
│   ├── Validation_Rules_Master.xlsx        # *** Authoritative validation rule workbook ***
│   ├── RULES_TEMPLATE_GUIDE.md             # How BAs author the workbook
│   └── EA_Transaction_Mapping.xlsx         # Transformation mapping source
│
├── staging_data/                           # Input: staging CSV files (CNT, CVG, ROL, ADD)
├── output/                                 # Generated at runtime
│
├── config/
│   └── project_config.yaml                 # Project-level configuration
│
├── docs/
│   ├── requirements.md                     # Full requirements document
│   ├── EXTENDING_THE_ENGINE.md             # Engineer guide: add rules/types without breaking existing code
│   └── workshop-notes/                     # Team workshop notes
│
└── .kiro/
    ├── steering/                           # Kiro IDE steering files
    ├── hooks/                              # Kiro IDE agent hooks
    └── specs/                              # Feature specifications
```

---

## Setup

### Step 1: Clone the repository

```powershell
git clone <repo-url>
cd assure-aat-etl-poc-kiro
```

### Step 2: Verify Java is installed

```powershell
java -version
```

Expected output: version 8, 11, or 17. If missing, install JDK from [Adoptium](https://adoptium.net/).

Set JAVA_HOME if not already set:

```powershell
# Check current value
echo $env:JAVA_HOME

# Set permanently (run as admin)
[System.Environment]::SetEnvironmentVariable("JAVA_HOME", "C:\Program Files\Java\jdk-17", "Machine")
```

### Step 3: Create and activate a virtual environment

```powershell
python -m venv .venv
.venv\Scripts\activate
```

### Step 4: Install dependencies

```powershell
pip install -r requirements.txt
```

### Step 5: Verify PySpark

```powershell
python -c "from pyspark.sql import SparkSession; spark = SparkSession.builder.master('local[1]').getOrCreate(); print('Spark OK'); spark.stop()"
```

### Step 6: Prepare the rule sheets

Validation rules live in a single authoritative workbook. Place it in `rules/`:

| Document | Save as | Place in |
|----------|---------|----------|
| Validation rules master workbook | `Validation_Rules_Master.xlsx` | `rules/` |
| EA Transaction Mapping | `EA_Transaction_Mapping.xlsx` | `rules/` |

`Validation_Rules_Master.xlsx` has five tabs — `Contract`, `Address`, `Roles`,
`Coverage`, and `Cross_References`. Authoring instructions are in
`rules/RULES_TEMPLATE_GUIDE.md`.

Then generate the template CSVs from the workbook:

```powershell
python scripts/generate_config_from_master.py
```

This writes `templates/v1/validation_rules.csv`, `cross_references.csv`,
`table_dependencies.csv`, and a `_reconciliation_report.txt`. Review the report
to confirm every rule type is recognized.

### Step 7: Prepare the sample data

Take the DATA SET EXAMPLE FINAL workbook and split each tab into a separate .xlsx file:

| Tab | Save as | Place in |
|-----|---------|----------|
| Contract data | `Sample_Contract_Data.xlsx` | `staging_data/` |
| Coverage data | `Sample_Coverage_Data.xlsx` | `staging_data/` |
| Role data | `Sample_Role_Data.xlsx` | `staging_data/` |
| Address data | `Sample_Address_Data.xlsx` | `staging_data/` |

### Step 8: Export staging data (generates CSVs from Excel)

```powershell
python scripts/export_sample_data.py
```

This reads the Excel files from `staging_data/` and produces the CSV files the pipeline consumes. Zero-pad normalization is applied to enumerated code fields during export.

### Step 9: Verify setup

```powershell
python -m option_b.main --validate --template-dir templates/v1 --output-dir output
```

Expected: Pipeline processes 4 tables (CNT, CVG, ROL, ADD) and reports CLEAN/WARNING/SEVERE counts.

---

## Running the Pipeline

### Full Pipeline (Validate + Transform + Output)

```powershell
python -m option_b.main --validate --transform --output
```

### Validation Only

```powershell
python -m option_b.main --validate
```

### Targeted Revalidation (Single Record)

```powershell
python -m option_b.main --revalidate --record-key "001|POL123456" --table CNT
```

### CLI Options

| Flag | Description |
|------|-------------|
| `--validate` | Run validation phase |
| `--transform` | Run transformation phase |
| `--output` | Run output phase (produce flat file) |
| `--revalidate` | Targeted revalidation mode |
| `--record-key` | Record key for revalidation |
| `--table` | Table name for revalidation |
| `--template-dir` | Template directory (default: `templates/v1`) |
| `--output-dir` | Output directory (default: `output`) |

---

## Output Files

| File | Description |
|------|-------------|
| `output/ea_transaction.txt` | Positional fixed-width flat file for EA system |
| `output/errors_<table>_<version>_<run_id>.csv` | Validation errors per table |
| `output/dependency_graph_<run_id>.json` | Table dependency graph for the run |
| `output/audit_<run_id>.json` | Execution audit trail |

---

## Template Files (Maintained by BAs)

### validation_rules.csv

Defines business rules. Each row is one rule:

| Column | Purpose | Example |
|--------|---------|---------|
| rule_id | Unique identifier | CNT_001 |
| target_table | Which table | CNT |
| target_field | Which field | CNT_COMPANY_CODE |
| rule_type | Rule type | not_blank, exact_length, allowed_values, valid_date, date_greater_than, conditional |
| severity | SEVERE or WARNING | SEVERE |
| param_1, param_2 | Rule parameters | 2 (for exact_length) |
| allowed_values | Pipe-separated values | A\|W\|B\|T |

### transformation_mappings.csv

Defines source-to-target field mappings for the EA flat file:

| Column | Purpose | Example |
|--------|---------|---------|
| mapping_id | Unique identifier | MAP_001 |
| source_table | Source table | CNT |
| source_field | Source column | CNT_COMPANY_CODE |
| target_field | Target field name | COMPANY-CODE |
| transformation_type | How to transform | direct_copy, date_split_year, constant, space_fill |
| target_length | Fixed width | 3 |
| target_data_type | CHAR, NUMERIC, etc. | CHAR |
| padding_rule | Padding approach | right_space, left_zero |
| sequence | Output position order | 5 |

### cross_references.csv

Cross-reference and conditional rules that span fields or tables. Loaded
alongside `validation_rules.csv` and applied by the orchestrator.

| Column | Purpose | Example |
|--------|---------|---------|
| xref_id | Unique identifier | XR_CON_008 |
| table_name | Table the rule applies to (code) | CNT |
| target_field | Field being checked | CNT_MATURE_EXPIRE_DATE |
| rule_type | Cross-reference rule type | cross_table_match, date_greater_than, conditional |
| severity | SEVERE or WARNING | SEVERE |
| precondition_field / _operator / _value | Optional gate | CNT_PRODUCT_TYPE / in / A\|W\|B |
| expected_result | Condition the target must satisfy | (free text allowed) |
| compare_table / compare_field | Other table + field for cross-table checks | CNT / CNT_ISSUE_DATE |
| join_child_fields / join_parent_fields | Pipe-separated join keys | CVG_COMPANY_CODE\|CVG_POLICY_NUMBER |
| error_message | Message emitted on failure | This date must be > CNT_ISSUE_DATE |
| active | Y/N (N = carried but not evaluated) | Y |

### Supported Rule Types

**Field-level** (in `validation_rules.csv`):
`not_blank`, `exact_length`, `max_length`, `exact_length_or_blank`,
`allowed_values`, `allowed_blank`, `valid_date`, `numeric`, `numeric_string`,
`numeric_decimal`, `numeric_range`, `min_value`, `project_defined_value`,
`conditional`, `conditional_null`, `conditional_blank`, `cross_field_conditional`,
`default_then_warn`, `date_greater_than`, `date_lte`, `numeric_min`, `numeric_max`

**Cross-reference** (in `cross_references.csv`):
`required`, `value_compare`, `field_compare`, `date_greater_than`,
`date_less_than_equal`, `cross_table_match`, `occurrence_check`,
`cross_reference_exists`, `conditional`

The engine is registry-based — see `docs/EXTENDING_THE_ENGINE.md` to add a new
type without altering existing rules or the orchestrator.

### Supported Transformation Types

`direct_copy`, `date_split_year`, `date_split_month`, `date_split_day`, `constant`, `space_fill`, `zero_fill`, `conditional_derived`, `system_generated`

---

## Running Tests

```powershell
pytest option_b/tests/ -v
```

---

## How It Works Technically

### Rules are Interpreted, Not Compiled to Code

The engine does NOT generate Python files from rules. Instead:
1. Template CSVs are loaded as lists of dicts
2. The Rule Compiler maps each `rule_type` string to a handler function via a dispatch table
3. Each handler returns a PySpark Column expression (a lazy computation descriptor)
4. Spark applies all expressions vectorized across all records simultaneously

### Processing is Set-Based, Not Row-by-Row

PySpark processes all records in a table as a single DataFrame operation. Adding a rule result column applies to all rows at once — there is no Python for-loop iterating over individual records.

### Why PySpark (Not Plain Python/Pandas)

- **AWS Glue compatibility** — Same PySpark code runs locally and in production Glue with minimal changes
- **Horizontal scalability** — Handles millions of records across a cluster (production)
- **Optimized execution** — Spark's Catalyst optimizer reorganizes operations for performance
- **Fault tolerance** — Built-in retry and recovery at the task level

---

## Adding a New Rule Type

1. Implement a handler in the appropriate module (`presence_format_rules.py`,
   `range_rules.py`, or `cross_reference_rules.py`)
2. Register it in `rule_compiler.py` → `RULE_HANDLER_REGISTRY` (field-level) or
   `CROSS_REFERENCE_HANDLER_REGISTRY` (cross-reference)
3. Add the type to `schema_definitions.py` → `REGISTERED_RULE_TYPES` or
   `REGISTERED_CROSS_REFERENCE_TYPES`
4. Author rules using the new type in `rules/Validation_Rules_Master.xlsx`, then
   regenerate with `python scripts/generate_config_from_master.py`
5. Add unit tests

Full recipes (field-level, cross-reference, join-based, new operator, new table)
are in `docs/EXTENDING_THE_ENGINE.md`.

---

## Adding a New Transformation Type

1. Add a case to `transformation_executor.py` → `_get_transform_expression()`
2. Register in `schema_definitions.py` → `REGISTERED_TRANSFORMATION_TYPES`
3. Add mappings using the new type to `templates/v1/transformation_mappings.csv`
4. Add unit tests

---

## Production Deployment (Future)

In production, this engine runs on AWS Glue with millions of records:

### Production Data Flow

```
Staging DB (Glue Data Catalog)
    → Spark reads (distributed across executors)
    → Validation (all in DataFrame — never collected to driver)
    → Write validated DataFrames to S3 as Parquet       ← checkpoint
    → Read back eligible records (CLEAN + WARNING)
    → Transformation (all in DataFrame)
    → Spark .write.text() directly to S3                ← no .collect()/.toPandas()
```

### Why S3 Intermediate Checkpoint

| Benefit | Description |
|---------|-------------|
| Decoupled phases | Validation and transformation run independently — if transformation fails, no re-validation needed |
| Memory safety | No single phase holds all data in driver memory; each reads from S3, processes, writes to S3 |
| Auditability | Validated intermediate data persists for debugging and compliance |
| Resumability | A failed run can resume from checkpoint without re-processing upstream |

### What Changes vs POC

| Component | POC | Production |
|-----------|-----|------------|
| SparkSession | Created locally (`local[1]`) | Provided by GlueContext |
| Staging data | Local CSV files | Glue Data Catalog / S3 / JDBC |
| Intermediate storage | In-memory DataFrames | S3 Parquet checkpoint |
| Output write | `.toPandas()` → file write | Spark `.write.text()` to S3 |
| Flat file adapter | ~5 lines change (swap `.toPandas()` for `.write.text()`) | Same adapter, different write method |
| All other engine code | Identical | Identical |

The engine code (`option_b/`) remains the same — only the data source, intermediate storage, and output write method change.

---

## Full Requirements

See [docs/requirements.md](docs/requirements.md) for the complete requirements document.
