# Policy Loader — Architecture Decision Record

**Version:** 1.0
**Date:** 2026-08-18
**Status:** Living Document
**Authors:** Vidhya Venugopal, Architecture Review Team

---

## 1. Project Context & Problem Statement

DXC executes large-scale data conversion projects that move customer data from legacy policy administration systems to modern platforms. These conversions involve hundreds of thousands of active contracts and millions of history records.

**The Problem:**

The existing ETL tooling (KNIME) was proving inadequate:
- Too slow for production-scale data volumes
- Too rigid — drag-and-drop node editing doesn't scale to hundreds of fields
- No version control (proprietary format, not Git-friendly)
- Requires commercial license
- Cannot be deployed to cloud environments (AWS) without significant rework
- Not readable or maintainable by team members unfamiliar with KNIME

**The Goal:**

Replace KNIME with a lightweight, Python-based ETL validation and transformation pipeline that is:
- Fast (handle 100K+ records in minutes)
- Git-versioned (full change history)
- Extensible (new tables and rules without architecture changes)
- Portable (runs anywhere Python exists — local, Lambda, Glue)
- No licence cost (open-source only)
- Understandable by any team member

---

## 2. POC Scope Decision

The full staging data model contains 20 business tables. The architect recommended scoping the POC to 4 tables:

| Table | Role | Why Selected |
|-------|------|--------------|
| CNT (Contract) | Parent table | Primary key holder, all other tables reference it |
| CVG (Coverage) | Child of CNT | Proves one-to-many relationships, cross-table validation |
| ROL (Roles) | Child of CNT | Multiple occurrences (insured, owner, payor, beneficiary) |
| ADD (Address) | Child of ROL | Multi-level join (ADD → ROL → CNT), address type filtering |

**Why these 4 prove the full pattern:**
- Parent-child cross-reference validation (CVG/ROL/ADD must reference valid CNT)
- Multiple occurrences handling (multiple roles per policy, multiple addresses per role)
- Conditional validation (rules that depend on other field values)
- Full transformation pipeline (staging → EA flat file output)
- The remaining 16 tables (PRM, FIN, NFN, LON, BNF, PIT, etc.) follow the identical pattern — no new architectural unknowns

---

## 3. Option A → Option B Evolution

### Option A: Pandas + Lambda Per Table (Deprecated)

**Architecture:**
- One Python validation module per table (`validate_cnt.py`, `validate_cvg.py`, etc.)
- One function per field (hardcoded validation logic)
- Each module independently deployable as an AWS Lambda function
- Pandas DataFrames for data manipulation
- Rules read from Excel at startup but logic hardcoded in Python

**Location in codebase:** `_deprecated_src_do_not_use/`

**What worked:**
- Proved the validation logic was correct
- Fast development for a single table
- Simple to understand (one function = one field)

**What failed:**
- Hardcoded rules: adding a new rule or changing severity required code changes
- Not BA-editable: BAs couldn't adjust validation without developer involvement
- Lambda-per-table: operational overhead (4 Lambdas now, 20 eventually, each with deployment pipeline)
- Code duplication: same patterns repeated across tables (classify_severity, split_results, etc.)
- Scaling concern: millions of records on Lambda (memory limits, timeout limits)
- No config-driven extensibility: every new table = new Python module from scratch

### Option B: Config-Driven PySpark Interpreter Engine (Current)

**Architecture:**
- Single fixed PySpark engine that reads ALL rules from versioned template CSV files
- No code generated — engine translates declarative templates into PySpark Column expressions at runtime
- Same code runs locally (POC) and on AWS Glue (production)
- Pluggable output adapters for different delivery formats

**Location in codebase:** `option_b/`

**Why Option B was chosen:**

