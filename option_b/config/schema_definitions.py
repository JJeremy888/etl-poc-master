"""Fixed schema constants for template validation.

These constants define the structure that all Template CSV files must conform to.
The engine validates loaded templates against these schemas before processing.
BAs edit template content; this schema is owned by the engineering team.
"""

# === Validation Rules Schema ===
VALIDATION_RULES_REQUIRED_COLUMNS = [
    "rule_id",
    "target_table",
    "target_field",
    "rule_type",
    "severity",
    "sequence",
]

VALIDATION_RULES_OPTIONAL_COLUMNS = [
    "param_1",
    "param_2",
    "allowed_values",
    "compare_field",
    "compare_table",
    "compare_column",
    "precondition_field",
    "precondition_operator",
    "precondition_value",
    "description",
]

# === Transformation Mappings Schema ===
TRANSFORMATION_MAPPINGS_REQUIRED_COLUMNS = [
    "mapping_id",
    "source_table",
    "source_field",
    "target_field",
    "transformation_type",
    "target_length",
    "target_data_type",
    "sequence",
]

TRANSFORMATION_MAPPINGS_OPTIONAL_COLUMNS = [
    "decimal_places",   # digits after the implied decimal point (COBOL Vnn); "0" for integers
    "signed",           # "Y" if PIC carries a leading S (sign), else "N"
    "comp3",            # "Y" if COMP-3 packed, else "N"
    "padding_rule",
    "default_value",
    "date_handling",
    "truncation_rule",
    "description",
]

# === Cross References Schema ===
# Cross-reference rules are maintained in a dedicated template (cross_references.csv),
# separate from field-level validation rules. They involve conditions across fields
# and/or tables, so they carry richer metadata (compare table/field, join keys,
# expected result) that does not fit the flat validation_rules schema.
CROSS_REFERENCES_REQUIRED_COLUMNS = [
    "xref_id",
    "table_name",
    "target_field",
    "rule_type",
    "severity",
]

CROSS_REFERENCES_OPTIONAL_COLUMNS = [
    "precondition_field",
    "precondition_operator",
    "precondition_value",
    # Optional SECOND / THIRD preconditions, combined with the first via precondition_logic.
    "precondition_field_2",
    "precondition_operator_2",
    "precondition_value_2",
    "precondition_field_3",
    "precondition_operator_3",
    "precondition_value_3",
    "precondition_logic",     # AND / OR (default AND) — how to combine the preconditions
    "expected_result",
    "compare_table",
    "compare_field",
    "join_child_fields",
    "join_parent_fields",
    # Aggregate columns (group-level checks: occurrence_count, values_present, ...).
    # Blank for non-aggregate rules. See RULES_TEMPLATE_GUIDE.md.
    "groupby_fields",         # pipe-delimited keys defining each group (e.g. one policy)
    "count_filter_field",     # field whose values are counted / must be present (also: compare-side filter field for match_through_intermediate)
    "count_filter_value",     # value(s) to count or require (pipe-delimited) (also: compare-side filter value)
    "count_operator",         # eq/neq/gt/lt/gte/lte for count-based assertions
    "count_value",            # numeric threshold for count-based assertions
    # Two-hop (match_through_intermediate) columns: target(this table) -> via a
    # FILTERED intermediate table -> compare a field on the compare table.
    "intermediate_table",       # middle-hop table (normalized to a code)
    "intermediate_filter_field",# field that selects the intermediate row (e.g. ROL_PERSON_CODE)
    "intermediate_filter_value",# value for that filter (e.g. O)
    "join_intermediate_fields", # hop-2 keys on the intermediate side (pipe-delimited)
    "join_compare_fields",      # hop-2 keys on the compare side (pipe-delimited, same order)
    "error_message",
    "active",
    "notes",
]

# === Table Dependencies Schema ===
TABLE_DEPENDENCIES_REQUIRED_COLUMNS = [
    "child_table",
    "parent_table",
    "join_fields_child",
    "join_fields_parent",
]

TABLE_DEPENDENCIES_OPTIONAL_COLUMNS: list[str] = []

# === Output Config Schema ===
OUTPUT_CONFIG_REQUIRED_COLUMNS = [
    "output_id",
    "adapter_type",
    "delivery_mechanism",
    "delivery_target",
    "include_severity",
]

OUTPUT_CONFIG_OPTIONAL_COLUMNS = [
    "description",
]

# === Registered Rule Types (field-level validation) ===
# The set of field-level validation rule types the engine can interpret.
# These apply to a single field within one table (see validation_rules.csv).
#
# TO ADD A NEW RULE TYPE:
#   1. Add the type name to this set.
#   2. Implement a compile_<type>(rule) -> Column function in
#      option_b/engine/presence_format_rules.py (or range_rules.py).
#   3. Register it in RULE_HANDLER_REGISTRY in option_b/engine/rule_compiler.py.
# No changes to the orchestrator or existing handlers are required.
REGISTERED_RULE_TYPES = frozenset([
    # --- Original POC types ---
    "not_blank",
    "exact_length",
    "max_length",
    "allowed_values",
    "valid_date",
    "numeric",
    "numeric_decimal",
    "date_greater_than",
    "date_lte",
    "numeric_min",
    "numeric_max",
    "conditional",
    "cross_field_conditional",
    "default_then_warn",
    # --- Added for Validation_Rules_Master.xlsx ---
    "numeric_range",            # value must fall within [param_1, param_2]
    "min_value",                # numeric value must be >= param_1
    "allowed_blank",            # declares blank is an allowed state for the field (optionality; never fails on its own)
    "conditional_null",         # field must be blank when a condition holds
    "conditional_blank",        # field must be blank when a condition holds (alias-style, product-driven)
    "exact_length_or_blank",    # exactly param_1 chars, or blank
    "numeric_string",           # digits-only content, preserved as string (leading zeros kept, no numeric cast)
    "project_defined_value",    # any user-defined value bounded by max length (param_1)
])

