"""Execution Audit Trail — Record and query execution metadata."""
import json
from datetime import datetime, timezone
from pathlib import Path


def record_audit_trail(
    run_id: str,
    template_version: str,
    trigger_type: str,
    tables_processed: list[str],
    record_counts: dict,
    outputs_produced: list[str],
    output_dir: str = "output",
) -> str:
    """Write execution audit trail as JSON."""
    audit_path = Path(output_dir)
    audit_path.mkdir(parents=True, exist_ok=True)
    
    trail = {
        "run_id": run_id,
        "template_version": template_version,
        "trigger_type": trigger_type,
        "start_time": datetime.now(timezone.utc).isoformat(),
        "tables_processed": tables_processed,
        "record_counts": record_counts,
        "outputs_produced": outputs_produced,
        "exit_code": 0,
    }
    
    audit_file = audit_path / "audit_trail.json"
    with open(audit_file, "w", encoding="utf-8") as f:
        json.dump(trail, f, indent=2)
    
    print(f"[AUDIT] Execution audit trail -> {audit_file}")
    return str(audit_file)


def query_record_trace(record_key: str, table_name: str, output_dir: str = "output") -> list[dict]:
    """Query per-record trace from error logs."""
    from option_b.error.error_logger import query_errors
    return query_errors(output_dir, {"record_key": record_key, "table_name": table_name})