| Criteria | Option A | Option B |
|----------|----------|----------|
| Adding a new rule | Code change + test + deploy | Edit CSV template |
| Adding a new table | New Python module (~500 lines) | Add rows to existing templates |
| BA can edit rules? | No | Yes (template CSVs) |
| Same code local + cloud? | Partially (Lambda vs local differ) | Yes (PySpark everywhere) |
| Handles millions of records? | Lambda memory limits | Spark distributed processing |
| Deterministic & auditable? | Yes but scattered across files | Yes, centralized in templates |
| Version control of rules? | Rules embedded in code | Templates are separate, versioned files |

**Key Design Decisions in Option B:**

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Processing engine | PySpark | Set-based parallelism; same code local + cluster |
| Rule storage | Versioned CSV templates | BA-editable, version-controlled, no code changes |
| Architecture pattern | Pure interpreter (no code generation) | Deterministic, auditable, single codebase |
| Output delivery | Pluggable adapter pattern | New formats added without touching core engine |

---

## 4. AI Usage Strategy

### AI During Development (YES)

AI (Kiro IDE) is used as a development accelerator:
- Architecture design and decision support
- Code generation (engine modules, test cases)
- Rule parsing from Nancy's Excel spreadsheets
- Template creation and documentation
- Spec authoring (requirements → design → tasks workflow)
- Code review and optimization suggestions

### AI At Runtime (NO)

The validation/transformation engine does NOT call any LLM or AI service during execution.

**Why no runtime AI:**

| Concern | Impact |
|---------|--------|
| Cost at scale | 100K+ records × cost per API call = significant operational expense |
| Determinism | LLMs are non-deterministic — same input may produce different output. Conversion requires reproducibility. |
| Auditability | "Why was this record flagged SEVERE?" must have a traceable answer (rule X, template version Y). LLM decisions are not explainable. |
| Latency | API calls add seconds per record. Batch processing needs millisecond-per-record throughput. |
| Internet dependency | Production pipeline cannot depend on external API availability |
| Compliance | Insurance data conversion may require regulatory proof of deterministic processing |

**The engine is purely deterministic:** Template rules + input data → predictable, reproducible, explainable result. Every single time.

---

## 5. Source Documents & Their Problems

### The Original DB2 Spreadsheets (DB_Section_*.xlsx) — historical

> **Status:** Superseded. These per-tab spreadsheets were the original source of
> truth. They have been consolidated into a single structured workbook,
> `rules/Validation_Rules_Master.xlsx` (see §13). The problems catalogued below
> are the *motivation* for that change and are retained for historical context.

**Role (original):** Authoritative source of truth for all field definitions, validation rules, allowable values, and cross-references across the 20 staging tables.

**Contents per table tab:**
- Field Name (Column A)
- Data Type, Length, Precision
- Edits/Validation rules
- Allowable Values
- Allowable Values Description
- Nancy Comments Including Cross References
- Definition

**Problems for automated consumption:**

| Problem | Example | Impact |
|---------|---------|--------|
| Strikethrough = inactive | Coverage fields crossed out but still in sheet | Parser can't detect Excel formatting |
| Different column layout per table | Roles tab missing Definition column, has duplicate headers | Parser needs per-table logic |
| Codes mixed with descriptions | "A:Automatic F:Facultative Blank: No reinsurance" | Parser must separate codes from prose |
| Severity in prose | "send severe message" / "send warning message" | Parser must interpret natural language |
| Numeric rules in allowable column | ">= 1 (Note: If 1st to die setup...)" | Misclassified as code list |
| Hidden legacy columns | Old WMA-specific allowables (bogus values) | Confusing — Nancy confirmed "IT IS BOGUS" |
| Cross-references in free text | Complex IF/THEN logic in one cell | Multiple rules embedded in single cell |
| Width rules mixed with validation | "Must be exactly 30 characters" (output width, not input validation) | Applied at wrong stage |

### Quinn's EA Transaction Mapping (CIUATEA1_EA_Trx_Mapping.xlsx)

**Role:** Defines how staging fields map to COBOL transaction output fields (positions, lengths, types, transformation logic).

**Problems for automated consumption:**

