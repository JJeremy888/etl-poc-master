"""Validation Orchestrator — Orchestrate validation across all staging tables."""
import uuid
from pyspark.sql import SparkSession, DataFrame

from option_b.config.template_loader import load_template
from option_b.input.staging_reader import read_all_staging_tables
from option_b.engine.rule_compiler import (
    compile_all_rules,
    compile_cross_reference_rule,
    CROSS_REFERENCE_JOIN_TYPES,
    CROSS_REFERENCE_AGGREGATE_TYPES,
)
from option_b.engine.cross_reference_rules import (
    apply_cross_reference,
    apply_cross_table_match,
    apply_occurrence_check,
    apply_values_present,
    apply_occurrence_count,
    apply_unique_per_group,
    apply_value_when_group_count,
    apply_match_across_occurrences,
    apply_required,
    apply_conditional_blank,
    apply_match_through_intermediate,
    _precondition_needs_parent,
)
from option_b.engine.severity_classifier import classify_severity
from option_b.engine.dependency_graph import build_dependency_graph, persist_graph
from option_b.error.error_logger import log_errors


# How many sequential withColumn/join operations to accumulate before
# truncating the Spark logical plan. Sequential transformations on one
# DataFrame grow the (unresolved) logical plan; past ~50 layers Spark's
# analyzer slows dramatically or fails to resolve deep columns. Materializing
# every CHECKPOINT_INTERVAL operations bounds the plan size so runtime stays
# roughly linear in the number of rules regardless of table/data volume.
CHECKPOINT_INTERVAL = 25


def _truncate_plan(df: DataFrame) -> DataFrame:
    """Cut the logical-plan lineage so it can't grow unbounded.

    Uses localCheckpoint(eager=True) — materializes the current DataFrame to
    executor storage and returns a new DataFrame with a fresh (empty) lineage.
    No checkpoint directory is required (unlike checkpoint()). This is the
    standard remedy for 'plan explosion' from many sequential withColumn/join
    calls, and keeps the fix inside Spark (no collect-to-pandas).
    """
    try:
        return df.localCheckpoint(eager=True)
    except Exception as exc:  # pragma: no cover - defensive
        # If checkpointing is unavailable for any reason, fall back to cache()
        # + count() which still forces materialization and bounds recompute.
        print(f"[VALIDATE] localCheckpoint unavailable ({exc}); falling back to cache()")
        df = df.cache()
        df.count()
        return df


def determine_table_order(dependencies: list[dict]) -> list[str]:
    """Topological sort — parents processed before children.
    
    Raises ValueError if a cycle is detected.
    """
    # Build adjacency: child -> set of parents
    parents_of = {}  # table -> set of parent tables
    all_tables = set()
    
    for dep in dependencies:
        child = dep["child_table"]
        parent = dep["parent_table"]
        all_tables.add(child)
        all_tables.add(parent)
        if child not in parents_of:
            parents_of[child] = set()
        parents_of[child].add(parent)
        if parent not in parents_of:
            parents_of[parent] = set()
    
    # Kahn's algorithm for topological sort
    in_degree = {t: len(parents_of.get(t, set())) for t in all_tables}
    queue = [t for t in all_tables if in_degree[t] == 0]
    result = []
    
    while queue:
        queue.sort()  # Deterministic ordering
        node = queue.pop(0)
        result.append(node)
        
        for t in all_tables:
            if node in parents_of.get(t, set()):
                in_degree[t] -= 1
                if in_degree[t] == 0:
                    queue.append(t)
    
    if len(result) != len(all_tables):
        cycle_tables = all_tables - set(result)
        raise ValueError(f"Circular dependency detected among tables: {sorted(cycle_tables)}")
    
    return result


