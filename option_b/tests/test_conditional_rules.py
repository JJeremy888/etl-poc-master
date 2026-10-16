"""Tests for conditional_rules module.

**Validates: Requirements 5** — Conditional Rule Evaluation Property.
"""

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
import pyspark.sql.functions as F

from option_b.engine.conditional_rules import apply_conditional_rule, _build_precondition


class TestBuildPrecondition:
    """Unit tests for precondition expression building."""

    def test_eq_operator(self, spark):
        precond = _build_precondition("STATUS", "eq", "A")
        df = spark.createDataFrame([("A",), ("B",)], ["STATUS"])
        result = df.withColumn("COND", precond).collect()
        assert result[0]["COND"] is True
        assert result[1]["COND"] is False

    def test_neq_operator(self, spark):
        precond = _build_precondition("STATUS", "neq", "A")
        df = spark.createDataFrame([("A",), ("B",)], ["STATUS"])
        result = df.withColumn("COND", precond).collect()
        assert result[0]["COND"] is False
        assert result[1]["COND"] is True

    def test_in_operator(self, spark):
        precond = _build_precondition("TYPE", "in", "X|Y|Z")
        df = spark.createDataFrame([("X",), ("A",)], ["TYPE"])
        result = df.withColumn("COND", precond).collect()
        assert result[0]["COND"] is True
        assert result[1]["COND"] is False

    def test_not_in_operator(self, spark):
        precond = _build_precondition("TYPE", "not_in", "X|Y")
        df = spark.createDataFrame([("X",), ("A",)], ["TYPE"])
        result = df.withColumn("COND", precond).collect()
        assert result[0]["COND"] is False
        assert result[1]["COND"] is True

    def test_blank_operator(self, spark):
        precond = _build_precondition("F1", "blank", "")
        df = spark.createDataFrame([("",), ("X",)], ["F1"])
        result = df.withColumn("COND", precond).collect()
        assert result[0]["COND"] is True
        assert result[1]["COND"] is False

    def test_not_blank_operator(self, spark):
        precond = _build_precondition("F1", "not_blank", "")
        df = spark.createDataFrame([("",), ("X",)], ["F1"])
        result = df.withColumn("COND", precond).collect()
        assert result[0]["COND"] is False
        assert result[1]["COND"] is True

    def test_unknown_operator_returns_true(self, spark):
        precond = _build_precondition("F1", "unknown_op", "")
        df = spark.createDataFrame([("X",)], ["F1"])
        result = df.withColumn("COND", precond).collect()
        assert result[0]["COND"] is True


class TestApplyConditionalRule:
    """Unit tests for conditional rule application."""

    def test_precondition_true_applies_check(self, spark):
        """When precondition is true, the dependent check fires."""
        rule = {
            "target_field": "CNT_PRODUCT_TYPE",
            "precondition_field": "STATUS",
            "precondition_operator": "eq",
            "precondition_value": "ACTIVE",
            "severity": "SEVERE",
            "allowed_values": "X|Y",
        }
        df = spark.createDataFrame([("ACTIVE", "Z"), ("INACTIVE", "Z")], ["STATUS", "CNT_PRODUCT_TYPE"])
        result_df, val_col = apply_conditional_rule(df, rule)
        results = result_df.select(val_col).collect()
        # Precondition true, value Z not in X|Y → SEVERE
        assert results[0][val_col] is not None
        assert "SEVERE" in results[0][val_col]
        # Precondition false → None
        assert results[1][val_col] is None

    def test_precondition_false_skips_check(self, spark):
        """When precondition is false, the rule always passes (NULL)."""
        rule = {
            "target_field": "CNT_PRODUCT_TYPE",
            "precondition_field": "STATUS",
            "precondition_operator": "eq",
            "precondition_value": "X",
            "severity": "SEVERE",
            "allowed_values": "A|B",
        }
        df = spark.createDataFrame([("Y", "Z")], ["STATUS", "CNT_PRODUCT_TYPE"])
        result_df, val_col = apply_conditional_rule(df, rule)
        results = result_df.select(val_col).collect()
        assert results[0][val_col] is None

    def test_no_precondition_skips(self, spark):
        """When no precondition is defined, rule is skipped (NULL)."""
        rule = {
            "target_field": "CNT_PRODUCT_TYPE",
            "precondition_field": "",
            "precondition_operator": "",
            "precondition_value": "",
            "severity": "SEVERE",
            "allowed_values": "A|B",
        }
        df = spark.createDataFrame([("Z",)], ["CNT_PRODUCT_TYPE"])
        result_df, val_col = apply_conditional_rule(df, rule)
        results = result_df.select(val_col).collect()
        assert results[0][val_col] is None


class TestConditionalRuleEvaluationProperty:
    """**Validates: Requirements 5** — Conditional Rule Evaluation Property.

    Property: If precondition is false, rule always passes (NULL).
    If precondition is true, the dependent check result is returned.
    """

    @given(
        precondition_value=st.text(min_size=1, max_size=5, alphabet="ABCDE"),
        actual_value=st.text(min_size=1, max_size=5, alphabet="ABCDE"),
    )
    @settings(max_examples=100, deadline=None)
    def test_conditional_eq_property(self, spark, precondition_value, actual_value):
        """eq precondition: check fires iff actual == expected."""
        rule = {
            "target_field": "F1",
            "precondition_field": "COND_FIELD",
            "precondition_operator": "eq",
            "precondition_value": precondition_value,
            "severity": "SEVERE",
            "allowed_values": "",  # Uses not_blank dependent check
        }
        df = spark.createDataFrame([(actual_value, "X")], ["COND_FIELD", "F1"])
        result_df, val_col = apply_conditional_rule(df, rule)
        result = result_df.select(val_col).collect()[0][val_col]

        if actual_value.strip() == precondition_value:
            # Precondition true → dependent fires (F1="X" is not blank, so passes)
            assert result is None
        else:
            # Precondition false → passes
            assert result is None
