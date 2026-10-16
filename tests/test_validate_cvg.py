# WARNING: These tests target the DEPRECATED codebase (_deprecated_src_do_not_use/). See option_b/tests/ for active tests.
"""Unit tests for validate_cvg.py - CVG field and cross-table validation."""

import pandas as pd
import pytest

from _deprecated_src_do_not_use.validate_cvg import validate_cvg, validate_cvg_cross_table, CVG_EXPECTED_COLUMNS


def _make_valid_cvg_row() -> dict:
    """Create a single fully valid CVG row."""
    return {
        "CVG_COMPANY_CODE": "001",
        "CVG_POLICY_NUMBER": "POL123456789",
        "CVG_COVERAGE_ID": "COV000001",
        "CVG_PRODUCT_TYPE": "T",
        "CVG_PLAN_CODE": "PLAN000001",
        "CVG_TYPE": "BASE",
        "CVG_STATUS": "01",
        "CVG_EFFECTIVE_DATE": "20100101",
        "CVG_EXPIRY_DATE": "20500101",
        "CVG_ISSUE_AGE": "35",
        "CVG_FACE_AMOUNT": "500000",
        "CVG_REINS_TYPE": "A",
        "CVG_REINS_PERCENT": "50",
        "CVG_RATE_CLASS": "ST",
        "CVG_SMOKER_STATUS": "N",
    }


def _make_cnt_df() -> pd.DataFrame:
    """Create a small CNT DataFrame for cross-table tests."""
    return pd.DataFrame([{
        "CNT_COMPANY_CODE": "001",
        "CNT_POLICY_NUMBER": "POL123456789",
        "CNT_REINS_TYPE": "A",
    }])


class TestCvgFieldValidation:
    def test_valid_row_produces_clean(self):
        """A fully valid CVG row should be CLEAN."""
        df = pd.DataFrame([_make_valid_cvg_row()])
        result = validate_cvg(df)
        assert result["ROW_SEVERITY"].iloc[0] == "CLEAN"

    def test_blank_company_code_severe(self):
        """Blank CVG_COMPANY_CODE must produce SEVERE."""
        row = _make_valid_cvg_row()
        row["CVG_COMPANY_CODE"] = ""
        df = pd.DataFrame([row])
        result = validate_cvg(df)
        assert result["ROW_SEVERITY"].iloc[0] == "SEVERE"
        assert str(result["VAL_CVG_COMPANY_CODE"].iloc[0]).startswith("SEVERE")

    def test_invalid_product_type_severe(self):
        """Invalid CVG_PRODUCT_TYPE must produce SEVERE."""
        row = _make_valid_cvg_row()
        row["CVG_PRODUCT_TYPE"] = "X"
        df = pd.DataFrame([row])
        result = validate_cvg(df)
        assert str(result["VAL_CVG_PRODUCT_TYPE"].iloc[0]).startswith("SEVERE")

    def test_invalid_effective_date_severe(self):
        """Invalid CVG_EFFECTIVE_DATE must produce SEVERE."""
        row = _make_valid_cvg_row()
        row["CVG_EFFECTIVE_DATE"] = "BADDATE1"
        df = pd.DataFrame([row])
        result = validate_cvg(df)
        assert str(result["VAL_CVG_EFFECTIVE_DATE"].iloc[0]).startswith("SEVERE")

    def test_expiry_before_effective_severe(self):
        """CVG_EXPIRY_DATE before CVG_EFFECTIVE_DATE must produce SEVERE."""
        row = _make_valid_cvg_row()
        row["CVG_EFFECTIVE_DATE"] = "20200101"
        row["CVG_EXPIRY_DATE"] = "20190101"
        df = pd.DataFrame([row])
        result = validate_cvg(df)
        assert str(result["VAL_CVG_EXPIRY_DATE"].iloc[0]).startswith("SEVERE")


class TestCvgCrossTable:
    def test_matching_cnt_no_error(self):
        """CVG with matching CNT record and matching REINS_TYPE should pass."""
        cvg_row = _make_valid_cvg_row()
        cvg_df = pd.DataFrame([cvg_row])
        cvg_df = validate_cvg(cvg_df)
        cnt_df = _make_cnt_df()
        result = validate_cvg_cross_table(cvg_df, cnt_df)
        val = result["VAL_CVG_CROSS_TABLE"].iloc[0]
        assert val is None or not str(val).startswith("SEVERE")

    def test_no_matching_cnt_severe(self):
        """CVG without a matching CNT record must produce SEVERE."""
        cvg_row = _make_valid_cvg_row()
        cvg_row["CVG_COMPANY_CODE"] = "999"
        cvg_row["CVG_POLICY_NUMBER"] = "ORPHAN"
        cvg_df = pd.DataFrame([cvg_row])
        cvg_df = validate_cvg(cvg_df)
        cnt_df = _make_cnt_df()
        result = validate_cvg_cross_table(cvg_df, cnt_df)
        assert str(result["VAL_CVG_CROSS_TABLE"].iloc[0]).startswith("SEVERE")
        assert result["ROW_SEVERITY"].iloc[0] == "SEVERE"

    def test_reins_type_mismatch_severe(self):
        """CVG_REINS_TYPE mismatching CNT_REINS_TYPE must produce SEVERE."""
        cvg_row = _make_valid_cvg_row()
        cvg_row["CVG_REINS_TYPE"] = "F"  # CNT has "A"
        cvg_df = pd.DataFrame([cvg_row])
        cvg_df = validate_cvg(cvg_df)
        cnt_df = _make_cnt_df()
        result = validate_cvg_cross_table(cvg_df, cnt_df)
        assert "does not match CNT_REINS_TYPE" in str(result["VAL_CVG_CROSS_TABLE"].iloc[0])
        assert result["ROW_SEVERITY"].iloc[0] == "SEVERE"
