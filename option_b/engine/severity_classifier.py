"""Severity Classifier — Assign ROW_SEVERITY based on all VAL_ columns."""
from pyspark.sql import DataFrame, functions as F
from pyspark.sql.types import StringType


def classify_severity(df: DataFrame) -> DataFrame:
    """Assign ROW_SEVERITY based on all VAL_ columns.

    SEVERE: if any VAL_ column value starts with "SEVERE:"
    WARNING: if any VAL_ column starts with "WARNING:" and none start with "SEVERE:"
    CLEAN: if all VAL_ columns are None
    """
    val_cols = [c for c in df.columns if c.startswith("VAL_")]

    if not val_cols:
        return df.withColumn("ROW_SEVERITY", F.lit("CLEAN"))

    # Build has_severe and has_warning conditions
    has_severe = F.lit(False)
    has_warning = F.lit(False)

    for col_name in val_cols:
        col = F.col(col_name)
        has_severe = has_severe | (col.isNotNull() & col.startswith("SEVERE:"))
        has_warning = has_warning | (col.isNotNull() & col.startswith("WARNING:"))

    return df.withColumn(
        "ROW_SEVERITY",
        F.when(has_severe, F.lit("SEVERE"))
        .when(has_warning, F.lit("WARNING"))
        .otherwise(F.lit("CLEAN"))
    )
