# Policy Loader — ETL Validation POC
## Kiro Spec: Python Validation Code Generation
### Tables: Contract · Premium Billing · Financial History · Non-Financial History

---

## HOW TO USE THIS SPEC IN KIRO

1. Open Kiro IDE and create a new Spec (`Ctrl+Shift+P` → **New Spec**)
2. Paste the contents of this file into the Spec prompt
3. Also attach the original Excel file `DB_Section_v2_New_-_5-4-26_from_NByers.xlsm` as additional context
4. Kiro will generate Requirements → Design → Tasks in sequence
5. Review each section before approving — do not skip the review step

---

## PART 1 — REQUIREMENTS

### Project Context
This is a Proof of Concept (POC) to replace the KNIME batch ETL engine with a Python-based validation pipeline running on AWS Lambda. The validation logic reads staging data from a Neon PostgreSQL database and classifies each row as CLEAN, WARNING, or SEVERE based on business rules defined in the field specification spreadsheet.

### Scope
Generate one Python validation module per table:
- `validate_cnt.py` — Contract table (32 fields)
- `validate_prm.py` — Premium Billing table (30 fields)
- `validate_fin.py` — Financial History table (56 fields)
- `validate_nfn.py` — Non-Financial History table (64 fields)

Each module must be independently deployable as an AWS Lambda function.

### General Rules Applying to ALL Tables
1. Validation is performed at the **application level only** — the database has primary keys and unique keys only; no CHECK constraints.
2. Every field-level validation must produce either:
   - `SEVERE` — the row is held back and must not proceed to downstream processing
   - `WARNING` — the row proceeds but is flagged for manual review
   - `None` — the field passed validation
3. After all field validations run, each row is classified with a `ROW_SEVERITY` column:
   - `CLEAN` — all field validations returned None
   - `WARNING` — at least one WARNING, no SEVERE
   - `SEVERE` — at least one SEVERE (regardless of warnings)
4. The validation result for each field must be stored in a column named `VAL_<FIELD_NAME>`.
5. All validation functions must accept a Pandas DataFrame and return a Pandas DataFrame.
6. A single entry-point function `validate_<prefix>(df)` must call all field validations in sequence and return the classified DataFrame.
7. Validation output DataFrame must be split at the end into three separate DataFrames: `clean_df`, `warning_df`, `severe_df`.

### Severity Classification Rules
- If the spec says **"send severe message"** → generate a `SEVERE` check
- If the spec says **"send warning message"** → generate a `WARNING` check
- If the spec says **"default to X if blank"** → apply the default silently first, then validate
- If the spec says **"must not be empty/blank"** → SEVERE
- If the spec says **"should not have spaces/blank"** → SEVERE

### Cross-Reference Rules
Cross-reference validations that compare a field in this table against a field in the CNT (Contract) table (e.g., `CNT_COMPANY_CODE = PRM_COMPANY_CODE`) must be implemented as **inter-table joins** in a separate function called `validate_<prefix>_cross_table(df, cnt_df)` that accepts both the current table DataFrame and the CNT DataFrame as inputs.

---

## PART 2 — DESIGN

### Technology Stack
- Language: Python 3.12
- Library: Pandas (no PySpark, no Spark dependency)
- Deployment target: AWS Lambda
- Database: Neon PostgreSQL (standard psycopg2 connection)
- Entry point: `lambda_handler(event, context)` per function

### Module Structure (same pattern for all 4 tables)

```
validate_cnt.py
├── validate_cnt_issue_system(df)
├── validate_cnt_company_code(df)
├── validate_cnt_policy_number(df)
├── ... (one function per field)
├── validate_cnt_cross_table(df, cnt_df)      ← inter-table cross-refs
├── validate_cnt(df, cnt_df=None)             ← master orchestrator
├── classify_severity(df)                     ← row-level classification
├── split_results(df)                         ← returns clean, warning, severe
└── lambda_handler(event, context)            ← AWS Lambda entry point
```

### Date Validation Standard
All DATE fields must validate:
1. Not null / not blank
2. Parseable as `YYYYMMDD` format
3. Result is a valid calendar date (e.g., month 1–12, day 1–31 per month)

```python
def is_valid_date(series):
    try:
        pd.to_datetime(series, format='%Y%m%d', errors='coerce')
        return pd.to_datetime(series, format='%Y%m%d', errors='coerce').notna()
    except:
        return pd.Series([False] * len(series))
```

### Numeric Validation Standard
All NUMERIC fields must validate:
1. Not null (unless spec says "allow blank if not applicable")
2. Convertible to float
3. Precision check where specified (e.g., NUMERIC(14,5) means max 14 digits, 5 decimal places)

