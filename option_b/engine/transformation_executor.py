"""Transformation Executor — Apply transformation mappings to eligible records.

POC approach: Collects eligible records to Pandas for transformation.
This avoids Spark's Catalyst plan explosion with 399 sequential withColumn() calls.
For production (millions of records), this should be refactored to use Spark select()
with pre-built column expressions or batched withColumn approaches.
"""
import re

import pandas as pd
from pyspark.sql import DataFrame, SparkSession, functions as F
from pyspark.sql.types import StringType


# Accumulates field-level overflow findings across a transform run so we surface
# them loudly (Byers requirement #1: never silently truncate a value that is
# wider than its Cobol target). Each entry: (target_field, kind, count, sample).
_OVERFLOW_REPORT: list[dict] = []


def _record_overflow(target_field: str, kind: str, count: int, sample: str) -> None:
    """Record an overflow/precision-loss finding for end-of-run reporting."""
    if count > 0:
        _OVERFLOW_REPORT.append({
            "target_field": target_field, "kind": kind,
            "count": int(count), "sample": str(sample)[:40],
        })


def transform(template: dict, validated_dfs: dict[str, DataFrame]) -> DataFrame | None:
    """Apply all transformation mappings to CLEAN+WARNING records.

    Joins child tables (CVG, ROL, ADD) to the base CNT DataFrame on
    company_code + policy_number, then applies mappings using Pandas.

    Returns a Spark DataFrame with target fields, or None if no eligible records.
    """
    mappings = template.get("transformation_mappings", [])
    if not mappings:
        return None

    primary_df = validated_dfs.get("CNT")
    if primary_df is None:
        return None

    # Filter to eligible records (CLEAN + WARNING only)
    eligible = primary_df.filter(F.col("ROW_SEVERITY").isin(["CLEAN", "WARNING"]))

    if eligible.limit(1).count() == 0:
        print("[TRANSFORM] No eligible records (all SEVERE)")
        return None

    eligible_count = eligible.count()
    print(f"[TRANSFORM] Transforming {eligible_count} eligible records ({len(mappings)} mappings)")

    # Collect CNT to Pandas
    cnt_pdf = eligible.toPandas()

    # Join child tables in Pandas (much faster for POC-scale data)
    joined_pdf = _join_child_tables_pandas(cnt_pdf, validated_dfs)

    # Reset the overflow/precision report for this run.
    _OVERFLOW_REPORT.clear()

    # Apply all transformations in Pandas
    sorted_mappings = sorted(mappings, key=lambda m: int(m.get("sequence", "0") or "0"))
    result_pdf = _apply_all_mappings(joined_pdf, sorted_mappings)

    # Surface any exact-length / precision findings loudly (never silent).
    if _OVERFLOW_REPORT:
        print(f"[TRANSFORM] WARNING: {len(_OVERFLOW_REPORT)} field(s) had overflow/precision-loss "
              f"mapping template -> Cobol layout:")
        for e in _OVERFLOW_REPORT:
            print(f"    {e['target_field']}: {e['kind']} on {e['count']} record(s) "
                  f"(e.g. {e['sample']!r})")
    else:
        print("[TRANSFORM] Exact-length/precision check: no overflow or precision loss detected.")

    # Convert back to Spark DataFrame for output adapters
    spark = SparkSession.getActiveSession()
    if spark is None:
        print("[TRANSFORM] ERROR: No active SparkSession")
        return None

    result_df = spark.createDataFrame(result_pdf)
    return result_df


