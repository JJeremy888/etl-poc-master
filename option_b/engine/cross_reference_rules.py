"""Cross-reference validation — DataFrame joins for referential integrity."""
from pyspark.sql import Column, DataFrame, functions as F
from pyspark.sql.types import StringType


def apply_cross_reference(
    child_df: DataFrame,
    parent_df: DataFrame,
    child_table: str,
    join_fields_child: list[str],
    join_fields_parent: list[str],
    severity: str = "SEVERE",
) -> DataFrame:
    """Apply cross-reference check via left anti-join.

    Records in child_df whose join keys don't exist in parent_df
    get a VAL_ column with a failure message.

    Returns the child_df with a new VAL_CROSS_TABLE column.
    """
    val_col = f"VAL_{child_table}_CROSS_TABLE"

    # Build join condition
    if not join_fields_child or not join_fields_parent:
        # No join fields defined — skip cross-reference
        return child_df.withColumn(val_col, F.lit(None).cast(StringType()))

    # Rename parent columns to avoid ambiguity
    parent_renamed = parent_df
    rename_map = {}
    for cf, pf in zip(join_fields_child, join_fields_parent):
        alias = f"_parent_{pf}"
        parent_renamed = parent_renamed.withColumnRenamed(pf, alias)
        rename_map[cf] = alias

    # Select only the join key columns from parent (deduplicated)
    parent_keys = parent_renamed.select([F.col(alias) for alias in rename_map.values()]).distinct()

    # Left join child to parent keys
    join_cond = [child_df[cf] == parent_keys[rename_map[cf]] for cf in join_fields_child]

    joined = child_df.join(parent_keys, join_cond, "left")

    # Records where parent key is null = no match
    first_parent_alias = list(rename_map.values())[0]
    no_match = F.col(first_parent_alias).isNull()

    result = joined.withColumn(
        val_col,
        F.when(
            no_match,
            F.lit(f"{severity}: No matching CNT record for this policy")
        ).otherwise(F.lit(None).cast(StringType()))
    )

    # Drop the parent key columns
    for alias in rename_map.values():
        result = result.drop(alias)

    return result


# =============================================================================
# Cross-reference handlers added for Validation_Rules_Master.xlsx
# =============================================================================
#
# There are two families of cross-reference handlers:
#
#   1. Column-producing handlers (compile_*): evaluate within a single record
#      and return a PySpark Column (None on pass, message on fail). These are
#      registered in CROSS_REFERENCE_HANDLER_REGISTRY and can run inside the
#      same withColumn pass as field-level rules.
#         - compile_required
#         - compile_value_compare
#         - compile_field_compare
#
#   2. DataFrame-level handlers (apply_*): require joins across tables and are
#      invoked by the validation orchestrator with parent/child DataFrames.
#         - apply_cross_reference     (existing referential integrity check)
#         - apply_cross_table_match   (target field must match a parent field)
#         - apply_occurrence_check    (record existence across tables)
# =============================================================================


def _single_precondition(pf: str, op: str, pv: str):
    """Build one boolean Column from a (field, operator, value) triple.

    Returns None when the triple is empty/`none`. `pf` must be a column that is
    present on the DataFrame the precondition will be evaluated against.
    """
    pf = (pf or "").strip()
    op = (op or "").strip()
    pv = (pv or "").strip()
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


def _combine_preconditions(p1, p2, logic: str):
    """Combine two optional precondition Columns via AND/OR.

    If only one is present, return it. If neither, return None.
    `logic` defaults to AND when blank/unrecognized.
    """
    if p1 is None and p2 is None:
        return None
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    return (p1 | p2) if (logic or "").strip().upper() == "OR" else (p1 & p2)


def _xref_precondition(rule: dict):
    """Build a boolean Column from the rule's precondition columns, combining a
    second precondition (precondition_field_2/operator_2/value_2) via
    precondition_logic (AND/OR, default AND). Returns None when there is no
    precondition (the rule is then unconditional).
    """
    p1 = _single_precondition(
        rule.get("precondition_field"),
        rule.get("precondition_operator"),
        rule.get("precondition_value"),
    )
    p2 = _single_precondition(
        rule.get("precondition_field_2"),
        rule.get("precondition_operator_2"),
        rule.get("precondition_value_2"),
    )
    p3 = _single_precondition(
        rule.get("precondition_field_3"),
        rule.get("precondition_operator_3"),
        rule.get("precondition_value_3"),
    )
    logic = rule.get("precondition_logic", "")
    combined = _combine_preconditions(p1, p2, logic)
    combined = _combine_preconditions(combined, p3, logic)
    return combined


def _xref_precondition_present(rule: dict) -> bool:
    """True if the rule defines at least one usable precondition triple."""
    for fkey, okey in (
        ("precondition_field", "precondition_operator"),
        ("precondition_field_2", "precondition_operator_2"),
        ("precondition_field_3", "precondition_operator_3"),
    ):
        pf = (rule.get(fkey) or "").strip()
        op = (rule.get(okey) or "").strip()
        if pf and op and op != "none":
            return True
    return False


def _is_number(value: str) -> bool:
    """True if the string parses as a number (int or float)."""
    try:
        float(str(value).strip())
        return True
    except (TypeError, ValueError):
        return False


def _xref_message(rule: dict, default: str) -> str:
    """Prefer an author-supplied error_message; fall back to a default."""
    msg = (rule.get("error_message") or "").strip()
    return msg if msg else default


def _re_ident(value: str) -> bool:
    """True if `value` looks like a field/column identifier (starts with a letter
    or underscore, contains only word characters) rather than a numeric or other
    literal. Used to tell a field reference from a literal on a comparison RHS."""
    import re as _re
    if value is None:
        return False
    return bool(_re.fullmatch(r"[A-Za-z_]\w*", str(value).strip()))


def _extract_numeric_literal(expected: str):
    """Return a float from an expected_result that is either a bare number
    ("0", "100.5") or a full expression that ends in a number
    ("CVG_TEMP_FLAT_EXTRA >= 0" -> 0.0). Returns None if no numeric literal
    is present, so callers can skip instead of raising on float()."""
    if expected is None:
        return None
    text = str(expected).strip()
    if not text:
        return None
    # Fast path: the whole value is numeric.
    try:
        return float(text)
    except ValueError:
        pass
    # Otherwise take the last whitespace-separated token (e.g. the "0" in
    # "FIELD >= 0") and try that.
    tokens = text.replace("=", " ").replace(">", " ").replace("<", " ").split()
    for tok in reversed(tokens):
        try:
            return float(tok)
        except ValueError:
            continue
    return None


def compile_required(rule: dict) -> Column:
    """target_field must not be blank.

    If a precondition is supplied, the requirement only applies when the
    precondition holds; otherwise it is unconditional.
    """
    field = rule["target_field"]
    severity = rule["severity"]
    precondition = _xref_precondition(rule)

    is_blank = F.col(field).isNull() | (F.trim(F.col(field)) == F.lit(""))
    trigger = is_blank if precondition is None else (precondition & is_blank)
    message = _xref_message(rule, f"{severity}: {field} is required")

    return F.when(trigger, F.lit(message)).otherwise(F.lit(None).cast(StringType()))


