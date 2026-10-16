# Extending the Option B Validation Engine

This is the engineer's playbook for adding capability to the validation engine
**without rewriting or breaking what already works.** The engine is
config-driven and registry-based: new behavior is added by writing a small
handler and registering it, not by editing the orchestrator or existing rules.

Read this before you change engine code. Most extensions touch only two files.

---

## Mental model

```
rules/Validation_Rules_Master.xlsx        <-- business authors rules here
        │  scripts/generate_config_from_master.py   (input adapter)
        ▼
templates/v1/                              <-- flat CSV contract
    validation_rules.csv        (field-level rules)
    cross_references.csv        (cross-table / conditional rules)
    table_dependencies.csv      (parent/child joins)
        │  option_b/config/template_loader.py   (loads + schema-validates)
        ▼
option_b/engine/                           <-- the interpreter
    rule_compiler.py            (registries: rule_type -> handler)
    presence_format_rules.py    (field-level handlers -> Column)
    range_rules.py              (date/numeric comparison handlers -> Column)
    cross_reference_rules.py    (cross-ref handlers: Column + DataFrame-join)
    validation_orchestrator.py  (drives the pass; wires join handlers)
    severity_classifier.py      (rolls VAL_* columns up to ROW_SEVERITY)
```

Two kinds of handler exist:

- **Column handlers** — evaluate one record and return a PySpark `Column` that is
  `None` on pass or a `"SEVERITY: message"` string on fail. Field-level rules and
  simple cross-reference rules are Column handlers.
- **Join handlers** — need another table, so they take parent/child DataFrames
  and append a `VAL_*` column. Cross-table rules are join handlers.

The severity classifier automatically rolls up **any** column named `VAL_*`, so a
correctly-named output column is picked up with no extra wiring.

---

## Recipe 1 — Add a new field-level rule type

Example: add `even_number` (value must be an even integer).

1. **Register the type name** in `option_b/config/schema_definitions.py`:
   ```python
   REGISTERED_RULE_TYPES = frozenset([
       ...,
       "even_number",   # <-- add
   ])
   ```

2. **Write the handler** in `option_b/engine/presence_format_rules.py`
   (or `range_rules.py` for numeric/date comparisons):
   ```python
   def compile_even_number(rule: dict) -> Column:
       field = rule["target_field"]
       severity = rule["severity"]
       val = F.trim(F.col(field))
       is_blank = F.col(field).isNull() | (val == F.lit(""))
       is_even = val.cast("long") % F.lit(2) == F.lit(0)
       return (
           F.when(is_blank, F.lit(f"{severity}: {field} must not be blank"))
            .when(~is_even, F.lit(f"{severity}: {field} must be even"))
            .otherwise(F.lit(None).cast(StringType()))
       )
   ```

3. **Register the handler** in `option_b/engine/rule_compiler.py`:
   ```python
   from option_b.engine.presence_format_rules import compile_even_number
   RULE_HANDLER_REGISTRY["even_number"] = compile_even_number
   ```

That's it. No orchestrator change. Authors can now use `even_number` in the
workbook; the adapter carries it through and the reconciliation report shows it
as registered.

---

## Recipe 2 — Add a simple (single-record) cross-reference type

Example: add `value_not_equal` (target must not equal `expected_result`).

1. **Register** the type in `REGISTERED_CROSS_REFERENCE_TYPES`
   (`schema_definitions.py`).

2. **Write** a Column handler in `option_b/engine/cross_reference_rules.py`.
   Reuse the shared helpers `_xref_precondition(rule)` (gate) and
   `_xref_message(rule, default)` (author message with fallback):
   ```python
   def compile_value_not_equal(rule: dict) -> Column:
       field = rule["target_field"]
       severity = rule["severity"]
       expected = (rule.get("expected_result") or "").strip()
       val = F.trim(F.col(field))
       violated = F.col(field).isNotNull() & (val == F.lit(expected))
       msg = _xref_message(rule, f"{severity}: {field} must not equal {expected}")
       return F.when(violated, F.lit(msg)).otherwise(F.lit(None).cast(StringType()))
   ```

3. **Register** it in `CROSS_REFERENCE_HANDLER_REGISTRY` (`rule_compiler.py`).

The orchestrator already routes single-record cross-references through
`compile_cross_reference_rule` and emits a `VAL_XREF_<id>` column — no change
needed there.

---

## Recipe 3 — Add a join-based cross-reference type

Example: a rule that needs to look at a parent/other table.

1. **Register** the type in `REGISTERED_CROSS_REFERENCE_TYPES`, and add its name
   to `CROSS_REFERENCE_JOIN_TYPES` in `rule_compiler.py` so the compiler knows it
   is applied by the orchestrator (not compiled to a Column).