def _join_child_tables_pandas(cnt_pdf: pd.DataFrame, validated_dfs: dict[str, DataFrame]) -> pd.DataFrame:
    """Left-join child tables to CNT in Pandas.

    Takes first record per policy for each child table (1:1 with CNT).
    """
    result = cnt_pdf.copy()

    # --- CVG join ---
    cvg_df = validated_dfs.get("CVG")
    if cvg_df is not None:
        cvg_eligible = cvg_df.filter(F.col("ROW_SEVERITY").isin(["CLEAN", "WARNING"]))
        if cvg_eligible.limit(1).count() > 0:
            cvg_pdf = cvg_eligible.toPandas()
            # Drop metadata columns
            drop_cols = [c for c in cvg_pdf.columns
                        if c.startswith("VAL_") or c in ("ROW_SEVERITY", "VALIDATION_ISSUES", "TEST_EXPECTED_ISSUE")]
            cvg_pdf = cvg_pdf.drop(columns=[c for c in drop_cols if c in cvg_pdf.columns])
            # First CVG per policy
            cvg_pdf = cvg_pdf.sort_values("CVG_SEQUENCE_NUMBER").drop_duplicates(
                subset=["CVG_COMPANY_CODE", "CVG_POLICY_NUMBER"], keep="first"
            )
            result = result.merge(
                cvg_pdf,
                left_on=["CNT_COMPANY_CODE", "CNT_POLICY_NUMBER"],
                right_on=["CVG_COMPANY_CODE", "CVG_POLICY_NUMBER"],
                how="left"
            )
            matched = result["CVG_PLAN_CODE"].notna().sum()
            print(f"[TRANSFORM] Joined CVG: {matched} records matched")

    # --- ROL join (multi-role: Insured, Owner, Payor) ---
    rol_df = validated_dfs.get("ROL")
    if rol_df is not None:
        rol_eligible = rol_df.filter(F.col("ROW_SEVERITY").isin(["CLEAN", "WARNING"]))
        if rol_eligible.limit(1).count() > 0:
            rol_pdf = rol_eligible.toPandas()
            drop_cols = [c for c in rol_pdf.columns
                        if c.startswith("VAL_") or c in ("ROW_SEVERITY", "VALIDATION_ISSUES", "TEST_EXPECTED_ISSUE")]
            rol_pdf = rol_pdf.drop(columns=[c for c in drop_cols if c in rol_pdf.columns])

            # Multi-role joins: each role type gets its own suffixed columns
            role_filters = {
                "INS": ["I", "1", "C"],   # Insured section
                "OWN": ["O"],             # Owner section
                "PAY": ["P"],             # Payor section
            }

            for role_suffix, codes in role_filters.items():
                role_subset = rol_pdf[rol_pdf["ROL_PERSON_CODE"].isin(codes)].copy()
                if role_subset.empty:
                    print(f"[TRANSFORM] Joined ROL ({role_suffix}): 0 records (no matching roles)")
                    continue
                # First matching role per policy (lowest sequence wins)
                role_subset = role_subset.sort_values("ROL_PERSON_SEQUENCE").drop_duplicates(
                    subset=["ROL_COMPANY_CODE", "ROL_POLICY_NUMBER"], keep="first"
                )
                # Rename columns with role suffix (except join keys)
                join_keys = {"ROL_COMPANY_CODE", "ROL_POLICY_NUMBER"}
                rename_map = {col: f"{col}_{role_suffix}" for col in role_subset.columns if col not in join_keys}
                role_subset = role_subset.rename(columns=rename_map)

                result = result.merge(
                    role_subset,
                    left_on=["CNT_COMPANY_CODE", "CNT_POLICY_NUMBER"],
                    right_on=["ROL_COMPANY_CODE", "ROL_POLICY_NUMBER"],
                    how="left",
                    suffixes=("", f"__{role_suffix}_dup")
                )
                # Drop duplicate join key columns
                dup_cols = [c for c in result.columns if c.endswith(f"__{role_suffix}_dup")]
                result = result.drop(columns=dup_cols, errors="ignore")
                # Also drop the ROL_COMPANY_CODE/ROL_POLICY_NUMBER from this merge if they appeared
                for jk in ["ROL_COMPANY_CODE", "ROL_POLICY_NUMBER"]:
                    if f"{jk}_x" in result.columns:
                        result = result.rename(columns={f"{jk}_x": jk})
                        result = result.drop(columns=[f"{jk}_y"], errors="ignore")

                matched = result[f"ROL_PERSON_CODE_{role_suffix}"].notna().sum()
                print(f"[TRANSFORM] Joined ROL ({role_suffix}): {matched} records matched")

            # Also keep base insured join (unsuffixed ROL_ columns for backward compat)
            # This provides ROL_ columns without suffix for direct_copy mappings
            # that reference ROL fields without role-gating conditions
            insured_rol = rol_pdf[rol_pdf["ROL_PERSON_CODE"].isin(["I", "1", "C"])].copy()
            if not insured_rol.empty:
                insured_rol = insured_rol.sort_values("ROL_PERSON_SEQUENCE").drop_duplicates(
                    subset=["ROL_COMPANY_CODE", "ROL_POLICY_NUMBER"], keep="first"
                )
                result = result.merge(
                    insured_rol,
                    left_on=["CNT_COMPANY_CODE", "CNT_POLICY_NUMBER"],
                    right_on=["ROL_COMPANY_CODE", "ROL_POLICY_NUMBER"],
                    how="left",
                    suffixes=("", "__ROL_BASE_dup")
                )
                dup_cols = [c for c in result.columns if c.endswith("__ROL_BASE_dup")]
                result = result.drop(columns=dup_cols, errors="ignore")

    # --- ADD join (person_sequence-aware: links to each role's person) ---
    add_df = validated_dfs.get("ADD")
    if add_df is not None:
        add_eligible = add_df.filter(F.col("ROW_SEVERITY").isin(["CLEAN", "WARNING"]))
        if add_eligible.limit(1).count() > 0:
            add_pdf = add_eligible.toPandas()
            drop_cols = [c for c in add_pdf.columns
                        if c.startswith("VAL_") or c in ("ROW_SEVERITY", "VALIDATION_ISSUES", "TEST_EXPECTED_ISSUE")]
            add_pdf = add_pdf.drop(columns=[c for c in drop_cols if c in add_pdf.columns])
            # Prefer residential (R) over alternate (A) for each person
            type_order = {"R": 0, "A": 1}
            add_pdf["_sort_key"] = add_pdf["ADD_ADDRESS_TYPE"].map(type_order).fillna(9)
            add_pdf = add_pdf.sort_values(["_sort_key"]).drop_duplicates(
                subset=["ADD_COMPANY_CODE", "ADD_POLICY_NUMBER", "ADD_PERSON_SEQUENCE"], keep="first"
            ).drop(columns=["_sort_key"])

            # Join ADD for each role type using the role's person_sequence
            add_role_map = {
                "INS": "ROL_PERSON_SEQUENCE_INS",
                "OWN": "ROL_PERSON_SEQUENCE_OWN",
                "PAY": "ROL_PERSON_SEQUENCE_PAY",
            }

            for role_suffix, seq_col in add_role_map.items():
                if seq_col not in result.columns:
                    continue
                # Build a temporary key: company + policy + person_sequence from the role
                add_subset = add_pdf.copy()
                add_rename = {col: f"{col}_{role_suffix}" for col in add_subset.columns
                              if col not in ("ADD_COMPANY_CODE", "ADD_POLICY_NUMBER", "ADD_PERSON_SEQUENCE")}
                add_subset = add_subset.rename(columns=add_rename)

                # Merge: match policy + person_sequence from the role
                result = result.merge(
                    add_subset,
                    left_on=["CNT_COMPANY_CODE", "CNT_POLICY_NUMBER", seq_col],
                    right_on=["ADD_COMPANY_CODE", "ADD_POLICY_NUMBER", "ADD_PERSON_SEQUENCE"],
                    how="left",
                    suffixes=("", f"__ADD_{role_suffix}_dup")
                )
                dup_cols = [c for c in result.columns if c.endswith(f"__ADD_{role_suffix}_dup")]
                result = result.drop(columns=dup_cols, errors="ignore")
                # Drop join key columns from ADD
                result = result.drop(columns=["ADD_COMPANY_CODE", "ADD_POLICY_NUMBER", "ADD_PERSON_SEQUENCE"], errors="ignore")

                matched = result[f"ADD_ADDRESS_TYPE_{role_suffix}"].notna().sum() if f"ADD_ADDRESS_TYPE_{role_suffix}" in result.columns else 0
                print(f"[TRANSFORM] Joined ADD ({role_suffix}): {matched} records matched")

            # Also keep base ADD join (unsuffixed) for non-role-gated mappings
            base_add = add_pdf.sort_values(["ADD_PERSON_SEQUENCE"]).drop_duplicates(
                subset=["ADD_COMPANY_CODE", "ADD_POLICY_NUMBER"], keep="first"
            )
            result = result.merge(
                base_add,
                left_on=["CNT_COMPANY_CODE", "CNT_POLICY_NUMBER"],
                right_on=["ADD_COMPANY_CODE", "ADD_POLICY_NUMBER"],
                how="left",
                suffixes=("", "__ADD_BASE_dup")
            )
            dup_cols = [c for c in result.columns if c.endswith("__ADD_BASE_dup")]
            result = result.drop(columns=dup_cols, errors="ignore")
            matched = result["ADD_PERSON_SEQUENCE"].notna().sum() if "ADD_PERSON_SEQUENCE" in result.columns else 0
            print(f"[TRANSFORM] Joined ADD (base): {matched} records matched")

    return result