### CHAR Length Validation Standard
For CHAR fields with a fixed length (e.g., `Must be exactly 2 character`):
- Trim whitespace first
- Check `len(value) == N`
- If not exactly N characters, generate SEVERE

---

## PART 3 — TABLE SPECIFICATIONS

---

### TABLE 1: CONTRACT (Prefix: CNT) — 32 Fields

**Primary Key:** CNT_COMPANY_CODE + CNT_POLICY_NUMBER
**Tab-level rule:** Contract tab is always required. If CNT_COMPANY_CODE is missing, send SEVERE.

#### Field Specifications

| Field Name | Type | Length | Precision | Severity | Rule |
|---|---|---|---|---|---|
| CNT_ISSUE_SYSTEM | CHAR | 2 | — | SEVERE | Not blank, exactly 2 chars |
| CNT_COMPANY_CODE | CHAR | 3 | — | SEVERE | Not blank, exactly 3 chars |
| CNT_POLICY_NUMBER | CHAR | 15 | — | SEVERE | Not blank, up to 15 chars |
| CNT_PRODUCT_TYPE | CHAR | 1 | — | SEVERE | Not blank; must be one of: A W B T K L I U V E J Z H D |
| CNT_POLICY_PLAN_CODE | CHAR | 10 | — | SEVERE | Not blank, exactly 10 chars |
| CNT_BASE_PLAN_CODE | CHAR | 10 | — | WARNING | Default to CNT_POLICY_PLAN_CODE if blank, send WARNING |
| CNT_POLICY_CODE | CHAR | 1 | — | — | Must be one of: X A C I O P S 5 J M B Z D |
| CNT_ISSUE_COUNTRY | CHAR | 2 | — | — | Must be one of: US CA 03 |
| CNT_ISSUE_STATE | CHAR | 2 | — | — | Not blank, exactly 2 chars |
| CNT_RESIDENT_STATE | CHAR | 2 | — | SEVERE | Must match Address tab Owner Role resident state |
| CNT_POLICY_STATUS | CHAR | 2 | — | — | Must be one of: 00 01 02 03 04 05 06 07 08 09 10 21 22 23 24 25 31 32 33 34 35 97 90 99 |
| CNT_ISSUE_AGE | INT | 3 | — | SEVERE | Numeric, not blank |
| CNT_ISSUE_DATE | DATE | 8 | — | SEVERE | Valid YYYYMMDD date |
| CNT_STATUS_DATE | DATE | 8 | — | — | Valid YYYYMMDD date if present |
| CNT_MATURE_EXPIRE_DATE | DATE | 8 | — | SEVERE | Valid date AND must be > CNT_ISSUE_DATE |
| CNT_APPLICATION_DATE | DATE | 8 | — | SEVERE | Valid date AND must be <= CNT_ISSUE_DATE |
| CNT_PARTICIPATION_STATUS | CHAR | 1 | — | — | Must be P or N; if PRODUCT_TYPE not in T K L D → must be N (WARNING) |
| CNT_GUAR_PAR_STATUS | CHAR | 1 | — | — | Must be one of: N C E O |
| CNT_NFO_OPTION | CHAR | 1 | — | — | Must be one of: A E R O N L T S U P |
| CNT_SEX_CODE | CHAR | 1 | — | SEVERE | Must be one of: 1 M 2 F 3 B J N E; cross-ref: if B then JOINT_LIFE_INDICATOR=F; if J then =J |
| CNT_JOINT_LIFE_INDICATOR | CHAR | 1 | — | SEVERE | Must be F J or N; cross-ref: if PRODUCT_TYPE in K J Z → must be F or J; if E → F J or N |
| CNT_JOINT_NUMBER_OF_LIVES | CHAR | 1 | — | WARNING | >= 1; if =1 then JOINT_RATE_AGE_REASON_CODE must be G (WARNING) |
| CNT_JOINT_RATE_AGE | INT | 3 | — | SEVERE | If JOINT_LIFE_INDICATOR=F or N → must be 0 |
| CNT_JOINT_RATE_AGE_REASON_CODE | CHAR | 1 | — | SEVERE | If INDICATOR=N→blank; if F→F/G/P; if J→A/B/C/D |
| CNT_PAYUP_DATE | DATE | 8 | — | SEVERE | Valid date AND <= CNT_MATURE_EXPIRE_DATE |
| CNT_QUALIFICATION_CODE | CHAR | 1 | — | SEVERE | Must be one of: N Q O K S H I T P R D Z A E U C; if Q/K/I/T/P/R/U → PRODUCT_TYPE must be A/W/B |
| CNT_PLAN_OPTION_ORIGINAL | CHAR | 1 | — | SEVERE | Must be L V R C or blank; if PRODUCT_TYPE=A/W/B/H → must be blank |
| CNT_GRACE_EXPIRY_DATE | DATE | 8 | — | SEVERE | If PRODUCT_TYPE=W/B/H → must be blank; else valid date |
| CNT_SERV_AGENT | CHAR | 12 | — | WARNING | If blank, send WARNING |
| CNT_SERV_AGENCY | CHAR | 12 | — | WARNING | If blank, send WARNING |
| CNT_PHONE_AUTH_TRNSFR | CHAR | 1 | — | — | Must be Y or N |
| CNT_REINS_TYPE | CHAR | 1 | — | SEVERE | Must be A F or blank |

