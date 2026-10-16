# WARNING: These tests target the DEPRECATED codebase (_deprecated_src_do_not_use/). See option_b/tests/ for active tests.
"""Unit tests for field_validator.py - shared generic validation engine.

Tests apply_field_rules() and classify_severity() directly and in isolation,
independent of any table-specific module (validate_cvg, validate_rol, etc.).

Severity values in all tests are sourced from the rules dict, mirroring how
rule_loader.py loads them from the BA rule sheet at runtime. No severity
values are hardcoded assumptions outside of the rules dict passed to the
functions under test.
"""

import pandas as pd
import pytest

from _deprecated_src_do_not_use.field_validator import apply_field_rules, classify_severity


# ─────────────────────────────────────────────────────────────────────
# Rules dicts used across tests — structured exactly as rule_loader.py
# would produce them from the BA rule sheet. Each carries a severity
# level that flows through apply_field_rules into classify_severity.
# ─────────────────────────────────────────────────────────────────────

RULES_TWO_FIELDS = {
    # Simulates a BA rule sheet entry: COMPANY_CODE must be exactly 3 chars, SEVERE
    "COMPANY_CODE": {
        "rule_type": "not_blank",
        "severity": "SEVERE",
        "length": 3,
        "allowed_values": None,
        "ref_field": None,
    },
    # Simulates: STATUS is allowed_values with WARNING severity
    "STATUS": {
        "rule_type": "allowed_values",
        "severity": "WARNING",
        "length": None,
        "allowed_values": ["01", "02", "03"],
        "ref_field": None,
    },
}

RULES_SEVERE_ONLY = {
    "ISSUE_DATE": {
        "rule_type": "valid_date",
        "severity": "SEVERE",
        "length": None,
        "allowed_values": None,
        "ref_field": None,
    },
}

RULES_WARNING_ONLY = {
    "AGENT_CODE": {
        "rule_type": "not_blank",
        "severity": "WARNING",
        "length": None,
        "allowed_values": None,
        "ref_field": None,
    },
}

RULES_MIXED_SEVERITY = {
    # SEVERE: numeric field from BA sheet
    "FACE_AMOUNT": {
        "rule_type": "numeric",
        "severity": "SEVERE",
        "length": None,
        "allowed_values": None,
        "ref_field": None,
    },
    # WARNING: optional date from BA sheet
    "EFFECTIVE_DATE": {
        "rule_type": "valid_date",
        "severity": "WARNING",
        "length": None,
        "allowed_values": None,
        "ref_field": None,
    },
}


# ─────────────────────────────────────────────────────────────────────
# TESTS FOR apply_field_rules()
# ─────────────────────────────────────────────────────────────────────


class TestApplyFieldRulesAllPass:
    """Test 1 - valid rules dict (2 field rules from BA sheet), all rows pass."""

    def test_no_violations_when_all_valid(self):
        df = pd.DataFrame({
            "COMPANY_CODE": ["001", "002", "003"],
            "STATUS": ["01", "02", "03"],
        })
        result = apply_field_rules(df, RULES_TWO_FIELDS)

        # Both VAL_ columns should be None for all rows — no violations
        assert result["VAL_COMPANY_CODE"].isna().all()
        assert result["VAL_STATUS"].isna().all()


class TestApplyFieldRulesOneViolation:
    """Test 2 - one row violates one rule; severity comes from rules dict."""

    def test_exactly_one_row_flagged_with_correct_severity(self):
        df = pd.DataFrame({
            "COMPANY_CODE": ["001", "002", ""],  # row 2 is blank — violates SEVERE rule
            "STATUS": ["01", "02", "03"],         # all valid
        })
        result = apply_field_rules(df, RULES_TWO_FIELDS)

        # Rows 0 and 1 pass
        assert result["VAL_COMPANY_CODE"].iloc[0] is None
        assert result["VAL_COMPANY_CODE"].iloc[1] is None

        # Row 2 is flagged — message must start with the severity from the rules dict
        violation_msg = str(result["VAL_COMPANY_CODE"].iloc[2])
        assert violation_msg.startswith("SEVERE"), (
            f"Expected severity 'SEVERE' from rules dict, got: {violation_msg}"
        )

        # STATUS passes on all rows (valid values)
        assert result["VAL_STATUS"].isna().all()

    def test_warning_severity_appears_when_rule_says_warning(self):
        df = pd.DataFrame({
            "COMPANY_CODE": ["001", "002", "003"],
            "STATUS": ["01", "XX", "03"],  # row 1 has invalid status
        })
        result = apply_field_rules(df, RULES_TWO_FIELDS)

        # STATUS rule has severity=WARNING in the rules dict
        violation_msg = str(result["VAL_STATUS"].iloc[1])
        assert violation_msg.startswith("WARNING"), (
            f"Expected severity 'WARNING' from rules dict, got: {violation_msg}"
        )