def compile_value_compare(rule: dict) -> Column:
    """Compare target_field to a literal (expected_result) using an operator.

    The operator comes from precondition_operator; the literal it compares
    against comes from expected_result. Numeric operators (gt/lt/gte/lte) cast
    both sides to double. Blank target values are skipped (presence is enforced
    by a separate not_blank/required rule) unless the operator is blank/not_blank.
    """
    field = rule["target_field"]
    severity = rule["severity"]
    xref_id = rule.get("xref_id", "?")

    # Resolve (operator, value) from the operator column and/or the expected text.
    # Supported Expected Result shapes (from the master workbook):
    #   - operator in column, bare value        : op='gte', expected='0'
    #   - operator + value embedded, col blank   : expected='eq 2', 'gt 0', 'lte 100', 'eq 99999999'
    #   - 'eq blanks' / 'eq blank'               : blank check
    #   - field repeated                         : expected='CVG_TEMP_FLAT_EXTRA >= 0'
    #   - function form                          : expected='NOT_BLANK(FIELD)'
    # If the rule genuinely cannot be interpreted, we DO NOT silently skip it —
    # we raise ValueError so it surfaces loudly (per the no-silent-no-op policy).
    op, value, kind = _parse_value_compare(rule, field)

    col = F.trim(F.col(field))
    is_blank = F.col(field).isNull() | (col == F.lit(""))

    if kind == "not_blank":
        violated = is_blank
    elif kind == "blank":
        violated = ~is_blank
    elif kind == "numeric":
        num = _extract_numeric_literal(value)
        if num is None:
            raise ValueError(
                f"value_compare {xref_id}: numeric operator '{op}' but no numeric "
                f"literal in expected_result {value!r} (target {field})"
            )
        left = col.cast("double")
        right = F.lit(num)
        cmp = {
            "gt": left <= right, "lt": left >= right,
            "gte": left < right, "lte": left > right,
            "eq": left != right, "neq": left == right,
        }.get(op)
        if cmp is None:
            raise ValueError(f"value_compare {xref_id}: unsupported numeric operator {op!r}")
        violated = ~is_blank & cmp
    elif kind == "string":
        if op == "eq":
            violated = ~is_blank & (col != F.lit(value))
        elif op == "neq":
            violated = ~is_blank & (col == F.lit(value))
        elif op == "in":
            allowed = [v.strip() for v in value.split("|")]
            violated = ~is_blank & ~col.isin(allowed)
        elif op == "not_in":
            disallowed = [v.strip() for v in value.split("|")]
            violated = ~is_blank & col.isin(disallowed)
        else:
            raise ValueError(f"value_compare {xref_id}: unsupported string operator {op!r}")
    else:
        # kind is None -> could not interpret. Surface loudly; do not skip.
        raise ValueError(
            f"value_compare {xref_id}: cannot interpret expected_result "
            f"{(rule.get('expected_result') or '')!r} with operator "
            f"{(rule.get('precondition_operator') or '')!r} (target {field})"
        )

    message = _xref_message(rule, f"{severity}: {field} fails comparison {op} {value}")
    return F.when(violated, F.lit(message)).otherwise(F.lit(None).cast(StringType()))


def _parse_value_compare(rule: dict, field: str):
    """Resolve (operator, value, kind) for a value_compare rule.

    kind is one of: 'numeric', 'string', 'blank', 'not_blank', or None (if the
    rule cannot be interpreted). Callers must treat kind=None as an ERROR (raise),
    never as a silent skip.
    """
    op = (rule.get("precondition_operator") or "").strip().lower()
    expected = (rule.get("expected_result") or "").strip()

    if not expected:
        return (op, "", None)

    # Function form: NOT_BLANK(...) / BLANK(...)
    up = expected.upper()
    if up.startswith("NOT_BLANK") or up.startswith("NOTBLANK"):
        return ("not_blank", "", "not_blank")
    if up.startswith("BLANK") or up.startswith("IS_BLANK"):
        return ("blank", "", "blank")

    # If no operator column, try to parse a leading operator token from expected,
    # e.g. 'eq 2', 'gt 0', 'lte 100', 'eq blanks'.
    OP_WORDS = {"eq", "neq", "ne", "gt", "lt", "gte", "lte", "ge", "le", "in", "not_in"}
    OP_SYMS = {">=": "gte", "<=": "lte", ">": "gt", "<": "lt", "=": "eq", "!=": "neq", "<>": "neq"}
    tokens = expected.split()
    if not op:
        # word operator as first token
        if tokens and tokens[0].lower() in OP_WORDS:
            op = tokens[0].lower()
            expected = " ".join(tokens[1:]).strip()
        else:
            # symbolic operator anywhere (e.g. 'FIELD >= 0')
            for sym, name in OP_SYMS.items():
                if sym in expected:
                    op = name
                    expected = expected.split(sym, 1)[1].strip()
                    break
    # Normalize operator aliases.
    op = {"ne": "neq", "ge": "gte", "le": "lte"}.get(op, op)

    if not op:
        return (op, expected, None)

    # 'blanks'/'blank' as the value means a blank check.
    if expected.lower() in ("blank", "blanks"):
        if op in ("eq",):
            return (op, "", "blank")
        if op in ("neq",):
            return (op, "", "not_blank")

    # Decide numeric vs string by whether a numeric literal is extractable.
    if op in ("gt", "lt", "gte", "lte"):
        return (op, expected, "numeric")
    if op in ("eq", "neq"):
        # numeric if the value parses as a number, else string equality
        if _extract_numeric_literal(expected) is not None and not any(c.isalpha() for c in expected):
            return (op, expected, "numeric")
        return (op, expected, "string")
    if op in ("in", "not_in"):
        return (op, expected, "string")

    return (op, expected, None)


def compile_substring_blank(rule: dict) -> Column:
    """Flag when a first/last N-char substring of target_field is blank.

    Built for XR_ADD_008: "ADD_POSTAL_CODE (last 5 characters) = blanks" — i.e.
    warn when the ZIP+4 tail is missing. Parameterized via existing columns:
      * count_operator = "first" | "last"  (which end to take the substring from)
      * count_value    = N                 (substring length, e.g. 5)

    Semantics:
      * The whole-field-blank case is SKIPPED here (presence is a separate
        not_blank/required concern), so this only fires when the field HAS
        content but the requested substring is blank/whitespace — i.e. the base
        value exists but the tail/head segment is absent.
      * If the field is shorter than N, the requested substring is treated as
        blank (segment absent) and flagged.
      * A precondition, if present, gates when the check applies.
    """
    field = rule["target_field"]
    severity = rule["severity"]
    side = (rule.get("count_operator") or "").strip().lower()
    n_raw = str(rule.get("count_value") or "").strip()

    if side not in ("first", "last") or not n_raw.isdigit() or int(n_raw) <= 0:
        # Misconfigured — do not silently misfire; carry as a no-op.
        return F.lit(None).cast(StringType())
    n = int(n_raw)

    col = F.col(field)
    whole = F.trim(col)
    is_blank = col.isNull() | (whole == F.lit(""))

    # Extract the requested substring from the RAW (untrimmed) value so trailing
    # spaces in a fixed-width field are seen as blank, then trim to test.
    length = F.length(col)
    if side == "last":
        # last N chars; if shorter than N, substring returns what exists.
        segment = F.expr(f"substring({field}, greatest(length({field}) - {n} + 1, 1), {n})")
        # Segment is "absent" when the field is shorter than N.
        too_short = length < F.lit(n)
    else:  # first
        segment = F.expr(f"substring({field}, 1, {n})")
        too_short = length < F.lit(n)

    seg_blank = segment.isNull() | (F.trim(segment) == F.lit("")) | too_short

    # Only warn when the field has content but the segment is blank/absent.
    violated = ~is_blank & seg_blank

    gate = _xref_precondition(rule)
    if gate is not None:
        violated = gate & violated

    message = _xref_message(
        rule, f"{severity}: {side} {n} characters of {field} are blank"
    )
    return F.when(violated, F.lit(message)).otherwise(F.lit(None).cast(StringType()))


