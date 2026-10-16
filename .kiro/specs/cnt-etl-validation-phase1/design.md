# Design Document: CNT ETL Validation Pipeline — Phase 1

## Overview

The Phase 1 ETL Validation Pipeline validates Contract (CNT) table data exported from legacy policy administration systems. It reads a CSV file of contract records, loads business rules from `DB_Section_Contract.csv` at runtime, applies 32 field-level rules and 17 cross-field rules, classifies each row as CLEAN/WARNING/SEVERE, and writes four output files.

The pipeline is built in Python 3.12 using Pandas for all data operations. It runs locally in Phase 1 and is designed to extend to AWS in later phases without changes to the core engine modules. The architecture strictly separates input reading, rule loading, validation, and output writing into four independent layers — a new table in Phase 2 requires only a new rules CSV section and no changes to the engine.

**Key design constraints:**
- **No Lambda, no database, no AWS** — local execution only for Phase 1
- **Invocation**: PDL/PL engine triggers the pipeline via shell command — no manual interaction
- **Runtime parameters**: `--input-file` and `--output-dir` supplied by the PDL/PL engine at invocation
- **Exit codes**: exit 0 on success (downstream processing continues), exit 1 on failure (engine halts)
- **Code location**: `src/` (source), `tests/` (tests), `scripts/` (utilities)
- **Tech stack**: Python 3.12, Pandas, pytest, ruff
- **Rule source**: `rules/DB_Section_Contract.csv` parsed at runtime
- **Primary keys**: CNT_COMPANY_CODE + CNT_POLICY_NUMBER
- **Replaces**: Legacy KNIME workflow — delivering speed, Git versioning, extensibility, portability, and zero licence cost

---

## Architecture

The pipeline follows a four-layer linear architecture. No layer imports from a layer above it.

```
┌─────────────────────────────────────────────────────┐
│  LAYER 1 — INPUT: input_reader.py                   │
│  Reads CSV in 10,000-row chunks → clean DataFrame   │
└──────────────────────┬──────────────────────────────┘
                       │ pd.DataFrame (32 CNT columns)
┌──────────────────────▼──────────────────────────────┐
│  LAYER 2 — RULES: rule_loader.py                    │
│  Reads DB_Section_Contract.csv → rules dict         │
└──────────────────────┬──────────────────────────────┘
                       │ dict[field_name → rule_config]
┌──────────────────────▼──────────────────────────────┐
│  LAYER 3 — ENGINE: validation_engine.py             │
│  Applies rules → adds VAL_* columns + ROW_SEVERITY  │
└──────────────────────┬──────────────────────────────┘
                       │ pd.DataFrame (enriched)
┌──────────────────────▼──────────────────────────────┐
│  LAYER 4 — OUTPUT: output_writer.py                 │
│  Splits by ROW_SEVERITY → writes CSV + summary      │
└─────────────────────────────────────────────────────┘

Shared: validation_utils.py  (pure helpers, no side effects)
Entry:  main.py               (CLI wiring, argparse)
Tests:  tests/                (pytest, one file per module)
```


### Rule Loading Strategy: Runtime Loading (Option A)

**Decision**: The pipeline will parse `DB_Section_Contract.csv` at runtime on every execution.

**Rationale**:
- POC stage with ~200 rows and 32 fields — CSV parsing overhead is negligible (milliseconds)
- Business analysts own the CSV and must be able to update rules without engineer involvement
- Zero-friction workflow: edit CSV → save → run pipeline (no intermediate generation step)
- `rule_loader.py` is isolated — if pre-generation becomes necessary in Phase 2+ (when PRM/FIN/NFN tables are added), we can refactor to load JSON without touching other modules
- Faster Phase 1 delivery — no rule generator or JSON schema to build

**Error Handling**: The rule loader will validate CSV structure on startup and raise clear exceptions if the file is malformed or contains invalid rule definitions. This happens before processing any data rows.

**Future Path**: If Phase 2+ adds ~180 fields across multiple tables, or if analysts request faster feedback on rule correctness, we can introduce a `generate_rules.py` script as a CI/CD pre-step. This does not block Phase 1.

---

### Hybrid Validation Pattern

