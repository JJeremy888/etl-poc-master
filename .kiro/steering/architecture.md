# Steering: Architecture
## Option B — Config-Driven PySpark Validation & Transformation Engine

---

## Purpose of This File

This file tells Kiro the architectural decisions, design principles, and system structure for the Option B Config-Driven Engine. Kiro must follow these decisions when generating any code, scripts, or configurations within `option_b/`.

---

## 1. System Overview

The Config-Driven Engine is a PySpark-based interpreter that:

1. Loads versioned validation rules and transformation mappings from structured Template CSV files
2. Reads policy data records from a staging database (simulated locally as Parquet/CSV files)
3. Interprets rules at runtime as PySpark DataFrame column expressions — no code is generated
4. Validates records across all tables (CNT, CVG, ROL, ADD) in dependency order
5. Classifies rows as CLEAN, WARNING, or SEVERE
6. Logs errors with full diagnostic detail for BA-facing dashboards
7. Transforms eligible (CLEAN + WARNING) records via template-driven mappings
8. Delivers output through pluggable adapters (positional flat file for POC)
9. Supports targeted revalidation of corrected records via a dependency graph

The engine operates on staging database tables. It assumes records have already passed a structural/file-level scan (upstream, out of scope). For the POC, PySpark runs locally in standalone mode (`pip install pyspark`). The intended production target is AWS Glue.

> Full requirements are in `.kiro/specs/option-b-config-driven-engine/requirements.md`.

---

## 2. Option A Legacy Note

The original pipeline (Option A) exists as a parallel codebase in `src/`. It uses a four-layer Pandas architecture with code-centric validation modules (`validation_engine.py`, `validate_cvg.py`, etc.). Option A is deprecated. It is retained as historical reference only — not for new development, not as a fallback, and not as a runtime target. All new work targets Option B exclusively.

---

## 3. Component Architecture

Option B replaces the layer-based architecture with a component-based design:

```
┌─────────────────────────────────────────────────────┐
│  RUN TRIGGER                                        │
│  main.py (CLI for POC)                             │
│  Accepts CLI arguments to initiate execution.       │
│  Open design question for production trigger.       │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│  CONFIG LAYER                                       │
│  template_loader.py + template_versioner.py         │
│  Loads versioned Template CSVs, validates schemas.  │
│  Records which version is active for auditability.  │
│  Rejects malformed templates with clear errors.     │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│  INPUT LAYER                                        │
│  staging_reader.py                                  │
│  Reads staging tables into Spark DataFrames.        │
│  POC: local Parquet/CSV files in staging_data/.     │
│  Production: Glue Data Catalog / JDBC.              │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│  CORE ENGINE                                        │
│  validation_orchestrator.py — orchestrates all      │
│    tables in dependency order                       │
│  rule_compiler.py — translates template rules       │
│    into PySpark Column expressions                  │
│  presence_format_rules.py — not_blank, length, etc. │
│  range_rules.py — numeric/date bounds               │
│  cross_reference_rules.py — DataFrame joins         │
│  conditional_rules.py — IF-THEN evaluation          │
│  severity_classifier.py — SEVERE/WARNING/CLEAN      │
│  transformation_executor.py — mapping application   │
│  dependency_graph.py — build + persist dep links    │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│  ERROR & REVALIDATION                              │
│  error_logger.py — persists Error_Records           │
│  targeted_revalidation.py — re-checks corrected     │
│    records + dependents via dependency graph         │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│  OUTPUT LAYER                                       │
│  adapter_registry.py — registers/dispatches adapters│
│  flat_file_adapter.py — positional fixed-width file │
│  base_adapter.py — abstract adapter interface       │
│  (Future: S3 adapter, REST API adapter)             │
└─────────────────────────────────────────────────────┘
```

---

## 4. Module Structure