| Problem | Example | Impact |
|---------|---------|--------|
| COBOL level numbers in field names | "05 COMPANY-CODE" | Must strip level number to get field name |
| Scratch notes in Sheet1 | Random working notes | Must be excluded from generation |
| Ambiguous conditional logic | Free-text transformation descriptions | Cannot always determine exact rule |
| Missing filter criteria | "Use CVG_PLAN_CODE" but doesn't say WHICH CVG record | Engine grabbed wrong records |
| Packed decimal unclear | COMP-3 fields — how to represent in output? | Required implementation research |
| Multi-source fields | "CNT_REINS_TYPE ; CVG_REINS_TYPE" | Compound source with semicolon separator |

---

## 6. Engine Architecture (How It Works)

### Input Adapter (Rules → Templates)

```
rules/Validation_Rules_Master.xlsx  (validation rules — 5 tabs)
rules/EA_Transaction_Mapping.xlsx   (transformation mappings)
        │
        ▼
Input Adapters:
  scripts/generate_config_from_master.py       (validation + cross-references)
  scripts/generate_transformation_mappings.py  (transformation mappings)
  • Read explicit, structured columns (Rule Type / Severity / Allowable Codes ...)
  • NO prose parsing, NO rule-type guessing, NO override list
  • Emit a reconciliation report flagging anything unrecognized
        │
        ▼
templates/v1/
  • validation_rules.csv
  • cross_references.csv
  • transformation_mappings.csv
  • table_dependencies.csv
  • output_config.csv
  • _reconciliation_report.txt
```

**Decision delivered:** The original validation adapter was 500+ lines of regex,
guessing, and confirmed-override patching against Nancy's per-tab sheets. It has
been replaced by `scripts/generate_config_from_master.py`, a deterministic
direct-read of the structured master workbook. Rule type and severity are
authored explicitly by data engineers and read verbatim; the adapter's job is
normalization (tab→table code, split join fields) and reconciliation, not
interpretation. Cross-reference rules now have their own template
(`cross_references.csv`) rather than being squeezed into `validation_rules.csv`.

### Template Layer (Configuration-as-Data)

The engine's behavior is entirely driven by template CSV files:

| Template File | Drives | Content |
|---------------|--------|---------|
| `validation_rules.csv` | What validation checks to perform | rule_id, field, rule_type, severity, params, allowable values |
| `transformation_mappings.csv` | How to map staging → COBOL output | source field, target field, type, length, padding, sequence |
| `table_dependencies.csv` | Processing order and cross-references | parent-child relationships, join keys |
| `output_config.csv` | Where and how to write output | adapter type, delivery mechanism, target path |
| `transaction_filters.csv` (NEW) | Which records to select per transaction | table, filter field, operator, value |

### Core Engine (Fixed Code)

```
option_b/
├── config/
│   └── template_loader.py          → Reads and validates all templates
├── input/
│   └── staging_reader.py           → Reads staging data (CSV/Parquet/JDBC)
├── engine/
│   ├── validation_orchestrator.py  → Topological sort, orchestrates all tables
│   ├── rule_compiler.py            → Template rules → PySpark Column expressions
│   ├── presence_format_rules.py    → not_blank, exact_length, allowed_values, etc.
│   ├── range_rules.py              → date comparisons, numeric ranges
│   ├── cross_reference_rules.py    → Anti-joins for referential integrity
│   ├── severity_classifier.py      → CLEAN / WARNING / SEVERE per record
│   ├── transformation_executor.py  → Applies mappings, joins, produces output
│   └── dependency_graph.py         → Tracks record-level dependencies
├── error/
│   └── error_logger.py             → Persists diagnostic error records
└── output/
    ├── adapter_registry.py         → Selects output adapter by config
    ├── flat_file_adapter.py        → Positional COBOL flat file
    └── csv_file_adapter.py         → BA-facing CSV with headers
```

