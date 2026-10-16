"""Error Logger — Persist Error_Records with full diagnostic detail."""
import json
from datetime import datetime, timezone
from pathlib import Path
from pyspark.sql import DataFrame, functions as F


def log_errors(
    validated_df: DataFrame,
    table_name: str,
    template_version: str,
    batch_run_id: str,
    output_dir: str,
) -> int:
    """Extract and persist all Error_Records from VAL_ columns.

    Returns count of errors logged.
    """
    val_cols = [c for c in validated_df.columns if c.startswith("VAL_")]
    if not val_cols:
        return 0

    output_path = Path(output_dir) / "errors"
    output_path.mkdir(parents=True, exist_ok=True)

    error_records = []

    # Collect only rows with at least one non-null VAL_ column
    # Use a filter to find failing rows
    has_error = F.lit(False)
    for vc in val_cols:
        has_error = has_error | F.col(vc).isNotNull()

    error_df = validated_df.filter(has_error)
    
    # Use toPandas() for more reliable serialization on Windows
    try:
        error_pdf = error_df.toPandas()
    except Exception:
        # Fallback: write to temp CSV and read back
        import tempfile, csv
        temp_path = Path(output_dir) / "errors" / f"_temp_{table_name}.csv"
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        error_df.write.mode("overwrite").option("header", "true").csv(str(temp_path))
        # Read back from CSV
        import pandas as pd
        csv_files = list(temp_path.glob("*.csv"))
        if csv_files:
            error_pdf = pd.concat([pd.read_csv(f) for f in csv_files])
        else:
            error_pdf = pd.DataFrame()
        # Clean up
        import shutil
        shutil.rmtree(str(temp_path), ignore_errors=True)

    for _, row_dict in error_pdf.iterrows():
        for vc in val_cols:
            error_msg = row_dict.get(vc)
            if error_msg and str(error_msg) != 'nan' and str(error_msg).strip():
                error_msg = str(error_msg)
                # Extract field name from VAL_ column name
                field_name = vc.replace("VAL_", "").replace(f"_{table_name}_CROSS_TABLE", "_CROSS_REF")
                severity = "SEVERE" if error_msg.startswith("SEVERE:") else "WARNING"

                error_records.append({
                    "batch_run_id": batch_run_id,
                    "template_version": template_version,
                    "table_name": table_name,
                    "record_key": _get_record_key_from_pandas(row_dict, table_name),
                    "field_name": field_name,
                    "rule_type": vc,
                    "severity": severity,
                    "error_message": error_msg,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })

    # Write as JSON lines
    errors_file = output_path / f"{table_name.lower()}_errors.jsonl"
    with open(errors_file, "w", encoding="utf-8") as f:
        for record in error_records:
            f.write(json.dumps(record) + "\n")

    return len(error_records)


def _get_record_key(row_dict: dict, table_name: str) -> str:
    """Extract the primary key from a row based on table prefix."""
    prefix = table_name + "_"
    company = row_dict.get(f"{prefix}COMPANY_CODE", "")
    policy = row_dict.get(f"{prefix}POLICY_NUMBER", "")
    return f"{company}|{policy}" if company or policy else "UNKNOWN"


def _get_record_key_from_pandas(row_dict, table_name: str) -> str:
    """Extract the primary key from a pandas row based on table prefix."""
    prefix = table_name + "_"
    company = str(row_dict.get(f"{prefix}COMPANY_CODE", "") or "")
    policy = str(row_dict.get(f"{prefix}POLICY_NUMBER", "") or "")
    if company == 'nan':
        company = ""
    if policy == 'nan':
        policy = ""
    return f"{company}|{policy}" if company or policy else "UNKNOWN"


def query_errors(output_dir: str, filters: dict = None) -> list[dict]:
    """Query stored error records with optional filters."""
    output_path = Path(output_dir) / "errors"
    if not output_path.exists():
        return []

    all_errors = []
    for jsonl_file in output_path.glob("*_errors.jsonl"):
        with open(jsonl_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    all_errors.append(json.loads(line))

    if not filters:
        return all_errors

    # Apply filters
    result = all_errors
    for key, value in filters.items():
        result = [e for e in result if e.get(key) == value]

    return result
