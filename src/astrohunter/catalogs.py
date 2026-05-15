"""Catalog retrieval and normalization for Phase 2 development samples."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from astrohunter.crossmatch import (
    add_placeholder_crossmatch_columns,
    angular_separation_arcsec,
    deduplicate_by_coordinates,
    safe_column_lookup,
)


COTTEN_SONG_2016 = "J/ApJS/225/15"
CHEN_2014 = "J/ApJS/211/25"
MCDONALD_2017 = "J/MNRAS/471/770"


def _table_to_dataframe(table: Any) -> pd.DataFrame:
    """Convert an astropy table-like object to a pandas DataFrame."""
    try:
        return table.to_pandas()
    except Exception:
        return pd.DataFrame(np.asarray(table))


def query_vizier_catalog(catalog_id: str, row_limit: int | None = None) -> pd.DataFrame:
    """Query a VizieR catalog and return concatenated tables as a DataFrame.

    Remote failures return an empty DataFrame with a printed warning. This keeps
    Phase 2 reproducible in offline environments without fabricating fallback
    rows.
    """
    if row_limit is not None and row_limit < 1:
        raise ValueError("row_limit must be None or a positive integer")

    try:
        from astroquery.vizier import Vizier
    except ImportError:
        print("Warning: astroquery is not installed; VizieR query skipped.")
        return pd.DataFrame()

    limit = -1 if row_limit is None else int(row_limit)
    vizier = Vizier(columns=["**"], row_limit=limit, timeout=60)
    print(f"Querying VizieR catalog {catalog_id} with row_limit={row_limit}...")

    try:
        tables = vizier.get_catalogs(catalog_id)
    except Exception as exc:
        print(f"Warning: VizieR query failed for {catalog_id}: {exc}")
        return pd.DataFrame()

    frames: list[pd.DataFrame] = []
    for table_name in tables.keys():
        table = tables[table_name]
        frame = _table_to_dataframe(table)
        if frame.empty:
            continue
        frame["vizier_catalog_id"] = catalog_id
        frame["vizier_table"] = str(table_name)
        frames.append(frame)

    if not frames:
        print(f"Warning: VizieR returned no rows for {catalog_id}.")
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True, sort=False)


def load_cotten_song(row_limit: int | None = None) -> pd.DataFrame:
    """Load Cotten & Song 2016 IR-excess/debris-disk compilation."""
    return query_vizier_catalog(COTTEN_SONG_2016, row_limit=row_limit)


def load_chen_2014(row_limit: int | None = None) -> pd.DataFrame:
    """Load Chen et al. 2014 Spitzer IRS debris-disk catalog."""
    return query_vizier_catalog(CHEN_2014, row_limit=row_limit)


def load_mcdonald_2017(row_limit: int | None = None) -> pd.DataFrame:
    """Load McDonald et al. 2017 IR-excess catalog.

    This source is treated as secondary/cautionary because the catalog can
    include evolved-star and YSO contaminants.
    """
    return query_vizier_catalog(MCDONALD_2017, row_limit=row_limit)


def _find_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    lookup = {str(column).lower(): column for column in df.columns}
    for candidate in candidates:
        found = lookup.get(candidate.lower())
        if found is not None:
            return found
    return None


def _numeric_series(df: pd.DataFrame, column: str | None) -> pd.Series:
    if column is None:
        return pd.Series(np.nan, index=df.index, dtype=float)
    return pd.to_numeric(df[column], errors="coerce")


def _parse_sexagesimal(value: Any, is_ra: bool) -> float:
    if pd.isna(value):
        return np.nan
    text = str(value).strip()
    if not text:
        return np.nan

    for token in ["h", "m", "s", "d", ":", ","]:
        text = text.replace(token, " ")
    parts = [part for part in text.split() if part]
    if len(parts) < 3:
        return np.nan

    try:
        first = float(parts[0])
        second = float(parts[1])
        third = float(parts[2])
    except ValueError:
        return np.nan

    if is_ra:
        return 15.0 * (first + second / 60.0 + third / 3600.0)

    sign = -1.0 if str(parts[0]).startswith("-") else 1.0
    return sign * (abs(first) + second / 60.0 + third / 3600.0)


def _sexagesimal_string_series(
    df: pd.DataFrame,
    column: str | None,
    is_ra: bool,
) -> pd.Series:
    if column is None:
        return pd.Series(np.nan, index=df.index, dtype=float)
    return df[column].map(lambda value: _parse_sexagesimal(value, is_ra=is_ra))


def _sexagesimal_ra(df: pd.DataFrame) -> pd.Series:
    h_col = _find_column(df, ["RAh", "RAh2000", "RAh_ICRS"])
    m_col = _find_column(df, ["RAm", "RAm2000", "RAm_ICRS"])
    s_col = _find_column(df, ["RAs", "RAs2000", "RAs_ICRS"])
    if not all([h_col, m_col, s_col]):
        return pd.Series(np.nan, index=df.index, dtype=float)
    hours = _numeric_series(df, h_col)
    minutes = _numeric_series(df, m_col)
    seconds = _numeric_series(df, s_col)
    return 15.0 * (hours + minutes / 60.0 + seconds / 3600.0)


def _sexagesimal_dec(df: pd.DataFrame) -> pd.Series:
    sign_col = _find_column(df, ["DE-", "DEsign", "DE_Sign"])
    d_col = _find_column(df, ["DEd", "DEd2000", "DEd_ICRS"])
    m_col = _find_column(df, ["DEm", "DEm2000", "DEm_ICRS"])
    s_col = _find_column(df, ["DEs", "DEs2000", "DEs_ICRS"])
    if not all([d_col, m_col, s_col]):
        return pd.Series(np.nan, index=df.index, dtype=float)

    degrees = _numeric_series(df, d_col)
    minutes = _numeric_series(df, m_col)
    seconds = _numeric_series(df, s_col)
    abs_dec = degrees.abs() + minutes / 60.0 + seconds / 3600.0
    signs = np.sign(degrees).replace(0, 1)
    if sign_col is not None:
        raw_sign = df[sign_col].astype(str).str.strip()
        signs = np.where(raw_sign == "-", -1, 1)
    return abs_dec * signs


def _target_name(df: pd.DataFrame) -> pd.Series:
    name_col = _find_column(
        df,
        [
            "target_name",
            "name",
            "Name",
            "star",
            "Star",
            "HD",
            "HIP",
            "TIC",
            "ID",
            "Object",
            "2MASS",
            "_2MASS",
        ],
    )
    if name_col is None:
        return pd.Series(pd.NA, index=df.index, dtype="object")
    return df[name_col].astype(str).replace({"nan": pd.NA, "None": pd.NA})


def normalize_catalog_columns(df: pd.DataFrame, source_name: str) -> pd.DataFrame:
    """Add normalized Phase 2 columns while preserving source catalog columns."""
    if df is None or df.empty:
        return pd.DataFrame(
            columns=[
                "target_name",
                "ra_deg",
                "dec_deg",
                "source_catalog",
                "source_priority",
                "is_secondary_source",
                "catalog_caution",
            ]
        )

    work = df.copy()
    ra_col = _find_column(
        work,
        ["ra_deg", "RAdeg", "RAJ2000", "_RAJ2000", "RA_ICRS", "_RA.icrs", "RA"],
    )
    dec_col = _find_column(
        work,
        ["dec_deg", "DEdeg", "DEJ2000", "_DEJ2000", "DE_ICRS", "_DE.icrs", "DEC", "Dec"],
    )

    ra = _numeric_series(work, ra_col)
    dec = _numeric_series(work, dec_col)
    if ra.isna().all():
        ra = _sexagesimal_string_series(work, ra_col, is_ra=True)
    if dec.isna().all():
        dec = _sexagesimal_string_series(work, dec_col, is_ra=False)
    if ra.isna().all():
        ra = _sexagesimal_ra(work)
    if dec.isna().all():
        dec = _sexagesimal_dec(work)

    source_key = source_name.lower().replace(" ", "_")
    is_mcdonald = "mcdonald" in source_key
    priority = 3 if is_mcdonald else (1 if "cotten" in source_key else 2)

    target_names = _target_name(work)
    work["source_catalog"] = source_name
    work["target_name"] = target_names
    work["ra_deg"] = ra
    work["dec_deg"] = dec
    work["source_priority"] = priority
    work["is_secondary_source"] = bool(is_mcdonald)
    work["catalog_caution"] = (
        "secondary/cautionary IR-excess source; filter evolved-star and YSO contaminants"
        if is_mcdonald
        else ""
    )
    work["phase2_sample_status"] = "development_target"
    work = add_placeholder_crossmatch_columns(work)

    normalized_columns = [
        "source_catalog",
        "target_name",
        "ra_deg",
        "dec_deg",
        "source_priority",
        "is_secondary_source",
        "catalog_caution",
        "phase2_sample_status",
        "tic_id",
        "gaia_dr3_source_id",
        "simbad_main_id",
        "crossmatch_status",
    ]
    remaining_columns = [column for column in work.columns if column not in normalized_columns]
    return work[normalized_columns + remaining_columns]


def _load_phase2_sources(dev: bool, max_targets: int | None) -> list[pd.DataFrame]:
    row_limit = None
    if dev:
        requested = max_targets or 20
        row_limit = max(50, requested * 5)

    sources = [
        ("Cotten & Song 2016", load_cotten_song(row_limit=row_limit)),
        ("Chen et al. 2014", load_chen_2014(row_limit=row_limit)),
        ("McDonald et al. 2017", load_mcdonald_2017(row_limit=row_limit)),
    ]

    normalized: list[pd.DataFrame] = []
    for source_name, frame in sources:
        norm = normalize_catalog_columns(frame, source_name)
        if not norm.empty:
            normalized.append(norm)
        else:
            print(f"Warning: no usable rows loaded for {source_name}.")
    return normalized


def build_target_sample(dev: bool = True, max_targets: int = 20) -> pd.DataFrame:
    """Build a small real Phase 2 debris-disk / IR-excess development sample."""
    if max_targets < 1:
        raise ValueError("max_targets must be at least 1")

    normalized_sources = _load_phase2_sources(dev=dev, max_targets=max_targets)
    if not normalized_sources:
        print("Warning: no source catalogs loaded; target sample is empty.")
        return pd.DataFrame()

    combined = pd.concat(normalized_sources, ignore_index=True, sort=False)
    combined = combined.sort_values(
        ["source_priority", "source_catalog", "target_name"],
        na_position="last",
    ).reset_index(drop=True)

    if {"ra_deg", "dec_deg"}.issubset(combined.columns):
        combined = deduplicate_by_coordinates(combined, radius_arcsec=5.0)

    if dev:
        combined = combined.head(max_targets).reset_index(drop=True)

    combined["sample_role"] = "disk_or_ir_excess_target"
    combined["sample_is_preliminary"] = True
    return combined


def _target_query_string(row: pd.Series) -> str | None:
    tic_id = row.get("tic_id")
    if pd.notna(tic_id):
        text = str(tic_id).strip()
        if text and text.lower() != "nan":
            return text if text.upper().startswith("TIC") else f"TIC {text}"

    target_name = row.get("target_name")
    if pd.notna(target_name):
        text = str(target_name).strip()
        if text and text.lower() not in {"nan", "none", "<na>"}:
            return text
    return None


def _extract_first_value(search_result, candidates: list[str]):
    try:
        table = search_result.table
    except Exception:
        return pd.NA
    if table is None:
        return pd.NA
    try:
        if len(table) == 0:
            return pd.NA
    except TypeError:
        pass
    colnames = list(getattr(table, "colnames", []))
    lookup = {str(column).lower(): column for column in colnames}
    for candidate in candidates:
        column = lookup.get(candidate.lower())
        if column is None:
            continue
        try:
            value = table[column][0]
        except Exception:
            continue
        if hasattr(value, "item"):
            try:
                value = value.item()
            except Exception:
                pass
        return value
    return pd.NA


def enrich_targets_with_tess_availability(
    df: pd.DataFrame,
    max_targets: int | None = None,
) -> pd.DataFrame:
    """Search MAST metadata for TESS light-curve availability.

    This function performs search metadata queries only. It does not download
    light curves.
    """
    work = df.copy()
    for column in [
        "n_tess_products",
        "has_tess_lightcurve",
        "first_author",
        "first_mission",
        "first_year",
        "first_sector",
        "tess_query_status",
    ]:
        if column not in work.columns:
            work[column] = pd.NA

    if work.empty:
        return work

    try:
        import lightkurve as lk
    except ImportError:
        print("Warning: lightkurve is not installed; TESS enrichment skipped.")
        work["tess_query_status"] = "skipped_missing_lightkurve"
        work["n_tess_products"] = 0
        work["has_tess_lightcurve"] = False
        return work

    limit = len(work) if max_targets is None else min(max_targets, len(work))
    print(f"Enriching TESS availability for {limit} target rows...")
    for idx in work.index[:limit]:
        query = _target_query_string(work.loc[idx])
        if query is None:
            work.loc[idx, "n_tess_products"] = 0
            work.loc[idx, "has_tess_lightcurve"] = False
            work.loc[idx, "tess_query_status"] = "skipped_no_query_identifier"
            continue

        try:
            search_result = lk.search_lightcurve(query, mission="TESS")
        except Exception as exc:
            print(f"Warning: TESS metadata search failed for {query!r}: {exc}")
            work.loc[idx, "n_tess_products"] = 0
            work.loc[idx, "has_tess_lightcurve"] = False
            work.loc[idx, "tess_query_status"] = "query_failed"
            continue

        n_products = int(len(search_result))
        work.loc[idx, "n_tess_products"] = n_products
        work.loc[idx, "has_tess_lightcurve"] = n_products > 0
        work.loc[idx, "tess_query_status"] = "ok"
        if n_products > 0:
            work.loc[idx, "first_author"] = _extract_first_value(
                search_result,
                ["author", "Author"],
            )
            work.loc[idx, "first_mission"] = _extract_first_value(
                search_result,
                ["mission", "Mission", "obs_collection"],
            )
            work.loc[idx, "first_year"] = _extract_first_value(
                search_result,
                ["year", "Year"],
            )
            work.loc[idx, "first_sector"] = _extract_first_value(
                search_result,
                ["sequence_number", "sector", "Sector"],
            )

    if limit < len(work):
        untouched = work.index[limit:]
        work.loc[untouched, "tess_query_status"] = "not_queried_limit"
    return work


def enrich_targets_with_basic_gaia_like_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add safe Gaia/TIC-like metadata placeholders without fabricating values."""
    work = df.copy()
    column_aliases = {
        "gaia_dr3_source_id": ["gaia_dr3_source_id", "GaiaDR3", "Source", "Gaia"],
        "parallax": ["parallax", "Plx", "plx"],
        "bp_rp": ["bp_rp", "BP_RP", "BP-RP", "G_BP-G_RP"],
        "tmag": ["tmag", "Tmag", "TESSMAG"],
    }
    for output_column, candidates in column_aliases.items():
        source_column = safe_column_lookup(work, candidates)
        if source_column is not None:
            work[output_column] = work[source_column]
        elif output_column not in work.columns:
            work[output_column] = pd.NA

    if "gaia_query_status" not in work.columns:
        work["gaia_query_status"] = "not_attempted_placeholder"
    if "tic_query_status" not in work.columns:
        work["tic_query_status"] = "not_attempted"
    print(
        "Warning: Gaia/TIC remote crossmatch is not implemented in Phase 2B; "
        "placeholder columns were added without fabricated values."
    )
    return work