---

### TABLE 2: PREMIUM BILLING (Prefix: PRM) — 30 Fields

**Primary Key:** PRM_COMPANY_CODE + PRM_POLICY_NUMBER + PRM_PARENT_TABLE_ID + PRM_PARENT_SEQ_NUM + PRM_VALUES_FROM
**Tab-level rule:** If PRM_PRODUCT_TYPE = W or B, this tab should not be present (SEVERE if present).

#### Field Specifications

| Field Name | Type | Length | Precision | Severity | Rule |
|---|---|---|---|---|---|
| PRM_ISSUE_SYSTEM | CHAR | 2 | — | SEVERE | Not blank, exactly 2 chars |
| PRM_COMPANY_CODE | CHAR | 3 | — | SEVERE | Not blank; must equal CNT_COMPANY_CODE (cross-table) |
| PRM_POLICY_NUMBER | CHAR | 15 | — | SEVERE | Not blank; must equal CNT_POLICY_NUMBER (cross-table) |
| PRM_PRODUCT_TYPE | CHAR | 1 | — | SEVERE | Must be one of: A W B T K L I U V E J Z H D; must equal CNT_PRODUCT_TYPE (cross-table) |
| PRM_PARENT_TABLE_ID | CHAR | 3 | — | SEVERE | Not blank, exactly 3 chars |
| PRM_PARENT_SEQ_NUM | CHAR | 3 | — | SEVERE | Must equal parent tab sequence number |
| PRM_VALUES_FROM | CHAR | 1 | — | SEVERE | Must be S or E |
| PRM_MODE_PREMIUM | NUMERIC | 14 | 5 | SEVERE | Not blank, numeric, >= 0 |
| PRM_PREMIUM_FORCED | CHAR | 1 | — | — | Must be one of: Y L N blank |
| PRM_PREMIUM_FORCED_END_DATE | DATE | 8 | — | SEVERE | Valid date AND <= CNT_MATURE_EXPIRE_DATE; if PRM_PREMIUM_FORCED != Y → default to CNT_ISSUE_DATE |
| PRM_BILLING_FORM | CHAR | 1 | — | — | Must be one of: 1 2 3 4 5 N S |
| PRM_MODE | CHAR | 2 | — | — | Must be one of: 01 03 06 12 or blank (flexible premium) |
| PRM_BILLED_TO_DATE | DATE | 8 | — | — | Valid YYYYMMDD if present |
| PRM_PAID_TO_DATE | DATE | 8 | — | — | Valid YYYYMMDD if present |
| PRM_BILL_EXTRACT_DATE | DATE | 8 | — | — | Valid YYYYMMDD if present |
| PRM_COMBINED_BILL_IND | CHAR | 1 | — | — | Must be C or blank |
| PRM_GROUP_NUMBER | CHAR | 10 | — | SEVERE | If Group_Billing tab not present → must be blank; else must equal GBL_GROUP_NUMBER |
| PRM_GROUP_NUMBER_2 | CHAR | 10 | — | — | Not blank, exactly 10 chars if present |
| PRM_NEXT_PAC_DATE | DATE | 8 | — | SEVERE | If PRM_BILLING_FORM != 4 → must be blank; else valid YYYYMMDD |
| PRM_DRAFT_DAY | CHAR | 2 | — | SEVERE | If BILLING_FORM not N/S → not blank AND between 1 and 28; else blank |
| PRM_DRAFT_USE | CHAR | 1 | — | SEVERE | If BILLING_FORM not N/S → not blank; else blank; must be 1 2 3 if present |
| PRM_PAC_IND | CHAR | 1 | — | SEVERE | If BILLING_FORM != 4 → must be blank; must be one of: blank 1 3 |
| PRM_AUTO_PAC_DATE | DATE | 8 | — | SEVERE | If BILLING_FORM != 4 → must be blank; else valid YYYYMMDD |
| PRM_PREMIUM_PER_UNIT | NUMERIC | 14 | 5 | WARNING | Numeric, >= 0; if > 999.99999 → send WARNING to validate |
| PRM_MONTHLY_MODE_FACTOR | NUMERIC | 14 | 5 | SEVERE | Numeric, not blank |
| PRM_QUARTERLY_MODE_FACTOR | NUMERIC | 14 | 5 | SEVERE | Numeric, not blank |
| PRM_SEMI_ANNUAL_MODE_FACTOR | NUMERIC | 14 | 5 | SEVERE | Numeric, not blank |
| PRM_ANNUAL_MODE_FACTOR | NUMERIC | 14 | 5 | SEVERE | Numeric, not blank |
| PRM_ADVANCED_PREM_PAY_OPTION | CHAR | 1 | — | — | Value TBD per system |
| PRM_PARENT_TABLE_ID (dup) | CHAR | 5 | — | — | Duplicate field — flag WARNING if differs from first occurrence |

