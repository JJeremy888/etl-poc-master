# WARNING: These tests target the DEPRECATED codebase (_deprecated_src_do_not_use/). See option_b/tests/ for active tests.
"""Unit tests for input_reader.py."""

import tempfile
from pathlib import Path

import pandas as pd
import pytest

from _deprecated_src_do_not_use.input_reader import read, EXPECTED_COLUMNS


def _create_valid_csv(path: Path, rows: int = 5) -> None:
    """Create a valid CSV file with all 32 expected columns."""
    data = {col: ["test"] * rows for col in EXPECTED_COLUMNS}
    df = pd.DataFrame(data)
    df.to_csv(path, index=False)


class TestRead:
    def test_valid_file_reads_correctly(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        _create_valid_csv(csv_path, rows=10)
        df = read(csv_path)
        assert len(df) == 10
        assert len(df.columns) == 32

    def test_missing_file_raises_file_not_found(self, tmp_path):
        csv_path = tmp_path / "nonexistent.csv"
        with pytest.raises(FileNotFoundError, match="Input CSV not found"):
            read(csv_path)

    def test_missing_columns_raises_value_error(self, tmp_path):
        csv_path = tmp_path / "incomplete.csv"
        # Only 3 columns
        df = pd.DataFrame({
            "CNT_ISSUE_SYSTEM": ["AA"],
            "CNT_COMPANY_CODE": ["001"],
            "CNT_POLICY_NUMBER": ["POL123"],
        })
        df.to_csv(csv_path, index=False)

        with pytest.raises(ValueError, match="Missing required columns"):
            read(csv_path)

    def test_missing_columns_lists_all_absent(self, tmp_path):
        csv_path = tmp_path / "partial.csv"
        # Include only first 5 columns
        data = {col: ["x"] for col in EXPECTED_COLUMNS[:5]}
        pd.DataFrame(data).to_csv(csv_path, index=False)

        with pytest.raises(ValueError) as exc_info:
            read(csv_path)

        # Should mention at least one missing column
        assert "CNT_SERV_AGENT" in str(exc_info.value)

    def test_chunked_reading_produces_same_result(self, tmp_path):
        csv_path = tmp_path / "large.csv"
        _create_valid_csv(csv_path, rows=25000)
        df = read(csv_path, chunksize=5000)
        assert len(df) == 25000

    def test_all_32_expected_columns_defined(self):
        assert len(EXPECTED_COLUMNS) == 32
        assert all(col.startswith("CNT_") for col in EXPECTED_COLUMNS)


class TestPipeDelimiter:
    def test_reader_uses_pipe_delimiter_from_config(self, tmp_path):
        """Confirm the reader uses PIPE delimiter when config sets delimiter to PIPE."""
        # Create a pipe-delimited file
        csv_path = tmp_path / "pipe_data.csv"
        data = {col: ["test"] * 3 for col in EXPECTED_COLUMNS}
        df = pd.DataFrame(data)
        df.to_csv(csv_path, index=False, sep="|")

        # Create a config with PIPE delimiter
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            "project: TEST\n"
            "input:\n"
            "  format: CSV\n"
            "  delimiter: PIPE\n"
            "  encoding: UTF-8\n"
            "  has_header: true\n"
            "output:\n"
            "  format: CSV\n"
            "  delimiter: PIPE\n"
            "  encoding: UTF-8\n"
            "  clean_suffix: _clean\n"
            "  warning_suffix: _warning\n"
            "  severe_suffix: _severe\n",
            encoding="utf-8",
        )

        from _deprecated_src_do_not_use.config_loader import load_config
        config = load_config(config_path)
        result = read(csv_path, config=config)
        assert len(result) == 3
        assert len(result.columns) == 32