The pipeline uses a hybrid pattern that separates concerns cleanly:

- **Shared engine (`field_validator.py`)**: Handles all field-level validation rules for every table. Exposes two public functions: `apply_field_rules(df, rules_dict, table_name="")` and `classify_severity(df)`. Contains no table-specific logic or field names.

- **Table-specific modules (`validate_cvg.py`, `validate_rol.py`, `validate_add.py`)**: Each contains a rules dictionary and cross-table validation functions. They delegate field-level validation to `field_validator.py`.

- **CNT table (`validation_engine.py`)**: Retains 16 cross-field rules but delegates all 32 field-level rules to `field_validator.py` via a thin wrapper:
  ```python
  def _apply_field_rules(df, rules):
      return apply_field_rules(df, rules, table_name="CNT")
  ```
  The public function signatures in `validation_engine.py` are unchanged.

**Benefits:**
- Adding a new table requires only creating `validate_<table>.py` with a rules dict and cross-table function — zero changes to `field_validator.py` or `validation_engine.py`.
- A bug fix in field validation logic is made once in `field_validator.py` and propagates to all tables automatically.
- Severity flows entirely from the BA rule sheet → `rule_loader.py` → rules dict → `apply_field_rules()` → `classify_severity()`. No severity values are hardcoded in `field_validator.py`.

---

### Logging Prefix Convention

All console output uses prefixed tags for machine-readable log parsing. The complete set of prefixes:

| Prefix | Source Module | Purpose |
|---|---|---|
| `[CONFIG]` | `config_loader.py` | Configuration loading messages |
| `[INPUT]` | `input_reader.py` | CSV reading progress and row/column counts |
| `[RULES]` | `rule_loader.py` | Rule file loading and rule counts |
| `[ENGINE]` | `validation_engine.py` | Validation execution progress |
| `[FIELD_VAL]` | `field_validator.py` | Shared engine start/end summaries and per-field DEBUG |
| `[OUTPUT]` | `output_writer.py` | Output file writing and row counts |
| `[TABLE]` | `validate_*.py` | Table-specific validation messages |
| `[DONE]` | `main.py` | Final pipeline completion with elapsed time |

**field_validator.py log points:**
- Start: `[FIELD_VAL] Processing <TABLE> — <N> rules loaded`
- Per-rule (DEBUG only, gated behind `verbose=False` default): `[FIELD_VAL] <FIELD> | <RULE_TYPE> | severity: <SEVERITY> — <N> violation(s)`
- End: `[FIELD_VAL] <TABLE> complete — CLEAN: <N>, WARNING: <N>, SEVERE: <N>`

---

### Rule Type Catalogue

All rule types supported by `field_validator.py`:

| Rule Type | Behaviour | Mutates DataFrame? | Notes |
|---|---|---|---|
| `not_blank` | Rejects null, empty, or whitespace-only values | No | Also checks exact length if `length` is set |
| `exact_length` | Rejects values where trimmed length ≠ specified N. Blank values fail. | No | New — validates field is exactly N characters |
| `max_length` | Rejects values exceeding maximum character count | No | |
| `allowed_values` | Rejects values not in the defined list | No | Handles blank-allowed lists (empty string in list) |
| `valid_date` | Rejects values not in YYYYMMDD calendar date format | No | |
| `numeric` | Rejects non-numeric values | No | |
| `default_then_warn` | Defaults a blank field to a reference field value, then emits WARNING | **Yes** | Only write rule type. Must be backed by a rule in BA steering file before use. |
| `date_gt` | Cross-field: rejects if date A is not greater than date B | No | Used via cross-field rules |
| `date_lte` | Cross-field: rejects if date A is not ≤ date B | No | Used via cross-field rules |

**Important**: `default_then_warn` is the only rule type that writes to the DataFrame. All other rule types are read-only. Any future rule requiring mutation must follow this pattern and be documented in the field_validator.py module docstring.

---

## Components and Interfaces

### main.py

```python
def main() -> None:
    """Parse CLI args, wire four layers, print final summary, exit with 0 or 1."""
```

CLI interface (invoked by PDL/PL engine):
```
python main.py --input-file /path/to/input.csv --output-dir /path/to/output/
```

