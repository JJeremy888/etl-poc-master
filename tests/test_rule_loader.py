# WARNING: These tests target the DEPRECATED codebase (_deprecated_src_do_not_use/). See option_b/tests/ for active tests.
"""Unit tests for rule_loader.py."""

from pathlib import Path

import pytest

from _deprecated_src_do_not_use.rule_loader import load, RULES_FILE_PATH


# All 32 expected CNT field names
EXPECTED_CNT_FIELDS = [
    "CNT_ISSUE_SYSTEM", "CNT_COMPANY_CODE", "CNT_POLICY_NUMBER",
    "CNT_PRODUCT_TYPE", "CNT_POLICY_PLAN_CODE", "CNT_BASE_PLAN_CODE",
    "CNT_POLICY_CODE", "CNT_ISSUE_COUNTRY", "CNT_ISSUE_STATE",
    "CNT_RESIDENT_STATE", "CNT_POLICY_STATUS", "CNT_ISSUE_AGE",
    "CNT_ISSUE_DATE", "CNT_STATUS_DATE", "CNT_MATURE_EXPIRE_DATE",
    "CNT_APPLICATION_DATE", "CNT_PARTICIPATION_STATUS", "CNT_GUAR_PAR_STATUS",
    "CNT_NFO_OPTION", "CNT_SEX_CODE", "CNT_JOINT_LIFE_INDICATOR",
    "CNT_JOINT_NUMBER_OF_LIVES", "CNT_JOINT_RATE_AGE",
    "CNT_JOINT_RATE_AGE_REASON_CODE", "CNT_PAYUP_DATE",
    "CNT_QUALIFICATION_CODE", "CNT_PLAN_OPTION",
    "CNT_GRACE_EXPIRY_DATE", "CNT_SERV_AGENT", "CNT_SERV_AGENCY",
    "CNT_PHONE_AUTH_TRNSFR", "CNT_REINS_TYPE",
]


class TestLoad:
    def test_load_returns_all_32_field_rules(self):
        """load('CNT') returns entries for all 32 CNT field names."""
        field_rules, _ = load("CNT")
        assert len(field_rules) == 32
        for field in EXPECTED_CNT_FIELDS:
            assert field in field_rules, f"Missing field rule for: {field}"

    def test_all_nine_rule_types_supported(self):
        """All nine rule types are supported: 7 field-level + date_gt/date_lte in cross-field rules."""
        field_rules, cross_rules = load("CNT")
        field_rule_types = {r["rule_type"] for r in field_rules.values()}
        # Seven field-level rule types
        expected_field_types = {
            "not_blank", "exact_length", "max_length",
            "allowed_values", "valid_date", "numeric", "default_then_warn",
        }
        assert expected_field_types.issubset(field_rule_types), (
            f"Missing field rule types: {expected_field_types - field_rule_types}"
        )
        # date_gt and date_lte are cross-field check types
        cross_check_types = {r.get("check_type") for r in cross_rules if "check_type" in r}
        assert "date_gt" in cross_check_types, "date_gt not found in cross-field rules"
        assert "date_lte" in cross_check_types, "date_lte not found in cross-field rules"

    def test_cross_field_rules_returned_as_list(self):
        """Cross-field rules should be returned as a list with at least 16 entries."""
        _, cross_rules = load("CNT")
        assert isinstance(cross_rules, list)
        assert len(cross_rules) >= 16

    def test_missing_file_raises_file_not_found_with_path(self, tmp_path):
        """Missing rules file raises FileNotFoundError with path in message."""
        fake_path = tmp_path / "nonexistent.csv"
        with pytest.raises(FileNotFoundError, match=str(fake_path).replace("\\", "\\\\")):
            load("CNT", rules_path=fake_path)

    def test_rules_file_path_constant_defined_at_module_top(self):
        """RULES_FILE_PATH constant is defined at module top (not inside a function)."""
        import _deprecated_src_do_not_use.rule_loader as module
        # Verify it's a module-level attribute
        assert hasattr(module, "RULES_FILE_PATH")
        assert module.RULES_FILE_PATH == Path("rules") / "DB_Section_Contract.csv"

    def test_field_rules_have_required_keys(self):
        """Each field rule must have: rule_type, severity, length, allowed_values, ref_field."""
        field_rules, _ = load("CNT")
        required_keys = {"rule_type", "severity", "length", "allowed_values", "ref_field"}
        for field_name, config in field_rules.items():
            assert required_keys.issubset(config.keys()), (
                f"Missing keys in {field_name}: expected {required_keys}, got {set(config.keys())}"
            )

    def test_cnt_issue_system_rule(self):
        """CNT_ISSUE_SYSTEM should be exact_length with SEVERE severity."""
        field_rules, _ = load("CNT")
        assert "CNT_ISSUE_SYSTEM" in field_rules
        rule = field_rules["CNT_ISSUE_SYSTEM"]
        assert rule["severity"] == "SEVERE"

    def test_cnt_base_plan_code_default_then_warn(self):
        """CNT_BASE_PLAN_CODE should be default_then_warn with ref to CNT_POLICY_PLAN_CODE."""
        field_rules, _ = load("CNT")
        assert "CNT_BASE_PLAN_CODE" in field_rules
        rule = field_rules["CNT_BASE_PLAN_CODE"]
        assert rule["rule_type"] == "default_then_warn"
        assert rule["ref_field"] == "CNT_POLICY_PLAN_CODE"
        assert rule["severity"] == "WARNING"

    def test_date_fields_have_valid_date_rule(self):
        """Date fields should have rule_type 'valid_date'."""
        field_rules, _ = load("CNT")
        date_fields = [
            "CNT_ISSUE_DATE", "CNT_MATURE_EXPIRE_DATE",
            "CNT_APPLICATION_DATE", "CNT_PAYUP_DATE",
        ]
        for field in date_fields:
            assert field_rules[field]["rule_type"] == "valid_date", (
                f"{field} should be valid_date but is {field_rules[field]['rule_type']}"
            )

    def test_numeric_fields_have_numeric_rule(self):
        """Numeric fields should have rule_type 'numeric'."""
        field_rules, _ = load("CNT")
        assert field_rules["CNT_ISSUE_AGE"]["rule_type"] == "numeric"
        assert field_rules["CNT_JOINT_RATE_AGE"]["rule_type"] == "numeric"

    def test_allowed_values_fields_have_lists(self):
        """Fields with allowed_values rule type should have non-empty allowed_values list."""
        field_rules, _ = load("CNT")
        av_fields = [f for f, r in field_rules.items() if r["rule_type"] == "allowed_values"]
        assert len(av_fields) > 0
        for field in av_fields:
            assert field_rules[field]["allowed_values"] is not None, (
                f"{field} has allowed_values rule but allowed_values is None"
            )
            assert len(field_rules[field]["allowed_values"]) > 0

    def test_log_output_on_success(self, capsys):
        """Successful load logs rule counts with [RULES] prefix."""
        load("CNT")
        captured = capsys.readouterr()
        assert "[RULES]" in captured.out
        assert "32 field rules" in captured.out
        assert "cross-field rules" in captured.out
        assert "CNT" in captured.out
