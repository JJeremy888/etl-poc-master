# Contributing Guide

Thank you for contributing to the Policy Loader ETL Validation Pipeline. This document covers the conventions and processes the team follows.

---

## Active Codebase

The active codebase is `option_b/`. All development, fixes, and new features must target this path.

The `_deprecated_src_do_not_use/` directory contains the old Option A code — do NOT use or modify it.

---

## Branch Naming Convention

Use a prefix that describes the type of work:

| Prefix | Use case |
|---|---|
| `feature/` | New functionality (e.g., `feature/prm-rule-loader`) |
| `bugfix/` | Fixing a defect (e.g., `bugfix/date-validation-leap-year`) |
| `chore/` | Non-functional changes (e.g., `chore/update-dependencies`) |
| `docs/` | Documentation only (e.g., `docs/update-requirements`) |

Keep branch names lowercase with hyphens. Be descriptive but concise.

---

## Commit Message Format

Follow the conventional commit format:

```
type: short description
```

Examples:

```
feat: add PRM validator to rule loader
fix: handle leap year edge case in date validation
test: add property tests for cross-field rules
docs: update requirements with Phase 2 scope
chore: pin pandas to 2.2.1
refactor: extract date helpers from validation engine
```

Allowed types: `feat`, `fix`, `test`, `docs`, `chore`, `refactor`, `perf`, `ci`

Keep the subject line under 72 characters. Use the body for additional context if needed.

---

## Pull Request Checklist

Before requesting a merge, confirm the following:

- [ ] All tests pass: `pytest option_b/tests/ -v` exits with 0 failures
- [ ] Ruff lint is clean: `ruff check option_b/` reports no errors
- [ ] No hardcoded field names or business rules in engine code
- [ ] If validation rules changed, regenerate via `python scripts/generate_config_from_master.py` and review `templates/v1/_reconciliation_report.txt`
- [ ] If scope or requirements changed, update relevant docs
- [ ] No hardcoded paths or machine-specific strings
- [ ] New code includes docstrings on all functions and a module-level docstring

---

## Architecture — Layer Ownership

The engine is config-driven. Business rules live in template CSVs, not in Python code.

| Layer | Location | Responsibility |
|---|---|---|
| Config | `option_b/config/` | Load and validate template CSVs |
| Engine | `option_b/engine/` | Compile rules into PySpark expressions, orchestrate validation |
| Input | `option_b/input/` | Read staging CSVs into Spark DataFrames |
| Output | `option_b/output/` | Write positional flat file and CSV output |
| Audit | `option_b/audit/` | Execution audit trail |
| Error | `option_b/error/` | Error logging and targeted revalidation |
| Templates | `templates/v1/` | Business rules and mappings (BA-maintained) |
| Scripts | `scripts/` | Input adapter + generator scripts (Excel → template CSV) |

Rules:
- The engine code must NEVER contain hardcoded field names or allowed values
- All business logic traces to `templates/v1/validation_rules.csv`, `templates/v1/cross_references.csv`, and `transformation_mappings.csv`
- Validation templates are generated from the single master workbook `rules/Validation_Rules_Master.xlsx` via `scripts/generate_config_from_master.py`

---

## How to Add or Update a Validation Rule

The engine is config-driven — most rule changes need no Python.

1. Edit `rules/Validation_Rules_Master.xlsx` (field rules on the table tab;
   cross-table/conditional rules on the `Cross_References` tab). See
   `rules/RULES_TEMPLATE_GUIDE.md` for the column reference.
2. Regenerate the templates: `python scripts/generate_config_from_master.py`
3. Review `templates/v1/_reconciliation_report.txt` — confirm counts and that no
   rule type shows as unregistered / not-evaluated.
4. Run the pipeline: `python -m option_b.main --validate`
5. Add tests if needed in `option_b/tests/`
6. Commit the workbook and the regenerated CSVs together.

If the rule needs a rule type the engine does not yet support, add a handler
first (see below and `docs/EXTENDING_THE_ENGINE.md`).

---

## How to Add a New Rule Type

1. Implement a handler function in the appropriate module:
   - `option_b/engine/presence_format_rules.py` — for field-level checks
   - `option_b/engine/range_rules.py` — for date/numeric comparisons
2. Register it in `option_b/engine/rule_compiler.py` → `RULE_HANDLER_REGISTRY`
   (field-level) or `CROSS_REFERENCE_HANDLER_REGISTRY` (cross-reference)
3. Add the type to `option_b/config/schema_definitions.py` →
   `REGISTERED_RULE_TYPES` or `REGISTERED_CROSS_REFERENCE_TYPES`
4. Author rules using the new type in `rules/Validation_Rules_Master.xlsx`
5. Add unit tests in `option_b/tests/`

Step-by-step recipes for each extension kind are in
`docs/EXTENDING_THE_ENGINE.md`.

---

## How to Add a New Table (Future Phases)

1. Add a tab for the new table to `rules/Validation_Rules_Master.xlsx`
2. Add the sample data Excel file to `staging_data/` and update `scripts/export_sample_data.py`
3. Map the tab name to a table code in `scripts/generate_config_from_master.py`
   (`TABLE_TAB_TO_CODE`), add the table to `VALID_TABLES` in
   `schema_definitions.py`, and add its parent/child entry to `TABLE_DEPENDENCIES`
4. Regenerate: `python scripts/generate_config_from_master.py`
5. Run the pipeline — the engine is table-agnostic, no code changes required
6. Update documentation

The core principle: **new tables add data and rules, not new engine code**.