Legacy alias support (backward compatibility with direct use):
```
python main.py --input sample_data/sample_cnt.csv --spec Day\ 2/DB_Section_Contract.csv --output output/
```

Exit code contract:
| Exit Code | Meaning | PDL/PL Engine Action |
|---|---|---|
| `0` | Pipeline completed successfully (all outputs written) | Continue downstream processing |
| `1` | Pipeline failed (missing file, unhandled exception, etc.) | Halt and report error |

The PDL/PL engine relies on these exit codes to decide whether to proceed. `main.py` wraps each layer in a try/except block and calls `sys.exit(1)` on any unhandled failure, `sys.exit(0)` on success.


Console output format (from ETL Engineering Standards steering file):
```
[INPUT]   Reading CNT data from: <path>
[INPUT]   Loaded N rows, 32 columns
[RULES]   Loaded 32 field rules and 17 cross-field rules for CNT
[ENGINE]  Running field validations...
[ENGINE]  Running cross-field validations...
[ENGINE]  Classification complete
[OUTPUT]  CLEAN:   N rows → output/cnt_clean.csv
[OUTPUT]  WARNING: N rows → output/cnt_warning.csv
[OUTPUT]  SEVERE:  N rows → output/cnt_severe.csv
[OUTPUT]  Summary  → output/cnt_summary.txt
[DONE]    Pipeline completed in X.X seconds
```

### input_reader.py

```python
EXPECTED_COLUMNS: list[str]  # all 32 CNT field names

def read(file_path: Path, chunksize: int = 10_000) -> pd.DataFrame:
    """Read the input CSV in chunks and return a validated DataFrame."""
```

Raises `FileNotFoundError` if file is missing. Raises `ValueError` listing all missing columns if any of the 32 expected columns are absent.

### rule_loader.py

```python
RULES_FILE_PATH = Path("rules") / "DB_Section_Contract.csv"

def load(table: str) -> dict[str, dict]:
    """Load and parse validation rules for the given table from the rules CSV."""

def parse_rule_row(row: dict) -> tuple[str, dict]:
    """Parse one CSV row into a field name and rule config dict."""

def validate_rule_schema(rules: dict) -> None:
    """Check that all required keys are present in the parsed rules."""
```


Returns a dict keyed by field name. Each value contains:
```python
{
  "rule_type": str,         # "not_blank" | "exact_length" | "max_length" |
                            # "allowed_values" | "valid_date" | "numeric" |
                            # "default_then_warn" | "date_gt" | "date_lte"
  "severity": str,          # "SEVERE" | "WARNING"
  "length": int | None,
  "allowed_values": list[str] | None,
  "ref_field": str | None,  # for cross-field and default rules
}
```

Cross-field rules are returned as a separate list of dicts alongside the field rules dict.

### validation_engine.py

```python
def run(df: pd.DataFrame, rules: dict) -> pd.DataFrame:
    """Apply all field and cross-field rules; return enriched DataFrame."""

def _apply_field_rules(df: pd.DataFrame, rules: dict) -> pd.DataFrame:
    """Thin wrapper — delegates to field_validator.apply_field_rules(df, rules, table_name='CNT').
    Preserves the existing call signature for backward compatibility."""

def _apply_cross_field_rules(df: pd.DataFrame) -> pd.DataFrame:
    """Apply all cross-field rules as named check functions."""

def classify_severity(df: pd.DataFrame) -> pd.DataFrame:
    """Assign ROW_SEVERITY to each row based on VAL_* column patterns."""

# Named cross-field check functions:
def _check_sex_code_joint_indicator(df: pd.DataFrame) -> pd.DataFrame: ...
def _check_product_type_joint_indicator(df: pd.DataFrame) -> pd.DataFrame: ...
def _check_joint_lives_rate_age_reason(df: pd.DataFrame) -> pd.DataFrame: ...
def _check_joint_indicator_rate_age(df: pd.DataFrame) -> pd.DataFrame: ...
def _check_joint_indicator_reason_code(df: pd.DataFrame) -> pd.DataFrame: ...
def _check_date_relationships(df: pd.DataFrame) -> pd.DataFrame: ...
def _check_qualification_product_type(df: pd.DataFrame) -> pd.DataFrame: ...
def _check_participation_product_type(df: pd.DataFrame) -> pd.DataFrame: ...
def _check_plan_option_product_type(df: pd.DataFrame) -> pd.DataFrame: ...
def _check_grace_expiry_product_type(df: pd.DataFrame) -> pd.DataFrame: ...
```

