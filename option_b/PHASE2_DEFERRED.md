# Phase 2 Deferred Transformations

This document catalogues the 15 transformation mapping rows excluded from the POC scope. Each entry identifies the mapping, the open question blocking implementation, and what is needed to unblock it.

These rows were filtered out during POC execution via `Mapping Status` = "Open - Clarification Needed" or "Review Required" in `rules/POC_Transformation_Mapping.csv`.

---

## JIRA 107 — Dummy Agent Fields (6 rows)

| Row | Target Field | Source Field(s) | Mapping Status |
|-----|-------------|-----------------|----------------|
| 72  | WRITING-AGENT-ID | ROL (agent role lookup) | Open - Clarification Needed |
| 73  | WRITING-AGENT-PERCENT | ROL (agent role lookup) | Open - Clarification Needed |
| 74  | WRITING-AGENT-COMM-SCHED | None (system-derived) | Open - Clarification Needed |
| 75  | SERVICING-AGENT-ID | CNT_SERV_AGENT | Open - Clarification Needed |
| 76  | SERVICING-AGENT-PERCENT | None (system-derived) | Open - Clarification Needed |
| 77  | SERVICING-AGENT-COMM-SCHED | None (system-derived) | Open - Clarification Needed |

**Open Question:** P+ system uses dummy agent codes during conversion. What are the specific dummy values, and should they be sourced from a lookup table or hardcoded as constants?

**Unblock:** Awaiting P+ input per JIRA 107. P+ team must provide the dummy agent ID format, default percentage (likely 100%), and commission schedule code for the conversion placeholder agents.

---

## JIRA 416 — Directory ID Generation (3 rows)

| Row | Target Field | Source Field(s) | Mapping Status |
|-----|-------------|-----------------|----------------|
| 68  | DIRECTORY-ID-1 | ROL_CLIENT_ID (Insured) | Open - Clarification Needed |
| 69  | DIRECTORY-ID-2 | ROL_CLIENT_ID (Joint/Owner) | Open - Clarification Needed |
| 70  | DIRECTORY-ID-3 | ROL_CLIENT_ID (Beneficiary) | Open - Clarification Needed |

**Open Question:** Directory IDs require a generation pattern — are they copied directly from the source ROL_CLIENT_ID values, or must they be reformatted/prefixed for the target system? Which role occurrence maps to which directory slot (1=insured, 2=joint, 3=bene)?

**Unblock:** Awaiting P+ system documentation per JIRA 416. Need the directory ID format specification and the role-to-slot assignment rules for multi-role policies.

---

## JIRA 403 — ORIGINATOR-CODE (1 row)

| Row | Target Field | Source Field(s) | Mapping Status |
|-----|-------------|-----------------|----------------|
| 95  | ORIGINATOR-CODE | None (constant) | Review Required |

**Open Question:** The constant value is believed to be "WiltonRe" (or a code representing WiltonRe as the conversion originator), but the exact value and its length/format within the target PIC definition have not been confirmed.

**Unblock:** Awaiting confirmation from WiltonRe/P+ per JIRA 403. Need the exact originator code string and whether it varies by product type or line of business.

---

## Translation Table — PREM-CLASS-CODE (1 row)

| Row | Target Field | Source Field(s) | Mapping Status |
|-----|-------------|-----------------|----------------|
| 112 | PREM-CLASS-CODE | CNT_RATE_CLASS (via translation) | Open - Clarification Needed |

**Open Question:** Source system rate class codes must be translated to the target system's premium class codes via a lookup table. The translation table does not yet exist — source-to-target code mappings have not been defined.

**Unblock:** BA team must provide the rate class translation table (source code → target PREM-CLASS-CODE). This may require collaboration between the legacy system SME and the P+ configuration team.

---

## Nancy's Co-Owner Sample Dataset Work (2 rows)

| Row | Target Field | Source Field(s) | Mapping Status |
|-----|-------------|-----------------|----------------|
| 130 | CO-OWNER-DATA-AREA | ROL (co-owner role occurrences) | Open - Clarification Needed |
| 131 | CO-OWNER-ADDRESS-INFO | ADD (co-owner address lookup) | Open - Clarification Needed |

**Open Question:** Co-owner data requires identifying the correct ROL occurrence (ROL_PERSON_CODE = 'N' for Contingent Owner) and assembling a composite data area. Nancy is building a sample dataset to clarify the expected output structure — specifically how multiple co-owners are serialized into the fixed-width area, and whether address info is pulled from the co-owner's address record or the primary owner's.

**Unblock:** Awaiting Nancy's sample dataset deliverable. Once provided, the composite field assembly logic and address cross-reference pattern can be implemented.

---

## RESTRICTION-CODE (1 row)

