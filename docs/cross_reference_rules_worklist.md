# Column 7 Cross-Reference Rules — DRAFT WORKLIST

**Status:** DRAFT — needs review  
**Date:** 2026-08-10  
**Scope:** All fields with non-empty Column 7 (Nancy Comments Including Cross References) across CNT, CVG, ROL, ADD  
**Total actionable rules identified:** 56 (from 114 fields with Column 7 content)  
**Note:** This worklist does NOT modify validation_rules.csv. It is a catalog for review only.

---

## Category 1: Same-Table Cross-Field Rules (IF field_a = X THEN field_b must = Y)

| # | Table | Field | Raw Column 7 Text (verbatim) | compare_field | precondition_field | precondition_operator | precondition_value | severity | Status |
|---|-------|-------|------------------------------|---------------|--------------------|-----------------------|--------------------|----------|--------|
| 1 | CNT | CNT_SEX_CODE | "If CNT_SEX_CODE=B, then CNT_JOINT_LIFE_INDICATOR = 'F'. If CNT_SEX_CODE=J, then CNT_JOINT_LIFE_INDICATOR = 'J'. If conditions not satisfied, send severe messages." | CNT_JOINT_LIFE_INDICATOR | CNT_SEX_CODE | eq | B | SEVERE | DRAFT — needs review |
| 2 | CNT | CNT_SEX_CODE (rule 2) | (same as above) | CNT_JOINT_LIFE_INDICATOR | CNT_SEX_CODE | eq | J | SEVERE | DRAFT — needs review |
| 3 | CNT | CNT_JOINT_LIFE_INDICATOR | "If CNT_PRODUCT_TYPE = K, J, Z, then CNT_JOINT_LIFE_INDICATOR = F or J. If CNT_PRODUCT_TYPE = E, then CNT_JOINT_LIFE INDICATOR = F, J, or N. If conditions not satisfied, send severe messages." | CNT_JOINT_LIFE_INDICATOR | CNT_PRODUCT_TYPE | in | K,J,Z | SEVERE | DRAFT — needs review |
| 4 | CNT | CNT_JOINT_LIFE_INDICATOR (rule 2) | (same as above) | CNT_JOINT_LIFE_INDICATOR | CNT_PRODUCT_TYPE | eq | E | SEVERE | DRAFT — needs review |
| 5 | CNT | CNT_JOINT_NUMBER_OF_LIVES | "If CNT_JOINT_NUMBER_OF_LIVES = 1, then CNT_JOINT_RATE_AGE_REASON_CODE = G... If condition not satisfied, send warning message." | CNT_JOINT_RATE_AGE_REASON_CODE | CNT_JOINT_NUMBER_OF_LIVES | eq | 1 | WARNING | DRAFT — needs review |
| 6 | CNT | CNT_JOINT_RATE_AGE | "IF CNT_JOINT_LIFE_INDICATOR = F or N, then CNT_JOINT_RATE_AGE = 0. If condition not satisfied, send severe messsage." | CNT_JOINT_RATE_AGE | CNT_JOINT_LIFE_INDICATOR | in | F,N | SEVERE | DRAFT — needs review |
| 7 | CNT | CNT_JOINT_RATE_AGE_REASON_CODE | "If CNT_JOINT_LIFE_INDICATOR = N, then CNT_JOINT_RATE_AGE_REASON_CODE = blank. If CNT_JOINT_LIFE_INDICATOR = F, then = F or G or P. If = J, then = A, B, C, or D. If conditions not satisfied, send severe messages." | CNT_JOINT_RATE_AGE_REASON_CODE | CNT_JOINT_LIFE_INDICATOR | eq | N | SEVERE | DRAFT — needs review |
| 8 | CNT | CNT_JOINT_RATE_AGE_REASON_CODE (rule 2) | (same as above) | CNT_JOINT_RATE_AGE_REASON_CODE | CNT_JOINT_LIFE_INDICATOR | eq | F | SEVERE | DRAFT — needs review |
| 9 | CNT | CNT_JOINT_RATE_AGE_REASON_CODE (rule 3) | (same as above) | CNT_JOINT_RATE_AGE_REASON_CODE | CNT_JOINT_LIFE_INDICATOR | eq | J | SEVERE | DRAFT — needs review |
| 10 | CNT | CNT_QUALIFICATION_CODE | "If CNT_QUALIFICATION CODE = Q, K, I, T, P, R, U, then CNT_PRODUCT_TYPE must be A, W, or B. If condition not satified, send severe message." | CNT_PRODUCT_TYPE | CNT_QUALIFICATION_CODE | in | Q,K,I,T,P,R,U | SEVERE | DRAFT — needs review |
| 11 | CNT | CNT_PLAN_OPTION_ORIGINAL | "If CNT_PRODUCT_TYPE = A, W, B, or H, then this field is blank. If CNT_PLAN_OPTION = C AND CNT_PRODUCT_TYPE = T, K, L, I, U, V, E, J, Z, D then at least one occurrence of CVG_TYPE = COLA must exist. If conditions not satisfied, send severe messages." | CNT_PLAN_OPTION_ORIGINAL | CNT_PRODUCT_TYPE | in | A,W,B,H | SEVERE | DRAFT — needs review |
| 12 | CNT | CNT_GRACE_EXPIRY_DATE | "If CNT_PRODUCT_TYPE = W, B, or H, then this field = blanks. If condition not satisfied, send severe message." | CNT_GRACE_EXPIRY_DATE | CNT_PRODUCT_TYPE | in | W,B,H | SEVERE | DRAFT — needs review |
| 13 | CNT | CNT_PARTICIPATION_STATUS | "CROSS REFERENCE: If CNT_PRODUCT_TYPE NE T, K, L, D then CNT_PARTICIPATION_STATUS = N." | CNT_PARTICIPATION_STATUS | CNT_PRODUCT_TYPE | not_in | T,K,L,D | WARNING | DRAFT — needs review |
| 14 | ROL | ROL_ROL_ID_USE | "If ROL_PERSON_TYPE = 'I', then ROL_ROL_ID_USE = 1. Else, this field = 2. If condition not satisfied, send severe message." | ROL_ROL_ID_USE | ROL_PERSON_TYPE | eq | I | SEVERE | DRAFT — needs review |
| 15 | ROL | ROL_CONTRACT_OWNER_IND | "If ROL_PERSON_CODE NE O, then this field = blank. If condition not satisfied, send severe message." | ROL_CONTRACT_OWNER_IND | ROL_PERSON_CODE | ne | O | SEVERE | DRAFT — needs review |
| 16 | ROL | ROL_DISTRIBUTION_FLAT_AMOUNT | "If ROL_DISTRIBUTION_PERCENT > 0, then this field = 0. If this field > 0, then ROL_DISTRIBUTION_PERCENT = 0. If conditions not satisfied, send severe messages." | ROL_DISTRIBUTION_FLAT_AMOUNT | ROL_DISTRIBUTION_PERCENT | gt | 0 | SEVERE | DRAFT — needs review |
| 17 | ROL | ROL_BIRTH_DATE | "IF ROL_PERSON_TYPE NE I, then this field is blank. If condition not satisfied, send severe message." | ROL_BIRTH_DATE | ROL_PERSON_TYPE | ne | I | SEVERE | DRAFT — needs review |
| 18 | ROL | ROL_DECEASED_FLAG | "IF ROL_PERSON_TYPE NE I, then this field is blank. If condition not satisfied, send severe message." | ROL_DECEASED_FLAG | ROL_PERSON_TYPE | ne | I | SEVERE | DRAFT — needs review |
| 19 | ROL | ROL_DEATH_DATE | "IF ROL_PERSON_TYPE NE I, then this field is blank. If condition not satisfied, send severe message." | ROL_DEATH_DATE | ROL_PERSON_TYPE | ne | I | SEVERE | DRAFT — needs review |
| 20 | ROL | ROL_BENE_LEVEL | "If ROL_PERSON_CODE = B, then this field is not blank and there can be 1 or more occurrences of Benes in this tab with values of 1, 2, or 3. If conditions not satisfied, send severe messages." | ROL_BENE_LEVEL | ROL_PERSON_CODE | eq | B | SEVERE | DRAFT — needs review |
| 21 | CVG | CVG_TYPE | "IF CVG_TYPE=ANNT or AH, then CVG_COVERED = 01 AND there are no other occurrences in this tab." | CVG_COVERED | CVG_TYPE | in | ANNT,AH | SEVERE | DRAFT — needs review |
| 22 | CVG | CVG_SUB_TYPE | "If CVG_TYPE = DI, then this field = one of the DI allowable subtypes 01 through 08. If the field is blank, send warning message. If CVG_TYPE = TR, then this field = CR or FR or AR." | CVG_SUB_TYPE | CVG_TYPE | eq | DI | WARNING | DRAFT — needs review |
| 23 | CVG | CVG_UNITS | "If COV_TYPE = ANNT or AH, then this field = 0. If condition not satisfied, send severe message." | CVG_UNITS | CVG_TYPE | in | ANNT,AH | SEVERE | DRAFT — needs review |
| 24 | CVG | CVG_FTD_DECR_DURATION | "If CVG_PRODUCT_TYPE = A, W, B, or H, then this field = 0. If conditions not satisfied, send severe message." | CVG_FTD_DECR_DURATION | CVG_PRODUCT_TYPE | in | A,W,B,H | SEVERE | DRAFT — needs review |
| 25 | CVG | CVG_ORIG_UNITS | "If CVG_PRODUCT_TYPE = A, W, B, or H, then this field = 0. If conditions not satisfied, send severe message." | CVG_ORIG_UNITS | CVG_PRODUCT_TYPE | in | A,W,B,H | SEVERE | DRAFT — needs review |
| 26 | CVG | CVG_DIVIDEND_OPTION_1 | "IF CVG_PRODUCT_TYPE = A, W, B, U, V, E, J, Z, H, then this field = blank. (Dividends are n/a.) If condition not satisfied, send severe message." | CVG_DIVIDEND_OPTION_1 | CVG_PRODUCT_TYPE | in | A,W,B,U,V,E,J,Z,H | SEVERE | DRAFT — needs review |
| 27 | CVG | CVG_DIVIDEND_OPTION_2 | "IF CVG_PRODUCT_TYPE = A, W, B, U, V, E, J, Z, H, then this field = blank. (Dividends are n/a.) If condition not satisfied, send severe message." | CVG_DIVIDEND_OPTION_2 | CVG_PRODUCT_TYPE | in | A,W,B,U,V,E,J,Z,H | SEVERE | DRAFT — needs review |
| 28 | CVG | CVG_RENEW_PREM_IND | "IF CVG_PRODUCT_TYPE = A, W, B, or H, then this field = blank. If condition not satisfied, send severe message." | CVG_RENEW_PREM_IND | CVG_PRODUCT_TYPE | in | A,W,B,H | SEVERE | DRAFT — needs review |
| 29 | CVG | CVG_INIT_REN_PERIOD | "If CVG_PRODUCT_TYPE NE L and NE D, then this field = 0. If condition not satisfied, send severe message." | CVG_INIT_REN_PERIOD | CVG_PRODUCT_TYPE | not_in | L,D | SEVERE | DRAFT — needs review |
| 30 | CVG | CVG_SUB_REN_START_DUR | "If CVG_PRODUCT_TYPE NE L and NE D, then this field = 0. If condition not satisfied, send severe message." | CVG_SUB_REN_START_DUR | CVG_PRODUCT_TYPE | not_in | L,D | SEVERE | DRAFT — needs review |
| 31 | CVG | CVG_SUB_REN_PERIOD | "If CVG_PRODUCT_TYPE NE L and NE D, then this field = 0. If condition not satisfied, send severe message." | CVG_SUB_REN_PERIOD | CVG_PRODUCT_TYPE | not_in | L,D | SEVERE | DRAFT — needs review |
| 32 | CVG | CVG_TEMP_FLAT_EXTRA | "If CVG_PRODUCT_TYPE = T, K, L, I, U V, E, J, Z, or D, then this field >= 0. Else, this field = 0. If conditions not satisfied, send severe messages." | CVG_TEMP_FLAT_EXTRA | CVG_PRODUCT_TYPE | in | A,W,B,H | SEVERE | DRAFT — needs review |
| 33 | CVG | CVG_PERM_FLAT_EXTRA | "If CVG_PRODUCT_TYPE = T, K, L, I, U, V, E, J, Z, or D, then this field >= 0. ELSE, this field = 0. If conditions not satisfied, send severe messages." | CVG_PERM_FLAT_EXTRA | CVG_PRODUCT_TYPE | in | A,W,B,H | SEVERE | DRAFT — needs review |
| 34 | CVG | CVG_PERM_TABLE_CODE | "If CVG_PRODUCT_TYPE = T, K, L, I, U, V, E, J, Z, or D, then this field may or may not = 00. ELSE, this field = 00. If conditions not satisfied, send severe messages." | CVG_PERM_TABLE_CODE | CVG_PRODUCT_TYPE | not_in | T,K,L,I,U,V,E,J,Z,D | SEVERE | DRAFT — needs review |
| 35 | CVG | CVG_PERM_EXTRA_PERCENT | "If CVG_PERM_TABLE_CODE = 00, then CVG_PERM_EXTRA_PERCENT = 100.00000. ELSE, CVG_PERM_EXTRA_PERCENT must be >= 100.00000. If conditons not satisfied, send severe messages." | CVG_PERM_EXTRA_PERCENT | CVG_PERM_TABLE_CODE | eq | 00 | SEVERE | DRAFT — needs review |
| 36 | CVG | CVG_TEMP_TABLE_CODE | "If CVG_PRODUCT_TYPE = T, K, L, I, U, V, E, J, Z, or D, then this field may or may not = 00. ELSE, this field = 00. If conditions not satisfied, send severe messages." | CVG_TEMP_TABLE_CODE | CVG_PRODUCT_TYPE | not_in | T,K,L,I,U,V,E,J,Z,D | SEVERE | DRAFT — needs review |
| 37 | CVG | CVG_TEMP_EXTRA_PERCENT | "If CVG_TEMP_TABLE_CODE = 00, then CVG_TEMP_EXTRA_PERCENT = 100.00000. ELSE, CVG_TEMP_EXTRA_PERCENT must be >= 100.00000. If conditons not satisfied, send severe messages." | CVG_TEMP_EXTRA_PERCENT | CVG_TEMP_TABLE_CODE | eq | 00 | SEVERE | DRAFT — needs review |