---

### TABLE 3: FINANCIAL HISTORY (Prefix: FIN) — 56 Fields

**Primary Key:** FIN_COMPANY_CODE + FIN_POLICY_NUMBER + FIN_RECORD_COUNTER
**Tab-level rule:** This tab may not be present for all policies — not an error if absent.

#### Field Specifications

| Field Name | Type | Length | Precision | Severity | Rule |
|---|---|---|---|---|---|
| FIN_ISSUE_SYSTEM | CHAR | 2 | — | SEVERE | Not blank, exactly 2 chars |
| FIN_COMPANY_CODE | CHAR | 3 | — | SEVERE | Not blank; must equal CNT_COMPANY_CODE (cross-table) |
| FIN_POLICY_NUMBER | CHAR | 15 | — | SEVERE | Not blank; must equal CNT_POLICY_NUMBER (cross-table) |
| FIN_PRODUCT_TYPE | CHAR | 1 | — | SEVERE | Must be one of: A W B T K L I U V E J Z H D |
| FIN_RECORD_COUNTER | INT | 9 | — | — | Numeric |
| FIN_PARENT_SEQ_NUM | INT | 2 | — | SEVERE | Not blank, numeric, >= 1 |
| FIN_TRANS_DATE | DATE | 8 | — | SEVERE | Valid YYYYMMDD |
| FIN_TRANS_DUE_DATE | DATE | 8 | — | — | Valid YYYYMMDD if present; blank allowed for flexible premium |
| FIN_EFFECTIVE_DATE | DATE | 8 | — | SEVERE | Valid YYYYMMDD |
| FIN_TRANS_CODE | CHAR | 4 | — | SEVERE | Not blank, exactly 4 chars; see allowable values list in Excel (0001–7006 range) |
| FIN_GROSS_AMOUNT | NUMERIC | 8 | 2 | SEVERE | Numeric (can be negative for reversals) |
| FIN_PREMIUM_LOAD | NUMERIC | 8 | 2 | — | Numeric if present |
| FIN_FREE_WITHDRAWAL_AMT | NUMERIC | 8 | 2 | — | Numeric if present |
| FIN_PREMIUM_TAXFIN_WITHHELD | NUMERIC | 8 | 2 | — | Numeric if present |
| FIN_TOTAL_TRX_FEE_AMT | NUMERIC | 8 | 2 | — | Numeric if present |
| FIN_ADMIN_CHARGES | NUMERIC | 8 | 2 | — | Numeric if present |
| FIN_FED_TAXFIN_WITHHELD | NUMERIC | 8 | 2 | — | Numeric if present |
| FIN_STATE_TAXFIN_WITHHELD | NUMERIC | 8 | 2 | — | Numeric if present |
| FIN_NET_AMOUNT | NUMERIC | 11 | 2 | SEVERE | Numeric, not blank |
| FIN_SURRENDER_CHARGE_AMT | NUMERIC | 11 | 2 | — | Numeric if present |
| FIN_BONUS_AMT | NUMERIC | 11 | 2 | — | Numeric if present |
| FIN_LOAN_ADV_INT | NUMERIC | 11 | 2 | SEVERE | If no loan on policy → must be 0 |
| FIN_LOAN_REPAY_AMT | NUMERIC | 11 | 2 | SEVERE | If no loan on policy → must be 0 |
| FIN_LOAN_TYPE | CHAR | 1 | — | SEVERE | If no loan → blank; else must be P N A |
| FIN_LOAN_SEQ_NUM | INT | 2 | — | SEVERE | If no loan → blank; else numeric |
| FIN_MEMO_CODE | CHAR | 2 | — | — | Exactly 2 chars if present |
| FIN_FIN_YEAR | INT | 4 | — | SEVERE | If CNT_QUALIFICATION_CODE = N → must be blank |
| FIN_MONTH_COUNT | INT | 3 | — | SEVERE | If FIN_TRANS_CODE = 0011 → must NOT be 0 |
| FIN_COST_BASIS | NUMERIC | 11 | 2 | — | Numeric if present |
| FIN_REVERSAL_IND | CHAR | 1 | — | — | Must be R or blank |
| FIN_TRX_FEE_OVERRIDE | CHAR | 1 | — | — | Must be Y or blank |
| FIN_TRX_FEE_OVERRIDE_AMT | NUMERIC | 11 | 2 | — | Numeric; can be 0 regardless of override flag |
| FIN_TAX_FORM_OVERRIDE | CHAR | 1 | — | SEVERE | Must be Y or blank; if CNT_QUALIFICATION_CODE=N → must be blank |
| FIN_USER_AREA | CHAR | 8 | — | — | Exactly 8 chars if present |
| FIN_SOURCE_CODE | CHAR | 2 | — | — | Exactly 2 chars if present |
| FIN_REDUCTION_ADJUST_AMT | NUMERIC | 11 | 2 | SEVERE | If TRANS_CODE not 4103 or 4104 → must be 0 |
| FIN_PAID_TO_DATE | DATE | 8 | — | — | Valid YYYYMMDD if present |
| FIN_LOAN_INTEREST_METHOD | CHAR | 1 | — | SEVERE | If no loan → blank; else must be 1 or 2 |
| FIN_LOAN_INTEREST_TYPE | CHAR | 1 | — | SEVERE | If no loan → blank; else must be F V A |
| FIN_TERM_DIV_INT | NUMERIC | 8 | 2 | SEVERE | If PRODUCT_TYPE not L or D → must be 0 |
| FIN_PREMIUM_REFUND | NUMERIC | 8 | 2 | — | Numeric if present |
| FIN_PAID_UP_ADDITION_SURR | NUMERIC | 9 | 2 | — | Numeric if present |
| FIN_FED_PREMIUM_TAX_OVERRIDE_IND | CHAR | 1 | — | — | Must be Y A or blank |
| FIN_FED_PREMIUM_TAX_OVERRIDE | NUMERIC | 11 | 2 | SEVERE | If IND = blank → must be 0 |
| FIN_STATE_PREMIUM_TAX_OVERRIDE_IND | CHAR | 1 | — | — | Must be Y A or blank |
| FIN_STATE_PREMIUM_TAX_OVERRIDE | NUMERIC | 11 | 2 | SEVERE | If IND = blank → must be 0 |
| FIN_BILLING_FORM | CHAR | 1 | — | — | Must be one of: 1 2 3 4 5 6 or blank |
| FIN_MODE | CHAR | 1 | — | — | Must be M Q S A or blank |
| FIN_ENCUMBRANCE_IND | CHAR | 1 | — | — | Must be Y or blank |
| FIN_ACCUM_DVD_ENCUMBRANCE | CHAR | 1 | — | — | Must be Y or blank |
| FIN_PAID_UP_ADDS_ENCUMBRANCE | CHAR | 1 | — | — | Must be Y or blank |
| FIN_UNAPPLIED_DVD_ENCUMBRANCE | CHAR | 1 | — | — | Must be Y or blank |
| FIN_PUAR_PUA_ENCUMBRANCE | CHAR | 1 | — | — | Must be Y or blank |
| FIN_FLEX_PUA_ENCUMBRANCE | CHAR | 1 | — | — | Must be Y or blank |
| FIN_BASE_POL_ENCUMBRANCE | CHAR | 1 | — | — | Must be Y or blank |
| FIN_DVD_AMT | NUMERIC | 11 | 2 | SEVERE | If PRODUCT_TYPE in A W B U V E J Z H → must be 0 |

