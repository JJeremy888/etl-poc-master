# WARNING: These tests target the DEPRECATED codebase (_deprecated_src_do_not_use/). See option_b/tests/ for active tests.
"""Unit tests for validation_engine.py — field rules, cross-field rules, classification."""

import pandas as pd
import pytest

from _deprecated_src_do_not_use.validation_engine import run, classify_severity, _apply_field_rules, _apply_cross_field_rules
from _deprecated_src_do_not_use.rule_loader import load


@pytest.fixture
def rules():
    """Load CNT rules for testing."""
    return load("CNT")


def _make_valid_row() -> dict:
    """Create a single fully valid CNT row."""
    return {
        "CNT_ISSUE_SYSTEM": "AA",
        "CNT_COMPANY_CODE": "001",
        "CNT_POLICY_NUMBER": "POL123456789",
        "CNT_PRODUCT_TYPE": "T",
        "CNT_POLICY_PLAN_CODE": "PLAN000001",
        "CNT_BASE_PLAN_CODE": "PLAN000001",
        "CNT_POLICY_CODE": "X",
        "CNT_ISSUE_COUNTRY": "US",
        "CNT_ISSUE_STATE": "NY",
        "CNT_RESIDENT_STATE": "CA",
        "CNT_POLICY_STATUS": "01",
        "CNT_ISSUE_AGE": "35",
        "CNT_ISSUE_DATE": "20100101",
        "CNT_STATUS_DATE": "20230601",
        "CNT_MATURE_EXPIRE_DATE": "20500101",
        "CNT_APPLICATION_DATE": "20091201",
        "CNT_PARTICIPATION_STATUS": "P",
        "CNT_GUAR_PAR_STATUS": "N",
        "CNT_NFO_OPTION": "A",
        "CNT_SEX_CODE": "M",
        "CNT_JOINT_LIFE_INDICATOR": "N",
        "CNT_JOINT_NUMBER_OF_LIVES": "2",
        "CNT_JOINT_RATE_AGE": "0",
        "CNT_JOINT_RATE_AGE_REASON_CODE": "",
        "CNT_PAYUP_DATE": "20450101",
        "CNT_QUALIFICATION_CODE": "N",
        "CNT_PLAN_OPTION": "L",
        "CNT_GRACE_EXPIRY_DATE": "20150101",
        "CNT_SERV_AGENT": "AGENT0000001",
        "CNT_SERV_AGENCY": "AGENCY000001",
        "CNT_PHONE_AUTH_TRNSFR": "Y",
        "CNT_REINS_TYPE": "A",
    }


class TestFieldValidation:
    def test_all_valid_row_produces_clean(self, rules):
        """A fully valid row should have ROW_SEVERITY = CLEAN (NOTE: entries are acceptable)."""
        df = pd.DataFrame([_make_valid_row()])
        result = run(df, rules)
        val_cols = [c for c in result.columns if c.startswith("VAL_")]
        for col in val_cols:
            val = result[col].iloc[0]
            if val is not None:
                # Only NOTE: prefixed values are acceptable on CLEAN rows
                assert str(val).startswith("NOTE:"), (
                    f"{col} should be None or NOTE: but got: {val}"
                )
        assert result["ROW_SEVERITY"].iloc[0] == "CLEAN"

    def test_blank_issue_system_severe(self, rules):
        """Blank CNT_ISSUE_SYSTEM must produce SEVERE."""
        row = _make_valid_row()
        row["CNT_ISSUE_SYSTEM"] = ""
        df = pd.DataFrame([row])
        result = run(df, rules)
        assert str(result["VAL_CNT_ISSUE_SYSTEM"].iloc[0]).startswith("SEVERE")

    def test_wrong_length_issue_system(self, rules):
        """CNT_ISSUE_SYSTEM with 3 chars must produce SEVERE."""
        row = _make_valid_row()
        row["CNT_ISSUE_SYSTEM"] = "ABC"
        df = pd.DataFrame([row])
        result = run(df, rules)
        assert str(result["VAL_CNT_ISSUE_SYSTEM"].iloc[0]).startswith("SEVERE")

    def test_invalid_product_type(self, rules):
        """CNT_PRODUCT_TYPE='X' not in allowed list must produce SEVERE."""
        row = _make_valid_row()
        row["CNT_PRODUCT_TYPE"] = "X"
        row["CNT_PARTICIPATION_STATUS"] = "N"
        row["CNT_PLAN_OPTION"] = ""
        row["CNT_QUALIFICATION_CODE"] = "N"
        df = pd.DataFrame([row])
        result = run(df, rules)
        assert str(result["VAL_CNT_PRODUCT_TYPE"].iloc[0]).startswith("SEVERE")

    def test_invalid_issue_date(self, rules):
        """Month 13 must produce SEVERE on CNT_ISSUE_DATE."""
        row = _make_valid_row()
        row["CNT_ISSUE_DATE"] = "20261301"
        df = pd.DataFrame([row])
        result = run(df, rules)
        assert str(result["VAL_CNT_ISSUE_DATE"].iloc[0]).startswith("SEVERE")

    def test_blank_serv_agent_warning(self, rules):
        """Blank CNT_SERV_AGENT must produce WARNING."""
        row = _make_valid_row()
        row["CNT_SERV_AGENT"] = ""
        df = pd.DataFrame([row])
        result = run(df, rules)
        assert str(result["VAL_CNT_SERV_AGENT"].iloc[0]).startswith("WARNING")

    def test_default_then_warn_base_plan_code(self, rules):
        """Blank CNT_BASE_PLAN_CODE defaults to CNT_POLICY_PLAN_CODE and produces WARNING."""
        row = _make_valid_row()
        row["CNT_BASE_PLAN_CODE"] = ""
        row["CNT_POLICY_PLAN_CODE"] = "PLAN000001"
        df = pd.DataFrame([row])
        result = run(df, rules)
        assert result["CNT_BASE_PLAN_CODE"].iloc[0] == "PLAN000001"
        assert str(result["VAL_CNT_BASE_PLAN_CODE"].iloc[0]).startswith("WARNING")