---

## Category 2: Cross-Table Equality (child must match parent)

| # | Table | Field | Raw Column 7 Text (verbatim) | compare_field | compare_table | compare_column | severity | Status |
|---|-------|-------|------------------------------|---------------|---------------|----------------|----------|--------|
| 38 | CVG | CVG_COMPANY_CODE | "Must equal CNT_COMPANY_CODE. Send severe message if not satisfied." | CVG_COMPANY_CODE | CNT | CNT_COMPANY_CODE | SEVERE | DRAFT — needs review |
| 39 | CVG | CVG_POLICY_NUMBER | "MUST EQUAL CNT_POLICY_NUMBER. Send severe message if not satisfied." | CVG_POLICY_NUMBER | CNT | CNT_POLICY_NUMBER | SEVERE | DRAFT — needs review |
| 40 | CVG | CVG_PRODUCT_TYPE | "MUST EQUAL CNT_PRODUCT_TYPE if tab present. Send severe message if not satisfied." | CVG_PRODUCT_TYPE | CNT | CNT_PRODUCT_TYPE | SEVERE | DRAFT — needs review |
| 41 | ROL | ROL_COMPANY_CODE | "CNT_COMPANY_CODE = ROL_COMPANY_CODE. Send severe message if not satisfied." | ROL_COMPANY_CODE | CNT | CNT_COMPANY_CODE | SEVERE | DRAFT — needs review |
| 42 | ROL | ROL_POLICY_NUMBER | "CNT_POLICY_NUMBER = ROL_POLICY_NUMBER. Send severe message if not satisfied." | ROL_POLICY_NUMBER | CNT | CNT_POLICY_NUMBER | SEVERE | DRAFT — needs review |
| 43 | ROL | ROL_PRODUCT_TYPE | "CNT_PRODUCT_TYPE = ROL_PRODUCT_TYPE. Send severe message if not satisfied." | ROL_PRODUCT_TYPE | CNT | CNT_PRODUCT_TYPE | SEVERE | DRAFT — needs review |
| 44 | ADD | ADD_COMPANY_CODE | "CNT_COMPANY_CODE = ADD_COMPANY_CODE. Send severe message if not satisfied." | ADD_COMPANY_CODE | CNT | CNT_COMPANY_CODE | SEVERE | DRAFT — needs review |
| 45 | ADD | ADD_POLICY_NUMBER | "CNT_POLICY_NUMBER = ADD_POLICY_NUMBER. Send severe message if not satisfied." | ADD_POLICY_NUMBER | CNT | CNT_POLICY_NUMBER | SEVERE | DRAFT — needs review |
| 46 | ADD | ADD_PRODUCT_TYPE | "CNT_PRODUCT_TYPE = ADD_PRODUCT_TYPE. Send severe message if not satisfied." | ADD_PRODUCT_TYPE | CNT | CNT_PRODUCT_TYPE | SEVERE | DRAFT — needs review |
| 47 | CNT | CNT_RESIDENT_STATE | "CNT_RESIDENT_STATE = Address tab resident state for Owner Role. If condition not satisfied, send severe message." | CNT_RESIDENT_STATE | ADD | ADD_STATE (where ROL_PERSON_CODE=O) | SEVERE | DRAFT — needs review |

