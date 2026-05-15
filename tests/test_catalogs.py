import pandas as pd
import sys
import types

from astrohunter.catalogs import (
    build_clean_target_table,
    build_target_sample_from_local_cotten_song,
    crossmatch_targets_with_gaia,
    crossmatch_targets_with_tic,
    enrich_targets_with_basic_gaia_like_columns,
    enrich_targets_with_tess_availability,
    filter_targets_for_dev_scan,
    normalize_catalog_columns,
    normalize_control_pool_columns,
    save_catalog,
)


def test_normalize_catalog_columns_decimal_coordinates():
    raw = pd.DataFrame(
        {
            "Name": ["HD 1", "HD 2"],
            "RAJ2000": [10.0, 20.0],
            "DEJ2000": [-5.0, 15.0],
            "Extra": ["a", "b"],
        }
    )

    normalized = normalize_catalog_columns(raw, "Cotten & Song 2016")

    assert normalized["target_name"].tolist() == ["HD 1", "HD 2"]
    assert normalized["ra_deg"].tolist() == [10.0, 20.0]
    assert normalized["dec_deg"].tolist() == [-5.0, 15.0]
    assert normalized["source_catalog"].iloc[0] == "Cotten & Song 2016"
    assert normalized["crossmatch_status"].iloc[0] == "not_attempted"
    assert "Extra" in normalized.columns


def test_normalize_catalog_columns_sexagesimal_coordinates():
    raw = pd.DataFrame(
        {
            "Star": ["Example"],
            "RAh": [1],
            "RAm": [30],
            "RAs": [0],
            "DE-": ["-"],
            "DEd": [10],
            "DEm": [30],
            "DEs": [0],
        }
    )

    normalized = normalize_catalog_columns(raw, "Chen et al. 2014")

    assert abs(normalized.loc[0, "ra_deg"] - 22.5) < 1e-9
    assert abs(normalized.loc[0, "dec_deg"] + 10.5) < 1e-9


def test_normalize_catalog_columns_vizier_sexagesimal_strings():
    raw = pd.DataFrame(
        {
            "Name": ["10 Tau"],
            "RAJ2000": ["03 36 52.38"],
            "DEJ2000": ["+00 24 05.9"],
        }
    )

    normalized = normalize_catalog_columns(raw, "Cotten & Song 2016")

    assert abs(normalized.loc[0, "ra_deg"] - 54.21825) < 1e-5
    assert abs(normalized.loc[0, "dec_deg"] - 0.4016389) < 1e-5


def test_mcdonald_marked_secondary_and_cautionary():
    raw = pd.DataFrame({"Name": ["IR source"], "RAdeg": [1.0], "DEdeg": [2.0]})

    normalized = normalize_catalog_columns(raw, "McDonald et al. 2017")

    assert bool(normalized.loc[0, "is_secondary_source"]) is True
    assert "cautionary" in normalized.loc[0, "catalog_caution"]


def test_save_catalog_roundtrip(tmp_path):
    df = pd.DataFrame({"target_name": ["HD 1"], "ra_deg": [10.0]})
    path = save_catalog(df, tmp_path / "nested" / "catalog.csv")

    loaded = pd.read_csv(path)

    assert path.exists()
    assert loaded.equals(df)


def test_tess_enrichment_can_be_mocked(monkeypatch):
    class DummyTable:
        colnames = ["author", "mission", "year", "sequence_number"]

        def __getitem__(self, key):
            values = {
                "author": ["SPOC"],
                "mission": ["TESS"],
                "year": [2020],
                "sequence_number": [6],
            }
            return values[key]

    class DummySearchResult:
        table = DummyTable()

        def __len__(self):
            return 2

    dummy_lk = types.SimpleNamespace(
        search_lightcurve=lambda query, mission=None: DummySearchResult()
    )
    monkeypatch.setitem(sys.modules, "lightkurve", dummy_lk)
    targets = pd.DataFrame({"target_name": ["Beta Pic"]})

    enriched = enrich_targets_with_tess_availability(targets, max_targets=1)

    assert enriched.loc[0, "n_tess_products"] == 2
    assert bool(enriched.loc[0, "has_tess_lightcurve"]) is True
    assert enriched.loc[0, "first_author"] == "SPOC"
    assert enriched.loc[0, "first_sector"] == 6


def test_gaia_like_placeholders_do_not_fabricate_values():
    targets = pd.DataFrame({"target_name": ["x"], "T*": [6000]})

    enriched = enrich_targets_with_basic_gaia_like_columns(targets)

    assert "gaia_dr3_source_id" in enriched.columns
    assert pd.isna(enriched.loc[0, "gaia_dr3_source_id"])
    assert "teff" not in enriched.columns
    assert enriched.loc[0, "gaia_query_status"] == "not_attempted_placeholder"


def test_filter_targets_for_dev_scan():
    targets = pd.DataFrame(
        {
            "ra_deg": [10.0, None, 30.0],
            "dec_deg": [5.0, 6.0, 7.0],
            "has_tess_lightcurve": [True, True, False],
        }
    )

    filtered = filter_targets_for_dev_scan(targets)

    assert len(filtered) == 1
    assert filtered.loc[0, "ra_deg"] == 10.0