class TestApplyFieldRulesEmptyDict:
    """Test 3 - empty rules dict."""

    def test_empty_rules_no_error_no_violations(self):
        df = pd.DataFrame({
            "FIELD_A": ["hello", "world", "test"],
        })
        result = apply_field_rules(df, {})

        # No VAL_ columns should be created
        val_cols = [c for c in result.columns if c.startswith("VAL_")]
        assert val_cols == []

        # Original data preserved
        assert list(result["FIELD_A"]) == ["hello", "world", "test"]


class TestApplyFieldRulesMissingColumn:
    """Test 4 - rules dict references a field not in the dataframe.

    Current behaviour: apply_field_rules() SKIPS missing fields gracefully
    via the guard `if field_name not in df.columns: continue`.
    No error is raised. No VAL_ column is created for the missing field.
    This is visible in code review — the function does not raise or log.
    """

    def test_missing_column_skipped_gracefully(self):
        df = pd.DataFrame({
            "COMPANY_CODE": ["001", "002", "003"],
            # "STATUS" column is NOT present in the DataFrame
        })
        # Rules dict references both COMPANY_CODE (present) and STATUS (absent)
        result = apply_field_rules(df, RULES_TWO_FIELDS)

        # VAL_COMPANY_CODE exists (field is present)
        assert "VAL_COMPANY_CODE" in result.columns

        # VAL_STATUS does NOT exist (field was absent, rule was skipped)
        assert "VAL_STATUS" not in result.columns

    def test_all_referenced_fields_missing_no_error(self):
        df = pd.DataFrame({
            "UNRELATED_COLUMN": ["x", "y", "z"],
        })
        rules = {
            "ABSENT_A": {"rule_type": "not_blank", "severity": "SEVERE", "length": None},
            "ABSENT_B": {"rule_type": "numeric", "severity": "WARNING"},
        }
        # Should not raise — all rules are skipped
        result = apply_field_rules(df, rules)

        val_cols = [c for c in result.columns if c.startswith("VAL_")]
        assert val_cols == []


# ─────────────────────────────────────────────────────────────────────
# TESTS FOR classify_severity()
#
# These tests use VAL_ column values whose severity prefix was produced
# by apply_field_rules() using the rules dict severity. We construct
# them here to match what the real pipeline produces — the prefix always
# comes from rules["severity"].
# ─────────────────────────────────────────────────────────────────────


class TestClassifySeverityAllClean:
    """Test 5 - all rows are CLEAN (no rules violated)."""

    def test_no_val_columns_all_clean(self):
        """DataFrame with no VAL_ columns at all."""
        df = pd.DataFrame({"DATA": ["a", "b", "c"]})
        result = classify_severity(df)
        assert list(result["ROW_SEVERITY"]) == ["CLEAN", "CLEAN", "CLEAN"]

    def test_val_columns_all_none_is_clean(self):
        """VAL_ columns exist but all values are None (all rules passed)."""
        df = pd.DataFrame({
            "VAL_COMPANY_CODE": [None, None, None],
            "VAL_STATUS": [None, None, None],
        })
        result = classify_severity(df)
        assert list(result["ROW_SEVERITY"]) == ["CLEAN", "CLEAN", "CLEAN"]


class TestClassifySeverityAllSevere:
    """Test 6 - all rows have at least one SEVERE violation.

    The 'SEVERE' prefix in VAL_ values originates from a rules dict entry
    where severity='SEVERE', as the BA sheet would define for critical fields.
    """

    def test_all_severe(self):
        # These messages mirror what apply_field_rules produces for SEVERE rules
        df = pd.DataFrame({
            "VAL_ISSUE_DATE": [
                "SEVERE: Must not be blank",
                "SEVERE: Invalid date format - expected YYYYMMDD",
                "SEVERE: Must not be blank",
            ],
        })
        result = classify_severity(df)
        assert list(result["ROW_SEVERITY"]) == ["SEVERE", "SEVERE", "SEVERE"]