---

## Category 3: Cross-Table Conditional (condition in one table, check in another)

| # | Table | Field | Raw Column 7 Text (verbatim) | compare_field | precondition_field | precondition_operator | precondition_value | severity | Status |
|---|-------|-------|------------------------------|---------------|--------------------|-----------------------|--------------------|----------|--------|
| 48 | CVG | CVG_PERSON_SEQ | "EACH CVG_PERSON_SEQ in an occurrence should have a corresponding ROL_PERSON_SEQ. If condition not satisfied, send severe message." | CVG_PERSON_SEQ | — | exists_in | ROL.ROL_PERSON_SEQUENCE | SEVERE | DRAFT — needs review |
| 49 | CVG | CVG_SEX | "IF CNT_JOINT_LIFE_INDICATOR NE N AND CNT_JOINT_NUMBER_OF_LIVES > 1 AND CVG_TYPE = TERM, then CNT_SEX_CODE = CVG_SEX for at least one of the two joint coverage occurrences." | CVG_SEX | CNT_JOINT_LIFE_INDICATOR | ne | N | SEVERE | DRAFT — needs review |
| 50 | CVG | CVG_ISSUE_AGE | "IF CNT_JOINT_LIFE_INDICATOR NE N AND CNT_JOINT_NUMBER_OF_LIVES > 1 AND CVG_TYPE = TERM, then CNT_ISSUE_AGE = CVG_ISSUE_AGE for at least one occurrence." | CVG_ISSUE_AGE | CNT_JOINT_LIFE_INDICATOR | ne | N | SEVERE | DRAFT — needs review |
| 51 | CVG | CVG_ISSUE_DATE | "IF CVG_TYPE = TERM OR ANNT or AH, then CNT_ISSUE_DATE = CVG_ISSUE_DATE for that occurrence. ELSE CVG_ISSUE_DATE >= CNT_ISSUE DATE. If conditions not satisfied, send severe messages." | CVG_ISSUE_DATE | CVG_TYPE | in | TERM,ANNT,AH | SEVERE | DRAFT — needs review |
| 52 | CVG | CVG_MATURE_EXPIRE_DATE | "IF CVG_TYPE = TERM OR ANNT or AH then CNT_MATURE_EXPIRE_DATE = CVG_MATURE_EXPIRE_DATE. ELSE CVG_MATURE_EXPIRE_DATE <= CNT_MATURE_EXPIRE_DATE. If conditions not satisfied, send severe messages." | CVG_MATURE_EXPIRE_DATE | CVG_TYPE | in | TERM,ANNT,AH | SEVERE | DRAFT — needs review |
| 53 | CVG | CVG_PAYUP_DATE | "IF CVG_TYPE = TERM OR ANNT, then CNT_PAYUP_DATE = CVG_PAYUP_DATE for that occurrence. If condition not satisfied, send severe message." | CVG_PAYUP_DATE | CVG_TYPE | in | TERM,ANNT | SEVERE | DRAFT — needs review |
| 54 | CVG | CVG_CURR_PROB_LIVING | "If CVG_PRODUCT_TYPE = J OR Z OR (CVG_PRODUCT_TYPE = E AND CNT_JOINT_NUMBER_OF_LIVES > 1), then this field NE blank. ELSE, this field = blank. If conditions not satisifed, send severe message." | CVG_CURR_PROB_LIVING | CVG_PRODUCT_TYPE | in | J,Z | SEVERE | DRAFT — needs review |
| 55 | CVG | CVG_GUAR_PROB_LIVING | "If CVG_PRODUCT_TYPE = J OR Z OR (CVG_PRODUCT_TYPE = E AND CNT_JOINT_NUMBER_OF_LIVES > 1), then this field NE blank. ELSE, this field = blank. If conditions not satisifed, send severe message." | CVG_GUAR_PROB_LIVING | CVG_PRODUCT_TYPE | in | J,Z | SEVERE | DRAFT — needs review |
| 56 | CNT | CNT_REINS_TYPE | "IF CNT_PRODUCT_TYPE = T, K, L, I, U, V, E, J, Z, or D AND CVG_TYPE = TERM, then this field = CVG_REINS_TYPE. IF CNT_PRODUCT_TYPE = A, W, or B and CVG_TYPE = ANNT, then this field = CVG_REINS_TYPE." | CNT_REINS_TYPE | CNT_PRODUCT_TYPE | in | T,K,L,I,U,V,E,J,Z,D | SEVERE | DRAFT — needs review |
| 57 | CNT | CNT_PLAN_OPTION_ORIGINAL (rule 2) | "If CNT_PLAN_OPTION = C AND CNT_PRODUCT_TYPE = T, K, L, I, U, V, E, J, Z, D then at least one occurrence of CVG_TYPE = COLA must exist." | CNT_PLAN_OPTION_ORIGINAL | CNT_PLAN_OPTION_ORIGINAL | eq | C | SEVERE | DRAFT — needs review |
| 58 | ROL | ROL_PERSON_CODE | "If CNT_JOINT_NUMBER_OF_LIVES = 2, then at least 2 roles must be present (1 & 2). If CNT_JOINT_LIFE_INDICATOR = N, then at least 1 role must be present (I)." | ROL_PERSON_CODE | CNT_JOINT_NUMBER_OF_LIVES | eq | 2 | SEVERE | DRAFT — needs review |
| 59 | ROL | ROL_SEX | "IF ROL_PERSON_CODE = I AND CNT_JOINT_NUMBER_OF_LIVES = 1, then CNT_SEX = ROL_SEX for this occurrence. If condition not satisfied, send severe message." | ROL_SEX | ROL_PERSON_CODE | eq | I | SEVERE | DRAFT — needs review |
| 60 | ADD | ADD_PERSON_SEQUENCE | "EACH ROL_PERSON SEQUENCE should have a corresponding ADD_PERSON SEQUENCE. If not satisfied, send warning message to supplement information." | ADD_PERSON_SEQUENCE | — | exists_in | ROL.ROL_PERSON_SEQUENCE | WARNING | DRAFT — needs review |
| 61 | ADD | ADD_ADDRESS_TYPE | "At least one resident address is required for each role of ROL_PERSON_CODE. If condition not satisfied, send severe message." | ADD_ADDRESS_TYPE | — | exists | R (per ROL_PERSON_CODE) | SEVERE | DRAFT — needs review |
| 62 | CVG | CVG_TEMP_FLAT_END_DATE | "If CVG_TEMP_FLAT_EXTRA = 0, then default this field to CNT_ISSUE_DATE. IF CVG_TEMP_FLAT_EXTRA > 0, then this field's date <= CVG_MATURE_EXPIRE_DATE." | CVG_TEMP_FLAT_END_DATE | CVG_TEMP_FLAT_EXTRA | eq | 0 | SEVERE | DRAFT — needs review |
| 63 | CVG | CVG_TEMP_TABLE_END_DATE | "If CVG_TEMP_TABLE_CODE = 00, then default this field to CNT_ISSUE_DATE. Else, this field <= CVG_MATURE_EXPIRE_DATE." | CVG_TEMP_TABLE_END_DATE | CVG_TEMP_TABLE_CODE | eq | 00 | SEVERE | DRAFT — needs review |
| 64 | CVG | CVG_VALUE_PER_UNIT | "If CVG_TYPE is not equal to TR and not equal to ANNT and not equal to AH, then this field > 0. If conditions not satisfied, send severe message." | CVG_VALUE_PER_UNIT | CVG_TYPE | not_in | TR,ANNT,AH | SEVERE | DRAFT — needs review |