---

### TABLE 4: NON-FINANCIAL HISTORY (Prefix: NFN) — 64 Fields

**Primary Key:** NFN_COMPANY_CODE + NFN_POLICY_NUMBER + NFN_SEQUENCE_NUMBER
**Tab-level rule:** This tab may or may not be present — not an error if absent. Multiple occurrences per policy are expected.

#### Field Specifications

| Field Name | Type | Length | Precision | Severity | Rule |
|---|---|---|---|---|---|
| NFN_ISSUE_SYSTEM | CHAR | 2 | — | SEVERE | Not blank, exactly 2 chars |
| NFN_COMPANY_CODE | CHAR | 3 | — | SEVERE | Not blank; must equal CNT_COMPANY_CODE (cross-table) |
| NFN_POLICY_NUMBER | CHAR | 15 | — | SEVERE | Not blank; must equal CNT_POLICY_NUMBER (cross-table) |
| NFN_PRODUCT_TYPE | CHAR | 1 | — | SEVERE | Must be one of: A W B T K L I U V E J Z H D; must equal CNT_PRODUCT_TYPE (cross-table) |
| NFN_SEQUENCE_NUMBER | CHAR | 4 | — | — | Exactly 4 chars |
| NFN_PARENT_TABLE_ID | CHAR | 3 | — | SEVERE | Not blank, exactly 3 chars |
| NFN_PARENT_SEQ_NUM | INT | 2 | — | SEVERE | Not blank, numeric |
| NFN_PHASE_CODE | CHAR | 3 | — | — | Valid if present |
| NFN_PERSON_CODE | CHAR | 1 | — | SEVERE | Must be one of: I 1 2; must correspond to a ROLES tab occurrence |
| NFN_TRANS_DATE | DATE | 8 | — | SEVERE | Valid YYYYMMDD |
| NFN_EFFECTIVE_DATE | DATE | 8 | — | SEVERE | Valid YYYYMMDD |
| NFN_TRX_CODE | CHAR | 4 | — | SEVERE | Not blank, exactly 4 chars; must be one of: C001 C002 C003 C004 C005 C006 C007 C008 C009 C010 C011 C012 C013 C014 C015 C016 C017 C018 C019 C020 C021 C022 C023 C024 C025 C026 C027 C028 C029 80CA (see Excel for full list) |
| NFN_REVERSAL_IND | CHAR | 1 | — | — | Must be R or blank |
| NFN_UNITS_OLD | NUMERIC | 11 | 5 | SEVERE | If PRODUCT_TYPE in A W B H → must be blank; if units not changing → blank |
| NFN_UNITS_NEW | NUMERIC | 11 | 5 | SEVERE | If PRODUCT_TYPE in A W B H → must be blank; if units not changing → blank |
| NFN_VALUE_PER_UNIT_OLD | NUMERIC | 7 | 2 | SEVERE | If PRODUCT_TYPE in A W B H → must be blank; if VPU not changing → blank |
| NFN_VALUE_PER_UNIT_NEW | NUMERIC | 7 | 2 | SEVERE | If PRODUCT_TYPE in A W B H → must be blank; if VPU not changing → blank |
| NFN_RATE_CLASS_OLD | CHAR | 2 | — | SEVERE | If rate class not changing → must be blank |
| NFN_RATE_CLASS_NEW | CHAR | 2 | — | SEVERE | If rate class not changing → must be blank |
| NFN_SEX_CODE_OLD | CHAR | 1 | — | SEVERE | If sex code not changing → blank; else must be 1 2 3 B J |
| NFN_SEX_CODE_NEW | CHAR | 1 | — | SEVERE | If sex code not changing → blank; else must be 1 2 3 B J |
| NFN_MODE_OLD | CHAR | 2 | — | SEVERE | If PRODUCT_TYPE=W or B → blank; if mode not changing → blank; else 01 03 06 12 or blank |
| NFN_MODE_NEW | CHAR | 2 | — | SEVERE | If PRODUCT_TYPE=W or B → blank; if mode not changing → blank; else 01 03 06 12 or blank |
| NFN_OPTION_OLD | CHAR | 1 | — | SEVERE | If PRODUCT_TYPE in A W B H → blank; if DBO not changing → blank; else L V R C |
| NFN_OPTION_NEW | CHAR | 1 | — | SEVERE | If PRODUCT_TYPE in A W B H → blank; if DBO not changing → blank; else L V R C |
| NFN_PLANNED_PREM_OLD | NUMERIC | 8 | 2 | SEVERE | If PRODUCT_TYPE in T K L H D → must be 0; else 0 or numeric |
| NFN_PLANNED_PREM_NEW | NUMERIC | 8 | 2 | SEVERE | If PRODUCT_TYPE in T K L H D → must be 0; else 0 or numeric |
| NFN_DIV_OPTION_OLD | CHAR | 1 | — | SEVERE | If PRODUCT_TYPE in A W B U V E J Z H → blank; else must be 1 2 3 4 5 or blank if not changing |
| NFN_DIV_OPTION_NEW | CHAR | 1 | — | SEVERE | If PRODUCT_TYPE in A W B U V E J Z H → blank; else must be 1 2 3 4 5 or blank if not changing |
| NFN_COST_OF_LIVING_INCR | NUMERIC | 9 | 3 | SEVERE | If PRODUCT_TYPE in A W B H → blank; if COLA not applicable → blank |
| NFN_BENEFIT_TYPE | CHAR | 2 | — | SEVERE | Not blank if benefit transaction; exactly 2 chars |
| NFN_BENEFIT_SUB_TYPE | CHAR | 1 | — | SEVERE | If not applicable → blank; else must match BNF_BENEFIT_SUB_TYPE |
| NFN_BENEFIT_ISSUE_AGE | INT | 2 | — | SEVERE | If benefit change → must match BNF_ISSUE_AGE; blank if not applicable |
| NFN_BENEFIT_CEASE_DATE | DATE | 8 | — | SEVERE | If benefit not applicable → blank; else valid YYYYMMDD |
| NFN_BENEFIT_SEQ_NUM | INT | 2 | — | SEVERE | If benefit not applicable → blank; else must match BNF_BENEFIT_SEQ |
| NFN_LOAN_INT_RATE_OLD | NUMERIC | 6 | 4 | SEVERE | If loan rate not changing → blank; else > 0 |
| NFN_LOAN_INT_RATE_NEW | NUMERIC | 6 | 4 | SEVERE | If loan rate not changing → blank; else > 0 |
| NFN_BAND_OLD | NUMERIC | 8 | 2 | — | Must be blank (WMA does not support) — WARNING if not blank |
| NFN_BAND_NEW | NUMERIC | 8 | 2 | — | Must be blank (WMA does not support) — WARNING if not blank |
| NFN_RMD_CODE_OLD | CHAR | 1 | — | — | Valid if present |
| NFN_RMD_CODE_NEW | CHAR | 1 | — | — | Valid if present |
| NFN_ISSUE_AGE_OLD | INT | 2 | — | SEVERE | If issue age not changing → blank |
| NFN_ISSUE_AGE_NEW | INT | 2 | — | SEVERE | If issue age not changing → blank |
| NFN_ISSUE_DATE_OLD | DATE | 8 | — | SEVERE | If issue date not changing → blank; else valid YYYYMMDD |
| NFN_ISSUE_DATE_NEW | DATE | 8 | — | SEVERE | If issue date not changing → blank; else valid YYYYMMDD |
| NFN_ORIGINAL_STATUS | CHAR | 2 | — | SEVERE | Exactly 2 chars; must correspond to coverage or benefit status |
| NFN_ORIGINAL_CLASS | CHAR | 1 | — | — | Blank if not applicable |
| NFN_ORIGINAL_ENTRY_CODE | CHAR | 1 | — | — | Valid if present |
| NFN_FACE_AMT_OLD | NUMERIC | 11 | 2 | — | Numeric if present |
| NFN_FACE_AMT_NEW | NUMERIC | 11 | 2 | — | Numeric if present |
| NFN_REASON | CHAR | 1 | — | SEVERE | Must be one of: R D I blank; if trans not causing increase/decrease/DBO/COLA → blank |
| NFN_TEMP_FLAT_EXTRA | NUMERIC | 11 | 5 | SEVERE | If PRODUCT_TYPE in A W B H → blank |
| NFN_TEMP_FLAT_END_DATE | DATE | 8 | — | SEVERE | If PRODUCT_TYPE in A W B H → blank; else valid YYYYMMDD |
| NFN_PERM_FLAT_EXTRA | NUMERIC | 11 | 5 | SEVERE | If PRODUCT_TYPE in A W B H → blank |
| NFN_PERM_TABLE_CODE | CHAR | 2 | — | SEVERE | If PRODUCT_TYPE in A W B H → blank; else exactly 2 chars |
| NFN_PERM_EXTRA_PERCENT | NUMERIC | 8 | 5 | SEVERE | If PRODUCT_TYPE in A W B H → blank |
| NFN_TEMP_TABLE_END_DATE | DATE | 8 | — | SEVERE | If PRODUCT_TYPE in A W B H → blank; else valid YYYYMMDD |
| NFN_TEMP_TABLE_CODE | CHAR | 2 | — | SEVERE | If PRODUCT_TYPE in A W B H → blank |
| NFN_TEMP_EXTRA_PERCENT | NUMERIC | 8 | 5 | SEVERE | If PRODUCT_TYPE in A W B H → blank |
| NFN_ISSUE_DATE | DATE | 8 | — | SEVERE | If coverage date not changing → use CVG_ISSUE_DATE; blank if not applicable |
| NFN_MORTRATE_CLASS_CODE | CHAR | 2 | — | SEVERE | If not applicable → blank; if applicable → exactly 2 chars or 00 |
| NFN_INCR_POLICYHOLDER_SEQ | INT | 2 | — | SEVERE | If coverage change → must equal CVG_SEQUENCE_NUMBER |
| NFN_INCREASE_TERM_DATE | DATE | 8 | — | SEVERE | If not coverage related → blank; else = CVG_MATURE_EXPIRE_DATE |
| NFN_ALLOCATION_TYPE_CA | CHAR | 1 | — | SEVERE | If TRX_CODE=80CA → not blank; else blank; must be A C P R |

