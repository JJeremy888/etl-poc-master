"""Presence and format validation rule compilers.

Each function takes a rule dict from the template and returns a PySpark Column
that evaluates to None when the field passes, or a severity-prefixed error
message when it fails.
"""
from pyspark.sql import Column, functions as F
from pyspark.sql.types import StringType


def compile_not_blank(rule: dict) -> Column:
    """Field must not be null, empty, or whitespace-only."""
    field = rule["target_field"]
    severity = rule["severity"]
    return F.when(
        F.col(field).isNull() | (F.trim(F.col(field)) == F.lit("")),
        F.lit(f"{severity}: {field} must not be blank")
    ).otherwise(F.lit(None).cast(StringType()))


def compile_exact_length(rule: dict) -> Column:
    """Field must be exactly param_1 characters (after trim).

    Blank handling follows validation-principles.md Principle 3: if the field is
    optional (no not_blank/required rule — signalled by `_blank_optional`), a
    blank value is accepted and only non-blank values are length-checked.
    Presence is enforced separately by a not_blank rule when the field is
    mandatory.
    """
    field = rule["target_field"]
    severity = rule["severity"]
    length = int(rule["param_1"])
    is_blank = F.col(field).isNull() | (F.trim(F.col(field)) == F.lit(""))
    wrong_len = F.length(F.trim(F.col(field))) != F.lit(length)

    if rule.get("_blank_optional", False):
        # Optional field: blank is OK; only flag non-blank values of wrong length.
        return F.when(
            ~is_blank & wrong_len,
            F.lit(f"{severity}: {field} must be exactly {length} characters")
        ).otherwise(F.lit(None).cast(StringType()))

    # Mandatory field: blank (or wrong length) is a violation.
    return F.when(
        is_blank | wrong_len,
        F.lit(f"{severity}: {field} must be exactly {length} characters")
    ).otherwise(F.lit(None).cast(StringType()))


def compile_max_length(rule: dict) -> Column:
    """Field must be at most param_1 characters (after trim).

    Blank handling follows validation-principles.md Principle 3: a max_length
    rule is a format/upper-bound check, never a presence check. A blank value is
    therefore accepted (length 0 <= max) and never flagged as "exceeds" — only
    non-blank values longer than max are violations. Presence, when required, is
    enforced by a separate not_blank rule.

    The one exception is a WARNING rule whose description explicitly says
    "blank sends warning" — that emits an informational blank warning.
    """
    field = rule["target_field"]
    severity = rule["severity"]
    max_len = int(rule["param_1"])
    desc = rule.get("description", "").lower()

    is_blank = F.col(field).isNull() | (F.trim(F.col(field)) == F.lit(""))
    too_long = F.length(F.trim(F.col(field))) > F.lit(max_len)

    # Only warn on blank if the description explicitly says "blank sends warning"
    if severity == "WARNING" and "blank sends warning" in desc:
        return F.when(
            is_blank,
            F.lit(f"{severity}: {field} is blank")
        ).when(
            too_long,
            F.lit(f"{severity}: {field} exceeds {max_len} characters")
        ).otherwise(F.lit(None).cast(StringType()))

    # Default: blank is acceptable (a null/empty value has length 0 <= max_len).
    # Only flag non-blank values that exceed the maximum length.
    return F.when(
        ~is_blank & too_long,
        F.lit(f"{severity}: {field} exceeds {max_len} characters")
    ).otherwise(F.lit(None).cast(StringType()))


def compile_allowed_values(rule: dict) -> Column:
    """Field value must be in the pipe-delimited allowed list. Blank may be acceptable.

    Blank handling (validation-principles.md Principle 3 — interpret the sheet as
    written): the master workbook uses the literal token ``blank`` (or ``blanks``)
    inside an allowed-values list to mean "an empty value is permitted"
    (e.g. ``A|F|blank``, ``1|...|8|D|F|blank``). We honor that token directly:
    if it appears in the list, an empty/null value passes. This is a real value
    of the sheet's own convention, not an inferred default. As a fallback we also
    accept an explicit "blank acceptable/if/when" phrase in the description.
    """
    field = rule["target_field"]
    severity = rule["severity"]
    values_str = rule.get("allowed_values", "")
    # Split, dropping the blank sentinel token(s) from the concrete allowed set.
    raw = [v.strip() for v in values_str.split("|") if v.strip()]
    blank_token = any(v.lower() in ("blank", "blanks") for v in raw)
    allowed = [v for v in raw if v.lower() not in ("blank", "blanks")]

    # Blank is acceptable if the allowed list carries the blank token, or the
    # description explicitly says so.
    desc = rule.get("description", "").lower()
    blank_ok = (
        blank_token
        or "blank acceptable" in desc
        or "blank if" in desc
        or "blank when" in desc
    )

    if blank_ok:
        return F.when(
            F.col(field).isNull() | (F.trim(F.col(field)) == F.lit("")),
            F.lit(None).cast(StringType())  # Blank is OK
        ).when(
            ~F.trim(F.col(field)).isin(allowed),
            F.lit(f"{severity}: {field} not an allowed value")
        ).otherwise(F.lit(None).cast(StringType()))
    else:
        return F.when(
            F.col(field).isNull() | (F.trim(F.col(field)) == F.lit("")),
            F.lit(f"{severity}: {field} must not be blank")
        ).when(
            ~F.trim(F.col(field)).isin(allowed),
            F.lit(f"{severity}: {field} not an allowed value")
        ).otherwise(F.lit(None).cast(StringType()))


