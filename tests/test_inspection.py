"""Tests for Phase 5F: inspection.py and plot_manual_review_priority_overview.

All tests are network-free and use synthetic data.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from astrohunter.inspection import (
    DISPOSITION_COLUMNS,
    INSPECTION_VERSION,
    MANUAL_LABEL_ALLOWED,
    build_inspection_target_list,
    create_disposition_template,
    create_event_inspection_plot,
    create_star_event_gallery,
    extract_event_window,
    load_cached_lightcurve_for_tic,
)
from astrohunter.plotting import plot_manual_review_priority_overview


# ---------------------------------------------------------------------------
# Synthetic data factories
# ---------------------------------------------------------------------------

def _make_candidates(
    n_target=3,
    n_control_ot=7,
    n_control_low=2,
    rng_seed=42,
) -> pd.DataFrame:
    """Build a synthetic candidate DataFrame with three TICs.

    TIC 1001: target, 3 events, low priority.
    TIC 1002: control, 7 events (overtriggered), 1 pass event.
    TIC 2001: control, 2 events, low priority.
    """
    rng = np.random.default_rng(rng_seed)
    rows = []

    # TIC 1001 – target, low-count
    for i in range(n_target):
        rows.append({
            "tic_id": 1001,
            "sample_role": "target",
            "target_name": "Test Star A",
            "event_time_btjd": 2000.0 + i * 10.0,
            "local_snr": 4.0 + rng.uniform(),
            "final_candidate_score": 0.50 + rng.uniform() * 0.1,
            "automated_vetting_status": "flagged",
            "external_false_positive_flag": "no_external_match",
            "depth_ppm": 300,
            "duration_hours": 2.0,
            "flag_low_snr": True,
            "flag_edge_event": False,
            "flag_single_point_like": False,
            "flag_likely_flare_shape": False,
            "flag_low_delta_chi2": False,
            "flag_poor_asymmetry_fit": False,
        })

    # TIC 1002 – control, overtriggered, first event is pass
    for i in range(n_control_ot):
        rows.append({
            "tic_id": 1002,
            "sample_role": "control",
            "target_name": "Test Star B",
            "event_time_btjd": 3000.0 + i * 5.0,
            "local_snr": 25.0 + rng.uniform(),
            "final_candidate_score": 0.85 + rng.uniform() * 0.05,
            "automated_vetting_status": "pass" if i == 0 else "flagged",
            "external_false_positive_flag": "no_external_match",
            "depth_ppm": 800,
            "duration_hours": 1.5,
            "flag_low_snr": False,
            "flag_edge_event": False,
            "flag_single_point_like": False,
            "flag_likely_flare_shape": False,
            "flag_low_delta_chi2": False,
            "flag_poor_asymmetry_fit": False,
        })

    # TIC 2001 – control, low
    for i in range(n_control_low):
        rows.append({
            "tic_id": 2001,
            "sample_role": "control",
            "target_name": "Test Star C",
            "event_time_btjd": 4000.0 + i * 10.0,
            "local_snr": 3.5,
            "final_candidate_score": 0.35,
            "automated_vetting_status": "flagged",
            "external_false_positive_flag": "no_external_match",
            "depth_ppm": 200,
            "duration_hours": 1.0,
            "flag_low_snr": True,
            "flag_edge_event": False,
            "flag_single_point_like": False,
            "flag_likely_flare_shape": False,
            "flag_low_delta_chi2": False,
            "flag_poor_asymmetry_fit": False,
        })

    return pd.DataFrame(rows)


def _make_priority_df(medium_tics: list[int] | None = None) -> pd.DataFrame:
    """Build a synthetic manual review priority table."""
    if medium_tics is None:
        medium_tics = []
    cands = _make_candidates()
    rows = []
    priority_map = {tic: "medium" if tic in medium_tics else "low" for tic in cands["tic_id"].unique()}
    # overtriggered if n_events >= 5
    counts = cands.groupby("tic_id").size()
    for tic, n in counts.items():
        if n >= 5:
            priority_map[tic] = "overtriggered_review"
    for tic in cands["tic_id"].unique():
        subset = cands[cands["tic_id"] == tic].head(3)
        for _, row in subset.iterrows():
            r = row.to_dict()
            r["recommended_review_priority"] = priority_map[tic]
            rows.append(r)
    return pd.DataFrame(rows)


def _make_overtriggered_df() -> pd.DataFrame:
    """Build a synthetic overtriggered-star table."""
    return pd.DataFrame({
        "tic_id": [1002],
        "sample_role": ["control"],
        "target_name": ["Test Star B"],
        "n_events": [7],
    })


def _make_lc(tic_id=9001, n=200, seed=42) -> pd.DataFrame:
    """Build a synthetic light curve DataFrame."""
    rng = np.random.default_rng(seed)
    t = np.linspace(1000.0, 1020.0, n)
    flux = 1.0 + rng.normal(0, 0.0005, n)
    return pd.DataFrame({
        "time_btjd": t,
        "flux": flux,
        "flux_err": 0.001,
        "quality": 0,
        "tic_id": tic_id,
        "product_label": f"TIC {tic_id}",
    })


def _make_star_summary() -> pd.DataFrame:
    """Build a synthetic star-level summary for plotting tests."""
    return pd.DataFrame({
        "tic_id": [1001, 1002, 2001],
        "target_name": ["Test Star A", "Test Star B", "Test Star C"],
        "sample_role": ["target", "control", "control"],
        "n_events": [3, 7, 2],
        "n_pass_automated_vetting": [0, 1, 0],
        "n_external_flags": [0, 0, 0],
        "max_final_candidate_score": [0.55, 0.90, 0.35],
        "max_local_snr": [4.5, 26.0, 3.5],
        "median_local_snr": [4.2, 25.0, 3.5],
        "max_depth_ppm": [300, 800, 200],
        "min_event_time_btjd": [2000.0, 3000.0, 4000.0],
        "max_event_time_btjd": [2020.0, 3030.0, 4010.0],
        "has_known_variable_match": [False, False, False],
        "has_tess_eb_match": [False, False, False],
        "recommended_review_priority": ["low", "overtriggered_review", "low"],
        "consolidation_version": ["phase5e_v1"] * 3,
    })


# ---------------------------------------------------------------------------
# TestBuildInspectionTargetList
# ---------------------------------------------------------------------------

class TestBuildInspectionTargetList:
    def test_empty_returns_empty(self):
        result = build_inspection_target_list(
            pd.DataFrame(),
            pd.DataFrame(),
            pd.DataFrame(),
        )
        assert result.empty

    def test_medium_priority_included(self):
        cand = _make_candidates()
        pri = _make_priority_df(medium_tics=[1001])
        ot = _make_overtriggered_df()
        result = build_inspection_target_list(cand, pri, ot)
        tic_1001 = result[result["tic_id"] == 1001]
        assert not tic_1001.empty, "TIC 1001 (medium) must be in inspection list"
        assert tic_1001["inspection_reason"].str.contains("medium_priority").any()

    def test_pass_events_included(self):
        cand = _make_candidates()
        pri = _make_priority_df()
        ot = _make_overtriggered_df()
        result = build_inspection_target_list(cand, pri, ot)
        pass_events = result[result["automated_vetting_status"] == "pass"]
        assert not pass_events.empty, "Pass events must be in inspection list"
        assert pass_events["inspection_reason"].str.contains("pass_vetting").all()

    def test_overtriggered_top5_included(self):
        cand = _make_candidates()
        pri = _make_priority_df()
        ot = _make_overtriggered_df()
        result = build_inspection_target_list(cand, pri, ot)
        ot_events = result[result["inspection_reason"].str.contains("overtriggered_top5")]
        assert not ot_events.empty, "Overtriggered TIC events must be included"
        assert (ot_events["tic_id"] == 1002).all()

    def test_target_top_event_included(self):
        cand = _make_candidates()
        pri = _make_priority_df()
        ot = _make_overtriggered_df()
        result = build_inspection_target_list(cand, pri, ot)
        target_events = result[result["sample_role"] == "target"]
        assert not target_events.empty, "Target TIC must have at least one event"
        assert target_events["inspection_reason"].str.contains("target_top_event").any()

    def test_max_events_per_star_respected(self):
        cand = _make_candidates()
        pri = _make_priority_df()
        ot = _make_overtriggered_df()
        for max_ev in [1, 2, 3]:
            result = build_inspection_target_list(cand, pri, ot, max_events_per_star=max_ev)
            # For the overtriggered TIC, count events with overtriggered_top5 reason
            ot_subset = result[result["inspection_reason"].str.contains("overtriggered_top5")]
            ot_counts = ot_subset.groupby("tic_id").size()
            if not ot_counts.empty:
                assert ot_counts.max() <= max_ev, (
                    f"max_events_per_star={max_ev} violated: got {ot_counts.max()}"
                )

    def test_deduplicates_events(self):
        # When pass events are also on an overtriggered TIC, no duplicates
        cand = _make_candidates()
        pri = _make_priority_df()
        ot = _make_overtriggered_df()
        result = build_inspection_target_list(cand, pri, ot)
        # Each (tic_id, event_time_btjd) pair should be unique
        if "event_time_btjd" in result.columns:
            dupes = result.duplicated(subset=["tic_id", "event_time_btjd"])
            assert not dupes.any(), "Duplicate events found in inspection list"

    def test_inspection_reason_combined(self):
        # Pass event on an overtriggered TIC should carry both reasons
        cand = _make_candidates()
        pri = _make_priority_df()
        ot = _make_overtriggered_df()
        result = build_inspection_target_list(cand, pri, ot)
        pass_events = result[result["automated_vetting_status"] == "pass"]
        # TIC 1002 is overtriggered, and has a pass event → both reasons
        if not pass_events.empty:
            reasons = pass_events.iloc[0]["inspection_reason"]
            assert "pass_vetting" in reasons
            assert "overtriggered_top5" in reasons

    def test_pass_events_sort_first(self):
        cand = _make_candidates()
        pri = _make_priority_df()
        ot = _make_overtriggered_df()
        result = build_inspection_target_list(cand, pri, ot)
        if len(result) >= 2:
            first_reason = result.iloc[0]["inspection_reason"]
            assert "pass_vetting" in first_reason or "medium_priority" in first_reason

    def test_inspection_reason_column_present(self):
        cand = _make_candidates()
        pri = _make_priority_df()
        ot = _make_overtriggered_df()
        result = build_inspection_target_list(cand, pri, ot)
        assert "inspection_reason" in result.columns

    def test_empty_overtriggered_still_runs(self):
        cand = _make_candidates()
        pri = _make_priority_df()
        result = build_inspection_target_list(cand, pri, pd.DataFrame())
        assert isinstance(result, pd.DataFrame)
        assert not result.empty

    def test_empty_priority_still_runs(self):
        cand = _make_candidates()
        ot = _make_overtriggered_df()
        result = build_inspection_target_list(cand, pd.DataFrame(), ot)
        assert isinstance(result, pd.DataFrame)

    def test_medium_tic_not_missed_when_not_in_priority_df(self):
        # If priority_df has no recommended_review_priority, target events still selected
        cand = _make_candidates()
        result = build_inspection_target_list(cand, pd.DataFrame(), pd.DataFrame())
        # At minimum, target_top_event should be included for TIC 1001
        assert (result["tic_id"] == 1001).any()


# ---------------------------------------------------------------------------
# TestLoadCachedLightcurve
# ---------------------------------------------------------------------------

class TestLoadCachedLightcurve:
    def test_missing_file_returns_none(self, tmp_path):
        result = load_cached_lightcurve_for_tic(99999999, cache_dir=tmp_path)
        assert result is None

    def test_parquet_loaded_correctly(self, tmp_path):
        lc = _make_lc(tic_id=1234)
        path = tmp_path / "tic_1234.parquet"
        lc.to_parquet(path)
        result = load_cached_lightcurve_for_tic(1234, cache_dir=tmp_path)
        assert result is not None
        assert "time_btjd" in result.columns
        assert "flux" in result.columns
        assert len(result) == len(lc)

    def test_corrupt_file_returns_none(self, tmp_path):
        bad_path = tmp_path / "tic_42.parquet"
        bad_path.write_bytes(b"this is not a parquet file")
        result = load_cached_lightcurve_for_tic(42, cache_dir=tmp_path)
        assert result is None


# ---------------------------------------------------------------------------
# TestExtractEventWindow
# ---------------------------------------------------------------------------

class TestExtractEventWindow:
    def test_basic_window(self):
        lc = _make_lc(n=100)
        event_t = float(lc["time_btjd"].iloc[50])
        result = extract_event_window(lc, event_t, window_days=1.0)
        assert not result.empty
        assert result["time_btjd"].min() >= event_t - 0.5
        assert result["time_btjd"].max() <= event_t + 0.5

    def test_empty_df_returns_empty(self):
        result = extract_event_window(pd.DataFrame(), 2000.0, window_days=1.0)
        assert result.empty

    def test_no_points_in_window_returns_empty(self):
        lc = _make_lc(n=50)  # time range 1000–1020
        result = extract_event_window(lc, 5000.0, window_days=1.0)
        assert result.empty

    def test_window_boundary_inclusive(self):
        # Points exactly at ±half_window should be included
        t = np.array([999.5, 1000.0, 1000.5])
        lc = pd.DataFrame({"time_btjd": t, "flux": np.ones(3)})
        result = extract_event_window(lc, 1000.0, window_days=1.0)
        assert len(result) == 3

    def test_no_time_column_returns_empty(self):
        lc = pd.DataFrame({"flux": [1.0, 2.0]})
        result = extract_event_window(lc, 1000.0)
        assert result.empty

    def test_narrow_window(self):
        lc = _make_lc(n=200)
        event_t = float(lc["time_btjd"].iloc[100])
        wide = extract_event_window(lc, event_t, window_days=5.0)
        narrow = extract_event_window(lc, event_t, window_days=0.1)
        assert len(narrow) <= len(wide)


# ---------------------------------------------------------------------------
# TestCreateDispositionTemplate
# ---------------------------------------------------------------------------

class TestCreateDispositionTemplate:
    def _make_inspection(self) -> pd.DataFrame:
        cand = _make_candidates()
        pri = _make_priority_df()
        ot = _make_overtriggered_df()
        return build_inspection_target_list(cand, pri, ot)

    def test_empty_returns_correct_columns(self):
        result = create_disposition_template(pd.DataFrame())
        for col in DISPOSITION_COLUMNS:
            assert col in result.columns, f"Missing column {col}"
        assert len(result) == 0

    def test_manual_fields_empty(self):
        insp = self._make_inspection()
        result = create_disposition_template(insp)
        manual_cols = [
            "manual_label", "reviewer_name", "review_date",
            "visual_event_quality", "likely_artifact_reason",
            "notes", "followup_priority",
        ]
        for col in manual_cols:
            assert col in result.columns
            assert (result[col] == "").all(), f"Column {col} should be empty string"

    def test_has_all_disposition_columns(self):
        insp = self._make_inspection()
        result = create_disposition_template(insp)
        for col in DISPOSITION_COLUMNS:
            assert col in result.columns, f"Disposition column {col} missing"

    def test_source_columns_preserved(self):
        insp = self._make_inspection()
        result = create_disposition_template(insp)
        assert (result["tic_id"] == insp["tic_id"]).all()
        if "local_snr" in insp.columns:
            assert result["local_snr"].notna().any() or insp["local_snr"].notna().any()

    def test_row_count_matches_inspection(self):
        insp = self._make_inspection()
        result = create_disposition_template(insp)
        assert len(result) == len(insp)

    def test_manual_label_allowed_values_documented(self):
        assert len(MANUAL_LABEL_ALLOWED) >= 7
        assert "keep_candidate" in MANUAL_LABEL_ALLOWED
        assert "unsure" in MANUAL_LABEL_ALLOWED
        assert "likely_systematic" in MANUAL_LABEL_ALLOWED


# ---------------------------------------------------------------------------
# TestEventInspectionPlot (no-lc and with-lc variants)
# ---------------------------------------------------------------------------

class TestEventInspectionPlot:
    def _make_event_row(self, include_flags=True) -> pd.Series:
        d = {
            "tic_id": 9001,
            "sample_role": "target",
            "target_name": "Test Star",
            "event_time_btjd": 1010.5,
            "local_snr": 8.5,
            "final_candidate_score": 0.75,
            "depth_ppm": 500,
            "duration_hours": 2.0,
            "automated_vetting_status": "flagged",
            "external_false_positive_flag": "no_external_match",
            "inspection_reason": "target_top_event",
            "recommended_review_priority": "low",
        }
        if include_flags:
            d.update({
                "flag_low_snr": False,
                "flag_edge_event": False,
                "flag_single_point_like": False,
                "flag_likely_flare_shape": False,
                "flag_low_delta_chi2": True,
                "flag_poor_asymmetry_fit": False,
            })
        return pd.Series(d)

    def test_no_lc_creates_figure(self, tmp_path):
        import matplotlib.pyplot as plt
        row = self._make_event_row()
        out = tmp_path / "event_no_lc.png"
        fig = create_event_inspection_plot(row, lc_df=None, output_path=out)
        plt.close(fig)
        assert out.exists()
        assert out.stat().st_size > 0

    def test_with_lc_creates_figure(self, tmp_path):
        import matplotlib.pyplot as plt
        row = self._make_event_row()
        lc = _make_lc(n=200)
        out = tmp_path / "event_with_lc.png"
        fig = create_event_inspection_plot(row, lc_df=lc, window_days=1.0, output_path=out)
        plt.close(fig)
        assert out.exists()
        assert out.stat().st_size > 0

    def test_no_output_path_returns_figure(self):
        import matplotlib.pyplot as plt
        row = self._make_event_row()
        fig = create_event_inspection_plot(row, lc_df=None)
        assert fig is not None
        plt.close(fig)

    def test_empty_window_does_not_crash(self, tmp_path):
        import matplotlib.pyplot as plt
        row = self._make_event_row()
        lc = _make_lc(n=200)  # times 1000–1020
        # event time outside LC range
        row = row.copy()
        row["event_time_btjd"] = 9999.0
        out = tmp_path / "event_outside_range.png"
        fig = create_event_inspection_plot(row, lc_df=lc, output_path=out)
        plt.close(fig)
        assert out.exists()


# ---------------------------------------------------------------------------
# TestCreateStarEventGallery
# ---------------------------------------------------------------------------

class TestCreateStarEventGallery:
    def _make_events_for_tic(self, tic_id=9001, n=3) -> pd.DataFrame:
        cand = _make_candidates()
        pri = _make_priority_df()
        ot = _make_overtriggered_df()
        insp = build_inspection_target_list(cand, pri, ot)
        subset = insp[insp["tic_id"] == tic_id]
        if subset.empty:
            # Fallback: build minimal events manually
            rows = []
            for i in range(n):
                rows.append({
                    "tic_id": tic_id,
                    "sample_role": "target",
                    "target_name": f"TIC {tic_id}",
                    "event_time_btjd": 1010.0 + i * 5.0,
                    "local_snr": 5.0,
                    "final_candidate_score": 0.6,
                    "automated_vetting_status": "flagged",
                    "external_false_positive_flag": "no_external_match",
                    "inspection_reason": "target_top_event",
                    "recommended_review_priority": "low",
                })
            return pd.DataFrame(rows)
        return subset.head(n)

    def test_creates_output_dir(self, tmp_path):
        events = self._make_events_for_tic(1001, n=1)
        create_star_event_gallery(1001, events, lc_df=None, output_dir=tmp_path)
        tic_dir = tmp_path / "tic_1001"
        assert tic_dir.exists()

    def test_creates_events_summary_csv(self, tmp_path):
        events = self._make_events_for_tic(1001, n=2)
        create_star_event_gallery(1001, events, lc_df=None, output_dir=tmp_path)
        csv = tmp_path / "tic_1001" / "events_summary.csv"
        assert csv.exists()
        loaded = pd.read_csv(csv)
        assert len(loaded) == len(events)

    def test_creates_metadata_json(self, tmp_path):
        events = self._make_events_for_tic(1001, n=2)
        create_star_event_gallery(1001, events, lc_df=None, output_dir=tmp_path)
        json_path = tmp_path / "tic_1001" / "metadata.json"
        assert json_path.exists()
        meta = json.loads(json_path.read_text())
        assert meta["tic_id"] == 1001
        assert "gallery_version" in meta
        assert meta["gallery_version"] == INSPECTION_VERSION
        assert meta["has_cached_lightcurve"] is False

    def test_event_plots_created(self, tmp_path):
        events = self._make_events_for_tic(1001, n=2)
        created = create_star_event_gallery(1001, events, lc_df=None, output_dir=tmp_path)
        png_files = [p for p in created if str(p).endswith(".png")]
        assert len(png_files) == len(events)

    def test_full_lc_plot_created_when_lc_available(self, tmp_path):
        events = self._make_events_for_tic(1001, n=2)
        lc = _make_lc(tic_id=1001)
        created = create_star_event_gallery(1001, events, lc_df=lc, output_dir=tmp_path)
        png_files = [p for p in created if str(p).endswith(".png")]
        # Should have: 1 full-LC plot + n event plots
        assert len(png_files) == len(events) + 1
        full_lc = tmp_path / "tic_1001" / "tic_1001_full_lc_with_events.png"
        assert full_lc.exists()

    def test_metadata_has_cached_lc_true_when_lc_provided(self, tmp_path):
        events = self._make_events_for_tic(1001, n=1)
        lc = _make_lc(tic_id=1001)
        create_star_event_gallery(1001, events, lc_df=lc, output_dir=tmp_path)
        meta = json.loads((tmp_path / "tic_1001" / "metadata.json").read_text())
        assert meta["has_cached_lightcurve"] is True

    def test_returns_list_of_paths(self, tmp_path):
        events = self._make_events_for_tic(1001, n=1)
        created = create_star_event_gallery(1001, events, lc_df=None, output_dir=tmp_path)
        assert isinstance(created, list)
        assert all(isinstance(p, Path) for p in created)


# ---------------------------------------------------------------------------
# TestPlotManualReviewPriorityOverview
# ---------------------------------------------------------------------------

class TestPlotManualReviewPriorityOverview:
    def test_creates_file(self, tmp_path):
        import matplotlib.pyplot as plt
        ss = _make_star_summary()
        out = tmp_path / "overview.png"
        fig = plot_manual_review_priority_overview(ss, output_path=out)
        plt.close(fig)
        assert out.exists()
        assert out.stat().st_size > 0

    def test_empty_df_does_not_crash(self, tmp_path):
        import matplotlib.pyplot as plt
        out = tmp_path / "overview_empty.png"
        fig = plot_manual_review_priority_overview(pd.DataFrame(), output_path=out)
        plt.close(fig)
        assert out.exists()

    def test_no_output_path_returns_figure(self):
        import matplotlib.pyplot as plt
        ss = _make_star_summary()
        fig = plot_manual_review_priority_overview(ss)
        assert fig is not None
        plt.close(fig)
