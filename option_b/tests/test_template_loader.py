"""Tests for template_loader module.

Validates: Requirements 1.2 — Schema Rejection Property
"""

import os
import tempfile
import shutil

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from pyspark.sql import SparkSession

from option_b.config.template_loader import load_template, _validate_schema as validate_schema
from option_b.config.schema_definitions import (
    VALIDATION_RULES_REQUIRED_COLUMNS,
    TRANSFORMATION_MAPPINGS_REQUIRED_COLUMNS,
    TABLE_DEPENDENCIES_REQUIRED_COLUMNS,
    OUTPUT_CONFIG_REQUIRED_COLUMNS,
    REGISTERED_RULE_TYPES,
)


class TestValidateSchema:
    """Unit tests for schema validation."""

    def test_valid_validation_rules(self):
        """Valid row dict with all required columns passes."""
        rows = [{"rule_id": "R1", "target_table": "CNT", "target_field": "CNT_FIELD",
                 "rule_type": "not_blank", "severity": "SEVERE", "sequence": "1"}]
        # Should not raise
        validate_schema(rows, "validation_rules", "test.csv")

    def test_missing_column_raises(self):
        """Row dict missing a required column raises ValueError."""
        rows = [{"rule_id": "R1", "target_table": "CNT", "target_field": "CNT_FIELD",
                 "rule_type": "not_blank", "severity": "SEVERE"}]
        # Missing 'sequence'
        with pytest.raises(ValueError, match="Missing required columns"):
            validate_schema(rows, "validation_rules", "test.csv")

    def test_empty_rows_passes(self):
        """Empty rows list is valid (no rules defined yet)."""
        validate_schema([], "validation_rules", "test.csv")


class TestLoadTemplate:
    """Unit tests for load_template function."""

    def test_load_real_template(self, template_dir):
        """Load real template files and verify structure."""
        if template_dir is None:
            pytest.skip("Template directory not available")

        result = load_template(template_dir)
        assert "validation_rules" in result
        assert "transformation_mappings" in result
        assert "table_dependencies" in result
        assert "output_config" in result
        assert "version" in result
        assert result["version"] == "v1"

    def test_missing_directory_raises(self):
        """Non-existent directory raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_template("/nonexistent/path")

    def test_unregistered_rule_type_warns(self, tmp_dir, capsys):
        """Template with unregistered rule_type logs a warning (does not raise)."""
        # Create minimal template with bad rule type
        tpl_dir = os.path.join(tmp_dir, "bad_template")
        os.makedirs(tpl_dir)

        # Write validation_rules with bad type
        with open(os.path.join(tpl_dir, "validation_rules.csv"), "w") as f:
            f.write("rule_id,target_table,target_field,rule_type,severity,sequence\n")
            f.write("R1,CNT,FIELD,FAKE_RULE_TYPE,SEVERE,1\n")

        # Write other required files (minimal valid)
        with open(os.path.join(tpl_dir, "transformation_mappings.csv"), "w") as f:
            f.write("mapping_id,source_table,source_field,target_field,transformation_type,target_length,target_data_type,sequence\n")
            f.write("M1,CNT,F1,T1,direct_copy,5,CHAR,1\n")

        with open(os.path.join(tpl_dir, "table_dependencies.csv"), "w") as f:
            f.write("child_table,parent_table,join_fields_child,join_fields_parent\n")
            f.write("CVG,CNT,CVG_CO|CVG_POL,CNT_CO|CNT_POL\n")

        with open(os.path.join(tpl_dir, "output_config.csv"), "w") as f:
            f.write("output_id,adapter_type,delivery_mechanism,delivery_target,include_severity\n")
            f.write("OUT1,positional_flat_file,local_filesystem,out.txt,CLEAN|WARNING\n")

        # Write versions.json in parent
        import json
        with open(os.path.join(tmp_dir, "versions.json"), "w") as f:
            json.dump({"active_version": "bad_template", "versions": [{"version_id": "bad_template", "created_at": "", "description": ""}]}, f)

        # Should NOT raise — just warns
        result = load_template(tpl_dir)
        captured = capsys.readouterr()
        assert "unrecognized" in captured.out.lower() or "FAKE_RULE_TYPE" in captured.out


class TestSchemaRejectionProperty:
    """**Validates: Requirements 1.2** — Schema Rejection Property.

    Property: Any template DataFrame missing at least one required column
    must be rejected with a ValueError.
    """

    @given(
        columns_to_drop=st.lists(
            st.sampled_from(VALIDATION_RULES_REQUIRED_COLUMNS),
            min_size=1,
            max_size=3,
            unique=True,
        )
    )
    @settings(max_examples=100)
    def test_dropping_required_columns_always_rejected(self, columns_to_drop):
        """Dropping any required column(s) from validation_rules must raise ValueError."""
        all_cols = list(VALIDATION_RULES_REQUIRED_COLUMNS)
        remaining = [c for c in all_cols if c not in columns_to_drop]

        # Must have at least one column remaining to create a row
        assume(len(remaining) > 0)

        rows = [{col: "x" for col in remaining}]

        with pytest.raises(ValueError, match="Missing required columns"):
            validate_schema(rows, "validation_rules", "test.csv")
