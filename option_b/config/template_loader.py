"""Template Loader — Load, schema-validate, and return parsed Template data.

This is the ONLY module that opens template CSV files.
Raises ValueError on schema violation. Raises FileNotFoundError if template missing.
"""
import csv
import json
from pathlib import Path
from typing import Any

from option_b.config.schema_definitions import (
    TEMPLATE_SCHEMAS,
    REGISTERED_RULE_TYPES,
    REGISTERED_CROSS_REFERENCE_TYPES,
    REGISTERED_TRANSFORMATION_TYPES,
    VALID_SEVERITIES,
    VALID_TABLES,
)


def load_template(template_dir: str) -> dict[str, Any]:
    """Load all template sections, validate schemas, return parsed template dict.
    
    Returns:
        {
            "validation_rules": list[dict],
            "cross_references": list[dict],
            "transformation_mappings": list[dict],
            "output_config": list[dict],
            "table_dependencies": list[dict],
            "version": str,
            "version_timestamp": str,
        }
    """
    template_path = Path(template_dir)
    if not template_path.exists():
        raise FileNotFoundError(f"Template directory not found: {template_dir}")

    # Load versions.json from parent
    versions_path = template_path.parent / "versions.json"
    if not versions_path.exists():
        raise FileNotFoundError(f"versions.json not found at: {versions_path}")
    
    with open(versions_path, "r", encoding="utf-8") as f:
        versions_data = json.load(f)
    
    active_version = versions_data.get("active_version", "")
    version_info = next(
        (v for v in versions_data.get("versions", []) if v["version_id"] == active_version),
        {"version_id": active_version, "created_at": ""}
    )

    # Load each section
    sections = {}
    file_map = {
        "validation_rules": "validation_rules.csv",
        "transformation_mappings": "transformation_mappings.csv",
        "table_dependencies": "table_dependencies.csv",
        "output_config": "output_config.csv",
    }

    for section_name, filename in file_map.items():
        filepath = template_path / filename
        if not filepath.exists():
            raise FileNotFoundError(
                f"Template file not found: {filepath}\n"
                f"Please ensure {template_dir} contains {filename}."
            )
        rows = _read_csv(filepath)
        _validate_schema(rows, section_name, filepath)
        sections[section_name] = rows

    # Cross-references are optional (dedicated template). Missing file = no cross-refs,
    # which keeps older template directories backward-compatible.
    xref_path = template_path / "cross_references.csv"
    if xref_path.exists():
        xref_rows = _read_csv(xref_path)
        _validate_schema(xref_rows, "cross_references", xref_path)
        sections["cross_references"] = xref_rows
        _validate_cross_reference_types(xref_rows)
    else:
        print("[TEMPLATE] No cross_references.csv found — proceeding with no cross-reference rules.")
        sections["cross_references"] = []

    # Additional validation: check rule_types and transformation_types are registered
    _validate_rule_types(sections["validation_rules"])
    _validate_transformation_types(sections["transformation_mappings"])

    return {
        **sections,
        "version": version_info["version_id"],
        "version_timestamp": version_info.get("created_at", ""),
    }


def _read_csv(filepath: Path) -> list[dict]:
    """Read a CSV file into a list of dicts."""
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return list(reader)


def _validate_schema(rows: list[dict], section_name: str, filepath: Path) -> None:
    """Validate that required columns are present in the CSV."""
    if not rows:
        return  # Empty file is valid (e.g., no rules defined yet)
    
    schema = TEMPLATE_SCHEMAS.get(section_name)
    if not schema:
        return
    
    required = set(schema["required_columns"])
    actual = set(rows[0].keys())
    missing = required - actual
    
    if missing:
        raise ValueError(
            f"Schema validation failed for {section_name} ({filepath}).\n"
            f"Missing required columns: {sorted(missing)}\n"
            f"Actual columns: {sorted(actual)}"
        )


def _validate_rule_types(rules: list[dict]) -> None:
    """Warn about unregistered rule types (skip them, don't crash)."""
    warnings = []
    for rule in rules:
        rule_type = rule.get("rule_type", "").strip()
        if rule_type and rule_type not in REGISTERED_RULE_TYPES:
            warnings.append(f"  Rule {rule.get('rule_id', '?')}: unrecognized rule_type '{rule_type}' — will be skipped")
    if warnings:
        print(f"[TEMPLATE] WARNING: {len(warnings)} rules reference unrecognized rule_types:")
        for w in warnings:
            print(w)


def _validate_cross_reference_types(xrefs: list[dict]) -> None:
    """Warn about unregistered cross-reference rule types (skip them, don't crash)."""
    warnings = []
    for x in xrefs:
        rule_type = x.get("rule_type", "").strip()
        if rule_type and rule_type not in REGISTERED_CROSS_REFERENCE_TYPES:
            warnings.append(
                f"  Cross-reference {x.get('xref_id', '?')}: unrecognized rule_type "
                f"'{rule_type}' — will be skipped"
            )
    if warnings:
        print(f"[TEMPLATE] WARNING: {len(warnings)} cross-references reference unrecognized rule_types:")
        for w in warnings:
            print(w)


def _validate_transformation_types(mappings: list[dict]) -> None:
    """Warn about unregistered transformation types."""
    warnings = []
    for m in mappings:
        xtype = m.get("transformation_type", "").strip()
        if xtype and xtype not in REGISTERED_TRANSFORMATION_TYPES:
            warnings.append(f"  Mapping {m.get('mapping_id', '?')}: unrecognized transformation_type '{xtype}' — will be skipped")
    if warnings:
        print(f"[TEMPLATE] WARNING: {len(warnings)} mappings reference unrecognized transformation_types:")
        for w in warnings:
            print(w)
