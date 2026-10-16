"""Generate transformation_mappings.csv from EA_Transaction_Mapping.xlsx.

Reads rules/EA_Transaction_Mapping.xlsx, sheet "Trx Mapping" only.
Sheet1 (scratch notes) is excluded entirely.

COLUMN CONTRACT: only columns A (target field), B (level), C (field format /
PIC), and I (Policy Data Loader Mapping = source) are read. Columns E (Definition),
G, K, and L are intentionally NOT consumed — Column I is the sole source-of-truth
for what feeds a target field. As a result the generator no longer emits a
`description`, and does not infer `space_fill`/`default_value` from prose in G/K/L;
fields with a blank Column I have no source to map and are flagged conditional_derived.

Any row where parsing fails goes to a needs_review output.
"""
import csv
import os
import re
import sys
from pathlib import Path

import openpyxl

WORKSPACE = Path(__file__).resolve().parent.parent
RULES_DIR = WORKSPACE / "rules"
OUTPUT_DIR = WORKSPACE / "templates" / "v1"

XLSX_FILE = RULES_DIR / "EA_Transaction_Mapping.xlsx"
SHEET_NAME = "Trx Mapping"

OUTPUT_COLUMNS = [
    "mapping_id", "source_table", "source_field", "target_field",
    "transformation_type", "target_length", "target_data_type",
    "decimal_places", "signed", "comp3",
    "padding_rule", "default_value", "date_handling", "truncation_rule",
    "sequence",
]

NEEDS_REVIEW_COLUMNS = [
    "row_number", "raw_col_a", "raw_col_c", "raw_col_i", "reason",
]


def parse_target_field(col_a_value):
    """Parse target_field from Col A by stripping leading COBOL level number + whitespace.
    
    E.g. '15  COMPANY-CODE' -> 'COMPANY-CODE'
         '05  RDW-LENGTH' -> 'RDW-LENGTH'
    Returns (target_field, success) tuple.
    """
    if not col_a_value:
        return ("", False)
    text = str(col_a_value).strip()
    # Pattern: digits + whitespace + field name
    m = re.match(r'^\d+\s+(.+)$', text)
    if m:
        field = m.group(1).strip().rstrip('.')
        return (field, True)
    return ("", False)


def parse_level(col_b_value, col_a_value=None):
    """Parse the COBOL level number, preferring Col B ("Level").

    Falls back to the leading number in Col A (e.g. "88  DELETED-RECORD" -> 88)
    when Col B is blank/non-numeric. Returns an int, or None if not determinable.
    """
    if col_b_value is not None and str(col_b_value).strip():
        s = str(col_b_value).strip()
        try:
            return int(float(s))
        except (TypeError, ValueError):
            pass
    if col_a_value:
        m = re.match(r'^(\d+)\s', str(col_a_value).strip())
        if m:
            return int(m.group(1))
    return None