def _out_column_name(mapping: dict) -> str:
    """Build a UNIQUE output-column name for a mapping row.

    POC NOTE (Nancy issue #4 — same field name in multiple record sections):
    ------------------------------------------------------------------------
    Several COBOL record sections legitimately reuse the same leaf field name
    (e.g. LAST-NAME / FIRST-NAME appear in the INSURED, OWNER, PAYOR and
    CO-OWNER sections). The old scheme named the output column purely from the
    leaf `target_field` ("OUT_LAST_NAME"), so every one of those rows wrote to
    the SAME column and the last row processed OVERWROTE the earlier ones —
    which is why the insured name slot showed the Owner's name.

    Option A (this POC fix): key the output column by the mapping row's own
    `sequence` so each row gets its own distinct positional slot:
        OUT_<sequence>__<SAFE_TARGET_FIELD>   e.g. OUT_117__LAST_NAME
    Because rows are applied in `sequence` order, the DataFrame column order
    (and therefore the positional flat-file byte order) is preserved.

    DURABLE SOLUTION (Option B — deferred): drive the output slot from an
    explicit `record_section` column in a structured, prose-free mapping
    template (INSURED-DATA / OWNER-DATA / CO-OWNER-ADDRESS-INFO ...), and
    handle OCCURS arrays as declared repetitions. When that template lands,
    replace this sequence-keyed name with a section-qualified name. The CSV
    adapter reverses this exact scheme, so keep the two in sync.
    """
    seq = str(mapping.get("sequence", "0") or "0").strip()
    tf = mapping.get("target_field", "").strip()
    safe_tf = tf.replace('-', '_').replace(' ', '_').replace('.', '_')
    return f"OUT_{seq}__{safe_tf}"


