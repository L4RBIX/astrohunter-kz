import importlib.util
import sys
import types
from pathlib import Path

import pandas as pd


def _load_script(name):
    script_path = Path(__file__).resolve().parents[1] / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_enrich_tess_mocked_lightkurve(monkeypatch):
    module = _load_script("enrich_tess.py")

    class DummyTable:
        colnames = ["sequence_number", "mission"]

        def __getitem__(self, key):
            return {"sequence_number": [7], "mission": ["TESS Sector 07"]}[key]

    class DummySearchResult:
        table = DummyTable()

        def __len__(self):
            return 3

    monkeypatch.setitem(
        sys.modules,
        "lightkurve",
        types.SimpleNamespace(search_lightcurve=lambda *args, **kwargs: DummySearchResult()),
    )
    df = pd.DataFrame({"tic_id": [123]})

    enriched = module.enrich_tess(df, max_targets=1)

    assert bool(enriched.loc[0, "has_tess_lightcurve"]) is True
    assert enriched.loc[0, "n_tess_products"] == 3
    assert enriched.loc[0, "first_sector"] == 7
    assert enriched.loc[0, "tess_query_status"] == "found"


def test_build_matched_pairs_synthetic():
    module = _load_script("build_controls.py")
    targets = pd.DataFrame(
        {
            "tic_id": [1],
            "target_name": ["target"],
            "has_tess_lightcurve": [True],
            "tmag": [8.0],
            "bp_rp": [0.5],
            "parallax": [20.0],
            "teff_tic": [6000],
        }
    )
    pool = pd.DataFrame(
        {
            "tic_id": ["10"],
            "has_tess_lightcurve": [True],
            "tmag": [8.1],
            "bp_rp": [0.55],
            "parallax": [19.0],
            "teff": [6050],
        }
    )

    pairs, unmatched = module.build_matched_pairs(targets, pool)

    assert len(pairs) == 1
    assert unmatched == 0
    assert pairs.loc[0, "control_tic_id"] == "10"
