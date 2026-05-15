"""Tests for Phase 5B matched scan scripts and stats improvements.

All tests use synthetic data — no network calls, no real TESS downloads.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Ensure the src package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from astrohunter.stats import (
    compute_candidate_yield_by_role,
    bootstrap_rate_ratio,
    summarize_rate_statistics,
    MIN_CANDIDATES_FOR_STABLE_STATS,
)
from astrohunter.vetting import add_basic_vetting_flags


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_matched_pairs(
    n_target: int = 5,
    n_control: int = 5,
    base_target: int = 10_000,
    base_control: int = 20_000,
) -> pd.DataFrame:
    target_tics = [base_target + i for i in range(n_target)]
    control_tics = [base_control + i for i in range(n_control)]
    return pd.DataFrame({
        "target_tic_id": target_tics,
        "target_name": [f"Star_T{i}" for i in range(n_target)],
        "control_tic_id": control_tics,
    })


def _make_candidate_df(
    tic_ids: list[int],
    roles: list[str],
    snr_values: list[float] | None = None,
) -> pd.DataFrame:
    n = len(tic_ids)
    assert len(roles) == n
    if snr_values is None:
        snr_values = [6.0] * n
    return pd.DataFrame({
        "tic_id": tic_ids,
        "sample_role": roles,
        "target_name": [f"TIC {t}" for t in tic_ids],
        "local_snr": snr_values,
        "depth_ppm": [500.0] * n,
        "duration_hours": [2.0] * n,
        "fwhm_hours": [1.0] * n,
        "egress_ingress_ratio": [2.0] * n,
        "skewness": [-0.5] * n,
        "delta_chi2_asym": [20.0] * n,
        "edge_event": [False] * n,
        "single_point_like": [False] * n,
        "final_candidate_score": [0.6] * n,
        "automated_vetting_status": ["pass"] * n,
        "pair_id": list(range(n)),
    })


def _make_scan_meta(
    target_tics_scanned: list[int],
    control_tics_scanned: list[int],
) -> dict:
    return {
        "n_target_attempted": len(target_tics_scanned),
        "n_control_attempted": len(control_tics_scanned),
        "n_target_success": len(target_tics_scanned),
        "n_control_success": len(control_tics_scanned),
        "n_target_failed": 0,
        "n_control_failed": 0,
        "target_tics_scanned": target_tics_scanned,
        "control_tics_scanned": control_tics_scanned,
        "target_tics_failed": [],
        "control_tics_failed": [],
    }


# ---------------------------------------------------------------------------
# sample_role column assignment
# ---------------------------------------------------------------------------

class TestSampleRoleAssignment:
    def test_role_column_used_directly(self):
        pairs = _make_matched_pairs(5, 5)
        cands = _make_candidate_df(
            [10_000, 10_001, 20_000],
            ["target", "target", "control"],
        )
        result = compute_candidate_yield_by_role(cands, pairs)
        assert result["target_candidates"] == 2
        assert result["control_candidates"] == 1

    def test_zero_control_candidates(self):
        pairs = _make_matched_pairs(5, 5)
        cands = _make_candidate_df([10_000, 10_001], ["target", "target"])
        result = compute_candidate_yield_by_role(cands, pairs)
        assert result["target_candidates"] == 2
        assert result["control_candidates"] == 0

    def test_tic_lookup_fallback_when_no_sample_role(self):
        pairs = _make_matched_pairs(5, 5)
        # No sample_role column
        cands = pd.DataFrame({
            "tic_id": [10_000, 20_000],
            "local_snr": [6.0, 6.0],
        })
        result = compute_candidate_yield_by_role(cands, pairs)
        assert result["target_candidates"] == 1
        assert result["control_candidates"] == 1

    def test_unknown_tic_counted(self):
        pairs = _make_matched_pairs(3, 3)
        cands = _make_candidate_df([99_999], ["target"])
        # TIC 99999 is in sample_role="target" so counted from sample_role
        result = compute_candidate_yield_by_role(cands, pairs)
        assert result["target_candidates"] == 1
        assert result["unknown_candidates"] == 0

    def test_empty_candidate_table(self):
        pairs = _make_matched_pairs(3, 3)
        cands = _make_candidate_df([], [])
        result = compute_candidate_yield_by_role(cands, pairs)
        assert result["target_candidates"] == 0
        assert result["control_candidates"] == 0


# ---------------------------------------------------------------------------
# Scan metadata exposure
# ---------------------------------------------------------------------------

class TestScanMetaExposure:
    def test_scan_meta_overrides_pairs_count(self):
        pairs = _make_matched_pairs(10, 10)  # 10 pairs each
        meta = _make_scan_meta(
            target_tics_scanned=[10_000, 10_001],   # only 2 scanned
            control_tics_scanned=[20_000],           # only 1 scanned
        )
        cands = _make_candidate_df([10_000], ["target"])
        result = compute_candidate_yield_by_role(cands, pairs, scan_meta=meta)
        assert result["target_exposure"] == 2.0
        assert result["control_exposure"] == 1.0
        assert result["exposure_source"] == "scan_meta_actual"

    def test_no_scan_meta_uses_pairs_total(self):
        pairs = _make_matched_pairs(7, 7)
        cands = _make_candidate_df([10_000], ["target"])
        result = compute_candidate_yield_by_role(cands, pairs, scan_meta=None)
        assert result["target_exposure"] == 7.0
        assert result["exposure_source"] == "matched_pairs_total"

    def test_scan_meta_empty_scanned_lists(self):
        pairs = _make_matched_pairs(5, 5)
        meta = _make_scan_meta([], [])  # nothing scanned
        cands = _make_candidate_df([10_000], ["target"])
        result = compute_candidate_yield_by_role(cands, pairs, scan_meta=meta)
        # Should not divide by zero — min exposure = 1
        assert result["target_exposure"] >= 1.0
        assert result["control_exposure"] >= 1.0


# ---------------------------------------------------------------------------
# Duplicate TIC handling
# ---------------------------------------------------------------------------

class TestDuplicateTicHandling:
    def test_same_tic_multiple_events_counted(self):
        """Multiple events from the same star contribute independently to counts."""
        pairs = _make_matched_pairs(5, 5)
        cands = _make_candidate_df(
            [10_000, 10_000, 20_000],
            ["target", "target", "control"],
        )
        result = compute_candidate_yield_by_role(cands, pairs)
        # Both events from TIC 10000 count (events, not unique stars)
        assert result["target_candidates"] == 2
        assert result["control_candidates"] == 1


# ---------------------------------------------------------------------------
# Bootstrap with scan_meta
# ---------------------------------------------------------------------------

class TestBootstrapWithScanMeta:
    def test_bootstrap_uses_scan_meta_exposure(self):
        pairs = _make_matched_pairs(10, 10)
        meta = _make_scan_meta(
            [10_000, 10_001, 10_002],
            [20_000, 20_001],
        )
        cands = _make_candidate_df(
            [10_000, 10_001, 20_000],
            ["target", "target", "control"],
        )
        result = bootstrap_rate_ratio(cands, pairs, n_bootstrap=100, random_state=0, scan_meta=meta)
        assert "bootstrap_rate_ratio_median" in result
        assert result["n_bootstrap"] == 100

    def test_bootstrap_zero_control_all_nan(self):
        pairs = _make_matched_pairs(5, 5)
        cands = _make_candidate_df([10_000, 10_001], ["target", "target"])
        result = bootstrap_rate_ratio(cands, pairs, n_bootstrap=100, random_state=42)
        # All bootstrap replicates have 0 control → all NaN → median NaN
        assert result["n_finite_replicates"] == 0
        assert math.isnan(result["bootstrap_rate_ratio_median"])


# ---------------------------------------------------------------------------
# Zero candidate handling in summarize
# ---------------------------------------------------------------------------

class TestZeroCandidateSummarize:
    def test_empty_dataframe_no_crash(self):
        pairs = _make_matched_pairs(5, 5)
        cands = add_basic_vetting_flags(_make_candidate_df([], []))
        result = summarize_rate_statistics(cands, pairs, n_bootstrap=20)
        assert isinstance(result, pd.DataFrame)
        assert len(result) > 0

    def test_preliminary_warning_set(self):
        pairs = _make_matched_pairs(5, 5)
        cands = add_basic_vetting_flags(_make_candidate_df([10_000], ["target"]))
        result = summarize_rate_statistics(cands, pairs, n_bootstrap=20)
        assert result["preliminary_warning"].notna().any()

    def test_scan_meta_passed_through(self):
        pairs = _make_matched_pairs(5, 5)
        meta = _make_scan_meta([10_000, 10_001], [20_000])
        cands = add_basic_vetting_flags(_make_candidate_df([10_000, 20_000], ["target", "control"]))
        result = summarize_rate_statistics(cands, pairs, n_bootstrap=20, scan_meta=meta)
        assert "exposure_source" in result.columns
        assert (result["exposure_source"] == "scan_meta_actual").any()


# ---------------------------------------------------------------------------
# run_matched_scan.py CLI unit tests (no network)
# ---------------------------------------------------------------------------

class TestRunMatchedScanCLI:
    """Test the CLI argument parsing and helper functions without network calls."""

    def test_parse_args_defaults(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        from run_matched_scan import _parse_args
        args = _parse_args([])
        assert args.max_pairs == 28
        assert args.max_lightcurves_per_star == 1
        assert args.sigma_threshold == 4.0
        assert args.include_targets is True
        assert args.include_controls is True

    def test_parse_args_no_targets(self):
        from run_matched_scan import _parse_args
        args = _parse_args(["--no-targets"])
        assert args.include_targets is False
        assert args.include_controls is True

    def test_parse_args_no_controls(self):
        from run_matched_scan import _parse_args
        args = _parse_args(["--no-controls"])
        assert args.include_controls is False
        assert args.include_targets is True

    def test_load_name_map_from_synthetic_csv(self, tmp_path):
        from run_matched_scan import _load_name_map
        ts_path = tmp_path / "target_sample.csv"
        ts_path.write_text("tic_id,target_name\n1001,Star A\n1002,Star B\n")
        cp_path = tmp_path / "control_pool.csv"
        cp_path.write_text("tic_id\n2001\n2002\n")
        name_map = _load_name_map(ts_path, cp_path)
        assert name_map[1001] == "Star A"
        assert name_map[2001] == "TIC 2001"

    def test_main_no_matched_pairs_file(self, tmp_path):
        from run_matched_scan import main
        ret = main([
            "--matched-pairs", str(tmp_path / "nonexistent.csv"),
            "--output", str(tmp_path / "out.csv"),
        ])
        assert ret == 1

    def test_main_writes_empty_table_when_no_candidates(self, tmp_path):
        """main() with an empty matched_pairs should exit cleanly."""
        from run_matched_scan import main
        mp_path = tmp_path / "matched_pairs.csv"
        mp_path.write_text("target_tic_id,control_tic_id\n")
        out_path = tmp_path / "out.csv"
        ret = main([
            "--matched-pairs", str(mp_path),
            "--target-catalog", str(tmp_path / "ts.csv"),
            "--control-pool", str(tmp_path / "cp.csv"),
            "--output", str(out_path),
            "--max-pairs", "0",
        ])
        assert ret == 0
        assert out_path.exists()


# ---------------------------------------------------------------------------
# Phase 5B plotting smoke tests
# ---------------------------------------------------------------------------

class TestPhase5BPlots:
    def test_plot_target_control_candidate_counts_with_data(self, tmp_path):
        from astrohunter.plotting import plot_target_control_candidate_counts
        cands = add_basic_vetting_flags(
            _make_candidate_df([10_000, 20_000], ["target", "control"])
        )
        out = tmp_path / "tc_counts.png"
        plot_target_control_candidate_counts(cands, output_path=out)
        assert out.exists()
        import matplotlib.pyplot as plt
        plt.close("all")

    def test_plot_target_control_candidate_counts_with_summary(self, tmp_path):
        from astrohunter.plotting import plot_target_control_candidate_counts
        from astrohunter.stats import summarize_rate_statistics
        pairs = _make_matched_pairs(5, 5)
        cands = add_basic_vetting_flags(
            _make_candidate_df([10_000, 20_000], ["target", "control"])
        )
        summary = summarize_rate_statistics(cands, pairs, n_bootstrap=20)
        out = tmp_path / "tc_counts_with_rates.png"
        plot_target_control_candidate_counts(cands, summary, output_path=out)
        assert out.exists()
        import matplotlib.pyplot as plt
        plt.close("all")

    def test_plot_target_control_empty_dataframe(self, tmp_path):
        from astrohunter.plotting import plot_target_control_candidate_counts
        out = tmp_path / "tc_empty.png"
        plot_target_control_candidate_counts(pd.DataFrame(), output_path=out)
        assert out.exists()
        import matplotlib.pyplot as plt
        plt.close("all")

    def test_matched_scan_score_distribution_plot(self, tmp_path):
        """Score distribution with sample_role column should not crash."""
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        from rank_matched_scan import _plot_matched_score_distribution
        cands = add_basic_vetting_flags(
            _make_candidate_df([10_000, 20_000], ["target", "control"])
        )
        out = tmp_path / "score_dist.png"
        _plot_matched_score_distribution(cands, out)
        assert out.exists()
        plt.close("all")

    def test_matched_scan_score_distribution_empty(self, tmp_path):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from rank_matched_scan import _plot_matched_score_distribution
        out = tmp_path / "score_dist_empty.png"
        _plot_matched_score_distribution(pd.DataFrame(), out)
        assert out.exists()
        plt.close("all")
