"""Tests for Phase 5E candidate consolidation functions.

All tests use synthetic data — no network calls, no real TESS downloads.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from astrohunter.consolidation import (
    CONSOLIDATION_VERSION,
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_MEDIUM,
    PRIORITY_OVERTRIGGERED,
    _assign_star_priority,
    attach_scan_status,
    build_manual_review_priority_table,
    identify_overtriggered_stars,
    select_top_event_per_star,
    summarize_candidates_by_star,
    summarize_pass_candidates,
)


# ============================================================================
# Synthetic data factories
# ============================================================================

def _make_events(
    tic_ids: list[int],
    roles: list[str] | None = None,
    n_per_tic: int = 1,
    scores: list[float] | None = None,
    snrs: list[float] | None = None,
    vetting_status: str = "flagged",
    ext_flag: str = "no_external_match",
) -> pd.DataFrame:
    """Build a minimal event-level candidate DataFrame for testing."""
    rows = []
    for i, tic in enumerate(tic_ids):
        role = (roles[i] if roles else "target") if roles else "target"
        for j in range(n_per_tic):
            score = scores[i] if scores else 0.5
            snr = snrs[i] if snrs else 5.0
            rows.append({
                "tic_id": tic,
                "target_name": f"Star {tic}",
                "sample_role": role,
                "event_time_btjd": 1000.0 + j * 10,
                "depth_ppm": 1000.0,
                "local_snr": snr + j * 0.1,
                "duration_hours": 2.0,
                "final_candidate_score": score,
                "ml_score": score * 0.9,
                "quality_score": 0.5,
                "automated_vetting_status": vetting_status,
                "external_false_positive_flag": ext_flag,
                "flag_external_catalog_match": False,
                "flag_low_snr": False,
                "flag_edge_event": False,
                "flag_single_point_like": False,
                "flag_likely_flare_shape": False,
                "flag_low_delta_chi2": True,
                "flag_poor_asymmetry_fit": False,
                "tess_eb_check_status": "not_found",
                "vsx_match_name": "",
                "simbad_otype": "*",
            })
    return pd.DataFrame(rows)


def _make_scan_status(
    tic_ids: list[int],
    roles: list[str] | None = None,
    successes: list[bool] | None = None,
) -> pd.DataFrame:
    rows = []
    for i, tic in enumerate(tic_ids):
        rows.append({
            "tic_id": tic,
            "sample_role": (roles[i] if roles else "target"),
            "matched_pair_id": i,
            "star_name": f"Star {tic}",
            "attempted": True,
            "success": (successes[i] if successes else True),
            "failure_reason": "",
            "n_candidates": 1,
            "cache_used": True,
            "scan_timestamp": "2026-01-01T00:00:00",
        })
    return pd.DataFrame(rows)


# ============================================================================
# summarize_candidates_by_star
# ============================================================================

class TestSummarizeCandidatesByStar:
    def test_empty_input_returns_empty(self):
        df = pd.DataFrame(columns=["tic_id", "sample_role", "automated_vetting_status"])
        result = summarize_candidates_by_star(df)
        assert result.empty

    def test_one_event_per_tic(self):
        df = _make_events([1001, 1002, 1003])
        result = summarize_candidates_by_star(df)
        assert len(result) == 3
        assert set(result["tic_id"].tolist()) == {1001, 1002, 1003}

    def test_n_events_counted_correctly(self):
        df = _make_events([1001, 1001, 1002], n_per_tic=1)
        # Two events for 1001 since we passed tic 1001 twice
        df2 = pd.concat([_make_events([1001], n_per_tic=3), _make_events([1002], n_per_tic=1)], ignore_index=True)
        result = summarize_candidates_by_star(df2)
        n_1001 = int(result.loc[result["tic_id"] == 1001, "n_events"].iloc[0])
        n_1002 = int(result.loc[result["tic_id"] == 1002, "n_events"].iloc[0])
        assert n_1001 == 3
        assert n_1002 == 1

    def test_pass_count(self):
        df = _make_events([1001] * 4, n_per_tic=1)
        # Mix pass and flagged
        df = _make_events([1001], n_per_tic=4)
        df.loc[:1, "automated_vetting_status"] = "pass"
        df.loc[2:, "automated_vetting_status"] = "flagged"
        result = summarize_candidates_by_star(df)
        n_pass = int(result.loc[result["tic_id"] == 1001, "n_pass_automated_vetting"].iloc[0])
        assert n_pass == 2

    def test_max_score_computed(self):
        df = _make_events([1001], n_per_tic=3)
        df["final_candidate_score"] = [0.3, 0.8, 0.5]
        result = summarize_candidates_by_star(df)
        max_score = float(result.loc[result["tic_id"] == 1001, "max_final_candidate_score"].iloc[0])
        assert abs(max_score - 0.8) < 1e-9

    def test_median_snr_computed(self):
        df = _make_events([1001], n_per_tic=4)
        df["local_snr"] = [4.0, 6.0, 8.0, 10.0]
        result = summarize_candidates_by_star(df)
        med = float(result.loc[result["tic_id"] == 1001, "median_local_snr"].iloc[0])
        assert abs(med - 7.0) < 1e-9

    def test_has_known_variable_match_true(self):
        df = _make_events([1001], n_per_tic=2)
        df.loc[0, "external_false_positive_flag"] = "known_variable_match"
        result = summarize_candidates_by_star(df)
        assert bool(result.loc[result["tic_id"] == 1001, "has_known_variable_match"].iloc[0])

    def test_has_known_variable_match_false_when_no_match(self):
        df = _make_events([1001], n_per_tic=2)
        result = summarize_candidates_by_star(df)
        assert not bool(result.loc[result["tic_id"] == 1001, "has_known_variable_match"].iloc[0])

    def test_has_tess_eb_match_true(self):
        df = _make_events([1001], n_per_tic=2)
        df.loc[0, "tess_eb_check_status"] = "matched"
        result = summarize_candidates_by_star(df)
        assert bool(result.loc[result["tic_id"] == 1001, "has_tess_eb_match"].iloc[0])

    def test_sorted_by_n_events_descending(self):
        df = pd.concat([
            _make_events([1001], n_per_tic=1),
            _make_events([1002], n_per_tic=3),
            _make_events([1003], n_per_tic=2),
        ], ignore_index=True)
        result = summarize_candidates_by_star(df)
        assert result["n_events"].tolist() == [3, 2, 1]

    def test_consolidation_version_column_present(self):
        df = _make_events([1001])
        result = summarize_candidates_by_star(df)
        assert "consolidation_version" in result.columns
        assert result["consolidation_version"].iloc[0] == CONSOLIDATION_VERSION

    def test_time_range_columns(self):
        df = _make_events([1001], n_per_tic=3)
        df["event_time_btjd"] = [100.0, 200.0, 150.0]
        result = summarize_candidates_by_star(df)
        assert abs(float(result.loc[result["tic_id"] == 1001, "min_event_time_btjd"].iloc[0]) - 100.0) < 1e-6
        assert abs(float(result.loc[result["tic_id"] == 1001, "max_event_time_btjd"].iloc[0]) - 200.0) < 1e-6


# ============================================================================
# _assign_star_priority
# ============================================================================

class TestAssignStarPriority:
    def test_overtriggered_takes_precedence(self):
        priority = _assign_star_priority(
            n_events=10, n_pass=2, has_concern_flag=False, has_tess_eb=False,
            max_score=0.9, max_snr=30.0, n_external_flags=0, overtrigger_threshold=5,
        )
        assert priority == PRIORITY_OVERTRIGGERED

    def test_high_when_pass_and_no_concern(self):
        priority = _assign_star_priority(
            n_events=2, n_pass=1, has_concern_flag=False, has_tess_eb=False,
            max_score=0.85, max_snr=8.0, n_external_flags=0, overtrigger_threshold=5,
        )
        assert priority == PRIORITY_HIGH

    def test_medium_when_pass_with_concern_flag(self):
        priority = _assign_star_priority(
            n_events=2, n_pass=1, has_concern_flag=True, has_tess_eb=False,
            max_score=0.85, max_snr=8.0, n_external_flags=0, overtrigger_threshold=5,
        )
        assert priority == PRIORITY_MEDIUM

    def test_medium_when_pass_with_tess_eb(self):
        priority = _assign_star_priority(
            n_events=2, n_pass=1, has_concern_flag=False, has_tess_eb=True,
            max_score=0.85, max_snr=8.0, n_external_flags=0, overtrigger_threshold=5,
        )
        assert priority == PRIORITY_MEDIUM

    def test_medium_when_high_score_no_flags(self):
        priority = _assign_star_priority(
            n_events=1, n_pass=0, has_concern_flag=False, has_tess_eb=False,
            max_score=0.75, max_snr=5.0, n_external_flags=0, overtrigger_threshold=5,
        )
        assert priority == PRIORITY_MEDIUM

    def test_medium_when_high_snr_no_flags(self):
        priority = _assign_star_priority(
            n_events=1, n_pass=0, has_concern_flag=False, has_tess_eb=False,
            max_score=0.4, max_snr=8.0, n_external_flags=0, overtrigger_threshold=5,
        )
        assert priority == PRIORITY_MEDIUM

    def test_low_when_concern_flag_and_no_pass(self):
        priority = _assign_star_priority(
            n_events=1, n_pass=0, has_concern_flag=True, has_tess_eb=False,
            max_score=0.8, max_snr=10.0, n_external_flags=2, overtrigger_threshold=5,
        )
        assert priority == PRIORITY_LOW

    def test_low_when_low_score_and_no_pass(self):
        priority = _assign_star_priority(
            n_events=1, n_pass=0, has_concern_flag=False, has_tess_eb=False,
            max_score=0.3, max_snr=3.0, n_external_flags=0, overtrigger_threshold=5,
        )
        assert priority == PRIORITY_LOW

    def test_exactly_at_overtrigger_threshold(self):
        priority = _assign_star_priority(
            n_events=5, n_pass=0, has_concern_flag=False, has_tess_eb=False,
            max_score=0.5, max_snr=5.0, n_external_flags=0, overtrigger_threshold=5,
        )
        assert priority == PRIORITY_OVERTRIGGERED

    def test_one_below_threshold_not_overtriggered(self):
        priority = _assign_star_priority(
            n_events=4, n_pass=0, has_concern_flag=False, has_tess_eb=False,
            max_score=0.5, max_snr=5.0, n_external_flags=0, overtrigger_threshold=5,
        )
        assert priority != PRIORITY_OVERTRIGGERED

    def test_external_variable_match_lowers_high_to_medium(self):
        # With concern flag, even pass candidates get at most medium
        priority = _assign_star_priority(
            n_events=3, n_pass=2, has_concern_flag=True, has_tess_eb=False,
            max_score=0.9, max_snr=20.0, n_external_flags=2, overtrigger_threshold=5,
        )
        assert priority == PRIORITY_MEDIUM

    def test_tess_eb_lowers_high_to_medium(self):
        priority = _assign_star_priority(
            n_events=2, n_pass=1, has_concern_flag=False, has_tess_eb=True,
            max_score=0.9, max_snr=20.0, n_external_flags=0, overtrigger_threshold=5,
        )
        assert priority == PRIORITY_MEDIUM


# ============================================================================
# select_top_event_per_star
# ============================================================================

class TestSelectTopEventPerStar:
    def test_empty_returns_empty(self):
        df = pd.DataFrame(columns=["tic_id", "final_candidate_score"])
        result = select_top_event_per_star(df)
        assert result.empty

    def test_one_event_per_tic(self):
        df = _make_events([1001, 1002])
        result = select_top_event_per_star(df)
        assert len(result) == 2

    def test_selects_highest_score_per_tic(self):
        df = _make_events([1001], n_per_tic=4)
        df["final_candidate_score"] = [0.3, 0.9, 0.5, 0.7]
        result = select_top_event_per_star(df)
        assert len(result) == 1
        assert abs(float(result["final_candidate_score"].iloc[0]) - 0.9) < 1e-9

    def test_tiebreak_by_snr(self):
        df = _make_events([1001], n_per_tic=3)
        df["final_candidate_score"] = [0.8, 0.8, 0.8]
        df["local_snr"] = [5.0, 12.0, 8.0]
        result = select_top_event_per_star(df)
        assert abs(float(result["local_snr"].iloc[0]) - 12.0) < 1e-9

    def test_all_tics_represented(self):
        df = _make_events([1, 2, 3, 4, 5])
        result = select_top_event_per_star(df)
        assert set(result["tic_id"].tolist()) == {1, 2, 3, 4, 5}


# ============================================================================
# identify_overtriggered_stars
# ============================================================================

class TestIdentifyOvertriggeredStars:
    def test_empty_returns_empty(self):
        df = pd.DataFrame(columns=["tic_id", "sample_role"])
        result = identify_overtriggered_stars(df)
        assert result.empty

    def test_no_overtriggered_returns_empty(self):
        df = _make_events([1001, 1002, 1003], n_per_tic=1)
        result = identify_overtriggered_stars(df, threshold_events=5)
        assert result.empty

    def test_identifies_overtriggered(self):
        df = pd.concat([
            _make_events([1001], n_per_tic=7),
            _make_events([1002], n_per_tic=2),
            _make_events([1003], n_per_tic=5),
        ], ignore_index=True)
        result = identify_overtriggered_stars(df, threshold_events=5)
        assert set(result["tic_id"].tolist()) == {1001, 1003}
        assert 1002 not in result["tic_id"].tolist()

    def test_sorted_by_n_events_desc(self):
        df = pd.concat([
            _make_events([1001], n_per_tic=10),
            _make_events([1002], n_per_tic=6),
        ], ignore_index=True)
        result = identify_overtriggered_stars(df, threshold_events=5)
        assert result["n_events"].tolist()[0] >= result["n_events"].tolist()[-1]

    def test_threshold_boundary_inclusive(self):
        df = _make_events([1001], n_per_tic=5)
        result = identify_overtriggered_stars(df, threshold_events=5)
        assert len(result) == 1

    def test_one_below_threshold_not_included(self):
        df = _make_events([1001], n_per_tic=4)
        result = identify_overtriggered_stars(df, threshold_events=5)
        assert result.empty

    def test_n_events_column_accurate(self):
        df = _make_events([1001], n_per_tic=9)
        result = identify_overtriggered_stars(df, threshold_events=5)
        assert int(result.loc[result["tic_id"] == 1001, "n_events"].iloc[0]) == 9


# ============================================================================
# build_manual_review_priority_table
# ============================================================================

class TestBuildManualReviewPriorityTable:
    def test_empty_returns_empty(self):
        df = pd.DataFrame(columns=["tic_id", "final_candidate_score"])
        result = build_manual_review_priority_table(df, max_events_per_star=3)
        assert result.empty

    def test_limits_events_per_star(self):
        df = _make_events([1001], n_per_tic=10)
        result = build_manual_review_priority_table(df, max_events_per_star=3)
        n_1001 = int((result["tic_id"] == 1001).sum())
        assert n_1001 == 3

    def test_max_events_per_star_one(self):
        df = _make_events([1001, 1002], n_per_tic=5)
        result = build_manual_review_priority_table(df, max_events_per_star=1)
        assert len(result) == 2

    def test_priority_column_attached(self):
        df = _make_events([1001], n_per_tic=2)
        result = build_manual_review_priority_table(df, max_events_per_star=3)
        assert "recommended_review_priority" in result.columns

    def test_overtriggered_priority_applied(self):
        df = _make_events([1001], n_per_tic=8)
        result = build_manual_review_priority_table(
            df, max_events_per_star=3, overtrigger_threshold=5
        )
        priorities = result.loc[result["tic_id"] == 1001, "recommended_review_priority"].unique()
        assert PRIORITY_OVERTRIGGERED in priorities

    def test_top_scored_events_selected(self):
        df = _make_events([1001], n_per_tic=5)
        df["final_candidate_score"] = [0.9, 0.1, 0.7, 0.3, 0.5]
        result = build_manual_review_priority_table(df, max_events_per_star=2)
        scores = sorted(result["final_candidate_score"].tolist(), reverse=True)
        # Top 2 should be 0.9 and 0.7
        assert scores[0] >= 0.9 - 1e-9
        assert scores[1] >= 0.7 - 1e-9

    def test_does_not_modify_input(self):
        df = _make_events([1001], n_per_tic=5)
        original_len = len(df)
        build_manual_review_priority_table(df, max_events_per_star=2)
        assert len(df) == original_len


# ============================================================================
# summarize_pass_candidates
# ============================================================================

class TestSummarizePassCandidates:
    def test_empty_returns_empty(self):
        result = summarize_pass_candidates(pd.DataFrame())
        assert result.empty

    def test_no_pass_returns_empty(self):
        df = _make_events([1001, 1002], vetting_status="flagged")
        result = summarize_pass_candidates(df)
        assert result.empty

    def test_returns_only_pass(self):
        df = pd.concat([
            _make_events([1001], vetting_status="pass"),
            _make_events([1002], vetting_status="flagged"),
        ], ignore_index=True)
        result = summarize_pass_candidates(df)
        assert len(result) == 1
        assert int(result["tic_id"].iloc[0]) == 1001

    def test_multiple_pass_returned(self):
        df = _make_events([1001, 1002, 1003], vetting_status="pass")
        result = summarize_pass_candidates(df)
        assert len(result) == 3

    def test_pass_candidates_by_role(self):
        df = pd.concat([
            _make_events([1001], roles=["target"], vetting_status="pass"),
            _make_events([1002], roles=["control"], vetting_status="pass"),
            _make_events([1003], roles=["target"], vetting_status="flagged"),
        ], ignore_index=True)
        result = summarize_pass_candidates(df)
        assert int((result["sample_role"] == "target").sum()) == 1
        assert int((result["sample_role"] == "control").sum()) == 1


# ============================================================================
# attach_scan_status
# ============================================================================

class TestAttachScanStatus:
    def test_empty_scan_status_returns_candidate_unchanged(self):
        cands = _make_events([1001, 1002])
        status = pd.DataFrame()
        result = attach_scan_status(cands, status)
        assert len(result) == len(cands)
        assert list(result.columns) == list(cands.columns)

    def test_attaches_cache_used(self):
        cands = _make_events([1001])
        status = _make_scan_status([1001], successes=[True])
        result = attach_scan_status(cands, status)
        assert "cache_used" in result.columns

    def test_does_not_overwrite_existing_columns(self):
        cands = _make_events([1001])
        cands["cache_used"] = "EXISTING"
        status = _make_scan_status([1001])
        result = attach_scan_status(cands, status)
        # Since cache_used already existed, it should not be added again
        assert result["cache_used"].iloc[0] == "EXISTING"

    def test_unknown_tic_gets_nan(self):
        cands = _make_events([9999])
        status = _make_scan_status([1001])
        result = attach_scan_status(cands, status)
        assert "cache_used" in result.columns
        # 9999 is not in status, so cache_used should be NaN
        assert pd.isna(result.loc[result["tic_id"] == 9999, "cache_used"].iloc[0])


# ============================================================================
# Plotting functions — verify files are created (no display)
# ============================================================================

class TestPlottingFunctions:
    def _make_star_summary(self, n=5):
        rows = []
        for i in range(n):
            rows.append({
                "tic_id": 1000 + i,
                "target_name": f"Star {i}",
                "sample_role": "target" if i % 2 == 0 else "control",
                "n_events": i + 1,
                "n_pass_automated_vetting": 1 if i == 0 else 0,
                "n_external_flags": 0,
                "max_final_candidate_score": 0.8 - i * 0.1,
                "max_local_snr": 8.0 - i * 0.5,
                "median_local_snr": 6.0,
                "max_depth_ppm": 1000.0,
                "min_event_time_btjd": 1000.0,
                "max_event_time_btjd": 2000.0,
                "has_known_variable_match": False,
                "has_tess_eb_match": False,
                "recommended_review_priority": [PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW, PRIORITY_LOW, PRIORITY_OVERTRIGGERED][i],
                "consolidation_version": CONSOLIDATION_VERSION,
            })
        return pd.DataFrame(rows)

    def test_plot_candidates_per_star_creates_file(self):
        from astrohunter.plotting import plot_candidates_per_star
        star_df = self._make_star_summary()
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            out = Path(f.name)
        plot_candidates_per_star(star_df, output_path=out)
        assert out.exists() and out.stat().st_size > 0
        out.unlink()

    def test_plot_candidates_per_star_empty(self):
        from astrohunter.plotting import plot_candidates_per_star
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            out = Path(f.name)
        plot_candidates_per_star(pd.DataFrame(), output_path=out)
        assert out.exists()
        out.unlink()

    def test_plot_top_scores_by_star_creates_file(self):
        from astrohunter.plotting import plot_top_scores_by_star
        df = _make_events([1001, 1002, 1003])
        df["recommended_review_priority"] = [PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW]
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            out = Path(f.name)
        plot_top_scores_by_star(df, output_path=out)
        assert out.exists() and out.stat().st_size > 0
        out.unlink()

    def test_plot_pass_candidates_by_role_creates_file(self):
        from astrohunter.plotting import plot_pass_candidates_by_role
        df = pd.concat([
            _make_events([1001], roles=["target"], vetting_status="pass"),
            _make_events([1002], roles=["control"], vetting_status="flagged"),
        ], ignore_index=True)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            out = Path(f.name)
        plot_pass_candidates_by_role(df, output_path=out)
        assert out.exists() and out.stat().st_size > 0
        out.unlink()

    def test_plot_pass_candidates_by_role_empty(self):
        from astrohunter.plotting import plot_pass_candidates_by_role
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            out = Path(f.name)
        plot_pass_candidates_by_role(pd.DataFrame(), output_path=out)
        assert out.exists()
        out.unlink()
