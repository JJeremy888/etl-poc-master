"""Tests for cross_reference_rules module.

**Validates: Requirements 4** — Cross-Reference Join Correctness Property.
"""

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
import pyspark.sql.functions as F

from option_b.engine.cross_reference_rules import apply_cross_reference


class TestApplyCrossReference:
    """Unit tests for apply_cross_reference."""

    def test_matching_records_pass(self, spark):
        """Records with matching parent key get NULL validation."""
        child = spark.createDataFrame(
            [("001", "POL1", "data1"), ("001", "POL2", "data2")],
            ["CO", "POL", "DATA"],
        )
        parent = spark.createDataFrame(
            [("001", "POL1"), ("001", "POL2")],
            ["P_CO", "P_POL"],
        )
        result = apply_cross_reference(
            child, parent,
            child_table="CVG",
            join_fields_child=["CO", "POL"],
            join_fields_parent=["P_CO", "P_POL"],
            severity="SEVERE",
        )
        # All records should have NULL VAL_CVG_CROSS_TABLE
        vals = result.select("VAL_CVG_CROSS_TABLE").collect()
        for row in vals:
            assert row["VAL_CVG_CROSS_TABLE"] is None

    def test_orphan_records_fail(self, spark):
        """Records without matching parent get SEVERE error."""
        child = spark.createDataFrame(
            [("999", "ORPHAN", "data")],
            ["CO", "POL", "DATA"],
        )
        parent = spark.createDataFrame(
            [("001", "POL1")],
            ["P_CO", "P_POL"],
        )
        result = apply_cross_reference(
            child, parent,
            child_table="CVG",
            join_fields_child=["CO", "POL"],
            join_fields_parent=["P_CO", "P_POL"],
            severity="SEVERE",
        )
        val = result.collect()[0]["VAL_CVG_CROSS_TABLE"]
        assert val is not None
        assert "SEVERE:" in val

    def test_empty_parent_all_fail(self, spark):
        """If parent is empty, all child records fail."""
        child = spark.createDataFrame(
            [("001", "POL1"), ("002", "POL2")],
            ["CO", "POL"],
        )
        parent = spark.createDataFrame([], "P_CO STRING, P_POL STRING")

        result = apply_cross_reference(
            child, parent,
            child_table="CVG",
            join_fields_child=["CO", "POL"],
            join_fields_parent=["P_CO", "P_POL"],
            severity="SEVERE",
        )
        vals = result.select("VAL_CVG_CROSS_TABLE").collect()
        for row in vals:
            assert row["VAL_CVG_CROSS_TABLE"] is not None

    def test_mixed_match_and_orphan(self, spark):
        """Some records match, some don't."""
        child = spark.createDataFrame(
            [("001", "POL1"), ("999", "ORPHAN")],
            ["CO", "POL"],
        )
        parent = spark.createDataFrame(
            [("001", "POL1")],
            ["P_CO", "P_POL"],
        )
        result = apply_cross_reference(
            child, parent,
            child_table="CVG",
            join_fields_child=["CO", "POL"],
            join_fields_parent=["P_CO", "P_POL"],
            severity="SEVERE",
        )
        rows = result.orderBy("CO").collect()
        assert rows[0]["VAL_CVG_CROSS_TABLE"] is None  # 001 matches
        assert rows[1]["VAL_CVG_CROSS_TABLE"] is not None  # 999 doesn't match


class TestCrossReferenceJoinProperty:
    """**Validates: Requirements 4** — Cross-Reference Join Correctness Property.

    Property: A child record passes cross-reference iff its join key exists
    in the parent table. Otherwise it fails with a SEVERE error.
    """

    @given(
        parent_keys=st.lists(
            st.tuples(
                st.text(min_size=1, max_size=5, alphabet="ABC123"),
                st.text(min_size=1, max_size=5, alphabet="XYZ789"),
            ),
            min_size=1,
            max_size=10,
            unique=True,
        ),
        child_keys=st.lists(
            st.tuples(
                st.text(min_size=1, max_size=5, alphabet="ABC123"),
                st.text(min_size=1, max_size=5, alphabet="XYZ789"),
            ),
            min_size=1,
            max_size=10,
        ),
    )
    @settings(max_examples=50, deadline=None)
    def test_cross_ref_correctness(self, spark, parent_keys, child_keys):
        """Child records match iff their key is in parent keys."""
        parent_set = set(parent_keys)

        parent_df = spark.createDataFrame(
            [(k[0], k[1]) for k in parent_keys], ["P_CO", "P_POL"]
        )
        child_df = spark.createDataFrame(
            [(k[0], k[1]) for k in child_keys], ["CO", "POL"]
        )

        result = apply_cross_reference(
            child_df, parent_df,
            child_table="CHILD",
            join_fields_child=["CO", "POL"],
            join_fields_parent=["P_CO", "P_POL"],
            severity="SEVERE",
        )

        rows = result.collect()
        for row in rows:
            key = (row["CO"], row["POL"])
            if key in parent_set:
                assert row["VAL_CHILD_CROSS_TABLE"] is None, f"Key {key} is in parent but got error"
            else:
                assert row["VAL_CHILD_CROSS_TABLE"] is not None, f"Key {key} not in parent but passed"