def compile_field_compare(rule: dict) -> Column:
    """Compare target_field to another field (compare_field) in the same record.

    Operator comes from precondition_operator (eq/neq/gt/lt/gte/lte). Comparison
    is skipped when either field is blank. A precondition, if present, gates
    when the comparison applies.
    """
    field = rule["target_field"]
    compare = rule["compare_field"]
    severity = rule["severity"]
    op = (rule.get("precondition_operator") or "eq").strip()

    left_raw = F.trim(F.col(field))
    right_raw = F.trim(F.col(compare))
    either_blank = (
        F.col(field).isNull() | (left_raw == F.lit(""))
        | F.col(compare).isNull() | (right_raw == F.lit(""))
    )

    if op in ("gt", "lt", "gte", "lte"):
        left = left_raw.cast("double")
        right = right_raw.cast("double")
        violated = {
            "gt": left <= right,
            "lt": left >= right,
            "gte": left < right,
            "lte": left > right,
        }[op]
    elif op == "eq":
        violated = left_raw != right_raw
    elif op == "neq":
        violated = left_raw == right_raw
    else:
        return F.lit(None).cast(StringType())

    gate = _xref_precondition(rule)
    trigger = (~either_blank & violated)
    if gate is not None:
        trigger = gate & trigger

    message = _xref_message(rule, f"{severity}: {field} {op} {compare} check failed")
    return F.when(trigger, F.lit(message)).otherwise(F.lit(None).cast(StringType()))


def _parse_expected_clause(expected: str):
    """Parse a simple, single-record Expected Result clause into (field, op, values).

    Supported forms (case-insensitive operators):
        FIELD = value            -> (FIELD, "eq", [value])
        FIELD != value / NE      -> (FIELD, "neq", [value])
        FIELD in (a|b|c) / a,b   -> (FIELD, "in", [a, b, c])
        FIELD not in (a|b)       -> (FIELD, "not_in", [...])
        FIELD > n / < / >= / <=  -> (FIELD, "gt"/"lt"/"gte"/"lte", [n])
        FIELD is blank / = blank -> (FIELD, "blank", [])
        FIELD not blank          -> (FIELD, "not_blank", [])

    Returns None when the clause is not a recognized simple form (e.g. it is an
    aggregate/multi-record expression such as COUNT(...), EXISTS(...), or free
    text). Such rules are handled by dedicated aggregate rule types, not here.
    """
    import re
    e = (expected or "").strip()
    if not e:
        return None
    # Reject aggregate / multi-record / free-text expressions. A plain value
    # list like "FIELD in (F|J)" is fine; we only reject known aggregate/function
    # constructs and multi-clause prose.
    lowered = e.lower()
    COMPLEX_TOKENS = (
        "count", "exists", "unique", "match_", "coverage_occurrence_count",
        "one_occurrence_per_joint_insured", "optional_multi_occurrence",
        "if_blank", "warning(", " and ", " or ", " then ", "each ",
        "occurrence", " when ",
    )
    if any(tok in lowered for tok in COMPLEX_TOKENS):
        return None
    # A function call like NAME(...) is complex. The SQL keyword "in" may be
    # legitimately followed by "(", so temporarily blank out "in (" before the
    # function-call check.
    probe = re.sub(r"\bin\s*\(", "in ", lowered)
    if re.search(r"[a-z_]\w*\s*\(", probe):
        return None

    # Normalize surrounding parentheses in value lists: "in (F|J)" -> "in F|J"
    def _strip_parens(s):
        s = s.strip()
        if s.startswith("(") and s.endswith(")"):
            s = s[1:-1].strip()
        return s

    # blank forms
    m = re.match(r"^(\w+)\s*(?:=\s*blank|is\s+blank)$", e, re.IGNORECASE)
    if m:
        return (m.group(1), "blank", [])
    m = re.match(r"^(\w+)\s+not\s+blank$", e, re.IGNORECASE)
    if m:
        return (m.group(1), "not_blank", [])

    # not in
    m = re.match(r"^(\w+)\s+not\s+in\s+(.+)$", e, re.IGNORECASE)
    if m:
        vals = [v.strip() for v in re.split(r"[|,]", _strip_parens(m.group(2))) if v.strip()]
        return (m.group(1), "not_in", vals)
    # in
    m = re.match(r"^(\w+)\s+in\s+(.+)$", e, re.IGNORECASE)
    if m:
        vals = [v.strip() for v in re.split(r"[|,]", _strip_parens(m.group(2))) if v.strip()]
        return (m.group(1), "in", vals)

    # comparison operators
    m = re.match(r"^(\w+)\s*(>=|<=|!=|<>|=|>|<)\s*(.+)$", e)
    if m:
        field, sym, val = m.group(1), m.group(2), m.group(3).strip()
        op = {"=": "eq", "!=": "neq", "<>": "neq",
              ">": "gt", "<": "lt", ">=": "gte", "<=": "lte"}[sym]
        return (field, op, [val])

    return None