def parse_pic_clause(col_c_value):
    """Parse a COBOL PIC clause from Col C into structured metadata.

    Returns a 5-tuple: (data_type, length, decimal_places, signed, comp3, recognized)

    - data_type     : CHAR | NUMERIC | BINARY | PACKED_DECIMAL | "" (group/parent)
    - length        : total DIGIT/char count (int digits + decimal digits for numerics),
                      as a string; "" for group/parent rows.
    - decimal_places : number of digits AFTER the implied decimal point (V), as a string
                       ("0" for integers/char; e.g. "2" for S9(6)V99). Drives precision.
    - signed        : "Y" if the PIC has a leading S (sign), else "N".
    - comp3         : "Y" if COMP-3 (packed), else "N".
    - recognized    : bool (False only for a genuinely unparseable non-empty PIC).

    NOTE: this returns a 6-tuple. `decimal_places` and `signed`/`comp3` were
    previously computed then discarded; they are now surfaced so the transform
    can rescale precision and honor exact Cobol widths (Byers requirements #1/#2).
    """
    # Convention: (data_type, length, decimal_places, signed, comp3, recognized)
    def R(dt, ln, dec="0", signed="N", comp3="N", ok=True):
        return (dt, ln, dec, signed, comp3, ok)

    if not col_c_value:
        return R("", "", "", "N", "N", True)  # No PIC = group/parent row (valid)

    text = str(col_c_value).strip()
    if not text:
        return R("", "", "", "N", "N", True)

    # A Col C that is only a period (COBOL group terminator) is a group/parent
    # header whose YY/MM/DD children carry the data — not an unrecognized PIC.
    if set(text) <= {"."}:
        return R("", "", "", "N", "N", True)

    # 1. PIC X(n). -> CHAR, length n
    m = re.match(r'^PIC\s+X\((\d+)\)', text, re.IGNORECASE)
    if m:
        return R("CHAR", m.group(1), "0", "N", "N")

    # 2. PIC X. (single character) -> CHAR, length 1
    m = re.match(r'^PIC\s+X\.', text, re.IGNORECASE)
    if m:
        return R("CHAR", "1", "0", "N", "N")

    # 3. PIC XX. / PIC XXX. (repeated X) -> CHAR, length = count of X's
    m = re.match(r'^PIC\s+(X+)\.', text, re.IGNORECASE)
    if m:
        return R("CHAR", str(len(m.group(1))), "0", "N", "N")

    # 4. PIC 9(n). -> NUMERIC, length n, 0 decimals
    m = re.match(r'^PIC\s+9\((\d+)\)', text, re.IGNORECASE)
    if m:
        return R("NUMERIC", m.group(1), "0", "N", "N")

    # 5. PIC 9...9. (repeated 9 digits) -> NUMERIC, length = count of 9s
    m = re.match(r'^PIC\s+(9+)\.', text, re.IGNORECASE)
    if m:
        return R("NUMERIC", str(len(m.group(1))), "0", "N", "N")

    # 6. PIC S9(n) COMP. -> BINARY, length n, signed
    m = re.match(r'^PIC\s+S9\((\d+)\)\s*COMP', text, re.IGNORECASE)
    if m:
        return R("BINARY", m.group(1), "0", "Y", "N")

    # 7. PIC S9(n)V9(m) COMP-3. -> PACKED_DECIMAL, length n+m, m decimals, signed
    m = re.match(r'^PIC\s+S9\((\d+)\)V9\((\d+)\)\s*COMP-3', text, re.IGNORECASE)
    if m:
        n = int(m.group(1)); mm = int(m.group(2))
        return R("PACKED_DECIMAL", str(n + mm), str(mm), "Y", "Y")

    # 8. PIC S9(n)V99 COMP-3. (repeated 9s after V, no parens) -> n + count decimals
    m = re.match(r'^PIC\s+S9\((\d+)\)V(9+)\s*COMP-3', text, re.IGNORECASE)
    if m:
        n = int(m.group(1)); dec = len(m.group(2))
        return R("PACKED_DECIMAL", str(n + dec), str(dec), "Y", "Y")

    # 9. Non-parenthesized int part, parenthesized decimal: S99V9(m) COMP-3.
    m = re.match(r'^PIC\s+S(9+)V9\((\d+)\)\s*COMP-3', text, re.IGNORECASE)
    if m:
        int_digits = len(m.group(1)); mm = int(m.group(2))
        return R("PACKED_DECIMAL", str(int_digits + mm), str(mm), "Y", "Y")

    # 10. Fully non-parenthesized packed decimal: S99V999 COMP-3. / S9V99 COMP-3.
    m = re.match(r'^PIC\s+S(9+)V(9+)\s*COMP-3', text, re.IGNORECASE)
    if m:
        int_digits = len(m.group(1)); dec = len(m.group(2))
        return R("PACKED_DECIMAL", str(int_digits + dec), str(dec), "Y", "Y")

    # 11. Integer-only packed decimal (no V): S99 COMP-3. / S999 COMP-3.
    m = re.match(r'^PIC\s+S(9+)\s*COMP-3', text, re.IGNORECASE)
    if m:
        return R("PACKED_DECIMAL", str(len(m.group(1))), "0", "Y", "Y")

    # Not recognized
    return R("", "", "", "N", "N", False)


