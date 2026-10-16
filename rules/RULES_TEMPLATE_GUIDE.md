# Rules Template Guide — `Validation_Rules_Master.xlsx`

This guide explains how to author validation rules in the master workbook so the
input adapter can turn them into the engine's configuration automatically.

**Audience:** Business analysts and data engineers who maintain the rules.
**You do not need to touch any Python code to add or change a rule** — you edit
the workbook, then run one command (or ask an engineer to).

---

## The one file that matters

```
rules/Validation_Rules_Master.xlsx
```

This single workbook is the authoritative source for all field-level validation
rules and cross-reference (cross-table / conditional) rules. It replaces the old
set of separate `DB_Section_*.xlsx` files.

It has **five tabs**:

| Tab              | What it holds                                   | Table code |
|------------------|-------------------------------------------------|------------|
| `Contract`       | Field rules for Contract fields (`CNT_*`)       | `CNT`      |
| `Address`        | Field rules for Address fields (`ADD_*`)        | `ADD`      |
| `Roles`          | Field rules for Roles fields (`ROL_*`)          | `ROL`      |
| `Coverage`       | Field rules for Coverage fields (`CVG_*`)       | `CVG`      |
| `Cross_References`| Rules that compare fields or span tables       | (per row)  |

---

## How the workbook becomes engine configuration

```
rules/Validation_Rules_Master.xlsx
        │
        ▼  python scripts/generate_config_from_master.py
        │
        ├─ templates/v1/validation_rules.csv     (field-level rules)
        ├─ templates/v1/cross_references.csv      (cross-reference rules)
        ├─ templates/v1/table_dependencies.csv    (parent/child joins)
        └─ templates/v1/_reconciliation_report.txt (what was read, what to review)
```

The adapter reads the columns **verbatim** — it does not guess. What you type in
the `Rule Type` column is what the engine uses. Always check
`_reconciliation_report.txt` after regenerating: it lists counts per table and
flags anything the engine does not yet understand.

---

## Table tabs — column reference

Each of the four table tabs uses these columns. **One row per (field, rule).**
A field that needs two checks (for example, must be exactly 2 characters *and*
must not be blank) gets **two rows** with the same `Field Name`.

| Column                | Required | Meaning                                                                 |
|-----------------------|----------|-------------------------------------------------------------------------|
| `Field Name`          | Yes      | Exact field name, e.g. `CNT_COMPANY_CODE`. Must start with the table code. |
| `Data Type`           | No       | `CHAR`, `INT`, etc. Documentation aid.                                   |
| `Length`              | Depends  | Max/exact character length. Used by length-based rule types (see below). |
| `Precision`           | Depends  | Decimal places. Used by `numeric_decimal`.                               |
| `Date Format`         | No       | e.g. `yyyyMMdd`. Documentation aid.                                      |
| `Is Key Field`        | No       | `YES`/`NO`. Documentation aid.                                           |
| `Rule Type`           | Yes      | One of the registered field-level rule types (table below).             |
| `Severity`            | Yes      | `SEVERE` or `WARNING`.                                                   |
| `Allowable Codes`     | Depends  | Accepted values for `allowed_values`, comma or pipe separated. |
| `Allowable Description`| No      | Human-readable meaning of the codes.                                     |
| `Description / Notes` | No       | Free text. Carried into the CSV `description` (trimmed).                 |

### Registered field-level rule types

| Rule Type               | What it checks                                                        | Uses |
|-------------------------|-----------------------------------------------------------------------|------|
| `not_blank`             | Value must not be empty/whitespace.                                    | —    |
| `exact_length`          | Trimmed length must equal `Length`.                                   | Length |
| `max_length`            | Trimmed length must be ≤ `Length`.                                   | Length |
| `exact_length_or_blank` | Exactly `Length` characters, or blank.                               | Length |
| `allowed_values`        | Value must be one of `Allowable Codes`.                              | Allowable Codes |
| `allowed_blank`         | Declares blank is allowed for the field (optionality). Never fails on its own; pair with `allowed_values`/`numeric_string`/etc. on the same field to constrain non-blank content. | — |
| `valid_date`            | Parses as a valid date (`yyyyMMdd`).                                 | —    |
| `numeric`               | Digits only (treated as a number).                                   | —    |
| `numeric_string`        | Digits only, **kept as text** (leading zeros preserved). Blank OK.   | —    |
| `numeric_decimal`       | Numeric with a decimal point; total length + precision.              | Length, Precision |
| `numeric_range`         | Numeric within `[param_1, param_2]`.                                | params |
| `min_value`             | Numeric ≥ `param_1`.                                                | param |
| `project_defined_value` | Any value up to `Length` characters; blank OK.                      | Length |
| `conditional`           | Value gated by a precondition (simple form).                        | precondition |
| `conditional_null`      | Field must be blank when a precondition holds.                      | precondition |
| `conditional_blank`     | Same as `conditional_null` (alias used by the business).            | precondition |
| `cross_field_conditional`| If precondition, target must be in an allowed set (or blank).      | precondition |
| `default_then_warn`     | Blank is defaulted downstream; emits a WARNING.                     | —    |