def compile_xref_conditional(rule: dict) -> Column:
    """Cross-reference conditional: IF precondition THEN target satisfies expected.

    Two shapes are supported:

    1. Expected Result is EMPTY  ->  the rule is advisory: it emits its message
       whenever the precondition holds (e.g. "if CNT_POLICY_CODE = D, warn and
       ask for the supplemental code"). If there is also no precondition, the
       rule always fires (rare; typically used with an author message).

    2. Expected Result is a SIMPLE single-record clause (FIELD = value,
       FIELD in (...), FIELD >= n, FIELD is blank, ...): the rule fires when the
       precondition holds AND the expected clause is violated.

    Aggregate / multi-record expected results (COUNT(...), EXISTS(...),
    MATCH_ANY_..., etc.) are NOT handled here — they use dedicated aggregate
    rule types. For those, this handler passes (returns None) so the row is
    carried without a spurious result.
    """
    severity = rule["severity"]
    precondition = _xref_precondition(rule)
    expected = (rule.get("expected_result") or "").strip()

    # --- Shape 1: empty expected result ---
    if not expected:
        target = rule.get("target_field", "record")
        pre_field = (rule.get("precondition_field") or "").strip()
        pre_op = (rule.get("precondition_operator") or "").strip().lower()
        pre_val = (rule.get("precondition_value") or "").strip().lower()

        # Presence-required shape: precondition is "<field> neq blank" (or
        # not_blank) with the field == target. This encodes "this field MUST be
        # present" — so the rule must FIRE when the field IS blank (precondition
        # NOT met), not when it is present. (e.g. XR_CON_001..004 "must not be
        # empty/blank".) Treating precondition-holds as the failure here would
        # flag every well-formed record — the opposite of the intent.
        is_presence_required = (
            pre_field == target
            and ((pre_op == "neq" and pre_val in ("blank", "blanks", "")) or pre_op == "not_blank")
        )
        if is_presence_required:
            col = F.trim(F.col(target))
            is_blank = F.col(target).isNull() | (col == F.lit(""))
            message = _xref_message(rule, f"{severity}: {target} must not be blank")
            return F.when(is_blank, F.lit(message)).otherwise(F.lit(None).cast(StringType()))

        # Otherwise this is a genuine advisory: emit the message WHEN the
        # precondition holds (e.g. XR_CON_006 "if CNT_POLICY_CODE = D, warn").
        trigger = precondition if precondition is not None else F.lit(True)
        message = _xref_message(
            rule, f"{severity}: {target} condition met"
        )
        return F.when(trigger, F.lit(message)).otherwise(F.lit(None).cast(StringType()))

    # --- Shape 2: simple expected clause ---
    parsed = _parse_expected_clause(expected)
    if parsed is None:
        # Aggregate / free-text expected result — not evaluable here.
        return F.lit(None).cast(StringType())

    field, op, values = parsed
    col = F.trim(F.col(field))
    is_blank = F.col(field).isNull() | (col == F.lit(""))

    # The right-hand side of a comparison may be a LITERAL or another FIELD name
    # (e.g. "CVG_TEMP_FLAT_END_DATE <= CVG_MATURE_EXPIRE_DATE"). Detect a field
    # reference by the identifier pattern (starts with a letter/underscore, not a
    # number). Field-to-field comparisons compare the two columns directly; for
    # YYYYMMDD dates and codes, trimmed-string comparison is order-correct.
    rhs = values[0] if values else ""
    # A right-hand side is a FIELD reference only if it both looks like an
    # identifier AND actually exists as a column in the data. Enum literals such
    # as "N", "F", "G", "D" also match the identifier pattern, so the identifier
    # test alone would wrongly turn them into F.col("N") and blow up the whole
    # run with UNRESOLVED_COLUMN. When the available-column list is provided
    # (injected by the orchestrator as `_available_columns`), require membership;
    # if it is absent, fall back to "treat as literal" — the safe default, since
    # a literal comparison never raises.
    available_columns = rule.get("_available_columns")
    if available_columns is not None:
        rhs_is_field = bool(_re_ident(rhs)) and rhs in available_columns
    else:
        rhs_is_field = bool(_re_ident(rhs)) and rhs.isupper() and "_" in rhs

    if op == "eq":
        right = F.trim(F.col(rhs)) if rhs_is_field else F.lit(rhs)
        violated = ~is_blank & (col != right)
    elif op == "neq":
        right = F.trim(F.col(rhs)) if rhs_is_field else F.lit(rhs)
        violated = ~is_blank & (col == right)
    elif op == "in":
        violated = ~is_blank & ~col.isin(values)
    elif op == "not_in":
        violated = ~is_blank & col.isin(values)
    elif op == "blank":
        violated = ~is_blank
    elif op == "not_blank":
        violated = is_blank
    elif op in ("gt", "lt", "gte", "lte"):
        if rhs_is_field:
            # Field-to-field: compare as trimmed strings, and only when BOTH
            # sides are non-blank (a missing comparand is not a violation here).
            other = F.trim(F.col(rhs))
            other_blank = F.col(rhs).isNull() | (other == F.lit(""))
            left, right = col, other
            cmp = {
                "gt": left <= right, "lt": left >= right,
                "gte": left < right, "lte": left > right,
            }[op]
            violated = ~is_blank & ~other_blank & cmp
        else:
            num = _extract_numeric_literal(rhs)
            if num is None:
                raise ValueError(
                    f"conditional {rule.get('xref_id','?')}: comparison RHS "
                    f"{rhs!r} is neither a number nor a field name (expected "
                    f"{expected!r})"
                )
            left = col.cast("double")
            right = F.lit(num)
            violated = ~is_blank & {
                "gt": left <= right, "lt": left >= right,
                "gte": left < right, "lte": left > right,
            }[op]
    else:
        return F.lit(None).cast(StringType())

    trigger = violated if precondition is None else (precondition & violated)
    message = _xref_message(rule, f"{severity}: {field} fails expected {expected}")
    return F.when(trigger, F.lit(message)).otherwise(F.lit(None).cast(StringType()))


def apply_cross_table_match(
    child_df: DataFrame,
    parent_df: DataFrame,
    child_table: str,
    target_field: str,
    compare_field: str,
    join_fields_child: list[str],
    join_fields_parent: list[str],
    severity: str = "SEVERE",
    error_message: str | None = None,
    val_col: str | None = None,
    rule: dict | None = None,
) -> DataFrame:
    """target_field in child_df must equal compare_field in the joined parent row.

    Joins child to parent on the given key fields, then flags records where the
    child's target_field does not match the parent's compare_field. Records with
    no parent match are skipped here (referential integrity is a separate rule).

    If `rule` carries a precondition (precondition_field/operator/value, plus an
    optional second precondition), the match is only enforced on rows where the
    precondition holds — e.g. only Coverage rows with CVG_TYPE in (ANNT|AH). The
    precondition field must be a column on the child DataFrame.

    Returns child_df with a new VAL_ column appended.
    """
    val_col = val_col or f"VAL_{child_table}_{target_field}_XMATCH"

    if not join_fields_child or not join_fields_parent:
        return child_df.withColumn(val_col, F.lit(None).cast(StringType()))

    # Optional precondition gate. Uses _attach_precondition_flag so a precondition
    # field on either the child OR the parent table is handled (and two
    # preconditions can be combined via precondition_logic). Adds _precond_ok.
    gated = rule is not None and _xref_precondition_present(rule)
    src_df = child_df
    if gated:
        src_df, reason = _attach_precondition_flag(
            child_df, parent_df, join_fields_child, join_fields_parent, rule,
        )
        if reason is not None:
            # Precondition references a field we can't resolve — carry, don't flag.
            return child_df.withColumn(val_col, F.lit(None).cast(StringType()))

    # Build the slim parent projection in ONE explicit select with fresh aliases,
    # rather than a chain of withColumnRenamed calls (which is fragile when the
    # compare field coincides with a join key, or when the parent == child table
    # in a self-referential rule). Each needed parent column is selected once,
    # aliased deterministically:
    #   join key i        -> _parent_<parentfield_i>
    #   compare field     -> _parent_<field> if it's a join key, else _parent_cmp_<field>
    rename_map = {}
    proj = []
    for cf, pf in zip(join_fields_child, join_fields_parent):
        alias = f"_parent_{pf}"
        rename_map[cf] = alias
        proj.append(F.col(pf).alias(alias))

    if compare_field in join_fields_parent:
        # Compare field IS a join key — reuse that alias, no extra column.
        compare_alias = f"_parent_{compare_field}"
    else:
        compare_alias = f"_parent_cmp_{compare_field}"
        proj.append(F.col(compare_field).alias(compare_alias))

    parent_slim = parent_df.select(*proj).distinct()

    join_cond = [src_df[cf] == parent_slim[rename_map[cf]] for cf in join_fields_child]
    joined = src_df.join(parent_slim, join_cond, "left")

    first_parent_alias = list(rename_map.values())[0]
    matched = F.col(first_parent_alias).isNotNull()
    mismatch = F.trim(F.col(target_field)) != F.trim(F.col(compare_alias))

    trigger = matched & mismatch
    if gated:
        trigger = F.col("_precond_ok") & trigger

    message = error_message or f"{severity}: {target_field} does not match parent {compare_field}"

    result = joined.withColumn(
        val_col,
        F.when(trigger, F.lit(message)).otherwise(F.lit(None).cast(StringType()))
    )

    # Dedupe: compare_alias may equal a join alias when compare_field is a join key.
    drop_cols = list(dict.fromkeys(list(rename_map.values()) + [compare_alias]))
    if gated:
        drop_cols.append("_precond_ok")
    for c in drop_cols:
        result = result.drop(c)

    return result