```
option_b/
├── main.py                         ← CLI entry point + run trigger
├── config/
│   ├── __init__.py
│   ├── template_loader.py          ← Load, validate, filter template files
│   ├── template_versioner.py       ← Version tracking, comparison, retrieval
│   └── schema_definitions.py       ← Fixed schema constants for validation
├── input/
│   ├── __init__.py
│   └── staging_reader.py           ← Read staging tables into Spark DataFrames
├── engine/
│   ├── __init__.py
│   ├── validation_orchestrator.py  ← Orchestrate validation across tables
│   ├── rule_compiler.py            ← Translate rules → PySpark expressions
│   ├── presence_format_rules.py    ← not_blank, exact_length, max_length, etc.
│   ├── range_rules.py              ← Numeric/date bounds
│   ├── cross_reference_rules.py    ← DataFrame joins for referential integrity
│   ├── conditional_rules.py        ← IF-THEN precondition evaluation
│   ├── severity_classifier.py      ← SEVERE/WARNING/CLEAN assignment
│   ├── transformation_executor.py  ← Apply transformation mappings
│   └── dependency_graph.py         ← Build and persist dependency links
├── error/
│   ├── __init__.py
│   ├── error_logger.py             ← Persist Error_Records
│   └── targeted_revalidation.py    ← Re-check corrected + dependent records
├── output/
│   ├── __init__.py
│   ├── adapter_registry.py         ← Register and dispatch Output_Adapters
│   ├── flat_file_adapter.py        ← Positional fixed-width flat file
│   └── base_adapter.py             ← Abstract adapter interface
├── audit/
│   ├── __init__.py
│   └── execution_audit.py          ← Execution audit trail logging
└── tests/
    ├── __init__.py
    ├── test_template_loader.py
    ├── test_rule_compiler.py
    ├── test_cross_reference_rules.py
    ├── test_conditional_rules.py
    ├── test_severity_classifier.py
    ├── test_transformation_executor.py
    ├── test_dependency_graph.py
    ├── test_error_logger.py
    ├── test_targeted_revalidation.py
    ├── test_flat_file_adapter.py
    ├── test_staging_reader.py
    ├── test_validation_orchestrator.py
    └── test_e2e_pipeline.py
templates/
├── v1/
│   ├── validation_rules.csv        ← Field-level validation rules for all tables
│   ├── cross_references.csv         ← Cross-reference / conditional rules
│   ├── transformation_mappings.csv ← Source→target field mappings
│   ├── output_config.csv           ← Output format + delivery configuration
│   └── table_dependencies.csv      ← Parent/child dependency declarations
├── versions.json                   ← Version registry with timestamps
└── schema/
    ├── validation_rules_schema.json
    ├── transformation_mappings_schema.json
    ├── output_config_schema.json
    └── table_dependencies_schema.json
staging_data/                        ← POC: local CSV files (exported from Sample_*_Data.xlsx)
├── cnt.csv
├── cvg.csv
├── rol.csv
└── add.csv
```

---

## 5. Processing Pipeline

```
main.py (CLI)
  │
  ├─► template_loader.load_template()
  │     └─ Reads template CSVs from templates/v<N>/
  │     └─ Validation templates are GENERATED from the single master workbook (rules/Validation_Rules_Master.xlsx) via scripts/generate_config_from_master.py; transformation mappings from EA_Transaction_Mapping.xlsx — not manually authored
  │     └─ Validates schema (rejects with clear error on violation)
  │     └─ Resolves active version
  │
  ├─► validation_orchestrator.determine_table_order()
  │     └─ Topological sort of table_dependencies.csv
  │     └─ Detects circular dependencies (fatal error)
  │     └─ Parents before children (CNT before CVG, ROL, ADD)
  │
  ├─► staging_reader.read_staging_table() [per table]
  │     └─ Reads Parquet/CSV into Spark DataFrame
  │     └─ Logs missing/empty tables (skips, does not fail)
  │
  ├─► validation_orchestrator.run_validation()
  │     └─ For each table in dependency order:
  │         ├─ rule_compiler.compile_all_rules() → Column expressions
  │         ├─ Apply presence/format, range rules as withColumn()
  │         ├─ Apply cross-reference rules as DataFrame joins
  │         ├─ Apply conditional rules (precondition → dependent)
  │         ├─ Record dependency links for cross-reference rules
  │         └─ severity_classifier.classify_severity()
  │
  ├─► error_logger.log_errors()
  │     └─ Persists Error_Records with full diagnostics
  │
  ├─► transformation_executor.transform()
  │     └─ Filters to CLEAN + WARNING records
  │     └─ Applies mappings in template sequence order
  │     └─ Formats fields (padding, truncation)
  │
  ├─► adapter_registry.get_adapter() → flat_file_adapter
  │     └─ Concatenates fields in sequence (no delimiters)
  │     └─ Verifies record length = sum(target_lengths)
  │     └─ Writes ea_transaction.txt
  │
  └─► execution_audit.write_audit_trail()
        └─ Template version, table counts, output artifacts
```

---

## 6. Design Constraints