---

## Category 4: Date Comparisons (same table)

| # | Table | Field | Raw Column 7 Text (verbatim) | compare_field | compare_operator | severity | Status |
|---|-------|-------|------------------------------|---------------|------------------|----------|--------|
| 65 | CNT | CNT_MATURE_EXPIRE_DATE | "This date must be > CNT_ISSUE_DATE. If condition not satisfied, send severe message." | CNT_ISSUE_DATE | gt | SEVERE | DRAFT — needs review |
| 66 | CNT | CNT_APPLICATION_DATE | "This date must be <= CNT_ISSUE_DATE. If condition not satisfied, send severe message." | CNT_ISSUE_DATE | lte | SEVERE | DRAFT — needs review |
| 67 | CNT | CNT_PAYUP_DATE | "Paidup date <= contract maturity date. If condition not satisfied, send severe message." | CNT_MATURE_EXPIRE_DATE | lte | SEVERE | DRAFT — needs review |
| 68 | ADD | ADD_SNOW_BIRD_END_DATE | "If the role does not have a snow bird address, this field is blank. ELSE, ADD_SNOW_BIRD_END_DATE > ADD_SNOW_BIRD_BEG_DATE. If conditions not satisfied, send severe messages." | ADD_SNOW_BIRD_BEG_DATE | gt | SEVERE | DRAFT — needs review |

