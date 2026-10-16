# WARNING: These tests target the DEPRECATED codebase (_deprecated_src_do_not_use/). See option_b/tests/ for active tests.
"""Unit tests for CONDITIONAL_OR_DERIVED pattern-based dispatch.

Tests the pass-through pattern, role-gated copy pattern, and skip logic
introduced by the Conditional/Derived Transformation + Output Guards bugfix.
"""

import pandas as pd
import pytest

from _deprecated_src_do_not_use.transformation_engine import (
    _is_passthrough_pattern,
    _try_role_gated_copy,
    _handle_conditional,
)


# ---------------------------------------------------------------------------
# Tests for _is_passthrough_pattern
# ---------------------------------------------------------------------------


class TestIsPassthroughPattern:
    """Test the pass-through pattern detector."""

    def test_empty_rule_is_passthrough(self):
        """Empty transformation rule is a pass-through."""
        assert _is_passthrough_pattern("", ["CNT_POLICY_NUMBER"]) is True

    def test_whitespace_only_rule_is_passthrough(self):
        """Whitespace-only rule is a pass-through."""
        assert _is_passthrough_pattern("   ", ["CNT_POLICY_NUMBER"]) is True

    def test_rule_matches_source_field_name(self):
        """Rule text that exactly matches a source field name is a pass-through."""
        assert _is_passthrough_pattern("CNT_ISSUE_COUNTRY", ["CNT_ISSUE_COUNTRY"]) is True

    def test_rule_matches_source_field_case_insensitive(self):
        """Matching is case-insensitive."""
        assert _is_passthrough_pattern("cnt_issue_country", ["CNT_ISSUE_COUNTRY"]) is True

    def test_move_field_reference_is_passthrough(self):
        """'MOVE <field_name>' without quotes is a pass-through."""
        assert _is_passthrough_pattern("MOVE CNT_ISSUE_COUNTRY", ["CNT_ISSUE_COUNTRY"]) is True

    def test_move_field_any_name_no_quotes(self):
        """'MOVE <any_field>' without quotes is a pass-through (even if not in source_fields)."""
        assert _is_passthrough_pattern("MOVE ROL_FIRST_NAME", ["ROL_FIRST_NAME"]) is True

    def test_move_with_quoted_literal_is_not_passthrough(self):
        """'MOVE '<literal>'' is NOT a pass-through — it's a constant assignment."""
        assert _is_passthrough_pattern("MOVE 'Y'", ["CNT_FIELD"]) is False

    def test_conditional_keyword_if_rejects(self):
        """Rule with 'IF ' keyword is NOT a pass-through."""
        assert _is_passthrough_pattern("IF CNT_CODE = 'A' MOVE CNT_VALUE", ["CNT_VALUE"]) is False

    def test_conditional_keyword_when_rejects(self):
        """Rule with 'WHEN ' keyword is NOT a pass-through."""
        assert _is_passthrough_pattern("WHEN CNT_CODE EQ 'B' MOVE CNT_X", ["CNT_X"]) is False

    def test_conditional_keyword_eq_rejects(self):
        """Rule with 'EQ ' keyword is NOT a pass-through."""
        assert _is_passthrough_pattern("CNT_CODE EQ 'B'", ["CNT_CODE"]) is False

    def test_conditional_keyword_equals_quote_rejects(self):
        """Rule with \"= '\" is NOT a pass-through."""
        assert _is_passthrough_pattern("ROL_PERSON_CODE = 'I' MOVE ROL_FIRST_NAME", ["ROL_FIRST_NAME"]) is False

    def test_rule_starts_with_field_no_remainder(self):
        """Rule that starts with field name with no extra text is pass-through."""
        assert _is_passthrough_pattern("CNT_ISSUE_STATE", ["CNT_ISSUE_STATE"]) is True

    def test_rule_starts_with_field_comma_remainder(self):
        """Rule that starts with field name followed by comma is pass-through."""
        assert _is_passthrough_pattern("CNT_ISSUE_STATE,", ["CNT_ISSUE_STATE"]) is True

    def test_move_field_with_no_source_fields(self):
        """MOVE with a field name, even if source_fields is empty, is still a pass-through."""
        assert _is_passthrough_pattern("MOVE SOME_FIELD", []) is True

    def test_otherwise_keyword_rejects(self):
        """Rule with OTHERWISE is NOT a pass-through."""
        assert _is_passthrough_pattern("MOVE CNT_X OTHERWISE SPACES", ["CNT_X"]) is False


# ---------------------------------------------------------------------------
# Tests for _try_role_gated_copy
# ---------------------------------------------------------------------------


