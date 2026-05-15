import pandas as pd
import sys
import types

from astrohunter.catalogs import crossmatch_targets_with_gaia, crossmatch_targets_with_tic
from astrohunter.crossmatch import (
    add_skycoord_columns,
    angular_separation_arcsec,
    build_approximate_matched_controls,
    crossmatch_by_coordinates,
    deduplicate_by_coordinates,
    deduplicate_by_skycoord,
    match_controls_to_targets,
    nearest_coordinate_matches,
    safe_column_lookup,
)


def test_angular_separation_arcsec_zero_for_same_position():
    sep = angular_separation_arcsec(10.0, -5.0, 10.0, -5.0)

    assert float(sep) == 0.0


def test_deduplicate_by_coordinates_removes_close_duplicate():
    df = pd.DataFrame(
        {
            "target_name": ["a", "a duplicate", "b"],
            "ra_deg": [10.0, 10.0002, 20.0],
            "dec_deg": [5.0, 5.0002, -5.0],
        }
    )

    deduped = deduplicate_by_coordinates(df, radius_arcsec=2.0)

    assert len(deduped) == 2
    assert deduped["target_name"].tolist() == ["a", "b"]


def test_add_skycoord_columns_and_safe_lookup():
    df = pd.DataFrame({"RA": ["10.0"], "Dec": ["-5.0"]})
    ra_col = safe_column_lookup(df, ["ra_deg", "RA"])
    dec_col = safe_column_lookup(df, ["dec_deg", "Dec"])

    with_coords = add_skycoord_columns(df, ra_col, dec_col)

    assert with_coords.loc[0, "ra_deg"] == 10.0
    assert with_coords.loc[0, "dec_deg"] == -5.0
    assert bool(with_coords.loc[0, "has_skycoord"]) is True


def test_crossmatch_by_coordinates_alias_and_skycoord_dedup():
    left = pd.DataFrame({"ra_deg": [10.0], "dec_deg": [5.0]})
    right = pd.DataFrame({"ra_deg": [10.0001], "dec_deg": [5.0001]})

    matches = crossmatch_by_coordinates(left, right, max_sep_arcsec=1.0)
    deduped = deduplicate_by_skycoord(
        pd.concat([left, right], ignore_index=True),
        max_sep_arcsec=1.0,
    )

    assert len(matches) == 1
    assert len(deduped) == 1


def test_nearest_coordinate_matches_within_radius():
    left = pd.DataFrame({"ra_deg": [10.0, 100.0], "dec_deg": [5.0, 0.0]})
    right = pd.DataFrame({"ra_deg": [10.0001, 50.0], "dec_deg": [5.0001, 0.0]})

    matches = nearest_coordinate_matches(left, right, radius_arcsec=1.0)

    assert len(matches) == 1
    assert matches.loc[0, "left_index"] == 0
    assert matches.loc[0, "right_index"] == 0


def test_build_approximate_matched_controls_requires_real_pool():
    targets = pd.DataFrame({"ra_deg": [10.0], "dec_deg": [5.0]})
    empty_pool = pd.DataFrame()

    controls, pairs = build_approximate_matched_controls(targets, empty_pool)

    assert controls.empty
    assert pairs.empty


def test_match_controls_to_targets_with_synthetic_metadata():
    targets = pd.DataFrame(
        {
            "target_name": ["target-a"],
            "tmag": [8.0],
            "bp_rp": [0.5],
            "parallax": [20.0],
            "has_tess_lightcurve": [True],
        }
    )
    pool = pd.DataFrame(
        {
            "target_name": ["control-good", "control-disk", "control-faint"],
            "tmag": [8.2, 8.1, 11.0],
            "bp_rp": [0.55, 0.52, 0.5],
            "parallax": [21.0, 20.5, 20.0],
            "has_tess_lightcurve": [True, True, True],
            "ir_excess_flag": [False, True, False],
        }
    )

    controls, pairs = match_controls_to_targets(targets, pool, control_ratio=2)

    assert len(controls) == 1
    assert controls.loc[0, "target_name"] == "control-good"
    assert len(pairs) == 1


def test_match_controls_missing_metadata_warns_without_crashing(capsys):
    targets = pd.DataFrame({"target_name": ["target-a"]})
    pool = pd.DataFrame(
        {
            "target_name": ["control-a"],
            "has_tess_lightcurve": [True],
            "ir_excess_flag": [False],
        }
    )

    controls, pairs = match_controls_to_targets(targets, pool)
    captured = capsys.readouterr()

    assert "Warning" in captured.out
    assert len(controls) == 1
    assert len(pairs) == 1


def test_tic_crossmatch_uses_nearest_mocked_match(monkeypatch):
    class DummyTicTable:
        def to_pandas(self):
            return pd.DataFrame(
                {
                    "ID": [111, 222],
                    "ra": [10.01, 10.0001],
                    "dec": [5.01, 5.0001],
                    "Tmag": [9.9, 8.8],
                    "Teff": [5000, 6100],
                }
            )

        def __len__(self):
            return 2

    class DummyCatalogs:
        @staticmethod
        def query_region(*args, **kwargs):
            return DummyTicTable()

    monkeypatch.setitem(
        sys.modules,
        "astroquery.mast",
        types.SimpleNamespace(Catalogs=DummyCatalogs),
    )
    targets = pd.DataFrame({"ra_deg": [10.0], "dec_deg": [5.0]})

    matched = crossmatch_targets_with_tic(targets, max_targets=1, radius_arcsec=5.0)

    assert matched.loc[0, "tic_query_status"] == "matched"
    assert matched.loc[0, "tic_id"] == 222
    assert matched.loc[0, "tmag"] == 8.8
    assert matched.loc[0, "teff_tic"] == 6100
    assert matched.loc[0, "tic_match_sep_arcsec"] > 0


def test_gaia_crossmatch_uses_nearest_mocked_match(monkeypatch):
    class DummyGaiaTable:
        def to_pandas(self):
            return pd.DataFrame(
                {
                    "source_id": [999, 888],
                    "ra": [10.01, 10.0001],
                    "dec": [5.01, 5.0001],
                    "bp_rp": [1.1, 0.7],
                    "parallax": [3.0, 20.0],
                }
            )

        def __len__(self):
            return 2

    class DummyJob:
        def get_results(self):
            return DummyGaiaTable()

    class DummyGaia:
        @staticmethod
        def cone_search_async(*args, **kwargs):
            return DummyJob()

    monkeypatch.setitem(
        sys.modules,
        "astroquery.gaia",
        types.SimpleNamespace(Gaia=DummyGaia),
    )
    targets = pd.DataFrame({"ra_deg": [10.0], "dec_deg": [5.0]})

    matched = crossmatch_targets_with_gaia(targets, max_targets=1, radius_arcsec=5.0)

    assert matched.loc[0, "gaia_query_status"] == "matched"
    assert matched.loc[0, "gaia_dr3_source_id"] == 888
    assert matched.loc[0, "bp_rp"] == 0.7
    assert matched.loc[0, "parallax"] == 20.0
    assert matched.loc[0, "gaia_match_sep_arcsec"] > 0