def _apply_all_mappings(pdf: pd.DataFrame, sorted_mappings: list[dict]) -> pd.DataFrame:
    """Apply all transformation mappings to the Pandas DataFrame."""
    result = pdf.copy()

    for mapping in sorted_mappings:
        target_field = mapping.get("target_field", "").strip()
        source_field = mapping.get("source_field", "").strip()
        source_table = mapping.get("source_table", "").strip()
        xtype = mapping.get("transformation_type", "").strip()
        target_length = int(mapping.get("target_length", "0") or "0")
        target_data_type = mapping.get("target_data_type", "CHAR").strip()
        default_value = mapping.get("default_value", "").strip()
        padding_rule = mapping.get("padding_rule", "").strip()
        # Cobol PIC metadata (from the mapping template's PIC clause). Drives
        # precision rescaling (#2) and exact-width/overflow handling (#1).
        target_decimals = int(mapping.get("decimal_places", "0") or "0")

        if not target_field:
            continue

        # Skip structural group markers — they produce no output
        if xtype == "GROUP_OR_PARENT":
            continue

        # POC fix #4: unique output slot per mapping row (see _out_column_name).
        safe_name = _out_column_name(mapping)

        # Compute column value
        col_values = _compute_column(
            result, xtype, source_field, target_length,
            target_data_type, default_value, padding_rule
        )

        # Precision: rescale the source's decimal representation to the target's
        # decimal count (WMA/Cobol scale may differ from the template's). This
        # runs BEFORE padding so the value is already at target precision. The
        # stored digit string is the value with the implied decimal point removed
        # (Cobol Vnn convention), e.g. 22.36 at 2dp -> "2236".
        if target_data_type in ("NUMERIC", "PACKED_DECIMAL") and target_decimals > 0:
            col_values = _rescale_decimals_series(col_values, target_decimals, target_field)

        # POC fix #2 (POLICY-CVG-UNITS / COMP-3): for packed-decimal signed
        # fields, surface the true COMP-3 packed value as a HEX DISPLAY string
        # (e.g. "00 00 09 59 54 7C") so it can be visually verified against the
        # COBOL/WMA expectation. See _comp3_hex_display for the important
        # production caveat (true binary output + 6-byte slot is a later step).
        if target_data_type == "PACKED_DECIMAL" and str(mapping.get("comp3", "")).strip().upper() == "Y":
            signed = str(mapping.get("signed", "")).strip().upper() == "Y"
            total_digits = target_length if target_length > 0 else (target_decimals + 6)
            col_values = _comp3_hex_display_series(col_values, total_digits, signed, target_field)
            # The hex display is already fixed-width/positional for the POC; skip
            # the numeric zero-pad below so we don't corrupt the hex string.
            result[safe_name] = col_values
            continue

        # Apply padding, detecting overflow (source wider than the Cobol field)
        # rather than silently truncating.
        if target_length > 0:
            col_values = _apply_padding_series(
                col_values, target_length, target_data_type, padding_rule, target_field
            )

        result[safe_name] = col_values

    return result