**Note:** Field-level validation is handled entirely by the shared `field_validator.py` engine. This module retains only the 16 cross-field rules (which encode CNT-specific business logic) and delegates all 32 field-level rules via `_apply_field_rules()` → `field_validator.apply_field_rules()`. The public function signatures are unchanged from the original design.

The engine does not open any files and contains no hardcoded field rules.


### validation_utils.py

```python
def is_not_blank(series: pd.Series) -> pd.Series:
    """Return True where the value is non-null and contains at least one non-whitespace character."""

def is_exact_length(series: pd.Series, n: int) -> pd.Series:
    """Return True where the trimmed string length equals n."""

def is_max_length(series: pd.Series, n: int) -> pd.Series:
    """Return True where the string length is less than or equal to n."""

def is_in_allowed_values(series: pd.Series, values: list[str]) -> pd.Series:
    """Return True where the value appears in the provided list."""

def is_valid_date(series: pd.Series) -> pd.Series:
    """Return True where the value is a valid calendar date in YYYYMMDD format."""

def is_numeric(series: pd.Series) -> pd.Series:
    """Return True where the value can be converted to a numeric type."""

def is_date_greater_than(series_a: pd.Series, series_b: pd.Series) -> pd.Series:
    """Return True where series_a represents a date strictly after series_b (YYYYMMDD)."""

def is_date_lte(series_a: pd.Series, series_b: pd.Series) -> pd.Series:
    """Return True where series_a represents a date on or before series_b (YYYYMMDD)."""
```

All functions accept a Pandas Series, return a boolean Pandas Series, use vectorised operations only, and have no side effects.

### output_writer.py

```python
def write(df: pd.DataFrame, output_dir: Path) -> None:
    """Split df by ROW_SEVERITY and write cnt_clean/warning/severe CSV and summary."""

def split_by_severity(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (clean_df, warning_df, severe_df) using boolean masks."""

def generate_summary(df: pd.DataFrame, input_file: str) -> str:
    """Generate summary text with run date, counts, percentages, and top failure reasons."""

def ensure_output_dir(output_dir: Path) -> None:
    """Create output directory if it does not already exist."""
```

### generate_test_data.py

```python
def generate_clean_rows(n: int) -> list[dict]:
    """Generate n fully valid CNT rows — all 32 fields correct, expect CLEAN."""

def generate_warning_rows(n: int) -> list[dict]:
    """Generate n rows with deliberate WARNING triggers; include TEST_EXPECTED_ISSUE column."""

def generate_severe_rows(n: int) -> list[dict]:
    """Generate n rows with deliberate SEVERE triggers; include TEST_EXPECTED_ISSUE column."""

def main() -> None:
    """Produce sample_data/sample_cnt.csv with ~200 rows (100 CLEAN, 50 WARNING, 50 SEVERE)."""
```


---

## Data Models

### Rules Dictionary

```python
# Returned by rule_loader.load("CNT")
rules: dict[str, dict] = {
    "CNT_ISSUE_SYSTEM": {
        "rule_type": "not_blank",
        "severity": "SEVERE",
        "length": 2,
        "allowed_values": None,
        "ref_field": None,
    },
    "CNT_BASE_PLAN_CODE": {
        "rule_type": "default_then_warn",
        "severity": "WARNING",
        "length": 10,
        "allowed_values": None,
        "ref_field": "CNT_POLICY_PLAN_CODE",
    },
    "CNT_PRODUCT_TYPE": {
        "rule_type": "allowed_values",
        "severity": "SEVERE",
        "length": 1,
        "allowed_values": ["A","W","B","T","K","L","I","U","V","E","J","Z","H","D"],
        "ref_field": None,
    },
    # ... 29 more field entries
}

cross_field_rules: list[dict] = [
    {
        "name": "sex_code_joint_indicator",
        "trigger_field": "CNT_SEX_CODE",
        "trigger_values": ["B"],
        "target_field": "CNT_JOINT_LIFE_INDICATOR",
        "required_values": ["F"],
        "severity": "SEVERE",
    },
    # ... 16 more cross-field entries
]
```

