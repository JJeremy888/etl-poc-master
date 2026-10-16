"""Template Versioner — Track, compare, and retrieve template versions."""
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def get_current_version(template_dir: str) -> dict[str, Any]:
    """Return the currently active template version info."""
    versions_path = Path(template_dir).parent / "versions.json"
    if not versions_path.exists():
        raise FileNotFoundError(f"versions.json not found at: {versions_path}")
    
    with open(versions_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    active_id = data.get("active_version", "")
    for v in data.get("versions", []):
        if v["version_id"] == active_id:
            return v
    
    return {"version_id": active_id, "created_at": "", "description": ""}


def create_version(template_base_dir: str, description: str = "") -> str:
    """Create a new version snapshot. Returns the new version ID."""
    base = Path(template_base_dir)
    versions_path = base / "versions.json"
    
    with open(versions_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Determine next version number
    existing_ids = [v["version_id"] for v in data.get("versions", [])]
    max_num = max((int(vid.replace("v", "")) for vid in existing_ids if vid.startswith("v")), default=0)
    new_id = f"v{max_num + 1}"
    
    # Copy current active version to new version directory
    active_dir = base / data["active_version"]
    new_dir = base / new_id
    if active_dir.exists():
        shutil.copytree(active_dir, new_dir)
    
    # Update versions.json
    new_entry = {
        "version_id": new_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "description": description,
    }
    data["versions"].append(new_entry)
    data["active_version"] = new_id
    
    with open(versions_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    
    return new_id


def compare_versions(template_base_dir: str, v1_id: str, v2_id: str) -> dict[str, Any]:
    """Compare two template versions and return a diff summary."""
    base = Path(template_base_dir)
    v1_dir = base / v1_id
    v2_dir = base / v2_id
    
    if not v1_dir.exists():
        raise FileNotFoundError(f"Version directory not found: {v1_dir}")
    if not v2_dir.exists():
        raise FileNotFoundError(f"Version directory not found: {v2_dir}")
    
    diffs = {}
    for csv_file in v1_dir.glob("*.csv"):
        v2_file = v2_dir / csv_file.name
        if not v2_file.exists():
            diffs[csv_file.name] = {"status": "removed_in_v2"}
            continue
        
        with open(csv_file, "r", encoding="utf-8-sig") as f:
            v1_content = f.read()
        with open(v2_file, "r", encoding="utf-8-sig") as f:
            v2_content = f.read()
        
        if v1_content != v2_content:
            diffs[csv_file.name] = {"status": "modified"}
        else:
            diffs[csv_file.name] = {"status": "unchanged"}
    
    # Check for files added in v2
    for csv_file in v2_dir.glob("*.csv"):
        if csv_file.name not in diffs:
            diffs[csv_file.name] = {"status": "added_in_v2"}
    
    return {"v1": v1_id, "v2": v2_id, "files": diffs}
