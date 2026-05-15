import importlib.util
from pathlib import Path

import pandas as pd


def _load_verify_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "verify_catalogs.py"
    spec = importlib.util.spec_from_file_location("verify_catalogs", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_verification_report_generation():
    module = _load_verify_module()
    df = pd.DataFrame(
        {
            "source_catalog": ["A", "A", "B"],
            "ra_deg": [1.0, None, 3.0],
            "dec_deg": [1.0, 2.0, 3.0],
            "has_tess_lightcurve": [True, False, True],
            "tic_query_status": ["matched", "not_attempted", "failed"],
            "gaia_query_status": ["matched", "not_found", "failed"],
            "tic_id": [123, None, "not_attempted_placeholder"],
            "gaia_dr3_source_id": [456, None, None],
            "tmag": [8.0, None, None],
            "bp_rp": [0.5, None, None],
            "parallax": [20.0, None, None],
        }
    )

    report = module.build_verification_report(df)
    metrics = dict(zip(report["metric"], report["value"]))

    assert metrics["n_rows"] == 3
    assert metrics["valid_ra_dec_count"] == 2
    assert metrics["tess_available_count"] == 2
    assert metrics["tic_matched_count"] == 1
    assert metrics["gaia_matched_count"] == 1
    assert metrics["placeholder_scientific_value_count"] == 1


def test_matched_pairs_report_generation():
    module = _load_verify_module()
    df = pd.DataFrame(
        {
            "target_tic_id": [1, 2],
            "control_tic_id": [10, 20],
            "tmag_target": [8.0, 9.0],
            "tmag_control": [8.2, 8.7],
            "bp_rp_target": [0.5, 0.8],
            "bp_rp_control": [0.55, 0.7],
            "parallax_target": [20.0, 10.0],
            "parallax_control": [18.0, 12.0],
            "match_quality_score": [0.5, 0.8],
        }
    )

    targets = pd.DataFrame({"has_tess_lightcurve": [True, True, True]})
    report = module.build_matched_pairs_report(df, targets)
    metrics = dict(zip(report["metric"], report["value"]))

    assert metrics["n_pairs"] == 2
    assert metrics["n_unmatched_targets"] == 1
    assert abs(metrics["tmag_diff_mean"] - 0.25) < 1e-9
    assert abs(metrics["bp_rp_diff_mean"] - 0.075) < 1e-9
    assert abs(metrics["parallax_diff_mean"] - 2.0) < 1e-9