def test_normalize_control_pool_columns_aliases():
    raw = pd.DataFrame(
        {
            "TIC": [123],
            "RA": [10.0],
            "DEC": [-5.0],
            "Tmag": [8.2],
            "BP_RP": [0.5],
            "Plx": [20.0],
            "has_tess": [True],
            "disk_flag": [False],
        }
    )

    normalized = normalize_control_pool_columns(raw)

    assert normalized.loc[0, "tic_id"] == 123
    assert normalized.loc[0, "ra_deg"] == 10.0
    assert normalized.loc[0, "bp_rp"] == 0.5
    assert bool(normalized.loc[0, "ir_excess_flag"]) is False


def test_build_clean_target_table_keeps_only_research_columns():
    raw = pd.DataFrame(
        {
            "target_name": ["x"],
            "source_catalog": ["Cotten & Song 2016"],
            "ra_deg": [10.0],
            "dec_deg": [-5.0],
            "SpT": ["A0V"],
            "T*": [9000],
            "Dist": [30.0],
            "Td1": [100.0],
            "Rd1": [12.0],
            "Ref": ["Example"],
            "sample_role": ["disk_or_ir_excess_target"],
            "has_tess_lightcurve": [True],
            "n_tess_products": [4],
            "first_author": ["SPOC"],
            "first_mission": ["TESS Sector 1"],
            "first_year": [2018],
            "first_sector": [1],
            "tess_query_status": ["ok"],
            "tic_id": ["not_attempted_placeholder"],
            "gaia_dr3_source_id": ["not_attempted_placeholder"],
            "tmag": ["not_attempted_placeholder"],
            "bp_rp": ["not_attempted_placeholder"],
            "parallax": ["not_attempted_placeholder"],
            "gaia_query_status": ["not_attempted_placeholder"],
            "tic_query_status": ["not_attempted"],
            "raw_unused_column": ["drop me"],
        }
    )

    clean = build_clean_target_table(raw)

    assert "raw_unused_column" not in clean.columns
    assert clean.loc[0, "sp_type"] == "A0V"
    assert clean.loc[0, "teff_catalog"] == 9000
    assert pd.isna(clean.loc[0, "tic_id"])
    assert pd.isna(clean.loc[0, "gaia_dr3_source_id"])
    assert clean.loc[0, "gaia_query_status"] == "not_attempted"


def test_build_clean_target_table_handles_missing_columns():
    clean = build_clean_target_table(pd.DataFrame({"target_name": ["x"]}))

    assert len(clean) == 1
    assert list(clean.columns)[0] == "target_name"
    assert pd.isna(clean.loc[0, "ra_deg"])
    assert clean.loc[0, "tic_query_status"] == "not_attempted"


def test_tic_crossmatch_failure_does_not_crash(monkeypatch):
    class FailingCatalogs:
        @staticmethod
        def query_region(*args, **kwargs):
            raise RuntimeError("network down")

    monkeypatch.setitem(
        sys.modules,
        "astroquery.mast",
        types.SimpleNamespace(Catalogs=FailingCatalogs),
    )
    targets = pd.DataFrame({"ra_deg": [10.0], "dec_deg": [-5.0]})

    result = crossmatch_targets_with_tic(targets, max_targets=1)

    assert result.loc[0, "tic_query_status"] == "failed"
    assert pd.isna(result.loc[0, "tic_id"])


def test_gaia_crossmatch_failure_does_not_crash(monkeypatch):
    class FailingGaia:
        @staticmethod
        def cone_search_async(*args, **kwargs):
            raise RuntimeError("network down")

    monkeypatch.setitem(
        sys.modules,
        "astroquery.gaia",
        types.SimpleNamespace(Gaia=FailingGaia),
    )
    targets = pd.DataFrame({"ra_deg": [10.0], "dec_deg": [-5.0]})

    result = crossmatch_targets_with_gaia(targets, max_targets=1)

    assert result.loc[0, "gaia_query_status"] == "failed"
    assert pd.isna(result.loc[0, "gaia_dr3_source_id"])


def test_build_target_sample_from_local_cotten_song_ascii_fallback(tmp_path):
    csv_path = tmp_path / "bad.csv"
    ascii_path = tmp_path / "table3.dat.txt"
    csv_path.write_text("<HTML>not a data csv</HTML>", encoding="utf-8")
    ascii_path.write_text(
        "\n".join(
            [
                "#Table: test",
                "------------------------|-|-----------------------|--------|-----|-----|----|------|----|----------|---------|---------|-|-|---|-|------------------------------",
                "HD 105                  | |00 05 52.64 -41 45 11.7|G0V     | 6070|1.010| 390|  0.50|  50|  34.66000|   4.530 |  39.380 | |3| 22|Y|Zuckerman et al. 2004",
            ]
        ),
        encoding="utf-8",
    )

    sample = build_target_sample_from_local_cotten_song(
        csv_path=csv_path,
        ascii_path=ascii_path,
        max_targets=1,
    )

    assert len(sample) == 1
    assert sample.loc[0, "target_name"] == "HD 105"
    assert abs(sample.loc[0, "ra_deg"] - 1.4693333333333334) < 1e-9
    assert sample.loc[0, "sp_type"] == "G0V"
