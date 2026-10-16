---
inclusion: always
---

# Business Validation Rules — Contract (CNT) Section

This steering document defines how validation rules are structured, loaded, and applied in the Policy Loader ETL Validation system. Follow these rules exactly when generating or modifying validation logic.

> **Option B Note:** Under the Option B architecture, ALL rules documented in this file are loaded from versioned template CSVs at runtime — field-level rules from `templates/v<N>/validation_rules.csv` and cross-reference/conditional rules from `templates/v<N>/cross_references.csv`. Those CSVs are generated from the single master workbook `rules/Validation_Rules_Master.xlsx` by `scripts/generate_config_from_master.py`. Rules are NOT coded in Python — the engine interprets them as PySpark DataFrame expressions. The master workbook is the **authoritative source the BA maintains**; this file is the business reference. The engine code itself contains no hardcoded field names or business rules.

> **Severity source of truth:** Severity levels are defined in this file per field and per table. Under Option B, they are specified in the `severity` column of the template CSV. The engine uses the template-specified severity and does not infer or override severity levels. This file remains the authoritative business reference.

## Key Constraints

- Rules are data-driven: loaded from versioned template CSVs at runtime. Never hardcode rules in Python.
- The engine is table-agnostic. It receives compiled rule expressions and DataFrames — no section-specific logic in the engine code.
- Business analysts own rule definitions. Changes to fields, severities, or allowed values happen in this document and in the template CSV — not in code.
- The "CNT" prefix denotes the Contract section. CNT, CVG, ROL, and ADD are staging database tables validated by the engine.

## Rule Types and Template Mappings

Each rule type maps to a handler in the engine's `rule_compiler.py`. The template `rule_type` column references these registered types. Field-level types are registered in `RULE_HANDLER_REGISTRY`; cross-reference types in `CROSS_REFERENCE_HANDLER_REGISTRY` / `CROSS_REFERENCE_JOIN_TYPES`. The full authoritative list lives in `schema_definitions.py`; to add a type see `docs/EXTENDING_THE_ENGINE.md`.

**Field-level rule types** (`validation_rules.csv`):

| Template `rule_type` | Checks |
|---|---|
| `not_blank` | Not empty/whitespace |
| `exact_length` | Exactly `param_1` chars |
| `max_length` | At most `param_1` chars |
| `exact_length_or_blank` | Exactly `param_1` chars, or blank |
| `allowed_values` | Value in allowed list |
| `allowed_blank` | Declares blank is allowed for the field (optionality; never fails on its own) |
| `valid_date` | Parses as a date |
| `numeric` | Digits only (as number) |
| `numeric_string` | Digits only, kept as text (leading zeros preserved) |
| `numeric_decimal` | Numeric with decimal; length + precision |
| `numeric_range` | Numeric within `[param_1, param_2]` |
| `min_value` | Numeric ≥ `param_1` |
| `project_defined_value` | Any value up to `param_1` chars; blank OK |
| `conditional` | Value gated by a precondition |
| `conditional_null` / `conditional_blank` | Must be blank when a precondition holds |
| `cross_field_conditional` | If precondition, target in allowed set (or blank) |
| `default_then_warn` | Blank is defaulted downstream; emits WARNING |
| `date_greater_than` / `date_lte` | Date comparisons |
| `numeric_min` / `numeric_max` | Numeric bounds |

**Cross-reference rule types** (`cross_references.csv`):

| Template `rule_type` | Checks |
|---|---|
| `required` | Target must not be blank (optionally gated) |
| `value_compare` | Compare target to a literal via an operator |
| `field_compare` | Compare target to another field in the record |
| `date_greater_than` | Target date > compare date |
| `date_less_than_equal` | Target date ≤ compare date |
| `cross_table_match` | Target equals a field in another table (via join) |
| `occurrence_check` | Target key exists in another table (via join) |
| `cross_reference_exists` | Referential-integrity existence check |
| `conditional` | If precondition, target satisfies expected result |

### Rule Type Notes

**exact_length** — field must be exactly N characters. Blank values fail this check (they are not skipped). Severity is set per the BA rule definition for that field.

**default_then_warn** — the only rule type that writes a value into the dataframe before output. The defaulted value flows into all output files as enriched data. The WARNING entry in the error log serves as the audit trail. Any new field requiring this behaviour must be explicitly approved by the BA and documented in this file before being added to the template.

## Severity Assignment

Severity is an **explicit `Severity` column** in the master workbook (`SEVERE` or
`WARNING`), authored by the data engineers and carried verbatim into the template
CSVs. It is not inferred from prose. The historical mapping below documents how
the business language corresponds to severity, for authors deciding what to enter:

| Business intent | Severity |
|---|---|
| "send severe message" / must not be blank | `SEVERE` |
| "send warning message" | `WARNING` |
| "default to X if blank, send warning" | `default_then_warn`, then `WARNING` |
| Rule present but no severity stated | `WARNING` (safe default) |

## Row Classification

After all validations, assign `ROW_SEVERITY` per record:

- `CLEAN` — all `VAL_` columns are `None`
- `WARNING` — at least one WARNING, no SEVERE
- `SEVERE` — at least one SEVERE (SEVERE always wins over WARNING)

Records classified as SEVERE are excluded from transformation and output. CLEAN and WARNING records proceed to transformation.

## CNT Section — Field Validation Rules

**Data source:** Loaded from `templates/v<N>/validation_rules.csv` where `target_table = CNT`
**BA reference sheet:** the `Contract` tab of `rules/Validation_Rules_Master.xlsx` (authoritative source). `scripts/generate_config_from_master.py` produces the template CSVs from it; the current `templates/v1/*.csv` are generated from this workbook.
**Field prefix:** `CNT_`
**Unique key:** `CNT_COMPANY_CODE` + `CNT_POLICY_NUMBER` + `CNT_ISSUE_SYSTEM` + `CNT_PRODUCT_TYPE`
**Section-level rule:** Contract section is always required. If `CNT_COMPANY_CODE` is missing or blank, the entire row is SEVERE.

### Field Rules

| Field | Type | Rule | Severity |
|---|---|---|---|
| CNT_ISSUE_SYSTEM | CHAR(2) | Not blank, exactly 2 chars | SEVERE |
| CNT_COMPANY_CODE | CHAR(3) | Not blank, exactly 3 chars | SEVERE |
| CNT_POLICY_NUMBER | CHAR(15) | Not blank, up to 15 chars | SEVERE |
| CNT_PRODUCT_TYPE | CHAR(1) | Not blank; allowed: A W B T K L I U V E J Z H D | SEVERE |
| CNT_POLICY_PLAN_CODE | CHAR(10) | Not blank, exactly 10 chars | SEVERE |
| CNT_BASE_PLAN_CODE | CHAR(10) | Default to CNT_POLICY_PLAN_CODE if blank, then WARNING | WARNING |
| CNT_POLICY_CODE | CHAR(1) | Allowed: X A C I O P S 5 J M B Z D | WARNING |
| CNT_ISSUE_COUNTRY | CHAR(2) | Allowed: 01 02 03 US CA | WARNING |
| CNT_ISSUE_STATE | CHAR(2) | Not blank, exactly 2 chars | SEVERE |
| CNT_RESIDENT_STATE | CHAR(2) | Not blank, exactly 2 chars | SEVERE |
| CNT_POLICY_STATUS | CHAR(2) | Allowed: 00 01 02 03 04 05 06 07 08 09 10 21 22 23 24 25 31 32 33 34 35 97 90 99 | WARNING |
| CNT_ISSUE_AGE | INT(3) | Not blank, numeric | SEVERE |
| CNT_ISSUE_DATE | DATE(8) | Valid YYYYMMDD | SEVERE |
| CNT_STATUS_DATE | DATE(8) | Valid YYYYMMDD if present | WARNING |
| CNT_MATURE_EXPIRE_DATE | DATE(8) | Valid date AND > CNT_ISSUE_DATE | SEVERE |
| CNT_APPLICATION_DATE | DATE(8) | Valid date AND <= CNT_ISSUE_DATE | SEVERE |
| CNT_PARTICIPATION_STATUS | CHAR(1) | Allowed: P N | WARNING |
| CNT_GUAR_PAR_STATUS | CHAR(1) | Allowed: N C E O | WARNING |
| CNT_NFO_OPTION | CHAR(1) | Allowed: A E R O N L T S U P | WARNING |
| CNT_SEX_CODE | CHAR(1) | Allowed: 1 M 2 F 3 B J N E | SEVERE |
| CNT_JOINT_LIFE_INDICATOR | CHAR(1) | Allowed: F J N | SEVERE |
| CNT_JOINT_NUMBER_OF_LIVES | CHAR(1) | Must be >= 1 | WARNING |
| CNT_JOINT_RATE_AGE | INT(3) | Must be 0 if JOINT_LIFE_INDICATOR = F or N | SEVERE |
| CNT_JOINT_RATE_AGE_REASON_CODE | CHAR(1) | Conditional on JOINT_LIFE_INDICATOR (see cross-field rules) | SEVERE |
| CNT_PAYUP_DATE | DATE(8) | Valid date AND <= CNT_MATURE_EXPIRE_DATE | SEVERE |
| CNT_QUALIFICATION_CODE | CHAR(1) | Allowed: N Q O K S H I T P R D Z A E U C | SEVERE |
| CNT_PLAN_OPTION_ORIGINAL | CHAR(1) | Allowed: L V R C or blank; must be blank if PRODUCT_TYPE in A W B H | SEVERE |
| CNT_GRACE_EXPIRY_DATE | DATE(8) | Blank if PRODUCT_TYPE in W B H; else valid date | SEVERE |
| CNT_SERV_AGENT | CHAR(12) | WARNING if blank | WARNING |
| CNT_SERV_AGENCY | CHAR(12) | WARNING if blank | WARNING |
| CNT_PHONE_AUTH_TRNSFR | CHAR(1) | Allowed: Y N | WARNING |
| CNT_REINS_TYPE | CHAR(1) | Allowed: A F or blank | SEVERE |