### DataFrame Schema

Input DataFrame: 32 CNT columns, all as `object` (string) dtype initially.

After validation, the engine adds:
- `VAL_CNT_ISSUE_SYSTEM` through `VAL_CNT_REINS_TYPE` — 32 VAL_ columns (`object`, None or message string)
- `ROW_SEVERITY` — `object` column, one of `CLEAN`, `WARNING`, `SEVERE`

The engine does not modify the original 32 input columns except for `CNT_BASE_PLAN_CODE` (default-then-warn replacement).


### Output Files

| File | Columns | Description |
|---|---|---|
| `cnt_clean.csv` | Original 32 + 32 VAL_ + ROW_SEVERITY | Rows where ROW_SEVERITY = CLEAN |
| `cnt_warning.csv` | Original 32 + 32 VAL_ + ROW_SEVERITY | Rows where ROW_SEVERITY = WARNING |
| `cnt_severe.csv` | Original 32 + 32 VAL_ + ROW_SEVERITY | Rows where ROW_SEVERITY = SEVERE |
| `cnt_summary.txt` | Plain text | Run metadata, counts, top failure reasons |

### Summary Report Format

```
Policy Loader Validation Summary
=================================
Run date        : 2026-07-07
Input file      : sample_cnt.csv
Total rows      : 10,000

Results
-------
CLEAN           : 8,450  (84.5%)
WARNING         :   930  ( 9.3%)
SEVERE          :   620  ( 6.2%)

Top 5 Failure Reasons (SEVERE)
--------------------------------
1. CNT_ISSUE_DATE — Invalid date format          : 210 rows
2. CNT_COMPANY_CODE — Must not be blank          : 185 rows
3. CNT_MATURE_EXPIRE_DATE — Must be > ISSUE_DATE :  95 rows
4. CNT_PRODUCT_TYPE — Not an allowed value        :  80 rows
5. CNT_SEX_CODE — Cross-field rule violation      :  50 rows

Top 3 Failure Reasons (WARNING)
---------------------------------
1. CNT_BASE_PLAN_CODE — Defaulted to POLICY_PLAN_CODE : 520 rows
2. CNT_SERV_AGENT — Blank servicing agent              : 250 rows
3. CNT_SERV_AGENCY — Blank servicing agency            : 160 rows
```

---

## File Structure

```
src/
├── field_validator.py          # Shared engine — apply_field_rules(), classify_severity()
├── validate_cvg.py             # CVG: rules dict + cross-table validation only
├── validate_rol.py             # ROL: rules dict + cross-table validation only
├── validate_add.py             # ADD: rules dict + cross-table validation only
├── validation_engine.py        # CNT: cross-field rules + thin wrapper to field_validator
├── validation_utils.py         # Pure helpers (no side effects) — unchanged
├── main.py                     # CLI entry point (argparse, wires 4 layers)
├── input_reader.py             # Layer 1: CSV reading
├── rule_loader.py              # Layer 2: rules CSV parsing
├── output_writer.py            # Layer 4: output writing
├── config_loader.py            # Project configuration
├── glue_job.py                 # AWS Glue job wrapper (Phase 2+)
├── __init__.py
tests/
├── test_field_validator.py     # 19 tests — shared engine (independent of any table)
├── test_input_reader.py
├── test_rule_loader.py
├── test_validation_engine.py
├── test_output_writer.py
├── test_validation_utils.py
├── test_validate_add.py
├── test_validate_cvg.py
├── test_validate_rol.py
├── __init__.py
scripts/
└── generate_test_data.py       # Produces sample_data/sample_cnt.csv
sample_data/
└── sample_cnt.csv              # ~200 rows (100 CLEAN, 50 WARNING, 50 SEVERE)
rules/
├── DB_Section_Contract.csv
├── DB_Section_Coverage.csv
├── DB_Section_Roles.csv
├── DB_Section_Address.csv
output/                         # Created at runtime
config/
└── project_config.yaml
requirements.txt
```