def apply_occurrence_check(
    child_df: DataFrame,
    parent_df: DataFrame,
    child_table: str,
    target_field: str,
    join_fields_child: list[str],
    join_fields_parent: list[str],
    severity: str = "SEVERE",
    error_message: str | None = None,
    val_col: str | None = None,
) -> DataFrame:
    """Each child record's key must occur (exist) in the parent table.

    A multi-record existence check: flags child records whose join key has no
    corresponding parent record. Implemented as a left join + null check on the
    parent key (semantically the same shape as apply_cross_reference, but named
    for the occurrence_check rule type and allowing a custom target/message).

    Returns child_df with a new VAL_ column appended.
    """
    val_col = val_col or f"VAL_{child_table}_{target_field}_OCCURS"

    if not join_fields_child or not join_fields_parent:
        return child_df.withColumn(val_col, F.lit(None).cast(StringType()))

    parent_renamed = parent_df
    rename_map = {}
    for cf, pf in zip(join_fields_child, join_fields_parent):
        alias = f"_parent_{pf}"
        parent_renamed = parent_renamed.withColumnRenamed(pf, alias)
        rename_map[cf] = alias

    parent_keys = parent_renamed.select([F.col(a) for a in rename_map.values()]).distinct()
    join_cond = [child_df[cf] == parent_keys[rename_map[cf]] for cf in join_fields_child]
    joined = child_df.join(parent_keys, join_cond, "left")

    first_parent_alias = list(rename_map.values())[0]
    no_match = F.col(first_parent_alias).isNull()
    message = error_message or f"{severity}: {target_field} has no matching {child_table} parent record"

    result = joined.withColumn(
        val_col,
        F.when(no_match, F.lit(message)).otherwise(F.lit(None).cast(StringType()))
    )

    for alias in rename_map.values():
        result = result.drop(alias)

    return result


# =============================================================================
# Aggregate (group-level) cross-reference handlers
# =============================================================================
#
# These evaluate a condition over a GROUP of rows (e.g. all rows for one policy)
# rather than a single record. When a group fails, EVERY row in that group is
# flagged, so the failure is visible on each contributing record.
#
# Optional parent gate: if a precondition references a parent-table field
# (compare_table + join fields), the check applies only to groups whose joined
# parent value satisfies the precondition. If no parent is involved, the
# precondition (if any) is evaluated against the child rows directly.
# =============================================================================

from pyspark.sql import Window


def _attach_precondition_flag(
    child_df, parent_df, join_fields_child, join_fields_parent, rule,
    flag_col="_precond_ok",
):
    """Return (df_with_flag, reason) where `flag_col` is True for rows whose
    precondition(s) hold. Supports up to two preconditions combined via
    `precondition_logic` (AND/OR). Precondition fields may live on the child or,
    if joined, on the parent table.

    `reason` is None on success, or a string when the check cannot be applied
    (a referenced precondition field is on neither the child nor a joinable
    parent) — the caller should then carry the rule without flagging.
    """
    triples = [
        (rule.get("precondition_field"), rule.get("precondition_operator"), rule.get("precondition_value")),
        (rule.get("precondition_field_2"), rule.get("precondition_operator_2"), rule.get("precondition_value_2")),
        (rule.get("precondition_field_3"), rule.get("precondition_operator_3"), rule.get("precondition_value_3")),
    ]
    # Which precondition fields must be sourced from the parent?
    parent_fields_needed = []
    df = child_df
    for pf, op, pv in triples:
        pf = (pf or "").strip()
        op = (op or "").strip()
        if not pf or not op or op == "none":
            continue
        if pf in child_df.columns:
            continue
        if parent_df is not None and pf in parent_df.columns and join_fields_child:
            parent_fields_needed.append(pf)
        else:
            return child_df, f"precondition field '{pf}' not found on child or parent"

    # Join needed parent precondition fields in (under their own names via alias
    # then rename back so _single_precondition can reference them directly).
    if parent_fields_needed:
        parent_renamed = parent_df
        rename_map = {}
        for cf, ppf in zip(join_fields_child, join_fields_parent):
            a = f"_pj_{ppf}"
            parent_renamed = parent_renamed.withColumnRenamed(ppf, a)
            rename_map[cf] = a
        select_cols = [F.col(a) for a in rename_map.values()] + [F.col(pf) for pf in parent_fields_needed]
        slim = parent_renamed.select(*select_cols).distinct()
        cond = [child_df[cf] == slim[rename_map[cf]] for cf in join_fields_child]
        df = child_df.join(slim, cond, "left")
        for a in rename_map.values():
            df = df.drop(a)

    logic = rule.get("precondition_logic", "")
    combined = None
    for t in triples:
        combined = _combine_preconditions(combined, _single_precondition(*t), logic)
    flag = combined if combined is not None else F.lit(True)
    df = df.withColumn(flag_col, flag)

    # Materialize the flag, then DROP the joined bare parent precondition columns.
    # The flag now captures the precondition result, so the source parent columns
    # are no longer needed. Leaving them on df would create a duplicate parent
    # lineage that a subsequent parent join (e.g. the compare-field join in
    # apply_match_across_occurrences / apply_cross_table_match) turns into an
    # ambiguous / UNRESOLVED_COLUMN error.
    if parent_fields_needed:
        for pf in parent_fields_needed:
            if pf in df.columns:
                df = df.drop(pf)
    return df, None


def apply_values_present(
    child_df: DataFrame,
    parent_df,
    child_table: str,
    groupby_fields: list[str],
    filter_field: str,
    required_values: list[str],
    join_fields_child: list[str],
    join_fields_parent: list[str],
    rule: dict,
    severity: str = "SEVERE",
    error_message: str | None = None,
    val_col: str | None = None,
) -> DataFrame:
    """Every value in `required_values` must appear at least once, within each
    group (defined by `groupby_fields`), among rows where the precondition(s) hold.

    Groups that satisfy the precondition but are missing any required value have
    ALL their rows flagged. Rows not in a triggered group pass. `rule` supplies
    the precondition columns (incl. an optional second precondition).
    """
    val_col = val_col or f"VAL_{child_table}_{filter_field}_VALUES_PRESENT"
    if not groupby_fields or not filter_field or not required_values:
        return child_df.withColumn(val_col, F.lit(None).cast(StringType()))

    df, reason = _attach_precondition_flag(
        child_df, parent_df, join_fields_child, join_fields_parent, rule,
    )
    if reason is not None:
        # Cannot evaluate — carry without flagging.
        return child_df.withColumn(val_col, F.lit(None).cast(StringType()))

    w = Window.partitionBy(*[F.col(g) for g in groupby_fields])
    fval = F.trim(F.col(filter_field))

    # For each required value, does it appear anywhere in the group (among rows
    # where the precondition holds)?
    missing_any = F.lit(False)
    for rv in required_values:
        present_in_group = F.max(
            F.when(F.col("_precond_ok") & (fval == F.lit(rv)), F.lit(1)).otherwise(F.lit(0))
        ).over(w)
        missing_any = missing_any | (present_in_group == F.lit(0))

    # Does this group have any row where the precondition holds? (Only then does
    # the requirement apply.)
    group_triggered = F.max(
        F.when(F.col("_precond_ok"), F.lit(1)).otherwise(F.lit(0))
    ).over(w) == F.lit(1)

    message = error_message or (
        f"{severity}: group missing required {filter_field} value(s) "
        f"{'|'.join(required_values)}"
    )
    result = df.withColumn(
        val_col,
        F.when(group_triggered & missing_any, F.lit(message)).otherwise(F.lit(None).cast(StringType()))
    ).drop("_precond_ok")
    return result


