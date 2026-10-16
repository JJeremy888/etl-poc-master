---
inclusion: always
---

# Validation Principles — Runtime Behavior Rules

These principles govern how the validation engine interprets and enforces rules from the source rule sheet (`rules/Validation_Rules_Master.xlsx`). They apply to all tables (CNT, CVG, ROL, ADD) and all future tables.

> **Source-of-truth note.** The master workbook has explicit `Rule Type` and
> `Severity` columns authored by data engineers. Rule type and severity are read
> verbatim by the input adapter — they are no longer inferred from prose. The
> principles below still hold: they govern how the engine *interprets* those
> authored rules and how blank/optional and enumerated-code fields behave.

---

## Principle 1 — Zero-Pad Normalization for Enumerated Code Fields

**Rule:** When the master workbook provides an explicit enumerated list of allowable values (the `Allowable Codes` column) that are zero-padded numeric codes (e.g., "001" through "044"), the validation engine SHALL normalize incoming values by adding leading zeros before checking against the list.

**Logic:**
- If the spec enumerates codes like 001, 002, ... 044 (known fixed-width numeric codes)
- And the input value is a shorter numeric string (e.g., "1", "29")
- Then normalize by left-padding with zeros to the expected width (e.g., "1" → "001", "29" → "029")
- Then check the normalized value against the allowed list
- If the input exceeds the target width (e.g., "1234" for a 3-digit field), it fails — no normalization attempted
- If the input is non-numeric, it fails — no normalization attempted

**When this applies:**
- The spec provides an EXPLICIT enumerated list of valid codes
- Those codes are visibly zero-padded (e.g., "001" not "1")
- The field is clearly a numeric code, not free-form text

**When this does NOT apply:**
- The spec says "must be exactly N characters" but does NOT provide an enumerated list
- The values are not numeric codes (e.g., "AA", "RS" — alpha codes)
- We don't know what the expected values look like

**Rationale:** Source systems often store numeric codes as integers, stripping leading zeros. The intent is unambiguous when the spec enumerates the codes — "1" and "001" carry the same semantic meaning. This is validation-time normalization, not data alteration or rule weakening.

---

## Principle 2 — No Derived or Hardcoded Rules; Source Rule Sheet is the Single Authority

**Rule:** All validation rules MUST derive directly and exclusively from the master workbook (`rules/Validation_Rules_Master.xlsx`). No validation rule shall be invented, hardcoded, or derived from any other source.

**What this means in practice:**
- Engine handlers must NOT contain hand-written rule dictionaries with values that differ from the master workbook
- If a field's allowed values in code differ from what the master workbook says, the CODE is wrong — not the data
- The generated `validation_rules.csv` / `cross_references.csv` and the runtime rule loading must both trace to the same `Validation_Rules_Master.xlsx` source
- When discrepancies are found between code and spec, the spec wins — the code must be corrected

**The master workbook defines:**
- Which values are allowed (`Allowable Codes` column)
- What the validation rule type is (explicit `Rule Type` column)
- What the severity is (explicit `Severity` column)
- The precondition / expected result for cross-reference rules (the `Cross_References` tab)