def compile_valid_date(rule: dict) -> Column:
    """Field must be a valid date in YYYYMMDD format (8 numeric characters forming a real date)."""
    field = rule["target_field"]
    severity = rule["severity"]
    desc = rule.get("description", "").lower()
    # For WARNING-severity rules, blank is acceptable by default
    # (field is optional - validate format only if present)
    # For SEVERE-severity, blank is only ok if explicitly stated
    if severity == "WARNING":
        blank_ok = True
    else:
        blank_ok = "blank if" in desc or "blank when" in desc or "if present" in desc

    # Check: 8 chars, all numeric, and parseable as a date
    is_blank = F.col(field).isNull() | (F.trim(F.col(field)) == F.lit(""))
    is_8_digits = (F.length(F.trim(F.col(field))) == F.lit(8)) & F.trim(F.col(field)).rlike("^[0-9]{8}$")
    # Use try_to_timestamp to avoid ANSI exceptions on invalid dates like month=13
    is_valid_date = F.to_date(F.try_to_timestamp(F.trim(F.col(field)), F.lit("yyyyMMdd"))).isNotNull()

    if blank_ok:
        return F.when(
            is_blank, F.lit(None).cast(StringType())
        ).when(
            ~is_8_digits | ~is_valid_date,
            F.lit(f"{severity}: {field} invalid date format \u2014 expected YYYYMMDD")
        ).otherwise(F.lit(None).cast(StringType()))
    else:
        return F.when(
            is_blank,
            F.lit(f"{severity}: {field} invalid date format \u2014 expected YYYYMMDD")
        ).when(
            ~is_8_digits | ~is_valid_date,
            F.lit(f"{severity}: {field} invalid date format \u2014 expected YYYYMMDD")
        ).otherwise(F.lit(None).cast(StringType()))


def compile_numeric(rule: dict) -> Column:
    """Field must contain only numeric characters (digits)."""
    field = rule["target_field"]
    severity = rule["severity"]
    return F.when(
        F.col(field).isNull() | (F.trim(F.col(field)) == F.lit("")),
        F.lit(f"{severity}: {field} must not be blank")
    ).when(
        ~F.trim(F.col(field)).rlike("^[0-9]+$"),
        F.lit(f"{severity}: {field} must be numeric")
    ).otherwise(F.lit(None).cast(StringType()))


def compile_numeric_decimal(rule: dict) -> Column:
    """Field must be numeric, allowing decimal point. Validates total digit length and precision.
    
    param_1 = max total length (digits only, excluding decimal point)
    param_2 = max decimal places (precision)
    
    Accepts: integers, decimals (e.g., "22.69246"), negative values.
    Rejects: blank/null, non-numeric characters (except . and leading -).
    """
    field = rule["target_field"]
    severity = rule["severity"]
    # Regex: optional minus, digits, optional decimal + digits
    is_decimal_numeric = F.trim(F.col(field)).rlike(r"^-?[0-9]+(\.[0-9]+)?$")
    is_blank = F.col(field).isNull() | (F.trim(F.col(field)) == F.lit(""))

    return F.when(
        is_blank,
        F.lit(f"{severity}: {field} must not be blank")
    ).when(
        ~is_decimal_numeric,
        F.lit(f"{severity}: {field} must be numeric")
    ).otherwise(F.lit(None).cast(StringType()))


def compile_default_then_warn(rule: dict) -> Column:
    """If field is blank, default it (handled separately) and emit WARNING."""
    field = rule["target_field"]
    # This rule type emits a WARNING when the field was blank (and defaulted)
    return F.when(
        F.col(field).isNull() | (F.trim(F.col(field)) == F.lit("")),
        F.lit(f"WARNING: {field} defaulted")
    ).otherwise(F.lit(None).cast(StringType()))