def _detect_role_from_source(source_field: str) -> str:
    """Detect which role section a mapping belongs to based on source_field text.

    Returns 'INS', 'OWN', 'PAY', or '' if no role detected.

    POC NOTE (Nancy issue #4): today the role is inferred by string-matching the
    BA's prose instruction (e.g. "ROL_PERSON_CODE = O ... MOVE ADD_LAST_NAME").
    This is deliberately conservative but fragile. The DURABLE solution is to
    read an explicit `role` column (INS/OWN/PAY/COOWNER) from a structured,
    prose-free mapping template so the engine never has to parse a sentence.
    """
    if not source_field:
        return ""
    text = source_field.upper()

    # Owner section (co-owner conditions also key off PERSON_CODE = O; they are
    # routed to the OWN role's source columns for the POC).
    if "PERSON_CODE = O" in text or "PERSON_CODE =O" in text:
        return "OWN"
    # Payor section
    if "PERSON_CODE = P" in text or "PERSON_CODE =P" in text:
        return "PAY"
    # Insured section (explicit)
    if "PERSON_CODE = I" in text or "= I OR 1 OR C" in text:
        return "INS"

    return ""


# Recognizes a quoted literal in the source_field / default_value, e.g. 'EA',
# "EA  ", "2". Used by POC fix #1 (TRX-CODE) so a literal authored in the
# instruction cell is emitted verbatim instead of being treated as a column
# name (which produced a blank). DURABLE solution: literals belong in a
# `default_value` column with transformation_type = 'constant'.
_QUOTED_LITERAL_RE = re.compile(r"""^\s*(?:'([^']*)'|"([^"]*)")\s*$""")


def _extract_quoted_literal(text: str):
    """Return the inner text of a quoted literal, or None if not a pure literal."""
    if not text:
        return None
    m = _QUOTED_LITERAL_RE.match(text)
    if not m:
        return None
    return m.group(1) if m.group(1) is not None else m.group(2)