---

## Category 5: Severity-with-Blank-Handling (if blank, send warning)

| # | Table | Field | Raw Column 7 Text (verbatim) | condition | severity | Status |
|---|-------|-------|------------------------------|-----------|----------|--------|
| 69 | CNT | CNT_SERV_AGENT | "If blank, send warning message to augment servicing agent information." | field is blank | WARNING | DRAFT — needs review |
| 70 | CNT | CNT_SERV_AGENCY | "If blank, send warning message to augment servicing agency information." | field is blank | WARNING | DRAFT — needs review |
| 71 | CNT | CNT_BASE_PLAN_CODE | "Default to CNT_POLICY_PLAN_CODE if field is blank and send warning message." | field is blank | WARNING | DRAFT — needs review |
| 72 | ROL | ROL_DISTRIBUTION_CODE | "If this field = 0, then send warning message to supplement information." | field eq 0 | WARNING | DRAFT — needs review |
| 73 | ROL | ROL_HOME_NUMBER | "Phone numbers are not required but warning message should be sent to target to supplement info if this field is blank." | field is blank | WARNING | DRAFT — needs review |
| 74 | ROL | ROL_CELL_NUMBER | "Phone numbers are not required but warning message should be sent to target to supplement info if this field is blank." | field is blank | WARNING | DRAFT — needs review |
| 75 | ROL | ROL_OFFICE_NUMBER | "Phone numbers are not required but warning message should be sent to target to supplement info if this field is blank." | field is blank | WARNING | DRAFT — needs review |
| 76 | ROL | ROL_FAX_NUMBER | "Phone numbers are not required but warning message should be sent to target to supplement info if this field is blank." | field is blank | WARNING | DRAFT — needs review |
| 77 | ROL | ROL_EMAIL | "Emails are not required but warning message should be sent to target to supplement info if field = blank." | field is blank | WARNING | DRAFT — needs review |
| 78 | ROL | ROL_DISTRIBUTION_PERCENT | "This field <= 100%. If condition not satisfied, send severe message." | field > 100 | SEVERE | DRAFT — needs review |
| 79 | ADD | ADD_POSTAL_CODE | "Zip+4 is not required but warning message should be sent to supplement info." | zip+4 missing | WARNING | DRAFT — needs review |
| 80 | CVG | CVG_LEGACY_RIDER_PLAN_CODE | "This field should not be all blanks. The originating system should have some identifying code for the coverage. If condition not satisfied, send message for further information." | field is blank | WARNING | DRAFT — needs review |