def apply_occurrence_count(
    child_df: DataFrame,
    parent_df,
    child_table: str,
    groupby_fields: list[str],
    filter_field: str,
    filter_values: list[str],
    count_operator: str,
    count_value: str,
    join_fields_child: list[str],
    join_fields_parent: list[str],
    rule: dict,
    severity: str = "SEVERE",
    error_message: str | None = None,
    val_col: str | None = None,
) -> DataFrame:
    """Count rows per group (optionally filtered to filter_field in filter_values,
    among rows where the precondition(s) hold) and assert count `count_operator`
    `count_value`. Groups that violate the assertion have all rows flagged.
    `rule` supplies the precondition columns (incl. an optional second one).
    """
    val_col = val_col or f"VAL_{child_table}_OCCURRENCE_COUNT"
    op = (count_operator or "").strip()
    count_value = str(count_value or "").strip()
    if not groupby_fields or not op or not count_value:
        return child_df.withColumn(val_col, F.lit(None).cast(StringType()))

    df, reason = _attach_precondition_flag(
        child_df, parent_df, join_fields_child, join_fields_parent, rule,
    )
    if reason is not None:
        return child_df.withColumn(val_col, F.lit(None).cast(StringType()))

    # Resolve the threshold. count_value may be a literal number OR the name of a
    # field (typically a PARENT field such as CNT_JOINT_NUMBER_OF_LIVES). When it
    # names a parent field that isn't already present, join it in.
    _COUNT_ALIAS = "_count_threshold_val"
    threshold_is_field = False
    if _is_number(count_value):
        threshold = F.lit(float(count_value))
    elif count_value in df.columns:
        threshold = F.col(count_value).cast("double")
        threshold_is_field = True
    elif parent_df is not None and count_value in parent_df.columns and join_fields_child:
        # Join the parent count field in.
        parent_renamed = parent_df
        rmap = {}
        for cf, pf in zip(join_fields_child, join_fields_parent):
            a = f"_cj_{pf}"
            parent_renamed = parent_renamed.withColumnRenamed(pf, a)
            rmap[cf] = a
        parent_renamed = parent_renamed.withColumnRenamed(count_value, _COUNT_ALIAS)
        slim = parent_renamed.select(*[F.col(a) for a in rmap.values()], F.col(_COUNT_ALIAS)).distinct()
        cond = [df[cf] == slim[rmap[cf]] for cf in join_fields_child]
        df = df.join(slim, cond, "left")
        for a in rmap.values():
            df = df.drop(a)
        threshold = F.col(_COUNT_ALIAS).cast("double")
        threshold_is_field = True
    else:
        # Unresolvable threshold — carry without flagging.
        return child_df.withColumn(val_col, F.lit(None).cast(StringType()))

    w = Window.partitionBy(*[F.col(g) for g in groupby_fields])

    # Row qualifies for counting if precondition holds AND:
    #   - filter_field + filter_values given -> filter_field value in filter_values
    #   - filter_field given but NO filter_values -> filter_field is non-blank
    #   - no filter_field -> every precondition-holding row counts
    qualifies = F.col("_precond_ok")
    if filter_field and filter_values:
        qualifies = qualifies & F.trim(F.col(filter_field)).isin(filter_values)
    elif filter_field:
        qualifies = qualifies & F.col(filter_field).isNotNull() & (F.trim(F.col(filter_field)) != F.lit(""))

    grp_count = F.sum(F.when(qualifies, F.lit(1)).otherwise(F.lit(0))).over(w)
    group_triggered = F.max(F.when(F.col("_precond_ok"), F.lit(1)).otherwise(F.lit(0))).over(w) == F.lit(1)

    violated = {
        "eq": grp_count != threshold, "neq": grp_count == threshold,
        "gt": grp_count <= threshold, "lt": grp_count >= threshold,
        "gte": grp_count < threshold, "lte": grp_count > threshold,
    }.get(op)
    if violated is None:
        return child_df.withColumn(val_col, F.lit(None).cast(StringType()))

    message = error_message or f"{severity}: group count fails {op} {count_value}"
    result = df.withColumn(
        val_col,
        F.when(group_triggered & violated, F.lit(message)).otherwise(F.lit(None).cast(StringType()))
    ).drop("_precond_ok")
    if threshold_is_field and _COUNT_ALIAS in result.columns:
        result = result.drop(_COUNT_ALIAS)
    return result


def apply_value_when_group_count(
    child_df: DataFrame,
    parent_df,
    child_table: str,
    target_field: str,
    expected_value: str,
    groupby_fields: list[str],
    count_operator: str,
    count_value: str,
    join_fields_child: list[str],
    join_fields_parent: list[str],
    rule: dict,
    severity: str = "SEVERE",
    error_message: str | None = None,
    val_col: str | None = None,
) -> DataFrame:
    """When a group's row count satisfies `count_operator`/`count_value`, every
    row in that group must have `target_field` == `expected_value`.

    Built for XR_CVG_007: "CVG_SEQUENCE_NUMBER = 1 WHEN COUNT(CVG_TYPE) = 1" —
    i.e. group Coverage by (policy + CVG_TYPE); for any group whose row count == 1,
    that single row's CVG_SEQUENCE_NUMBER must equal 1.

    Only rows in groups whose cardinality matches the count assertion AND whose
    precondition(s) hold are candidates; among those, rows whose target_field
    does not equal expected_value are flagged (per-row). Blank target values are
    NOT flagged (absence is handled by required/conditional rules elsewhere).
    Numeric comparison is used when both sides parse as numbers so "01" == 1.
    """
    val_col = val_col or f"VAL_{child_table}_{target_field}_VALUE_WHEN_COUNT"
    op = (count_operator or "").strip()
    count_value = str(count_value or "").strip()
    expected_value = str(expected_value or "").strip()
    if not groupby_fields or not target_field or not op or not count_value or expected_value == "":
        return child_df.withColumn(val_col, F.lit(None).cast(StringType()))

    df, reason = _attach_precondition_flag(
        child_df, parent_df, join_fields_child, join_fields_parent, rule,
    )
    if reason is not None:
        return child_df.withColumn(val_col, F.lit(None).cast(StringType()))

    # Threshold for the group-cardinality condition (literal only; the count is a
    # cardinality, not a data-driven field here).
    if not _is_number(count_value):
        return child_df.withColumn(val_col, F.lit(None).cast(StringType()))
    threshold = F.lit(float(count_value))

    w = Window.partitionBy(*[F.col(g) for g in groupby_fields])
    # Count precondition-holding rows in the group.
    grp_count = F.sum(F.when(F.col("_precond_ok"), F.lit(1)).otherwise(F.lit(0))).over(w)

    group_matches = {
        "eq": grp_count == threshold, "neq": grp_count != threshold,
        "gt": grp_count > threshold, "lt": grp_count < threshold,
        "gte": grp_count >= threshold, "lte": grp_count <= threshold,
    }.get(op)
    if group_matches is None:
        return child_df.withColumn(val_col, F.lit(None).cast(StringType()))

    tval = F.trim(F.col(target_field))
    is_blank = F.col(target_field).isNull() | (tval == F.lit(""))
    if _is_number(expected_value):
        mismatches = tval.cast("double") != F.lit(float(expected_value))
    else:
        mismatches = tval != F.lit(expected_value)

    message = error_message or (
        f"{severity}: {target_field} must equal {expected_value} "
        f"when group count {op} {count_value}"
    )
    result = df.withColumn(
        val_col,
        F.when(
            F.col("_precond_ok") & group_matches & ~is_blank & mismatches,
            F.lit(message),
        ).otherwise(F.lit(None).cast(StringType()))
    ).drop("_precond_ok")
    return result


