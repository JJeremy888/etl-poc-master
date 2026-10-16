"""Transform POC_Transformation_Mapping_scoped.csv into the template schema for templates/v1/transformation_mappings.csv."""

import csv
import re
import sys
from pathlib import Path

# Paths
ROOT = Path(__file__).resolve().parent.parent
SOURCE_PATH = ROOT / "rules" / "POC_Transformation_Mapping_scoped.csv"
OUTPUT_DIR = ROOT / "templates" / "v1"
OUTPUT_PATH = OUTPUT_DIR / "transformation_mappings.csv"

# Target schema columns
TARGET_COLUMNS = [
    "mapping_id",
    "source_table",
    "source_field",
    "target_field",
    "transformation_type",
    "target_length",
    "target_data_type",
    "padding_rule",
    "default_value",
    "date_handling",
    "truncation_rule",
    "sequence",
    "description",
]

# Transformation type mapping
TRANSFORMATION_TYPE_MAP = {
    "DIRECT_SOURCE": "direct_copy",
    "CONSTANT": "constant",
    "INITIALIZE_SPACES": "space_fill",
    "INITIALIZE_NUMERIC_OR_DATE": "zero_fill",
    "SYSTEM_GENERATED": "system_generated",
    "CONDITIONAL_OR_DERIVED": "conditional_derived",
    "GROUP_OR_PARENT": "skip",
}


def normalize_padding_rule(raw: str) -> str:
    """Normalize Padding Rule to template values."""
    if not raw or not raw.strip():
        return ""
    lower = raw.strip().lower()
    if lower.startswith("right pad with spaces"):
        return "right_space"
    if lower.startswith("left pad with zeroes") or lower.startswith("left pad with zeros"):
        return "left_zero"
    if lower.startswith("no padding after split"):
        return "none"
    return ""


def normalize_truncation_rule(raw: str) -> str:
    """Normalize Truncation Rule to template values."""
    if not raw or not raw.strip():
        return ""
    lower = raw.strip().lower()
    if lower.startswith("do not truncate"):
        return "none"
    # For any other value, keep as-is or empty
    return ""


def determine_date_split_type(target_field: str, target_length: str) -> str:
    """Determine DATE_SPLIT sub-type from target field name and length."""
    field_upper = target_field.upper()
    length = int(target_length) if target_length.strip().isdigit() else 0

    # Check for year indicators
    if length == 4:
        return "date_split_year"
    if "YY" in field_upper or "YR" in field_upper:
        return "date_split_year"

    # Check for month indicators
    if "MM" in field_upper or "MO" in field_upper:
        return "date_split_month"

    # Check for day indicators
    if "DD" in field_upper or "DA" in field_upper:
        return "date_split_day"

    # Fallback based on length alone (2 chars could be month or day - ambiguous)
    if length == 2:
        # Can't determine without name; default to day as last resort
        return "date_split_day"

    return "date_split_year"


def map_transformation_type(raw_type: str, target_field: str, target_length: str) -> str:
    """Map source Transformation Type to template value."""
    raw = raw_type.strip()

    if raw == "DATE_SPLIT":
        return determine_date_split_type(target_field, target_length)

    mapped = TRANSFORMATION_TYPE_MAP.get(raw)
    if mapped:
        return mapped

    # Fallback for unknown types
    return raw.lower()


def truncate_description(desc: str, max_len: int = 100) -> str:
    """Truncate description to max_len chars."""
    if not desc:
        return ""
    desc = desc.strip()
    # Remove newlines, collapse whitespace
    desc = re.sub(r'\s+', ' ', desc)
    if len(desc) > max_len:
        return desc[:max_len]
    return desc


def transform_row(row: dict, idx: int) -> dict | None:
    """Transform a single source row into the template schema. Returns None for skipped rows."""
    raw_type = row.get("Transformation Type", "").strip()

    # Skip GROUP_OR_PARENT rows
    if raw_type == "GROUP_OR_PARENT":
        return None

    target_field = row.get("Target Field", "").strip()
    target_length = row.get("Target Length", "").strip()

    mapping_id = f"MAP_{idx:03d}"
    source_table = row.get("Source Table(s)", "").strip()
    source_field = row.get("Source Field(s)", "").strip()
    transformation_type = map_transformation_type(raw_type, target_field, target_length)
    target_data_type = row.get("Target Data Type", "").strip()
    padding_rule = normalize_padding_rule(row.get("Padding Rule", ""))
    default_value = row.get("Default / Constant Value", "").strip()
    date_handling = row.get("Date Handling", "").strip()
    truncation_rule = normalize_truncation_rule(row.get("Truncation Rule", ""))
    sequence = row.get("Original Sheet Row", "").strip()
    description = truncate_description(row.get("Definition", ""))

    return {
        "mapping_id": mapping_id,
        "source_table": source_table,
        "source_field": source_field,
        "target_field": target_field,
        "transformation_type": transformation_type,
        "target_length": target_length,
        "target_data_type": target_data_type,
        "padding_rule": padding_rule,
        "default_value": default_value,
        "date_handling": date_handling,
        "truncation_rule": truncation_rule,
        "sequence": sequence,
        "description": description,
    }


def main():
    """Main entry point: read source, transform, write output."""
    if not SOURCE_PATH.exists():
        print(f"ERROR: Source file not found: {SOURCE_PATH}", file=sys.stderr)
        sys.exit(1)

    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Read source CSV
    with open(SOURCE_PATH, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        source_rows = list(reader)

    print(f"Read {len(source_rows)} rows from source file")

    # Transform rows
    output_rows = []
    skipped = 0
    idx = 1  # Sequential mapping_id counter

    for row in source_rows:
        result = transform_row(row, idx)
        if result is None:
            skipped += 1
            continue
        output_rows.append(result)
        idx += 1

    print(f"Transformed {len(output_rows)} rows ({skipped} skipped as GROUP_OR_PARENT)")

    # Write output CSV
    with open(OUTPUT_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TARGET_COLUMNS)
        writer.writeheader()
        writer.writerows(output_rows)

    print(f"Written to: {OUTPUT_PATH}")
    print(f"Final row count: {len(output_rows)}")

    # Verify: 400 source rows minus GROUP_OR_PARENT exclusions = expected output
    expected = len(source_rows) - skipped
    if len(output_rows) != expected:
        print(f"ERROR: Row count mismatch! Expected {expected}, got {len(output_rows)}")
        sys.exit(1)

    print(f"Verification: {len(source_rows)} source - {skipped} GROUP_OR_PARENT = {len(output_rows)} output rows")
    return len(output_rows)


if __name__ == "__main__":
    count = main()