**Key principle:** Engine code is FIXED. All business logic is in templates. No code changes required for:
- New validation rules
- New transformation mappings
- New output formats
- New tables

### Output Adapter (Pluggable)

```
Validated + Transformed Data
        │
        ▼
Output Adapter Registry (selects by output_config.csv)
        │
        ├── Positional Flat File Adapter
        │     • COBOL-aligned fixed-width records
        │     • Packed decimal / signed fields
        │     • Fields concatenated by sequence order
        │     • System-of-record format for downstream
        │
        └── CSV File Adapter
              • Human-readable with COBOL field names (dashes) as headers
              • BA-facing review deliverable
              • Same data, different format
```

Both outputs produced from a single transformation pass — no duplicate processing.

---

## 7. Medallion Architecture (Bronze/Silver/Gold)

### Why Medallion Was Chosen

The architecture follows the Medallion (Lakehouse) pattern adapted for conversion:

| Layer | Purpose | Data State |
|-------|---------|-----------|
| Bronze | Raw source preservation | As-received, immutable, full fidelity |
| Silver | Validated canonical data | Schema-conformant, quality-classified |
| Gold | Target-system-ready output | COBOL-formatted, consumer-ready |

**Why it fits Policy Loader:**
- Directly answers the "source data arrives in different formats" challenge (Bronze handles any source)
- Provides replay capability (re-validate from Bronze when rules change)
- Clean separation between source-specific and target-specific concerns
- Built-in auditability (trace Gold → Silver → Bronze)
- Aligns with AWS Glue production target (native S3/Parquet/Iceberg support)

**Adaptation for conversion (vs. traditional analytics Medallion):**
- Gold is "target-shaped" not "analytics-aggregated"
- Batch semantics (snapshot per conversion run, not streaming append)
- Quality-filtered at Silver→Gold boundary (SEVERE records excluded)
- Error/quarantine zone within Silver (SEVERE classification, not data loss)

### Layer Implementation

```
┌─────────────────────────────────────────────────────────────────────┐
│                    POLICY LOADER — MEDALLION LAYERS                   │
├──────────────┬──────────────────┬────────────────┬──────────────────┤
│   BRONZE     │      SILVER      │     GOLD       │     CONTROL      │
│   (S3)       │   (Aurora v2)    │     (S3)       │   (Aurora v2)    │
├──────────────┼──────────────────┼────────────────┼──────────────────┤
│ Raw source   │ Canonical schema │ EA flat file   │ Error records    │
│ files as-is  │ Validated        │ EA CSV         │ Dependency graph │
│ Partitioned  │ Severity         │ Future targets │ Audit trail      │
│ by source/   │ classified       │ Versioned      │ Batch metadata   │
│ batch/date   │ BA-queryable SQL │ Delivery-ready │ Template versions│
└──────────────┴──────────────────┴────────────────┴──────────────────┘
```

---

## 8. Permissive Database Schema

### The Core Decision

All business fields in Aurora Silver are stored as `VARCHAR` (text), all nullable. The database NEVER rejects data based on content.

### Why Permissive

```
WITHOUT permissive:  Source → TRY to load → DB REJECTS bad data → Lost forever
WITH permissive:     Source → LOAD everything → Validate AFTER → Classify & report
```

**Benefits:**
- ALL data is visible — BAs can see good and bad records in the same query
- Rich error diagnostics: "field X contains 'ABC', expected numeric" instead of "INSERT failed"
- Targeted revalidation: can fix and re-validate individual records
- No silent data loss: nothing is dropped without explanation
- Rules can change without DB schema changes

### What IS Constrained

| Constraint Type | Where Enforced | Why |
|----------------|----------------|-----|
| Primary key (surrogate SERIAL) | Database | Prevents duplicate records (system integrity) |
| Business unique key (UQ fields) | Database | Dedup by company_code + policy_number + sequence (NOT NULL on UQ fields) |
| Metadata fields (batch_id, timestamps) | Database | System-controlled values must always exist |
| Business field types/lengths/allowables | Validation Engine | Produces meaningful error messages, not DB rejections |
| Cross-references (FK relationships) | Validation Engine | Produces dependency graph and targeted revalidation |

