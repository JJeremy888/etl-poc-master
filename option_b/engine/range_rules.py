"""Range validation rule compilers — date and numeric comparisons."""
from pyspark.sql import Column, functions as F
from pyspark.sql.types import StringType


def _safe_to_date(col_expr):
    """Parse date safely using try_to_timestamp to avoid ANSI exceptions on invalid dates."""
    return F.to_date(F.try_to_timestamp(col_expr, F.lit("yyyyMMdd")))


def compile_date_greater_than(rule: dict) -> Column:
    """target_field date must be strictly greater than compare_field date."""
    field = rule["target_field"]
    compare = rule["compare_field"]
    severity = rule["severity"]

    target_date = _safe_to_date(F.trim(F.col(field)))
    compare_date = _safe_to_date(F.trim(F.col(compare)))

    # Only compare when both fields have valid dates
    both_valid = target_date.isNotNull() & compare_date.isNotNull()

    return F.when(
        ~both_valid, F.lit(None).cast(StringType())  # Skip if either is invalid (format check handles that)
    ).when(
        target_date <= compare_date,
        F.lit(f"{severity}: {field} not greater than {compare}")
    ).otherwise(F.lit(None).cast(StringType()))


def compile_date_lte(rule: dict) -> Column:
    """target_field date must be less than or equal to compare_field date."""
    field = rule["target_field"]
    compare = rule["compare_field"]
    severity = rule["severity"]

    target_date = _safe_to_date(F.trim(F.col(field)))
    compare_date = _safe_to_date(F.trim(F.col(compare)))

    both_valid = target_date.isNotNull() & compare_date.isNotNull()

    return F.when(
        ~both_valid, F.lit(None).cast(StringType())
    ).when(
        target_date > compare_date,
        F.lit(f"{severity}: {field} not <= {compare}")
    ).otherwise(F.lit(None).cast(StringType()))


# =============================================================================
# Handlers added for Validation_Rules_Master.xlsx (cross-reference date checks)
# =============================================================================


def compile_date_less_than_equal(rule: dict) -> Column:
    """target_field date must be <= compare_field date.

    Same semantics as compile_date_lte, exposed under the cross-reference type
    name 'date_less_than_equal' used in cross_references.csv. Both fields must
    parse to valid dates for the comparison to fire (format is enforced by the
    field-level valid_date rule).
    """
    field = rule["target_field"]
    compare = rule["compare_field"]
    severity = rule["severity"]

    target_date = _safe_to_date(F.trim(F.col(field)))
    compare_date = _safe_to_date(F.trim(F.col(compare)))

    both_valid = target_date.isNotNull() & compare_date.isNotNull()

    return F.when(
        ~both_valid, F.lit(None).cast(StringType())
    ).when(
        target_date > compare_date,
        F.lit(f"{severity}: {field} must be on or before {compare}")
    ).otherwise(F.lit(None).cast(StringType()))
