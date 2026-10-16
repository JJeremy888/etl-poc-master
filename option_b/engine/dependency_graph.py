"""Dependency Graph — Build and persist dependency links for targeted revalidation."""
import json
from pathlib import Path
from pyspark.sql import DataFrame, functions as F


def build_dependency_graph(
    child_df: DataFrame,
    child_table: str,
    parent_table: str,
    join_fields_child: list[str],
    join_fields_parent: list[str],
    batch_run_id: str,
    template_version: str,
) -> list[dict]:
    """Build dependency links from cross-reference evaluation.
    
    Each child record creates one DependencyLink to its parent reference.
    """
    if not join_fields_child:
        return []
    
    links = []
    # Use toPandas for more reliable serialization on Windows
    try:
        rows_pdf = child_df.select(*join_fields_child).toPandas()
    except Exception:
        rows_pdf = None
    
    if rows_pdf is not None:
        for _, row in rows_pdf.iterrows():
            child_key = "|".join(str(row.get(f, "") or "") for f in join_fields_child)
            if child_key == 'nan':
                child_key = ""
            links.append({
                "batch_run_id": batch_run_id,
                "template_version": template_version,
                "source_table": child_table,
                "source_record_key": child_key,
                "referenced_table": parent_table,
                "referenced_field": "|".join(join_fields_parent),
                "reference_value": child_key,
            })
    
    return links


def persist_graph(links: list[dict], output_dir: str) -> None:
    """Write dependency graph links to JSONL file."""
    output_path = Path(output_dir) / "dependency_graph"
    output_path.mkdir(parents=True, exist_ok=True)
    
    graph_file = output_path / "links.jsonl"
    with open(graph_file, "w", encoding="utf-8") as f:
        for link in links:
            f.write(json.dumps(link) + "\n")


def load_graph(output_dir: str) -> list[dict]:
    """Load existing dependency graph."""
    graph_file = Path(output_dir) / "dependency_graph" / "links.jsonl"
    if not graph_file.exists():
        return []
    
    links = []
    with open(graph_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                links.append(json.loads(line))
    return links


def check_staleness(graph_template_version: str, active_template_version: str) -> bool:
    """Return True if graph is stale (version mismatch)."""
    return graph_template_version != active_template_version


def find_affected_records(graph: list[dict], corrected_table: str, corrected_record_key: str) -> list[dict]:
    """Find all records that depend on the corrected reference."""
    affected = []
    for link in graph:
        if link["referenced_table"] == corrected_table and link["reference_value"] == corrected_record_key:
            affected.append(link)
    return affected