### VARCHAR Sizing Convention

| Original Type | Permissive Type | Rationale |
|---------------|----------------|-----------|
| CHAR(1-2) | VARCHAR(10) | Safety margin for unexpected source data |
| CHAR(3-9) | VARCHAR(20) | |
| CHAR(10-15) | VARCHAR(50) | |
| CHAR(16-50) | VARCHAR(100) | |
| CHAR(51+) | VARCHAR(200) | |
| INT(any) | VARCHAR(20) | "ABC" in integer field gets stored and flagged, not rejected |
| DECIMAL(any) | VARCHAR(30) | |
| DATE(8) | VARCHAR(20) | "20261332" (invalid month) gets stored and flagged |

### Performance Consideration

For the 10% of queries needing typed comparison (e.g., "policies issued after 2020"), options include:
- `CAST` in WHERE clause (fine for ad-hoc)
- Generated columns on specific fields (for frequent typed queries)
- Materialized views (for reporting layer)

For conversion workloads (bulk processing, key lookups, severity filters), permissive VARCHAR has negligible performance impact.

---

## 9. Storage Technology Decisions

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| **Bronze** | Amazon S3 (Parquet) | Cheap, serverless, infinite scale, immutable, native Glue integration |
| **Silver** | Aurora PostgreSQL Serverless v2 | SQL access for BAs, row-level updates for revalidation, already approved, scales to zero when idle |
| **Gold** | Amazon S3 (flat files) | Output delivery artifacts, versioned, triggers downstream via EventBridge |
| **Control** | Aurora PostgreSQL (same instance) | Relational joins with Silver data, SQL access for operations, one instance to manage |

**Cost estimate:** ~$160-420/month for POC/early production workload.

**Aurora schema structure:**
```sql
silver.cnt, silver.cvg, silver.rol, silver.add  -- Business tables (permissive)
control.error_records                            -- Validation failures
control.dependency_links                         -- Cross-reference graph
control.batch_runs                               -- Processing history
control.template_versions                        -- Template registry
```

---

## 10. Data Standardization Decisions

These were resolved through discussions with Nancy (BA/domain expert) and established as platform-wide standards:

| Decision | Standard | Rationale |
|----------|----------|-----------|
| DATE not applicable | BLANK (NULL) | No zeros, no nines, no dummy dates. Blank means "doesn't apply." |
| DATE applicable but missing | SEVERE error | Validation engine flags it with specific diagnostic |
| NUMERIC not applicable | BLANK (NULL) | Distinguishes "doesn't apply" from "value is zero" |
| NUMERIC is genuinely zero | 0 | Zero is a legitimate business value |
| Allowable values scope | Broader than WMA | Staging template designed for multiple target systems |
| Multiple occurrences | Separate rows, same policy_number | Differentiated by sequence number (person_seq, cvg_seq, etc.) |
| Empty/missing tabs | No records created | Absence of record = not applicable (not an error) |
| Field names (staging) | Underscores: CNT_COMPANY_CODE | Nancy's naming convention preserved exactly |
| Field names (COBOL output) | Dashes: COMPANY-CODE | COBOL copybook convention |
| Client source fields | Separate from staging fields | NOT 1:1 mapping — explicit source-to-staging map required |

---

## 11. Source Ingestion Strategy

### Original Assumption
Data arrives as CSV/Excel files, one file per table, pre-structured to match staging schema.

### New Requirement
Additional source: positional flat file from mainframe (not VSAM — already extracted to ASCII fixed-width).

### Architecture Decision: Source Adapter Pattern

```
CSV/Excel ─── csv_adapter ──────┐
                                 ├──► Bronze (S3 Parquet) ──► Silver (Aurora)
Positional ── flatfile_adapter ──┘
flat file     (future)
```

