# WARNING: These tests target the DEPRECATED codebase (_deprecated_src_do_not_use/). See option_b/tests/ for active tests.
"""Unit tests for validate_rol.py - ROL field and cross-table validation."""

import pandas as pd
import pytest

from _deprecated_src_do_not_use.validate_rol import validate_rol, validate_rol_cross_table, ROL_EXPECTED_COLUMNS


def _make_valid_rol_row() -> dict:
    """Create a single fully valid ROL row."""
    return {
        "ROL_COMPANY_CODE": "001",
        "ROL_POLICY_NUMBER": "POL123456789",
        "ROL_ROLE_TYPE": "OW",
        "ROL_ROLE_SEQUENCE": "1",
        "ROL_FIRST_NAME": "John",
        "ROL_LAST_NAME": "Smith",
        "ROL_DATE_OF_BIRTH": "19800115",
        "ROL_SEX_CODE": "M",
        "ROL_SSN_TIN": "123456789",
        "ROL_RELATIONSHIP": "SE",
        "ROL_PERCENT": "100",
        "ROL_EFFECTIVE_DATE": "20100101",
    }


def _make_cnt_df() -> pd.DataFrame:
    """Create a small CNT DataFrame for cross-table tests."""
    return pd.DataFrame([{
        "CNT_COMPANY_CODE": "001",
        "CNT_POLICY_NUMBER": "POL123456789",
        "CNT_REINS_TYPE": "A",
    }])


class TestRolFieldValidation:
    def test_valid_row_produces_clean(self):
        """A fully valid ROL row should be CLEAN."""
        df = pd.DataFrame([_make_valid_rol_row()])
        result = validate_rol(df)
        assert result["ROW_SEVERITY"].iloc[0] == "CLEAN"

    def test_blank_first_name_severe(self):
        """Blank ROL_FIRST_NAME must produce SEVERE."""
        row = _make_valid_rol_row()
        row["ROL_FIRST_NAME"] = ""
        df = pd.DataFrame([row])
        result = validate_rol(df)
        assert result["ROW_SEVERITY"].iloc[0] == "SEVERE"
        assert str(result["VAL_ROL_FIRST_NAME"].iloc[0]).startswith("SEVERE")

    def test_invalid_role_type_severe(self):
        """Invalid ROL_ROLE_TYPE must produce SEVERE."""
        row = _make_valid_rol_row()
        row["ROL_ROLE_TYPE"] = "ZZ"
        df = pd.DataFrame([row])
        result = validate_rol(df)
        assert str(result["VAL_ROL_ROLE_TYPE"].iloc[0]).startswith("SEVERE")

    def test_non_numeric_sequence_severe(self):
        """Non-numeric ROL_ROLE_SEQUENCE must produce SEVERE."""
        row = _make_valid_rol_row()
        row["ROL_ROLE_SEQUENCE"] = "ABC"
        df = pd.DataFrame([row])
        result = validate_rol(df)
        assert str(result["VAL_ROL_ROLE_SEQUENCE"].iloc[0]).startswith("SEVERE")


class TestRolCrossTable:
    def test_matching_cnt_no_error(self):
        """ROL with matching CNT record should pass cross-table."""
        rol_df = pd.DataFrame([_make_valid_rol_row()])
        rol_df = validate_rol(rol_df)
        cnt_df = _make_cnt_df()
        result = validate_rol_cross_table(rol_df, cnt_df)
        val = result["VAL_ROL_CROSS_TABLE"].iloc[0]
        assert val is None

    def test_no_matching_cnt_severe(self):
        """ROL without a matching CNT record must produce SEVERE."""
        row = _make_valid_rol_row()
        row["ROL_COMPANY_CODE"] = "999"
        row["ROL_POLICY_NUMBER"] = "ORPHAN"
        rol_df = pd.DataFrame([row])
        rol_df = validate_rol(rol_df)
        cnt_df = _make_cnt_df()
        result = validate_rol_cross_table(rol_df, cnt_df)
        assert str(result["VAL_ROL_CROSS_TABLE"].iloc[0]).startswith("SEVERE")
        assert result["ROW_SEVERITY"].iloc[0] == "SEVERE"