def _empty_scientific_value(value):
    if pd.isna(value):
        return pd.NA
    text = str(value).strip().lower()
    if text in {
        "",
        "nan",
        "none",
        "<na>",
        "not_attempted",
        "not_attempted_placeholder",
        "failed",
        "not_found",
    }:
        return pd.NA
    return value


def _coerce_status(value) -> str:
    if pd.isna(value):
        return "not_attempted"
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "<na>", "not_attempted_placeholder"}:
        return "not_attempted"
    if text in {"matched", "not_found", "failed", "not_attempted"}:
        return text
    return text


def _first_existing_series(df: pd.DataFrame, candidates: list[str]) -> pd.Series:
    for column in candidates:
        if column in df.columns:
            return df[column]
    return pd.Series(pd.NA, index=df.index)


def _first_numeric_series(df: pd.DataFrame, candidates: list[str]) -> pd.Series:
    for column in candidates:
        if column in df.columns:
            values = pd.to_numeric(df[column], errors="coerce")
            if values.notna().any():
                return values
    return pd.Series(np.nan, index=df.index, dtype=float)


def build_clean_target_table(df: pd.DataFrame) -> pd.DataFrame:
    """Create a compact research-facing target table with no fake values."""
    work = df.copy()
    clean = pd.DataFrame(index=work.index)
    clean["target_name"] = _first_existing_series(work, ["target_name", "Name", "Star"])
    clean["source_catalog"] = _first_existing_series(work, ["source_catalog"])
    clean["ra_deg"] = pd.to_numeric(_first_existing_series(work, ["ra_deg"]), errors="coerce")
    clean["dec_deg"] = pd.to_numeric(_first_existing_series(work, ["dec_deg"]), errors="coerce")
    clean["sp_type"] = _first_existing_series(work, ["sp_type", "SpT", "SpType"])
    clean["teff_catalog"] = _first_numeric_series(work, ["teff_catalog", "T*", "Teff", "TEFF"])
    clean["distance_pc"] = _first_numeric_series(work, ["distance_pc", "Dist", "D"])
    clean["disk_temperature"] = _first_numeric_series(
        work,
        ["disk_temperature", "Td1", "Tdt2", "Tgr", "Tgr1", "Tgr2"],
    )
    clean["disk_radius"] = _first_numeric_series(
        work,
        ["disk_radius", "Rd1", "Rd2", "D1", "D2"],
    )
    clean["reference"] = _first_existing_series(work, ["reference", "Ref", "BibCode"])
    clean["sample_role"] = _first_existing_series(work, ["sample_role"])
    clean["has_tess_lightcurve"] = _first_existing_series(work, ["has_tess_lightcurve"])
    clean["n_tess_products"] = pd.to_numeric(
        _first_existing_series(work, ["n_tess_products"]),
        errors="coerce",
    )
    clean["first_author"] = _first_existing_series(work, ["first_author"])
    clean["first_mission"] = _first_existing_series(work, ["first_mission"])
    clean["first_year"] = pd.to_numeric(
        _first_existing_series(work, ["first_year"]),
        errors="coerce",
    )
    clean["first_sector"] = pd.to_numeric(
        _first_existing_series(work, ["first_sector"]),
        errors="coerce",
    )
    clean["tess_query_status"] = _first_existing_series(work, ["tess_query_status"]).map(
        _coerce_status
    )

    tic_status = _first_existing_series(work, ["tic_query_status"]).map(_coerce_status)
    gaia_status = _first_existing_series(work, ["gaia_query_status"]).map(_coerce_status)

    clean["tic_id"] = _first_existing_series(work, ["tic_id"]).map(_empty_scientific_value)
    clean["gaia_dr3_source_id"] = _first_existing_series(
        work,
        ["gaia_dr3_source_id"],
    ).map(_empty_scientific_value)
    clean["tmag"] = pd.to_numeric(
        _first_existing_series(work, ["tmag"]).map(_empty_scientific_value),
        errors="coerce",
    )
    clean["bp_rp"] = pd.to_numeric(
        _first_existing_series(work, ["bp_rp"]).map(_empty_scientific_value),
        errors="coerce",
    )
    clean["parallax"] = pd.to_numeric(
        _first_existing_series(work, ["parallax"]).map(_empty_scientific_value),
        errors="coerce",
    )
    clean["gaia_query_status"] = gaia_status
    clean["tic_query_status"] = tic_status

    for column in ["tic_id", "tmag"]:
        clean.loc[clean["tic_query_status"] != "matched", column] = pd.NA
    for column in ["gaia_dr3_source_id", "bp_rp", "parallax"]:
        clean.loc[clean["gaia_query_status"] != "matched", column] = pd.NA

    clean = clean.reset_index(drop=True)
    return clean[
        [
            "target_name",
            "source_catalog",
            "ra_deg",
            "dec_deg",
            "sp_type",
            "teff_catalog",
            "distance_pc",
            "disk_temperature",
            "disk_radius",
            "reference",
            "sample_role",
            "has_tess_lightcurve",
            "n_tess_products",
            "first_author",
            "first_mission",
            "first_year",
            "first_sector",
            "tess_query_status",
            "tic_id",
            "gaia_dr3_source_id",
            "tmag",
            "bp_rp",
            "parallax",
            "gaia_query_status",
            "tic_query_status",
        ]
    ]