def infer_source_table(col_i_value):
    """Infer source_table from the prefix of Col I value.
    
    CNT_ -> CNT, CVG_ -> CVG, ROL_ -> ROL, ADD_ -> ADD
    Blank or 'System generated' -> empty string
    """
    if not col_i_value:
        return ""
    text = str(col_i_value).strip()
    if not text or text.lower() == "system generated":
        return ""
    
    for prefix in ("CNT_", "CVG_", "ROL_", "ADD_"):
        if text.startswith(prefix):
            return prefix[:-1]  # Remove trailing underscore
    return ""


def determine_transformation_type(col_a, col_c, col_i, target_field, prev_rows, level=None):
    """Determine transformation_type from columns A, B (level), C, and I ONLY.

    Per the mapping contract, Column I ("Policy Data Loader Mapping") is the sole
    source of truth for what feeds a target field; Columns E/G/K/L are NOT read.

    Priority order (first match wins):
      a0) Level 88 (COBOL condition-name) -> condition_name (not a data field, not a parent)
      a) No PIC clause in Col C -> GROUP_OR_PARENT
      b) Col I = "System generated" -> system_generated
      c) Col I has exactly one field reference -> direct_copy, unless YY/MM/DD -> date_split_*
      d) Anything else (incl. Col I blank -> no source to map) -> conditional_derived (flagged)

    `level` is the COBOL level number from Col B (int) when available. Level 88
    items are condition-names attached to the preceding field; they hold no data
    and are neither a direct source nor a group parent, so they are classified
    separately rather than being swept into GROUP_OR_PARENT by the "blank PIC" rule.
    """
    c_text = str(col_c).strip() if col_c else ""
    i_text = str(col_i).strip() if col_i else ""
    
    # a0) COBOL 88-level condition name (not a data field, not a group parent)
    if level == 88:
        return ("condition_name", False)
    
    # a) No PIC clause (group/parent row)
    if not c_text:
        return ("GROUP_OR_PARENT", False)
    
    # b) System generated
    if i_text.lower() == "system generated":
        return ("system_generated", False)
    
    # d) Col I has exactly one non-blank value (a field reference)
    if i_text and i_text.lower() != "system generated":
        # Check if it's a simple single field reference (starts with a table prefix)
        is_simple_ref = any(i_text.startswith(p) for p in ("CNT_", "CVG_", "ROL_", "ADD_"))
        
        if is_simple_ref:
            # Check for direct_copy vs date_split_* component
            # Date component: target field name ends with -YY, -MM, -DD, -MO, -DA, -YR
            tf_upper = target_field.upper() if target_field else ""
            is_date_component = bool(re.search(r'-(YY|MM|DD|MO|DA|YR)$', tf_upper))
            
            if is_date_component:
                # Determine which component based on target field suffix
                if re.search(r'-(YY|YR)$', tf_upper):
                    return ("date_split_year", False)
                elif re.search(r'-(MM|MO)$', tf_upper):
                    return ("date_split_month", False)
                elif re.search(r'-(DD|DA)$', tf_upper):
                    return ("date_split_day", False)
                else:
                    # Can't determine component — flag for review
                    return ("needs_review_date_split", False)
            else:
                return ("direct_copy", False)
        else:
            # Col I has content but NOT a recognized table prefix
            # This includes: literal constants ('9999'), PRM_ fields,
            # complex conditional text, "Commented in module", etc.
            # All fall through to CONDITIONAL_OR_DERIVED
            return ("conditional_derived", True)
    
    # e) Col I is blank -> no source to map (engine leaves the output position
    # empty/spaces by default). Flagged as conditional_derived since A/B/C/I alone
    # do not tell us how to fill it.
    return ("conditional_derived", True)


