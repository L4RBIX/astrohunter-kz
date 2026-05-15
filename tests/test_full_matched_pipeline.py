"""Tests for Phase 5D full matched pipeline helper functions.

All tests use synthetic data — no network calls, no real TESS downloads.
Tests cover the pure helper functions in scripts/run_full_matched_pipeline.py.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ------------------------------------------------------------------ imports
# Load the pipeline module from scripts/ without installing it as a package.
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
_MODULE_PATH = _SCRIPTS_DIR / "run_full_matched_pipeline.py"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

_spec = importlib.util.spec_from_file_location(
    "run_full_matched_pipeline", _MODULE_PATH
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

_build_scan_status_row = _mod._build_scan_status_row
_get_resume_tics = _mod._get_resume_tics
_deduplicate_scan_list = _mod._deduplicate_scan_list
_build_scan_list = _mod._build_scan_list
_build_run_summary = _mod._build_run_summary
PIPELINE_VERSION = _mod.PIPELINE_VERSION


# ============================================================================
# _build_scan_status_row
# ============================================================================

class TestBuildScanStatusRow:
    def test_all_fields_present(self):
        row = _build_scan_status_row(
            tic_id=123456,
            sample_role="target",
            matched_pair_id=0,
            star_name="HD 1234",
            success=True,
            failure_reason="",
            n_candidates=3,
            cache_used=True,
        )
        expected_keys = {
            "tic_id", "sample_role", "matched_pair_id", "star_name",
            "attempted", "success", "failure_reason", "n_candidates",
            "cache_used", "scan_timestamp",
        }
        assert expected_keys == set(row.keys())

    def test_success_true(self):
        row = _build_scan_status_row(
            tic_id=1, sample_role="target", matched_pair_id=0,
            star_name="X", success=True, failure_reason="",
            n_candidates=2, cache_used=False,
        )
        assert row["success"] is True
        assert row["failure_reason"] == ""
        assert row["n_candidates"] == 2

    def test_success_false_preserves_reason(self):
        reason = "download_failed: timeout"
        row = _build_scan_status_row(
            tic_id=2, sample_role="control", matched_pair_id=1,
            star_name="TIC 2", success=False, failure_reason=reason,
            n_candidates=0, cache_used=False,
        )
        assert row["success"] is False
        assert row["failure_reason"] == reason
        assert row["n_candidates"] == 0

    def test_attempted_always_true(self):
        row = _build_scan_status_row(
            tic_id=3, sample_role="target", matched_pair_id=0,
            star_name="X", success=False, failure_reason="no_data",
            n_candidates=0, cache_used=False,
        )
        assert row["attempted"] is True

    def test_cache_used_preserved(self):
        row = _build_scan_status_row(
            tic_id=4, sample_role="target", matched_pair_id=0,
            star_name="X", success=True, failure_reason="",
            n_candidates=0, cache_used=True,
        )
        assert row["cache_used"] is True

    def test_scan_timestamp_is_string(self):
        row = _build_scan_status_row(
            tic_id=5, sample_role="target", matched_pair_id=0,
            star_name="X", success=True, failure_reason="",
            n_candidates=0, cache_used=False,
        )
        assert isinstance(row["scan_timestamp"], str)
        assert len(row["scan_timestamp"]) > 0

    def test_tic_id_preserved(self):
        row = _build_scan_status_row(
            tic_id=999999, sample_role="control", matched_pair_id=5,
            star_name="TIC 999999", success=True, failure_reason="",
            n_candidates=1, cache_used=True,
        )
        assert row["tic_id"] == 999999
        assert row["sample_role"] == "control"
        assert row["matched_pair_id"] == 5


# ============================================================================
# _get_resume_tics
# ============================================================================

class TestGetResumeTics:
    def test_empty_dataframe_returns_empty_set(self):
        assert _get_resume_tics(pd.DataFrame()) == set()

    def test_missing_success_column_returns_empty_set(self):
        df = pd.DataFrame({"tic_id": [1, 2, 3]})
        assert _get_resume_tics(df) == set()

    def test_missing_tic_id_column_returns_empty_set(self):
        df = pd.DataFrame({"success": [True, True]})
        assert _get_resume_tics(df) == set()

    def test_all_failed_returns_empty_set(self):
        df = pd.DataFrame({
            "tic_id": [10, 20, 30],
            "success": [False, False, False],
        })
        assert _get_resume_tics(df) == set()

    def test_returns_only_successful_tics(self):
        df = pd.DataFrame({
            "tic_id": [10, 20, 30, 40],
            "success": [True, False, True, False],
        })
        result = _get_resume_tics(df)
        assert result == {10, 30}

    def test_all_successful(self):
        df = pd.DataFrame({
            "tic_id": [100, 200, 300],
            "success": [True, True, True],
        })
        assert _get_resume_tics(df) == {100, 200, 300}

    def test_nan_tic_ids_are_skipped(self):
        df = pd.DataFrame({
            "tic_id": [1.0, float("nan"), 3.0],
            "success": [True, True, True],
        })
        result = _get_resume_tics(df)
        assert float("nan") not in result
        assert 1 in result
        assert 3 in result
        assert len(result) == 2

    def test_returns_set_of_ints(self):
        df = pd.DataFrame({
            "tic_id": [10.0, 20.0],
            "success": [True, True],
        })
        result = _get_resume_tics(df)
        for tic in result:
            assert isinstance(tic, int)

    def test_boolean_like_values(self):
        df = pd.DataFrame({
            "tic_id": [1, 2, 3],
            "success": [1, 0, 1],  # integer 0/1 instead of bool
        })
        result = _get_resume_tics(df)
        # 1 and 0 are truthy/falsy but == True matches only integer 1
        assert 1 in result
        assert 3 in result


# ============================================================================
# _deduplicate_scan_list
# ============================================================================

class TestDeduplicateScanList:
    def test_empty_list(self):
        assert _deduplicate_scan_list([]) == []

    def test_no_duplicates(self):
        scan_list = [
            (1, "target", 0, "Star A"),
            (2, "control", 0, "TIC 2"),
            (3, "target", 1, "Star B"),
        ]
        result = _deduplicate_scan_list(scan_list)
        assert result == scan_list

    def test_removes_duplicate_tic(self):
        scan_list = [
            (1, "target", 0, "Star A"),
            (1, "target", 1, "Star A again"),  # same TIC
            (2, "control", 0, "TIC 2"),
        ]
        result = _deduplicate_scan_list(scan_list)
        assert len(result) == 2
        assert result[0][0] == 1
        assert result[1][0] == 2

    def test_keeps_first_occurrence(self):
        scan_list = [
            (99, "target", 0, "First occurrence"),
            (99, "control", 1, "Second occurrence"),
        ]
        result = _deduplicate_scan_list(scan_list)
        assert len(result) == 1
        assert result[0][2] == 0   # pair_id of first occurrence
        assert result[0][1] == "target"

    def test_all_duplicates_of_same_tic(self):
        scan_list = [(5, "target", i, f"copy_{i}") for i in range(10)]
        result = _deduplicate_scan_list(scan_list)
        assert len(result) == 1
        assert result[0][0] == 5

    def test_preserves_order(self):
        scan_list = [
            (10, "target", 0, "A"),
            (20, "control", 0, "B"),
            (30, "target", 1, "C"),
        ]
        result = _deduplicate_scan_list(scan_list)
        assert [e[0] for e in result] == [10, 20, 30]


# ============================================================================
# _build_scan_list
# ============================================================================

class TestBuildScanList:
    def _make_pairs(self, n=3):
        return pd.DataFrame({
            "target_tic_id": [1000 + i for i in range(n)],
            "target_name": [f"Star {i}" for i in range(n)],
            "control_tic_id": [2000 + i for i in range(n)],
        })

    def test_basic_construction(self):
        pairs = self._make_pairs(3)
        result = _build_scan_list(pairs, limit_pairs=None)
        # 3 targets + 3 controls = 6 entries
        assert len(result) == 6
        roles = [r[1] for r in result]
        assert roles.count("target") == 3
        assert roles.count("control") == 3

    def test_limit_pairs(self):
        pairs = self._make_pairs(5)
        result = _build_scan_list(pairs, limit_pairs=2)
        # 2 targets + 2 controls = 4 entries
        assert len(result) == 4

    def test_limit_pairs_larger_than_available(self):
        pairs = self._make_pairs(3)
        result = _build_scan_list(pairs, limit_pairs=100)
        assert len(result) == 6

    def test_include_targets_only(self):
        pairs = self._make_pairs(3)
        result = _build_scan_list(pairs, limit_pairs=None,
                                  include_targets=True, include_controls=False)
        roles = [r[1] for r in result]
        assert all(r == "target" for r in roles)
        assert len(result) == 3

    def test_include_controls_only(self):
        pairs = self._make_pairs(3)
        result = _build_scan_list(pairs, limit_pairs=None,
                                  include_targets=False, include_controls=True)
        roles = [r[1] for r in result]
        assert all(r == "control" for r in roles)
        assert len(result) == 3

    def test_deduplicates_repeated_tic(self):
        pairs = pd.DataFrame({
            "target_tic_id": [1001, 1001, 1002],   # 1001 repeated
            "target_name": ["Star A", "Star A dup", "Star B"],
            "control_tic_id": [2001, 2002, 2003],
        })
        result = _build_scan_list(pairs, limit_pairs=None)
        tic_ids = [r[0] for r in result]
        assert tic_ids.count(1001) == 1   # deduplicated
        assert len(result) == 5  # 2 unique targets + 3 unique controls

    def test_target_name_from_column(self):
        pairs = pd.DataFrame({
            "target_tic_id": [5555],
            "target_name": ["HD 999"],
            "control_tic_id": [6666],
        })
        result = _build_scan_list(pairs, limit_pairs=None)
        target_entry = next(e for e in result if e[1] == "target")
        assert target_entry[3] == "HD 999"

    def test_control_name_is_tic_string(self):
        pairs = pd.DataFrame({
            "target_tic_id": [5555],
            "target_name": ["HD 999"],
            "control_tic_id": [6666],
        })
        result = _build_scan_list(pairs, limit_pairs=None)
        control_entry = next(e for e in result if e[1] == "control")
        assert "6666" in control_entry[3]

    def test_zero_tic_id_skipped(self):
        pairs = pd.DataFrame({
            "target_tic_id": [0, 1002],
            "target_name": ["bad", "good"],
            "control_tic_id": [2001, 2002],
        })
        result = _build_scan_list(pairs, limit_pairs=None)
        tic_ids = [r[0] for r in result]
        assert 0 not in tic_ids

    def test_empty_pairs_returns_empty(self):
        pairs = pd.DataFrame(columns=["target_tic_id", "target_name", "control_tic_id"])
        result = _build_scan_list(pairs, limit_pairs=None)
        assert result == []


# ============================================================================
# _build_run_summary
# ============================================================================

class TestBuildRunSummary:
    def _make_status(self, target_ok=2, target_fail=1, control_ok=2, control_fail=0):
        rows = []
        for i in range(target_ok):
            rows.append({"tic_id": 1000 + i, "sample_role": "target", "success": True})
        for i in range(target_fail):
            rows.append({"tic_id": 1100 + i, "sample_role": "target", "success": False})
        for i in range(control_ok):
            rows.append({"tic_id": 2000 + i, "sample_role": "control", "success": True})
        for i in range(control_fail):
            rows.append({"tic_id": 2100 + i, "sample_role": "control", "success": False})
        return pd.DataFrame(rows)

    def _make_candidates(self, n_target=3, n_control=1):
        rows = (
            [{"sample_role": "target", "tic_id": 1000 + i} for i in range(n_target)]
            + [{"sample_role": "control", "tic_id": 2000 + i} for i in range(n_control)]
        )
        return pd.DataFrame(rows)

    def test_basic_fields_present(self):
        status_df = self._make_status()
        summary = _build_run_summary(
            candidates_df=self._make_candidates(),
            status_df=status_df,
            rate_summary_df=None,
            phases_run=["scan", "ranking"],
            phases_skipped=["stats"],
            output_prefix="test",
        )
        assert "pipeline_version" in summary
        assert summary["pipeline_version"] == PIPELINE_VERSION
        assert "output_prefix" in summary
        assert "run_timestamp" in summary

    def test_star_counts(self):
        status_df = self._make_status(target_ok=3, target_fail=1, control_ok=2, control_fail=2)
        summary = _build_run_summary(
            candidates_df=self._make_candidates(2, 1),
            status_df=status_df,
            rate_summary_df=None,
            phases_run=["scan"],
            phases_skipped=[],
            output_prefix="test",
        )
        assert summary["n_target_success"] == 3
        assert summary["n_target_failed"] == 1
        assert summary["n_target_attempted"] == 4
        assert summary["n_control_success"] == 2
        assert summary["n_control_failed"] == 2
        assert summary["n_control_attempted"] == 4

    def test_candidate_counts(self):
        status_df = self._make_status()
        cands = self._make_candidates(n_target=4, n_control=1)
        summary = _build_run_summary(
            candidates_df=cands,
            status_df=status_df,
            rate_summary_df=None,
            phases_run=["scan"],
            phases_skipped=[],
            output_prefix="test",
        )
        assert summary["n_candidates_target"] == 4
        assert summary["n_candidates_control"] == 1
        assert summary["n_candidates_total"] == 5

    def test_phases_stored_as_comma_string(self):
        status_df = self._make_status()
        summary = _build_run_summary(
            candidates_df=None,
            status_df=status_df,
            rate_summary_df=None,
            phases_run=["scan", "ranking", "vetting"],
            phases_skipped=["external", "stats"],
            output_prefix="prefix",
        )
        assert summary["phases_run"] == "scan,ranking,vetting"
        assert summary["phases_skipped"] == "external,stats"

    def test_none_candidates_gives_zero_counts(self):
        status_df = self._make_status()
        summary = _build_run_summary(
            candidates_df=None,
            status_df=status_df,
            rate_summary_df=None,
            phases_run=[],
            phases_skipped=[],
            output_prefix="x",
        )
        assert summary["n_candidates_total"] == 0
        assert summary["n_candidates_target"] == 0
        assert summary["n_candidates_control"] == 0

    def test_empty_status_gives_zero_star_counts(self):
        summary = _build_run_summary(
            candidates_df=None,
            status_df=pd.DataFrame(),
            rate_summary_df=None,
            phases_run=[],
            phases_skipped=[],
            output_prefix="x",
        )
        assert summary["n_target_success"] == 0
        assert summary["n_control_success"] == 0

    def test_rate_summary_included_when_provided(self):
        status_df = self._make_status()
        rate_df = pd.DataFrame([{
            "rate_ratio": 2.5,
            "rate_ratio_ci_lo": 0.5,
            "rate_ratio_ci_hi": 8.0,
            "subset": "all",
        }])
        summary = _build_run_summary(
            candidates_df=self._make_candidates(),
            status_df=status_df,
            rate_summary_df=rate_df,
            phases_run=["scan", "stats"],
            phases_skipped=[],
            output_prefix="test",
        )
        assert "rate_ratio" in summary
        assert abs(summary["rate_ratio"] - 2.5) < 1e-9
        assert abs(summary["rate_ratio_ci_lo"] - 0.5) < 1e-9

    def test_rate_summary_absent_when_none(self):
        status_df = self._make_status()
        summary = _build_run_summary(
            candidates_df=self._make_candidates(),
            status_df=status_df,
            rate_summary_df=None,
            phases_run=[],
            phases_skipped=[],
            output_prefix="x",
        )
        assert "rate_ratio" not in summary

    def test_output_prefix_preserved(self):
        status_df = self._make_status()
        summary = _build_run_summary(
            candidates_df=None,
            status_df=status_df,
            rate_summary_df=None,
            phases_run=[],
            phases_skipped=[],
            output_prefix="my_run_v2",
        )
        assert summary["output_prefix"] == "my_run_v2"

    def test_candidates_without_sample_role_column(self):
        cands = pd.DataFrame({"tic_id": [1, 2, 3]})  # no sample_role
        status_df = self._make_status()
        summary = _build_run_summary(
            candidates_df=cands,
            status_df=status_df,
            rate_summary_df=None,
            phases_run=[],
            phases_skipped=[],
            output_prefix="x",
        )
        assert summary["n_candidates_total"] == 3
        assert summary["n_candidates_target"] == 0
        assert summary["n_candidates_control"] == 0

    def test_partial_failures_counted_correctly(self):
        status_df = self._make_status(target_ok=2, target_fail=3, control_ok=1, control_fail=1)
        summary = _build_run_summary(
            candidates_df=None,
            status_df=status_df,
            rate_summary_df=None,
            phases_run=["scan"],
            phases_skipped=[],
            output_prefix="x",
        )
        assert summary["n_target_failed"] == 3
        assert summary["n_target_attempted"] == 5
        assert summary["n_control_failed"] == 1
        assert summary["n_control_attempted"] == 2


# ============================================================================
# Edge-case integration: resume + scan_list interaction
# ============================================================================

class TestResumeIntegration:
    def test_resume_excludes_succeeded_tics_from_scan_list(self):
        pairs = pd.DataFrame({
            "target_tic_id": [1001, 1002, 1003],
            "target_name": ["A", "B", "C"],
            "control_tic_id": [2001, 2002, 2003],
        })
        scan_list = _build_scan_list(pairs, limit_pairs=None)
        status_df = pd.DataFrame({
            "tic_id": [1001, 2001],
            "success": [True, True],
        })
        resume_tics = _get_resume_tics(status_df)
        remaining = [e for e in scan_list if e[0] not in resume_tics]
        assert 1001 not in [e[0] for e in remaining]
        assert 2001 not in [e[0] for e in remaining]
        assert len(remaining) == 4   # 6 total - 2 resumed

    def test_failed_tics_are_not_in_resume_set(self):
        status_df = pd.DataFrame({
            "tic_id": [1001, 1002, 1003],
            "success": [True, False, True],
        })
        resume_tics = _get_resume_tics(status_df)
        assert 1002 not in resume_tics

    def test_empty_status_means_no_tics_resumed(self):
        resume_tics = _get_resume_tics(pd.DataFrame())
        pairs = pd.DataFrame({
            "target_tic_id": [1001],
            "target_name": ["A"],
            "control_tic_id": [2001],
        })
        scan_list = _build_scan_list(pairs, limit_pairs=None)
        remaining = [e for e in scan_list if e[0] not in resume_tics]
        assert len(remaining) == len(scan_list)


# ============================================================================
# Smoke test: parse_args works with default values
# ============================================================================

class TestParseArgs:
    def test_default_args(self):
        args = _mod._parse_args([])
        assert args.output_prefix == "full_matched"
        assert args.sigma_threshold == 4.0
        assert args.max_lightcurves_per_star == 1
        assert args.snr_threshold == 5.0
        assert args.resume is False
        assert args.skip_scan is False
        assert args.limit_pairs is None

    def test_limit_pairs(self):
        args = _mod._parse_args(["--limit-pairs", "5"])
        assert args.limit_pairs == 5

    def test_resume_flag(self):
        args = _mod._parse_args(["--resume"])
        assert args.resume is True

    def test_skip_flags(self):
        args = _mod._parse_args([
            "--skip-scan", "--skip-ranking", "--skip-vetting",
            "--skip-external", "--skip-stats",
        ])
        assert args.skip_scan is True
        assert args.skip_ranking is True
        assert args.skip_vetting is True
        assert args.skip_external is True
        assert args.skip_stats is True

    def test_custom_prefix(self):
        args = _mod._parse_args(["--output-prefix", "my_run"])
        assert args.output_prefix == "my_run"

    def test_sigma_threshold(self):
        args = _mod._parse_args(["--sigma-threshold", "3.5"])
        assert abs(args.sigma_threshold - 3.5) < 1e-9

    def test_skip_external_catalogs(self):
        args = _mod._parse_args(["--skip-vsx", "--skip-simbad", "--skip-tess-eb"])
        assert args.skip_vsx is True
        assert args.skip_simbad is True
        assert args.skip_tess_eb is True
