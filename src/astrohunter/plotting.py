"""Matplotlib plotting helpers for AstroHunter KZ (Phase 1 + Phase 3 + Phase 4)."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def _prepare_output_path(output_path) -> Path | None:
    if output_path is None:
        return None
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _finish_figure(fig, output_path=None):
    path = _prepare_output_path(output_path)
    if path is not None:
        fig.savefig(path, dpi=180, bbox_inches="tight")
    return fig


def plot_full_lightcurve(time, flux, title, output_path=None):
    """Plot the full normalized light curve."""
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(time, flux, "k.", markersize=2, alpha=0.55)
    ax.set_title(title)
    ax.set_xlabel("Time (BTJD days)")
    ax.set_ylabel("Normalized flux")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    return _finish_figure(fig, output_path)


def plot_event_window(
    time,
    flux,
    event_time,
    window_days: float = 0.5,
    title: str | None = None,
    output_path=None,
):
    """Plot a local window around one candidate dip-like feature."""
    half_window = window_days / 2.0
    time_values = np.asarray(time, dtype=float)
    flux_values = np.asarray(flux, dtype=float)
    mask = (time_values >= event_time - half_window) & (
        time_values <= event_time + half_window
    )

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(time_values[mask], flux_values[mask], "k.-", markersize=3, alpha=0.75)
    ax.axvline(
        event_time,
        color="tab:red",
        linestyle="--",
        linewidth=1.2,
        label="Candidate event",
    )
    ax.set_title(title or f"Candidate Dip-Like Feature near BTJD {event_time:.3f}")
    ax.set_xlabel("Time (BTJD days)")
    ax.set_ylabel("Normalized flux")
    ax.grid(alpha=0.25)
    ax.legend(loc="best")
    fig.tight_layout()
    return _finish_figure(fig, output_path)


def plot_zoom_window(time, flux, start, end, title, output_path=None):
    """Plot a user-selected time interval."""
    if end <= start:
        raise ValueError("end must be greater than start")

    time_values = np.asarray(time, dtype=float)
    flux_values = np.asarray(flux, dtype=float)
    mask = (time_values >= start) & (time_values <= end)

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(time_values[mask], flux_values[mask], "k.-", markersize=3, alpha=0.75)
    ax.set_title(title)
    ax.set_xlabel("Time (BTJD days)")
    ax.set_ylabel("Normalized flux")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    return _finish_figure(fig, output_path)


def plot_lightcurve_with_events(time, flux, events_df, title, output_path=None):
    """Plot the full light curve and mark candidate event times."""
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(time, flux, "k.", markersize=2, alpha=0.5)

    if isinstance(events_df, pd.DataFrame) and not events_df.empty:
        for event_time in events_df["event_time_btjd"].to_numpy(dtype=float):
            ax.axvline(event_time, color="tab:red", alpha=0.35, linewidth=0.8)
        ax.plot(
            events_df["event_time_btjd"],
            np.interp(events_df["event_time_btjd"], time, flux),
            "v",
            color="tab:red",
            markersize=5,
            label="Candidate dip-like feature",
        )
        ax.legend(loc="best")

    ax.set_title(title)
    ax.set_xlabel("Time (BTJD days)")
    ax.set_ylabel("Normalized flux")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    return _finish_figure(fig, output_path)


def plot_injected_dip_example(
    time,
    flux_original,
    flux_injected,
    event_time: float,
    depth_ppm: float,
    ingress_hours: float,
    egress_hours: float,
    window_days: float = 1.5,
    output_path=None,
):
    """Plot original vs. injected flux for one synthetic dip example.

    Shows the clean window around the injected event so the dip morphology
    is clearly visible.
    """
    half = window_days / 2.0
    t_arr = np.asarray(time, dtype=float)
    f_orig = np.asarray(flux_original, dtype=float)
    f_inj = np.asarray(flux_injected, dtype=float)
    mask = (t_arr >= event_time - half) & (t_arr <= event_time + half)

    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(t_arr[mask], f_orig[mask], "k.-", markersize=3, alpha=0.55, label="Original flux")
    ax.plot(t_arr[mask], f_inj[mask], ".-", color="tab:blue", markersize=3, alpha=0.8,
            label="Injected dip")
    ax.axvline(event_time, color="tab:red", linestyle="--", linewidth=1.1, label="Dip minimum")
    ax.set_title(
        f"Injected synthetic dip — depth {depth_ppm:.0f} ppm, "
        f"ingress {ingress_hours:.1f} h, egress {egress_hours:.1f} h"
    )
    ax.set_xlabel("Time (BTJD days)")
    ax.set_ylabel("Normalized flux")
    ax.grid(alpha=0.25)
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    return _finish_figure(fig, output_path)


def plot_recovery_vs_depth(recovery_df: pd.DataFrame, output_path=None):
    """Plot injection-recovery fraction as a function of injected depth.

    Bins injected depths into logarithmically spaced bins and computes
    the fraction of injections recovered in each bin.

    This plot characterizes *detector sensitivity*, not real candidate purity.
    """
    if recovery_df is None or recovery_df.empty:
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.text(0.5, 0.5, "No injection-recovery data", ha="center", va="center",
                transform=ax.transAxes)
        return _finish_figure(fig, output_path)

    depths = pd.to_numeric(recovery_df.get("injected_depth_ppm", pd.Series(dtype=float)),
                           errors="coerce").dropna()
    if depths.empty:
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.text(0.5, 0.5, "No depth data in recovery table", ha="center", va="center",
                transform=ax.transAxes)
        return _finish_figure(fig, output_path)

    # Log-spaced bins from min to max depth
    d_min = max(depths.min(), 10.0)
    d_max = depths.max() * 1.05
    bins = np.logspace(np.log10(d_min), np.log10(d_max), num=12)
    bin_centers = 0.5 * (bins[:-1] + bins[1:])

    rec_col = recovery_df.get("recovered", pd.Series(dtype=object))
    recovered = rec_col.astype(bool) if not rec_col.empty else pd.Series(False, index=recovery_df.index)

    frac, counts = [], []
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (depths >= lo) & (depths < hi)
        n = int(mask.sum())
        counts.append(n)
        if n > 0:
            frac.append(float(recovered[mask].sum()) / n)
        else:
            frac.append(np.nan)

    frac_arr = np.array(frac)
    counts_arr = np.array(counts)
    valid = counts_arr > 0

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.step(bin_centers[valid], frac_arr[valid], where="mid", color="tab:blue", linewidth=1.8)
    ax.scatter(bin_centers[valid], frac_arr[valid], c="tab:blue", zorder=3,
               s=[max(5, c * 3) for c in counts_arr[valid]])
    ax.set_xscale("log")
    ax.set_xlim(d_min * 0.8, d_max)
    ax.set_ylim(-0.05, 1.05)
    ax.axhline(0.5, color="gray", linestyle=":", linewidth=1.0)
    ax.set_xlabel("Injected depth (ppm)")
    ax.set_ylabel("Recovery fraction")
    ax.set_title(
        "Injection-recovery: fraction recovered vs. injected depth\n"
        "(Sensitivity test — not real candidate purity)"
    )
    ax.grid(alpha=0.25)
    fig.tight_layout()
    return _finish_figure(fig, output_path)


def plot_recovery_heatmap_depth_duration(recovery_df: pd.DataFrame, output_path=None):
    """Plot a 2-D heatmap of recovery fraction vs. depth × total duration.

    Uses a grid of depth bins (log-scale) and egress-duration bins (linear)
    to show where the detector is most and least sensitive.

    This is a *detector sensitivity* diagnostic, not a result about real events.
    """
    if recovery_df is None or recovery_df.empty:
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.text(0.5, 0.5, "No injection-recovery data", ha="center", va="center",
                transform=ax.transAxes)
        return _finish_figure(fig, output_path)

    depths = pd.to_numeric(recovery_df.get("injected_depth_ppm", pd.Series(dtype=float)),
                           errors="coerce")
    durations = pd.to_numeric(recovery_df.get("injected_egress_hours", pd.Series(dtype=float)),
                              errors="coerce")

    valid = depths.notna() & durations.notna()
    depths = depths[valid]
    durations = durations[valid]
    rec_col = recovery_df.get("recovered", pd.Series(dtype=object))
    recovered = rec_col[valid].astype(bool)

    if depths.empty:
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.text(0.5, 0.5, "Insufficient data for heatmap", ha="center", va="center",
                transform=ax.transAxes)
        return _finish_figure(fig, output_path)

    n_depth_bins = 8
    n_dur_bins = 6
    depth_bins = np.logspace(np.log10(max(depths.min(), 10.0)), np.log10(depths.max() * 1.05), n_depth_bins + 1)
    dur_bins = np.linspace(durations.min() * 0.95, durations.max() * 1.05, n_dur_bins + 1)

    grid = np.full((n_dur_bins, n_depth_bins), np.nan)
    for di in range(n_depth_bins):
        for dui in range(n_dur_bins):
            d_mask = (depths >= depth_bins[di]) & (depths < depth_bins[di + 1])
            du_mask = (durations >= dur_bins[dui]) & (durations < dur_bins[dui + 1])
            mask = d_mask & du_mask
            n = int(mask.sum())
            if n > 0:
                grid[dui, di] = float(recovered[mask].sum()) / n

    depth_centers = 0.5 * (depth_bins[:-1] + depth_bins[1:])
    dur_centers = 0.5 * (dur_bins[:-1] + dur_bins[1:])

    fig, ax = plt.subplots(figsize=(9, 5))
    img = ax.pcolormesh(
        depth_bins, dur_bins, grid,
        cmap="RdYlGn", vmin=0.0, vmax=1.0, shading="flat",
    )
    cbar = fig.colorbar(img, ax=ax, label="Recovery fraction")
    ax.set_xscale("log")
    ax.set_xlabel("Injected depth (ppm)")
    ax.set_ylabel("Injected egress duration (hours)")
    ax.set_title(
        "Injection-recovery heatmap: depth × egress duration\n"
        "(Detector sensitivity — not real event rate)"
    )
    fig.tight_layout()
    return _finish_figure(fig, output_path)


def plot_recovered_vs_missed_examples(
    time,
    flux,
    recovery_df: pd.DataFrame,
    n_examples: int = 3,
    window_days: float = 1.5,
    output_path=None,
):
    """Plot side-by-side windows of recovered and missed injection examples.

    Selects up to *n_examples* each of recovered and missed events and
    plots the local window around the injected event time.
    """
    if recovery_df is None or recovery_df.empty:
        fig, ax = plt.subplots(figsize=(8, 3))
        ax.text(0.5, 0.5, "No injection-recovery data", ha="center", va="center",
                transform=ax.transAxes)
        return _finish_figure(fig, output_path)

    t_arr = np.asarray(time, dtype=float)
    f_arr = np.asarray(flux, dtype=float)

    rec_mask = recovery_df.get("recovered", pd.Series(False, index=recovery_df.index)).astype(bool)
    recovered_rows = recovery_df[rec_mask].head(n_examples)
    missed_rows = recovery_df[~rec_mask].head(n_examples)

    total = len(recovered_rows) + len(missed_rows)
    if total == 0:
        fig, ax = plt.subplots(figsize=(8, 3))
        ax.text(0.5, 0.5, "No examples to show", ha="center", va="center",
                transform=ax.transAxes)
        return _finish_figure(fig, output_path)

    fig, axes = plt.subplots(1, total, figsize=(4.5 * total, 3.5), squeeze=False)
    axes = axes.flatten()

    col_idx = 0
    for _, row in recovered_rows.iterrows():
        _plot_example_panel(axes[col_idx], t_arr, f_arr, row, window_days, label="RECOVERED",
                            color="tab:green")
        col_idx += 1
    for _, row in missed_rows.iterrows():
        _plot_example_panel(axes[col_idx], t_arr, f_arr, row, window_days, label="MISSED",
                            color="tab:red")
        col_idx += 1

    fig.suptitle("Injection-recovery examples (sensitivity test only)", fontsize=9)
    fig.tight_layout()
    return _finish_figure(fig, output_path)


# ---------------------------------------------------------------------------
# Phase 4: ML ranker plots
# ---------------------------------------------------------------------------

def plot_ml_feature_importance(
    model,
    feature_names: list,
    output_path=None,
    title: str = "ML Ranker Feature Importance",
):
    """Plot feature importances from the trained ranker.

    Works with XGBoost and sklearn models that expose ``feature_importances_``.

    The figure communicates which detector features drive the ranking score.
    It does NOT imply that high-importance features confirm astrophysical signal.
    """
    importances = getattr(model, "feature_importances_", None)
    if importances is None or len(importances) == 0:
        fig, ax = plt.subplots(figsize=(7, 3))
        ax.text(0.5, 0.5, "Feature importances not available for this model type.",
                ha="center", va="center", transform=ax.transAxes)
        return _finish_figure(fig, output_path)

    importances = np.asarray(importances, dtype=float)
    n = min(len(importances), len(feature_names))
    feats = list(feature_names)[:n]
    imps = importances[:n]

    order = np.argsort(imps)
    feats_sorted = [feats[i] for i in order]
    imps_sorted = imps[order]

    fig, ax = plt.subplots(figsize=(8, max(3, 0.4 * n + 1)))
    bars = ax.barh(feats_sorted, imps_sorted, color="tab:blue", alpha=0.75)
    ax.set_xlabel("Feature importance (model-internal)")
    ax.set_title(f"{title}\n(Injection-trained ranker — not a discovery metric)")
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    return _finish_figure(fig, output_path)


def plot_precision_recall_curve(
    y_true,
    y_score,
    output_path=None,
    pr_auc: float | None = None,
):
    """Plot the precision–recall curve for the injection-trained ranker.

    Reports PR-AUC on injected synthetic signals only.  This does NOT measure
    real-candidate purity.
    """
    from sklearn.metrics import precision_recall_curve, average_precision_score  # noqa

    y_true_arr = np.asarray(y_true, dtype=int)
    y_score_arr = np.asarray(y_score, dtype=float)

    fig, ax = plt.subplots(figsize=(6, 5))

    if len(np.unique(y_true_arr)) < 2:
        ax.text(0.5, 0.5,
                "PR curve requires both positive and negative\nexamples in the test set.",
                ha="center", va="center", transform=ax.transAxes)
        ax.set_title("Precision–Recall Curve (insufficient test data)")
        fig.tight_layout()
        return _finish_figure(fig, output_path)

    precision, recall, _ = precision_recall_curve(y_true_arr, y_score_arr)
    auc_val = pr_auc if pr_auc is not None else float(average_precision_score(y_true_arr, y_score_arr))

    ax.step(recall, precision, where="post", color="tab:blue", linewidth=1.8,
            label=f"PR-AUC = {auc_val:.3f}")
    ax.fill_between(recall, precision, alpha=0.12, color="tab:blue", step="post")
    ax.set_xlim(0.0, 1.02)
    ax.set_ylim(0.0, 1.05)
    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision")
    ax.set_title(
        "Precision–Recall Curve (injection-trained ranker)\n"
        "Metrics on synthetic injections — not real-data purity"
    )
    ax.legend(loc="upper right")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    return _finish_figure(fig, output_path)


def plot_roc_curve(
    y_true,
    y_score,
    output_path=None,
    roc_auc: float | None = None,
):
    """Plot the receiver operating characteristic curve.

    ROC-AUC is computed on injection-recovery test rows.  It does NOT
    measure discrimination between real exocomet candidates and noise.
    """
    from sklearn.metrics import roc_curve, roc_auc_score  # noqa

    y_true_arr = np.asarray(y_true, dtype=int)
    y_score_arr = np.asarray(y_score, dtype=float)

    fig, ax = plt.subplots(figsize=(6, 5))

    if len(np.unique(y_true_arr)) < 2:
        ax.text(0.5, 0.5,
                "ROC curve requires both positive and negative\nexamples in the test set.",
                ha="center", va="center", transform=ax.transAxes)
        ax.set_title("ROC Curve (insufficient test data)")
        fig.tight_layout()
        return _finish_figure(fig, output_path)

    fpr, tpr, _ = roc_curve(y_true_arr, y_score_arr)
    auc_val = roc_auc if roc_auc is not None else float(roc_auc_score(y_true_arr, y_score_arr))

    ax.plot(fpr, tpr, color="tab:blue", linewidth=1.8, label=f"ROC-AUC = {auc_val:.3f}")
    ax.plot([0, 1], [0, 1], "k--", linewidth=0.8, alpha=0.5)
    ax.set_xlim(0.0, 1.02)
    ax.set_ylim(0.0, 1.05)
    ax.set_xlabel("False positive rate")
    ax.set_ylabel("True positive rate")
    ax.set_title(
        "ROC Curve (injection-trained ranker)\n"
        "Metrics on synthetic injections — not real-data purity"
    )
    ax.legend(loc="lower right")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    return _finish_figure(fig, output_path)


def plot_candidate_score_distribution(
    candidate_df: pd.DataFrame,
    output_path=None,
    score_col: str = "final_candidate_score",
):
    """Plot the distribution of final candidate ranking scores.

    Candidates flagged as edge_event or single_point_like are shown in a
    different colour to highlight their reduced weight in the ranking.

    The x-axis is the composite ranking score; it is NOT a probability of
    confirming an exocomet.
    """
    fig, ax = plt.subplots(figsize=(8, 4))

    if candidate_df is None or candidate_df.empty or score_col not in candidate_df.columns:
        ax.text(0.5, 0.5,
                "No scored candidates available.\n"
                "Run train_event_ranker.py with a non-empty candidate table.",
                ha="center", va="center", transform=ax.transAxes)
        ax.set_title("Candidate ranking score distribution (no data)")
        fig.tight_layout()
        return _finish_figure(fig, output_path)

    scores = pd.to_numeric(candidate_df[score_col], errors="coerce").dropna()
    if scores.empty:
        ax.text(0.5, 0.5, "All scores are NaN.", ha="center", va="center",
                transform=ax.transAxes)
        fig.tight_layout()
        return _finish_figure(fig, output_path)

    edge_col = "edge_event" if "edge_event" in candidate_df.columns else None
    single_col = "single_point_like" if "single_point_like" in candidate_df.columns else None

    flagged = pd.Series(False, index=candidate_df.index)
    if edge_col:
        flagged |= candidate_df[edge_col].astype(bool)
    if single_col:
        flagged |= candidate_df[single_col].astype(bool)

    good_scores = candidate_df.loc[~flagged, score_col].dropna() if flagged.any() else scores
    bad_scores = candidate_df.loc[flagged, score_col].dropna() if flagged.any() else pd.Series(dtype=float)

    bins = np.linspace(0.0, 1.0, 15)

    if not good_scores.empty:
        ax.hist(good_scores, bins=bins, alpha=0.75, color="tab:blue",
                label=f"Clean ({len(good_scores)})")
    if not bad_scores.empty:
        ax.hist(bad_scores, bins=bins, alpha=0.65, color="tab:orange",
                label=f"Flagged edge/single-pt ({len(bad_scores)})")

    ax.set_xlabel(f"{score_col}")
    ax.set_ylabel("Candidate count")
    ax.set_title(
        "Candidate ranking score distribution\n"
        "(Score ranks review priority — not confirmation probability)"
    )
    if flagged.any():
        ax.legend(loc="best")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    return _finish_figure(fig, output_path)


def _plot_example_panel(ax, t_arr, f_arr, row, window_days, label, color):
    event_time = float(row.get("injected_event_time_btjd", np.nan))
    if not np.isfinite(event_time):
        ax.set_axis_off()
        return
    half = window_days / 2.0
    mask = (t_arr >= event_time - half) & (t_arr <= event_time + half)
    ax.plot(t_arr[mask], f_arr[mask], "k.-", markersize=2, alpha=0.6)
    ax.axvline(event_time, color=color, linestyle="--", linewidth=1.1)
    depth = row.get("injected_depth_ppm", np.nan)
    title = f"{label}\n{float(depth):.0f} ppm" if np.isfinite(float(depth)) else label
    ax.set_title(title, fontsize=8, color=color)
    ax.set_xlabel("BTJD", fontsize=7)
    ax.set_ylabel("Flux", fontsize=7)
    ax.grid(alpha=0.2)
    ax.tick_params(labelsize=7)


def plot_target_control_balance(target_df, control_df, columns, output_path=None):
    """Plot side-by-side target/control numeric distributions."""
    available_columns = []
    for column in columns:
        if column not in target_df.columns or column not in control_df.columns:
            continue
        target_values = pd.to_numeric(target_df[column], errors="coerce").dropna()
        control_values = pd.to_numeric(control_df[column], errors="coerce").dropna()
        if len(target_values) > 0 and len(control_values) > 0:
            available_columns.append(column)

    n_panels = max(1, len(available_columns))
    fig, axes = plt.subplots(n_panels, 1, figsize=(8, 3.2 * n_panels))
    axes = np.atleast_1d(axes)

    if not available_columns:
        axes[0].text(
            0.5,
            0.5,
            "No shared numeric balance columns available",
            ha="center",
            va="center",
            transform=axes[0].transAxes,
        )
        axes[0].set_axis_off()
    else:
        for ax, column in zip(axes, available_columns):
            target_values = pd.to_numeric(target_df[column], errors="coerce").dropna()
            control_values = pd.to_numeric(control_df[column], errors="coerce").dropna()
            ax.hist(
                target_values,
                bins=min(12, max(3, len(target_values))),
                alpha=0.6,
                label="Targets",
                color="tab:blue",
            )
            ax.hist(
                control_values,
                bins=min(12, max(3, len(control_values))),
                alpha=0.6,
                label="Controls",
                color="tab:orange",
            )
            ax.set_title(f"Target/Control Balance: {column}")
            ax.set_xlabel(column)
            ax.set_ylabel("Count")
            ax.grid(alpha=0.25)
            ax.legend(loc="best")

    fig.tight_layout()
    return _finish_figure(fig, output_path)