def _clean_source_column(source_field: str) -> str:
    """Extract a clean, single source COLUMN NAME from a source_field cell.

    POC NOTE (Nancy issue #3 — PLAN-CODE): BAs sometimes append prose to the
    source cell, e.g. "CVG_PLAN_CODE\\n\\nNote: This is a correction ...". The
    engine looks the cell up as a column name and, because of the trailing note,
    finds nothing and emits a blank. For the POC we take the first clean
    identifier-looking token (UPPERCASE table_field style). DURABLE solution:
    the structured template keeps `source_field` = a single clean column name
    and moves any commentary to a separate `comment` column the engine ignores.
    """
    if not source_field:
        return ""
    # First non-empty line, first token that looks like a STAGING column name.
    first_line = source_field.strip().splitlines()[0].strip() if source_field.strip() else ""
    # A staging column looks like TABLE_FIELD (e.g. CVG_PLAN_CODE, ADD_LAST_NAME).
    m = re.match(r'^([A-Z][A-Z0-9]*_[A-Z0-9_]+)', first_line)
    if m:
        return m.group(1)
    return first_line


def _compute_column(
    pdf: pd.DataFrame, xtype: str, source_field: str,
    target_length: int, target_data_type: str,
    default_value: str, padding_rule: str
) -> pd.Series:
    """Compute transformation for a single mapping."""
    primary_source = source_field.split(";")[0].strip() if source_field else ""

    # POC fix #1 (TRX-CODE): a quoted literal authored in the instruction cell
    # (e.g. 'EA' or "EA  ") should be emitted verbatim, not treated as a column
    # name. Applies to the "derived/copy" style rows where BAs put constants.
    # DURABLE solution: use transformation_type='constant' + a default_value col.
    if xtype in ("direct_copy", "conditional_derived", "constant"):
        literal = _extract_quoted_literal(source_field) or _extract_quoted_literal(default_value)
        if literal is not None:
            return pd.Series([literal] * len(pdf), index=pdf.index)

    # Role disambiguation: detect if mapping is role-gated (#4).
    role_suffix = _detect_role_from_source(source_field)
    if role_suffix:
        # Try to find the actual field to MOVE from the source_field text
        move_match = re.search(r'MOVE\s+((?:ADD|ROL)_\w+)', source_field, re.IGNORECASE)
        if move_match:
            actual_field = move_match.group(1).strip()
            # Prefer the role-suffixed version so the correct person's value is
            # pulled (insured vs owner vs payor). This is what makes the insured
            # name slot resolve to the Insured (ADD_LAST_NAME_INS) rather than
            # whatever person happened to land in the unsuffixed base column.
            suffixed = f"{actual_field}_{role_suffix}"
            if suffixed in pdf.columns:
                primary_source = suffixed
            elif actual_field in pdf.columns:
                primary_source = actual_field
        else:
            # No explicit MOVE — try suffixing the primary_source itself
            if primary_source:
                suffixed = f"{primary_source}_{role_suffix}"
                if suffixed in pdf.columns:
                    primary_source = suffixed
    else:
        # POC fix #3 (PLAN-CODE): when there's no role logic, the source cell
        # may still carry a trailing note. Reduce it to a clean column name.
        if primary_source and primary_source not in pdf.columns:
            cleaned = _clean_source_column(source_field)
            if cleaned and cleaned in pdf.columns:
                primary_source = cleaned

    if xtype == "direct_copy" and primary_source and primary_source in pdf.columns:
        return pdf[primary_source].fillna("")

    elif xtype in ("date_split_year", "date_split_month", "date_split_day"):
        if primary_source and primary_source in pdf.columns:
            date_str = pdf[primary_source].fillna("").astype(str).str.strip()
            if xtype == "date_split_year":
                return date_str.str[:4]
            elif xtype == "date_split_month":
                return date_str.str[4:6]
            else:
                return date_str.str[6:8]
        return pd.Series(["0" * target_length] * len(pdf), index=pdf.index)

    elif xtype in ("zip_first5", "zip_plus4"):
        # ZIP 5 and ZIP+4 both come from ONE 10-char source (ADD_POSTAL_CODE):
        # positions 1-5 are the 5-digit ZIP, positions 6-9 are the +4 extension.
        # Slice the appropriate part rather than copying the whole field into a
        # narrower slot.
        if primary_source and primary_source in pdf.columns:
            zip_str = pdf[primary_source].fillna("").astype(str).str.strip()
            if xtype == "zip_first5":
                return zip_str.str[:5]
            else:  # zip_plus4 -> characters 6..9 (0-indexed 5..9)
                return zip_str.str[5:9]
        return pd.Series([" " * target_length] * len(pdf), index=pdf.index)

    elif xtype == "constant":
        return pd.Series([default_value or ""] * len(pdf), index=pdf.index)

    elif xtype == "space_fill":
        return pd.Series([" " * target_length] * len(pdf), index=pdf.index)

    elif xtype == "zero_fill":
        return pd.Series(["0" * target_length] * len(pdf), index=pdf.index)

    elif xtype == "system_generated":
        if target_data_type in ("NUMERIC", "PACKED_DECIMAL", "BINARY_COMP"):
            return pd.Series(["0" * target_length] * len(pdf), index=pdf.index)
        return pd.Series([" " * target_length] * len(pdf), index=pdf.index)

    elif xtype == "conditional_derived":
        if primary_source and primary_source in pdf.columns:
            fill = default_value if default_value else ""
            return pdf[primary_source].fillna(fill)
        fill = default_value if default_value else " " * target_length
        return pd.Series([fill] * len(pdf), index=pdf.index)

    # Fallback
    return pd.Series([" " * max(target_length, 1)] * len(pdf), index=pdf.index)


