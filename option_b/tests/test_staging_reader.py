"""Tests for staging_reader module.

**Validates: Requirements 7** — Missing Table Graceful Skip Property.
"""

import os
import tempfile
import shutil

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis import HealthCheck
from pyspark.sql.types import StructType

from option_b.input.staging_reader import read_staging_table, read_all_staging_tables


class TestReadStagingTable:
    """Unit tests for read_staging_table."""

    def test_reads_existing_csv(self, spark, staging_dir):
        """Reads an existing CSV file correctly."""
        # Write a test CSV
        csv_path = os.path.join(staging_dir, "test_table.csv")
        with open(csv_path, "w") as f:
            f.write("col1,col2\n")
            f.write("a,b\n")
            f.write("c,d\n")

        config = {"staging_dir": staging_dir}
        df = read_staging_table(spark, "test_table", config)
        assert df.count() == 2
        assert "col1" in df.columns
        assert "col2" in df.columns

    def test_missing_file_returns_empty(self, spark, tmp_dir):
        """Missing file returns empty DataFrame without raising."""
        config = {"staging_dir": tmp_dir}
        df = read_staging_table(spark, "nonexistent_table", config)
        assert df.count() == 0
        assert isinstance(df.schema, StructType)

    def test_empty_file_returns_empty(self, spark, tmp_dir):
        """Empty file (header only) returns empty DataFrame."""
        staging = os.path.join(tmp_dir, "staging")
        os.makedirs(staging)
        csv_path = os.path.join(staging, "empty.csv")
        with open(csv_path, "w") as f:
            f.write("col1,col2\n")

        config = {"staging_dir": staging}
        df = read_staging_table(spark, "empty", config)
        assert df.count() == 0


class TestReadAllStagingTables:
    """Unit tests for read_all_staging_tables."""

    def test_reads_multiple_tables(self, spark, staging_dir):
        """Reads multiple tables into a dictionary."""
        # Create test files
        for name in ["alpha", "beta"]:
            csv_path = os.path.join(staging_dir, f"{name}.csv")
            with open(csv_path, "w") as f:
                f.write("x,y\n1,2\n")

        config = {"staging_dir": staging_dir}
        result = read_all_staging_tables(spark, ["alpha", "beta"], config)
        assert "alpha" in result
        assert "beta" in result
        assert result["alpha"].count() == 1
        assert result["beta"].count() == 1

    def test_mixed_existing_and_missing(self, spark, staging_dir):
        """Mix of existing and missing tables works gracefully."""
        csv_path = os.path.join(staging_dir, "exists.csv")
        with open(csv_path, "w") as f:
            f.write("a,b\n1,2\n")

        config = {"staging_dir": staging_dir}
        result = read_all_staging_tables(spark, ["exists", "missing"], config)
        assert result["exists"].count() == 1
        assert result["missing"].count() == 0


class TestMissingTableGracefulSkipProperty:
    """**Validates: Requirements 7** — Missing Table Graceful Skip Property.

    Property: For any table name that does not exist as a file, the reader
    must return an empty DataFrame (never raise an exception).
    """

    @given(
        table_name=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_"),
            min_size=1,
            max_size=20,
        )
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_any_missing_table_returns_empty_df(self, spark, tmp_dir, table_name):
        """Any random table name that doesn't exist returns empty DF."""
        config = {"staging_dir": tmp_dir}
        df = read_staging_table(spark, table_name, config)
        assert df.count() == 0