def apply_unique_per_group(
    child_df: DataFrame,
    parent_df,
    child_table: str,
    groupby_fields: list[str],
    filter_field: str,
    join_fields_child: list[str],
    join_fields_parent: list[str],
    rule: dict,
    severity: str = "SEVERE",
    error_message: str | None = None,
    val_col: str | None = None,
) -> DataFrame:
    """`filter_field` must be unique within each group (`groupby_fields`).

    Only the DUPLICATE rows are flagged — i.e. rows whose (group + value) occurs
    more than once (counting only rows where the precondition holds). Blank
    values are not treated as duplicates. `rule` supplies the precondition
    columns (incl. an optional second one).
    """
    val_col = val_col or f"VAL_{child_table}_{filter_field}_UNIQUE"
    if not groupby_fields or not filter_field:
        return child_df.withColumn(val_col, F.lit(None).cast(StringType()))

    df, reason = _attach_precondition_flag(
        child_df, parent_df, join_fields_child, join_fields_parent, rule,
    )
    if reason is not None:
        return child_df.withColumn(val_col, F.lit(None).cast(StringType()))

    fval = F.trim(F.col(filter_field))
    is_blank = F.col(filter_field).isNull() | (fval == F.lit(""))

    # Count occurrences of each (group + value) among precondition-holding,
    # non-blank rows.
    w = Window.partitionBy(*[F.col(g) for g in groupby_fields], fval)
    dup_count = F.sum(
        F.when(F.col("_precond_ok") & ~is_blank, F.lit(1)).otherwise(F.lit(0))
    ).over(w)

    # A row is a duplicate if it qualifies (precondition holds, non-blank) and
    # its (group + value) appears more than once.
    this_row_qualifies = F.col("_precond_ok") & ~is_blank
    message = error_message or f"{severity}: {filter_field} must be unique within the group"

    result = df.withColumn(
        val_col,
        F.when(this_row_qualifies & (dup_count > F.lit(1)), F.lit(message))
         .otherwise(F.lit(None).cast(StringType()))
    ).drop("_precond_ok")
    return result


def apply_required(
    child_df: DataFrame,
    parent_df,
    child_table: str,
    target_field: str,
    join_fields_child: list[str],
    join_fields_parent: list[str],
    rule: dict,
    severity: str = "SEVERE",
    error_message: str | None = None,
    val_col: str | None = None,
) -> DataFrame:
    """DataFrame-level 'required': target_field must not be blank when the
    precondition(s) hold. Unlike the column-only compile_required, this variant
    can evaluate a precondition whose field lives on the PARENT table (joined in
    via _attach_precondition_flag). Used when a required rule references a parent
    field in its precondition.
    """
    val_col = val_col or f"VAL_{child_table}_{target_field}_REQUIRED"

    df, reason = _attach_precondition_flag(
        child_df, parent_df, join_fields_child, join_fields_parent, rule,
    )
    if reason is not None:
        return child_df.withColumn(val_col, F.lit(None).cast(StringType()))

    is_blank = F.col(target_field).isNull() | (F.trim(F.col(target_field)) == F.lit(""))
    message = error_message or f"{severity}: {target_field} is required"
    result = df.withColumn(
        val_col,
        F.when(F.col("_precond_ok") & is_blank, F.lit(message)).otherwise(F.lit(None).cast(StringType()))
    ).drop("_precond_ok")
    return result


def apply_conditional_blank(
    child_df: DataFrame,
    parent_df,
    child_table: str,
    target_field: str,
    join_fields_child: list[str],
    join_fields_parent: list[str],
    rule: dict,
    severity: str = "SEVERE",
    error_message: str | None = None,
    val_col: str | None = None,
) -> DataFrame:
    """DataFrame-level 'must be blank when precondition holds'. Like the
    column-only compile_conditional_null/blank, but can evaluate a precondition
    whose field lives on the PARENT table (joined in via
    _attach_precondition_flag). Used when the precondition references a parent
    field. Flags rows that are NON-blank while the precondition holds.
    """
    val_col = val_col or f"VAL_{child_table}_{target_field}_MUST_BLANK"

    df, reason = _attach_precondition_flag(
        child_df, parent_df, join_fields_child, join_fields_parent, rule,
    )
    if reason is not None:
        return child_df.withColumn(val_col, F.lit(None).cast(StringType()))

    is_not_blank = F.col(target_field).isNotNull() & (F.trim(F.col(target_field)) != F.lit(""))
    message = error_message or f"{severity}: {target_field} must be blank when condition applies"
    result = df.withColumn(
        val_col,
        F.when(F.col("_precond_ok") & is_not_blank, F.lit(message)).otherwise(F.lit(None).cast(StringType()))
    ).drop("_precond_ok")
    return result


def _precondition_needs_parent(rule: dict, child_columns) -> bool:
    """True if any precondition field is NOT on the child (so a parent join is
    required to evaluate the precondition)."""
    child_columns = set(child_columns)
    for fkey, okey in (
        ("precondition_field", "precondition_operator"),
        ("precondition_field_2", "precondition_operator_2"),
        ("precondition_field_3", "precondition_operator_3"),
    ):
        pf = (rule.get(fkey) or "").strip()
        op = (rule.get(okey) or "").strip()
        if pf and op and op != "none" and pf not in child_columns:
            return True
    return False


