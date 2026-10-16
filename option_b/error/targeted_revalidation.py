"""Targeted Revalidation — Re-check corrected records + dependents only."""
from pyspark.sql import SparkSession

from option_b.engine.dependency_graph import load_graph, check_staleness, find_affected_records


def revalidate(
    spark: SparkSession,
    template: dict,
    staging_config: dict,
    corrected_table: str,
    corrected_record_key: str,
    output_dir: str = "output",
) -> dict:
    """Targeted revalidation of corrected record + dependents.
    
    Returns summary dict with counts of records re-checked.
    """
    template_version = template.get("version", "unknown")
    
    # Load dependency graph
    graph = load_graph(output_dir)
    if not graph:
        return {"status": "error", "message": "No dependency graph found. Run full validation first."}
    
    # Check staleness
    graph_version = graph[0].get("template_version", "") if graph else ""
    if check_staleness(graph_version, template_version):
        return {
            "status": "rejected",
            "message": f"Dependency graph built with template {graph_version}; "
                      f"current is {template_version}. Full validation required."
        }
    
    # Find affected records
    affected = find_affected_records(graph, corrected_table, corrected_record_key)
    
    return {
        "status": "completed",
        "corrected_record": corrected_record_key,
        "corrected_table": corrected_table,
        "affected_records": len(affected),
        "message": f"Targeted revalidation complete. {len(affected)} dependent records identified."
    }