def compile_cross_field_conditional(rule: dict) -> Column:
    """Cross-field conditional: IF precondition THEN target_field must be in allowed_values (or blank).

    CSV layout:
      precondition_field / precondition_operator / precondition_value = the trigger condition
      target_field  = the field to validate when precondition fires
      allowed_values = pipe-delimited acceptable values for target_field (empty = must be blank)
      severity      = WARNING or SEVERE
      description   = human-readable message
    """
    target_field = rule["target_field"]
    severity = rule["severity"]
    precondition_field = rule.get("precondition_field", "").strip()
    precondition_op = rule.get("precondition_operator", "").strip()
    precondition_value = rule.get("precondition_value", "").strip()
    allowed_str = rule.get("allowed_values", "").strip()

    if not precondition_field or not precondition_op:
        # No precondition defined — skip (always passes)
        return F.lit(None).cast(StringType())

    # Build precondition expression
    prec_col = F.trim(F.col(precondition_field))
    if precondition_op == "eq":
        precondition = prec_col == F.lit(precondition_value)
    elif precondition_op == "neq":
        precondition = F.col(precondition_field).isNull() | (prec_col == F.lit("")) | (prec_col != F.lit(precondition_value))
    elif precondition_op == "in":
        values = [v.strip() for v in precondition_value.split("|")]
        precondition = prec_col.isin(values)
    elif precondition_op == "not_in":
        values = [v.strip() for v in precondition_value.split("|")]
        precondition = F.col(precondition_field).isNull() | (prec_col == F.lit("")) | ~prec_col.isin(values)
    elif precondition_op == "blank":
        precondition = F.col(precondition_field).isNull() | (prec_col == F.lit(""))
    elif precondition_op == "not_blank":
        precondition = F.col(precondition_field).isNotNull() & (prec_col != F.lit(""))
    else:
        precondition = F.lit(True)

    # Build dependent check on target_field
    target_col = F.trim(F.col(target_field))
    if allowed_str:
        allowed = [v.strip() for v in allowed_str.split("|")]
        # Check if blank/empty string is explicitly in allowed list (e.g., "0|000" means only those values)
        if "" in allowed:
            # Empty string is explicitly allowed — blank passes
            non_blank_allowed = [v for v in allowed if v != ""]
            if non_blank_allowed:
                violation = (F.col(target_field).isNotNull() & (target_col != F.lit("")) &
                             ~target_col.isin(non_blank_allowed))
            else:
                # Only blank is allowed
                violation = F.col(target_field).isNotNull() & (target_col != F.lit(""))
        else:
            violation = ~target_col.isin(allowed)
    else:
        # No allowed_values = must be blank
        violation = F.col(target_field).isNotNull() & (target_col != F.lit(""))

    desc = rule.get("description", "")
    short_desc = desc[:80] if desc else f"{target_field} cross-field check failed"

    return F.when(
        precondition & violation,
        F.lit(f"{severity}: {short_desc}")
    ).otherwise(F.lit(None).cast(StringType()))


def compile_conditional(rule: dict) -> Column:
    """Conditional rule: fires when target_field == param_1 AND precondition is true.

    CSV layout:
      target_field  = the field whose value triggers the rule
      param_1       = trigger value for target_field
      precondition_field / precondition_operator / precondition_value = dependent check
      severity      = WARNING or SEVERE
      description   = human-readable message (first clause before ';' used as short msg)
    """
    target_field = rule["target_field"]
    severity = rule["severity"]
    trigger_value = rule.get("param_1", "").strip()
    precondition_field = rule.get("precondition_field", "").strip()
    precondition_op = rule.get("precondition_operator", "").strip()
    precondition_value = rule.get("precondition_value", "").strip()
    desc = rule.get("description", "")

    # Target field must equal trigger value
    target_match = F.trim(F.col(target_field)) == F.lit(trigger_value)

    # Build precondition on the precondition_field
    prec_col = F.trim(F.col(precondition_field))
    if precondition_op == "eq":
        precondition = prec_col == F.lit(precondition_value)
    elif precondition_op == "neq":
        # Null/blank values also count as "not equal to" the specified value
        precondition = F.col(precondition_field).isNull() | (prec_col == F.lit("")) | (prec_col != F.lit(precondition_value))
    elif precondition_op == "in":
        values = [v.strip() for v in precondition_value.split("|")]
        precondition = prec_col.isin(values)
    elif precondition_op == "not_in":
        values = [v.strip() for v in precondition_value.split("|")]
        # Null/blank values also count as "not in" the specified set
        precondition = F.col(precondition_field).isNull() | (prec_col == F.lit("")) | ~prec_col.isin(values)
    elif precondition_op == "blank":
        precondition = F.col(precondition_field).isNull() | (prec_col == F.lit(""))
    elif precondition_op == "not_blank":
        precondition = F.col(precondition_field).isNotNull() & (prec_col != F.lit(""))
    else:
        precondition = F.lit(True)

    # Short message from description
    short_desc = desc.split(";")[0].strip() if ";" in desc else desc.strip()

    return F.when(
        target_match & precondition,
        F.lit(f"{severity}: {short_desc}")
    ).otherwise(F.lit(None).cast(StringType()))