# === Registered Cross-Reference Rule Types ===
# These involve multiple fields and/or tables. They are maintained in a dedicated
# template (cross_references.csv) and applied by the validation orchestrator
# (some require parent/child DataFrame joins).
#
# TO ADD A NEW CROSS-REFERENCE TYPE:
#   1. Add the type name here.
#   2. Implement a handler in option_b/engine/cross_reference_rules.py
#      (or range_rules.py for pure date/value comparisons).
#   3. Register it in CROSS_REFERENCE_HANDLER_REGISTRY in rule_compiler.py, and
#      if it needs joins, wire it in validation_orchestrator.py.
REGISTERED_CROSS_REFERENCE_TYPES = frozenset([
    "cross_reference_exists",   # child key must exist in parent (referential integrity)
    "conditional",              # IF precondition THEN target must satisfy expected_result
    "required",                 # target field must not be blank (unconditional)
    "cross_table_match",        # target field must equal a field in another table (via join)
    "value_compare",            # compare target field to a literal/field using an operator
    "field_compare",            # compare two fields within the same record
    "date_greater_than",        # target date > compare date
    "date_less_than_equal",     # target date <= compare date
    "occurrence_check",         # multi-record existence check across tables
    # --- Aggregate (group-level) types ---
    "values_present",           # every value in count_filter_value must appear in the group
    "occurrence_count",         # count of (optionally filtered) rows in a group vs count_operator/value
    "unique_per_group",         # count_filter_field must be unique within each group
    "match_across_occurrences", # target_field must equal a parent value for >=1 in-scope row in the group
    "value_when_group_count",   # when a group's row count satisfies count_operator/count_value, target_field must equal expected_result
    "substring_blank",          # a first/last N-char substring of target_field is blank (advisory); count_operator=first|last, count_value=N
    "conditional_null",         # target must be blank when precondition holds (cross-table variant)
    "conditional_blank",        # target must be blank when precondition holds (cross-table variant)
    "match_through_intermediate", # target must equal a compare-table field reached via a filtered intermediate table (two-hop join)
])

# === Registered Transformation Types ===
# The set of transformation types the engine can interpret.
# Adding a genuinely new type requires a developer to implement a handler.
REGISTERED_TRANSFORMATION_TYPES = frozenset([
    "direct_copy",
    "date_split_year",
    "date_split_month",
    "date_split_day",
    "zip_first5",   # first 5 chars of a 10-char postal code (5-digit ZIP)
    "zip_plus4",    # chars 6-9 of a 10-char postal code (ZIP +4 extension)
    "constant",
    "space_fill",
    "zero_fill",
    "conditional_derived",
    "system_generated",
])

# === Valid Severity Levels ===
VALID_SEVERITIES = frozenset(["SEVERE", "WARNING"])

# === Valid Tables (POC scope) ===
VALID_TABLES = frozenset(["CNT", "CVG", "ROL", "ADD"])

# === Valid Data Types ===
VALID_DATA_TYPES = frozenset([
    "CHAR",
    "NUMERIC",
    "PACKED_DECIMAL",
    "BINARY_COMP",
    "GROUP",
])

# === Valid Output Adapter Types ===
VALID_ADAPTER_TYPES = frozenset(["positional_flat_file", "csv_file"])

# === Valid Delivery Mechanisms ===
VALID_DELIVERY_MECHANISMS = frozenset(["local_filesystem"])

# === Valid Precondition / Comparison Operators ===
# Used by conditional, value_compare, field_compare, and cross-reference rules.
VALID_PRECONDITION_OPERATORS = frozenset([
    "eq",
    "neq",
    "in",
    "not_in",
    "blank",
    "not_blank",
    # --- Added for Validation_Rules_Master.xlsx ---
    "gt",       # greater than
    "lt",       # less than
    "gte",      # greater than or equal
    "lte",      # less than or equal
    "exists",   # value exists in a referenced set/table (occurrence checks)
    "none",     # no precondition (rule is unconditional / self-contained)
])

# === Schema Registry (for programmatic access) ===
TEMPLATE_SCHEMAS = {
    "validation_rules": {
        "required_columns": VALIDATION_RULES_REQUIRED_COLUMNS,
        "optional_columns": VALIDATION_RULES_OPTIONAL_COLUMNS,
    },
    "transformation_mappings": {
        "required_columns": TRANSFORMATION_MAPPINGS_REQUIRED_COLUMNS,
        "optional_columns": TRANSFORMATION_MAPPINGS_OPTIONAL_COLUMNS,
    },
    "cross_references": {
        "required_columns": CROSS_REFERENCES_REQUIRED_COLUMNS,
        "optional_columns": CROSS_REFERENCES_OPTIONAL_COLUMNS,
    },
    "table_dependencies": {
        "required_columns": TABLE_DEPENDENCIES_REQUIRED_COLUMNS,
        "optional_columns": TABLE_DEPENDENCIES_OPTIONAL_COLUMNS,
    },
    "output_config": {
        "required_columns": OUTPUT_CONFIG_REQUIRED_COLUMNS,
        "optional_columns": OUTPUT_CONFIG_OPTIONAL_COLUMNS,
    },
}
