"""Tests for rule_compiler and presence/format rules.

**Validates: Requirements 2** — Presence/Format Rule Correctness Property.
"""

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
import pyspark.sql.functions as F

from option_b.engine.rule_compiler import compile_rule, compile_all_rules
from option_b.engine.presence_format_rules import (
    compile_not_blank,
    compile_exact_length,
    compile_max_length,
    compile_allowed_values,
    compile_valid_date,
    compile_numeric,
)


class TestCompileNotBlank:
    """Unit tests for not_blank rule."""

    def test_non_blank_passes(self, spark):
        rule = {"target_field": "F1", "severity": "SEVERE"}
        df = spark.createDataFrame([("hello",)], ["F1"])
        result = df.withColumn("VAL", compile_not_blank(rule))
        assert result.collect()[0]["VAL"] is None

    def test_blank_fails(self, spark):
        rule = {"target_field": "F1", "severity": "SEVERE"}
        df = spark.createDataFrame([("",)], ["F1"])
        result = df.withColumn("VAL", compile_not_blank(rule))
        val = result.collect()[0]["VAL"]
        assert val is not None
        assert "SEVERE:" in val

    def test_null_fails(self, spark):
        rule = {"target_field": "F1", "severity": "SEVERE"}
        from pyspark.sql.types import StructType, StructField, StringType
        schema = StructType([StructField("F1", StringType(), True)])
        df = spark.createDataFrame([(None,)], schema=schema)
        result = df.withColumn("VAL", compile_not_blank(rule))
        val = result.collect()[0]["VAL"]
        assert val is not None
        assert "SEVERE:" in val


class TestCompileExactLength:
    """Unit tests for exact_length rule."""

    def test_correct_length_passes(self, spark):
        rule = {"target_field": "F1", "severity": "SEVERE", "param_1": "3"}
        df = spark.createDataFrame([("ABC",)], ["F1"])
        result = df.withColumn("VAL", compile_exact_length(rule))
        assert result.collect()[0]["VAL"] is None

    def test_wrong_length_fails(self, spark):
        rule = {"target_field": "F1", "severity": "SEVERE", "param_1": "3"}
        df = spark.createDataFrame([("ABCD",)], ["F1"])
        result = df.withColumn("VAL", compile_exact_length(rule))
        assert result.collect()[0]["VAL"] is not None

    def test_blank_fails(self, spark):
        """Blank values fail exact_length (length 0 != target)."""
        rule = {"target_field": "F1", "severity": "SEVERE", "param_1": "3"}
        df = spark.createDataFrame([("",)], ["F1"])
        result = df.withColumn("VAL", compile_exact_length(rule))
        assert result.collect()[0]["VAL"] is not None


class TestCompileAllowedValues:
    """Unit tests for allowed_values rule."""

    def test_allowed_value_passes(self, spark):
        rule = {"target_field": "F1", "severity": "SEVERE", "allowed_values": "A|B|C"}
        df = spark.createDataFrame([("B",)], ["F1"])
        result = df.withColumn("VAL", compile_allowed_values(rule))
        assert result.collect()[0]["VAL"] is None

    def test_disallowed_value_fails(self, spark):
        rule = {"target_field": "F1", "severity": "SEVERE", "allowed_values": "A|B|C"}
        df = spark.createDataFrame([("X",)], ["F1"])
        result = df.withColumn("VAL", compile_allowed_values(rule))
        assert result.collect()[0]["VAL"] is not None

    def test_blank_fails_without_blank_acceptable(self, spark):
        """Blank values fail when description doesn't say 'blank acceptable'."""
        rule = {"target_field": "F1", "severity": "SEVERE", "allowed_values": "A|B"}
        df = spark.createDataFrame([("",)], ["F1"])
        result = df.withColumn("VAL", compile_allowed_values(rule))
        assert result.collect()[0]["VAL"] is not None

    def test_blank_passes_when_blank_acceptable(self, spark):
        """Blank values pass when description says 'blank acceptable'."""
        rule = {"target_field": "F1", "severity": "SEVERE", "allowed_values": "A|B",
                "description": "Blank acceptable for no value"}
        df = spark.createDataFrame([("",)], ["F1"])
        result = df.withColumn("VAL", compile_allowed_values(rule))
        assert result.collect()[0]["VAL"] is None