2. **Write** an `apply_<type>(...)` function in `cross_reference_rules.py`. Follow
   the shape of `apply_cross_table_match` / `apply_occurrence_check`: take the
   child + parent DataFrames and the split join-field lists, do a left join with
   aliased parent columns, append a single `VAL_*` column, and drop the temp
   join columns.

3. **Wire** it in `option_b/engine/validation_orchestrator.py` inside
   `apply_cross_references_for_table`, in the `if rule_type in
   CROSS_REFERENCE_JOIN_TYPES:` branch — add a case that calls your `apply_*`
   function with the resolved parent DataFrame (`available_dfs[compare_table]`).

Join handlers are the only extension that touches the orchestrator, and only in
that one clearly-marked branch.

---

## Recipe 4 — Add a new operator

Operators are used by preconditions and by `value_compare` / `field_compare`.

1. Add the operator to `VALID_PRECONDITION_OPERATORS` in `schema_definitions.py`.
2. Handle it in `_build_precondition` (`presence_format_rules.py`) and/or
   `_xref_precondition` (`cross_reference_rules.py`), and in the comparison
   handlers if it applies there.

---

## Recipe 5 — Onboard a new table

The POC covers 4 of ~20 tables (CNT, CVG, ROL, ADD). To add another:

1. Add a tab to `rules/Validation_Rules_Master.xlsx` for the table.
2. Map the tab name to a table code in `TABLE_TAB_TO_CODE` (and, if the sheet
   refers to it by name elsewhere, `TABLE_NAME_ALIASES`) in
   `scripts/generate_config_from_master.py`.
3. Add the table to `VALID_TABLES` in `schema_definitions.py`.
4. Add its parent/child entry to `TABLE_DEPENDENCIES` in the adapter (and thus
   `table_dependencies.csv`).
5. Regenerate and check the reconciliation report.

---

## Guardrails (do not break these)

- **Handlers are pure and record-local (Column handlers).** Return a `Column`;
  do not read files, mutate global state, or reference hardcoded field names.
- **Always name failure columns `VAL_*`.** That prefix is the contract the
  severity classifier depends on.
- **Messages start with the severity.** `"SEVERE: ..."` or `"WARNING: ..."` — the
  classifier matches on that prefix.
- **Never hardcode business values in the engine.** Allowed values, lengths,
  thresholds, and table names come from the rule dict / template, never from
  code. This is enforced by `validation-principles.md`.
- **The adapter reads the sheet verbatim.** Do not add prose-parsing/guessing to
  `generate_config_from_master.py`; if the business needs a new concept, add a
  column or a rule type, not a heuristic.
- **Additive changes only.** Adding a registry entry must not change the behavior
  of existing rule types. Existing templates must keep loading unchanged.
- **No silent skips.** If a handler cannot interpret an Active rule, RAISE
  (`ValueError` with the `xref_id` and raw value) — never `return None`/no-op to
  make it vanish. The orchestrator turns that into a visible SEVERE
  `UNINTERPRETABLE_RULE` marker on every row and continues. A dropped rule that
  looks "clean" is worse than a loud error. (See validation-principles.md
  Principle 4.)
- **Bound the logical plan.** Any loop applying many `withColumn`/join ops to one
  DataFrame must checkpoint (`localCheckpoint(eager=True)`) every ~25 ops to stop
  Spark plan explosion. See etl-engineering-standards.md §5.5.
- **Build parent join projections in one `select(...alias...)` pass**, not chained
  `withColumnRenamed` — chained renames break on self-joins / compare-field ==
  join-key and cause `UNRESOLVED_COLUMN`. See etl-engineering-standards.md §5.6.

---

## Verifying an extension

1. Regenerate config: `python scripts/generate_config_from_master.py` and read
   `templates/v1/_reconciliation_report.txt` — your new type should appear as
   registered / evaluable.
2. Confirm the template still loads:
   ```python
   from option_b.config.template_loader import load_template
   load_template("templates/v1")
   ```
3. Add tests for the new handler (unit test the Column truth table; the project
   uses PySpark + Hypothesis). Testing conventions live in
   `.kiro/steering/etl-engineering-standards.md`.

---

## Where things live (quick index)

| Concern                         | File |
|---------------------------------|------|
| Registered types / operators / schemas | `option_b/config/schema_definitions.py` |
| Type → handler registries       | `option_b/engine/rule_compiler.py` |
| Field-level handlers            | `option_b/engine/presence_format_rules.py` |
| Date/numeric comparison handlers| `option_b/engine/range_rules.py` |
| Cross-reference handlers        | `option_b/engine/cross_reference_rules.py` |
| Orchestration / join wiring     | `option_b/engine/validation_orchestrator.py` |
| Severity roll-up                | `option_b/engine/severity_classifier.py` |
| Template loading + validation   | `option_b/config/template_loader.py` |
| Input adapter (workbook → CSV)  | `scripts/generate_config_from_master.py` |
| Business authoring guide        | `rules/RULES_TEMPLATE_GUIDE.md` |
