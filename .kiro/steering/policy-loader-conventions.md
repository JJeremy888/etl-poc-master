# Steering: Policy Loader Conventions
## Policy Loader ETL — Shared Team Standards

---

## Purpose of This File

This file defines the short, shared conventions that all team members and all steering files refer to. It is the single source of truth for naming, formatting, and structural standards.

All team members own this file. Changes require agreement from the full team.

---

## 1. Field Prefix Conventions

Every table has a 3-letter prefix used on all field names and output files.

| Table | Prefix | Example Field |
|---|---|---|
| Contract | CNT_ | CNT_POLICY_NUMBER |
| Coverage | CVG_ | CVG_REINS_TYPE |
| Role | ROL_ | ROL_CNT_ID |
| Address | ADD_ | ADD_CNT_ID |
| Premium Billing | PRM_ | PRM_MODE_PREMIUM |
| Financial History | FIN_ | FIN_TRANS_CODE |
| Non-Financial History | NFN_ | NFN_TRX_CODE |

---

## 2. Validation Result Column Naming

Every validated field gets a result column named `VAL_` followed by the exact field name.

```
CNT_ISSUE_SYSTEM   →   VAL_CNT_ISSUE_SYSTEM
CNT_PRODUCT_TYPE   →   VAL_CNT_PRODUCT_TYPE
CNT_ISSUE_DATE     →   VAL_CNT_ISSUE_DATE
```

A `None` value in a VAL_ column means the field passed. Any other value is the failure message.

---

## 3. Severity Message Format

Every validation message must begin with the severity level followed by a colon and a space.

```
SEVERE: Must not be blank
SEVERE: Must be exactly 2 characters
SEVERE: Invalid date format — expected YYYYMMDD
WARNING: Blank servicing agent — please review
WARNING: Defaulted CNT_BASE_PLAN_CODE to CNT_POLICY_PLAN_CODE
```

Messages must never start with lowercase. They must never omit the severity prefix.

---

## 4. Row Severity Values

The `ROW_SEVERITY` column uses exactly these three values — no variations, no lowercase.

```
CLEAN
WARNING
SEVERE
```

---

## 5. Date Format Standard

All date fields are stored and validated as 8-character strings in `YYYYMMDD` format.

```
Valid:   20260101
Valid:   19991231
Invalid: 01/01/2026
Invalid: 2026-01-01
```

Convert to datetime only for comparison operations. Store and write back as the original string.

---

## 6. Primary Keys

| Table | Primary Key Fields |
|---|---|
| CNT | CNT_COMPANY_CODE + CNT_POLICY_NUMBER |
| CVG | CVG_COMPANY_CODE + CVG_POLICY_NUMBER + CVG_PLAN_CODE |
| ROL | ROL_COMPANY_CODE + ROL_POLICY_NUMBER + ROL_PERSON_CODE |
| ADD | ADD_COMPANY_CODE + ADD_POLICY_NUMBER + ADD_ADDRESS_TYPE |
| PRM | PRM_COMPANY_CODE + PRM_POLICY_NUMBER + PRM_PARENT_TABLE_ID + PRM_PARENT_SEQ_NUM + PRM_VALUES_FROM |
| FIN | FIN_COMPANY_CODE + FIN_POLICY_NUMBER + FIN_RECORD_COUNTER |
| NFN | NFN_COMPANY_CODE + NFN_POLICY_NUMBER + NFN_SEQUENCE_NUMBER |

---

## 7. Output File Naming

Output files follow a consistent pattern: `<prefix>_<severity>.csv`

```
cnt_clean.csv
cnt_warning.csv
cnt_severe.csv
cnt_summary.txt
```

All output files are written to the `output/` directory, which is created at runtime if it does not exist.

### Transformation Output Files

The transformation phase produces additional output files:

```
ea_transaction.txt              ← Fixed-width positional flat file (no delimiters)
transformed_dataframe.csv       ← Intermediate columnar CSV (target fields as headers)
transformation_audit_log.csv    ← Per-field audit trail (SUCCESS/SKIPPED/ERROR per field)
```

These files are written to the same `output/` directory as validation outputs.

---

## 8. Rules File Location

Under Option B, the engine reads validation and transformation rules from the **Template directory**:

```
templates/v<N>/validation_rules.csv       ← Field-level validation rules for all tables
templates/v<N>/cross_references.csv        ← Cross-reference / conditional rules
templates/v<N>/transformation_mappings.csv ← Source→target field mappings
templates/v<N>/output_config.csv          ← Output adapter configuration
templates/v<N>/table_dependencies.csv     ← Parent/child dependency declarations
```