def _parse_cotten_coord(coord_text: str) -> tuple[float, float]:
    parts = str(coord_text).split()
    if len(parts) < 6:
        return np.nan, np.nan
    ra_deg = _parse_sexagesimal(" ".join(parts[:3]), is_ra=True)
    dec_deg = _parse_sexagesimal(" ".join(parts[3:6]), is_ra=False)
    return ra_deg, dec_deg


def _parse_float_or_nan(value) -> float:
    if pd.isna(value):
        return np.nan
    text = str(value).strip()
    if not text:
        return np.nan
    return pd.to_numeric(text, errors="coerce")


def _read_cotten_song_pipe_table(path: Path) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    with Path(path).open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.rstrip("\n")
            if "|" not in line or line.startswith("#") or set(line.strip()) <= {"-"}:
                continue
            parts = [part.strip() for part in line.split("|")]
            if len(parts) < 17 or parts[0] in {"Name", ""} or set(parts[0]) <= {"-"}:
                continue

            ra_deg, dec_deg = _parse_cotten_coord(parts[2])
            rows.append(
                {
                    "target_name": parts[0] or pd.NA,
                    "source_catalog": "Cotten & Song 2016 table3",
                    "ra_deg": ra_deg,
                    "dec_deg": dec_deg,
                    "sp_type": parts[3] or pd.NA,
                    "teff_catalog": _parse_float_or_nan(parts[4]),
                    "disk_temperature": _parse_float_or_nan(parts[6]),
                    "disk_radius": _parse_float_or_nan(parts[7]),
                    "distance_pc": _parse_float_or_nan(parts[11]),
                    "reference": parts[16] if len(parts) > 16 and parts[16] else pd.NA,
                    "sample_role": "disk_or_ir_excess_target",
                }
            )
    return pd.DataFrame(rows)