class TestTryRoleGatedCopy:
    """Test the role-gated copy pattern detector."""

    def _make_record(self, data: dict) -> pd.Series:
        return pd.Series(data)

    def _make_mapping(self, target_field="TEST_FIELD", target_length=20,
                      data_type="CHAR", source_fields=None, source_tables=None):
        return {
            "target_field": target_field,
            "target_length": target_length,
            "target_data_type": data_type,
            "source_fields": source_fields or [],
            "source_tables": source_tables or [],
            "padding_rule": "",
        }

    def test_simple_role_gated_copy_gate_passes(self):
        """IF ROL_PERSON_CODE = 'I' MOVE ROL_FIRST_NAME — gate passes."""
        record = self._make_record({
            "ROL_PERSON_CODE": "I",
            "ROL_FIRST_NAME": "John",
        })
        mapping = self._make_mapping()
        rule = "IF ROL_PERSON_CODE = 'I' MOVE ROL_FIRST_NAME"
        result = _try_role_gated_copy(mapping, rule, record, "")
        assert result == "John"

    def test_simple_role_gated_copy_gate_fails(self):
        """IF ROL_PERSON_CODE = 'I' MOVE ROL_FIRST_NAME — gate fails → empty."""
        record = self._make_record({
            "ROL_PERSON_CODE": "O",
            "ROL_FIRST_NAME": "John",
        })
        mapping = self._make_mapping()
        rule = "IF ROL_PERSON_CODE = 'I' MOVE ROL_FIRST_NAME"
        result = _try_role_gated_copy(mapping, rule, record, "")
        assert result == ""

    def test_multi_gate_and_condition_passes(self):
        """ROL_PERSON_CODE = 'I' and ROL_PERSON_SEQUENCE = '01' MOVE ROL_LAST_NAME — both pass."""
        record = self._make_record({
            "ROL_PERSON_CODE": "I",
            "ROL_PERSON_SEQUENCE": "01",
            "ROL_LAST_NAME": "Smith",
        })
        mapping = self._make_mapping()
        rule = "ROL_PERSON_CODE = 'I' and ROL_PERSON_SEQUENCE = '01' MOVE ROL_LAST_NAME"
        result = _try_role_gated_copy(mapping, rule, record, "")
        assert result == "Smith"

    def test_multi_gate_and_condition_fails(self):
        """ROL_PERSON_CODE = 'I' and ROL_PERSON_SEQUENCE = '01' — second gate fails."""
        record = self._make_record({
            "ROL_PERSON_CODE": "I",
            "ROL_PERSON_SEQUENCE": "02",
            "ROL_LAST_NAME": "Smith",
        })
        mapping = self._make_mapping()
        rule = "ROL_PERSON_CODE = 'I' and ROL_PERSON_SEQUENCE = '01' MOVE ROL_LAST_NAME"
        result = _try_role_gated_copy(mapping, rule, record, "")
        assert result == ""

    def test_quoted_literal_payload_returns_none(self):
        """Rule with quoted literal in payload is NOT a role-gated copy."""
        record = self._make_record({"ROL_PERSON_CODE": "I"})
        mapping = self._make_mapping()
        rule = "IF ROL_PERSON_CODE = 'I' MOVE 'Y'"
        result = _try_role_gated_copy(mapping, rule, record, "")
        assert result is None

    def test_no_equals_sign_returns_none(self):
        """Rule without '=' is not a role-gated copy."""
        record = self._make_record({"ROL_PERSON_CODE": "I"})
        mapping = self._make_mapping()
        rule = "MOVE ROL_FIRST_NAME"
        result = _try_role_gated_copy(mapping, rule, record, "")
        assert result is None

    def test_no_move_keyword_returns_none(self):
        """Rule without 'MOVE' is not a role-gated copy."""
        record = self._make_record({"ROL_PERSON_CODE": "I"})
        mapping = self._make_mapping()
        rule = "IF ROL_PERSON_CODE = 'I'"
        result = _try_role_gated_copy(mapping, rule, record, "")
        assert result is None

    def test_gate_field_not_in_record_fails(self):
        """Gate field not present in record → gate fails."""
        record = self._make_record({"ROL_FIRST_NAME": "John"})
        mapping = self._make_mapping()
        rule = "IF ROL_PERSON_CODE = 'I' MOVE ROL_FIRST_NAME"
        result = _try_role_gated_copy(mapping, rule, record, "")
        assert result == ""

    def test_payload_field_not_in_record_returns_empty(self):
        """Payload field not found in record → returns empty string."""
        record = self._make_record({"ROL_PERSON_CODE": "I"})
        mapping = self._make_mapping()
        rule = "IF ROL_PERSON_CODE = 'I' MOVE ROL_FIRST_NAME"
        result = _try_role_gated_copy(mapping, rule, record, "")
        assert result == ""

    def test_case_insensitive_gate_matching(self):
        """Gate matching is case-insensitive."""
        record = self._make_record({
            "ROL_PERSON_CODE": "i",
            "ROL_FIRST_NAME": "Jane",
        })
        mapping = self._make_mapping()
        rule = "IF ROL_PERSON_CODE = 'I' MOVE ROL_FIRST_NAME"
        result = _try_role_gated_copy(mapping, rule, record, "")
        assert result == "Jane"