- Each source format has its own adapter implementation
- All adapters produce the same output: per-table data with CCDM field names
- The validation engine is source-agnostic — reads from Silver regardless of source origin
- New source formats require only a new adapter — no changes to validation/transformation

### Positional Flat File Adapter (Future)
- Needs: field position map (or COBOL copybook), sample file, encoding confirmation
- Simpler than VSAM (already ASCII, no packed decimals in source, standard newline-terminated)
- Builds when sample data arrives — architecture is ready now

---

## 12. Transformation Architecture Decisions

### Transaction-Type-Aware Processing

Each COBOL transaction (EA policy add, NA premium payment, rider add, etc.) uses different subsets of staging data with different filters. The transformation engine must be told WHICH records to use for WHICH transaction.

**Problem identified by Nancy:** The POC was pulling ALL coverage records for the EA transaction. The EA base policy should only use CVG_TYPE = TERM, CVG_SEQUENCE_NUMBER = 01.

### Resolution: Transaction Filters in Configuration

**What goes in the mapping configuration (not engine code):**

| Transaction | Table | Filter | Value |
|-------------|-------|--------|-------|
| EA (base) | CVG | CVG_TYPE = TERM, SEQUENCE = 01 | Base policy coverage only |
| EA (base) | ADD | ADD_ADDRESS_TYPE = R | Resident address only |
| EA (base) | ROL | ROL_PERSON_TYPE IN (I, O, P) | Insured, Owner, Payor |
| RIDER | CVG | CVG_SEQUENCE > 01, TYPE ≠ TERM | Non-base coverages |
| BENEFIT | BNF | BNF_PARENT_SEQUENCE = {CVG_SEQUENCE} | Benefits for selected coverage |

**What the engine already handles correctly:**
- ROL filtering by person type (INS/OWN/PAY sections)
- ADD join via ADD_PERSON_SEQUENCE = ROL_PERSON_SEQUENCE
- Role-to-address linking per person

**What needed fixing:**
- CVG type/sequence filter: was in neither mapping sheet nor engine code (engine guessed "first by sequence")
- ADD address type filter: not specified (engine took first address per person)

**Fix approach:** Both are configuration (mapping sheet) problems. Engine gets a small one-time change to read and apply filter criteria from `transaction_filters.csv`. After that, all future transaction types are config-only additions.

### Benefit-to-Coverage Linking

Benefits relate to coverages via:
```
BNF_PARENT_TABLE_ID = 'CVG'
BNF_PARENT_SEQUENCE = CVG_SEQUENCE_NUMBER
```

One coverage can have multiple benefits. Multiple coverages per policy, each with their own benefits. This parent-child chain is defined in the mapping configuration — the engine resolves it at runtime based on which coverage was selected by the transaction filters.

---

## 13. New Rules Template Design

### Why a New Template

The original per-tab spreadsheets worked for human analysts but caused
interpretation errors when consumed by automation. The decision was made to:
1. Keep the analysts' working documents as-is
2. Create one structured master workbook that Data Engineering populates (one-time migration)
3. BAs maintain the master workbook going forward
4. The adapter reads it with zero interpretation needed

### Template Structure (as delivered)

**File:** `rules/Validation_Rules_Master.xlsx`
**Authoring guide:** `rules/RULES_TEMPLATE_GUIDE.md`

**5 tabs:**

| Tab | Content | Who Maintains |
|-----|---------|---------------|
| Contract | Contract (`CNT_*`) fields + validation rules | BA |
| Address | Address (`ADD_*`) fields + validation rules | BA |
| Roles | Roles (`ROL_*`) fields + validation rules | BA |
| Coverage | Coverage (`CVG_*`) fields + validation rules | BA |
| Cross_References | Conditional and cross-table rules | BA |