---

## PART 4 — TASKS

Kiro must execute the following tasks in order. Do not proceed to the next task until the current task is complete and verified.

### Task 1 — Scaffold the project structure
```
policy_loader_poc/
├── validate_cnt.py
├── validate_prm.py
├── validate_fin.py
├── validate_nfn.py
├── validation_utils.py      ← shared helpers (date check, numeric check, length check)
├── test_validate_cnt.py
├── test_validate_prm.py
├── test_validate_fin.py
├── test_validate_nfn.py
└── requirements.txt         ← pandas, psycopg2-binary
```

### Task 2 — Build validation_utils.py
Generate the shared utility module containing:
- `is_valid_date(series)` — validates YYYYMMDD format
- `is_valid_length(series, length)` — exact character length check
- `is_not_blank(series)` — checks for null or whitespace-only
- `is_numeric(series)` — safe numeric conversion check
- `classify_severity(df)` — scans all VAL_ columns and sets ROW_SEVERITY
- `split_results(df)` — returns (clean_df, warning_df, severe_df)

### Task 3 — Generate validate_cnt.py
One function per field in the CNT table. Include all field-level validations, cross-field validations (SEX_CODE vs JOINT_LIFE_INDICATOR, APPLICATION_DATE vs ISSUE_DATE, etc.), and the Lambda handler.

