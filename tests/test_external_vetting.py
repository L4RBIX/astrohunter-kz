"""Tests for Phase 5C external catalog crossmatch vetting.

All tests are network-free.  Catalog queries are mocked at the astroquery
Vizier / Simbad level, or at the individual query_* function level for
higher-level integration tests.

No real catalog connections are made.  A test that passes does NOT mean
the catalogs returned scientifically meaningful results.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from astrohunter.external_vetting import (
    FP_CHECK_FAILED,
    FP_KNOWN_VARIABLE,
    FP_NO_MATCH,
    FP_POSSIBLE_EB,
    FP_SIMBAD_PROBLEMATIC,
    STATUS_FAILED,
    STATUS_MATCHED,
    STATUS_NOT_ATTEMPTED,
    STATUS_NOT_FOUND,
    _classify_external_flag,
    external_check_candidate_table,
    query_simbad_object_type,
    query_tess_eb_catalog_near_position,
    query_vsx_near_position,
    summarize_external_checks,
)
from astrohunter.vetting import apply_external_flags_to_vetting


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_candidate_df(n: int = 3) -> pd.DataFrame:
    return pd.DataFrame({
        "tic_id": list(range(10_000, 10_000 + n)),
        "ra_deg": [45.0 + i * 0.01 for i in range(n)],
        "dec_deg": [30.0 + i * 0.01 for i in range(n)],
        "local_snr": [6.0] * n,
        "automated_vetting_status": ["pass"] * n,
    })


def _vsx_result(status=STATUS_NOT_FOUND, name="", vtype="", sep=float("nan")):
    return {
        "vsx_check_status": status,
        "vsx_match_name": name,
        "vsx_variable_type": vtype,
        "vsx_sep_arcsec": sep,
    }


def _sim_result(status=STATUS_NOT_FOUND, main_id="", otype="", otypes="", sep=float("nan")):
    return {
        "simbad_check_status": status,
        "simbad_main_id": main_id,
        "simbad_otype": otype,
        "simbad_otypes": otypes,
        "simbad_sep_arcsec": sep,
    }


def _eb_result(status=STATUS_NOT_FOUND, match_id="", sep=float("nan")):
    return {
        "tess_eb_check_status": status,
        "tess_eb_match_id": match_id,
        "tess_eb_sep_arcsec": sep,
    }


# ---------------------------------------------------------------------------
# 1. query_vsx_near_position — mocking at Vizier level
# ---------------------------------------------------------------------------

class TestQueryVsx:
    def test_nan_coords_returns_not_attempted(self):
        result = query_vsx_near_position(float("nan"), 30.0)
        assert result["vsx_check_status"] == STATUS_NOT_ATTEMPTED

    @patch("astrohunter.external_vetting.Vizier")
    def test_no_match_empty_table_list(self, MockVizier):
        mock_v = MockVizier.return_value
        mock_v.query_region.return_value = []
        result = query_vsx_near_position(45.0, 30.0, radius_arcsec=10)
        assert result["vsx_check_status"] == STATUS_NOT_FOUND
        assert result["vsx_match_name"] == ""

    @patch("astrohunter.external_vetting.Vizier")
    def test_no_match_none_return(self, MockVizier):
        mock_v = MockVizier.return_value
        mock_v.query_region.return_value = None
        result = query_vsx_near_position(45.0, 30.0)
        assert result["vsx_check_status"] == STATUS_NOT_FOUND

    @patch("astrohunter.external_vetting.Vizier")
    def test_matched_ea_eclipsing_binary(self, MockVizier):
        from astropy.table import Table
        mock_table = Table({
            "Name": ["V* TZ For"],
            "Type": ["EA"],
            "RAJ2000": np.array([45.001]),
            "DEJ2000": np.array([30.001]),
        })
        mock_v = MockVizier.return_value
        mock_v.query_region.return_value = [mock_table]

        result = query_vsx_near_position(45.0, 30.0, radius_arcsec=30)
        assert result["vsx_check_status"] == STATUS_MATCHED
        assert result["vsx_variable_type"] == "EA"
        assert result["vsx_match_name"] == "V* TZ For"
        assert np.isfinite(result["vsx_sep_arcsec"])

    @patch("astrohunter.external_vetting.Vizier")
    def test_matched_rr_lyrae(self, MockVizier):
        from astropy.table import Table
        mock_table = Table({
            "Name": ["SomeRRL"],
            "Type": ["RRAB"],
            "RAJ2000": np.array([45.0]),
            "DEJ2000": np.array([30.0]),
        })
        mock_v = MockVizier.return_value
        mock_v.query_region.return_value = [mock_table]

        result = query_vsx_near_position(45.0, 30.0)
        assert result["vsx_check_status"] == STATUS_MATCHED
        assert result["vsx_variable_type"] == "RRAB"

    @patch("astrohunter.external_vetting.Vizier")
    def test_exception_returns_failed(self, MockVizier):
        mock_v = MockVizier.return_value
        mock_v.query_region.side_effect = ConnectionError("timeout")
        result = query_vsx_near_position(45.0, 30.0)
        assert result["vsx_check_status"] == STATUS_FAILED


# ---------------------------------------------------------------------------
# 2. query_simbad_object_type — mocking at _SimbadBase level
# ---------------------------------------------------------------------------

class TestQuerySimbad:
    def test_nan_coords_returns_not_attempted(self):
        result = query_simbad_object_type(45.0, float("nan"))
        assert result["simbad_check_status"] == STATUS_NOT_ATTEMPTED

    @patch("astrohunter.external_vetting._SimbadBase")
    def test_no_match_none_return(self, MockSimbad):
        mock_instance = MockSimbad.return_value
        mock_instance.query_region.return_value = None
        result = query_simbad_object_type(45.0, 30.0)
        assert result["simbad_check_status"] == STATUS_NOT_FOUND

    @patch("astrohunter.external_vetting._SimbadBase")
    def test_matched_eb_star(self, MockSimbad):
        from astropy.table import Table
        mock_table = Table({
            "MAIN_ID": [b"* eps Aur"],
            "OTYPE": ["EB*"],
            "OTYPES": ["EB*;*;"],
            "RA": ["05 01 58.13"],
            "DEC": ["+43 49 23.9"],
        })
        mock_instance = MockSimbad.return_value
        mock_instance.query_region.return_value = mock_table

        result = query_simbad_object_type(75.49, 43.82)
        assert result["simbad_check_status"] == STATUS_MATCHED
        assert result["simbad_otype"] == "EB*"
        assert "eps Aur" in result["simbad_main_id"]

    @patch("astrohunter.external_vetting._SimbadBase")
    def test_matched_nonstellar_type(self, MockSimbad):
        from astropy.table import Table
        mock_table = Table({
            "MAIN_ID": [b"Some Galaxy"],
            "OTYPE": ["Galaxy"],
            "OTYPES": ["Galaxy;"],
            "RA": ["45 00 00.0"],
            "DEC": ["+30 00 00.0"],
        })
        mock_instance = MockSimbad.return_value
        mock_instance.query_region.return_value = mock_table

        result = query_simbad_object_type(45.0, 30.0)
        assert result["simbad_check_status"] == STATUS_MATCHED
        assert result["simbad_otype"] == "Galaxy"

    @patch("astrohunter.external_vetting._SimbadBase")
    def test_exception_returns_failed(self, MockSimbad):
        mock_instance = MockSimbad.return_value
        mock_instance.query_region.side_effect = RuntimeError("service unavailable")
        result = query_simbad_object_type(45.0, 30.0)
        assert result["simbad_check_status"] == STATUS_FAILED
        assert result["simbad_main_id"] == ""


# ---------------------------------------------------------------------------
# 3. query_tess_eb_catalog_near_position
# ---------------------------------------------------------------------------

class TestQueryTessEB:
    def test_nan_coords_returns_not_attempted(self):
        result = query_tess_eb_catalog_near_position(float("nan"), 30.0)
        assert result["tess_eb_check_status"] == STATUS_NOT_ATTEMPTED

    @patch("astrohunter.external_vetting.Vizier")
    def test_no_match_empty_result(self, MockVizier):
        mock_v = MockVizier.return_value
        mock_v.query_region.return_value = []
        result = query_tess_eb_catalog_near_position(45.0, 30.0)
        assert result["tess_eb_check_status"] == STATUS_NOT_FOUND

    @patch("astrohunter.external_vetting.Vizier")
    def test_matched_eb(self, MockVizier):
        from astropy.table import Table
        mock_table = Table({
            "TIC": ["123456789"],
            "RAJ2000": np.array([45.001]),
            "DEJ2000": np.array([30.001]),
        })
        mock_v = MockVizier.return_value
        mock_v.query_region.return_value = [mock_table]

        result = query_tess_eb_catalog_near_position(45.0, 30.0, radius_arcsec=30)
        assert result["tess_eb_check_status"] == STATUS_MATCHED
        assert result["tess_eb_match_id"] == "123456789"
        assert np.isfinite(result["tess_eb_sep_arcsec"])

    @patch("astrohunter.external_vetting.Vizier")
    def test_exception_returns_failed(self, MockVizier):
        mock_v = MockVizier.return_value
        mock_v.query_region.side_effect = TimeoutError("network timeout")
        result = query_tess_eb_catalog_near_position(45.0, 30.0)
        assert result["tess_eb_check_status"] == STATUS_FAILED


# ---------------------------------------------------------------------------
# 4. _classify_external_flag
# ---------------------------------------------------------------------------

class TestClassifyExternalFlag:
    def test_no_matches_all_not_found(self):
        vsx = _vsx_result(STATUS_NOT_FOUND)
        sim = _sim_result(STATUS_NOT_FOUND)
        eb = _eb_result(STATUS_NOT_FOUND)
        flag, notes = _classify_external_flag(vsx, sim, eb)
        assert flag == FP_NO_MATCH
        assert notes == ""

    def test_tess_eb_match_gives_possible_eb(self):
        flag, notes = _classify_external_flag(
            _vsx_result(STATUS_NOT_FOUND),
            _sim_result(STATUS_NOT_FOUND),
            _eb_result(STATUS_MATCHED, match_id="12345", sep=5.0),
        )
        assert flag == FP_POSSIBLE_EB
        assert "TESS-EB" in notes

    def test_vsx_ea_type_gives_possible_eb(self):
        flag, notes = _classify_external_flag(
            _vsx_result(STATUS_MATCHED, name="TZ Aur", vtype="EA", sep=3.5),
            _sim_result(STATUS_NOT_FOUND),
            _eb_result(STATUS_NOT_FOUND),
        )
        assert flag == FP_POSSIBLE_EB
        assert "VSX" in notes

    def test_vsx_rrab_type_gives_possible_eb(self):
        flag, notes = _classify_external_flag(
            _vsx_result(STATUS_MATCHED, name="RR Lyr", vtype="RRAB", sep=2.0),
            _sim_result(STATUS_NOT_FOUND),
            _eb_result(STATUS_NOT_FOUND),
        )
        assert flag == FP_POSSIBLE_EB

    def test_simbad_eb_type_gives_simbad_problematic(self):
        flag, notes = _classify_external_flag(
            _vsx_result(STATUS_NOT_FOUND),
            _sim_result(STATUS_MATCHED, otype="EB*", main_id="HD 1234", sep=4.0),
            _eb_result(STATUS_NOT_FOUND),
        )
        assert flag == FP_SIMBAD_PROBLEMATIC
        assert "SIMBAD" in notes

    def test_all_failed_gives_check_failed(self):
        flag, notes = _classify_external_flag(
            _vsx_result(STATUS_FAILED),
            _sim_result(STATUS_FAILED),
            _eb_result(STATUS_FAILED),
        )
        assert flag == FP_CHECK_FAILED
        assert "failed" in notes.lower()

    def test_one_failed_one_matched_reports_match(self):
        # TESS-EB matched; SIMBAD failed → should report the match, not failed
        flag, notes = _classify_external_flag(
            _vsx_result(STATUS_NOT_FOUND),
            _sim_result(STATUS_FAILED),
            _eb_result(STATUS_MATCHED, match_id="999", sep=8.0),
        )
        assert flag == FP_POSSIBLE_EB

    def test_tess_eb_priority_over_vsx(self):
        # TESS-EB match should keep FP_POSSIBLE_EB even if VSX also matches with M type
        flag, _ = _classify_external_flag(
            _vsx_result(STATUS_MATCHED, name="Mira", vtype="M", sep=2.0),
            _sim_result(STATUS_NOT_FOUND),
            _eb_result(STATUS_MATCHED, match_id="777", sep=1.0),
        )
        assert flag == FP_POSSIBLE_EB

    def test_not_attempted_is_not_failure(self):
        # All not_attempted (skip flags set) → FP_NO_MATCH (not FP_CHECK_FAILED)
        flag, _ = _classify_external_flag(
            _vsx_result(STATUS_NOT_ATTEMPTED),
            _sim_result(STATUS_NOT_ATTEMPTED),
            _eb_result(STATUS_NOT_ATTEMPTED),
        )
        assert flag == FP_NO_MATCH


# ---------------------------------------------------------------------------
# 5. external_check_candidate_table
# ---------------------------------------------------------------------------

class TestExternalCheckCandidateTable:
    def test_empty_dataframe_returns_empty(self):
        result = external_check_candidate_table(pd.DataFrame())
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0

    def test_all_columns_present_after_check(self):
        df = _make_candidate_df(2)
        result = external_check_candidate_table(
            df, skip_vsx=True, skip_simbad=True, skip_tess_eb=True
        )
        for col in [
            "vsx_check_status", "vsx_match_name", "vsx_variable_type", "vsx_sep_arcsec",
            "simbad_check_status", "simbad_main_id", "simbad_otype",
            "tess_eb_check_status", "tess_eb_match_id",
            "external_false_positive_flag", "external_vetting_notes",
            "external_vetter_version",
        ]:
            assert col in result.columns, f"Missing column: {col}"

    def test_skip_all_sets_not_attempted(self):
        df = _make_candidate_df(2)
        result = external_check_candidate_table(
            df, skip_vsx=True, skip_simbad=True, skip_tess_eb=True
        )
        assert (result["vsx_check_status"] == STATUS_NOT_ATTEMPTED).all()
        assert (result["simbad_check_status"] == STATUS_NOT_ATTEMPTED).all()
        assert (result["tess_eb_check_status"] == STATUS_NOT_ATTEMPTED).all()

    def test_no_ra_dec_columns_sets_not_attempted(self):
        df = pd.DataFrame({"tic_id": [1001, 1002], "local_snr": [6.0, 7.0]})
        result = external_check_candidate_table(
            df, skip_vsx=True, skip_simbad=True, skip_tess_eb=True
        )
        # No coords → not_attempted for all
        assert (result["vsx_check_status"] == STATUS_NOT_ATTEMPTED).all()

    def test_nan_ra_dec_sets_not_attempted(self):
        df = pd.DataFrame({
            "tic_id": [1001],
            "ra_deg": [float("nan")],
            "dec_deg": [float("nan")],
        })
        result = external_check_candidate_table(
            df, skip_vsx=True, skip_simbad=True, skip_tess_eb=True
        )
        assert result.at[result.index[0], "vsx_check_status"] == STATUS_NOT_ATTEMPTED

    @patch("astrohunter.external_vetting.query_vsx_near_position")
    @patch("astrohunter.external_vetting.query_simbad_object_type")
    @patch("astrohunter.external_vetting.query_tess_eb_catalog_near_position")
    def test_vsx_match_propagates_to_fp_flag(self, mock_eb, mock_sim, mock_vsx):
        mock_vsx.return_value = _vsx_result(STATUS_MATCHED, name="TZ For", vtype="EA", sep=3.0)
        mock_sim.return_value = _sim_result(STATUS_NOT_FOUND)
        mock_eb.return_value = _eb_result(STATUS_NOT_FOUND)

        df = _make_candidate_df(1)
        result = external_check_candidate_table(df)
        assert result.at[result.index[0], "external_false_positive_flag"] == FP_POSSIBLE_EB
        assert result.at[result.index[0], "vsx_check_status"] == STATUS_MATCHED

    @patch("astrohunter.external_vetting.query_vsx_near_position")
    @patch("astrohunter.external_vetting.query_simbad_object_type")
    @patch("astrohunter.external_vetting.query_tess_eb_catalog_near_position")
    def test_all_not_found_gives_no_external_match(self, mock_eb, mock_sim, mock_vsx):
        mock_vsx.return_value = _vsx_result(STATUS_NOT_FOUND)
        mock_sim.return_value = _sim_result(STATUS_NOT_FOUND)
        mock_eb.return_value = _eb_result(STATUS_NOT_FOUND)

        df = _make_candidate_df(1)
        result = external_check_candidate_table(df)
        assert result.at[result.index[0], "external_false_positive_flag"] == FP_NO_MATCH

    @patch("astrohunter.external_vetting.query_vsx_near_position")
    @patch("astrohunter.external_vetting.query_simbad_object_type")
    @patch("astrohunter.external_vetting.query_tess_eb_catalog_near_position")
    def test_all_queries_failed_gives_check_failed(self, mock_eb, mock_sim, mock_vsx):
        mock_vsx.return_value = _vsx_result(STATUS_FAILED)
        mock_sim.return_value = _sim_result(STATUS_FAILED)
        mock_eb.return_value = _eb_result(STATUS_FAILED)

        df = _make_candidate_df(1)
        result = external_check_candidate_table(df)
        assert result.at[result.index[0], "external_false_positive_flag"] == FP_CHECK_FAILED

    def test_original_columns_preserved(self):
        df = _make_candidate_df(2)
        df["some_existing_col"] = "keep_me"
        result = external_check_candidate_table(
            df, skip_vsx=True, skip_simbad=True, skip_tess_eb=True
        )
        assert "some_existing_col" in result.columns
        assert (result["some_existing_col"] == "keep_me").all()


# ---------------------------------------------------------------------------
# 6. summarize_external_checks
# ---------------------------------------------------------------------------

class TestSummarizeExternalChecks:
    def test_empty_dataframe(self):
        summary = summarize_external_checks(pd.DataFrame())
        assert isinstance(summary, pd.DataFrame)
        assert "catalog" in summary.columns

    def test_all_not_attempted(self):
        df = _make_candidate_df(3)
        df["vsx_check_status"] = STATUS_NOT_ATTEMPTED
        df["simbad_check_status"] = STATUS_NOT_ATTEMPTED
        df["tess_eb_check_status"] = STATUS_NOT_ATTEMPTED
        df["external_false_positive_flag"] = FP_NO_MATCH

        summary = summarize_external_checks(df)
        vsx_row = summary[summary["catalog"].str.contains("VSX")].iloc[0]
        assert vsx_row["n_not_attempted"] == 3
        assert vsx_row["n_matched"] == 0

    def test_summary_counts_correct(self):
        df = pd.DataFrame({
            "vsx_check_status": [STATUS_MATCHED, STATUS_NOT_FOUND, STATUS_FAILED],
            "simbad_check_status": [STATUS_NOT_FOUND] * 3,
            "tess_eb_check_status": [STATUS_NOT_ATTEMPTED] * 3,
            "external_false_positive_flag": [FP_POSSIBLE_EB, FP_NO_MATCH, FP_CHECK_FAILED],
        })
        summary = summarize_external_checks(df)
        vsx_row = summary[summary["catalog"].str.contains("VSX")].iloc[0]
        assert vsx_row["n_matched"] == 1
        assert vsx_row["n_not_found"] == 1
        assert vsx_row["n_failed"] == 1

        flag_row = summary[summary["catalog"].str.contains("possible_eclipsing")]
        assert len(flag_row) == 1
        assert flag_row.iloc[0]["n_matched"] == 1


# ---------------------------------------------------------------------------
# 7. apply_external_flags_to_vetting
# ---------------------------------------------------------------------------

class TestApplyExternalFlagsToVetting:
    def test_no_external_col_no_change(self):
        df = pd.DataFrame({
            "automated_vetting_status": ["pass", "flagged"],
        })
        result = apply_external_flags_to_vetting(df)
        assert list(result["automated_vetting_status"]) == ["pass", "flagged"]

    def test_known_variable_demotes_pass(self):
        df = pd.DataFrame({
            "automated_vetting_status": ["pass"],
            "external_false_positive_flag": [FP_KNOWN_VARIABLE],
        })
        result = apply_external_flags_to_vetting(df)
        assert result.at[result.index[0], "automated_vetting_status"] == "flagged"
        assert result.at[result.index[0], "flag_external_catalog_match"] == True  # noqa: E712

    def test_possible_eb_demotes_pass(self):
        df = pd.DataFrame({
            "automated_vetting_status": ["pass"],
            "external_false_positive_flag": [FP_POSSIBLE_EB],
        })
        result = apply_external_flags_to_vetting(df)
        assert result.at[result.index[0], "automated_vetting_status"] == "flagged"

    def test_simbad_problematic_demotes_pass(self):
        df = pd.DataFrame({
            "automated_vetting_status": ["pass"],
            "external_false_positive_flag": [FP_SIMBAD_PROBLEMATIC],
        })
        result = apply_external_flags_to_vetting(df)
        assert result.at[result.index[0], "automated_vetting_status"] == "flagged"

    def test_no_match_does_not_demote(self):
        df = pd.DataFrame({
            "automated_vetting_status": ["pass"],
            "external_false_positive_flag": [FP_NO_MATCH],
        })
        result = apply_external_flags_to_vetting(df)
        assert result.at[result.index[0], "automated_vetting_status"] == "pass"

    def test_check_failed_does_not_demote(self):
        df = pd.DataFrame({
            "automated_vetting_status": ["pass"],
            "external_false_positive_flag": [FP_CHECK_FAILED],
        })
        result = apply_external_flags_to_vetting(df)
        assert result.at[result.index[0], "automated_vetting_status"] == "pass"

    def test_already_flagged_stays_flagged(self):
        df = pd.DataFrame({
            "automated_vetting_status": ["flagged"],
            "external_false_positive_flag": [FP_NO_MATCH],
        })
        result = apply_external_flags_to_vetting(df)
        assert result.at[result.index[0], "automated_vetting_status"] == "flagged"

    def test_existing_vetting_columns_preserved(self):
        df = pd.DataFrame({
            "automated_vetting_status": ["pass"],
            "flag_low_snr": [True],
            "external_false_positive_flag": [FP_POSSIBLE_EB],
        })
        result = apply_external_flags_to_vetting(df)
        assert result.at[result.index[0], "flag_low_snr"] == True  # noqa: E712

    def test_returns_copy_not_inplace(self):
        df = pd.DataFrame({
            "automated_vetting_status": ["pass"],
            "external_false_positive_flag": [FP_POSSIBLE_EB],
        })
        result = apply_external_flags_to_vetting(df)
        assert df.at[df.index[0], "automated_vetting_status"] == "pass"  # original unchanged


# ---------------------------------------------------------------------------
# 8. plot_external_catalog_flag_counts
# ---------------------------------------------------------------------------

class TestPlotExternalCatalogFlagCounts:
    def test_creates_file_with_data(self, tmp_path):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from astrohunter.plotting import plot_external_catalog_flag_counts

        df = _make_candidate_df(3)
        df["vsx_check_status"] = [STATUS_MATCHED, STATUS_NOT_FOUND, STATUS_FAILED]
        df["simbad_check_status"] = STATUS_NOT_FOUND
        df["tess_eb_check_status"] = STATUS_NOT_ATTEMPTED
        df["external_false_positive_flag"] = [FP_POSSIBLE_EB, FP_NO_MATCH, FP_CHECK_FAILED]

        out = tmp_path / "ext_flags.png"
        plot_external_catalog_flag_counts(df, output_path=out)
        assert out.exists()
        plt.close("all")

    def test_creates_file_with_empty_df(self, tmp_path):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from astrohunter.plotting import plot_external_catalog_flag_counts

        out = tmp_path / "ext_flags_empty.png"
        plot_external_catalog_flag_counts(pd.DataFrame(), output_path=out)
        assert out.exists()
        plt.close("all")

    def test_creates_file_no_external_cols(self, tmp_path):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from astrohunter.plotting import plot_external_catalog_flag_counts

        df = _make_candidate_df(2)  # no external columns at all
        out = tmp_path / "ext_flags_no_cols.png"
        plot_external_catalog_flag_counts(df, output_path=out)
        assert out.exists()
        plt.close("all")


# ---------------------------------------------------------------------------
# 9. run_external_vetting.py CLI — no network
# ---------------------------------------------------------------------------

class TestRunExternalVettingCLI:
    def test_missing_candidate_table_returns_1(self, tmp_path):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        from run_external_vetting import main
        ret = main([
            "--candidate-table", str(tmp_path / "nonexistent.csv"),
            "--output", str(tmp_path / "out.csv"),
        ])
        assert ret == 1

    def test_empty_candidate_table_returns_0(self, tmp_path):
        from run_external_vetting import main
        cand_path = tmp_path / "empty_candidates.csv"
        cand_path.write_text("tic_id,local_snr\n")
        out_path = tmp_path / "out.csv"
        sum_path = tmp_path / "summary.csv"
        ret = main([
            "--candidate-table", str(cand_path),
            "--output", str(out_path),
            "--summary-output", str(sum_path),
            "--skip-vsx", "--skip-simbad", "--skip-tess-eb",
        ])
        assert ret == 0
        assert out_path.exists()

    def test_full_run_skip_all_returns_0(self, tmp_path):
        from run_external_vetting import main
        cand_path = tmp_path / "cands.csv"
        pd.DataFrame({
            "tic_id": [10_000, 20_000],
            "ra_deg": [45.0, 46.0],
            "dec_deg": [30.0, 31.0],
            "local_snr": [6.0, 7.0],
            "automated_vetting_status": ["pass", "flagged"],
        }).to_csv(cand_path, index=False)

        out_path = tmp_path / "checked.csv"
        sum_path = tmp_path / "summary.csv"
        ret = main([
            "--candidate-table", str(cand_path),
            "--output", str(out_path),
            "--summary-output", str(sum_path),
            "--skip-vsx", "--skip-simbad", "--skip-tess-eb",
        ])
        assert ret == 0
        assert out_path.exists()
        assert sum_path.exists()
        out_df = pd.read_csv(out_path)
        assert "external_false_positive_flag" in out_df.columns
        assert "vsx_check_status" in out_df.columns

    def test_coord_lookup_from_catalog_files(self, tmp_path):
        from run_external_vetting import _build_coord_lookup
        ts = tmp_path / "ts.csv"
        ts.write_text("tic_id,ra_deg,dec_deg,target_name\n10000,45.0,30.0,Star A\n")
        cp = tmp_path / "cp.csv"
        cp.write_text("tic_id,ra_deg,dec_deg\n20000,90.0,45.0\n")
        lookup = _build_coord_lookup(ts, cp)
        assert 10_000 in lookup
        assert lookup[10_000] == (45.0, 30.0)
        assert 20_000 in lookup
        assert lookup[20_000] == (90.0, 45.0)

    def test_coord_lookup_missing_file(self, tmp_path):
        from run_external_vetting import _build_coord_lookup
        lookup = _build_coord_lookup(
            tmp_path / "nonexistent_ts.csv",
            tmp_path / "nonexistent_cp.csv",
        )
        assert isinstance(lookup, dict)
        assert len(lookup) == 0