> "Uses Length" means the adapter reads the `Length` column into the rule's
> `param_1`. "Uses params/precondition" fields are typically seeded by an
> engineer or via the Cross_References tab.

---

## Cross_References tab — column reference

One row per cross-reference rule. These cover conditional logic and checks that
span more than one field or table.

| Column                 | Meaning                                                                       |
|------------------------|-------------------------------------------------------------------------------|
| `XRef ID`              | Unique id, e.g. `XR_CON_001`. Becomes the rule's error column suffix.          |
| `Table Name`           | The table the rule applies to (Contract/Address/Roles/Coverage; normalized to a code). |
| `Target Field`         | The field being checked.                                                      |
| `Rule Type`            | One of the registered cross-reference types (table below).                    |
| `Severity`             | `SEVERE` or `WARNING`.                                                         |
| `Precondition Field`   | Field whose value gates the rule (optional).                                  |
| `Precondition Operator`| `eq, neq, in, not_in, blank, not_blank, gt, lt, gte, lte, exists, none`.       |
| `Precondition Value`   | Value(s) for the operator; pipe-separate lists (`A|W|B`). `none` = no gate.    |
| `Precondition Field 2/3` / `Operator 2/3` / `Value 2/3` | Optional SECOND and THIRD preconditions (same operators). |
| `Precondition Logic`   | `AND` / `OR` — how to combine the preconditions (default `AND`; applies to all). |
| `Expected Result`      | The condition the target must satisfy (free text allowed for complex rules).  |
| `Compare Table`        | For cross-table rules: the other table (normalized to a code).                |
| `Compare Field`        | For cross-table/field comparisons: the field to compare against.              |
| `Join Child Fields`    | Pipe-separated keys on the target table (e.g. `CVG_COMPANY_CODE|CVG_POLICY_NUMBER`). |
| `Join Parent Fields`   | Pipe-separated keys on the compare table, in the same order.                  |
| `Error Message`        | Message emitted on failure (falls back to a generated one).                   |
| `Active`               | `Y`/`N`. `N` (or No/False/0) means the rule is carried but not evaluated.     |
| `Notes`                | Free text.                                                                     |

### Registered cross-reference rule types

| Rule Type              | What it does                                                          |
|------------------------|----------------------------------------------------------------------|
| `required`             | Target field must not be blank (optionally gated by a precondition). |
| `value_compare`        | Compare target to a literal using an operator.                       |
| `field_compare`        | Compare target to another field in the same record.                  |
| `date_greater_than`    | Target date must be greater than the compare-field date.             |
| `date_less_than_equal` | Target date must be on or before the compare-field date.             |
| `cross_table_match`    | Target must equal a field in another table (via the join keys).      |
| `occurrence_check`     | The target's key must exist in another table (via the join keys).    |
| `cross_reference_exists`| Referential-integrity existence check.                              |
| `conditional`          | If the precondition holds, the target must satisfy `Expected Result`.|
| `values_present`       | Within each group, every value in `Count Filter Value` must appear in `Count Filter Field`. |
| `occurrence_count`     | Count rows per group (optionally filtered) and assert `Count Operator` `Count Value`. |
| `unique_per_group`     | `Count Filter Field` must be unique within each group; only the duplicate rows are flagged. |
| `match_across_occurrences` | Within each group, at least one in-scope row's `Target Field` must equal the parent's `Compare Field`; scope is defined by the preconditions. Flags the in-scope rows when none match. |
| `match_through_intermediate` | Two-hop: `Target Field` must equal a `Compare Field` reached via a **filtered intermediate table**. Flags SEVERE on mismatch OR when the related record is missing. Uses the extra columns below. |

### Two-hop (match_through_intermediate) columns

For rules where the value to compare lives on a table reached *through* another
(filtered) table — e.g. "Contract resident state must equal the Owner's resident
Address state," where the Owner is identified on Roles:

| Column | Purpose | Example |
|--------|---------|---------|
| `Join Child Fields` / `Join Parent Fields` | Hop 1: this table → intermediate | `CNT_COMPANY_CODE\|CNT_POLICY_NUMBER` ↔ `ROL_COMPANY_CODE\|ROL_POLICY_NUMBER` |
| `Intermediate Table` | The middle-hop table | `Roles` |
| `Intermediate Filter Field` / `Intermediate Filter Value` | Selects the intermediate row | `ROL_PERSON_CODE` / `O` |
| `Join Intermediate Fields` / `Join Compare Fields` | Hop 2: intermediate → compare table | `ROL_COMPANY_CODE\|ROL_POLICY_NUMBER\|ROL_PERSON_SEQUENCE` ↔ `ADD_COMPANY_CODE\|ADD_POLICY_NUMBER\|ADD_PERSON_SEQUENCE` |
| `Compare Table` / `Compare Field` | The final table + field to compare | `Address` / `ADD_STATE` |
| `Count Filter Field` / `Count Filter Value` | (reused) filter on the compare table | `ADD_ADDRESS_TYPE` / `R` |

### Aggregate (group-level) rule columns

`values_present` and `occurrence_count` evaluate a condition over a **group of
rows** (e.g. all rows for one policy), not a single record. When a group fails,
every row in that group is flagged. They use these additional columns:

| Column | Purpose | Example |
|--------|---------|---------|
| `GroupBy Fields`     | Pipe-separated keys defining each group | `ROL_COMPANY_CODE\|ROL_POLICY_NUMBER` |
| `Count Filter Field` | Field whose values are counted / must be present | `ROL_PERSON_CODE` |
| `Count Filter Value` | Value(s) to count or require (pipe-separated) | `1\|2` |
| `Count Operator`     | For `occurrence_count`: `eq/neq/gt/lt/gte/lte` | `gte` |
| `Count Value`        | For `occurrence_count`: a numeric threshold **or the name of a parent field** to compare the group count against | `2` or `CNT_JOINT_NUMBER_OF_LIVES` |

> For `occurrence_count`: if `Count Filter Field` is set but `Count Filter Value`
> is empty, the rule counts rows where that field is **non-blank**. If `Count
> Value` names a parent field (via `Compare Table` + join keys), the group count
> is compared to that joined parent value (e.g. "one occurrence per joint insured").

A precondition may reference a **parent-table** field (via `Compare Table` +
`Join Child/Parent Fields`); the group check then applies only where the joined
parent value satisfies the precondition. Example: `values_present` with
precondition `CNT_JOINT_NUMBER_OF_LIVES = 2` (from Contract) and `Count Filter
Value = 1|2` on `ROL_PERSON_CODE` means "when the policy has 2 joint lives, both
role codes 1 and 2 must be present."

> **About complex conditionals.** Some `conditional` rows still describe
> multi-record logic (e.g. "match any TERM occurrence") that isn't yet expressed
> with the aggregate columns above. Those are **preserved in the CSV** so nothing
> is lost, but only evaluated once restructured into a supported type or handler.
> The reconciliation report lists which rows are carried-but-not-yet-evaluated.
> Adding support is an engine change (see `docs/EXTENDING_THE_ENGINE.md`).

---

## Authoring workflow (checklist)

1. Open `rules/Validation_Rules_Master.xlsx`.
2. Add or edit rows on the correct tab. One row per (field, rule).
3. Use only rule types from the tables above. If you need something new, ask an
   engineer to add a handler first (see `docs/EXTENDING_THE_ENGINE.md`).
4. Save the workbook (keep the `.xlsx` format and the tab names).
5. Regenerate the configuration:
   ```
   python scripts/generate_config_from_master.py
   ```
6. Open `templates/v1/_reconciliation_report.txt`. Confirm the counts look right
   and that there are no unexpected "NOT REGISTERED" / "not evaluated" entries.
7. Commit the workbook **and** the regenerated CSVs together.

---

## Common mistakes

- **Renaming a tab.** The adapter looks for the exact tab names. If you rename a
  tab, add its name to `TABLE_TAB_TO_CODE` in the adapter (engineer task).
- **A rule type with a typo.** It will show up under "NOT REGISTERED" in the
  reconciliation report and be skipped at runtime. Fix the spelling.
- **Forgetting the second row.** "Exactly 2 chars and not blank" is two rows, not
  one.
- **Join field order mismatch.** `Join Child Fields` and `Join Parent Fields`
  must list keys in the same order.
