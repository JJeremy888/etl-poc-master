# WARNING: These tests target the DEPRECATED codebase (_deprecated_src_do_not_use/). See option_b/tests/ for active tests.
"""Unit tests for output_writer.py — output format validation."""

from pathlib import Path

import pandas as pd
import pytest

from _deprecated_src_do_not_use.input_reader import EXPECTED_COLUMNS
from _deprecated_src_do_not_use.output_writer import write, split_by_severity, generate_summary, ensure_output_dir


def _make_validated_df() -> pd.DataFrame:
    """Create a small validated DataFrame with mixed severities and VAL_ columns."""
    data = {col: ["TEST"] * 5 for col in EXPECTED_COLUMNS}
    data["CNT_COMPANY_CODE"] = ["001", "002", "", "004", ""]
    data["CNT_POLICY_NUMBER"] = ["P1", "P2", "P3", "P4", "P5"]
    data["VAL_CNT_COMPANY_CODE"] = [None, None, "SEVERE: Must not be blank", None, "SEVERE: Must not be blank"]
    data["VAL_CNT_POLICY_NUMBER"] = [None, "WARNING: too short", None, None, None]
    data["VAL_CNT_SERV_AGENT"] = [None, None, None, None, "WARNING: blank"]
    data["ROW_SEVERITY"] = ["CLEAN", "WARNING", "SEVERE", "CLEAN", "SEVERE"]
    data["TEST_EXPECTED_ISSUE"] = ["", "warn issue", "severe issue", "", "severe issue 2"]
    return pd.DataFrame(data)


class TestSplitBySeverity:
    def test_correct_split(self):
        df = _make_validated_df()
        clean, warning, severe = split_by_severity(df)
        assert len(clean) == 2
        assert len(warning) == 1
        assert len(severe) == 2

    def test_no_overlap(self):
        df = _make_validated_df()
        clean, warning, severe = split_by_severity(df)
        total = len(clean) + len(warning) + len(severe)
        assert total == len(df)