def _comp3_hex_display_series(series: pd.Series, total_digits: int, signed: bool,
                              target_field: str) -> pd.Series:
    """Encode a numeric value as COMP-3 (packed decimal) and return a HEX DISPLAY.

    Nancy issue #2 — POLICY-CVG-UNITS is PIC S9(6)V9(5) COMP-3.

    COBOL COMP-3 packs two decimal digits per byte, with the final nibble
    holding the sign (C = positive, D = negative, F = unsigned). For N digits
    the on-disk size is ceil((N + 1) / 2) bytes. Example: 9.59547 -> the 11
    digits 00000959547 -> packed bytes 00 00 09 59 54 7C (trailing C = +).

    ============================= POC SCOPE / PRODUCTION NOTE =============================
    This function returns a HUMAN-READABLE HEX STRING (e.g. "00 00 09 59 54 7C")
    so the value can be verified against the COBOL/WMA expectation and stays
    representable in the current TEXT flat file + CSV.

    It does NOT yet emit the raw packed BINARY bytes. A production positional
    flat file must contain the actual ceil((N+1)/2) packed bytes (6 bytes here),
    which requires:
      1. a binary-capable output writer (the current FlatFileAdapter writes UTF-8 text),
      2. the record layout to budget the PACKED byte width (6) for this field
         instead of the digit width (11) — this re-flows all downstream offsets,
      3. confirmation from Russell (conversion SME) on the exact target format
         (true binary COMP-3 vs. a display/zoned representation).
    When that decision is made, replace the hex-display return with real packed
    bytes and switch the adapter to binary. Search for "COMP-3" / issue #2 to
    find the related touch points (flat_file_adapter.py, schema widths).
    ======================================================================================
    """
    def encode(val):
        s = "" if val is None else str(val).strip()
        if s == "":
            return ""
        neg = s.startswith("-")
        digits = re.sub(r"\D", "", s)  # keep only digits (decimal already implied)
        if digits == "":
            return s  # not numeric — leave as-is
        # Left-pad / trim to the field's total digit count.
        digits = digits[-total_digits:].rjust(total_digits, "0")
        # Sign nibble: C = +, D = -, F = unsigned.
        sign_nibble = ("D" if neg else "C") if signed else "F"
        nibbles = digits + sign_nibble
        # Pad to an even number of nibbles (leading zero) so it packs into bytes.
        if len(nibbles) % 2 == 1:
            nibbles = "0" + nibbles
        # Group into bytes and present as space-separated hex for readability.
        byte_pairs = [nibbles[i:i + 2] for i in range(0, len(nibbles), 2)]
        return " ".join(byte_pairs)

    return series.apply(encode)


