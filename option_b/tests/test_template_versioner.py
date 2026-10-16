"""Tests for template_versioner module."""

import json
import os
import shutil
import tempfile

import pytest

from option_b.config.template_versioner import (
    get_current_version,
    create_version,
    compare_versions,
)


@pytest.fixture
def versioned_templates(tmp_dir):
    """Create a minimal versioned template structure.
    
    The versioner expects:
    - template_dir points to a version dir (e.g., templates/v1)
    - versions.json sits at template_dir.parent (i.e., templates/)
    - create_version and compare_versions operate on the base dir (templates/)
    """
    tpl_dir = os.path.join(tmp_dir, "templates")
    os.makedirs(tpl_dir)

    # Create v1 directory with files
    v1_dir = os.path.join(tpl_dir, "v1")
    os.makedirs(v1_dir)
    with open(os.path.join(v1_dir, "validation_rules.csv"), "w") as f:
        f.write("rule_id,target_table,target_field,rule_type,severity,sequence\n")
        f.write("R1,CNT,FIELD,not_blank,SEVERE,1\n")
    with open(os.path.join(v1_dir, "transformation_mappings.csv"), "w") as f:
        f.write("mapping_id,source_table,source_field,target_field,transformation_type,target_length,target_data_type,sequence\n")

    # Create versions.json at the base templates dir
    versions_data = {
        "active_version": "v1",
        "versions": [
            {
                "version_id": "v1",
                "created_at": "2026-01-01T00:00:00Z",
                "description": "Initial version",
            }
        ],
    }
    with open(os.path.join(tpl_dir, "versions.json"), "w") as f:
        json.dump(versions_data, f)

    return tpl_dir


class TestGetCurrentVersion:
    def test_returns_active_version(self, versioned_templates):
        # get_current_version expects a version dir path (e.g., templates/v1)
        # It looks for versions.json at template_dir.parent
        v1_dir = os.path.join(versioned_templates, "v1")
        result = get_current_version(v1_dir)
        assert result["version_id"] == "v1"
        assert result["description"] == "Initial version"

    def test_missing_versions_json_raises(self, tmp_dir):
        # Pass a path whose parent has no versions.json
        fake_dir = os.path.join(tmp_dir, "no_versions", "v1")
        os.makedirs(fake_dir, exist_ok=True)
        with pytest.raises(FileNotFoundError):
            get_current_version(fake_dir)


class TestCreateVersion:
    def test_creates_new_version(self, versioned_templates):
        # create_version takes the base dir (templates/) and returns a version ID string
        new_id = create_version(versioned_templates, "Second version")
        assert new_id == "v2"

        # Verify directory was created
        v2_dir = os.path.join(versioned_templates, "v2")
        assert os.path.exists(v2_dir)
        assert os.path.exists(os.path.join(v2_dir, "validation_rules.csv"))

        # Verify versions.json updated
        with open(os.path.join(versioned_templates, "versions.json")) as f:
            data = json.load(f)
        assert data["active_version"] == "v2"
        assert len(data["versions"]) == 2
        assert data["versions"][1]["description"] == "Second version"


class TestCompareVersions:
    def test_compare_identical_versions(self, versioned_templates):
        # Create v2 (copy of v1)
        create_version(versioned_templates, "Copy")

        result = compare_versions(versioned_templates, "v1", "v2")
        assert result["v1"] == "v1"
        assert result["v2"] == "v2"
        # All files should be unchanged
        for filename, info in result["files"].items():
            assert info["status"] == "unchanged"

    def test_compare_with_modifications(self, versioned_templates):
        create_version(versioned_templates, "Modified")

        # Modify a file in v2
        v2_rules = os.path.join(versioned_templates, "v2", "validation_rules.csv")
        with open(v2_rules, "a") as f:
            f.write("R2,CVG,FIELD2,numeric,SEVERE,2\n")

        result = compare_versions(versioned_templates, "v1", "v2")
        modified = [f for f, info in result["files"].items() if info["status"] == "modified"]
        assert "validation_rules.csv" in modified

    def test_nonexistent_version_raises(self, versioned_templates):
        with pytest.raises(FileNotFoundError):
            compare_versions(versioned_templates, "v1", "v99")
