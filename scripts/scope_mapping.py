"""
Script to filter POC_Transformation_Mapping.csv to create a scoped version for the POC.

Inclusion criteria (both must be met):
1. Source Table(s) column contains ONLY tables from {CNT, CVG, ROL, ADD}
   - Empty/blank Source Table(s) are included (SYSTEM_GENERATED/INITIALIZE_SPACES rows)
2. Mapping Status is either "Confirmed for POC Review" OR "System Generated"
"""

import csv
import sys
import os

ALLOWED_TABLES = {"CNT", "CVG", "ROL", "ADD"}
ALLOWED_STATUSES = {"Confirmed for POC Review", "System Generated"}

def main():
    input_path = os.path.join(os.path.dirname(__file__), "..", "rules", "POC_Transformation_Mapping.csv")
    output_path = os.path.join(os.path.dirname(__file__), "..", "rules", "POC_Transformation_Mapping_scoped.csv")

    input_path = os.path.abspath(input_path)
    output_path = os.path.abspath(output_path)

    # Read all rows
    with open(input_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        all_rows = list(reader)

    total_original = len(all_rows)

    included = []
    excluded_source_table = []  # Group A
    excluded_status = []  # Group B

    for row in all_rows:
        source_tables_raw = row.get("Source Table(s)", "").strip()
        mapping_status = row.get("Mapping Status", "").strip()

        # Check Source Table(s) criterion
        source_tables_ok = True
        unsupported_tables = set()
        if source_tables_raw:
            tables = [t.strip() for t in source_tables_raw.split(";")]
            for t in tables:
                if t and t not in ALLOWED_TABLES:
                    source_tables_ok = False
                    unsupported_tables.add(t)

        # Check Mapping Status criterion
        status_ok = mapping_status in ALLOWED_STATUSES

        if source_tables_ok and status_ok:
            included.append(row)
        elif not source_tables_ok:
            # Excluded by source table (Group A takes priority)
            excluded_source_table.append({
                "target_field": row.get("Target Field", ""),
                "unsupported_tables": unsupported_tables,
                "source_tables_raw": source_tables_raw,
            })
        else:
            # source_tables_ok but status not ok (Group B)
            excluded_status.append({
                "target_field": row.get("Target Field", ""),
                "mapping_status": mapping_status,
            })

    # Write scoped output
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(included)

    total_scoped = len(included)

    # Report
    print("=" * 70)
    print("POC_Transformation_Mapping Scoping Report")
    print("=" * 70)
    print(f"\n1. Total rows in original (excluding header): {total_original}")
    print(f"2. Total rows in scoped output (excluding header): {total_scoped}")
    print(f"   Excluded total: {total_original - total_scoped}")

    print(f"\n3. Exclusion Details:")
    print(f"\n   GROUP A: Excluded because Source Table(s) contains a table NOT in {{CNT, CVG, ROL, ADD}}")
    print(f"   Count: {len(excluded_source_table)}")
    print(f"   {'Target Field':<45} {'Unsupported Table(s)'}")
    print(f"   {'-'*45} {'-'*25}")
    for item in excluded_source_table:
        print(f"   {item['target_field']:<45} {', '.join(sorted(item['unsupported_tables']))}")

    print(f"\n   GROUP B: Excluded because Mapping Status is NOT 'Confirmed for POC Review' or 'System Generated'")
    print(f"   Count: {len(excluded_status)}")
    print(f"   {'Target Field':<45} {'Actual Mapping Status'}")
    print(f"   {'-'*45} {'-'*30}")
    for item in excluded_status:
        print(f"   {item['target_field']:<45} {item['mapping_status']}")

    print(f"\n{'=' * 70}")


if __name__ == "__main__":
    main()