class TestClassifySeverityAllWarning:
    """Test 7 - all rows have only WARNING violations (no SEVERE).

    The 'WARNING' prefix originates from a rules dict entry where
    severity='WARNING', as the BA sheet defines for non-critical fields.
    """

    def test_all_warning(self):
        df = pd.DataFrame({
            "VAL_AGENT_CODE": [
                "WARNING: Must not be blank",
                "WARNING: Must not be blank",
                "WARNING: Must not be blank",
            ],
            "VAL_STATUS": [None, None, None],  # another field passes
        })
        result = classify_severity(df)
        assert list(result["ROW_SEVERITY"]) == ["WARNING", "WARNING", "WARNING"]


class TestClassifySeverityMixed:
    """Test 8 - mixed rows with SEVERE, WARNING, and CLEAN.

    Uses a rules dict with both SEVERE and WARNING entries, then builds
    VAL_ columns as apply_field_rules would produce them.
    """

    def test_mixed_classification_from_rules_dict_severities(self):
        # First, run apply_field_rules to generate realistic VAL_ columns
        df = pd.DataFrame({
            "FACE_AMOUNT": ["500000", "ABC", "100"],     # row 1 is non-numeric -> SEVERE
            "EFFECTIVE_DATE": ["20200101", "20200101", "BADDATE"],  # row 2 invalid -> WARNING
        })
        result = apply_field_rules(df, RULES_MIXED_SEVERITY)
        result = classify_severity(result)

        # Row 0: both fields valid -> CLEAN
        assert result["ROW_SEVERITY"].iloc[0] == "CLEAN"

        # Row 1: FACE_AMOUNT fails (SEVERE from rules dict) -> SEVERE
        assert result["ROW_SEVERITY"].iloc[1] == "SEVERE"

        # Row 2: EFFECTIVE_DATE fails (WARNING from rules dict) -> WARNING
        assert result["ROW_SEVERITY"].iloc[2] == "WARNING"

    def test_severe_wins_over_warning_on_same_row(self):
        """A row with both SEVERE and WARNING violations is classified SEVERE."""
        df = pd.DataFrame({
            "FACE_AMOUNT": ["ABC"],       # non-numeric -> SEVERE (from rules dict)
            "EFFECTIVE_DATE": ["BADDATE"], # invalid date -> WARNING (from rules dict)
        })
        result = apply_field_rules(df, RULES_MIXED_SEVERITY)
        result = classify_severity(result)

        # SEVERE from FACE_AMOUNT wins over WARNING from EFFECTIVE_DATE
        assert result["ROW_SEVERITY"].iloc[0] == "SEVERE"

    def test_note_prefix_does_not_affect_classification(self):
        """NOTE: entries (used for deferred validations) do not change severity."""
        df = pd.DataFrame({
            "VAL_REINS_TYPE": [
                "NOTE: Cross-table validation deferred to Phase 2",
                "NOTE: Cross-table validation deferred to Phase 2",
            ],
        })
        result = classify_severity(df)
        # NOTE does not count as SEVERE or WARNING
        assert list(result["ROW_SEVERITY"]) == ["CLEAN", "CLEAN"]


# ─────────────────────────────────────────────────────────────────────
# TESTS FOR exact_length RULE TYPE
#
# This rule type was added to field_validator.py during the CNT refactor.
# It checks: blank -> SEVERE, then non-blank must be exactly N chars.
# Severity comes from the rules dict (BA sheet).
# ─────────────────────────────────────────────────────────────────────

RULES_EXACT_LENGTH = {
    "SYSTEM_CODE": {
        "rule_type": "exact_length",
        "severity": "SEVERE",
        "length": 2,
        "allowed_values": None,
        "ref_field": None,
    },
}