class TestCompileValidDate:
    """Unit tests for valid_date rule."""

    def test_valid_date_passes(self, spark):
        rule = {"target_field": "F1", "severity": "SEVERE"}
        df = spark.createDataFrame([("20230115",)], ["F1"])
        result = df.withColumn("VAL", compile_valid_date(rule))
        assert result.collect()[0]["VAL"] is None

    def test_invalid_date_fails(self, spark):
        rule = {"target_field": "F1", "severity": "SEVERE"}
        df = spark.createDataFrame([("BADDATE1",)], ["F1"])
        result = df.withColumn("VAL", compile_valid_date(rule))
        assert result.collect()[0]["VAL"] is not None

    def test_too_short_fails(self, spark):
        rule = {"target_field": "F1", "severity": "SEVERE"}
        df = spark.createDataFrame([("2023",)], ["F1"])
        result = df.withColumn("VAL", compile_valid_date(rule))
        assert result.collect()[0]["VAL"] is not None

    def test_invalid_month_fails(self, spark):
        rule = {"target_field": "F1", "severity": "SEVERE"}
        df = spark.createDataFrame([("20231301",)], ["F1"])
        result = df.withColumn("VAL", compile_valid_date(rule))
        assert result.collect()[0]["VAL"] is not None


class TestCompileNumeric:
    """Unit tests for numeric rule."""

    def test_digits_pass(self, spark):
        rule = {"target_field": "F1", "severity": "SEVERE"}
        df = spark.createDataFrame([("12345",)], ["F1"])
        result = df.withColumn("VAL", compile_numeric(rule))
        assert result.collect()[0]["VAL"] is None

    def test_alpha_fails(self, spark):
        rule = {"target_field": "F1", "severity": "SEVERE"}
        df = spark.createDataFrame([("ABC",)], ["F1"])
        result = df.withColumn("VAL", compile_numeric(rule))
        assert result.collect()[0]["VAL"] is not None

    def test_zero_passes(self, spark):
        rule = {"target_field": "F1", "severity": "SEVERE"}
        df = spark.createDataFrame([("0",)], ["F1"])
        result = df.withColumn("VAL", compile_numeric(rule))
        assert result.collect()[0]["VAL"] is None


class TestCompileRule:
    """Unit tests for the compile_rule dispatcher."""

    def test_dispatches_not_blank(self, spark):
        rule = {"rule_id": "R1", "target_field": "F1", "rule_type": "not_blank",
                "severity": "SEVERE", "precondition_field": None}
        col = compile_rule(rule)
        assert col is not None

    def test_unknown_type_returns_none(self, spark):
        rule = {"rule_id": "R1", "target_field": "F1", "rule_type": "unknown_xyz",
                "severity": "SEVERE", "precondition_field": None}
        col = compile_rule(rule)
        assert col is None

    def test_cross_reference_returns_none(self, spark):
        rule = {"rule_id": "R1", "target_field": "F1", "rule_type": "cross_reference_exists",
                "severity": "SEVERE", "precondition_field": None}
        col = compile_rule(rule)
        assert col is None


class TestPresenceFormatCorrectnessProperty:
    """**Validates: Requirements 2** — Presence/Format Rule Correctness Property.

    Property: For any non-blank string of correct length/format, validation passes.
    For any string that violates the rule, validation fails with severity prefix.
    """

    @given(value=st.text(min_size=1, max_size=50))
    @settings(max_examples=100, deadline=None)
    def test_not_blank_passes_for_any_non_empty(self, spark, value):
        """Any non-blank string must pass not_blank."""
        assume(value.strip() != "")
        rule = {"target_field": "F1", "severity": "SEVERE"}
        df = spark.createDataFrame([(value,)], ["F1"])
        result = df.withColumn("VAL", compile_not_blank(rule)).collect()[0]["VAL"]
        assert result is None

    @given(length=st.integers(min_value=1, max_value=20))
    @settings(max_examples=100, deadline=None)
    def test_exact_length_matches_generated_string(self, spark, length):
        """A string of exactly N chars must pass exact_length(N)."""
        value = "X" * length
        rule = {"target_field": "F1", "severity": "SEVERE", "param_1": str(length)}
        df = spark.createDataFrame([(value,)], ["F1"])
        result = df.withColumn("VAL", compile_exact_length(rule)).collect()[0]["VAL"]
        assert result is None

    @given(
        value=st.text(
            alphabet="0123456789",
            min_size=1,
            max_size=10,
        )
    )
    @settings(max_examples=100, deadline=None)
    def test_numeric_passes_for_digit_strings(self, spark, value):
        """Any string of digits must pass numeric rule."""
        rule = {"target_field": "F1", "severity": "SEVERE"}
        df = spark.createDataFrame([(value,)], ["F1"])
        result = df.withColumn("VAL", compile_numeric(rule)).collect()[0]["VAL"]
        assert result is None