---

## Fields Excluded (Informational Notes Only — no actionable rule)

The following fields have Column 7 content that is informational/advisory only, not a validatable rule:

- **CNT_COMPANY_CODE** — restates "must not be blank" (already a field-level rule)
- **CNT_POLICY_NUMBER** — restates "must be present" (already a field-level rule)
- **CNT_PRODUCT_TYPE** — restates "must not be empty/blank" (already a field-level rule)
- **CNT_POLICY_PLAN_CODE** — restates "must not be empty/blank" (already a field-level rule)
- **CNT_POLICY_CODE** — informational note about other restrict codes, no testable rule
- **CNT_ISSUE_COUNTRY** — note about "foreign country" interpretation, no testable rule
- **CNT_ISSUE_STATE** — note about consistency with Address tab allowable list
- **CNT_ISSUE_AGE** — informational: "may not equal JOINT_RATE_AGE if INDICATOR=J"
- **CNT_ISSUE_DATE** — informational: "redundant with coverage tab"
- **CNT_STATUS_DATE** — informational: "checking among Financial/Non-Financial tabs is too complex"
- **CNT_NFO_OPTION** — informational: description of APL codes, no testable rule
- **CVG_SEQUENCE_NUMBER** — informational: uniqueness note (already implicit)
- **CVG_STATUS** — informational: payout status note, no testable rule
- **CVG_RATE_CLASS** — informational: rate class note
- **CVG_PERCENT_RATING** — informational: documentation about rating factor
- **CVG_REINS_TYPE** — informational: "adding blank for completeness"
- **CVG_COVERED** — complex example-based note (not a simple IF/THEN rule)
- **CVG_PLAN_CODE** — restates "must have a plan code" (already a field-level rule)
- **ROL_PERSON_SEQUENCE** — informational: cross-tab consistency note
- **ROL_COVERAGE_SEQUENCE** — informational: role-coverage linkage note
- **ROL_LANGUAGE_CODE** — informational: "proposed field, keep for future"
- **ROL_TERM_DATE** — informational: "if no end-date, field = 99999999"
- **ROL_CITIZENSHIP_COUNTRY** — "ok"
- **ADD_ISSUE_SYSTEM** — "ok"
- **ADD_LAST_NAME** — informational: name truncation note
- **ADD_FIRST_NAME** — informational: name truncation note
- **ADD_MIDDLE_INIT** — "ok"
- **ADD_NAME_PREFIX** — "ok"
- **ADD_NAME_SUFFIX** — "ok"
- **ADD_ADDRESS_1 through ADD_ADDRESS_4** — "ok"
- **ADD_UNIVERSAL_CITY** — informational: field naming note
- **ADD_STATE** — informational: consistency note with US postal codes
- **ADD_SNOW_BIRD_BEG_DATE** — informational: "blank if no snow bird address"
- **ADD_ADDRESS_STATUS** — informational: "unclear of intention"
- **ADD_COUNTRY_CODE** — informational: "superfluous" note
- **ADD_BAD_ADDRESS_IND** — "ok"