### Cross-Field Rules

Apply these after all individual field validations complete. Each compares two fields within the same row. In the template, these are expressed as `conditional` rule_type entries with precondition fields and dependent checks.

| Condition | Expected | Severity |
|---|---|---|
| CNT_SEX_CODE = B | CNT_JOINT_LIFE_INDICATOR = F | SEVERE |
| CNT_SEX_CODE = J | CNT_JOINT_LIFE_INDICATOR = J | SEVERE |
| CNT_PRODUCT_TYPE in K J Z | CNT_JOINT_LIFE_INDICATOR in F J | SEVERE |
| CNT_PRODUCT_TYPE = E | CNT_JOINT_LIFE_INDICATOR in F J N | SEVERE |
| CNT_JOINT_NUMBER_OF_LIVES = 1 | CNT_JOINT_RATE_AGE_REASON_CODE = G | WARNING |
| CNT_JOINT_LIFE_INDICATOR in F N | CNT_JOINT_RATE_AGE = 0 | SEVERE |
| CNT_JOINT_LIFE_INDICATOR = N | CNT_JOINT_RATE_AGE_REASON_CODE = blank | SEVERE |
| CNT_JOINT_LIFE_INDICATOR = F | CNT_JOINT_RATE_AGE_REASON_CODE in F G P | SEVERE |
| CNT_JOINT_LIFE_INDICATOR = J | CNT_JOINT_RATE_AGE_REASON_CODE in A B C D | SEVERE |
| CNT_MATURE_EXPIRE_DATE | > CNT_ISSUE_DATE | SEVERE |
| CNT_APPLICATION_DATE | <= CNT_ISSUE_DATE | SEVERE |
| CNT_PAYUP_DATE | <= CNT_MATURE_EXPIRE_DATE | SEVERE |
| CNT_QUALIFICATION_CODE in Q K I T P R U | CNT_PRODUCT_TYPE in A W B | SEVERE |
| CNT_PRODUCT_TYPE not in T K L D | CNT_PARTICIPATION_STATUS = N | WARNING |
| CNT_PRODUCT_TYPE in A W B H | CNT_PLAN_OPTION_ORIGINAL = blank | SEVERE |
| CNT_PRODUCT_TYPE in W B H | CNT_GRACE_EXPIRY_DATE = blank | SEVERE |

---

## Cross-Reference (Cross-Table) Validation Rules

Under Option B, cross-reference rules live in their own template,
`cross_references.csv` (authored on the `Cross_References` tab of the master
workbook), separate from field-level `validation_rules.csv`. Join-based types are
implemented as **PySpark DataFrame joins** against other staging tables;
single-record types compile to a Column like field-level rules.

### Template Definition Format

In `cross_references.csv`, each rule uses:

| Column | Purpose | Example |
|---|---|---|
| `xref_id` | Unique id (also the VAL_ column suffix) | `XR_ADD_002` |
| `table_name` | The table being validated (code) | `ADD` |
| `target_field` | The field being checked | `ADD_COMPANY_CODE` |
| `rule_type` | Cross-reference rule type | `cross_table_match` |
| `severity` | `SEVERE` or `WARNING` | `SEVERE` |
| `compare_table` / `compare_field` | Other table + field to match | `CNT` / `CNT_COMPANY_CODE` |
| `join_child_fields` / `join_parent_fields` | Pipe-delimited join keys (same order) | `ADD_COMPANY_CODE\|ADD_POLICY_NUMBER` |
| `precondition_field/_operator/_value` | Optional gate | — |
| `expected_result` | Condition the target must satisfy | — |
| `error_message` | Message on failure | `ADD_COMPANY_CODE must equal CNT_COMPANY_CODE.` |
| `active` | `Y`/`N` (`N` = carried but not evaluated) | `Y` |