---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Input round-trip preserves row count and columns

*For any* valid CNT CSV file, `input_reader.read()` shall return a DataFrame with exactly the same number of rows as the file and all 32 expected CNT column names present.

**Validates: Requirements 2.1, 2.3**

---

### Property 2: Missing columns are fully reported

*For any* CNT CSV file that is missing one or more of the 32 required columns, `input_reader.read()` shall raise a `ValueError` whose message contains every missing column name.

**Validates: Requirements 2.3, 2.4**

---

### Property 3: Valid field values produce no validation message

*For any* DataFrame row where a CNT field contains a value that satisfies all its configured rules (correct length, in allowed values, valid date format, non-blank, numeric as required), the corresponding `VAL_*` column shall be `None` after `validation_engine.run()` completes.

**Validates: Requirements 4.1, 4.2**

---

### Property 4: Invalid field values produce correctly prefixed messages

*For any* DataFrame row where a CNT field contains a value that violates its configured rule, the corresponding `VAL_*` column shall contain a non-None string starting with `SEVERE:` (for SEVERE-severity fields) or `WARNING:` (for WARNING-severity fields).

**Validates: Requirements 4.3, 4.4**

---

### Property 5: Default-then-warn transformation is consistent

*For any* DataFrame row where `CNT_BASE_PLAN_CODE` is blank, after `validation_engine.run()` the value of `CNT_BASE_PLAN_CODE` shall equal `CNT_POLICY_PLAN_CODE` from the same row, and `VAL_CNT_BASE_PLAN_CODE` shall start with `WARNING:`.

**Validates: Requirements 4.5**


---

### Property 6: Cross-field rule violations produce SEVERE messages

*For any* DataFrame row where a cross-field trigger condition is satisfied (e.g., `CNT_SEX_CODE = B`) but the dependent field does not hold the required value (e.g., `CNT_JOINT_LIFE_INDICATOR ≠ F`), the `VAL_*` column for the dependent field shall contain a message starting with `SEVERE:`.

**Validates: Requirements 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.11, 5.12, 5.13, 5.14, 5.16, 5.17**

---

### Property 7: Row classification is determined solely by VAL_* column patterns

*For any* DataFrame where all `VAL_*` columns are `None`, `ROW_SEVERITY` shall be `CLEAN`. For any DataFrame where at least one `VAL_*` column starts with `WARNING:` and none starts with `SEVERE:`, `ROW_SEVERITY` shall be `WARNING`. For any DataFrame where at least one `VAL_*` column starts with `SEVERE:`, `ROW_SEVERITY` shall be `SEVERE` regardless of any WARNING values present.

**Validates: Requirements 6.2, 6.3, 6.4**

---

### Property 8: Output partitions the input without overlap or loss

*For any* validated DataFrame, the three output DataFrames produced by `output_writer.write()` shall form a partition of the input: the sum of their row counts equals the total input row count, and no Primary_Key (`CNT_COMPANY_CODE` + `CNT_POLICY_NUMBER`) appears in more than one output file.

**Validates: Requirements 7.1, 7.2, 7.3**

---

### Property 9: Validation_Utils correctness across all inputs

*For any* Pandas Series, each `validation_utils` function shall return a boolean Series of the same length where: `is_not_blank` returns `True` iff the value is non-null and contains at least one non-whitespace character; `is_exact_length(s, n)` returns `True` iff `len(str(v).strip()) == n`; `is_max_length(s, n)` returns `True` iff `len(str(v)) <= n`; `is_in_allowed_values(s, vals)` returns `True` iff the value appears in `vals`; `is_valid_date` returns `True` iff the value is a valid YYYYMMDD calendar date; `is_numeric` returns `True` iff the value can be converted to float; `is_date_greater_than(a, b)` returns `True` iff `a > b` as YYYYMMDD dates; `is_date_lte(a, b)` returns `True` iff `a <= b` as YYYYMMDD dates.

**Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8**

---

### Property 10: Generated test rows are classified correctly by the pipeline

