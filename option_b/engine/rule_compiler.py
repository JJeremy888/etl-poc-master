"""Rule Compiler — Translate template rules into PySpark Column expressions.

No hardcoded field names. All behavior driven by template metadata.
This module IS the interpreter — it reads rule definitions and produces Spark Columns.
"""
from pyspark.sql import Column, functions as F
from pyspark.sql.types import StringType

from option_b.engine.presence_format_rules import (
    compile_not_blank,
    compile_exact_length,
    compile_max_length,
    compile_allowed_values,
    compile_valid_date,
    compile_numeric,
    compile_numeric_decimal,
    compile_default_then_warn,
    compile_conditional,
    compile_cross_field_conditional,
    # Added for Validation_Rules_Master.xlsx
    compile_numeric_range,
    compile_min_value,
    compile_allowed_blank,
    compile_conditional_null,
    compile_conditional_blank,
    compile_exact_length_or_blank,
    compile_numeric_string,
    compile_project_defined_value,
)
from option_b.engine.range_rules import (
    compile_date_greater_than,
    compile_date_lte,
    # Added for Validation_Rules_Master.xlsx
    compile_date_less_than_equal,
)
from option_b.engine.cross_reference_rules import (
    # Column-producing cross-reference handlers (single-record)
    compile_required,
    compile_value_compare,
    compile_field_compare,
    compile_substring_blank,
    compile_xref_conditional,
)

# =============================================================================
# Field-level rule registry — maps rule_type to a Column-producing compiler.
#
# TO ADD A NEW FIELD-LEVEL RULE TYPE:
#   1. Register the type name in REGISTERED_RULE_TYPES (schema_definitions.py).
#   2. Implement compile_<type>(rule) -> Column in presence_format_rules.py
#      (or range_rules.py).
#   3. Add the mapping here. No other file needs to change.
# =============================================================================
RULE_HANDLER_REGISTRY: dict[str, callable] = {
    # --- Original POC types ---
    "not_blank": compile_not_blank,
    "exact_length": compile_exact_length,
    "max_length": compile_max_length,
    "allowed_values": compile_allowed_values,
    "valid_date": compile_valid_date,
    "numeric": compile_numeric,
    "numeric_decimal": compile_numeric_decimal,
    "default_then_warn": compile_default_then_warn,
    "date_greater_than": compile_date_greater_than,
    "date_lte": compile_date_lte,
    "conditional": compile_conditional,
    "cross_field_conditional": compile_cross_field_conditional,
    # --- Added for Validation_Rules_Master.xlsx ---
    "numeric_range": compile_numeric_range,
    "min_value": compile_min_value,
    "allowed_blank": compile_allowed_blank,
    "conditional_null": compile_conditional_null,
    "conditional_blank": compile_conditional_blank,
    "exact_length_or_blank": compile_exact_length_or_blank,
    "numeric_string": compile_numeric_string,
    "project_defined_value": compile_project_defined_value,
}

# =============================================================================
# Cross-reference rule registry — for rules in cross_references.csv.
#
# Split into two families:
#   * COLUMN handlers: single-record checks that produce a Column. These can be
#     compiled and applied like field-level rules (via compile_cross_reference_rule).
#   * JOIN handlers ("cross_table_match", "occurrence_check", "cross_reference_exists"):
#     require parent/child DataFrame joins and are applied by the orchestrator,
#     NOT compiled here. They are listed in CROSS_REFERENCE_JOIN_TYPES so callers
#     can route them to the appropriate apply_* function.
#
# TO ADD A NEW CROSS-REFERENCE TYPE:
#   1. Register it in REGISTERED_CROSS_REFERENCE_TYPES (schema_definitions.py).
#   2. If single-record: implement compile_<type> and add it below.
#      If it needs joins: implement apply_<type> in cross_reference_rules.py,
#      add its name to CROSS_REFERENCE_JOIN_TYPES, and wire it in the orchestrator.
# =============================================================================
CROSS_REFERENCE_HANDLER_REGISTRY: dict[str, callable] = {
    "required": compile_required,
    "value_compare": compile_value_compare,
    "field_compare": compile_field_compare,
    "substring_blank": compile_substring_blank,
    "date_greater_than": compile_date_greater_than,
    "date_less_than_equal": compile_date_less_than_equal,
    # Cross-reference conditionals use a dedicated handler that understands the
    # cross_references.csv shape (precondition + optional simple Expected Result,
    # incl. the advisory "empty Expected Result = warn when precondition holds").
    "conditional": compile_xref_conditional,
    # "must be blank when precondition holds" — column path for CHILD-only
    # preconditions; a parent-side precondition is routed to apply_conditional_blank
    # by the orchestrator.
    "conditional_null": compile_conditional_null,
    "conditional_blank": compile_conditional_blank,
}

# Cross-reference types that require DataFrame joins (handled by the orchestrator).
CROSS_REFERENCE_JOIN_TYPES: frozenset = frozenset([
    "cross_reference_exists",
    "cross_table_match",
    "occurrence_check",
    "match_through_intermediate",
])