Simple referential-integrity (`cross_reference_exists`) can also fall back to the
compound join keys declared in `table_dependencies.csv`.

### Current Cross-Reference Rules

| Child Table | Child Field | Parent Table | Parent Field | Severity |
|---|---|---|---|---|
| CVG | CVG_COMPANY_CODE + CVG_POLICY_NUMBER | CNT | CNT_COMPANY_CODE + CNT_POLICY_NUMBER | SEVERE |
| ROL | ROL_CNT_ID | CNT | CNT_POLICY_NUMBER | SEVERE |
| ADD | ADD_CNT_ID | CNT | CNT_POLICY_NUMBER | SEVERE |
| CVG | CVG_REINS_TYPE | CNT | CNT_REINS_TYPE (value match) | SEVERE |

### Error Reporting for Cross-Reference Failures

When a cross-reference check fails, the Error_Record includes:
- `referenced_table`: the parent table name
- `referenced_field`: the parent field that was looked up
- `referenced_value`: the value that was not found

This allows BAs to identify the missing reference from the error dashboard without developer assistance.

---

## Conditional (If-Then) Rule Handling in Template

Under Option B, conditional rules are defined declaratively using precondition columns — simple field-level conditionals in `validation_rules.csv`, and cross-table/conditional rules in `cross_references.csv`. The engine evaluates preconditions first — if false, the dependent check is skipped entirely (no error generated).

> Some conditional rules describe multi-record or aggregate logic (e.g. "at least
> two coverage occurrences of type TERM"). These are preserved in
> `cross_references.csv` but only the single-record shapes are evaluated by the
> engine today; the reconciliation report lists any carried-but-not-evaluated
> rows. Adding evaluation is an engine extension (see `docs/EXTENDING_THE_ENGINE.md`).

### Template Columns for Conditional Rules

| Column | Purpose | Example |
|---|---|---|
| `precondition_field` | Field to evaluate in the precondition | `CNT_PRODUCT_TYPE` |
| `precondition_operator` | Operator: `eq`, `neq`, `in`, `not_in`, `blank`, `not_blank` | `in` |
| `precondition_value` | Value(s) for precondition, pipe-delimited for lists | `K\|J\|Z` |
| `rule_type` | The dependent check type (any supported type) | `allowed_values` |
| `target_field` | The field the dependent check applies to | `CNT_JOINT_LIFE_INDICATOR` |
| `allowed_values` | Parameters for the dependent check | `F\|J` |

### Evaluation Logic

1. **Precondition evaluates to FALSE** → Skip the dependent check. `VAL_<field>` = None. No Error_Record generated.
2. **Precondition evaluates to TRUE and dependent check PASSES** → `VAL_<field>` = None.
3. **Precondition evaluates to TRUE and dependent check FAILS** → `VAL_<field>` = severity-prefixed error message. Error_Record includes both the precondition expression and the failure detail.

### Example

Template row:
```
rule_id: CNT_XFIELD_003
target_table: CNT
target_field: CNT_JOINT_LIFE_INDICATOR
rule_type: allowed_values
severity: SEVERE
allowed_values: F|J
precondition_field: CNT_PRODUCT_TYPE
precondition_operator: in
precondition_value: K|J|Z
description: If PRODUCT_TYPE in K,J,Z then JOINT_LIFE_INDICATOR must be F or J
```

---

## VAL_ Column Convention

Every validated field produces a result column: `VAL_<FIELD_NAME>`.
- `None` = passed validation.
- Non-None = validation message prefixed with `SEVERE:` or `WARNING:`.

Example: `CNT_ISSUE_SYSTEM` → `VAL_CNT_ISSUE_SYSTEM`

## Extensibility — Adding New Sections

When adding a new section (e.g., PRM for Phase 2):

1. Add a tab to `rules/Validation_Rules_Master.xlsx` for the new table's field rules, and its cross-table/conditional rules on the `Cross_References` tab. Regenerate with `scripts/generate_config_from_master.py`.
2. Add the table's parent/child entry to `TABLE_DEPENDENCIES` in the adapter (emitted to `table_dependencies.csv`).
3. The same engine and rule types apply without code modification.
4. Add a new field-rules section to this steering file for that section's fields (documentation).
5. No new Python modules or code changes are needed for standard rule types.
