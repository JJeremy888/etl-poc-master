---
inclusion: always
---

## ⚠️ MANDATORY: option_b/ IS THE ONLY ACTIVE CODEBASE ⚠️

The deprecated codebase (formerly src/, now renamed _deprecated_src_do_not_use/) must NEVER be used. This is a hard rule with no exceptions:

- EVERY command, fix, investigation, or file edit in this project MUST target option_b/, regardless of whether the user's message explicitly says "option_b" or not. Silence on this point means option_b — never the deprecated path.

- Kiro MUST NOT read, edit, execute, or reference ANY file under the deprecated path for ANY reason — not for comparison, not for "checking if the problem exists there too" — UNLESS the user explicitly writes the literal words "use the deprecated path" or "use src" in that specific message. Even then, confirm with the user once before proceeding, since this would be unusual.

- Before running ANY command, Kiro MUST verify the command path contains "option_b" — e.g. "python -m option_b.main". If a command about to be run references the deprecated path, STOP and re-derive the correct option_b equivalent first.

- This applies identically across all future sessions. If Kiro is unsure which codebase a file belongs to, ASK before proceeding rather than defaulting to whichever one it found first.

# Field Name and Rule Authority — Project-Wide Governance

This steering file governs ALL sessions, ALL tasks, and ALL specs in this project. It is not optional, not context-dependent, and not overridable by any task instruction.

## Purpose of This Project

This is a config-driven ETL and validation ENGINE. The engine's behavior at runtime is 100% deterministic and traceable to explicit configuration (validation_rules.csv, cross_references.csv, transformation_mappings.csv) that itself traces directly to the master rule workbook (`rules/Validation_Rules_Master.xlsx`).

No AI judgment, inference, or guessing is permitted anywhere in that chain — not in the engine's runtime behavior, and not in how the configuration is authored.

Kiro's role in this project is to help build, maintain, and fix that configuration and the code that executes it — under explicit human direction, using the master rule workbook as the sole, literal source of business content. Kiro is NOT authorized to make business decisions (what a field is called, what values are valid, what a rule should check) under any circumstance. Those decisions belong to the BAs, data engineers, and project lead. Kiro's job is implementation, not authorship of business logic.

---

## RULE 1 — Absolute, No Exceptions

**Applies at runtime AND at design time:**

Never invent, rename, guess, assume, or silently modify a field name or a business rule.

If validation_rules.csv, cross_references.csv, or transformation_mappings.csv is missing something, or a field referenced doesn't exist in the master workbook, **STOP and flag it as an open question**.

Do not fill the gap with a plausible-sounding guess, even temporarily, even as a placeholder, even if it seems obviously correct.

This applies whether you are:
- Running the pipeline
- Writing new rules
- Fixing existing ones
- Generating sample data
- Creating or updating any file that references field names

---

## RULE 2 — The Only Exception (Requires Explicit Human Sign-Off)

A field name or rule may be corrected ONLY when:

1. The person explicitly asks for a specific correction, AND
2. You have directly verified the correction against `rules/Validation_Rules_Master.xlsx` yourself and shown the person the evidence (the exact tab + row) before making the change.

This is a rare, deliberate repair action — not a normal part of any workflow — and should never happen as a side effect of another task.

---

## RULE 3 — How to Read `Validation_Rules_Master.xlsx`

The authoritative workbook is:
- `rules/Validation_Rules_Master.xlsx`

It has five tabs. The four **table tabs** (`Contract`, `Address`, `Roles`,
`Coverage`) hold field-level rules; the **`Cross_References`** tab holds
cross-table and conditional rules. The BA authoring reference is
`rules/RULES_TEMPLATE_GUIDE.md`.

### Table-tab column meanings

| Column | Name | Usage |
|--------|------|-------|
| `Field Name` | **Field name** | The ONLY source of truth for field names. For the CURRENT POC PHASE, this column also IS the staging schema itself — there is no separate staging database file to consult. Every staging CSV column, every validation rule's target_field, and every transformation mapping's source_field must match a `Field Name` entry exactly, character for character. |
| `Data Type` | Data type | `CHAR`/`INT`/etc. Structural reference. |
| `Length` / `Precision` | Size | Feed length/precision-based rule params. |
| `Date Format` | Date format | Reference for date fields. |
| `Is Key Field` | Key flag | Reference/traceability only. |
| `Rule Type` | **Rule type** | The authored rule type — used verbatim, never inferred. |
| `Severity` | **Severity** | `SEVERE`/`WARNING`, used verbatim. |
| `Allowable Codes` | Allowable values | Use verbatim as a literal list of valid codes, not a numeric range, unless stated. |
| `Allowable Description` | Code meanings | Reference only. |
| `Description / Notes` | Notes | Business meaning / traceability, reference only. |

### Cross_References tab

Cross-table logic, join keys, preconditions, and expected results live on the
`Cross_References` tab (columns: XRef ID, Table Name, Target Field, Rule Type,
Severity, Precondition Field/Operator/Value, Expected Result, Compare
Table/Field, Join Child/Parent Fields, Error Message, Active, Notes). Always read
this tab before assuming a cross-table rule doesn't exist or inventing one.