def apply_match_across_occurrences(
    child_df: DataFrame,
    parent_df: DataFrame,
    child_table: str,
    target_field: str,
    compare_field: str,
    groupby_fields: list[str],
    join_fields_child: list[str],
    join_fields_parent: list[str],
    rule: dict,
    severity: str = "SEVERE",
    error_message: str | None = None,
    val_col: str | None = None,
) -> DataFrame:
    """Within each group, at least ONE in-scope row's target_field must equal the
    parent's compare_field value. If none match, the in-scope rows are flagged.

    "In-scope" = rows where the rule's precondition(s) hold (e.g. CVG_TYPE=TERM
    and the joint-life gates). The parent compare value (e.g. CNT_SEX_CODE) is a
    single value per policy, joined in via the join keys. Precondition fields may
    live on the child or the parent.

    Only the in-scope rows of a failing group are flagged (rows that satisfy the
    precondition but where no occurrence in the group matched the parent value).
    """
    val_col = val_col or f"VAL_{child_table}_{target_field}_MATCH_ANY"
    if not groupby_fields or not compare_field or not join_fields_child or not join_fields_parent:
        return child_df.withColumn(val_col, F.lit(None).cast(StringType()))

    # Attach the precondition flag first (this also joins any parent-side
    # precondition fields the gate needs).
    df, reason = _attach_precondition_flag(
        child_df, parent_df, join_fields_child, join_fields_parent, rule,
    )
    if reason is not None:
        return child_df.withColumn(val_col, F.lit(None).cast(StringType()))

    # Join the parent compare value in under an alias. Build the slim parent
    # projection in ONE explicit select with fresh aliases (not chained
    # withColumnRenamed), which is robust when the compare field coincides with a
    # join key or when parent == child table in a self-referential rule.
    rename_map = {}
    proj = []
    for cf, pf in zip(join_fields_child, join_fields_parent):
        a = f"_mp_{pf}"
        rename_map[cf] = a
        proj.append(F.col(pf).alias(a))
    if compare_field in join_fields_parent:
        cmp_alias = f"_mp_{compare_field}"
    else:
        cmp_alias = f"_mp_cmp_{compare_field}"
        proj.append(F.col(compare_field).alias(cmp_alias))
    slim = parent_df.select(*proj).distinct()
    cond = [df[cf] == slim[rename_map[cf]] for cf in join_fields_child]
    df = df.join(slim, cond, "left")

    w = Window.partitionBy(*[F.col(g) for g in groupby_fields])

    # Does this row match the parent value AND is it in scope?
    in_scope = F.col("_precond_ok")
    this_matches = in_scope & (F.trim(F.col(target_field)) == F.trim(F.col(cmp_alias)))

    # Did ANY in-scope row in the group match?
    any_match_in_group = F.max(F.when(this_matches, F.lit(1)).otherwise(F.lit(0))).over(w) == F.lit(1)

    message = error_message or (
        f"{severity}: no {target_field} occurrence matches parent {compare_field} in the group"
    )
    result = df.withColumn(
        val_col,
        F.when(in_scope & ~any_match_in_group, F.lit(message)).otherwise(F.lit(None).cast(StringType()))
    )

    # Drop temp columns.
    for c in list(rename_map.values()) + [cmp_alias, "_precond_ok"]:
        result = result.drop(c)
    return result


def apply_match_through_intermediate(
    child_df: DataFrame,
    intermediate_df: DataFrame,
    compare_df: DataFrame,
    child_table: str,
    target_field: str,
    compare_field: str,
    join_child_to_inter_child: list[str],
    join_child_to_inter_inter: list[str],
    inter_filter_field: str,
    inter_filter_value: str,
    join_inter_to_cmp_inter: list[str],
    join_inter_to_cmp_cmp: list[str],
    cmp_filter_field: str = "",
    cmp_filter_value: str = "",
    severity: str = "SEVERE",
    error_message: str | None = None,
    val_col: str | None = None,
) -> DataFrame:
    """Two-hop match: target_field (on child_df) must equal compare_field, where
    the compare value is reached through a FILTERED intermediate table.

    Shape (generic; example = XR_CON_007):
      child (Contract)  --hop1 join-->  intermediate (Roles, filtered to the
      owner via inter_filter_field=inter_filter_value)  --hop2 join-->  compare
      (Address, optionally filtered via cmp_filter_field=cmp_filter_value) whose
      compare_field (ADD_STATE) must equal the child's target_field
      (CNT_RESIDENT_STATE).

    A child row is flagged SEVERE when a resolved compare value exists and does
    NOT equal target_field, OR when NO compare value can be resolved (the
    filtered intermediate/compare chain yields nothing) — i.e. the required
    related record is missing.

    Returns child_df with a new VAL_ column appended (no extra columns leak).
    """
    val_col = val_col or f"VAL_{child_table}_{target_field}_THRU"
    if (not join_child_to_inter_child or not join_child_to_inter_inter
            or not join_inter_to_cmp_inter or not join_inter_to_cmp_cmp
            or not compare_field):
        return child_df.withColumn(val_col, F.lit(None).cast(StringType()))

    # --- Build the resolved compare value per child, as a slim lookup ---
    # 1. Filter the intermediate table (e.g. Roles where ROL_PERSON_CODE = O).
    inter = intermediate_df
    if inter_filter_field:
        f = F.trim(F.col(inter_filter_field))
        inter = inter.filter(f == F.lit(inter_filter_value))

    # 2. Filter the compare table (e.g. Address where ADD_ADDRESS_TYPE = R).
    cmp = compare_df
    if cmp_filter_field and cmp_filter_value:
        cf = F.trim(F.col(cmp_filter_field))
        cmp = cmp.filter(cf == F.lit(cmp_filter_value))

    # 3. Hop-2 join: intermediate(owner) -> compare(resident address), pull the
    #    compare value. Alias everything to avoid collisions.
    cmp_val_alias = "_thru_cmpval"
    cmp_renamed = cmp.withColumnRenamed(compare_field, cmp_val_alias)
    ren_c = {}
    for icol, ccol in zip(join_inter_to_cmp_inter, join_inter_to_cmp_cmp):
        a = f"_thru_c_{ccol}"
        cmp_renamed = cmp_renamed.withColumnRenamed(ccol, a)
        ren_c[icol] = a
    cmp_slim = cmp_renamed.select(*[F.col(a) for a in ren_c.values()], F.col(cmp_val_alias)).distinct()
    h2_cond = [inter[icol] == cmp_slim[ren_c[icol]] for icol in join_inter_to_cmp_inter]
    inter_with_val = inter.join(cmp_slim, h2_cond, "left")
    for a in ren_c.values():
        inter_with_val = inter_with_val.drop(a)

    # 4. Reduce to (hop-1 intermediate keys -> resolved compare value), one per
    #    child key. Alias hop-1 intermediate keys.
    ren_i = {}
    lookup = inter_with_val
    for ccol, icol in zip(join_child_to_inter_child, join_child_to_inter_inter):
        a = f"_thru_i_{icol}"
        lookup = lookup.withColumnRenamed(icol, a)
        ren_i[ccol] = a
    lookup = lookup.select(*[F.col(a) for a in ren_i.values()], F.col(cmp_val_alias)).distinct()

    # 5. Hop-1 join child -> lookup.
    h1_cond = [child_df[ccol] == lookup[ren_i[ccol]] for ccol in join_child_to_inter_child]
    joined = child_df.join(lookup, h1_cond, "left")

    resolved = F.col(cmp_val_alias)
    target = F.trim(F.col(target_field))
    missing = resolved.isNull()
    mismatch = resolved.isNotNull() & (target != F.trim(resolved))
    message = error_message or (
        f"{severity}: {target_field} does not match the related {compare_field} "
        f"(or the related record is missing)"
    )
    result = joined.withColumn(
        val_col,
        F.when(missing | mismatch, F.lit(message)).otherwise(F.lit(None).cast(StringType()))
    )
    for a in list(ren_i.values()) + [cmp_val_alias]:
        if a in result.columns:
            result = result.drop(a)
    return result