### Task 4 — Generate validate_prm.py
One function per field in the PRM table. Include cross-field validations (BILLING_FORM driving PAC/draft fields). Cross-table validations against CNT go into `validate_prm_cross_table(df, cnt_df)`.

### Task 5 — Generate validate_fin.py
One function per field in the FIN table. Include loan-related conditional rules, tax override rules, and trans-code-driven rules. Cross-table validations against CNT go into `validate_fin_cross_table(df, cnt_df)`.

### Task 6 — Generate validate_nfn.py
One function per field in the NFN table. Include PRODUCT_TYPE-driven blank rules (for fields that must be blank when PRODUCT_TYPE is in A/W/B/H), and "old/new" pair consistency checks. Cross-table validations against CNT go into `validate_nfn_cross_table(df, cnt_df)`.

### Task 7 — Generate unit tests
For each validation module, generate test cases covering:
- Sample rows where all fields are valid → expect CLEAN
- Rows with SEVERE violations → expect ROW_SEVERITY = SEVERE
- Rows with WARNING conditions → expect ROW_SEVERITY = WARNING
- Cross-field rule triggers (at least 2 per table)

### Task 8 — Verify locally
Run all four test files. All tests must pass before proceeding to deployment.

### Task 9 — Package for Lambda
For each validation module, generate a Lambda-ready ZIP structure:
```
cnt_lambda.zip
├── validate_cnt.py
├── validation_utils.py
└── requirements.txt
```