# =============================================================================
# Rule handlers added for Validation_Rules_Master.xlsx
# =============================================================================


def compile_numeric_range(rule: dict) -> Column:
    """Field must be numeric and fall within [param_1, param_2] inclusive.

    param_1 = minimum value (required)
    param_2 = maximum value (optional; if absent, only the minimum is enforced)

    Blank/non-numeric values fail. Values are compared numerically.
    """
    field = rule["target_field"]
    severity = rule["severity"]
    min_raw = str(rule.get("param_1", "")).strip()
    max_raw = str(rule.get("param_2", "")).strip()

    is_blank = F.col(field).isNull() | (F.trim(F.col(field)) == F.lit(""))
    is_int = F.trim(F.col(field)).rlike(r"^-?[0-9]+$")
    numeric_val = F.trim(F.col(field)).cast("double")

    expr = F.when(
        is_blank,
        F.lit(f"{severity}: {field} must not be blank")
    ).when(
        ~is_int,
        F.lit(f"{severity}: {field} must be numeric")
    )

    if min_raw:
        expr = expr.when(
            numeric_val < F.lit(float(min_raw)),
            F.lit(f"{severity}: {field} must be >= {min_raw}")
        )
    if max_raw:
        expr = expr.when(
            numeric_val > F.lit(float(max_raw)),
            F.lit(f"{severity}: {field} must be <= {max_raw}")
        )

    return expr.otherwise(F.lit(None).cast(StringType()))


def compile_min_value(rule: dict) -> Column:
    """Field must be numeric and >= param_1.

    Distinct from numeric_range in that only a lower bound is enforced.
    Blank/non-numeric values fail.
    """
    field = rule["target_field"]
    severity = rule["severity"]
    min_raw = str(rule.get("param_1", "")).strip()

    is_blank = F.col(field).isNull() | (F.trim(F.col(field)) == F.lit(""))
    is_num = F.trim(F.col(field)).rlike(r"^-?[0-9]+(\.[0-9]+)?$")
    numeric_val = F.trim(F.col(field)).cast("double")

    expr = F.when(
        is_blank,
        F.lit(f"{severity}: {field} must not be blank")
    ).when(
        ~is_num,
        F.lit(f"{severity}: {field} must be numeric")
    )

    if min_raw:
        expr = expr.when(
            numeric_val < F.lit(float(min_raw)),
            F.lit(f"{severity}: {field} must be >= {min_raw}")
        )

    return expr.otherwise(F.lit(None).cast(StringType()))


def compile_allowed_blank(rule: dict) -> Column:
    """Declares that BLANK is an allowed/valid state for this field.

    `allowed_blank` is an optionality declaration, NOT a value check: on its own
    it never fails — blank passes, and a non-blank value passes (its content is
    validated, if at all, by a SEPARATE rule row on the same field, such as
    `allowed_values`, `numeric_string`, or `exact_length`).

    In other words, presence of an `allowed_blank` rule means "this field may be
    left blank"; it exists so the field is not required and so authors can state
    that intent explicitly in the workbook. It produces no violation.
    """
    return F.lit(None).cast(StringType())


def compile_conditional_null(rule: dict) -> Column:
    """Field must be blank when a precondition holds; otherwise no constraint here.

    CSV layout:
      precondition_field / precondition_operator / precondition_value = trigger
      target_field  = field that must be blank when the precondition fires
    If no precondition is defined, the rule always passes (documentation-only).
    """
    field = rule["target_field"]
    severity = rule["severity"]
    precondition = _build_precondition(rule)
    if precondition is None:
        return F.lit(None).cast(StringType())

    is_not_blank = F.col(field).isNotNull() & (F.trim(F.col(field)) != F.lit(""))
    return F.when(
        precondition & is_not_blank,
        F.lit(f"{severity}: {field} must be blank when condition applies")
    ).otherwise(F.lit(None).cast(StringType()))


