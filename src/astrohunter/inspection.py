"""Phase 5F: Manual review gallery and candidate inspection package.

Converts automated-pipeline candidate tables into visual inspection materials
that a human reviewer can use to decide whether each event is likely
astrophysical, variable-star behaviour, a systematic artifact, or
detector over-triggering.

SCIENTIFIC CAUTION:
- Visual review does NOT confirm exocomet detections.
- Disposition labels produced here are preliminary and must not be presented
  as scientific results without further validation.
- TIC 444335503 (control, 20 events) must be treated as likely overtriggered
  until all events have been individually inspected.
- Final paper/report requires completed manual review, multi-sector
  confirmation, and expert validation.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

INSPECTION_VERSION = "phase5f_v1"

MANUAL_LABEL_ALLOWED: tuple[str, ...] = (
    "keep_candidate",
    "likely_systematic",
    "likely_variable_star",
    "likely_flare",
    "likely_eb_or_contamination",
    "insufficient_data",
    "unsure",
)

DISPOSITION_COLUMNS: tuple[str, ...] = (
    "tic_id",
    "event_time_btjd",
    "sample_role",
    "target_name",
    "recommended_review_priority",
    "inspection_reason",
    "local_snr",
    "final_candidate_score",
    "depth_ppm",
    "duration_hours",
    "automated_vetting_status",
    "external_false_positive_flag",
    "manual_label",
    "reviewer_name",
    "review_date",
    "visual_event_quality",
    "likely_artifact_reason",
    "notes",
    "followup_priority",
)

_VETTING_FLAG_COLS = (
    "flag_low_snr",
    "flag_edge_event",
    "flag_single_point_like",
    "flag_likely_flare_shape",
    "flag_low_delta_chi2",
    "flag_poor_asymmetry_fit",
)

_MANUAL_EMPTY_COLS = frozenset({
    "manual_label",
    "reviewer_name",
    "review_date",
    "visual_event_quality",
    "likely_artifact_reason",
    "notes",
    "followup_priority",
})


# ---------------------------------------------------------------------------
# Inspection target list
# ---------------------------------------------------------------------------

def build_inspection_target_list(
    candidate_df: pd.DataFrame,
    priority_df: pd.DataFrame,
    overtriggered_df: pd.DataFrame,
    max_events_per_star: int = 5,
) -> pd.DataFrame:
    """Build the prioritised list of candidate events for manual inspection.

    Selection criteria (events may satisfy multiple):

    1. *medium_priority* — all events on medium-priority TICs, up to
       max_events_per_star per TIC (sorted by final_candidate_score desc).
    2. *pass_vetting* — all events with automated_vetting_status == "pass".
    3. *overtriggered_top5* — top max_events_per_star events (by score) for
       each of the five TICs with the highest total candidate count.
    4. *target_top_event* — the top-scoring event on every target TIC not
       already represented by criteria 1–3.

    Each selected event carries an ``inspection_reason`` column containing a
    comma-separated list of the criteria it matched.  Events are sorted with
    pass-vetting events first, then medium-priority, overtriggered, then
    target-top.

    Parameters
    ----------
    candidate_df:
        Full event-level candidate table (Phase 5D / 5E output).
    priority_df:
        Manual review priority table with ``recommended_review_priority``
        column (Phase 5E output).
    overtriggered_df:
        Overtriggered-star table (Phase 5E output).
    max_events_per_star:
        Cap on events selected per TIC for medium-priority and
        overtriggered criteria.

    Returns
    -------
    pd.DataFrame with all original columns plus ``inspection_reason``.
    """
    empty_cols = list(candidate_df.columns) + ["inspection_reason"]
    if candidate_df.empty:
        return pd.DataFrame(columns=empty_cols)

    # Build priority map: tic_id -> recommended_review_priority
    priority_map: dict[int, str] = {}
    if (
        not priority_df.empty
        and "recommended_review_priority" in priority_df.columns
        and "tic_id" in priority_df.columns
    ):
        priority_map = dict(
            zip(
                priority_df["tic_id"].astype(int),
                priority_df["recommended_review_priority"],
            )
        )

    score_col = "final_candidate_score" if "final_candidate_score" in candidate_df.columns else None
    cand_sorted = (
        candidate_df.sort_values(score_col, ascending=False)
        if score_col
        else candidate_df.copy()
    )

    # event key: (tic_id, event_time rounded to avoid float equality traps)
    def _key(row: pd.Series) -> tuple:
        t = row.get("event_time_btjd", float("nan"))
        try:
            t_r = round(float(t), 6)
        except (TypeError, ValueError):
            t_r = float("nan")
        return (int(row["tic_id"]), t_r)

    event_reasons: dict[tuple, set[str]] = {}
    event_rows: dict[tuple, pd.Series] = {}

    def _add(row: pd.Series, reason: str) -> None:
        k = _key(row)
        event_reasons.setdefault(k, set()).add(reason)
        event_rows[k] = row

    # 1. Medium-priority TICs
    medium_tics = {tic for tic, p in priority_map.items() if p == "medium"}
    for tic in medium_tics:
        subset = cand_sorted[cand_sorted["tic_id"] == tic].head(max_events_per_star)
        for _, row in subset.iterrows():
            _add(row, "medium_priority")

    # 2. Pass events
    if "automated_vetting_status" in candidate_df.columns:
        for _, row in candidate_df[candidate_df["automated_vetting_status"] == "pass"].iterrows():
            _add(row, "pass_vetting")

    # 3. Top 5 overtriggered TICs
    if not overtriggered_df.empty and "tic_id" in overtriggered_df.columns:
        for tic in overtriggered_df["tic_id"].head(5).tolist():
            subset = cand_sorted[cand_sorted["tic_id"] == tic].head(max_events_per_star)
            for _, row in subset.iterrows():
                _add(row, "overtriggered_top5")

    # 4. Top event per target TIC
    if "sample_role" in candidate_df.columns:
        for tic in candidate_df[candidate_df["sample_role"] == "target"]["tic_id"].unique():
            top = cand_sorted[cand_sorted["tic_id"] == tic].head(1)
            if not top.empty:
                _add(top.iloc[0], "target_top_event")

    if not event_rows:
        return pd.DataFrame(columns=empty_cols)

    rows = []
    for k, row in event_rows.items():
        r = row.copy()
        r["inspection_reason"] = ",".join(sorted(event_reasons[k]))
        rows.append(r)

    result = pd.DataFrame(rows).reset_index(drop=True)

    # Attach recommended_review_priority if not already present
    if priority_map and "recommended_review_priority" not in result.columns:
        result["recommended_review_priority"] = (
            result["tic_id"].map(priority_map).fillna("low")
        )
    elif priority_map and result["recommended_review_priority"].isna().all():
        result["recommended_review_priority"] = (
            result["tic_id"].map(priority_map).fillna("low")
        )

    def _sort_cat(reason_str: str) -> int:
        if "pass_vetting" in reason_str:
            return 0
        if "medium_priority" in reason_str:
            return 1
        if "overtriggered_top5" in reason_str:
            return 2
        return 3

    result["_sort_cat"] = result["inspection_reason"].apply(_sort_cat)
    sort_cols = ["_sort_cat"] + ([score_col] if score_col and score_col in result.columns else [])
    result = result.sort_values(
        sort_cols,
        ascending=[True] + [False] * (len(sort_cols) - 1),
    )
    return result.drop(columns=["_sort_cat"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Light-curve I/O
# ---------------------------------------------------------------------------

def load_cached_lightcurve_for_tic(
    tic_id: int,
    cache_dir: str | Path = "cache/lightcurves",
) -> pd.DataFrame | None:
    """Load a cached Parquet light curve for a given TIC.

    Returns
    -------
    DataFrame with at least ``time_btjd`` and ``flux`` columns, or None if
    the cache file does not exist or cannot be read.
    """
    path = Path(cache_dir) / f"tic_{tic_id}.parquet"
    if not path.exists():
        logger.debug("No cached light curve for TIC %s at %s.", tic_id, path)
        return None
    try:
        return pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load cached LC for TIC %s: %s", tic_id, exc)
        return None


def extract_event_window(
    lc_df: pd.DataFrame,
    event_time_btjd: float,
    window_days: float = 1.0,
) -> pd.DataFrame:
    """Return lc_df rows within ±(window_days/2) of event_time_btjd.

    Returns an empty DataFrame (same columns) when no rows fall in the window
    or when lc_df has no ``time_btjd`` column.
    """
    if lc_df is None or lc_df.empty:
        return pd.DataFrame(columns=getattr(lc_df, "columns", []))
    if "time_btjd" not in lc_df.columns:
        return pd.DataFrame(columns=lc_df.columns)
    half = window_days / 2.0
    t = pd.to_numeric(lc_df["time_btjd"], errors="coerce")
    mask = (t >= event_time_btjd - half) & (t <= event_time_btjd + half)
    return lc_df[mask].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Per-event inspection plot
# ---------------------------------------------------------------------------

def _annotation_lines(event_row: pd.Series) -> list[str]:
    """Build text annotation lines for an event panel."""
    tic = event_row.get("tic_id", "?")
    name = event_row.get("target_name", f"TIC {tic}")
    role = event_row.get("sample_role", "?")
    t = event_row.get("event_time_btjd", float("nan"))
    snr = event_row.get("local_snr", float("nan"))
    score = event_row.get("final_candidate_score", float("nan"))
    depth = event_row.get("depth_ppm", float("nan"))
    dur = event_row.get("duration_hours", float("nan"))
    status = event_row.get("automated_vetting_status", "?")
    ext = event_row.get("external_false_positive_flag", "?")
    reason = event_row.get("inspection_reason", "")
    priority = event_row.get("recommended_review_priority", "")

    def _fmt(v, fmt=".2f"):
        try:
            f = float(v)
            return format(f, fmt) if np.isfinite(f) else "?"
        except (TypeError, ValueError):
            return "?"

    lines = [
        f"TIC {tic}  [{role}]",
        f"{name}",
        "─" * 22,
        f"BTJD {_fmt(t, '.4f')}",
        f"SNR      {_fmt(snr)}",
        f"score    {_fmt(score, '.3f')}",
        f"depth    {_fmt(depth, '.0f')} ppm",
        f"dur      {_fmt(dur)} h",
        "─" * 22,
        f"vetting: {status}",
        f"ext:     {ext}",
    ]
    if priority:
        lines.append(f"priority: {priority}")
    if reason:
        for part in reason.split(","):
            lines.append(f"  [{part.strip()}]")

    active_flags = [
        c.replace("flag_", "")
        for c in _VETTING_FLAG_COLS
        if c in event_row.index and bool(event_row.get(c, False))
    ]
    if active_flags:
        lines.append("─" * 22)
        lines.append("flags:")
        for f in active_flags:
            lines.append(f"  {f}")

    return lines


def create_event_inspection_plot(
    event_row: pd.Series,
    lc_df: pd.DataFrame | None,
    window_days: float = 1.0,
    output_path: str | Path | None = None,
    title: str | None = None,
) -> Any:
    """Create an inspection figure for one candidate event.

    Layout (when lc_df is available):
    - Top row  (full width): full light curve with event time marked.
    - Bottom left (75 %): zoom window ±window_days/2 around event.
    - Bottom right (25 %): text annotation with key event metrics.

    When lc_df is None or empty, a single annotation-only panel is shown.

    Returns the matplotlib Figure object.  If output_path is given the figure
    is also saved there.

    SCIENTIFIC CAUTION:  These plots are for visual triage only.
    A clean-looking event does NOT confirm an exocomet detection.
    """
    event_time = float(event_row.get("event_time_btjd", float("nan")))
    tic = event_row.get("tic_id", "?")
    role = event_row.get("sample_role", "?")
    status = event_row.get("automated_vetting_status", "?")
    ann_text = "\n".join(_annotation_lines(event_row))
    title = title or f"TIC {tic} [{role}]  BTJD {event_time:.4f}  [{status}]"

    no_lc = lc_df is None or lc_df.empty or "time_btjd" not in lc_df.columns

    if no_lc:
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.axis("off")
        ax.text(
            0.04, 0.97, ann_text,
            transform=ax.transAxes, va="top", ha="left",
            fontsize=9, family="monospace",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="lightyellow", alpha=0.9),
        )
        ax.set_title(title + "\n[No cached light curve]", fontsize=10)
        fig.tight_layout()
    else:
        time_arr = pd.to_numeric(lc_df["time_btjd"], errors="coerce").to_numpy()
        flux_arr = pd.to_numeric(lc_df["flux"], errors="coerce").to_numpy()
        win_df = extract_event_window(lc_df, event_time, window_days=window_days)

        fig = plt.figure(figsize=(13, 7))
        gs = fig.add_gridspec(
            2, 2,
            width_ratios=[3, 1],
            height_ratios=[1, 1.5],
            hspace=0.38,
            wspace=0.06,
        )
        ax_full = fig.add_subplot(gs[0, :])
        ax_zoom = fig.add_subplot(gs[1, 0])
        ax_ann = fig.add_subplot(gs[1, 1])

        # Full LC
        ax_full.plot(time_arr, flux_arr, "k.", markersize=1.5, alpha=0.4, rasterized=True)
        if np.isfinite(event_time):
            ax_full.axvline(
                event_time, color="tab:red", linewidth=1.0, alpha=0.85,
                label="Candidate event",
            )
        ax_full.set_ylabel("Norm. flux", fontsize=9)
        ax_full.set_xlabel("Time (BTJD)", fontsize=9)
        ax_full.tick_params(labelsize=8)
        ax_full.grid(alpha=0.2)
        ax_full.legend(loc="upper right", fontsize=8)
        ax_full.set_title("Full light curve", fontsize=9, pad=2)

        # Zoom
        if not win_df.empty:
            zt = pd.to_numeric(win_df["time_btjd"], errors="coerce").to_numpy()
            zf = pd.to_numeric(win_df["flux"], errors="coerce").to_numpy()
            ax_zoom.plot(zt, zf, "k.-", markersize=4, linewidth=0.8, alpha=0.85)
        else:
            ax_zoom.text(
                0.5, 0.5, "No data in window",
                ha="center", va="center", transform=ax_zoom.transAxes, fontsize=10,
            )
        if np.isfinite(event_time):
            ax_zoom.axvline(
                event_time, color="tab:red", linestyle="--", linewidth=1.3,
                label="Candidate event",
            )
        ax_zoom.set_ylabel("Norm. flux", fontsize=9)
        ax_zoom.set_xlabel("Time (BTJD)", fontsize=9)
        ax_zoom.tick_params(labelsize=8)
        ax_zoom.grid(alpha=0.2)
        ax_zoom.legend(loc="upper left", fontsize=8)
        ax_zoom.set_title(f"Zoom  ±{window_days / 2:.2f} d", fontsize=9, pad=2)

        # Annotation panel
        ax_ann.axis("off")
        ax_ann.text(
            0.04, 0.98, ann_text,
            transform=ax_ann.transAxes, va="top", ha="left",
            fontsize=8, family="monospace",
            bbox=dict(boxstyle="round,pad=0.35", facecolor="lightyellow", alpha=0.92),
        )

        fig.suptitle(title, fontsize=10, y=1.00)

    if output_path is not None:
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(p, dpi=150, bbox_inches="tight")

    return fig


# ---------------------------------------------------------------------------
# Per-TIC gallery
# ---------------------------------------------------------------------------

def _build_tic_metadata(
    tic_id: int,
    events_df: pd.DataFrame,
    lc_df: pd.DataFrame | None,
) -> dict:
    """Return the metadata dict for a TIC gallery folder."""
    row0 = events_df.iloc[0] if not events_df.empty else pd.Series(dtype=object)

    def _scalar(col, default=None):
        v = row0.get(col, default)
        if isinstance(v, float) and np.isnan(v):
            return None
        if hasattr(v, "item"):
            return v.item()
        return v

    reasons: list[str] = []
    if "inspection_reason" in events_df.columns:
        seen: set[str] = set()
        for r_str in events_df["inspection_reason"]:
            for part in str(r_str).split(","):
                part = part.strip()
                if part and part not in seen:
                    seen.add(part)
                    reasons.append(part)

    n_pass = 0
    if "automated_vetting_status" in events_df.columns:
        n_pass = int((events_df["automated_vetting_status"] == "pass").sum())

    def _safe_max(col):
        if col not in events_df.columns:
            return None
        s = pd.to_numeric(events_df[col], errors="coerce")
        return float(s.max()) if not s.isna().all() else None

    return {
        "tic_id": tic_id,
        "target_name": _scalar("target_name", f"TIC {tic_id}"),
        "sample_role": _scalar("sample_role", "?"),
        "recommended_review_priority": _scalar("recommended_review_priority", "?"),
        "inspection_reasons": reasons,
        "n_events_in_inspection": len(events_df),
        "n_pass_vetting": n_pass,
        "max_local_snr": _safe_max("local_snr"),
        "max_final_candidate_score": _safe_max("final_candidate_score"),
        "ra_deg": _scalar("ra_deg"),
        "dec_deg": _scalar("dec_deg"),
        "has_cached_lightcurve": lc_df is not None and not lc_df.empty,
        "gallery_version": INSPECTION_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def create_star_event_gallery(
    tic_id: int,
    events_df: pd.DataFrame,
    lc_df: pd.DataFrame | None,
    output_dir: str | Path,
    window_days: float = 1.0,
) -> list[Path]:
    """Create the inspection gallery for all events on one TIC.

    Saves to ``output_dir/tic_{tic_id}/``:

    - ``tic_{tic_id}_full_lc_with_events.png``  (if lc_df is available)
    - ``event_{i:02d}_BTJD{time:.3f}.png``       (one per event, sorted by score)
    - ``events_summary.csv``
    - ``metadata.json``

    Returns list of created file Paths.

    SCIENTIFIC CAUTION:  These plots are for visual triage only.
    A visually clean event is NOT a confirmed exocomet detection.
    """
    from astrohunter.plotting import plot_lightcurve_with_events  # local to avoid coupling

    tic_dir = Path(output_dir) / f"tic_{tic_id}"
    tic_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []

    # Full LC with all events marked
    if lc_df is not None and not lc_df.empty and "time_btjd" in lc_df.columns:
        lc_fig_path = tic_dir / f"tic_{tic_id}_full_lc_with_events.png"
        name = events_df["target_name"].iloc[0] if "target_name" in events_df.columns else f"TIC {tic_id}"
        role = events_df["sample_role"].iloc[0] if "sample_role" in events_df.columns else "?"
        priority = (
            events_df["recommended_review_priority"].iloc[0]
            if "recommended_review_priority" in events_df.columns
            else "?"
        )
        lc_title = (
            f"TIC {tic_id}  [{role}]  {name}  |  priority={priority}\n"
            f"{len(events_df)} inspection events"
        )
        t = pd.to_numeric(lc_df["time_btjd"], errors="coerce").to_numpy()
        f = pd.to_numeric(lc_df["flux"], errors="coerce").to_numpy()
        fig = plot_lightcurve_with_events(t, f, events_df, title=lc_title, output_path=lc_fig_path)
        plt.close(fig)
        created.append(lc_fig_path)

    # Per-event zoom plots (sorted by score desc)
    score_col = "final_candidate_score" if "final_candidate_score" in events_df.columns else None
    events_sorted = (
        events_df.sort_values(score_col, ascending=False).reset_index(drop=True)
        if score_col
        else events_df.reset_index(drop=True)
    )

    for i, (_, row) in enumerate(events_sorted.iterrows()):
        t_val = row.get("event_time_btjd", float("nan"))
        try:
            t_str = f"{float(t_val):.3f}"
        except (TypeError, ValueError):
            t_str = "nan"
        fig_path = tic_dir / f"event_{i:02d}_BTJD{t_str}.png"
        fig = create_event_inspection_plot(
            event_row=row,
            lc_df=lc_df,
            window_days=window_days,
            output_path=fig_path,
        )
        plt.close(fig)
        created.append(fig_path)

    # Events summary CSV
    csv_path = tic_dir / "events_summary.csv"
    events_sorted.to_csv(csv_path, index=False)
    created.append(csv_path)

    # Metadata JSON
    meta = _build_tic_metadata(tic_id, events_df, lc_df)
    json_path = tic_dir / "metadata.json"
    json_path.write_text(json.dumps(meta, indent=2, default=str))
    created.append(json_path)

    return created


# ---------------------------------------------------------------------------
# Disposition template
# ---------------------------------------------------------------------------

def create_disposition_template(inspection_df: pd.DataFrame) -> pd.DataFrame:
    """Create an empty disposition template for manual review.

    Returns a DataFrame with one row per inspection event.  Manual fields
    (manual_label, reviewer_name, review_date, visual_event_quality,
    likely_artifact_reason, notes, followup_priority) are empty strings.

    Allowed manual_label values (documented here, not programmatically enforced):
    ``keep_candidate``, ``likely_systematic``, ``likely_variable_star``,
    ``likely_flare``, ``likely_eb_or_contamination``, ``insufficient_data``,
    ``unsure``.

    SCIENTIFIC CAUTION:  Disposition labels filled in by a reviewer are
    preliminary and do NOT constitute scientific confirmation or rejection.
    """
    if inspection_df.empty:
        return pd.DataFrame(columns=list(DISPOSITION_COLUMNS))

    result = pd.DataFrame(index=inspection_df.index)

    for col in DISPOSITION_COLUMNS:
        if col in _MANUAL_EMPTY_COLS:
            result[col] = ""
        elif col in inspection_df.columns:
            result[col] = inspection_df[col].values
        else:
            result[col] = pd.NA

    return result.reset_index(drop=True)