def _rescale_decimals_series(series: pd.Series, target_decimals: int, target_field: str) -> pd.Series:
    """Rescale a numeric source value to the target's decimal precision.

    The template may carry more (or fewer) decimal places than the Cobol/WMA
    field (Byers requirement #2). This converts each source value to exactly
    `target_decimals` decimal places, then returns the digits with the implied
    decimal point removed (Cobol Vnn convention) — e.g. "22.36" at 2dp -> "2236",
    "22.69246" at 2dp -> "2269" (with precision-loss recorded).

    Non-numeric / blank values pass through unchanged (a separate validation
    rule governs whether the value should have been numeric).
    """
    tf = target_field
    lost = {"n": 0, "sample": ""}

    def rescale(val):
        s = "" if val is None else str(val).strip()
        if s == "":
            return s
        # Sign handling: keep track, operate on magnitude.
        neg = s.startswith("-")
        body = s[1:] if neg else s
        # Only rescale clean numerics; leave anything else untouched.
        if not re.fullmatch(r"\d*\.?\d*", body) or body in ("", "."):
            return s
        if "." in body:
            int_part, dec_part = body.split(".", 1)
        else:
            int_part, dec_part = body, ""
        # Detect precision loss (source has more decimals than target keeps).
        if len(dec_part) > target_decimals:
            lost["n"] += 1
            if not lost["sample"]:
                lost["sample"] = s
        # Pad or trim the decimal part to exactly target_decimals (truncate extra).
        dec_fixed = (dec_part + "0" * target_decimals)[:target_decimals]
        int_norm = int_part.lstrip("0") or "0"
        digits = (int_norm + dec_fixed)
        return ("-" + digits) if neg else digits

    out = series.apply(rescale)
    _record_overflow(tf, f"decimal precision reduced to {target_decimals}dp", lost["n"], lost["sample"])
    return out


def _apply_padding_series(series: pd.Series, target_length: int, data_type: str,
                          padding_rule: str, target_field: str = "") -> pd.Series:
    """Pad each value to exact target_length, detecting overflow.

    Exact-length contract (Byers requirement #1): every value must fit the Cobol
    field width. If a value is WIDER than target_length it is an overflow — we
    still truncate to keep the positional layout intact, but we RECORD it so the
    run surfaces the finding rather than silently corrupting data.
    """
    is_numeric = data_type in ("NUMERIC", "PACKED_DECIMAL", "BINARY", "BINARY_COMP") or padding_rule == "left_zero"
    overflow = {"n": 0, "sample": ""}

    def pad_value(val):
        s = str(val) if val is not None else ""
        # Overflow: significant content longer than the field can hold.
        # For numerics, compare digit count (excluding a leading '-'); for char,
        # compare full length.
        measure = s[1:] if (is_numeric and s.startswith("-")) else s
        if len(measure) > target_length:
            overflow["n"] += 1
            if not overflow["sample"]:
                overflow["sample"] = s
            # Truncate to preserve fixed-width layout (keep least-significant
            # digits for numerics = rightmost; keep leftmost for char).
            s = measure[-target_length:] if is_numeric else s[:target_length]
        if is_numeric:
            return s.zfill(target_length)
        else:
            return s[:target_length].ljust(target_length)

    out = series.apply(pad_value)
    _record_overflow(target_field or "(field)", f"value exceeded Cobol width {target_length}",
                     overflow["n"], overflow["sample"])
    return out