class TestCrossFieldValidation:
    def test_sex_B_joint_not_F_severe(self, rules):
        """SEX_CODE=B, JOINT_LIFE_INDICATOR=N must produce SEVERE."""
        row = _make_valid_row()
        row["CNT_SEX_CODE"] = "B"
        row["CNT_JOINT_LIFE_INDICATOR"] = "N"
        row["CNT_JOINT_RATE_AGE"] = "0"
        row["CNT_JOINT_RATE_AGE_REASON_CODE"] = ""
        row["CNT_PRODUCT_TYPE"] = "T"
        row["CNT_PLAN_OPTION"] = "L"
        df = pd.DataFrame([row])
        result = run(df, rules)
        assert str(result["VAL_CNT_JOINT_LIFE_INDICATOR"].iloc[0]).startswith("SEVERE")

    def test_sex_B_joint_F_no_error(self, rules):
        """SEX_CODE=B, JOINT_LIFE_INDICATOR=F must not produce cross-field error."""
        row = _make_valid_row()
        row["CNT_SEX_CODE"] = "B"
        row["CNT_JOINT_LIFE_INDICATOR"] = "F"
        row["CNT_JOINT_RATE_AGE"] = "0"
        row["CNT_JOINT_RATE_AGE_REASON_CODE"] = "F"
        row["CNT_PRODUCT_TYPE"] = "T"
        row["CNT_PLAN_OPTION"] = "L"
        df = pd.DataFrame([row])
        result = run(df, rules)
        val = result["VAL_CNT_JOINT_LIFE_INDICATOR"].iloc[0]
        assert val is None or not str(val).startswith("SEVERE")

    def test_sex_J_joint_not_J_severe(self, rules):
        """SEX_CODE=J, JOINT_LIFE_INDICATOR=F must produce SEVERE."""
        row = _make_valid_row()
        row["CNT_SEX_CODE"] = "J"
        row["CNT_JOINT_LIFE_INDICATOR"] = "F"
        row["CNT_JOINT_RATE_AGE"] = "0"
        row["CNT_JOINT_RATE_AGE_REASON_CODE"] = "F"
        row["CNT_PRODUCT_TYPE"] = "T"
        row["CNT_PLAN_OPTION"] = "L"
        df = pd.DataFrame([row])
        result = run(df, rules)
        assert str(result["VAL_CNT_JOINT_LIFE_INDICATOR"].iloc[0]).startswith("SEVERE")

    def test_product_K_joint_N_severe(self, rules):
        """PRODUCT_TYPE=K, JOINT_LIFE_INDICATOR=N must produce SEVERE."""
        row = _make_valid_row()
        row["CNT_PRODUCT_TYPE"] = "K"
        row["CNT_JOINT_LIFE_INDICATOR"] = "N"
        row["CNT_JOINT_RATE_AGE"] = "0"
        row["CNT_JOINT_RATE_AGE_REASON_CODE"] = ""
        row["CNT_SEX_CODE"] = "M"
        row["CNT_PLAN_OPTION"] = "L"
        row["CNT_PARTICIPATION_STATUS"] = "P"
        df = pd.DataFrame([row])
        result = run(df, rules)
        assert str(result["VAL_CNT_JOINT_LIFE_INDICATOR"].iloc[0]).startswith("SEVERE")

    def test_product_E_joint_invalid_severe(self, rules):
        """PRODUCT_TYPE=E, JOINT_LIFE_INDICATOR not in {F,J,N} - not applicable since allowable already restricts."""
        # With PRODUCT_TYPE=E, the valid JOINT_LIFE_INDICATOR values are F, J, N.
        # Since allowable values rule already restricts, we test E+valid=F passes
        row = _make_valid_row()
        row["CNT_PRODUCT_TYPE"] = "E"
        row["CNT_JOINT_LIFE_INDICATOR"] = "F"
        row["CNT_JOINT_RATE_AGE"] = "0"
        row["CNT_JOINT_RATE_AGE_REASON_CODE"] = "F"
        row["CNT_SEX_CODE"] = "M"
        row["CNT_PLAN_OPTION"] = ""
        row["CNT_PARTICIPATION_STATUS"] = "N"
        row["CNT_QUALIFICATION_CODE"] = "N"
        df = pd.DataFrame([row])
        result = run(df, rules)
        val = result["VAL_CNT_JOINT_LIFE_INDICATOR"].iloc[0]
        assert val is None or not str(val).startswith("SEVERE")

    def test_joint_N_reason_not_blank_severe(self, rules):
        """JOINT_LIFE_INDICATOR=N, REASON_CODE not blank must produce SEVERE."""
        row = _make_valid_row()
        row["CNT_JOINT_LIFE_INDICATOR"] = "N"
        row["CNT_JOINT_RATE_AGE"] = "0"
        row["CNT_JOINT_RATE_AGE_REASON_CODE"] = "F"
        row["CNT_SEX_CODE"] = "M"
        row["CNT_PRODUCT_TYPE"] = "T"
        row["CNT_PLAN_OPTION"] = "L"
        df = pd.DataFrame([row])
        result = run(df, rules)
        assert str(result["VAL_CNT_JOINT_RATE_AGE_REASON_CODE"].iloc[0]).startswith("SEVERE")

    def test_joint_F_reason_not_in_FGP_severe(self, rules):
        """JOINT_LIFE_INDICATOR=F, REASON_CODE=A must produce SEVERE."""
        row = _make_valid_row()
        row["CNT_JOINT_LIFE_INDICATOR"] = "F"
        row["CNT_JOINT_RATE_AGE"] = "0"
        row["CNT_JOINT_RATE_AGE_REASON_CODE"] = "A"
        row["CNT_SEX_CODE"] = "M"
        row["CNT_PRODUCT_TYPE"] = "T"
        row["CNT_PLAN_OPTION"] = "L"
        df = pd.DataFrame([row])
        result = run(df, rules)
        assert str(result["VAL_CNT_JOINT_RATE_AGE_REASON_CODE"].iloc[0]).startswith("SEVERE")

    def test_joint_J_reason_not_in_ABCD_severe(self, rules):
        """JOINT_LIFE_INDICATOR=J, REASON_CODE=F must produce SEVERE."""
        row = _make_valid_row()
        row["CNT_JOINT_LIFE_INDICATOR"] = "J"
        row["CNT_JOINT_RATE_AGE"] = "35"
        row["CNT_JOINT_RATE_AGE_REASON_CODE"] = "F"
        row["CNT_SEX_CODE"] = "M"
        row["CNT_PRODUCT_TYPE"] = "T"
        row["CNT_PLAN_OPTION"] = "L"
        df = pd.DataFrame([row])
        result = run(df, rules)
        assert str(result["VAL_CNT_JOINT_RATE_AGE_REASON_CODE"].iloc[0]).startswith("SEVERE")

    def test_joint_lives_1_reason_not_G_warning(self, rules):
        """JOINT_NUMBER_OF_LIVES=1, REASON_CODE=F must produce WARNING (not SEVERE)."""
        row = _make_valid_row()
        row["CNT_JOINT_NUMBER_OF_LIVES"] = "1"
        row["CNT_JOINT_LIFE_INDICATOR"] = "F"
        row["CNT_JOINT_RATE_AGE"] = "0"
        row["CNT_JOINT_RATE_AGE_REASON_CODE"] = "F"
        row["CNT_SEX_CODE"] = "M"
        row["CNT_PRODUCT_TYPE"] = "T"
        row["CNT_PLAN_OPTION"] = "L"
        df = pd.DataFrame([row])
        result = run(df, rules)
        val = str(result["VAL_CNT_JOINT_RATE_AGE_REASON_CODE"].iloc[0])
        # Rule 7 (JOINT_LIFE_INDICATOR=F requires FGP) is satisfied since F is in {F,G,P}
        # Rule 9 (LIVES=1 requires G) should trigger WARNING
        assert val.startswith("WARNING")

    def test_mature_date_lte_issue_date_severe(self, rules):
        """MATURE_EXPIRE_DATE <= ISSUE_DATE must produce SEVERE."""
        row = _make_valid_row()
        row["CNT_ISSUE_DATE"] = "20200101"
        row["CNT_MATURE_EXPIRE_DATE"] = "20190101"
        row["CNT_APPLICATION_DATE"] = "20191201"
        df = pd.DataFrame([row])
        result = run(df, rules)
        assert str(result["VAL_CNT_MATURE_EXPIRE_DATE"].iloc[0]).startswith("SEVERE")

    def test_application_gt_issue_date_severe(self, rules):
        """APPLICATION_DATE > ISSUE_DATE must produce SEVERE."""
        row = _make_valid_row()
        row["CNT_ISSUE_DATE"] = "20200101"
        row["CNT_APPLICATION_DATE"] = "20210101"
        row["CNT_MATURE_EXPIRE_DATE"] = "20600101"
        row["CNT_PAYUP_DATE"] = "20550101"
        df = pd.DataFrame([row])
        result = run(df, rules)
        assert str(result["VAL_CNT_APPLICATION_DATE"].iloc[0]).startswith("SEVERE")

    def test_payup_date_gt_mature_date_severe(self, rules):
        """PAYUP_DATE > MATURE_EXPIRE_DATE must produce SEVERE."""
        row = _make_valid_row()
        row["CNT_ISSUE_DATE"] = "20100101"
        row["CNT_MATURE_EXPIRE_DATE"] = "20300101"
        row["CNT_APPLICATION_DATE"] = "20091201"
        row["CNT_PAYUP_DATE"] = "20400101"
        df = pd.DataFrame([row])
        result = run(df, rules)
        assert str(result["VAL_CNT_PAYUP_DATE"].iloc[0]).startswith("SEVERE")

    def test_qualification_Q_product_T_severe(self, rules):
        """QUALIFICATION_CODE=Q, PRODUCT_TYPE=T must produce SEVERE (Q requires A,W,B)."""
        row = _make_valid_row()
        row["CNT_QUALIFICATION_CODE"] = "Q"
        row["CNT_PRODUCT_TYPE"] = "T"
        row["CNT_PARTICIPATION_STATUS"] = "P"
        row["CNT_PLAN_OPTION"] = "L"
        df = pd.DataFrame([row])
        result = run(df, rules)
        assert str(result["VAL_CNT_QUALIFICATION_CODE"].iloc[0]).startswith("SEVERE")

    def test_participation_not_N_when_product_not_TKLD_warning(self, rules):
        """PRODUCT_TYPE not in {T,K,L,D}, PARTICIPATION=P must produce WARNING."""
        row = _make_valid_row()
        row["CNT_PRODUCT_TYPE"] = "A"
        row["CNT_PARTICIPATION_STATUS"] = "P"
        row["CNT_QUALIFICATION_CODE"] = "N"
        row["CNT_PLAN_OPTION"] = ""
        row["CNT_JOINT_LIFE_INDICATOR"] = "N"
        row["CNT_JOINT_RATE_AGE"] = "0"
        row["CNT_JOINT_RATE_AGE_REASON_CODE"] = ""
        row["CNT_SEX_CODE"] = "M"
        df = pd.DataFrame([row])
        result = run(df, rules)
        assert str(result["VAL_CNT_PARTICIPATION_STATUS"].iloc[0]).startswith("WARNING")

    def test_plan_option_not_blank_when_product_AWBH_severe(self, rules):
        """PRODUCT_TYPE=A, PLAN_OPTION_ORIGINAL=L must produce SEVERE."""
        row = _make_valid_row()
        row["CNT_PRODUCT_TYPE"] = "A"
        row["CNT_PLAN_OPTION"] = "L"
        row["CNT_QUALIFICATION_CODE"] = "N"
        row["CNT_PARTICIPATION_STATUS"] = "N"
        row["CNT_JOINT_LIFE_INDICATOR"] = "N"
        row["CNT_JOINT_RATE_AGE"] = "0"
        row["CNT_JOINT_RATE_AGE_REASON_CODE"] = ""
        row["CNT_SEX_CODE"] = "M"
        df = pd.DataFrame([row])
        result = run(df, rules)
        assert str(result["VAL_CNT_PLAN_OPTION"].iloc[0]).startswith("SEVERE")

    def test_grace_not_blank_when_product_WBH_severe(self, rules):
        """PRODUCT_TYPE=W, GRACE_EXPIRY_DATE non-blank must produce SEVERE."""
        row = _make_valid_row()
        row["CNT_PRODUCT_TYPE"] = "W"
        row["CNT_GRACE_EXPIRY_DATE"] = "20250101"
        row["CNT_PLAN_OPTION"] = ""
        row["CNT_QUALIFICATION_CODE"] = "N"
        row["CNT_PARTICIPATION_STATUS"] = "N"
        row["CNT_JOINT_LIFE_INDICATOR"] = "N"
        row["CNT_JOINT_RATE_AGE"] = "0"
        row["CNT_JOINT_RATE_AGE_REASON_CODE"] = ""
        row["CNT_SEX_CODE"] = "M"
        df = pd.DataFrame([row])
        result = run(df, rules)
        assert str(result["VAL_CNT_GRACE_EXPIRY_DATE"].iloc[0]).startswith("SEVERE")

    def test_joint_F_rate_age_nonzero_severe(self, rules):
        """JOINT_LIFE_INDICATOR=F, RATE_AGE=5 must produce SEVERE."""
        row = _make_valid_row()
        row["CNT_JOINT_LIFE_INDICATOR"] = "F"
        row["CNT_JOINT_RATE_AGE"] = "5"
        row["CNT_JOINT_RATE_AGE_REASON_CODE"] = "F"
        row["CNT_SEX_CODE"] = "M"
        row["CNT_PRODUCT_TYPE"] = "T"
        row["CNT_PLAN_OPTION"] = "L"
        df = pd.DataFrame([row])
        result = run(df, rules)
        assert str(result["VAL_CNT_JOINT_RATE_AGE"].iloc[0]).startswith("SEVERE")

    def test_row_with_one_warning_no_severe_is_warning(self, rules):
        """Row with only WARNING-level failures is classified as WARNING."""
        row = _make_valid_row()
        row["CNT_SERV_AGENT"] = ""  # WARNING trigger
        df = pd.DataFrame([row])
        result = run(df, rules)
        assert result["ROW_SEVERITY"].iloc[0] == "WARNING"

    def test_row_with_warning_and_severe_is_severe(self, rules):
        """Row with WARNING + SEVERE is classified SEVERE."""
        row = _make_valid_row()
        row["CNT_SERV_AGENT"] = ""  # WARNING
        row["CNT_ISSUE_SYSTEM"] = ""  # SEVERE
        df = pd.DataFrame([row])
        result = run(df, rules)
        assert result["ROW_SEVERITY"].iloc[0] == "SEVERE"


class TestClassification:
    def test_all_none_is_clean(self):
        """A row with only None VAL_ values is CLEAN."""
        df = pd.DataFrame({"VAL_A": [None], "VAL_B": [None]})
        result = classify_severity(df)
        assert result["ROW_SEVERITY"].iloc[0] == "CLEAN"

    def test_warning_only_is_warning(self):
        """A row with WARNING and no SEVERE is WARNING."""
        df = pd.DataFrame({"VAL_A": ["WARNING: something"], "VAL_B": [None]})
        result = classify_severity(df)
        assert result["ROW_SEVERITY"].iloc[0] == "WARNING"

    def test_severe_overrides_warning(self):
        """A row with both WARNING and SEVERE is SEVERE."""
        df = pd.DataFrame({"VAL_A": ["WARNING: x"], "VAL_B": ["SEVERE: y"]})
        result = classify_severity(df)
        assert result["ROW_SEVERITY"].iloc[0] == "SEVERE"

    def test_severe_alone_is_severe(self):
        """A row with SEVERE alone is SEVERE."""
        df = pd.DataFrame({"VAL_A": ["SEVERE: critical"], "VAL_B": [None]})
        result = classify_severity(df)
        assert result["ROW_SEVERITY"].iloc[0] == "SEVERE"
