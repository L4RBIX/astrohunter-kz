#!/usr/bin/env python
"""Build a real TIC control pool and greedy matched pairs."""

from __future__ import annotations

import argparse
import gzip
import sys
import tarfile
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from astrohunter.catalogs import build_target_sample_from_local_cotten_song, save_catalog
from astrohunter.crossmatch import angular_separation_arcsec, safe_column_lookup
from scripts.enrich_tess import enrich_tess


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build real non-disk TIC controls.")
    parser.add_argument("--targets", required=True)
    parser.add_argument("--output-pool", required=True)
    parser.add_argument("--output-pairs", required=True)
    parser.add_argument("--control-ratio", type=int, default=3)
    parser.add_argument("--max-query-targets", type=int, default=None)
    parser.add_argument("--max-candidates-per-target", type=int, default=10)
    parser.add_argument("--max-control-tess-checks", type=int, default=80)
    return parser.parse_args()


def _as_numeric(series):
    return pd.to_numeric(series, errors="coerce")


def _clean_tic(value):
    if pd.isna(value):
        return pd.NA
    try:
        return str(int(float(value)))
    except Exception:
        text = str(value).strip().replace("TIC", "").strip()
        return text if text else pd.NA


def _table_to_dataframe(table) -> pd.DataFrame:
    try:
        return table.to_pandas()
    except Exception:
        return pd.DataFrame(np.asarray(table))