# Cross-reference types evaluated over a GROUP of rows (group-by aggregates).
# Applied by the orchestrator via apply_values_present / apply_occurrence_count.
CROSS_REFERENCE_AGGREGATE_TYPES: frozenset = frozenset([
    "values_present",
    "occurrence_count",
    "unique_per_group",
    "match_across_occurrences",
    "value_when_group_count",
])


def compile_cross_reference_rule(rule: dict) -> Column | None:
    """Compile a single-record cross-reference rule into a Column.

    Returns None for join-based types (they are applied by the orchestrator) and
    for unrecognized types (skipped with a warning).
    """
    rule_type = (rule.get("rule_type") or "").strip()

    if rule_type in CROSS_REFERENCE_JOIN_TYPES or rule_type in CROSS_REFERENCE_AGGREGATE_TYPES:
        return None

    handler = CROSS_REFERENCE_HANDLER_REGISTRY.get(rule_type)
    if handler is None:
        print(f"[VALIDATE] WARNING: Skipping cross-reference {rule.get('xref_id', '?')} — unrecognized type '{rule_type}'")
        return None

    return handler(rule)


def compile_rule(rule: dict) -> Column | None:
    """Translate a single validation rule dict into a PySpark Column expression.

    Returns None for unrecognized rule types (they are skipped with a warning).
    """
    rule_type = rule.get("rule_type", "").strip()

    # Skip cross_reference (handled separately)
    if rule_type in ("cross_reference_exists",):
        return None

    handler = RULE_HANDLER_REGISTRY.get(rule_type)
    if handler is None:
        print(f"[VALIDATE] WARNING: Skipping rule {rule.get('rule_id', '?')} — unrecognized type '{rule_type}'")
        return None

    return handler(rule)


def compile_all_rules(rules: list[dict], table_name: str, available_columns: list[str] | None = None) -> list[tuple[str, Column]]:
    """Compile all rules for a given table into (VAL_column_name, Column) pairs.

    Filters rules to only those targeting the specified table.
    Skips conditional and cross_reference rules (handled elsewhere).
    Skips rules referencing fields not in available_columns (if provided).
    """
    compiled = []

    # A field is "mandatory" only if it has an explicit presence-requiring rule
    # (not_blank / required) for THIS table. Blank/optional is governed by the
    # source sheet (validation-principles.md Principle 3) — a format rule such as
    # exact_length must NOT fail a blank value when the field is optional. We
    # compute the mandatory set here (where all the table's rules are visible)
    # and pass a per-field `_blank_optional` flag into each format handler.
    mandatory_fields = set()
    for r in rules:
        if r.get("target_table", "").strip() != table_name:
            continue
        if r.get("rule_type", "").strip() in ("not_blank", "required"):
            f = r.get("target_field", "").strip()
            if f:
                mandatory_fields.add(f)

    for rule in rules:
        if rule.get("target_table", "").strip() != table_name:
            continue

        rule_type = rule.get("rule_type", "").strip()

        # Skip cross_reference — handled separately
        if rule_type in ("cross_reference_exists",):
            continue

        # Skip rules for fields that don't exist in the DataFrame
        field = rule.get("target_field", "").strip()
        if available_columns and field and field not in available_columns:
            print(f"[VALIDATE] SKIP rule {rule.get('rule_id', '?')}: field '{field}' not in staging data")
            continue

        # For range rules, also check compare_field
        compare_field = rule.get("compare_field", "").strip()
        if available_columns and compare_field and compare_field not in available_columns:
            print(f"[VALIDATE] SKIP rule {rule.get('rule_id', '?')}: compare field '{compare_field}' not in staging data")
            continue

        # For conditional rules, also check precondition_field
        precondition_field = rule.get("precondition_field", "").strip()
        if available_columns and precondition_field and precondition_field not in available_columns:
            print(f"[VALIDATE] SKIP rule {rule.get('rule_id', '?')}: precondition field '{precondition_field}' not in staging data")
            continue

        # Tell format handlers whether blank is acceptable for this field:
        # optional unless the field has an explicit not_blank/required rule.
        rule = dict(rule)  # shallow copy so we don't mutate the caller's dict
        rule["_blank_optional"] = field not in mandatory_fields

        col_expr = compile_rule(rule)
        if col_expr is None:
            continue

        # Determine VAL_ column name
        rule_id = rule.get("rule_id", "").strip()

        # Use rule_id suffix for conditional rules to avoid column name collision
        if rule_type in ("conditional", "cross_field_conditional"):
            val_col_name = f"VAL_{field}_{rule_id}"
        # Use rule_id suffix for comparison rules to avoid column name collision
        elif rule_id.endswith("b"):
            val_col_name = f"VAL_{field}_{rule_type}"
        else:
            val_col_name = f"VAL_{field}"

        compiled.append((val_col_name, col_expr))

    return compiled
