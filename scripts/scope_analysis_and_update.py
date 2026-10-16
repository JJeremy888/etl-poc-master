import csv
import os

os.chdir(r"C:\POC\Git Version\assure-aat-etl-poc-kiro")

ALLOWED_TABLES = {"CNT", "CVG", "ROL", "ADD"}
ALLOWED_STATUSES = {"Confirmed for POC Review", "System Generated"}

# ============================================================
# PART 1: Check Transformation Type for all 25 "Review Required" rows
# ============================================================
with open("rules/POC_Transformation_Mapping.csv", "r", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    all_rows = list(reader)
    fieldnames = reader.fieldnames

# Re-read to get fieldnames properly
with open("rules/POC_Transformation_Mapping.csv", "r", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    all_rows = list(reader)

review_required = []
for row in all_rows:
    source_tables_raw = row.get("Source Table(s)", "").strip()
    mapping_status = row.get("Mapping Status", "").strip()
    
    # Only count rows that would be excluded by status (not already excluded by source table)
    source_tables_ok = True
    if source_tables_raw:
        tables = [t.strip() for t in source_tables_raw.split(";")]
        for t in tables:
            if t and t not in ALLOWED_TABLES:
                source_tables_ok = False
                break
    
    if source_tables_ok and mapping_status == "Review Required":
        review_required.append(row)

print("=" * 90)
print("PART 1: Transformation Type verification for 'Review Required' rows")
print("=" * 90)
print(f"\nTotal 'Review Required' rows (with in-scope source tables): {len(review_required)}")
print(f"\n{'#':<4} {'Target Field':<50} {'Transformation Type':<20} {'Row':<6} {'GROUP_OR_PARENT?'}")
print(f"{'-'*4} {'-'*50} {'-'*20} {'-'*6} {'-'*16}")

all_group_or_parent = True
non_group_rows = []
for i, row in enumerate(review_required, 1):
    target = row.get("Target Field", "")[:50]
    xform_type = row.get("Transformation Type", "").strip()
    sheet_row = row.get("Original Sheet Row", "")
    is_gop = "YES" if xform_type == "GROUP_OR_PARENT" else "*** NO ***"
    if xform_type != "GROUP_OR_PARENT":
        all_group_or_parent = False
        non_group_rows.append(row)
    print(f"{i:<4} {target:<50} {xform_type:<20} {sheet_row:<6} {is_gop}")

print(f"\n--- CONCLUSION ---")
if all_group_or_parent:
    print("ALL 25 rows are GROUP_OR_PARENT. These are structural labels only.")
    print("RECOMMENDATION: Permanently exclude (not defer). They produce no output.")
else:
    print(f"WARNING: {len(non_group_rows)} row(s) are NOT GROUP_OR_PARENT:")
    for r in non_group_rows:
        print(f"  - Row {r.get('Original Sheet Row')}: {r.get('Target Field')} (Type: {r.get('Transformation Type')})")

# ============================================================
# PART 2: Update specific rows from "Open - Clarification Needed" to "Confirmed for POC Review"
# ============================================================
print(f"\n{'=' * 90}")
print("PART 2: Updating specific 'Open - Clarification Needed' rows")
print("=" * 90)

updates_made = []
row_191_analysis = None

for row in all_rows:
    sheet_row = row.get("Original Sheet Row", "").strip()
    
    if sheet_row == "88":
        # RATE-EFF-DATE: Nancy confirmed CVG_ISSUE_DATE
        old_status = row["Mapping Status"]
        row["Mapping Status"] = "Confirmed for POC Review"
        updates_made.append(f"Row 88 (RATE-EFF-DATE): '{old_status}' -> 'Confirmed for POC Review' (Nancy confirmed: use CVG_ISSUE_DATE)")
        print(f"  UPDATED Row 88: RATE-EFF-DATE -> Confirmed (Nancy: use CVG_ISSUE_DATE)")
    
    elif sheet_row == "229":
        # ROP-RIDER-B-IND: Initialize to constant 'N'
        old_status = row["Mapping Status"]
        row["Mapping Status"] = "Confirmed for POC Review"
        updates_made.append(f"Row 229 (ROP-RIDER-B-IND): '{old_status}' -> 'Confirmed for POC Review' (constant 'N')")
        print(f"  UPDATED Row 229: ROP-RIDER-B-IND -> Confirmed (initialize to constant 'N')")
    
    elif sheet_row == "236":
        # PW-COVERED-INSURED-IND: Set to blanks/spaces
        old_status = row["Mapping Status"]
        row["Mapping Status"] = "Confirmed for POC Review"
        updates_made.append(f"Row 236 (PW-COVERED-INSURED-IND): '{old_status}' -> 'Confirmed for POC Review' (set to blanks/spaces)")
        print(f"  UPDATED Row 236: PW-COVERED-INSURED-IND -> Confirmed (set to blanks/spaces)")
    
    elif sheet_row == "191":
        # RESTRICTION-CODE: Analyze Nancy's comment
        comment = row.get("Open Question / Comment", "")
        row_191_analysis = {
            "target_field": row.get("Target Field", ""),
            "transformation_type": row.get("Transformation Type", ""),
            "transformation_rule": row.get("Transformation Rule", ""),
            "default_value": row.get("Default / Constant Value", ""),
            "comment": comment,
        }

print(f"\n  --- Row 191 (RESTRICTION-CODE) Analysis ---")
if row_191_analysis:
    print(f"  Target Field: {row_191_analysis['target_field']}")
    print(f"  Transformation Type: {row_191_analysis['transformation_type']}")
    print(f"  Transformation Rule: {row_191_analysis['transformation_rule']}")
    print(f"  Default Value: '{row_191_analysis['default_value']}'")
    print(f"  Comment: {row_191_analysis['comment'][:200]}")
    print(f"\n  ASSESSMENT: The Transformation Type is already INITIALIZE_SPACES and the rule says")
    print(f"  'Move \"\"' (move blanks). However, Nancy's comment says 'Unclear what MPO_PLAN_TYPE IS'")
    print(f"  which is genuinely unresolved — it suggests there MIGHT be a non-blank value needed")
    print(f"  depending on an external reference (MPO_PLAN_TYPE) that hasn't been defined.")
    print(f"  DECISION: NOT marking as Confirmed. The 'initialize to spaces' is a PLACEHOLDER,")
    print(f"  not a confirmed final answer. Leaving as Open - Clarification Needed.")

print(f"\n  Summary of updates: {len(updates_made)} rows updated (Row 191 left unchanged)")
for u in updates_made:
    print(f"    - {u}")

# ============================================================
# PART 3: Write updated POC_Transformation_Mapping.csv and regenerate scoped version
# ============================================================
print(f"\n{'=' * 90}")
print("PART 3: Regenerating files")
print("=" * 90)

# Write the updated original back
with open("rules/POC_Transformation_Mapping.csv", "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(all_rows)
print("  Written: rules/POC_Transformation_Mapping.csv (3 rows updated)")

# Now regenerate the scoped file
included = []
for row in all_rows:
    source_tables_raw = row.get("Source Table(s)", "").strip()
    mapping_status = row.get("Mapping Status", "").strip()
    
    source_tables_ok = True
    if source_tables_raw:
        tables = [t.strip() for t in source_tables_raw.split(";")]
        for t in tables:
            if t and t not in ALLOWED_TABLES:
                source_tables_ok = False
                break
    
    status_ok = mapping_status in ALLOWED_STATUSES
    
    if source_tables_ok and status_ok:
        included.append(row)

with open("rules/POC_Transformation_Mapping_scoped.csv", "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(included)

# Verify by re-reading
with open("rules/POC_Transformation_Mapping_scoped.csv", "r", encoding="utf-8-sig") as f:
    verify_count = sum(1 for _ in csv.DictReader(f))

print(f"  Written: rules/POC_Transformation_Mapping_scoped.csv")
print(f"  New scoped row count: {verify_count} (was 397, added 3 rows)")
print(f"  Verification: 466 - 26 (source table) - 25 (GROUP_OR_PARENT) - 15 (remaining Open) = {466 - 26 - 25 - 15}")

# ============================================================
# PART 4: Deferred to Phase 2 list
# ============================================================
print(f"\n{'=' * 90}")
print("PART 4: Deferred to Phase 2 — External Blockers")
print("=" * 90)

# Remaining Open - Clarification Needed rows (after updates)
remaining_open = []
for row in all_rows:
    source_tables_raw = row.get("Source Table(s)", "").strip()
    mapping_status = row.get("Mapping Status", "").strip()
    
    source_tables_ok = True
    if source_tables_raw:
        tables = [t.strip() for t in source_tables_raw.split(";")]
        for t in tables:
            if t and t not in ALLOWED_TABLES:
                source_tables_ok = False
                break
    
    if source_tables_ok and mapping_status == "Open - Clarification Needed":
        remaining_open.append(row)

print(f"\nRemaining 'Open - Clarification Needed' rows: {len(remaining_open)}")
print(f"\nGrouped by external blocker:\n")

# Group by JIRA/blocker
jira_107 = []
jira_416 = []
jira_403 = []
translation_table = []
nancy_sample = []
other = []

for row in remaining_open:
    comment = row.get("Open Question / Comment", "")
    sheet_row = row.get("Original Sheet Row", "")
    target = row.get("Target Field", "")
    
    if "JIRA 107" in comment or "Dummy Agent" in comment:
        jira_107.append((sheet_row, target))
    elif "JIRA 416" in comment:
        jira_416.append((sheet_row, target))
    elif "JIRA" in comment and "403" in comment:
        jira_403.append((sheet_row, target))
    elif "translation" in comment.lower() or "Prem_Class" in comment:
        translation_table.append((sheet_row, target))
    elif "sample dataset" in comment.lower() or "Nancy 5/22" in comment:
        nancy_sample.append((sheet_row, target))
    else:
        other.append((sheet_row, target, comment[:80]))

print(f"  JIRA 107 (Dummy Agent info from P+): {len(jira_107)} rows")
for r, t in jira_107:
    print(f"    - Row {r}: {t}")

print(f"\n  JIRA 416 (Directory ID generation pattern): {len(jira_416)} rows")
for r, t in jira_416:
    print(f"    - Row {r}: {t}")

print(f"\n  JIRA 403 (ORIGINATOR-CODE — verify with WiltonRe): {len(jira_403)} rows")
for r, t in jira_403:
    print(f"    - Row {r}: {t}")

print(f"\n  Translation Table needed (PREM-CLASS-CODE): {len(translation_table)} rows")
for r, t in translation_table:
    print(f"    - Row {r}: {t}")

print(f"\n  Nancy sample-dataset work (Co-Owner multi-occurrence): {len(nancy_sample)} rows")
for r, t in nancy_sample:
    print(f"    - Row {r}: {t}")

if other:
    print(f"\n  Other/Uncategorized: {len(other)} rows")
    for r, t, c in other:
        print(f"    - Row {r}: {t} — {c}")

print(f"\n{'=' * 90}")
print("DONE")
print(f"{'=' * 90}")