def derive_padding_rule(data_type):
    """Derive padding_rule mechanically from data_type only."""
    if data_type == "CHAR":
        return "right_space"
    elif data_type in ("NUMERIC", "BINARY", "PACKED_DECIMAL"):
        return "left_zero"
    return ""


# Target-field suffixes that indicate a date COMPONENT (year/month/day).
_DATE_COMPONENT_RE = re.compile(r'-(YY|MM|DD|MO|DA|YR)$', re.IGNORECASE)


def _date_component_split_type(target_field):
    """Return date_split_year/month/day for a -YY/-MM/-DD (etc.) target, else ''."""
    tf = (target_field or "").upper()
    if re.search(r'-(YY|YR)$', tf):
        return "date_split_year"
    if re.search(r'-(MM|MO)$', tf):
        return "date_split_month"
    if re.search(r'-(DD|DA)$', tf):
        return "date_split_day"
    return ""


def _source_references_date(source_text):
    """True if a source string references a DATE field (e.g. ROL_BIRTH_DATE,
    CNT_ISSUE_DATE) — used to decide whether a GROUP_OR_PARENT can feed its
    YY/MM/DD children as date splits."""
    if not source_text:
        return False
    return bool(re.search(r'\b(?:CNT|CVG|ROL|ADD|PRM)_\w*DATE\w*\b', str(source_text), re.IGNORECASE))