def build_target_sample_from_local_cotten_song(
    csv_path="catalogs/raw/cotten_song_table3.csv",
    ascii_path="catalogs/raw/cotten_song_table3.dat.txt",
    max_targets: int = 50,
) -> pd.DataFrame:
    """Build a dev target sample from local Cotten & Song table3 files.

    The downloaded ``cotten_song_table3.csv`` may be an HTML help page depending
    on how VizieR exported it. In that case this function falls back to the real
    local ASCII table3 file and does not fabricate rows.
    """
    if max_targets < 1:
        raise ValueError("max_targets must be at least 1")

    csv_path = Path(csv_path)
    ascii_path = Path(ascii_path)
    source_df = pd.DataFrame()
    if csv_path.exists():
        head = csv_path.read_text(encoding="utf-8", errors="replace")[:512].lower()
        if "<html" not in head:
            try:
                raw = pd.read_csv(csv_path)
                normalized = normalize_catalog_columns(raw, "Cotten & Song 2016 table3")
                source_df = build_clean_target_table(normalized)
            except Exception as exc:
                print(f"Warning: local Cotten CSV parse failed, trying ASCII table: {exc}")
        else:
            print(
                "Warning: catalogs/raw/cotten_song_table3.csv is HTML, not a data CSV; "
                "using catalogs/raw/cotten_song_table3.dat.txt instead."
            )

    if source_df.empty:
        if not ascii_path.exists():
            raise FileNotFoundError(
                f"No parseable Cotten table found at {csv_path} or {ascii_path}"
            )
        source_df = _read_cotten_song_pipe_table(ascii_path)

    keep_columns = [
        "target_name",
        "source_catalog",
        "ra_deg",
        "dec_deg",
        "sp_type",
        "teff_catalog",
        "disk_temperature",
        "disk_radius",
        "distance_pc",
        "reference",
        "sample_role",
    ]
    for column in keep_columns:
        if column not in source_df.columns:
            source_df[column] = pd.NA

    return source_df[keep_columns].head(max_targets).reset_index(drop=True)