*For any* row produced by `generate_test_data.generate_clean_rows()`, running it through the full pipeline shall produce `ROW_SEVERITY = CLEAN`. For any row from `generate_warning_rows()`, the result shall be `WARNING`. For any row from `generate_severe_rows()`, the result shall be `SEVERE`.

**Validates: Requirements 9.1, 9.2, 9.3, 9.4**


---

## Error Handling

Every function that performs file I/O uses `try/except` and raises typed exceptions with actionable messages.

| Scenario | Exception | Message format |
|---|---|---|
| Input CSV not found | `FileNotFoundError` | `"Input CSV not found at: {path}\nCheck the file path and try again."` |
| Required CNT column missing | `ValueError` | `"Missing required columns: {col1}, {col2}, ..."` |
| Rules file not found | `FileNotFoundError` | `"Rules file not found at: {RULES_FILE_PATH}\nEnsure DB_Section_Contract.csv is in the rules/ folder."` |
| Rules CSV malformed | `ValueError` | `"Rules CSV malformed at row {row_num}: {reason}"` |
| Output directory not writable | `OSError` | `"Cannot create output directory: {path}\n{reason}"` |
| Layer failure in main.py | (re-raised) | `"[LAYER NAME] failed: {cause}"` → exit code 1 |

The pipeline does not swallow exceptions silently. Any unhandled exception in a layer surfaces to `main.py`, which prints the error with a layer prefix and exits with code 1.

Date comparison rules (`is_date_greater_than`, `is_date_lte`) handle invalid dates gracefully: if either operand is not a valid YYYYMMDD date, the comparison returns `False` (the validation fails), which is the safe default — the field-level date validation will already have flagged the invalid date.

---

## PDL/PL Engine Integration

The pipeline is designed to be triggered by the PDL/PL engine as a subprocess. The integration contract is:

1. **Invocation**: The engine calls the pipeline via a shell command, passing `--input-file` and `--output-dir` as arguments.
2. **No hardcoded paths**: The pipeline uses only the paths supplied at invocation — it is fully parameterised.
3. **Exit codes**: The engine inspects the process exit code to determine success (`0`) or failure (`1`).
4. **No interactive prompts**: The pipeline runs unattended; all configuration comes from CLI arguments.
5. **Stdout logging**: Console output uses prefixed layer tags (`[INPUT]`, `[RULES]`, `[ENGINE]`, `[OUTPUT]`, `[DONE]`, `[ERROR]`) for machine-readable log parsing by the engine.

### Advantages over KNIME

This pipeline replaces the legacy KNIME workflow. The key advantages that justify the technology shift:

| Advantage | Detail |
|---|---|
| Speed | Native Python/Pandas vectorised operations process large files significantly faster than KNIME visual nodes |
| Git versioning | Full change history, branching, and code review — impossible with KNIME's binary workflow files |
| Extensibility | New tables and rules are added via Python functions, not drag-and-drop node editing |
| Portability | Runs anywhere Python 3.12 is installed — no platform-specific IDE required |
| No licence cost | Relies only on open-source packages; no commercial KNIME extensions needed |

---

## Testing Strategy

### Framework and Configuration

- **Test runner**: `pytest >= 8.0.0`
- **Property-based testing**: `hypothesis >= 6.0.0` (add to `requirements.txt`)
- **Linting**: `ruff >= 0.1.0`
- **Execution**: `pytest tests/ -v` from workspace root
- Minimum 100 iterations per property test (Hypothesis default: 100)
- Each property test references its design document property number in a comment

### Unit Tests (example-based)

Unit tests cover specific scenarios and error conditions. They are complementary to property tests — they verify concrete behaviors, not universal properties.

| Test file | Key scenarios |
|---|---|
| `test_input_reader.py` | Valid file reads correctly; missing file raises FileNotFoundError with path; missing columns raises ValueError listing all absent columns |
| `test_rule_loader.py` | DB_Section_Contract.csv loads without error; returns entries for all 32 fields; all nine rule types represented; missing file raises FileNotFoundError |
| `test_validation_engine.py` | All-valid row → all VAL_* None; each field type triggers SEVERE correctly; WARNING field triggers WARNING; default-then-warn transforms CNT_BASE_PLAN_CODE; each of the 17 cross-field rules triggers on a known example |
| `test_output_writer.py` | CLEAN rows go to cnt_clean.csv; WARNING rows go to cnt_warning.csv; SEVERE rows go to cnt_severe.csv; output dir created if absent; summary file written and contains expected strings |
| `test_validation_utils.py` | Each function: valid input → True; invalid input → False; edge cases (empty string, whitespace-only, boundary lengths, invalid date like 20260231, leap year 20240229) |