def main():
    if not XLSX_FILE.exists():
        print(f"ERROR: {XLSX_FILE} not found")
        sys.exit(1)
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    wb = openpyxl.load_workbook(str(XLSX_FILE), data_only=True)
    ws = wb[SHEET_NAME]
    
    print(f"Reading {XLSX_FILE.name}, sheet '{SHEET_NAME}'")
    print(f"Total rows: {ws.max_row}, Columns: {ws.max_column}")
    print()
    
    mappings = []
    needs_review = []
    seq = 0
    prev_rows = []  # Track previous rows for date-split adjacency check
    # Tracks the most recent GROUP_OR_PARENT row whose source is a DATE, so its
    # -YY/-MM/-DD (or -YR/-MO/-DA) child components can inherit that source and be
    # emitted as date_split_* rather than copying the whole date into each slot.
    # Shape: {"source_field": str, "source_table": str} or None.
    date_parent = None

    for row_num in range(2, ws.max_row + 1):
        col_a = ws.cell(row=row_num, column=1).value
        if not col_a:
            continue  # Skip blank rows
        
        # Read ONLY columns A, B (level), C (format), I (source). Columns E/G/K/L
        # are intentionally not read — Column I is the sole source-of-truth.
        col_b = ws.cell(row=row_num, column=2).value
        col_c = ws.cell(row=row_num, column=3).value
        col_i = ws.cell(row=row_num, column=9).value

        # COBOL level number (Col B, fallback to leading number in Col A).
        level = parse_level(col_b, col_a)
        
        seq += 1
        
        # 1. Parse target_field from Col A
        target_field, field_ok = parse_target_field(col_a)
        if not field_ok:
            needs_review.append({
                "row_number": str(row_num),
                "raw_col_a": str(col_a)[:200],
                "raw_col_c": str(col_c)[:200] if col_c else "",
                "raw_col_i": str(col_i)[:200] if col_i else "",
                "reason": "Could not extract target_field from Col A",
            })
            continue
        
        # 1b. COBOL 88-level condition names: attached to the preceding field,
        # hold no data of their own (Col C is a VALUE clause, not a PIC), and are
        # neither a direct source nor a group parent. Emit as condition_name with
        # empty type/length rather than sending their VALUE clause to needs_review.
        if level == 88:
            # Strip any trailing COBOL VALUE/VALUES clause from the condition
            # name (e.g. "DELETED-RECORD VALUE 'D'" -> "DELETED-RECORD").
            condition_name = re.split(r'\s+VALUES?\b', target_field, maxsplit=1, flags=re.IGNORECASE)[0].strip().rstrip('.')
            mapping_id = f"MAP_{seq:03d}"
            mappings.append({
                "mapping_id": mapping_id,
                "source_table": "",
                "source_field": "",
                "target_field": condition_name,
                "transformation_type": "condition_name",
                "target_length": "",
                "target_data_type": "",
                "decimal_places": "",
                "signed": "",
                "comp3": "",
                "padding_rule": "",
                "default_value": "",
                "date_handling": "",
                "truncation_rule": "",
                "sequence": str(row_num),
            })
            prev_rows.append({
                "target_field": condition_name,
                "source_field": "",
                "row_num": row_num,
            })
            continue

        # 2. Parse PIC clause from Col C
        data_type, target_length, decimal_places, signed, comp3, pic_recognized = parse_pic_clause(col_c)
        if not pic_recognized:
            needs_review.append({
                "row_number": str(row_num),
                "raw_col_a": str(col_a)[:200],
                "raw_col_c": str(col_c)[:200] if col_c else "",
                "raw_col_i": str(col_i)[:200] if col_i else "",
                "reason": f"PIC clause not recognized - needs manual review: {str(col_c)[:100]}",
            })
            continue
        
        # 3. Source field from Col I
        source_field = str(col_i).strip() if col_i else ""
        if source_field.lower() == "system generated":
            source_field = ""  # Will be handled by transformation_type
        # Handle "Not used in module" - treat as blank
        if source_field.lower().startswith("not used"):
            source_field = ""
        # Handle "MOVE ROL_CLIENT_ID" patterns - extract the field name
        if source_field.upper().startswith("MOVE "):
            source_field = source_field[5:].strip()
        
        # 4. Source table from prefix
        source_table = infer_source_table(source_field if source_field else col_i)
        
        # 5. Transformation type (from A/B/C/I only)
        transformation_type, flagged = determine_transformation_type(
            col_a, col_c, col_i, target_field, prev_rows, level=level
        )
        
        # Handle date_split_component_unknown → needs_review
        if transformation_type == "needs_review_date_split":
            needs_review.append({
                "row_number": str(row_num),
                "raw_col_a": str(col_a)[:200],
                "raw_col_c": str(col_c)[:200] if col_c else "",
                "raw_col_i": str(col_i)[:200] if col_i else "",
                "reason": "date split component could not be determined from target field name",
            })
            continue

        # 5b. Date-split propagation.
        #   A group parent whose source is a DATE (e.g. BIRTHDATE -> ROL_BIRTH_DATE)
        #   defines the source for its YY/MM/DD children, which appear on separate
        #   rows with no source of their own. Without this, each child would copy
        #   the whole 8-char date into its 2/4-char slot (overflow). We remember
        #   the parent's date source and hand it to the components.
        if transformation_type == "GROUP_OR_PARENT":
            if _source_references_date(source_field) or _source_references_date(col_i):
                date_parent = {"source_field": source_field, "source_table": source_table}
            else:
                # A non-date group parent ends any prior date grouping.
                date_parent = None
        else:
            split_type = _date_component_split_type(target_field)
            # A date component (-YY/-MM/-DD/...) becomes a date_split when a date
            # source is available — either on THIS row's own source text (owner/
            # payor sections carry "If ROL_PERSON_CODE = O MOVE ROL_BIRTH_DATE"
            # on each child) OR inherited from the group parent (insured section
            # carries the source once on the BIRTHDATE parent). Rows whose source
            # is not a date (e.g. a stray/garbage value) are left as-is so we don't
            # fabricate a split that isn't backed by a real date field.
            if split_type and transformation_type != "direct_copy" and not transformation_type.startswith("date_split_"):
                own_is_date = _source_references_date(source_field) or _source_references_date(col_i)
                if own_is_date:
                    transformation_type = split_type
                    # source_field already holds the row's own date reference.
                    if not source_table:
                        source_table = infer_source_table(source_field or "")
                elif date_parent:
                    transformation_type = split_type
                    if not source_field:
                        source_field = date_parent["source_field"]
                    if not source_table:
                        source_table = date_parent["source_table"]

            # ZIP 5 / ZIP+4 both derive from the single 10-char ADD_POSTAL_CODE
            # field (per the template note "use different parts of it"). Assign a
            # slicing transform so each lands the correct part instead of copying
            # the whole postal code into a narrower slot.
            tf_up = (target_field or "").upper()
            if "ADD_POSTAL_CODE" in (source_field or "").upper() or "ADD_POSTAL_CODE" in str(col_i or "").upper():
                if tf_up.endswith("ZIP-POSTAL-CODE-5"):
                    transformation_type = "zip_first5"
                    if not source_field:
                        source_field = str(col_i).strip() if col_i else "ADD_POSTAL_CODE"
                    if not source_table:
                        source_table = "ADD"
                elif tf_up.endswith("ZIP-POSTAL-CODE-4"):
                    transformation_type = "zip_plus4"
                    if not source_field:
                        source_field = str(col_i).strip() if col_i else "ADD_POSTAL_CODE"
                    if not source_table:
                        source_table = "ADD"

        # 6. Padding rule
        padding_rule = derive_padding_rule(data_type)
        
        # Build mapping row. default_value stays empty: it was previously derived
        # from Col G/K/L, which are no longer read (Column I is the only source).
        mapping_id = f"MAP_{seq:03d}"
        
        mappings.append({
            "mapping_id": mapping_id,
            "source_table": source_table,
            "source_field": source_field,
            "target_field": target_field,
            "transformation_type": transformation_type,
            "target_length": target_length,
            "target_data_type": data_type,
            "decimal_places": decimal_places,
            "signed": signed,
            "comp3": comp3,
            "padding_rule": padding_rule,
            "default_value": "",
            "date_handling": "",
            "truncation_rule": "",
            "sequence": str(row_num),
        })
        
        # Track for adjacency checks
        prev_rows.append({
            "target_field": target_field,
            "source_field": source_field,
            "row_num": row_num,
        })
    
    # Write transformation_mappings.csv
    output_path = OUTPUT_DIR / "transformation_mappings.csv"
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(mappings)
    
    # Write needs_review
    review_path = OUTPUT_DIR / "transformation_mappings_needs_review.csv"
    with open(review_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=NEEDS_REVIEW_COLUMNS)
        writer.writeheader()
        writer.writerows(needs_review)
    
    # Summary
    print("=" * 60)
    print("TRANSFORMATION MAPPING GENERATION SUMMARY")
    print("=" * 60)
    print(f"\nTotal rows processed: {seq}")
    print(f"Mappings generated: {len(mappings)}")
    print(f"Needs review: {len(needs_review)}")
    
    # Type breakdown
    type_counts = {}
    for m in mappings:
        t = m["transformation_type"]
        type_counts[t] = type_counts.get(t, 0) + 1
    
    print(f"\nTransformation type breakdown:")
    for t, count in sorted(type_counts.items()):
        print(f"  {t}: {count}")
    
    # Source table breakdown
    table_counts = {}
    for m in mappings:
        st = m["source_table"] or "(none)"
        table_counts[st] = table_counts.get(st, 0) + 1
    
    print(f"\nSource table breakdown:")
    for t, count in sorted(table_counts.items()):
        print(f"  {t}: {count}")
    
    if needs_review:
        print(f"\nNeeds review items:")
        for item in needs_review:
            print(f"  Row {item['row_number']}: {item['reason']}")
            print(f"    Col A: {item['raw_col_a'][:60]}")
            print(f"    Col C: {item['raw_col_c'][:60]}")
    
    print(f"\nOutput files:")
    print(f"  {output_path}")
    print(f"  {review_path}")
    
    wb.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