def _query_region_arcsec(ra_deg: float, dec_deg: float, radius_arcsec: float):
    from astropy.coordinates import SkyCoord
    import astropy.units as u

    return SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg), radius_arcsec * u.arcsec


def crossmatch_targets_with_tic(
    df: pd.DataFrame,
    max_targets: int | None = None,
    radius_arcsec: float = 5.0,
) -> pd.DataFrame:
    """Crossmatch targets to TIC by RA/Dec using MAST Catalogs.query_region."""
    work = df.copy()
    for column in ["tic_id", "tmag", "teff_tic", "tic_match_sep_arcsec", "tic_query_status"]:
        if column not in work.columns:
            work[column] = pd.NA
    work["tic_query_status"] = work["tic_query_status"].map(_coerce_status)

    try:
        from astroquery.mast import Catalogs
    except ImportError:
        print("Warning: astroquery.mast is unavailable; TIC crossmatch skipped.")
        work["tic_query_status"] = "failed"
        return work

    limit = len(work) if max_targets is None else min(max_targets, len(work))
    print(f"Crossmatching TIC metadata for {limit} target rows...")
    for idx in work.index[:limit]:
        ra = pd.to_numeric(work.loc[idx, "ra_deg"], errors="coerce")
        dec = pd.to_numeric(work.loc[idx, "dec_deg"], errors="coerce")
        if not np.isfinite(ra) or not np.isfinite(dec):
            work.loc[idx, "tic_query_status"] = "not_found"
            continue
        try:
            coord, radius = _query_region_arcsec(float(ra), float(dec), radius_arcsec)
            result = Catalogs.query_region(coord, radius=radius, catalog="TIC")
        except Exception as exc:
            print(f"Warning: TIC query failed for row {idx}: {exc}")
            work.loc[idx, ["tic_id", "tmag", "teff_tic", "tic_match_sep_arcsec"]] = pd.NA
            work.loc[idx, "tic_query_status"] = "failed"
            continue
        if result is None or len(result) == 0:
            work.loc[idx, ["tic_id", "tmag", "teff_tic", "tic_match_sep_arcsec"]] = pd.NA
            work.loc[idx, "tic_query_status"] = "not_found"
            continue

        result_df = _table_to_dataframe(result)
        ra_col = safe_column_lookup(result_df, ["ra", "RA", "ra_deg"])
        dec_col = safe_column_lookup(result_df, ["dec", "DEC", "dec_deg"])
        if ra_col is not None and dec_col is not None:
            sep = angular_separation_arcsec(
                ra,
                dec,
                pd.to_numeric(result_df[ra_col], errors="coerce").to_numpy(),
                pd.to_numeric(result_df[dec_col], errors="coerce").to_numpy(),
            )
            best_idx = int(np.nanargmin(sep))
            if float(sep[best_idx]) > radius_arcsec:
                work.loc[idx, ["tic_id", "tmag", "teff_tic", "tic_match_sep_arcsec"]] = pd.NA
                work.loc[idx, "tic_query_status"] = "not_found"
                continue
            match_sep = float(sep[best_idx])
        else:
            best_idx = 0
            match_sep = pd.NA

        best = result_df.iloc[best_idx]
        tic_col = safe_column_lookup(result_df, ["ID", "tic_id", "TIC"])
        tmag_col = safe_column_lookup(result_df, ["Tmag", "tmag", "TESSMAG"])
        teff_col = safe_column_lookup(result_df, ["Teff", "teff", "TEFF"])
        gaia_col = safe_column_lookup(result_df, ["GAIA", "Gaia", "gaia", "gaia_dr3_source_id"])
        work.loc[idx, "tic_id"] = best.get(tic_col, pd.NA) if tic_col else pd.NA
        if tmag_col:
            work.loc[idx, "tmag"] = pd.to_numeric(best.get(tmag_col), errors="coerce")
        if teff_col:
            work.loc[idx, "teff_tic"] = pd.to_numeric(best.get(teff_col), errors="coerce")
        work.loc[idx, "tic_match_sep_arcsec"] = match_sep
        if gaia_col and "gaia_dr3_source_id" in work.columns and pd.notna(best.get(gaia_col)):
            work.loc[idx, "gaia_dr3_source_id"] = best.get(gaia_col)
        work.loc[idx, "tic_query_status"] = "matched"

    if limit < len(work):
        work.loc[work.index[limit:], "tic_query_status"] = "not_attempted"
    return work