def apply_cross_references_for_table(
    df: DataFrame,
    table_name: str,
    cross_references: list[dict],
    available_dfs: dict[str, DataFrame],
) -> DataFrame:
    """Apply all cross-reference rules whose table_name matches this table.

    Two families are handled:
      * Column-producing types (required, value_compare, field_compare,
        date_greater_than, date_less_than_equal, conditional) are compiled into
        a Column and added via withColumn.
      * Join types (cross_table_match, occurrence_check) resolve a compare/parent
        table from `compare_table` and apply the appropriate join handler.

    Rules are skipped (with a message) when:
      * marked inactive (active column is a falsey string), or
      * they reference fields/tables not present in the available data.
    """
    applied_since_checkpoint = 0
    for xref in cross_references:
        if xref.get("table_name", "").strip() != table_name:
            continue

        # Honor an optional 'active' flag — blank/missing means active.
        active_raw = (xref.get("active") or "").strip().lower()
        if active_raw in ("false", "no", "n", "0", "inactive"):
            continue

        rule_type = (xref.get("rule_type") or "").strip()
        xref_id = xref.get("xref_id", "?")
        target_field = (xref.get("target_field") or "").strip()
        _cols_before = len(df.columns)

        if rule_type == "match_through_intermediate":
            # --- Two-hop: child -> filtered intermediate -> compare table ---
            severity = (xref.get("severity") or "SEVERE").strip()
            error_message = (xref.get("error_message") or "").strip() or None
            val_col = f"VAL_XREF_{xref_id}"
            compare_table = (xref.get("compare_table") or "").strip()
            inter_table = (xref.get("intermediate_table") or "").strip()
            inter_df = available_dfs.get(inter_table)
            cmp_df = available_dfs.get(compare_table)
            if inter_df is None or cmp_df is None:
                print(f"[VALIDATE] SKIP cross-ref {xref_id}: intermediate '{inter_table}' or compare '{compare_table}' table not available")
                continue
            j_ci_child = [f.strip() for f in (xref.get("join_child_fields") or "").split("|") if f.strip()]
            j_ci_inter = [f.strip() for f in (xref.get("join_parent_fields") or "").split("|") if f.strip()]
            j_ic_inter = [f.strip() for f in (xref.get("join_intermediate_fields") or "").split("|") if f.strip()]
            j_ic_cmp = [f.strip() for f in (xref.get("join_compare_fields") or "").split("|") if f.strip()]
            if not (j_ci_child and j_ci_inter and j_ic_inter and j_ic_cmp):
                print(f"[VALIDATE] SKIP cross-ref {xref_id}: match_through_intermediate needs both join hops")
                continue
            df = apply_match_through_intermediate(
                df, inter_df, cmp_df, table_name, target_field,
                (xref.get("compare_field") or "").strip(),
                j_ci_child, j_ci_inter,
                (xref.get("intermediate_filter_field") or "").strip(),
                (xref.get("intermediate_filter_value") or "").strip(),
                j_ic_inter, j_ic_cmp,
                (xref.get("count_filter_field") or "").strip(),
                (xref.get("count_filter_value") or "").strip(),
                severity, error_message, val_col,
            )
        elif rule_type in CROSS_REFERENCE_JOIN_TYPES:
            # --- Join-based cross-reference ---
            compare_table = (xref.get("compare_table") or "").strip()
            parent_df = available_dfs.get(compare_table)
            if parent_df is None:
                print(f"[VALIDATE] SKIP cross-ref {xref_id}: compare table "
                      f"'{compare_table}' not available")
                continue

            join_child = [f.strip() for f in (xref.get("join_child_fields") or "").split("|") if f.strip()]
            join_parent = [f.strip() for f in (xref.get("join_parent_fields") or "").split("|") if f.strip()]
            if not join_child or not join_parent:
                print(f"[VALIDATE] SKIP cross-ref {xref_id}: missing join fields")
                continue

            # Resilience guard: verify every field the join needs actually exists
            # on the relevant DataFrame BEFORE applying, so a single mistyped
            # field name (e.g. compare_field 'CNT_ISSUE' instead of
            # 'CNT_ISSUE_DATE') is skipped with a warning rather than aborting the
            # entire pipeline with an UNRESOLVED_COLUMN error.
            child_needed = [f for f in (join_child + ([target_field] if target_field else [])) if f]
            missing_child = [f for f in child_needed if f not in df.columns]
            parent_needed = list(join_parent)
            compare_field = (xref.get("compare_field") or "").strip()
            if rule_type == "cross_table_match" and compare_field:
                parent_needed = parent_needed + [compare_field]
            missing_parent = [f for f in parent_needed if f not in parent_df.columns]
            if missing_child or missing_parent:
                print(f"[VALIDATE] SKIP cross-ref {xref_id}: fields not in data "
                      f"(child missing {missing_child}, parent missing {missing_parent})")
                continue

            severity = (xref.get("severity") or "SEVERE").strip()
            error_message = (xref.get("error_message") or "").strip() or None
            val_col = f"VAL_XREF_{xref_id}"

            if rule_type == "cross_table_match":
                df = apply_cross_table_match(
                    df, parent_df, table_name, target_field, compare_field,
                    join_child, join_parent, severity, error_message, val_col,
                    rule=xref,
                )
            else:  # occurrence_check (and cross_reference_exists routed here)
                df = apply_occurrence_check(
                    df, parent_df, table_name, target_field,
                    join_child, join_parent, severity, error_message, val_col,
                )
        elif rule_type in CROSS_REFERENCE_AGGREGATE_TYPES:
            # --- Group-level aggregate cross-reference ---
            severity = (xref.get("severity") or "SEVERE").strip()
            error_message = (xref.get("error_message") or "").strip() or None
            val_col = f"VAL_XREF_{xref_id}"
            groupby = [f.strip() for f in (xref.get("groupby_fields") or "").split("|") if f.strip()]
            filter_field = (xref.get("count_filter_field") or "").strip()
            filter_values = [v.strip() for v in (xref.get("count_filter_value") or "").split("|") if v.strip()]
            join_child = [f.strip() for f in (xref.get("join_child_fields") or "").split("|") if f.strip()]
            join_parent = [f.strip() for f in (xref.get("join_parent_fields") or "").split("|") if f.strip()]
            # Parent only needed if the precondition field lives on it.
            compare_table = (xref.get("compare_table") or "").strip()
            parent_df = available_dfs.get(compare_table)
            pre_field = (xref.get("precondition_field") or "").strip()
            pre_op = (xref.get("precondition_operator") or "").strip()
            pre_val = (xref.get("precondition_value") or "").strip()

            if not groupby:
                print(f"[VALIDATE] SKIP cross-ref {xref_id}: missing groupby_fields")
                continue

            if rule_type == "values_present":
                if not filter_field or not filter_values:
                    print(f"[VALIDATE] SKIP cross-ref {xref_id}: values_present needs count_filter_field + count_filter_value")
                    continue
                df = apply_values_present(
                    df, parent_df, table_name, groupby, filter_field, filter_values,
                    join_child, join_parent, xref,
                    severity, error_message, val_col,
                )
            elif rule_type == "unique_per_group":
                if not filter_field:
                    print(f"[VALIDATE] SKIP cross-ref {xref_id}: unique_per_group needs count_filter_field")
                    continue
                df = apply_unique_per_group(
                    df, parent_df, table_name, groupby, filter_field,
                    join_child, join_parent, xref,
                    severity, error_message, val_col,
                )
            elif rule_type == "match_across_occurrences":
                compare_field = (xref.get("compare_field") or "").strip()
                if parent_df is None or not compare_field:
                    print(f"[VALIDATE] SKIP cross-ref {xref_id}: match_across_occurrences needs compare_table + compare_field")
                    continue
                df = apply_match_across_occurrences(
                    df, parent_df, table_name, target_field, compare_field,
                    groupby, join_child, join_parent, xref,
                    severity, error_message, val_col,
                )
            elif rule_type == "value_when_group_count":
                expected_value = (xref.get("expected_result") or "").strip()
                if not target_field or not expected_value or not (xref.get("count_operator") or "").strip() or not (xref.get("count_value") or "").strip():
                    print(f"[VALIDATE] SKIP cross-ref {xref_id}: value_when_group_count needs target_field + expected_result + count_operator + count_value")
                    continue
                df = apply_value_when_group_count(
                    df, parent_df, table_name, target_field, expected_value,
                    groupby,
                    (xref.get("count_operator") or "").strip(),
                    (xref.get("count_value") or "").strip(),
                    join_child, join_parent, xref,
                    severity, error_message, val_col,
                )
            else:  # occurrence_count
                df = apply_occurrence_count(
                    df, parent_df, table_name, groupby, filter_field, filter_values,
                    (xref.get("count_operator") or "").strip(),
                    (xref.get("count_value") or "").strip(),
                    join_child, join_parent, xref,
                    severity, error_message, val_col,
                )
        elif rule_type in ("required", "conditional_null", "conditional_blank") and _precondition_needs_parent(xref, df.columns):
            # A required / conditional-blank rule whose precondition references a
            # PARENT-table field needs a DataFrame-level join, so route it through
            # the apply_* variant rather than the column path (which only sees the
            # child DataFrame).
            severity = (xref.get("severity") or "SEVERE").strip()
            error_message = (xref.get("error_message") or "").strip() or None
            join_child = [f.strip() for f in (xref.get("join_child_fields") or "").split("|") if f.strip()]
            join_parent = [f.strip() for f in (xref.get("join_parent_fields") or "").split("|") if f.strip()]
            compare_table = (xref.get("compare_table") or "").strip()
            parent_df = available_dfs.get(compare_table)
            if parent_df is None or not join_child or not join_parent:
                print(f"[VALIDATE] SKIP cross-ref {xref_id}: parent-precondition rule needs compare_table + join fields")
                continue
            # Target field must still be on the child.
            if target_field and target_field not in df.columns:
                print(f"[VALIDATE] SKIP cross-ref {xref_id}: target field '{target_field}' not in data")
                continue
            if rule_type == "required":
                df = apply_required(
                    df, parent_df, table_name, target_field,
                    join_child, join_parent, xref,
                    severity, error_message, f"VAL_XREF_{xref_id}",
                )
            else:  # conditional_null / conditional_blank
                df = apply_conditional_blank(
                    df, parent_df, table_name, target_field,
                    join_child, join_parent, xref,
                    severity, error_message, f"VAL_XREF_{xref_id}",
                )
        else:
            # --- Column-producing cross-reference ---
            # Skip when a referenced field is absent from the DataFrame.
            fields_needed = [
                target_field,
                (xref.get("compare_field") or "").strip(),
                (xref.get("precondition_field") or "").strip(),
            ]
            missing = [f for f in fields_needed if f and f not in df.columns]
            if missing:
                print(f"[VALIDATE] SKIP cross-ref {xref_id}: fields not in data {missing}")
                continue

            # Tell literal-vs-field RHS detection which names are real columns,
            # so enum literals (e.g. "N", "F") are not mistaken for columns.
            xref = dict(xref)
            xref["_available_columns"] = list(df.columns)
            try:
                col_expr = compile_cross_reference_rule(xref)
                if col_expr is None:
                    continue
                candidate = df.withColumn(f"VAL_XREF_{xref_id}", col_expr)
                # Force Catalyst analysis NOW so an unresolved-column or other
                # binding error is raised here (and caught below) rather than
                # aborting the whole pipeline at a later action.
                candidate.schema  # noqa: B018 - triggers analysis
                df = candidate
            except Exception as exc:
                # NO SILENT SKIP: a rule the engine cannot interpret must surface
                # loudly, not vanish. Emit an explicit SEVERE "uninterpretable
                # rule" marker on every row so it appears in the results and the
                # error report, and log it. One bad rule must not abort the run.
                from pyspark.sql import functions as _F
                from pyspark.sql.types import StringType as _ST
                msg = f"UNINTERPRETABLE_RULE {xref_id}: {exc}"
                print(f"[VALIDATE] ERROR {msg}")
                df = df.withColumn(f"VAL_XREF_{xref_id}",
                                   _F.lit(f"SEVERE: {msg}").cast(_ST()))
                if len(df.columns) != _cols_before:
                    applied_since_checkpoint += 1
                    if applied_since_checkpoint >= CHECKPOINT_INTERVAL:
                        df = _truncate_plan(df)
                        applied_since_checkpoint = 0
                continue

        # Count this rule as applied only if it actually changed the frame
        # (a skipped/continue'd rule won't reach here). Truncate the plan every
        # CHECKPOINT_INTERVAL applied rules to keep the logical plan bounded.
        if len(df.columns) != _cols_before:
            applied_since_checkpoint += 1
            if applied_since_checkpoint >= CHECKPOINT_INTERVAL:
                df = _truncate_plan(df)
                applied_since_checkpoint = 0

    return df