The template version directory (`v1`, `v2`, etc.) is the single runtime source. The engine reads ONLY these template files.

### BA Rule Sheet (Authoritative Source)

Validation rules are authored in one workbook that BAs own and maintain:

```
rules/Validation_Rules_Master.xlsx   ← 5 tabs: Contract, Address, Roles, Coverage, Cross_References
```

The engine does not read the workbook directly. The input adapter
`scripts/generate_config_from_master.py` mechanically produces the template CSVs
(`validation_rules.csv`, `cross_references.csv`, `table_dependencies.csv`) plus a
`_reconciliation_report.txt`. BAs own the Excel content; the adapter produces the
runtime config. Authoring instructions: `rules/RULES_TEMPLATE_GUIDE.md`.
Transformation mappings come from `rules/EA_Transaction_Mapping.xlsx` via
`scripts/generate_transformation_mappings.py`.

### Transformation Mapping

Transformation metadata lives in:

```
templates/v<N>/transformation_mappings.csv
```

This is the single authoritative source for all transformation logic — no source-to-target field mappings are hardcoded in Python.

---

## 8a. Table Inventory and Validation Pattern

All tables use a unified, config-driven validation pattern. All rules (field-level, cross-field, and cross-table) are defined in the template and interpreted by the engine's `rule_compiler.py`. No table-specific Python modules exist in Option B.

| Table | Staging Source | Field Rules | Cross-Reference |
|---|---|---|---|
| CNT (Contract) | `staging_data/cnt.csv` | Defined in template `validation_rules.csv` | Parent table — no cross-ref needed |
| CVG (Coverage) | `staging_data/cvg.csv` | Defined in template `validation_rules.csv` | References CNT (compound key) |
| ROL (Role) | `staging_data/rol.csv` | Defined in template `validation_rules.csv` | References CNT |
| ADD (Address) | `staging_data/add.csv` | Defined in template `validation_rules.csv` | References CNT |

**CNT is the parent table.** CNT must always be validated first (enforced by topological sort of `table_dependencies.csv`). All other tables perform cross-reference checks against the CNT DataFrame via PySpark joins.

**Transformation flow:** After validation, eligible records (CLEAN + WARNING) from all four tables are passed to the transformation executor. The transformation executor joins child tables to CNT as specified by the template and produces the EA Transaction positional flat file.

---

## 8b. Adding a New Table

Under Option B, adding a new table requires **no code changes**:

1. **Add validation rules:** Add a tab to `rules/Validation_Rules_Master.xlsx` for the new table's field rules, and add cross-table/conditional rules to its `Cross_References` tab. Regenerate with `scripts/generate_config_from_master.py` (produces `validation_rules.csv` and `cross_references.csv`).
2. **Declare dependencies:** Add the table's parent/child entry to `TABLE_DEPENDENCIES` in the adapter (emitted to `templates/v<N>/table_dependencies.csv`).
3. **Add transformation mappings:** Insert rows into `templates/v<N>/transformation_mappings.csv` if the new table contributes to output.
4. **Provide staging data:** Place the staging file (Parquet or CSV) in `staging_data/` (POC) or configure the Glue Catalog entry (production).
5. **Bump template version:** Create a new version directory (`v<N+1>`) or update the existing version and record in `versions.json`.

No changes to `rule_compiler.py`, `validation_orchestrator.py`, `transformation_executor.py`, `flat_file_adapter.py`, or any other engine module are needed.

---

## 9. Technology Stack

| Item | Choice |
|---|---|
| Language | Python 3.12+ |
| Processing engine | PySpark (local standalone for POC) |
| Staging database | Local Parquet/CSV files simulating staging DB (POC) |
| Template format | Versioned CSV files with fixed schemas |
| Testing | pytest + Hypothesis (property-based) |
| POC execution | Local PySpark (`pip install pyspark`) |
| Production execution | AWS Glue (managed Spark) |
| Property testing | Hypothesis with PySpark DataFrames |

---

## 10. What Validation Does NOT Do

- Validation reads FROM the staging database; it does not modify staging records directly
- Validation does not perform structural scanning (file-level checks are upstream)
- Validation does not generate code from rules — it interprets rules at runtime
- Validation does not delete or quarantine records — it classifies and reports only
- Validation does not invoke AI/LLM/ML models at runtime
- Validation does not modify the original staging data

---

*Steering file version: Option B*
*Owner: Whole Team*
*Last updated: July 2026*