### POC Phase vs. Future Production

When this project moves beyond POC into full development against a provisioned, live staging database, this governance will change — at that point, the live database's actual column names become authoritative instead, and this file must be explicitly updated to reflect that.

Until you see that update, assume the `Field Name` column of the master workbook is still the staging schema.

---

## Pre-Flight Check — Before Creating or Modifying Any Field-Referencing File

BEFORE creating or modifying any file that references field names (validation_rules.csv, transformation_mappings.csv, staging CSVs, or any staging schema), you MUST:

1. Read the relevant tab(s) of `rules/Validation_Rules_Master.xlsx` in this same working session
2. Verify every field name used against the `Field Name` column before the file is written — not after
3. Flag any field name not found in the `Field Name` column as an open question
4. Never proceed with a "best guess" to fill the gap

---

## Open Questions Protocol

When a field is needed but does not appear in the master workbook:

1. Flag it explicitly in your response as: **OPEN QUESTION FOR BA CONFIRMATION**
2. State which file needs it and why (e.g., "needed by MAP_023 in transformation_mappings.csv")
3. Add it to `BA_Validation_Report.txt`'s "Questions for BA" section — this is the persistent record; a chat response alone is not sufficient, since it won't be visible to a future session or to Nancy.
4. Do NOT add the field to any working file (validation_rules.csv, transformation_mappings.csv, staging CSVs) until the project lead or BA confirms it.
5. Do NOT invent a placeholder name.


---

## RULE 4 — Ambiguous File References

This project contains multiple files that share common names (requirements.md, design.md, tasks.md) across different specs and the top-level docs folder:

**requirements.md (4 files):**
1. .kiro/specs/option-b-config-driven-engine/requirements.md
2. .kiro/specs/cnt-etl-validation-phase1/requirements.md
3. .kiro/specs/ea-transformation-engine/requirements.md
4. docs/requirements.md

**design.md (3 files):**
1. .kiro/specs/option-b-config-driven-engine/design.md
2. .kiro/specs/cnt-etl-validation-phase1/design.md
3. .kiro/specs/ea-transformation-engine/design.md

**tasks.md (3 files):**
1. .kiro/specs/option-b-config-driven-engine/tasks.md
2. .kiro/specs/cnt-etl-validation-phase1/tasks.md
3. .kiro/specs/ea-transformation-engine/tasks.md

If any instruction refers to one of these filenames WITHOUT a full, unambiguous path, you MUST STOP and ask which specific file is meant before editing anything. Do not guess based on which spec or branch is "currently active," and do not silently pick one. Confirm the full path back to the person before proceeding, every time this ambiguity could exist.


---

## Default Values and Missing-Data Handling

The same evidence rule that applies to field names and validation rules applies to default values and missing-data handling:

- Kiro is NEVER authorized to invent a default value (e.g. 0, a fixed code, today's date, "N/A") for any field when the source value is missing or blank.
- Before generating sample data, writing a transformation rule, or defining a validation rule that involves a default, Kiro must check whether `Validation_Rules_Master.xlsx` or transformation_mappings.csv explicitly states what should happen when the source is missing.
- If no such rule exists in either source, Kiro must NOT decide silently — whether that means defaulting to a value, leaving it blank, or excluding the field. Instead, Kiro must flag it as an open question requiring BA confirmation, using the same Open Questions Protocol already defined above for field names.
- This applies to all fields, not only newly-added ones — if an existing default is discovered during any future work that has no traceable source, it must also be flagged rather than left as-is or "corrected" based on assumption.

---

## Rule Sheet Is Authoritative Over Sample Data

The rule sheet (`rules/Validation_Rules_Master.xlsx`) governs validation logic. Sample or
staging data is NEVER a basis for writing, adjusting, or "correcting"
validation code. Specifically:

- Allowed values come ONLY from the rule sheet's Allowable Values /
  Allowable Values Description content. If the sheet specifies a
  fixed digit width (e.g. "001"-"044"), staging values must be
  normalized (zero-padded) to match — the RULE does not get relaxed
  to match unpadded data.
- If the rule sheet does not specify a fixed-width numeric code, no
  padding is applied.
- Blank/empty values are only permitted when the rule sheet explicitly
  states so (e.g. "blanks if not applicable," "default to blank").
  Absent that language, blank is invalid.
- Date fields are validated for FORMAT (YYYYMMDD) when populated;
  they are not rejected for being blank unless the sheet says blank
  is disallowed.
- If sample/staging data conflicts with what the rule sheet specifies,
  this is either (a) a data quality issue to flag, or (b) evidence the
  validation code was built from an incorrect source and needs to be
  corrected to match the sheet — it is NEVER a reason to change the
  rule sheet's definition or loosen the validation logic to
  accommodate the data.
- Kiro must never author, hardcode, or infer field names, allowed
  values, or validation logic by "reasoning backward" from what sample
  data looks like. Every field name and rule must trace to the `Field Name`
  and `Rule Type`/`Severity` content of the actual master workbook.