- **Language:** Python 3.12+
- **Processing engine:** PySpark — local standalone for POC, AWS Glue for production
- **No AI/LLM at runtime:** All rule evaluation is deterministic; no machine-learning inference, no probabilistic thresholds
- **No code generation:** The engine interprets template rules directly as PySpark DataFrame operations. No Python/SQL/PySpark scripts are generated from rules at any point.
- **Template-driven:** All validation rules, transformation mappings, and output configuration live in versioned Template CSVs. BAs edit templates; developers add new types only when genuinely new logic patterns are required.
- **Set-based processing:** All validation and transformation as DataFrame column expressions or joins. No row-by-row Python loops for data processing.
- **POC scope:** Runs entirely on a local machine with `pip install pyspark`. No cloud dependencies.

---

## 7. Non-Functional Requirements

### 7.1 Extensibility
- Adding a new validation rule using an existing Rule_Type requires only a template edit — no code changes.
- Adding a new table requires adding a tab to `Validation_Rules_Master.xlsx` (field rules + cross-references) and a `table_dependencies` entry — no engine code changes.
- Adding a genuinely new Rule_Type or Transformation_Type requires a developer to implement and register it in the engine.

### 7.2 Deterministic Execution
- Same input records + same Template_Version = identical outputs on every run.
- Full execution audit trail (template version, record counts, output artifacts).
- Per-record audit trace available showing each rule applied and its result.

### 7.3 Separation of Concerns
- Config Layer knows nothing about data processing.
- Core Engine knows nothing about file I/O or delivery mechanisms.
- Output Adapters know nothing about validation logic.
- Error/Revalidation knows nothing about output formatting.

### 7.4 Performance
- All validation as PySpark DataFrame column expressions (set-based, parallelized by Spark).
- Cross-reference checks as DataFrame joins (not row-level lookups).
- Targeted revalidation via dependency graph (not full-batch re-run).
- POC: `local[*]` Spark mode. Production: distributed Spark cluster.

### 7.5 Production Scalability (Millions of Records)

**Critical constraint:** At production scale, data must NEVER be collected to the Spark driver via `.collect()`, `.toPandas()`, or `.toLocalIterator()`. All processing must remain distributed across Spark executors.

**Recommended production data flow:**

```
Staging DB → Spark validates (distributed)
    → Write validated DataFrames to S3 as Parquet (checkpoint)
    → Read back eligible records (CLEAN + WARNING)
    → Transform (distributed)
    → Spark .write.text() to S3 (no driver memory)
```

**Rules for production-scale code:**

1. **No `.collect()` or `.toPandas()`** in any code path that handles full datasets. These pull all data into driver memory and cause OutOfMemoryError at scale.
2. **Use S3 Parquet as intermediate storage** between validation and transformation phases. This decouples the phases, enables resumability, and bounds memory usage.
3. **Use Spark-native `.write.text()`** for the flat file output adapter instead of collecting records and writing line-by-line.
4. **Use `coalesce(1)`** only when the downstream system requires a single output file. If the target accepts a directory of part files, omit `coalesce(1)` for maximum parallelism.
5. **The POC uses `.toPandas()`** in `flat_file_adapter.py` for simplicity — this is acceptable for hundreds of sample records and will be replaced for production.

**What changes for production (single file change):**

| Component | Change Required |
|-----------|----------------|
| `flat_file_adapter.py` | Replace `.toPandas()` → `.write.text()` (~5 lines) |
| All other engine code | No changes — stays identical |

### 7.6 Reliability
- Template schema violations → immediate rejection with descriptive error.
- Missing staging tables → log warning, skip dependent rules, continue.
- Circular dependencies → detect and reject template.
- Transformation field failure → default fill, log error, continue record.
- Uninterpretable Active rule → emit explicit SEVERE `UNINTERPRETABLE_RULE`
  marker + log ERROR; never silently skip, never abort the whole run
  (see 7.7-C and validation-principles.md Principle 4).

### 7.6 Portability
- Engine code is identical between POC and production.
- Only "edges" change: Spark session init, data source connection, delivery mechanism.
- All paths use `pathlib.Path`.

### 7.7 Runtime Robustness (Validation Orchestrator)

These are hard-won engine behaviors discovered while running the full validation
on real sample data. They apply to any table and scale, and must be preserved.

**A. Spark logical-plan truncation (avoids "plan explosion").**
The orchestrator applies many rules to one DataFrame as sequential `withColumn`
/ join operations (a table can have 60+ field rules and 100+ cross-reference
rules). Chaining that many operations onto one un-materialized DataFrame grows
the Spark *logical plan* without bound; past ~50 layers the Catalyst analyzer
slows dramatically or fails to resolve deep columns (symptom: a giant nested
`Project [...]` plan dump, or `UNRESOLVED_COLUMN` deep in the stack).