def _normalize_tic_rows(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    aliases = {
        "tic_id": ["ID", "tic_id", "TIC"],
        "tmag": ["Tmag", "tmag", "TESSMAG"],
        "teff": ["Teff", "teff", "TEFF"],
        "parallax": ["plx", "parallax", "Plx"],
        "bp_rp": ["bp_rp", "BP_RP"],
        "ra_deg": ["ra", "RA", "ra_deg"],
        "dec_deg": ["dec", "DEC", "dec_deg"],
        "gaia_dr3_source_id": ["GAIA", "Gaia", "gaia"],
    }
    out = pd.DataFrame(index=df.index)
    for output, candidates in aliases.items():
        column = safe_column_lookup(df, candidates)
        out[output] = df[column] if column is not None else pd.NA
    bp_col = safe_column_lookup(df, ["gaiabp", "phot_bp_mean_mag"])
    rp_col = safe_column_lookup(df, ["gaiarp", "phot_rp_mean_mag"])
    if "bp_rp" in out.columns and out["bp_rp"].isna().all() and bp_col and rp_col:
        out["bp_rp"] = pd.to_numeric(df[bp_col], errors="coerce") - pd.to_numeric(
            df[rp_col],
            errors="coerce",
        )
    for column in ["tmag", "teff", "bp_rp", "parallax", "ra_deg", "dec_deg"]:
        out[column] = pd.to_numeric(out[column], errors="coerce")
    out["tic_id"] = out["tic_id"].map(_clean_tic)
    return out.dropna(subset=["tic_id", "ra_deg", "dec_deg"]).drop_duplicates("tic_id")


def _load_mcdonald_ir_coords(path: Path) -> pd.DataFrame:
    if not path.exists() or not tarfile.is_tarfile(path):
        return pd.DataFrame(columns=["ra_deg", "dec_deg"])
    rows = []
    try:
        with tarfile.open(path) as archive:
            raw = gzip.decompress(archive.extractfile("./table3.dat.gz").read()).decode(
                "latin1",
                "replace",
            )
        for line in raw.splitlines():
            if not line.strip():
                continue
            ra = pd.to_numeric(line[16:27].strip(), errors="coerce")
            dec = pd.to_numeric(line[28:39].strip(), errors="coerce")
            if np.isfinite(ra) and np.isfinite(dec):
                rows.append({"ra_deg": float(ra), "dec_deg": float(dec)})
    except Exception as exc:
        print(f"Warning: could not parse McDonald IR-excess coordinates: {exc}")
    return pd.DataFrame(rows, columns=["ra_deg", "dec_deg"])


def _load_exclusion_coords(targets: pd.DataFrame) -> tuple[set[str], pd.DataFrame]:
    tic_ids = set(targets["tic_id"].dropna().map(_clean_tic).astype(str)) if "tic_id" in targets else set()
    frames = []
    try:
        frames.append(build_target_sample_from_local_cotten_song(max_targets=10_000)[["ra_deg", "dec_deg"]])
    except Exception as exc:
        print(f"Warning: could not load Cotten exclusion coordinates: {exc}")
    frames.append(_load_mcdonald_ir_coords(Path("catalogs/raw/mcdonald_2017_irexcess.dat")))
    if frames:
        coords = pd.concat(frames, ignore_index=True)
        coords["ra_deg"] = pd.to_numeric(coords["ra_deg"], errors="coerce")
        coords["dec_deg"] = pd.to_numeric(coords["dec_deg"], errors="coerce")
        coords = coords.dropna(subset=["ra_deg", "dec_deg"]).reset_index(drop=True)
    else:
        coords = pd.DataFrame(columns=["ra_deg", "dec_deg"])
    print(
        f"Loaded {len(coords)} IR-excess exclusion coordinates and {len(tic_ids)} target TIC IDs.",
        flush=True,
    )
    return tic_ids, coords


def _is_excluded(row, excluded_tics: set[str], excluded_coords: pd.DataFrame) -> str:
    tic = _clean_tic(row.get("tic_id"))
    if pd.notna(tic) and str(tic) in excluded_tics:
        return "known_ir_excess_tic"
    if excluded_coords.empty:
        return ""
    ra = row.get("ra_deg")
    dec = row.get("dec_deg")
    if not np.isfinite(ra) or not np.isfinite(dec):
        return ""
    sep = angular_separation_arcsec(
        ra,
        dec,
        excluded_coords["ra_deg"].to_numpy(),
        excluded_coords["dec_deg"].to_numpy(),
    )
    if np.any(sep <= 5.0):
        return "known_ir_excess_coordinate"
    return ""


def query_tic_candidates(targets: pd.DataFrame, args: argparse.Namespace) -> pd.DataFrame:
    from astroquery.mast import Catalogs

    rows = []
    query_targets = targets.copy()
    if args.max_query_targets is not None:
        query_targets = query_targets.head(args.max_query_targets)

    for target in query_targets.itertuples(index=False):
        tmag = getattr(target, "tmag", np.nan)
        teff = getattr(target, "teff_tic", np.nan)
        if not np.isfinite(tmag) or not np.isfinite(teff):
            continue
        tmin, tmax = float(tmag) - 0.5, float(tmag) + 0.5
        emin, emax = max(2500.0, float(teff) - 300.0), float(teff) + 300.0
        try:
            result = Catalogs.query_criteria(catalog="TIC", Tmag=[tmin, tmax], Teff=[emin, emax])
        except Exception as exc:
            print(
                f"Warning: TIC control query failed near target {getattr(target, 'target_name', '')}: {exc}",
                flush=True,
            )
            continue
        normalized = _normalize_tic_rows(_table_to_dataframe(result))
        if normalized.empty:
            continue
        rows.append(normalized.head(args.max_candidates_per_target))
        if rows and sum(len(frame) for frame in rows) >= args.max_control_tess_checks:
            break

    if not rows:
        return pd.DataFrame()
    candidates = pd.concat(rows, ignore_index=True).drop_duplicates("tic_id").reset_index(drop=True)
    print(f"Queried {len(candidates)} unique TIC candidate controls before exclusions.", flush=True)
    return candidates


def enrich_control_tess(candidates: pd.DataFrame, max_checks: int) -> pd.DataFrame:
    candidates = candidates.head(max_checks).copy()
    enriched = enrich_tess(candidates, max_targets=len(candidates))
    return enriched


def build_control_pool(targets: pd.DataFrame, args: argparse.Namespace) -> pd.DataFrame:
    excluded_tics, excluded_coords = _load_exclusion_coords(targets)
    candidates = query_tic_candidates(targets, args)
    if candidates.empty:
        print("Warning: no TIC control candidates returned.")
        return pd.DataFrame()

    candidates["excluded_reason"] = candidates.apply(
        lambda row: _is_excluded(row, excluded_tics, excluded_coords),
        axis=1,
    )
    candidates = candidates[candidates["excluded_reason"] == ""].reset_index(drop=True)
    print(f"{len(candidates)} TIC candidate controls remain after IR-excess exclusions.", flush=True)
    if candidates.empty:
        print("Warning: all TIC control candidates were excluded as known IR-excess sources.")
        return pd.DataFrame()

    candidates = enrich_control_tess(candidates, max_checks=args.max_control_tess_checks)
    has_tess = candidates["has_tess_lightcurve"].astype(str).str.lower().isin(["true"])
    pool = candidates[has_tess].copy().reset_index(drop=True)
    for column in [
        "bp_rp",
        "parallax",
        "first_sector",
        "n_tess_products",
        "has_tess_lightcurve",
        "excluded_reason",
    ]:
        if column not in pool.columns:
            pool[column] = pd.NA if column != "excluded_reason" else ""
    return pool[
        [
            "tic_id",
            "tmag",
            "teff",
            "bp_rp",
            "parallax",
            "ra_deg",
            "dec_deg",
            "has_tess_lightcurve",
            "n_tess_products",
            "first_sector",
            "excluded_reason",
        ]
    ]


def build_matched_pairs(targets: pd.DataFrame, pool: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    pair_rows = []
    used_controls: set[str] = set()
    eligible_targets = targets[targets["has_tess_lightcurve"].astype(str).str.lower().isin(["true"])].copy()

    for target in eligible_targets.itertuples(index=False):
        target_tic = _clean_tic(getattr(target, "tic_id", pd.NA))
        tmag = getattr(target, "tmag", np.nan)
        bp_rp = getattr(target, "bp_rp", np.nan)
        parallax = getattr(target, "parallax", np.nan)
        teff = getattr(target, "teff_tic", np.nan)

        candidates = pool[~pool["tic_id"].astype(str).isin(used_controls)].copy()
        candidates = candidates[candidates["has_tess_lightcurve"].astype(str).str.lower().isin(["true"])]
        if np.isfinite(tmag):
            candidates = candidates[(candidates["tmag"] - tmag).abs() < 0.5]
        if np.isfinite(bp_rp) and "bp_rp" in candidates:
            color = pd.to_numeric(candidates["bp_rp"], errors="coerce")
            color_candidates = candidates[(color - bp_rp).abs() < 0.15]
            if not color_candidates.empty:
                candidates = color_candidates
            elif np.isfinite(teff):
                candidates = candidates[(pd.to_numeric(candidates["teff"], errors="coerce") - teff).abs() < 300]
        elif np.isfinite(teff):
            candidates = candidates[(pd.to_numeric(candidates["teff"], errors="coerce") - teff).abs() < 300]
        if np.isfinite(parallax) and parallax > 0:
            cplx = pd.to_numeric(candidates["parallax"], errors="coerce")
            candidates = candidates[((cplx - parallax).abs() / parallax) < 0.5]

        if candidates.empty:
            continue

        score = (candidates["tmag"] - tmag).abs() / 0.5 if np.isfinite(tmag) else 0.0
        if np.isfinite(bp_rp) and "bp_rp" in candidates:
            score = score + (pd.to_numeric(candidates["bp_rp"], errors="coerce") - bp_rp).abs().fillna(0.15) / 0.15
        elif np.isfinite(teff):
            score = score + (pd.to_numeric(candidates["teff"], errors="coerce") - teff).abs().fillna(300) / 300
        if np.isfinite(parallax) and parallax > 0:
            score = score + ((pd.to_numeric(candidates["parallax"], errors="coerce") - parallax).abs() / parallax).fillna(0.5) / 0.5

        best_idx = score.sort_values().index[0]
        best = candidates.loc[best_idx]
        used_controls.add(str(best["tic_id"]))
        pair_rows.append(
            {
                "target_tic_id": target_tic,
                "target_name": getattr(target, "target_name", pd.NA),
                "control_tic_id": best["tic_id"],
                "tmag_target": tmag,
                "tmag_control": best["tmag"],
                "bp_rp_target": bp_rp,
                "bp_rp_control": best.get("bp_rp", pd.NA),
                "parallax_target": parallax,
                "parallax_control": best.get("parallax", pd.NA),
                "match_quality_score": float(score.loc[best_idx]),
            }
        )

    pairs = pd.DataFrame(
        pair_rows,
        columns=[
            "target_tic_id",
            "target_name",
            "control_tic_id",
            "tmag_target",
            "tmag_control",
            "bp_rp_target",
            "bp_rp_control",
            "parallax_target",
            "parallax_control",
            "match_quality_score",
        ],
    )
    return pairs, int(len(eligible_targets) - len(pairs))


def main() -> int:
    args = parse_args()
    targets = pd.read_csv(args.targets)
    pool = build_control_pool(targets, args)
    save_catalog(pool, args.output_pool)
    print(f"Control pool after exclusions and TESS filtering: {len(pool)} stars")

    pairs, unmatched = build_matched_pairs(targets, pool)
    save_catalog(pairs, args.output_pairs)
    print(f"Matched pairs found: {len(pairs)}")
    print(f"Targets with no match found: {unmatched}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
