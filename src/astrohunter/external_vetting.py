"""Phase 5C external catalog crossmatching for AstroHunter KZ candidate vetting.

Checks candidate host stars against external catalogs of known variable stars,
eclipsing binaries, and SIMBAD objects to help identify likely false positives.

External sources queried:
- AAVSO VSX via VizieR B/vsx/vsx
- SIMBAD object-type lookup via astroquery.simbad
- TESS Eclipsing Binary catalog via VizieR J/ApJS/258/16

SCIENTIFIC CONSTRAINTS:
- External catalog checks REDUCE false-positive contamination but do NOT
  confirm exocomet detections.
- A catalog match indicates possible contamination; it is NOT definitive.
- Lack of an external match does NOT prove astrophysical validity.
- Remote catalog failures (network, timeout, API) are reported transparently
  via status = 'failed'; they do NOT mean 'not found'.
- Manual inspection of every candidate is still required.
- Automated false-positive flags are heuristic classifiers, not verdicts.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

EXTERNAL_VETTER_VERSION = "phase5c_v1"

# --------------------------------------------------------------------------
# Status constants
# --------------------------------------------------------------------------

STATUS_NOT_ATTEMPTED = "not_attempted"
STATUS_FAILED = "failed"
STATUS_NOT_FOUND = "not_found"
STATUS_MATCHED = "matched"

# --------------------------------------------------------------------------
# False-positive label constants
# --------------------------------------------------------------------------

FP_KNOWN_VARIABLE = "known_variable_match"
FP_POSSIBLE_EB = "possible_eclipsing_binary_match"
FP_SIMBAD_PROBLEMATIC = "simbad_nonstellar_or_problematic_type"
FP_NO_MATCH = "no_external_match"
FP_CHECK_FAILED = "external_check_failed"

# --------------------------------------------------------------------------
# Catalog reference sets
# --------------------------------------------------------------------------

# VSX variable types that suggest eclipsing binary or similar contamination.
# These are prefixes; a type like "EA/SD" starts with "EA".
VSX_EB_PREFIXES: frozenset[str] = frozenset({
    "EA", "EB", "EW", "E", "EC",
    "RR", "RRAB", "RRC",
    "DCEP", "CEP",
    "CV", "UG", "SU", "NL",
    "HADS", "DSCT", "GDOR",
})

# All VSX types we flag as "known variable" (broader than EB)
VSX_VARIABLE_PREFIXES: frozenset[str] = frozenset({
    "M", "SR", "SRB", "SRS",
    "LPV", "MISC",
})

# SIMBAD OTYPE codes that indicate contamination concern.
# Keys are SIMBAD otype strings; values are human-readable labels.
SIMBAD_CONCERN_OTYPES: dict[str, str] = {
    "EB*": "eclipsing binary",
    "EB": "eclipsing binary",
    "EclBin": "eclipsing binary",
    "Algol": "Algol-type EB",
    "bCep": "beta Cep variable",
    "RRLyr": "RR Lyrae variable",
    "Cepheid": "Cepheid variable",
    "LPV*": "long-period variable",
    "Mira": "Mira variable",
    "YSO": "young stellar object",
    "CV*": "cataclysmic variable",
    "Nova": "nova",
    "V*": "variable star (generic)",
    "pulsV*": "pulsating variable",
    "WD*": "white dwarf",
    "BYDra": "BY Dra type variable",
    "RS*": "RS CVn variable",
    "RRLyr*": "RR Lyrae variable",
}

# Astropy/astroquery availability
try:
    from astropy.coordinates import SkyCoord
    import astropy.units as _u
    from astroquery.vizier import Vizier
    from astroquery.simbad import Simbad as _SimbadBase
    _ASTROQUERY_AVAILABLE = True
except ImportError:  # pragma: no cover
    _ASTROQUERY_AVAILABLE = False
    logger.warning(
        "astroquery/astropy not available — all external catalog queries "
        "will return status='failed'."
    )


# --------------------------------------------------------------------------
# Individual catalog query functions
# --------------------------------------------------------------------------

def query_vsx_near_position(
    ra_deg: float,
    dec_deg: float,
    radius_arcsec: float = 10.0,
) -> dict:
    """Query AAVSO VSX via VizieR B/vsx/vsx for known variable stars.

    Parameters
    ----------
    ra_deg, dec_deg:
        Sky position in decimal degrees (J2000).
    radius_arcsec:
        Search radius in arcseconds.

    Returns
    -------
    dict with keys:
        vsx_check_status, vsx_match_name, vsx_variable_type, vsx_sep_arcsec
    """
    result: dict = {
        "vsx_check_status": STATUS_NOT_ATTEMPTED,
        "vsx_match_name": "",
        "vsx_variable_type": "",
        "vsx_sep_arcsec": float("nan"),
    }

    if not (np.isfinite(float(ra_deg)) and np.isfinite(float(dec_deg))):
        return result

    if not _ASTROQUERY_AVAILABLE:
        result["vsx_check_status"] = STATUS_FAILED
        return result

    try:
        coord = SkyCoord(ra=float(ra_deg) * _u.deg, dec=float(dec_deg) * _u.deg)
        v = Vizier(columns=["Name", "Type", "RAJ2000", "DEJ2000"])
        v.ROW_LIMIT = 5
        tables = v.query_region(coord, radius=float(radius_arcsec) * _u.arcsec,
                                catalog="B/vsx/vsx")

        if tables is None or len(tables) == 0:
            result["vsx_check_status"] = STATUS_NOT_FOUND
            return result

        vsx_table = tables[0]
        if len(vsx_table) == 0:
            result["vsx_check_status"] = STATUS_NOT_FOUND
            return result

        ra_arr = np.asarray(vsx_table["RAJ2000"], dtype=float)
        dec_arr = np.asarray(vsx_table["DEJ2000"], dtype=float)
        match_coords = SkyCoord(ra=ra_arr * _u.deg, dec=dec_arr * _u.deg)
        seps = coord.separation(match_coords)
        idx = int(np.argmin(seps.arcsec))

        result["vsx_check_status"] = STATUS_MATCHED
        result["vsx_match_name"] = str(vsx_table["Name"][idx])
        result["vsx_variable_type"] = str(vsx_table["Type"][idx])
        result["vsx_sep_arcsec"] = float(seps[idx].arcsec)

    except Exception as exc:
        logger.warning("VSX query failed (RA=%.4f Dec=%.4f): %s", ra_deg, dec_deg, exc)
        result["vsx_check_status"] = STATUS_FAILED

    return result


def query_simbad_object_type(
    ra_deg: float,
    dec_deg: float,
    radius_arcsec: float = 10.0,
) -> dict:
    """Query SIMBAD for the primary object type near the given position.

    Parameters
    ----------
    ra_deg, dec_deg:
        Sky position in decimal degrees (J2000).
    radius_arcsec:
        Search radius in arcseconds.

    Returns
    -------
    dict with keys:
        simbad_check_status, simbad_main_id, simbad_otype, simbad_otypes,
        simbad_sep_arcsec
    """
    result: dict = {
        "simbad_check_status": STATUS_NOT_ATTEMPTED,
        "simbad_main_id": "",
        "simbad_otype": "",
        "simbad_otypes": "",
        "simbad_sep_arcsec": float("nan"),
    }

    if not (np.isfinite(float(ra_deg)) and np.isfinite(float(dec_deg))):
        return result

    if not _ASTROQUERY_AVAILABLE:
        result["simbad_check_status"] = STATUS_FAILED
        return result

    try:
        simbad_obj = _SimbadBase()
        # Request otype (single-value field, always safe).
        # otypes field returns a sub-table in astroquery 0.4.11 TAP, which
        # complicates row indexing — skip it and fall back to the otype column.
        try:
            simbad_obj.add_votable_fields("otype")
        except Exception:
            pass

        coord = SkyCoord(ra=float(ra_deg) * _u.deg, dec=float(dec_deg) * _u.deg)
        simbad_result = simbad_obj.query_region(
            coord, radius=float(radius_arcsec) * _u.arcsec
        )

        if simbad_result is None or len(simbad_result) == 0:
            result["simbad_check_status"] = STATUS_NOT_FOUND
            return result

        # Build a case-insensitive column name map for robustness across
        # astroquery versions (0.4.x TAP returns lowercase; older returns UPPERCASE)
        col_map = {c.lower(): c for c in simbad_result.colnames}
        logger.debug("SIMBAD returned columns: %s", list(simbad_result.colnames))

        # Try to compute separations and pick the closest match.
        # astroquery 0.4.11 (TAP) returns RA/DEC as decimal-degree strings.
        # Older astroquery returns sexagesimal strings.
        idx = 0
        sep = float("nan")
        try:
            ra_col = col_map.get("ra")
            dec_col = col_map.get("dec")
            if ra_col and dec_col:
                try:
                    ra_vals = np.asarray(simbad_result[ra_col], dtype=float)
                    dec_vals = np.asarray(simbad_result[dec_col], dtype=float)
                    match_coords = SkyCoord(ra=ra_vals * _u.deg, dec=dec_vals * _u.deg)
                except (ValueError, TypeError):
                    # Fallback: try parsing as sexagesimal (older astroquery)
                    match_coords = SkyCoord(
                        ra=list(simbad_result[ra_col]),
                        dec=list(simbad_result[dec_col]),
                        unit=(_u.hourangle, _u.deg),
                    )
                seps = coord.separation(match_coords)
                idx = int(np.argmin(seps.arcsec))
                sep = float(seps[idx].arcsec)
        except Exception:
            pass

        def _get_col(table, *names, row=0, default=""):
            for name in names:
                actual = col_map.get(name.lower())
                if actual:
                    try:
                        return str(table[actual][row])
                    except Exception:
                        pass
            return default

        result["simbad_check_status"] = STATUS_MATCHED
        # astroquery 0.4.11 TAP: "main_id"; older: "MAIN_ID"
        result["simbad_main_id"] = _get_col(simbad_result, "MAIN_ID", "main_id", "ID")
        # astroquery 0.4.11 TAP: "otype"; older: "OTYPE"
        result["simbad_otype"] = _get_col(simbad_result, "OTYPE", "otype", "OTYPE_S")
        # astroquery 0.4.11 TAP: "otypes.otype"; older: "OTYPES"
        result["simbad_otypes"] = _get_col(
            simbad_result, "OTYPES", "otypes", "otypes.otype", "OTYPE_LIST"
        )
        result["simbad_sep_arcsec"] = sep

    except Exception as exc:
        logger.warning("SIMBAD query failed (RA=%.4f Dec=%.4f): %s", ra_deg, dec_deg, exc)
        result["simbad_check_status"] = STATUS_FAILED

    return result


def query_tess_eb_catalog_near_position(
    ra_deg: float,
    dec_deg: float,
    radius_arcsec: float = 30.0,
) -> dict:
    """Query the TESS Eclipsing Binary catalog via VizieR J/ApJS/258/16.

    Reference: Prsa et al. 2022, ApJS 258, 16.

    Parameters
    ----------
    ra_deg, dec_deg:
        Sky position in decimal degrees (J2000).
    radius_arcsec:
        Search radius in arcseconds. Wider default (30″) because the
        TESS pixel scale is ~21″/pixel.

    Returns
    -------
    dict with keys:
        tess_eb_check_status, tess_eb_match_id, tess_eb_sep_arcsec
    """
    result: dict = {
        "tess_eb_check_status": STATUS_NOT_ATTEMPTED,
        "tess_eb_match_id": "",
        "tess_eb_sep_arcsec": float("nan"),
    }

    if not (np.isfinite(float(ra_deg)) and np.isfinite(float(dec_deg))):
        return result

    if not _ASTROQUERY_AVAILABLE:
        result["tess_eb_check_status"] = STATUS_FAILED
        return result

    try:
        coord = SkyCoord(ra=float(ra_deg) * _u.deg, dec=float(dec_deg) * _u.deg)
        v = Vizier(columns=["TIC", "RAJ2000", "DEJ2000"])
        v.ROW_LIMIT = 5
        tables = v.query_region(
            coord,
            radius=float(radius_arcsec) * _u.arcsec,
            catalog="J/ApJS/258/16",
        )

        if tables is None or len(tables) == 0:
            result["tess_eb_check_status"] = STATUS_NOT_FOUND
            return result

        eb_table = tables[0]
        if len(eb_table) == 0:
            result["tess_eb_check_status"] = STATUS_NOT_FOUND
            return result

        ra_arr = np.asarray(eb_table["RAJ2000"], dtype=float)
        dec_arr = np.asarray(eb_table["DEJ2000"], dtype=float)
        match_coords = SkyCoord(ra=ra_arr * _u.deg, dec=dec_arr * _u.deg)
        seps = coord.separation(match_coords)
        idx = int(np.argmin(seps.arcsec))

        result["tess_eb_check_status"] = STATUS_MATCHED
        result["tess_eb_match_id"] = str(eb_table["TIC"][idx])
        result["tess_eb_sep_arcsec"] = float(seps[idx].arcsec)

    except Exception as exc:
        logger.warning("TESS-EB query failed (RA=%.4f Dec=%.4f): %s", ra_deg, dec_deg, exc)
        result["tess_eb_check_status"] = STATUS_FAILED

    return result


# --------------------------------------------------------------------------
# Classification helper
# --------------------------------------------------------------------------

def _classify_external_flag(
    vsx_result: dict,
    simbad_result: dict,
    eb_result: dict,
) -> tuple[str, str]:
    """Derive (external_false_positive_flag, external_vetting_notes) from query results.

    Priority order for flag assignment:
      TESS-EB match > VSX EB-type match > VSX other variable > SIMBAD problematic type

    A failed query alone (with no matches from other catalogs) yields
    FP_CHECK_FAILED to signal that the no-match interpretation is unreliable.
    """
    flag = FP_NO_MATCH
    notes: list[str] = []
    any_failed = False

    # TESS-EB (most specific EB signal)
    eb_status = eb_result.get("tess_eb_check_status", STATUS_NOT_ATTEMPTED)
    if eb_status == STATUS_MATCHED:
        flag = FP_POSSIBLE_EB
        match_id = eb_result.get("tess_eb_match_id", "")
        sep = eb_result.get("tess_eb_sep_arcsec", float("nan"))
        sep_str = f"{sep:.1f}\"" if np.isfinite(float(sep)) else "?"
        notes.append(f"TESS-EB catalog: TIC {match_id} ({sep_str})")
    elif eb_status == STATUS_FAILED:
        any_failed = True

    # VSX
    vsx_status = vsx_result.get("vsx_check_status", STATUS_NOT_ATTEMPTED)
    if vsx_status == STATUS_MATCHED:
        vtype_raw = str(vsx_result.get("vsx_variable_type", ""))
        vtype = vtype_raw.split(":")[0].split("/")[0].strip().upper()
        vname = vsx_result.get("vsx_match_name", "")
        sep = vsx_result.get("vsx_sep_arcsec", float("nan"))
        sep_str = f"{float(sep):.1f}\"" if np.isfinite(float(sep)) else "?"

        is_eb = any(vtype.startswith(p) for p in VSX_EB_PREFIXES)
        if is_eb:
            if flag == FP_NO_MATCH:
                flag = FP_POSSIBLE_EB
        else:
            if flag == FP_NO_MATCH:
                flag = FP_KNOWN_VARIABLE
        notes.append(f"VSX: {vname} type={vtype_raw} ({sep_str})")
    elif vsx_status == STATUS_FAILED:
        any_failed = True

    # SIMBAD
    sim_status = simbad_result.get("simbad_check_status", STATUS_NOT_ATTEMPTED)
    if sim_status == STATUS_MATCHED:
        otype = str(simbad_result.get("simbad_otype", ""))
        main_id = simbad_result.get("simbad_main_id", "")
        sep = simbad_result.get("simbad_sep_arcsec", float("nan"))
        sep_str = f"{float(sep):.1f}\"" if np.isfinite(float(sep)) else "?"

        if otype in SIMBAD_CONCERN_OTYPES:
            human = SIMBAD_CONCERN_OTYPES[otype]
            if flag == FP_NO_MATCH:
                flag = FP_SIMBAD_PROBLEMATIC
            notes.append(f"SIMBAD: {main_id} otype={otype} ({human}) ({sep_str})")
        else:
            notes.append(f"SIMBAD: {main_id} otype={otype} ({sep_str})")
    elif sim_status == STATUS_FAILED:
        any_failed = True

    # If nothing matched but at least one failed → can't trust "no match"
    if flag == FP_NO_MATCH and any_failed:
        flag = FP_CHECK_FAILED
        notes.append("WARNING: one or more catalog queries failed — no-match is unreliable")

    return flag, "; ".join(notes)


# --------------------------------------------------------------------------
# Table-level check
# --------------------------------------------------------------------------

_EMPTY_VSX = {
    "vsx_check_status": STATUS_NOT_ATTEMPTED,
    "vsx_match_name": "",
    "vsx_variable_type": "",
    "vsx_sep_arcsec": float("nan"),
}
_EMPTY_SIM = {
    "simbad_check_status": STATUS_NOT_ATTEMPTED,
    "simbad_main_id": "",
    "simbad_otype": "",
    "simbad_otypes": "",
    "simbad_sep_arcsec": float("nan"),
}
_EMPTY_EB = {
    "tess_eb_check_status": STATUS_NOT_ATTEMPTED,
    "tess_eb_match_id": "",
    "tess_eb_sep_arcsec": float("nan"),
}

ALL_EXTERNAL_COLUMNS: list[str] = [
    "vsx_check_status", "vsx_match_name", "vsx_variable_type", "vsx_sep_arcsec",
    "simbad_check_status", "simbad_main_id", "simbad_otype", "simbad_otypes",
    "simbad_sep_arcsec",
    "tess_eb_check_status", "tess_eb_match_id", "tess_eb_sep_arcsec",
    "external_false_positive_flag", "external_vetting_notes",
    "external_vetter_version",
]


def external_check_candidate_table(
    candidate_df: pd.DataFrame,
    radius_arcsec: float = 10.0,
    skip_vsx: bool = False,
    skip_simbad: bool = False,
    skip_tess_eb: bool = False,
) -> pd.DataFrame:
    """Run external catalog checks on each candidate row.

    Requires ``ra_deg`` and ``dec_deg`` columns.  If absent, all checks for
    that row are set to ``not_attempted``.

    Parameters
    ----------
    candidate_df:
        Candidate event table (must have ``ra_deg``, ``dec_deg`` for queries).
    radius_arcsec:
        Position-match radius for VSX and SIMBAD.
        TESS-EB uses 3× this value (TESS pixel scale ~21″/pixel).
    skip_vsx, skip_simbad, skip_tess_eb:
        Skip individual catalog queries (useful for offline/test runs).

    Returns
    -------
    pd.DataFrame
        Copy of input with external-check columns appended.
    """
    result = candidate_df.copy()

    # Initialise all output columns
    nan_cols = {"vsx_sep_arcsec", "simbad_sep_arcsec", "tess_eb_sep_arcsec"}
    for col in ALL_EXTERNAL_COLUMNS:
        if col not in result.columns:
            result[col] = float("nan") if col in nan_cols else ""

    if result.empty:
        return result

    has_coords = "ra_deg" in result.columns and "dec_deg" in result.columns

    for i, idx in enumerate(result.index):
        ra = float(result.at[idx, "ra_deg"]) if has_coords else float("nan")
        dec = float(result.at[idx, "dec_deg"]) if has_coords else float("nan")

        tic_id = result.at[idx, "tic_id"] if "tic_id" in result.columns else "?"
        logger.info(
            "External check %d/%d TIC %s RA=%.4f Dec=%.4f",
            i + 1, len(result), tic_id, ra, dec,
        )

        if not (np.isfinite(ra) and np.isfinite(dec)):
            for k, v in {**_EMPTY_VSX, **_EMPTY_SIM, **_EMPTY_EB}.items():
                result.at[idx, k] = v
            result.at[idx, "external_false_positive_flag"] = FP_NO_MATCH
            result.at[idx, "external_vetting_notes"] = "No RA/Dec available for this candidate"
            result.at[idx, "external_vetter_version"] = EXTERNAL_VETTER_VERSION
            continue

        # VSX
        if skip_vsx:
            vsx_res = dict(_EMPTY_VSX)
        else:
            vsx_res = query_vsx_near_position(ra, dec, radius_arcsec=radius_arcsec)

        # SIMBAD
        if skip_simbad:
            sim_res = dict(_EMPTY_SIM)
        else:
            sim_res = query_simbad_object_type(ra, dec, radius_arcsec=radius_arcsec)

        # TESS-EB (wider search radius)
        if skip_tess_eb:
            eb_res = dict(_EMPTY_EB)
        else:
            eb_res = query_tess_eb_catalog_near_position(
                ra, dec, radius_arcsec=radius_arcsec * 3.0
            )

        fp_flag, notes = _classify_external_flag(vsx_res, sim_res, eb_res)

        for k, v in {**vsx_res, **sim_res, **eb_res}.items():
            result.at[idx, k] = v
        result.at[idx, "external_false_positive_flag"] = fp_flag
        result.at[idx, "external_vetting_notes"] = notes
        result.at[idx, "external_vetter_version"] = EXTERNAL_VETTER_VERSION

    return result


# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------

def summarize_external_checks(candidate_df: pd.DataFrame) -> pd.DataFrame:
    """Compute a per-catalog and per-flag summary of external check results.

    Parameters
    ----------
    candidate_df:
        Candidate table after ``external_check_candidate_table()``.

    Returns
    -------
    pd.DataFrame
        One row per catalog / per flag value with n_matched, n_not_found,
        n_failed, n_not_attempted columns.
    """
    rows: list[dict] = []
    total = len(candidate_df)

    for label, status_col in [
        ("VSX (B/vsx/vsx)", "vsx_check_status"),
        ("SIMBAD", "simbad_check_status"),
        ("TESS-EB (J/ApJS/258/16)", "tess_eb_check_status"),
    ]:
        if status_col not in candidate_df.columns:
            rows.append({
                "catalog": label,
                "n_total": total,
                "n_matched": 0,
                "n_not_found": 0,
                "n_failed": 0,
                "n_not_attempted": total,
            })
            continue
        col = candidate_df[status_col]
        rows.append({
            "catalog": label,
            "n_total": total,
            "n_matched": int((col == STATUS_MATCHED).sum()),
            "n_not_found": int((col == STATUS_NOT_FOUND).sum()),
            "n_failed": int((col == STATUS_FAILED).sum()),
            "n_not_attempted": int((col == STATUS_NOT_ATTEMPTED).sum()),
        })

    # External false-positive flag breakdown
    fp_col = "external_false_positive_flag"
    if fp_col in candidate_df.columns:
        for flag_val, count in candidate_df[fp_col].value_counts().items():
            rows.append({
                "catalog": f"flag:{flag_val}",
                "n_total": total,
                "n_matched": int(count),
                "n_not_found": 0,
                "n_failed": 0,
                "n_not_attempted": 0,
            })

    return pd.DataFrame(rows)
