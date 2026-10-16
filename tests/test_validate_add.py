# WARNING: These tests target the DEPRECATED codebase (_deprecated_src_do_not_use/). See option_b/tests/ for active tests.
"""Unit tests for validate_add.py - ADD field and cross-table validation."""

import pandas as pd
import pytest

from _deprecated_src_do_not_use.validate_add import validate_add, validate_add_cross_table, ADD_EXPECTED_COLUMNS


def _make_valid_add_row() -> dict:
    """Create a single fully valid ADD row."""
    return {
        "ADD_COMPANY_CODE": "001",
        "ADD_POLICY_NUMBER": "POL123456789",
        "ADD_ADDRESS_TYPE": "RS",
        "ADD_ADDRESS_SEQUENCE": "1",
        "ADD_LINE_1": "123 Main Street",
        "ADD_LINE_2": "Apt 4B",
        "ADD_CITY": "New York",
        "ADD_STATE": "NY",
        "ADD_ZIP_CODE": "10001",
        "ADD_COUNTRY": "US",
        "ADD_EFFECTIVE_DATE": "20100101",
        "ADD_PHONE": "2125551234",
    }


def _make_cnt_df() -> pd.DataFrame:
    """Create a small CNT DataFrame for cross-table tests."""
    return pd.DataFrame([{
        "CNT_COMPANY_CODE": "001",
        "CNT_POLICY_NUMBER": "POL123456789",
        "CNT_REINS_TYPE": "A",
    }])


class TestAddFieldValidation:
    def test_valid_row_produces_clean(self):
        """A fully valid ADD row should be CLEAN."""
        df = pd.DataFrame([_make_valid_add_row()])
        result = validate_add(df)
        assert result["ROW_SEVERITY"].iloc[0] == "CLEAN"

    def test_blank_line_1_severe(self):
        """Blank ADD_LINE_1 must produce SEVERE."""
        row = _make_valid_add_row()
        row["ADD_LINE_1"] = ""
        df = pd.DataFrame([row])
        result = validate_add(df)
        assert result["ROW_SEVERITY"].iloc[0] == "SEVERE"
        assert str(result["VAL_ADD_LINE_1"].iloc[0]).startswith("SEVERE")

    def test_invalid_address_type_severe(self):
        """Invalid ADD_ADDRESS_TYPE must produce SEVERE."""
        row = _make_valid_add_row()
        row["ADD_ADDRESS_TYPE"] = "XX"
        df = pd.DataFrame([row])
        result = validate_add(df)
        assert str(result["VAL_ADD_ADDRESS_TYPE"].iloc[0]).startswith("SEVERE")

    def test_blank_city_severe(self):
        """Blank ADD_CITY must produce SEVERE."""
        row = _make_valid_add_row()
        row["ADD_CITY"] = ""
        df = pd.DataFrame([row])
        result = validate_add(df)
        assert str(result["VAL_ADD_CITY"].iloc[0]).startswith("SEVERE")


class TestAddCrossTable:
    def test_matching_cnt_no_error(self):
        """ADD with matching CNT record should pass cross-table."""
        add_df = pd.DataFrame([_make_valid_add_row()])
        add_df = validate_add(add_df)
        cnt_df = _make_cnt_df()
        result = validate_add_cross_table(add_df, cnt_df)
        val = result["VAL_ADD_CROSS_TABLE"].iloc[0]
        assert val is None

    def test_no_matching_cnt_severe(self):
        """ADD without a matching CNT record must produce SEVERE."""
        row = _make_valid_add_row()
        row["ADD_COMPANY_CODE"] = "999"
        row["ADD_POLICY_NUMBER"] = "ORPHAN"
        add_df = pd.DataFrame([row])
        add_df = validate_add(add_df)
        cnt_df = _make_cnt_df()
        result = validate_add_cross_table(add_df, cnt_df)
        assert str(result["VAL_ADD_CROSS_TABLE"].iloc[0]).startswith("SEVERE")
        assert result["ROW_SEVERITY"].iloc[0] == "SEVERE"