> Parent/child relationships (the former "Table_Relationships" idea) are held in
> the adapter's `TABLE_DEPENDENCIES` and emitted to `table_dependencies.csv`;
> transaction-filter/selection logic belongs to the transformation phase
> (`EA_Transaction_Mapping.xlsx`), so neither is a tab in this workbook.

**11 columns per table tab:**

| Column | Adapter Reads? | Purpose |
|--------|---------------|---------|
| Field Name | YES | Exact field name (underscores) |
| Data Type | YES | CHAR / INT / NUMERIC / DATE |
| Length | YES | Business-defined length (feeds length-based rule params) |
| Precision | YES | Decimal places (NUMERIC only) |
| Date Format | reference | YYYYMMDD (DATE only) |
| Is Key Field | reference | YES / NO |
| Rule Type | YES | Explicit registered rule type (verbatim) |
| Severity | YES | SEVERE / WARNING |
| Allowable Codes | YES | Comma/pipe-separated codes (A\|W\|B\|T...) |
| Allowable Description | NO | Human context (A:Annuity W:Whole...) |
| Description / Notes | NO | Business definition + BA notes combined |

> Blank/optional behavior is expressed by which rule rows exist for a field
> (e.g. a `not_blank` row) plus `allowed_blank` / `conditional_null` types —
> there is no separate `Nullable` column.

**Key improvements over the original sheets:**
- Same column layout for every table (no per-table variations)
- No hidden columns
- Allowable codes in their own clean column (not mixed with descriptions)
- Rule type explicit (not inferred from prose)
- Severity explicit (not parsed from "send severe message")
- Cross-references in a structured separate tab → separate `cross_references.csv`

### Flow

```
Validation_Rules_Master.xlsx (BA maintains)
        │
        ▼
scripts/generate_config_from_master.py (deterministic direct-read + reconciliation)
        │
        ▼
templates/v1/*.csv (engine reads: validation_rules.csv + cross_references.csv + table_dependencies.csv)
        │
        ▼
Engine validates and transforms
```

---

## 14. Error Handling & Correction Flow

### Processing Flow

```
STEP 1: LOAD (Source → Bronze → Silver)
  • Source file archived in Bronze (S3) as-is
  • Loaded into Aurora Silver (permissive schema)
  • row_severity = NULL (not yet validated)
  • NO validation at this step — just data landing

STEP 2: VALIDATE (Engine reads Silver, classifies)
  • Reads records WHERE row_severity IS NULL
  • Applies all template rules
  • Classifies: CLEAN / WARNING / SEVERE
  • Updates Silver: SET row_severity, validated_at
  • Creates error records in control schema

STEP 3: TRANSFORM (Engine reads CLEAN from Silver, produces Gold)
  • Reads records WHERE row_severity IN ('CLEAN', 'WARNING')
  • Applies transformation mappings
  • Produces EA flat file + CSV → Gold (S3)

STEP 4: CORRECTION CYCLE (if needed)
  • BA reviews SEVERE records (SQL query against Silver)
  • Corrects source data
  • Re-uploads ONLY corrected records (not full file)
  • UPSERT into Silver (replaces bad records, resets severity)
  • Engine revalidates just those records + their dependents
  • Cycle until all CLEAN or intentionally excluded
```

### Error Record Diagnostics

Every validation failure produces a record in `control.error_records` containing:
- batch_run_id, template_version
- table_name, field_name, record_key
- rule_id, rule_type, severity
- failing_value, expected_value
- error_message (human-readable)

### Dependency Graph

Cross-reference validation builds a dependency graph:
- Forward lookup: "If parent record is corrected, which children need revalidation?"
- Backward lookup: "If child failed, which parent does it reference?"
- Staleness detection: template version change → graph invalid → requires full re-run

### Targeted Revalidation

When corrected records are re-uploaded:
1. UPSERT replaces the bad record in Silver
2. Engine identifies affected records via dependency graph
3. Revalidates ONLY: corrected record + dependent children
4. Does NOT revalidate unaffected CLEAN records
5. Audit trail preserved: "record arrived batch_001, was SEVERE, corrected batch_002, now CLEAN"