- **Fix:** `validation_orchestrator._truncate_plan()` calls
  `df.localCheckpoint(eager=True)` to materialize the DataFrame and reset its
  lineage. Both the field-rule loop (`run_validation`) and the cross-reference
  loop (`apply_cross_references_for_table`) checkpoint every
  `CHECKPOINT_INTERVAL` (default 25) applied operations.
- **Why localCheckpoint:** truncates lineage without needing a checkpoint dir;
  keeps processing inside Spark (no collect-to-pandas). Falls back to
  `cache()`+`count()` if checkpointing is unavailable.
- **Do NOT** remove the checkpointing to "simplify" the loop — it is what keeps
  runtime roughly linear in the number of rules regardless of data volume, and
  is essential when the remaining tables (PRM/FIN/NFN/etc.) are added.

**B. Cross-table join column aliasing.**
`apply_cross_table_match` / `apply_match_across_occurrences` join a child to a
parent (or compare) table and must alias the pulled-in parent columns to avoid
collisions. Build the slim parent projection in ONE explicit
`select(F.col(pf).alias(...))` pass — NOT a chain of `withColumnRenamed` calls.
Chained renames break when (a) the compare field is also a join key, or (b) the
parent and child are the same table (self-referential rule), producing
`UNRESOLVED_COLUMN` on a `_parent_cmp_*` alias. Also: `_attach_precondition_flag`
drops the joined bare parent precondition columns after building the flag, so a
later parent join does not create ambiguous duplicate lineage.

**C. No silent skips (see validation-principles.md Principle 4).**
A rule the engine cannot interpret is emitted as an explicit SEVERE
`UNINTERPRETABLE_RULE <id>` marker on every row and logged as
`[VALIDATE] ERROR`, never silently dropped. One uninterpretable rule must not
abort the whole run, and must not vanish. Rules that are merely out of scope for
the active table set (missing table/field) are logged as `SKIP` (visible, not
hidden).

**D. Resilience guard on join rules.**
Before applying a join-based cross-reference, the orchestrator verifies the
needed fields exist on the child and parent DataFrames. A mistyped field name
(e.g. `CNT_ISSUE` vs `CNT_ISSUE_DATE`) is logged as `SKIP ... fields not in data`
rather than aborting the run with `UNRESOLVED_COLUMN`.

---

## 8. Run Trigger (Open Design Question)

For the POC, manual CLI invocation is the run trigger:

```bash
python -m option_b.main --validate --transform --output
python -m option_b.main --validate
python -m option_b.main --revalidate --record-key POL001 --table CNT
```

For production, an event-driven trigger (S3 events / Step Functions) is recommended, with CLI preserved as a manual override. The trigger mechanism is replaceable without modifying core engine logic.

---

## 9. Team Ownership by Component

| Component | Directory | Owner |
|---|---|---|
| CLI / Run Trigger | `option_b/main.py` | ETL Engineer |
| Config Layer | `option_b/config/` | Business Analyst + ETL Engineer |
| Input Layer | `option_b/input/` | Data / ETL Engineer |
| Core Engine | `option_b/engine/` | Software Engineer |
| Error & Revalidation | `option_b/error/` | Software Engineer |
| Output Layer | `option_b/output/` | Software Engineer / Integration |
| Audit | `option_b/audit/` | Software Engineer |
| Templates | `templates/` | Business Analyst (owns content) |
| Template Schema | `templates/schema/` | Software Engineer (owns schema) |

When team members update their component, they must not modify files outside their ownership boundary without team agreement.

---

## 10. POC vs Production Differences

| Aspect | POC (Local) | Production (AWS Glue) |
|--------|-------------|----------------------|
| Spark session | `local[*]` via `pip install pyspark` | GlueContext creates session |
| Staging database | Local CSV files in `staging_data/` (exported from Excel) | Glue Data Catalog / S3 / JDBC |
| Template storage | Local `templates/` directory | S3 bucket with versioning |
| Intermediate storage | In-memory DataFrames (no checkpoint) | S3 Parquet checkpoint between validation and transformation |
| Output write method | `.toPandas()` → file write (small data OK) | Spark-native `.write.text()` directly to S3 (no driver memory) |
| Error record store | Local Parquet in `output/errors/` | DynamoDB or RDS |
| Dependency graph | Local Parquet file | DynamoDB or S3 |
| Output delivery | Local filesystem write | S3 upload, REST API POST |
| Run trigger | CLI | EventBridge / Step Functions |
| Audit trail | Local JSON file | CloudWatch Logs + S3 |

---

*Steering file version: Option B*
*Owner: Architecture Team*
*Last updated: July 2026*