def crossmatch_targets_with_gaia(
    df: pd.DataFrame,
    max_targets: int | None = None,
    radius_arcsec: float = 5.0,
) -> pd.DataFrame:
    """Crossmatch targets to Gaia DR3 by RA/Dec using astroquery.gaia."""
    work = df.copy()
    for column in [
        "gaia_dr3_source_id",
        "bp_rp",
        "parallax",
        "gaia_match_sep_arcsec",
        "gaia_query_status",
    ]:
        if column not in work.columns:
            work[column] = pd.NA
    work["gaia_query_status"] = work["gaia_query_status"].map(_coerce_status)

    try:
        from astroquery.gaia import Gaia
        from astropy.coordinates import SkyCoord
        import astropy.units as u
    except ImportError:
        print("Warning: astroquery.gaia is unavailable; Gaia crossmatch skipped.")
        work["gaia_query_status"] = "failed"
        return work

    limit = len(work) if max_targets is None else min(max_targets, len(work))
    print(f"Crossmatching Gaia DR3 metadata for {limit} target rows...")
    for idx in work.index[:limit]:
        ra = pd.to_numeric(work.loc[idx, "ra_deg"], errors="coerce")
        dec = pd.to_numeric(work.loc[idx, "dec_deg"], errors="coerce")
        if not np.isfinite(ra) or not np.isfinite(dec):
            work.loc[idx, "gaia_query_status"] = "not_found"
            continue
        try:
            coord = SkyCoord(ra=float(ra) * u.deg, dec=float(dec) * u.deg)
            job = Gaia.cone_search_async(coord, radius=radius_arcsec * u.arcsec)
            result = job.get_results()
        except Exception as exc:
            print(f"Warning: Gaia query failed for row {idx}: {exc}")
            work.loc[
                idx,
                ["gaia_dr3_source_id", "bp_rp", "parallax", "gaia_match_sep_arcsec"],
            ] = pd.NA
            work.loc[idx, "gaia_query_status"] = "failed"
            continue
        if result is None or len(result) == 0:
            work.loc[
                idx,
                ["gaia_dr3_source_id", "bp_rp", "parallax", "gaia_match_sep_arcsec"],
            ] = pd.NA
            work.loc[idx, "gaia_query_status"] = "not_found"
            continue

        result_df = _table_to_dataframe(result)
        ra_col = safe_column_lookup(result_df, ["ra", "RA", "ra_deg"])
        dec_col = safe_column_lookup(result_df, ["dec", "DEC", "dec_deg"])
        if ra_col is not None and dec_col is not None:
            sep = angular_separation_arcsec(
                ra,
                dec,
                pd.to_numeric(result_df[ra_col], errors="coerce").to_numpy(),
                pd.to_numeric(result_df[dec_col], errors="coerce").to_numpy(),
            )
            best_idx = int(np.nanargmin(sep))
            if float(sep[best_idx]) > radius_arcsec:
                work.loc[
                    idx,
                    ["gaia_dr3_source_id", "bp_rp", "parallax", "gaia_match_sep_arcsec"],
                ] = pd.NA
                work.loc[idx, "gaia_query_status"] = "not_found"
                continue
            match_sep = float(sep[best_idx])
        else:
            best_idx = 0
            match_sep = pd.NA

        best = result_df.iloc[best_idx]
        source_col = safe_column_lookup(result_df, ["source_id", "SOURCE_ID", "gaia_dr3_source_id"])
        bp_col = safe_column_lookup(result_df, ["bp_rp", "BP_RP", "bp_rp_corr"])
        plx_col = safe_column_lookup(result_df, ["parallax", "Plx", "plx"])
        work.loc[idx, "gaia_dr3_source_id"] = (
            best.get(source_col, pd.NA) if source_col else pd.NA
        )
        if bp_col:
            work.loc[idx, "bp_rp"] = pd.to_numeric(best.get(bp_col), errors="coerce")
        if plx_col:
            work.loc[idx, "parallax"] = pd.to_numeric(best.get(plx_col), errors="coerce")
        work.loc[idx, "gaia_match_sep_arcsec"] = match_sep
        work.loc[idx, "gaia_query_status"] = "matched"

    if limit < len(work):
        work.loc[work.index[limit:], "gaia_query_status"] = "not_attempted"
    return work