---

## 15. Open Items & Future Roadmap

### Paused Architecture Review Tasks (3-10)

The strategic architecture review identified 10 tasks. Tasks 1-2 were completed. Tasks 3-10 are paused pending further progress:

| Task | Topic | Status |
|------|-------|--------|
| 3 | Source Ingestion Strategy | Deferred — positional flat file adapter when sample data available |
| 4 | Staging Architecture Evaluation | Resolved — Medallion with permissive Silver |
| 5 | Validation Ownership | Resolved — application layer, not DB |
| 6 | Data Modeling Strategy | Resolved — standardization decisions made |
| 7 | Error Management & Auditability | Resolved — error records + dependency graph |
| 8 | Scalability & Future-State Readiness | Partially addressed — adapter pattern + template extensibility |
| 9 | Architecture Options Assessment | Pending |
| 10 | Final Recommendation | Pending (all prior tasks must complete) |

### Immediate Next Steps

| Item | Action | Owner |
|------|--------|-------|
| Rules Template migration | Data Engineers populate new template from Nancy's sheets | Data Engineering |
| Transaction filters | Add `transaction_filters.csv` to templates, small engine update | Development |
| CVG/ADD filter fix | Update transformation mapping config per Nancy's feedback | Development |
| Nancy's co-owner sample dataset | Awaiting delivery for co-owner EA output mapping | Nancy |
| EA output review with Nancy | Share current output for occurrences validation | Team |

### Phase 2 Deferred Transformations

15 transformation mapping rows are blocked on external inputs:
- JIRA 107: Dummy agent codes (P+ system input needed)
- JIRA 416: Directory ID generation pattern (P+ documentation needed)
- JIRA 403: Originator code value (WiltonRe confirmation needed)
- Rate class translation table (BA team deliverable)
- Co-owner composite fields (Nancy's sample dataset)
- RESTRICTION-CODE decision tree (BA review)
- LINE-OF-BUSINESS-CODE target values (P+ confirmation)

### Future Expansion

| When | What |
|------|------|
| POC proven | Add PRM, FIN, NFN tables to Rules Template (same pattern) |
| Flat file source available | Build positional flat file source adapter |
| Aurora provisioned | Deploy Silver + Control schemas, update staging_reader to JDBC |
| Production | Deploy to AWS Glue, switch to S3/EventBridge triggers |
| Multi-client | Add client-specific scoping to Rules Template (scope column) |
| New target system | Add new transaction types to Transaction_Filters + Transformation_Maps |

---

## Appendix: Key Documents & Locations

| Document | Location | Purpose |
|----------|----------|---------|
| Option B Design Spec | `.kiro/specs/option-b-config-driven-engine/design.md` | Full technical design |
| Requirements | `docs/requirements.md` | Functional/non-functional requirements |
| Cross-Reference Worklist | `docs/cross_reference_rules_worklist.md` | 56 identified cross-ref rules (DRAFT) |
| Phase 2 Deferred Items | `option_b/PHASE2_DEFERRED.md` | 15 blocked transformation mappings |
| Validation Rules Master | `rules/Validation_Rules_Master.xlsx` | Authoritative field + cross-reference rule workbook (5 tabs) |
| Rules Template Guide | `rules/RULES_TEMPLATE_GUIDE.md` | How BAs author the master workbook |
| Mapping Sheet | `rules/EA_Transaction_Mapping.xlsx` | COBOL transaction mapping source |
| Engine Extension Guide | `docs/EXTENDING_THE_ENGINE.md` | How engineers add rule types/handlers |
| Permissive Schema LDM | `docs/Policy_Loader_LDM_v6_Permissive.drawio` | 20-table logical data model |
| Workshop Notes | `docs/workshop-notes/` | Day 1 spec + Day 2 team guide |

---

*This is a living document. Update as decisions are made or revised.*