| Row | Target Field | Source Field(s) | Mapping Status |
|-----|-------------|-----------------|----------------|
| 191 | RESTRICTION-CODE | CNT (conditional derivation) | Review Required |

**Open Question:** Partially resolved — the field indicates policy restrictions (e.g., assignment restrictions, withdrawal limits). The derivation logic references multiple source fields and conditions, but the complete decision tree has not been finalized. Some branches depend on product-type-specific business rules that vary across traditional, UL, and annuity lines.

**Unblock:** BA review of the conditional derivation logic needed. Recommend Nancy or Steve confirm the decision tree for each product type family (TRAD, UL, ANN) and whether a default "no restriction" code applies when conditions aren't met.

---

## LINE-OF-BUSINESS-CODE (1 row)

| Row | Target Field | Source Field(s) | Mapping Status |
|-----|-------------|-----------------|----------------|
| 98  | LINE-OF-BUSINESS-CODE | CNT_PRODUCT_TYPE (derived) | Review Required |

**Open Question:** Partially resolved — the derivation groups product types into lines of business (e.g., T/K/L/D → "TRAD", U/V/E/J/Z → "UL", A/W/B → "ANN", I → "ISL", H → "AH"). The grouping is clear but the exact target code values (numeric? alpha? length?) have not been confirmed against the P+ system's LOB code table.

**Unblock:** P+ system team must confirm the target LOB code values and format. Once the code table is provided, this becomes a straightforward CONDITIONAL_OR_DERIVED mapping using CNT_PRODUCT_TYPE as input.

---

---

## Role-Section Disambiguation (transformation_executor.py)

| Component | Location | Current Behavior |
|-----------|----------|-----------------|
| ROL join deduplication | `option_b/engine/transformation_executor.py` lines 98-102 | Naive "prefer insured role (I), then first by sequence" sort |

**Open Question:** The EA Transaction record structure has separate sections for Insured data (rows ~115-148), Owner data (rows ~431-466), Payor data (rows ~489-524), and Co-Owner data (rows ~710-745). Each section requires resolving which ROL occurrence to use based on `ROL_PERSON_CODE`:
- Insured section: ROL_PERSON_CODE = 'I'
- Owner section: ROL_PERSON_CODE = 'O' or 'N' (Contingent Owner)
- Payor section: ROL_PERSON_CODE = 'P'
- Co-Owner section: ROL_PERSON_CODE = 'N' (secondary occurrences)

The current implementation joins ROL to CNT by selecting only ONE role record per policy (insured preferred, then lowest sequence). This means Owner, Payor, and Co-Owner fields in the EA transaction are populated from the wrong role occurrence — producing incorrect output for multi-role policies.

**Impact:** 21 target fields across 4 EA record sections (LAST-NAME, FIRST-NAME, PREFIX, SUFFIX, ADDRESS-1, ADDRESS-LINE-2/3, CITY, STATE, ZIP-POSTAL-CODE-4/5, TAX-ID-NUMBER, SEX-CODE, CASE-INDIV-CODE, CITIZENSHIP-COUNTRY, BIRTH-YY/MM/DD) are affected. Currently these fields are SKIPPED with "Rule cannot be parsed with confidence" because the conditional_or_derived handler cannot resolve which role occurrence to use.

**Unblock:** Define the role-to-section mapping as configuration (not hardcoded). Options:
1. Add a `role_filter` column to transformation_mappings.csv specifying which ROL_PERSON_CODE value(s) apply to each mapping row
2. Use the existing source_field compound pattern (ROL_PERSON_CODE;ROL_PERSON_TYPE in the source_field) as the filter indicator, with the engine joining ROL multiple times — once per section

**Blocked on:** Architecture decision (configuration approach) + BA confirmation of the exact ROL_PERSON_CODE → section assignments for all 4 sections.

## Summary

| Category | Rows | Blocking Dependency |
|----------|------|---------------------|
| JIRA 107 (dummy agents) | 6 | P+ system input |
| JIRA 416 (directory IDs) | 3 | P+ system documentation |
| JIRA 403 (originator code) | 1 | WiltonRe/P+ confirmation |
| Translation table (prem class) | 1 | BA translation table |
| Co-owner fields (Nancy) | 2 | Nancy's sample dataset |
| RESTRICTION-CODE | 1 | BA decision tree review |
| LINE-OF-BUSINESS-CODE | 1 | P+ LOB code table |
| Role-section disambiguation | 21 fields | Architecture decision + BA confirmation |
| **Total** | **15 + 21 fields** | |

All 15 rows are tracked and will be implemented in Phase 2 once the respective blockers are resolved. No code changes are required to the engine — these rows are already excluded by the mapping loader's status filter.