class TestExactLength:
    """Tests for the exact_length rule type in field_validator."""

    def test_a_value_matches_required_exact_length(self):
        """Test A - field value matches the required exact length. No violation."""
        df = pd.DataFrame({"SYSTEM_CODE": ["AA", "BB", "CC"]})
        result = apply_field_rules(df, RULES_EXACT_LENGTH)
        assert result["VAL_SYSTEM_CODE"].isna().all()

    def test_b_value_shorter_than_required_length(self):
        """Test B - field value is shorter than required length.
        Violation flagged with severity from rules dict."""
        df = pd.DataFrame({"SYSTEM_CODE": ["A", "BB", "C"]})
        result = apply_field_rules(df, RULES_EXACT_LENGTH)

        # Row 0: "A" is 1 char, required 2 -> flagged
        msg_0 = str(result["VAL_SYSTEM_CODE"].iloc[0])
        assert msg_0.startswith("SEVERE"), f"Expected SEVERE from rules dict, got: {msg_0}"
        assert "exactly 2 characters" in msg_0

        # Row 1: "BB" is 2 chars -> passes
        assert result["VAL_SYSTEM_CODE"].iloc[1] is None

        # Row 2: "C" is 1 char -> flagged
        msg_2 = str(result["VAL_SYSTEM_CODE"].iloc[2])
        assert msg_2.startswith("SEVERE")

    def test_c_blank_value_fails_exact_length(self):
        """Test C - blank value fails the exact length check (blank = SEVERE)."""
        df = pd.DataFrame({"SYSTEM_CODE": ["", "  ", "AA"]})
        result = apply_field_rules(df, RULES_EXACT_LENGTH)

        # Row 0: blank -> flagged
        msg_0 = str(result["VAL_SYSTEM_CODE"].iloc[0])
        assert msg_0.startswith("SEVERE")
        assert "Must not be blank" in msg_0

        # Row 1: whitespace only -> flagged as blank
        msg_1 = str(result["VAL_SYSTEM_CODE"].iloc[1])
        assert msg_1.startswith("SEVERE")

        # Row 2: valid "AA" -> passes
        assert result["VAL_SYSTEM_CODE"].iloc[2] is None

    def test_exact_length_longer_than_required(self):
        """Value longer than required exact length is also flagged."""
        df = pd.DataFrame({"SYSTEM_CODE": ["ABC"]})  # 3 chars, required 2
        result = apply_field_rules(df, RULES_EXACT_LENGTH)
        msg = str(result["VAL_SYSTEM_CODE"].iloc[0])
        assert msg.startswith("SEVERE")
        assert "exactly 2 characters" in msg


# ─────────────────────────────────────────────────────────────────────
# TESTS FOR default_then_warn RULE TYPE
#
# This rule type was added to field_validator.py during the CNT refactor.
# It defaults a blank field to a reference field value, then emits WARNING.
# Severity for this rule type is always WARNING (as defined in the BA sheet).
# ─────────────────────────────────────────────────────────────────────

RULES_DEFAULT_THEN_WARN = {
    "BASE_PLAN_CODE": {
        "rule_type": "default_then_warn",
        "severity": "WARNING",
        "length": None,
        "allowed_values": None,
        "ref_field": "POLICY_PLAN_CODE",
    },
}


class TestDefaultThenWarn:
    """Tests for the default_then_warn rule type in field_validator."""

    def test_d_blank_field_defaulted_and_warning_emitted(self):
        """Test D - field is blank, reference field has a value.
        The blank field is defaulted to the reference value AND a WARNING is emitted."""
        df = pd.DataFrame({
            "BASE_PLAN_CODE": ["", "", "EXISTING1"],
            "POLICY_PLAN_CODE": ["PLAN00001A", "PLAN00002B", "PLAN00003C"],
        })
        result = apply_field_rules(df, RULES_DEFAULT_THEN_WARN)

        # Row 0: was blank -> defaulted to POLICY_PLAN_CODE value
        assert result["BASE_PLAN_CODE"].iloc[0] == "PLAN00001A"
        msg_0 = str(result["VAL_BASE_PLAN_CODE"].iloc[0])
        assert msg_0.startswith("WARNING"), f"Expected WARNING, got: {msg_0}"
        assert "Defaulted BASE_PLAN_CODE to POLICY_PLAN_CODE" in msg_0

        # Row 1: was blank -> defaulted
        assert result["BASE_PLAN_CODE"].iloc[1] == "PLAN00002B"
        msg_1 = str(result["VAL_BASE_PLAN_CODE"].iloc[1])
        assert msg_1.startswith("WARNING")

        # Row 2: already had a value -> no defaulting, no warning
        assert result["BASE_PLAN_CODE"].iloc[2] == "EXISTING1"
        assert result["VAL_BASE_PLAN_CODE"].iloc[2] is None

    def test_e_non_blank_field_not_defaulted(self):
        """Test E - field already has a value. No defaulting, no WARNING."""
        df = pd.DataFrame({
            "BASE_PLAN_CODE": ["VALUE_A", "VALUE_B", "VALUE_C"],
            "POLICY_PLAN_CODE": ["REF_A", "REF_B", "REF_C"],
        })
        result = apply_field_rules(df, RULES_DEFAULT_THEN_WARN)

        # All rows already have values -> no defaulting
        assert list(result["BASE_PLAN_CODE"]) == ["VALUE_A", "VALUE_B", "VALUE_C"]
        # No warnings emitted
        assert result["VAL_BASE_PLAN_CODE"].isna().all()