### Task 10 — Deploy to AWS Lambda
Using the AWS MCP Server, create four Lambda functions:
- `policy-loader-validate-cnt`
- `policy-loader-validate-prm`
- `policy-loader-validate-fin`
- `policy-loader-validate-nfn`

Runtime: Python 3.12. Memory: 512 MB. Timeout: 5 minutes.

---

## STEERING FILE INSTRUCTIONS FOR KIRO

Add the following to your `steering.md` file in Kiro before running this spec:

```markdown
## Policy Loader POC — Steering Rules

- Always use Pandas for data manipulation. Never import PySpark or Spark libraries.
- All validation columns must be prefixed with VAL_ followed by the exact field name.
- SEVERE messages must contain the word "SEVERE:" at the start.
- WARNING messages must contain the word "WARNING:" at the start.
- Never enforce constraints in the database — all validation is in Python only.
- Primary keys in the database are: CNT (COMPANY_CODE + POLICY_NUMBER), PRM (COMPANY_CODE + POLICY_NUMBER + PARENT_TABLE_ID + PARENT_SEQ_NUM + VALUES_FROM), FIN (COMPANY_CODE + POLICY_NUMBER + RECORD_COUNTER), NFN (COMPANY_CODE + POLICY_NUMBER + SEQUENCE_NUMBER).
- The CNT table is the parent for all other tables. Cross-table validations must use a Pandas merge, not a database JOIN.
- All date fields use YYYYMMDD string format as stored — convert to datetime only for comparison.
- Field prefixes: CNT_ = Contract, PRM_ = Premium Billing, FIN_ = Financial History, NFN_ = Non-Financial History.
```

---

*Spec generated from: DB_Section_v2_New_-_5-4-26_from_NByers.xlsm*
*Tables: Contract (32 fields) · Premium Billing (30 fields) · Financial History (56 fields) · Non-Financial History (64 fields)*
*Total fields covered: 182*