# ---------------------------------------------------------------------------
# Tests for _handle_conditional (integration of patterns)
# ---------------------------------------------------------------------------


class TestHandleConditionalIntegration:
    """Integration tests for the full _handle_conditional dispatcher."""

    def _make_record(self, data: dict) -> pd.Series:
        return pd.Series(data)

    def _make_mapping(self, target_field="TEST_FIELD", target_length=20,
                      data_type="CHAR", transformation_rule="",
                      source_fields=None, source_tables=None):
        return {
            "target_field": target_field,
            "target_length": target_length,
            "target_data_type": data_type,
            "transformation_rule": transformation_rule,
            "source_fields": source_fields or [],
            "source_tables": source_tables or [],
            "padding_rule": "",
            "default_value": "",
        }

    def test_empty_rule_passthrough_with_value(self):
        """Empty rule + source value → pass-through, formatted to target length."""
        record = self._make_record({"CNT_FIELD": "ABC"})
        mapping = self._make_mapping(
            target_length=10, data_type="CHAR", transformation_rule="",
            source_fields=["CNT_FIELD"], source_tables=["CNT"]
        )
        result = _handle_conditional(mapping, "ABC", record)
        assert result == "ABC       "
        assert len(result) == 10

    def test_empty_rule_passthrough_no_value(self):
        """Empty rule + no source value → default initialization."""
        record = self._make_record({"CNT_FIELD": ""})
        mapping = self._make_mapping(
            target_length=5, data_type="NUMERIC", transformation_rule="",
            source_fields=["CNT_FIELD"], source_tables=["CNT"]
        )
        result = _handle_conditional(mapping, "", record)
        assert result == "00000"
        assert len(result) == 5

    def test_role_gated_pattern_executes(self):
        """Role-gated rule with passing gate → copies payload field."""
        record = self._make_record({
            "ROL_PERSON_CODE": "I",
            "ROL_FIRST_NAME": "Alice",
        })
        mapping = self._make_mapping(
            target_length=15, data_type="CHAR",
            transformation_rule="IF ROL_PERSON_CODE = 'I' MOVE ROL_FIRST_NAME",
            source_fields=["ROL_FIRST_NAME"], source_tables=["ROL"]
        )
        result = _handle_conditional(mapping, "Alice", record)
        assert result is not None
        assert len(result) == 15
        assert result.strip() == "Alice"

    def test_unavailable_source_table_skips(self):
        """Source table not available (e.g., PRM) → returns None (SKIP)."""
        record = self._make_record({"CNT_POLICY_NUMBER": "12345"})
        mapping = self._make_mapping(
            target_length=10, data_type="CHAR",
            transformation_rule="PRM_FIELD_X",
            source_fields=["PRM_FIELD_X"], source_tables=["PRM"]
        )
        result = _handle_conditional(mapping, "", record)
        assert result is None

    def test_unparseable_rule_skips(self):
        """Complex rule that can't be parsed → returns None (SKIP)."""
        record = self._make_record({"CNT_POLICY_NUMBER": "12345"})
        mapping = self._make_mapping(
            target_length=5, data_type="CHAR",
            transformation_rule="IF CNT_DIVIDEND_CODE = 'A' MOVE 'ANNUAL' OTHERWISE MOVE 'NONE'",
            source_fields=["CNT_DIVIDEND_CODE"], source_tables=["CNT"]
        )
        # This has quoted literal in payload, so role-gated won't match.
        # It has IF keyword so passthrough won't match.
        # Result should be None (SKIP).
        result = _handle_conditional(mapping, "A", record)
        assert result is None

    def test_known_named_rule_product_code(self):
        """Known named rule (PRODUCT-CODE) still executes correctly."""
        record = self._make_record({
            "CNT_PRODUCT_TYPE": "T",
            "CNT_POLICY_NUMBER": "12345",
        })
        mapping = self._make_mapping(
            target_field="PRODUCT-CODE", target_length=2, data_type="CHAR",
            transformation_rule="IF CNT_PRODUCT_TYPE in {T,K,L,D,H} move 'T1'",
            source_fields=["CNT_PRODUCT_TYPE"], source_tables=["CNT"]
        )
        result = _handle_conditional(mapping, "T", record)
        assert result == "T1"