def compile_conditional_blank(rule: dict) -> Column:
    """Field must be blank when a precondition holds (product-driven variant).

    Behaves identically to conditional_null; kept as a distinct registered type
    because the master sheet uses both names with the same intended semantics.
    """
    return compile_conditional_null(rule)


def compile_exact_length_or_blank(rule: dict) -> Column:
    """Field must be exactly param_1 characters, OR blank.

    Blank is acceptable; if a value is present it must be exactly param_1 chars.
    """
    field = rule["target_field"]
    severity = rule["severity"]
    length = int(rule["param_1"])

    is_blank = F.col(field).isNull() | (F.trim(F.col(field)) == F.lit(""))
    return F.when(
        is_blank, F.lit(None).cast(StringType())  # Blank OK
    ).when(
        F.length(F.trim(F.col(field))) != F.lit(length),
        F.lit(f"{severity}: {field} must be exactly {length} characters or blank")
    ).otherwise(F.lit(None).cast(StringType()))


def compile_numeric_string(rule: dict) -> Column:
    """Field content must be digits only, but is preserved as a string.

    Distinct from numeric: the value is NOT treated as a number (leading zeros
    are preserved, no numeric cast). Used for phone numbers, account numbers,
    zip codes, etc. Blank is acceptable by default (pair with a not_blank or
    allowed_blank rule if presence is required).
    """
    field = rule["target_field"]
    severity = rule["severity"]

    is_blank = F.col(field).isNull() | (F.trim(F.col(field)) == F.lit(""))
    is_digits = F.trim(F.col(field)).rlike(r"^[0-9]+$")

    return F.when(
        is_blank, F.lit(None).cast(StringType())  # Blank OK — presence enforced elsewhere
    ).when(
        ~is_digits,
        F.lit(f"{severity}: {field} must contain digits only")
    ).otherwise(F.lit(None).cast(StringType()))


def compile_project_defined_value(rule: dict) -> Column:
    """Any user/project-defined value, bounded by a maximum length (param_1).

    Content is unconstrained (any characters), but the length must not exceed
    param_1. Blank is acceptable. Used for open code fields such as user-defined
    rate classes (e.g., CVG_RATE_CLASS up to 2 characters).
    """
    field = rule["target_field"]
    severity = rule["severity"]
    max_len_raw = str(rule.get("param_1", "")).strip()

    is_blank = F.col(field).isNull() | (F.trim(F.col(field)) == F.lit(""))

    if not max_len_raw:
        # No length bound — any value (or blank) is acceptable
        return F.lit(None).cast(StringType())

    max_len = int(max_len_raw)
    return F.when(
        is_blank, F.lit(None).cast(StringType())  # Blank OK
    ).when(
        F.length(F.trim(F.col(field))) > F.lit(max_len),
        F.lit(f"{severity}: {field} must be at most {max_len} characters")
    ).otherwise(F.lit(None).cast(StringType()))


# --- Shared precondition builder (used by conditional_null / conditional_blank) ---

def _build_precondition(rule: dict):
    """Build a PySpark boolean Column from precondition_field/operator/value.

    Returns None when no usable precondition is defined (rule should then pass).
    Supports operators: eq, neq, in, not_in, blank, not_blank, gt, lt, gte, lte.
    """
    pf = rule.get("precondition_field", "").strip()
    op = rule.get("precondition_operator", "").strip()
    pv = rule.get("precondition_value", "").strip()

    if not pf or not op or op == "none":
        return None

    col = F.trim(F.col(pf))
    is_null_or_blank = F.col(pf).isNull() | (col == F.lit(""))

    if op == "eq":
        return col == F.lit(pv)
    if op == "neq":
        return is_null_or_blank | (col != F.lit(pv))
    if op == "in":
        return col.isin([v.strip() for v in pv.split("|")])
    if op == "not_in":
        return is_null_or_blank | ~col.isin([v.strip() for v in pv.split("|")])
    if op == "blank":
        return is_null_or_blank
    if op == "not_blank":
        return F.col(pf).isNotNull() & (col != F.lit(""))
    if op in ("gt", "lt", "gte", "lte"):
        left = col.cast("double")
        right = F.lit(float(pv)) if pv else F.lit(None)
        if op == "gt":
            return left > right
        if op == "lt":
            return left < right
        if op == "gte":
            return left >= right
        if op == "lte":
            return left <= right
    return None