### Property-Based Tests

Property tests use Hypothesis to generate diverse inputs and verify universal properties across all valid and invalid scenarios. They run 100+ iterations per test.

| Property | Test description | Tag |
|---|---|---|
| Property 1 | Generate random valid CNT CSVs (varying row counts, all fields valid), verify `read()` preserves row count and all 32 columns present | `Feature: cnt-etl-validation-phase1, Property 1: Input round-trip` |
| Property 2 | Generate CSVs with random subsets of missing columns, verify all missing names in exception message | `Feature: cnt-etl-validation-phase1, Property 2: Missing columns reported` |
| Property 3 | Generate valid field values for each rule type (exact length, within allowed values, valid dates, numeric), verify all corresponding VAL_* = None | `Feature: cnt-etl-validation-phase1, Property 3: Valid values pass` |
| Property 4 | Generate invalid field values (wrong length, not in allowed values, invalid dates, non-numeric), verify VAL_* starts with correct severity prefix | `Feature: cnt-etl-validation-phase1, Property 4: Invalid values flagged` |
| Property 5 | Generate rows with blank CNT_BASE_PLAN_CODE and random CNT_POLICY_PLAN_CODE, verify default applied and WARNING message | `Feature: cnt-etl-validation-phase1, Property 5: Default-then-warn` |
| Property 6 | Generate rows satisfying each cross-field trigger with wrong dependent value, verify SEVERE message appears in target field's VAL_* column | `Feature: cnt-etl-validation-phase1, Property 6: Cross-field violations` |
| Property 7 | Generate arbitrary VAL_* column patterns (all None, some WARNING, some SEVERE), verify ROW_SEVERITY matches classification rules | `Feature: cnt-etl-validation-phase1, Property 7: Row classification` |
| Property 8 | Generate validated DataFrames with random ROW_SEVERITY assignments, verify output partition invariant (no overlap, no loss) | `Feature: cnt-etl-validation-phase1, Property 8: Output partition` |
| Property 9 | Generate diverse Series inputs (empty, whitespace, boundary values, valid/invalid dates), verify each util function returns correct boolean Series | `Feature: cnt-etl-validation-phase1, Property 9: Utils correctness` |
| Property 10 | Run generated test rows (from generate_test_data.py) through pipeline, verify severity matches expected TEST_EXPECTED_ISSUE value | `Feature: cnt-etl-validation-phase1, Property 10: Test data classification` |

### Dual Coverage Principle

Unit tests and property tests are complementary, not redundant:
- **Unit tests** verify specific concrete behaviors using hand-crafted examples  
  (e.g., "CNT_ISSUE_SYSTEM = 'AB' passes", "CNT_ISSUE_SYSTEM = 'A' fails with SEVERE")
- **Property tests** verify universal invariants across 100+ generated inputs  
  (e.g., "any 2-character non-blank string passes", "any string not exactly 2 chars fails")
- Together they provide high confidence: unit tests catch specific known bugs, property tests uncover edge cases and unexpected combinations


### AWS Execution Recommendation (Phase 2+)

For Phase 2 and beyond, the pipeline will need to run on AWS. Based on the Phase 1 structure:

- The pipeline is a straightforward Pandas script with linear execution and chunked CSV reading
- Peak memory usage is stable (10,000-row chunks) and well within 2GB
- No parallel processing is required
- No containerisation is strictly needed

**Recommendation: AWS Glue Python Shell**

AWS Glue Python Shell supports Pandas natively, has a 48-hour time limit (far beyond Phase 1 needs), and requires no containerisation overhead. The pipeline script can be uploaded directly with minimal changes. AWS Batch would be the fallback if memory exceeds 2GB after adding PRM/FIN/NFN tables in Phase 2+.