def run_validation(
    spark: SparkSession,
    template: dict,
    staging_config: dict,
    output_dir: str = "output",
) -> dict[str, DataFrame]:
    """Execute full validation pass across all tables.
    
    Returns dict of {table_name: validated_DataFrame_with_severity}.
    """
    batch_run_id = str(uuid.uuid4())[:8]
    template_version = template.get("version", "unknown")
    
    # Determine table order
    dependencies = template["table_dependencies"]
    table_order = determine_table_order(dependencies)
    print(f"[VALIDATE] Table processing order: {table_order}")
    
    # Read all staging tables
    staging_dfs = read_all_staging_tables(spark, table_order, staging_config)
    
    # Build dependency lookup
    dep_lookup = {}
    for dep in dependencies:
        child = dep["child_table"]
        dep_lookup[child] = dep
    
    # Validate each table
    validated_dfs = {}
    all_dep_links = []
    
    for table_name in table_order:
        df = staging_dfs.get(table_name)
        if df is None or df.limit(1).count() == 0:
            print(f"[VALIDATE] Skipping {table_name} — empty or missing")
            continue
        
        print(f"[VALIDATE] Processing {table_name} — {df.count()} records")
        
        # Compile and apply field-level rules. Truncate the plan every
        # CHECKPOINT_INTERVAL columns so a table with many field rules does not
        # build an unbounded logical plan.
        compiled_rules = compile_all_rules(template["validation_rules"], table_name, df.columns)
        _applied = 0
        for val_col_name, col_expr in compiled_rules:
            df = df.withColumn(val_col_name, col_expr)
            _applied += 1
            if _applied % CHECKPOINT_INTERVAL == 0:
                df = _truncate_plan(df)
        
        # Apply cross-reference check if this is a child table
        if table_name in dep_lookup:
            dep = dep_lookup[table_name]
            parent_table = dep["parent_table"]
            parent_df = validated_dfs.get(parent_table)
            
            if parent_df is not None:
                join_child = dep["join_fields_child"].split("|")
                join_parent = dep["join_fields_parent"].split("|")
                
                df = apply_cross_reference(
                    df, parent_df, table_name,
                    join_child, join_parent, "SEVERE"
                )
                
                # Build dependency graph links
                links = build_dependency_graph(
                    df, table_name, parent_table,
                    join_child, join_parent,
                    batch_run_id, template_version
                )
                all_dep_links.extend(links)
        
        # Apply cross-reference rules (dedicated cross_references template).
        # validated_dfs holds parent/compare tables already processed this pass.
        cross_references = template.get("cross_references", [])
        if cross_references:
            df = apply_cross_references_for_table(
                df, table_name, cross_references, validated_dfs
            )
        
        # Classify severity
        df = classify_severity(df)
        
        # Log errors
        error_count = log_errors(df, table_name, template_version, batch_run_id, output_dir)
        
        # Print summary
        if "ROW_SEVERITY" in df.columns:
            try:
                counts_pdf = df.groupBy("ROW_SEVERITY").count().toPandas()
                count_dict = {row["ROW_SEVERITY"]: row["count"] for _, row in counts_pdf.iterrows()}
            except Exception:
                count_dict = {"CLEAN": "?", "WARNING": "?", "SEVERE": "?"}
            print(f"[VALIDATE] {table_name}: CLEAN={count_dict.get('CLEAN', 0)}, "
                  f"WARNING={count_dict.get('WARNING', 0)}, SEVERE={count_dict.get('SEVERE', 0)}")
        
        validated_dfs[table_name] = df
    
    # Persist dependency graph
    if all_dep_links:
        persist_graph(all_dep_links, output_dir)
    
    return validated_dfs
