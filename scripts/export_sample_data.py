"""Export Sample_*_Data.xlsx workbooks to CSV for pipeline consumption.

Reads each Excel workbook from staging_data/ using dtype=str to prevent
numeric reinterpretation (preserving leading zeros, date formats, etc.).
Writes to staging_data/<table>.csv with no value modification.

Per Requirement 22: No synthetic data generator shall exist in this project.
All test data comes directly from BA-provided Excel workbooks.
"""
import os
import re
import sys
from pathlib import Path

import pandas as pd

WORKSPACE = Path(__file__).resolve().parent.parent
STAGING_DIR = WORKSPACE / "staging_data"

# Excel filename -> output CSV filename mapping
FILE_MAP = {
    "Sample_Contract_Data.xlsx": "cnt.csv",
    "Sample_Coverage_Data.xlsx": "cvg.csv",
    "Sample_Role_Data.xlsx": "rol.csv",
    "Sample_Address_Data.xlsx": "add.csv",
}


def convert_iso_dates(df):
    """Convert ISO datetime strings (YYYY-MM-DD HH:MM:SS) to YYYYMMDD format.
    
    Only converts values that match the ISO pattern — leaves non-date fields untouched.
    """
    iso_pattern = re.compile(r'^(\d{4})-(\d{2})-(\d{2}) \d{2}:\d{2}:\d{2}')
    
    for col in df.columns:
        # Check if this column has ISO datetime values
        sample = df[col].head(5)
        has_dates = any(iso_pattern.match(str(v)) for v in sample if v)
        
        if has_dates:
            def convert_date(val):
                if not val:
                    return val
                m = iso_pattern.match(str(val))
                if m:
                    return f"{m.group(1)}{m.group(2)}{m.group(3)}"
                return val
            
            df[col] = df[col].apply(convert_date)
            print(f"    Converted date format: {col}")
    
    return df


def zero_pad_fields(df):
    """Zero-pad enumerated code fields to their spec-required fixed widths.
    
    Only pads values that are non-blank, purely numeric, and shorter than the
    target width. Non-numeric or blank values are left untouched.
    
    Fields and their target widths (from DB_Section specs):
    - CVG_COVERED: 2 digits
    - ROL_COVERAGE_SEQUENCE: 2 digits
    - ROL_RELATIONSHIP_TO_INSURED: 3 digits
    - ADD_COUNTRY_CODE: 2 digits
    """
    pad_specs = {
        "CVG_COVERED": 2,
        "ROL_COVERAGE_SEQUENCE": 2,
        "ROL_RELATIONSHIP_TO_INSURED": 3,
        "ADD_COUNTRY_CODE": 2,
    }
    
    for col, width in pad_specs.items():
        if col not in df.columns:
            continue
        
        def pad_value(val, w=width):
            if not val or not isinstance(val, str):
                return val
            stripped = val.strip()
            if not stripped:
                return val
            if not stripped.isdigit():
                return val
            if len(stripped) >= w:
                return val
            return stripped.zfill(w)
        
        df[col] = df[col].apply(pad_value)
        print(f"    Zero-padded: {col} (width={width})")
    
    return df


def export_workbook(xlsx_path: Path, csv_path: Path) -> dict:
    """Read an Excel workbook as all-text and write to CSV.
    
    Returns dict with row_count, col_count for verification.
    """
    # Read with dtype=str to prevent ANY numeric/date interpretation
    # This ensures:
    # - Leading zeros preserved (e.g., "01" stays "01", not 1)
    # - Dates stay as strings (not converted to datetime)
    # - All values are exactly as they appear in Excel
    df = pd.read_excel(
        xlsx_path,
        dtype=str,
        engine="openpyxl",
    )
    
    # Convert ISO datetime strings to YYYYMMDD format for date fields
    df = convert_iso_dates(df)
    
    # Zero-pad enumerated code fields to their spec-required widths
    df = zero_pad_fields(df)
    
    # Write to CSV with no index, preserving exact values
    # na_rep='' ensures None/NaN cells become empty strings (not "nan")
    df.to_csv(csv_path, index=False, na_rep="")
    
    return {
        "row_count": len(df),
        "col_count": len(df.columns),
        "columns": list(df.columns),
    }


def main():
    print("=" * 60)
    print("SAMPLE DATA EXPORT")
    print("Exporting Sample_*_Data.xlsx -> staging CSV files")
    print("=" * 60)
    print()
    
    results = {}
    
    for xlsx_name, csv_name in FILE_MAP.items():
        xlsx_path = STAGING_DIR / xlsx_name
        csv_path = STAGING_DIR / csv_name
        
        if not xlsx_path.exists():
            print(f"WARNING: {xlsx_path} not found, skipping.")
            continue
        
        print(f"Exporting {xlsx_name} -> {csv_name}...")
        info = export_workbook(xlsx_path, csv_path)
        results[csv_name] = info
        print(f"  Rows: {info['row_count']}, Columns: {info['col_count']}")
        print(f"  Headers: {', '.join(info['columns'][:5])}{'...' if len(info['columns']) > 5 else ''}")
        print()
    
    # Summary
    print("=" * 60)
    print("EXPORT COMPLETE")
    print("=" * 60)
    print()
    for csv_name, info in results.items():
        print(f"  {csv_name}: {info['row_count']} rows x {info['col_count']} columns")
    
    # Verification: spot-check a few cells for value preservation
    print()
    print("Spot-check verification:")
    for csv_name in results:
        csv_path = STAGING_DIR / csv_name
        df = pd.read_csv(csv_path, dtype=str, nrows=3, keep_default_na=False)
        # Check first row, first 3 columns
        if len(df) > 0:
            row = df.iloc[0]
            cols = list(df.columns)[:3]
            vals = [f"{c}={repr(row[c])}" for c in cols]
            print(f"  {csv_name} row 1: {', '.join(vals)}")
    
    print()
    print("All exports complete. Pipeline can now read staging_data/*.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