def filter_targets_for_dev_scan(df: pd.DataFrame) -> pd.DataFrame:
    """Keep rows with finite coordinates and TESS light-curve availability."""
    if df.empty:
        return df.copy()
    required = {"ra_deg", "dec_deg", "has_tess_lightcurve"}
    missing = required.difference(df.columns)
    if missing:
        print(f"Warning: cannot fully filter dev scan; missing columns: {sorted(missing)}")
        return df.copy()

    work = df.copy()
    coords_ok = np.isfinite(pd.to_numeric(work["ra_deg"], errors="coerce")) & np.isfinite(
        pd.to_numeric(work["dec_deg"], errors="coerce")
    )
    tess_ok = work["has_tess_lightcurve"].astype(str).str.lower().isin(["true", "1", "yes"])
    return work[coords_ok & tess_ok].reset_index(drop=True)


def normalize_control_pool_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize a user-provided real non-disk control pool."""
    if df is None or df.empty:
        return pd.DataFrame()
    work = df.copy()
    aliases = {
        "tic_id": ["tic_id", "TIC", "ID"],
        "target_name": ["target_name", "name", "Name", "tic_id", "TIC"],
        "ra_deg": ["ra_deg", "ra", "RA", "RAJ2000"],
        "dec_deg": ["dec_deg", "dec", "DEC", "DEJ2000", "Dec"],
        "tmag": ["tmag", "Tmag", "TESSMAG"],
        "bp_rp": ["bp_rp", "BP_RP", "BP-RP"],
        "teff": ["teff", "Teff", "TEFF"],
        "parallax": ["parallax", "Plx", "plx"],
        "n_tess_products": ["n_tess_products", "n_tess", "tess_products"],
        "has_tess_lightcurve": ["has_tess_lightcurve", "has_tess", "tess_available"],
        "ir_excess_flag": ["ir_excess_flag", "has_ir_excess", "disk_flag"],
    }
    for output_column, candidates in aliases.items():
        source_column = safe_column_lookup(work, candidates)
        if source_column is not None:
            work[output_column] = work[source_column]
        elif output_column not in work.columns:
            work[output_column] = pd.NA

    for column in ["ra_deg", "dec_deg", "tmag", "bp_rp", "teff", "parallax", "n_tess_products"]:
        work[column] = pd.to_numeric(work[column], errors="coerce")
    work["sample_role"] = "candidate_control"
    work["sample_is_preliminary"] = True
    return work


def save_catalog(df: pd.DataFrame, path) -> Path:
    """Save a catalog CSV with parent directories created."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    return output_path