---

## VERIFICATION SAMPLE (15% of actionable rules — 12 rules sampled)

Below is a randomly-selected sample of 12 rules (spread across all 5 categories and all 4 tables) for accuracy review:

### Sample 1 — Category 1 (Same-table), CNT, Rule #6
**Field:** CNT_JOINT_RATE_AGE  
**Raw Column 7:** "IF CNT_JOINT_LIFE_INDICATOR = F or N, then CNT_JOINT_RATE_AGE = 0. If condition not satisfied, send severe messsage."  
**Drafted structure:**  
- compare_field: CNT_JOINT_RATE_AGE  
- precondition_field: CNT_JOINT_LIFE_INDICATOR  
- precondition_operator: in  
- precondition_value: F,N  
- expected_value: 0  
- severity: SEVERE  
**DRAFT — needs review**

### Sample 2 — Category 1 (Same-table), ROL, Rule #15
**Field:** ROL_CONTRACT_OWNER_IND  
**Raw Column 7:** "If ROL_PERSON_CODE NE O, then this field = blank. If condition not satisfied, send severe message."  
**Drafted structure:**  
- compare_field: ROL_CONTRACT_OWNER_IND  
- precondition_field: ROL_PERSON_CODE  
- precondition_operator: ne  
- precondition_value: O  
- expected_value: blank  
- severity: SEVERE  
**DRAFT — needs review**

### Sample 3 — Category 1 (Same-table), CVG, Rule #26
**Field:** CVG_DIVIDEND_OPTION_1  
**Raw Column 7:** "IF CVG_PRODUCT_TYPE = A, W, B, U, V, E, J, Z, H, then this field = blank. (Dividends are n/a.) If condition not satisfied, send severe message."  
**Drafted structure:**  
- compare_field: CVG_DIVIDEND_OPTION_1  
- precondition_field: CVG_PRODUCT_TYPE  
- precondition_operator: in  
- precondition_value: A,W,B,U,V,E,J,Z,H  
- expected_value: blank  
- severity: SEVERE  
**DRAFT — needs review**

### Sample 4 — Category 2 (Cross-table equality), CVG, Rule #40
**Field:** CVG_PRODUCT_TYPE  
**Raw Column 7:** "MUST EQUAL CNT_PRODUCT_TYPE if tab present. Send severe message if not satisfied."  
**Drafted structure:**  
- compare_field: CVG_PRODUCT_TYPE  
- compare_table: CNT  
- compare_column: CNT_PRODUCT_TYPE  
- severity: SEVERE  
**DRAFT — needs review**

### Sample 5 — Category 2 (Cross-table equality), ADD, Rule #44
**Field:** ADD_COMPANY_CODE  
**Raw Column 7:** "CNT_COMPANY_CODE = ADD_COMPANY_CODE. Send severe message if not satisfied."  
**Drafted structure:**  
- compare_field: ADD_COMPANY_CODE  
- compare_table: CNT  
- compare_column: CNT_COMPANY_CODE  
- severity: SEVERE  
**DRAFT — needs review**