class TestWrite:
    def test_output_files_created(self, tmp_path):
        df = _make_validated_df()
        write(df, tmp_path, input_file="test.csv")
        assert (tmp_path / "cnt_clean.csv").exists()
        assert (tmp_path / "cnt_warning.csv").exists()
        assert (tmp_path / "cnt_severe.csv").exists()
        assert (tmp_path / "cnt_summary.txt").exists()

    def test_clean_file_has_33_columns(self, tmp_path):
        """cnt_clean.csv has exactly 33 columns: 32 CNT fields + ROW_SEVERITY."""
        df = _make_validated_df()
        write(df, tmp_path)
        clean_df = pd.read_csv(tmp_path / "cnt_clean.csv")
        assert len(clean_df.columns) == 33

    def test_warning_file_has_34_columns(self, tmp_path):
        """cnt_warning.csv has exactly 34 columns: 32 CNT fields + ERROR_SUMMARY + ROW_SEVERITY."""
        df = _make_validated_df()
        write(df, tmp_path)
        warning_df = pd.read_csv(tmp_path / "cnt_warning.csv")
        assert len(warning_df.columns) == 34

    def test_severe_file_has_34_columns(self, tmp_path):
        """cnt_severe.csv has exactly 34 columns: 32 CNT fields + ERROR_SUMMARY + ROW_SEVERITY."""
        df = _make_validated_df()
        write(df, tmp_path)
        severe_df = pd.read_csv(tmp_path / "cnt_severe.csv")
        assert len(severe_df.columns) == 34

    def test_clean_file_contains_only_clean_rows(self, tmp_path):
        df = _make_validated_df()
        write(df, tmp_path)
        clean_df = pd.read_csv(tmp_path / "cnt_clean.csv")
        assert all(clean_df["ROW_SEVERITY"] == "CLEAN")

    def test_warning_file_contains_only_warning_rows(self, tmp_path):
        df = _make_validated_df()
        write(df, tmp_path)
        warning_df = pd.read_csv(tmp_path / "cnt_warning.csv")
        assert all(warning_df["ROW_SEVERITY"] == "WARNING")

    def test_severe_file_contains_only_severe_rows(self, tmp_path):
        df = _make_validated_df()
        write(df, tmp_path)
        severe_df = pd.read_csv(tmp_path / "cnt_severe.csv")
        assert all(severe_df["ROW_SEVERITY"] == "SEVERE")

    def test_no_val_columns_in_output(self, tmp_path):
        """VAL_ columns must not appear in any output file."""
        df = _make_validated_df()
        write(df, tmp_path)
        for filename in ("cnt_clean.csv", "cnt_warning.csv", "cnt_severe.csv"):
            out_df = pd.read_csv(tmp_path / filename)
            val_cols = [c for c in out_df.columns if c.startswith("VAL_")]
            assert val_cols == [], f"Found VAL_ columns in {filename}: {val_cols}"

    def test_no_test_expected_issue_in_output(self, tmp_path):
        """TEST_EXPECTED_ISSUE column must not appear in any output file."""
        df = _make_validated_df()
        write(df, tmp_path)
        for filename in ("cnt_clean.csv", "cnt_warning.csv", "cnt_severe.csv"):
            out_df = pd.read_csv(tmp_path / filename)
            assert "TEST_EXPECTED_ISSUE" not in out_df.columns, f"Found TEST_EXPECTED_ISSUE in {filename}"

    def test_error_summary_not_empty_in_warning(self, tmp_path):
        """ERROR_SUMMARY must not be empty in cnt_warning.csv."""
        df = _make_validated_df()
        write(df, tmp_path)
        warning_df = pd.read_csv(tmp_path / "cnt_warning.csv")
        assert "ERROR_SUMMARY" in warning_df.columns
        for val in warning_df["ERROR_SUMMARY"]:
            assert pd.notna(val) and str(val).strip() != "", "ERROR_SUMMARY must not be empty"

    def test_error_summary_not_empty_in_severe(self, tmp_path):
        """ERROR_SUMMARY must not be empty in cnt_severe.csv."""
        df = _make_validated_df()
        write(df, tmp_path)
        severe_df = pd.read_csv(tmp_path / "cnt_severe.csv")
        assert "ERROR_SUMMARY" in severe_df.columns
        for val in severe_df["ERROR_SUMMARY"]:
            assert pd.notna(val) and str(val).strip() != "", "ERROR_SUMMARY must not be empty"

    def test_error_summary_contains_field_name(self, tmp_path):
        """ERROR_SUMMARY should include the field name before the message."""
        df = _make_validated_df()
        write(df, tmp_path)
        warning_df = pd.read_csv(tmp_path / "cnt_warning.csv")
        summary = str(warning_df["ERROR_SUMMARY"].iloc[0])
        assert "CNT_POLICY_NUMBER:" in summary

    def test_error_summary_uses_pipe_separator(self, tmp_path):
        """Multiple errors should be separated by pipe."""
        df = _make_validated_df()
        write(df, tmp_path)
        severe_df = pd.read_csv(tmp_path / "cnt_severe.csv")
        # Row index 4 has both SEVERE on company code and WARNING on serv_agent
        summaries = severe_df["ERROR_SUMMARY"].tolist()
        # At least one row should have pipe separator (the one with 2 errors)
        has_pipe = any("|" in str(s) for s in summaries)
        assert has_pipe, "Expected at least one row with multiple errors separated by pipe"

    def test_clean_file_no_error_summary(self, tmp_path):
        """cnt_clean.csv should NOT have ERROR_SUMMARY column."""
        df = _make_validated_df()
        write(df, tmp_path)
        clean_df = pd.read_csv(tmp_path / "cnt_clean.csv")
        assert "ERROR_SUMMARY" not in clean_df.columns

    def test_output_dir_created_if_absent(self, tmp_path):
        new_dir = tmp_path / "subdir" / "output"
        df = _make_validated_df()
        write(df, new_dir)
        assert new_dir.exists()

    def test_summary_contains_total_count(self, tmp_path):
        df = _make_validated_df()
        write(df, tmp_path, input_file="sample.csv")
        summary = (tmp_path / "cnt_summary.txt").read_text()
        assert "Total rows" in summary
        assert "5" in summary


class TestGenerateSummary:
    def test_summary_format(self):
        df = _make_validated_df()
        summary = generate_summary(df, "test.csv")
        assert "Policy Loader Validation Summary" in summary
        assert "CLEAN" in summary
        assert "WARNING" in summary
        assert "SEVERE" in summary
        assert "test.csv" in summary
        assert "Top 5 Failure Reasons (SEVERE)" in summary
        assert "Top 3 Failure Reasons (WARNING)" in summary


class TestEnsureOutputDir:
    def test_creates_directory(self, tmp_path):
        new_dir = tmp_path / "new_output"
        ensure_output_dir(new_dir)
        assert new_dir.exists()

    def test_existing_directory_no_error(self, tmp_path):
        ensure_output_dir(tmp_path)


class TestPipeDelimiterOutput:
    def test_writer_uses_pipe_delimiter_from_config(self, tmp_path):
        """Confirm the writer uses PIPE delimiter when config sets delimiter to PIPE."""
        df = _make_validated_df()

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
        write(df, tmp_path, input_file="test.csv", config=config)

        # Read back the clean file with pipe delimiter
        clean_df = pd.read_csv(tmp_path / "cnt_clean.csv", sep="|")
        assert len(clean_df.columns) == 33
        assert "ROW_SEVERITY" in clean_df.columns
        assert all(clean_df["ROW_SEVERITY"] == "CLEAN")