**The source rule sheet does NOT define:**
- Runtime architecture decisions (those are engineering choices)
- How the engine loads or compiles rules (that's implementation)

---

## Principle 3 — Source Rule Sheet is the Authority on Blank/Optional Fields

**Rule:** The master workbook determines whether blank/empty is a valid state for a field. The validation engine must respect this exactly.

**How blank-handling is expressed in the master workbook:**
- A `not_blank` rule row on the field → blank is NOT allowed (severity from the `Severity` column)
- An `allowed_blank` rule → the value must be in the allowed list OR blank (blank always accepted)
- A `valid_date`/format rule with no accompanying `not_blank` row → blank IS allowed; validate format only when a value is present
- `conditional_null` / `conditional_blank` → the field must be blank when the precondition holds
- No `not_blank` row for a field → the field is optional (blank accepted)

**Severity for optional fields:**
- When a value IS present: validate its format/content per the spec, with the severity stated in the spec
- When blank: no violation generated (field is optional)
- This maps to the `valid_date` with `severity=WARNING` pattern: validate format when non-blank, accept blanks silently

**Do NOT assume:**
- That every date field must be non-blank (many are "blank if not applicable")
- That a field is mandatory just because it has a validation rule (the rule may only apply when a value is present)
- That SEVERE is the default for all fields (use the spec language to determine severity)

---

## Principle 4 — No Silent Skips: An Uninterpretable Rule Must Surface Loudly

**Rule:** If the engine cannot interpret or evaluate a rule that is Active, it MUST
NOT silently skip it. An uninterpretable rule must surface as an explicit,
visible failure — never vanish as a quiet no-op that leaves the impression the
record passed.

**Why:** A silently dropped rule creates false confidence — results look "clean"
when in fact a check never ran. That is more dangerous than a loud error. Every
Active rule must have a visible outcome: it either evaluates (pass/fail) or it is
reported as uninterpretable.

**How the engine enforces this:**
- A handler that cannot interpret its inputs (e.g. `compile_value_compare` given
  an `expected_result` it cannot parse) RAISES rather than returning a silent
  no-op Column.
- The orchestrator catches that error and emits an explicit
  `UNINTERPRETABLE_RULE <xref_id>: <reason>` marker as a **SEVERE** value on every
  row for that rule (via a `VAL_XREF_<id>` column), and logs
  `[VALIDATE] ERROR UNINTERPRETABLE_RULE ...`. The rule therefore appears in the
  results and error report; it is not lost. One bad rule does NOT abort the run.

**Distinction — "cannot interpret" vs. "not applicable in scope":**
- **Cannot interpret** (engine limitation / malformed rule) → surface loudly as
  above. This is the case this principle governs.
- **Not applicable in current scope** (rule references a table/field not loaded
  in the active table set, e.g. a rule needing ROL while processing ADD) → these
  are logged as `[VALIDATE] SKIP ... not available / fields not in data`. They
  are legitimately out of scope for the run, not engine failures. They are still
  logged (visible), not hidden.

**Do NOT:**
- Return a null/no-op Column to make an unparseable rule "disappear."
- Use a bare `continue` that drops an Active rule without any recorded outcome.
- Treat `float()`/parse exceptions as reasons to skip — treat them as reasons to
  flag.

---

## Application to Code

These principles affect:
1. **option_b/engine/presence_format_rules.py** — implements rule handlers including zero-pad normalization for enumerated code fields
2. **templates/v1/validation_rules.csv** and **templates/v1/cross_references.csv** — the config-driven rule set consumed by option_b; must NOT contain hardcoded values that diverge from the spec. Generated by `scripts/generate_config_from_master.py` from `rules/Validation_Rules_Master.xlsx`.
3. **scripts/generate_config_from_master.py** — reads the master workbook's explicit `Rule Type`/`Severity` columns verbatim (no prose parsing) and emits the template CSVs plus a `_reconciliation_report.txt` flagging anything unrecognized.
4. **scripts/export_sample_data.py** — must export data as-is from Excel; must NOT alter values to make validation pass (zero-padding of enumerated code fields is the sole exception, per Principle 1)

---

## Validation Audit Checklist

When reviewing validation results, before accepting a failure as "genuine data quality issue," verify:
1. Is the rule correctly derived from the source rule sheet? (Principle 2)
2. Does the rule correctly handle blank/optional per the spec? (Principle 3)
3. For enumerated code fields, is the engine normalizing leading zeros? (Principle 1)
4. Is the export faithfully representing the Excel source data? (no silent alteration)
5. Are there any `UNINTERPRETABLE_RULE` markers in the output/log? Those are rules
   the engine could not evaluate and MUST be fixed (rule type/config or engine
   support), not ignored. (Principle 4)
6. If results are uniformly SEVERE (e.g. 100% of records fail), suspect a
   systemic misfire (a field-level rule wrong for all rows, or a data-shape
   mismatch) before concluding the data is bad.