### Sample 6 — Category 3 (Cross-table conditional), CVG, Rule #51
**Field:** CVG_ISSUE_DATE  
**Raw Column 7:** "IF CVG_TYPE = TERM OR ANNT or AH, then CNT_ISSUE_DATE = CVG_ISSUE_DATE for that occurrence. ELSE CVG_ISSUE_DATE >= CNT_ISSUE DATE. If conditions not satisfied, send severe messages."  
**Drafted structure:**  
- compare_field: CVG_ISSUE_DATE  
- precondition_field: CVG_TYPE  
- precondition_operator: in  
- precondition_value: TERM,ANNT,AH  
- then: must equal CNT.CNT_ISSUE_DATE  
- else: must be >= CNT.CNT_ISSUE_DATE  
- severity: SEVERE  
**DRAFT — needs review**

### Sample 7 — Category 3 (Cross-table conditional), ROL, Rule #59
**Field:** ROL_SEX  
**Raw Column 7:** "IF ROL_PERSON_CODE = I AND if CNT_JOINT_NUMBER_OF_LIVES = 1, then CNT_SEX = ROL_SEX for this occurrence. If condition not satisfied, send severe message."  
**Drafted structure:**  
- compare_field: ROL_SEX  
- precondition_field: ROL_PERSON_CODE  
- precondition_operator: eq  
- precondition_value: I  
- additional_precondition: CNT.CNT_JOINT_NUMBER_OF_LIVES = 1  
- then: must equal CNT.CNT_SEX_CODE  
- severity: SEVERE  
**DRAFT — needs review**

### Sample 8 — Category 3 (Cross-table conditional), CVG, Rule #54
**Field:** CVG_CURR_PROB_LIVING  
**Raw Column 7:** "If CVG_PRODUCT_TYPE = J OR Z OR (CVG_PRODUCT_TYPE = E AND CNT_JOINT_NUMBER_OF_LIVES > 1), then this field NE blank AND there must be a separate occurrence for each joint insured. ELSE, this field = blank. If conditions not satisifed, send severe message."  
**Drafted structure:**  
- compare_field: CVG_CURR_PROB_LIVING  
- precondition_field: CVG_PRODUCT_TYPE  
- precondition_operator: in  
- precondition_value: J,Z  
- OR: CVG_PRODUCT_TYPE = E AND CNT.CNT_JOINT_NUMBER_OF_LIVES > 1  
- then: must not be blank  
- else: must be blank  
- severity: SEVERE  
**DRAFT — needs review**

### Sample 9 — Category 4 (Date comparison), CNT, Rule #67
**Field:** CNT_PAYUP_DATE  
**Raw Column 7:** "Paidup date <= contract maturity date. If condition not satisfied, send severe message."  
**Drafted structure:**  
- compare_field: CNT_MATURE_EXPIRE_DATE  
- compare_operator: lte  
- severity: SEVERE  
**DRAFT — needs review**

### Sample 10 — Category 4 (Date comparison), ADD, Rule #68
**Field:** ADD_SNOW_BIRD_END_DATE  
**Raw Column 7:** "If the role does not have a snow bird address, this field is blank. ELSE, ADD_SNOW_BIRD_END_DATE > ADD_SNOW_BIRD_BEG_DATE. If conditions not satisfied, send severe messages."  
**Drafted structure:**  
- compare_field: ADD_SNOW_BIRD_BEG_DATE  
- compare_operator: gt  
- precondition: field is not blank (snow bird address exists)  
- severity: SEVERE  
**DRAFT — needs review**

### Sample 11 — Category 5 (Severity-with-blank), ROL, Rule #73
**Field:** ROL_HOME_NUMBER  
**Raw Column 7:** "Phone numbers are not required but warning message should be sent to target to supplement info if this field is blank."  
**Drafted structure:**  
- condition: field is blank  
- severity: WARNING  
- note: Field is optional; blank triggers info-supplementing warning only  
**DRAFT — needs review**

### Sample 12 — Category 5 (Severity-with-blank), CNT, Rule #69
**Field:** CNT_SERV_AGENT  
**Raw Column 7:** "If blank, send warning message to augment servicing agent information."  
**Drafted structure:**  
- condition: field is blank  
- severity: WARNING  
- note: Already implemented as default_then_warn / not_blank WARNING in current pipeline  
**DRAFT — needs review**

---

## Summary Statistics

| Category | Count | Tables Represented |
|----------|-------|--------------------|
| 1. Same-table cross-field | 37 rules | CNT (13), ROL (7), CVG (17) |
| 2. Cross-table equality | 10 rules | CVG (3), ROL (3), ADD (3), CNT (1) |
| 3. Cross-table conditional | 17 rules | CVG (11), ROL (3), ADD (2), CNT (1) |
| 4. Date comparisons | 4 rules | CNT (3), ADD (1) |
| 5. Severity-with-blank | 12 rules | CNT (3), ROL (6), ADD (1), CVG (1) |
| **TOTAL actionable** | **80 rules** | All 4 tables |
| Informational (excluded) | 34 fields | — |

**Note:** Some fields produce multiple rules (e.g., CNT_JOINT_RATE_AGE_REASON_CODE has 3 conditional branches), hence the total rule count exceeds the total field count.

---

*End of worklist. All rules marked DRAFT — needs review before implementation.*
