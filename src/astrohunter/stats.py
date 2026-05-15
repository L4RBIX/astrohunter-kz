"""Phase 5 candidate-yield rate statistics for AstroHunter KZ.

Computes preliminary target/control candidate-yield rate ratios from
vetted candidate tables and matched-pair catalogs.

SCIENTIFIC CONSTRAINTS:
- Dev-sample statistics are preliminary and unstable with N < 10 candidates.
- Rate ratios are estimated from a small development scan, not a full survey.
- Confidence intervals assume Poisson counting statistics.
- Bootstrap CIs on small samples (N < 5) are unreliable.
- These statistics do not constitute a scientific claim.
- All results require validation on a full survey sample.
"""

from __future__ import annotations

import logging
import warnings
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

logger = logging.getLogger(__name__)

STATS_VERSION = "phase5_v1"

# Minimum candidates for rate statistics to be considered stable
MIN_CANDIDATES_FOR_STABLE_STATS = 10


# ---------------------------------------------------------------------------
# Exposure estimation
# ---------------------------------------------------------------------------

def _estimate_exposure_from_pairs(
    matched_pairs_df: pd.DataFrame,
    role: str,
) -> float:
    """Estimate relative exposure (star-count proxy) for a role.

    Without full-survey lightcurve duration data, star count is used as a
    proxy for exposure.  This is an approximation; real exposure requires
    per-star lightcurve baseline lengths.

    Parameters
    ----------
    matched_pairs_df:
        matched_pairs.csv with columns target_tic_id, control_tic_id.
    role:
        "target" or "control".

    Returns
    -------
    float
        Number of unique stars of the given role in the matched-pairs catalog.
    """
    if matched_pairs_df is None or matched_pairs_df.empty:
        return 1.0

    if role == "target":
        col = "target_tic_id"
    elif role == "control":
        col = "control_tic_id"
    else:
        raise ValueError(f"role must be 'target' or 'control', got {role!r}")

    if col not in matched_pairs_df.columns:
        return 1.0

    return float(matched_pairs_df[col].nunique())


# ---------------------------------------------------------------------------
# Core rate functions
# ---------------------------------------------------------------------------

def poisson_confidence_interval(
    count: int,
    exposure: float = 1.0,
    confidence: float = 0.95,
) -> tuple[float, float]:
    """Return Poisson confidence interval for an observed count.

    Uses the exact Garwood interval (chi-squared method).

    Parameters
    ----------
    count:
        Observed event count (non-negative integer).
    exposure:
        Exposure (star-count proxy or observation time).  Rate = count/exposure.
    confidence:
        Confidence level (default 0.95).

    Returns
    -------
    (lower_rate, upper_rate)
        Lower and upper rate bounds.

    Notes
    -----
    When count = 0, the lower bound is 0.  The upper bound is derived from
    the chi-squared CDF.  Intervals on counts < 5 are wide and unreliable.
    """
    alpha = 1.0 - confidence
    if count == 0:
        lower = 0.0
        upper = scipy_stats.chi2.ppf(1.0 - alpha / 2.0, df=2) / 2.0
    else:
        lower = scipy_stats.chi2.ppf(alpha / 2.0, df=2 * count) / 2.0
        upper = scipy_stats.chi2.ppf(1.0 - alpha / 2.0, df=2 * (count + 1)) / 2.0

    return float(lower / exposure), float(upper / exposure)


def compute_rate_ratio(
    target_count: int,
    target_exposure: float,
    control_count: int,
    control_exposure: float,
) -> dict[str, float]:
    """Compute candidate yield rate and rate ratio with asymmetric Poisson CIs.

    Parameters
    ----------
    target_count, control_count:
        Observed candidate counts for target and control samples.
    target_exposure, control_exposure:
        Exposure (star-count proxy) for each sample.

    Returns
    -------
    dict
        Keys: target_rate, control_rate, rate_ratio, plus CI bounds.

    Notes
    -----
    Rate ratio = (target_count / target_exposure) / (control_count / control_exposure).
    When control_count = 0, rate_ratio is NaN (undefined).
    """
    target_exposure = max(target_exposure, 1e-9)
    control_exposure = max(control_exposure, 1e-9)

    target_rate = target_count / target_exposure
    control_rate = control_count / control_exposure

    t_lo, t_hi = poisson_confidence_interval(target_count, target_exposure)
    c_lo, c_hi = poisson_confidence_interval(control_count, control_exposure)

    if control_rate > 0:
        rate_ratio = target_rate / control_rate
        rr_lo = t_lo / (c_hi if c_hi > 0 else 1e-9)
        rr_hi = (t_hi if t_hi > 0 else 0.0) / max(c_lo, 1e-9)
    else:
        rate_ratio = float("nan")
        rr_lo = float("nan")
        rr_hi = float("nan")

    return {
        "target_count": target_count,
        "target_exposure": target_exposure,
        "target_rate": target_rate,
        "target_rate_ci_lo": t_lo,
        "target_rate_ci_hi": t_hi,
        "control_count": control_count,
        "control_exposure": control_exposure,
        "control_rate": control_rate,
        "control_rate_ci_lo": c_lo,
        "control_rate_ci_hi": c_hi,
        "rate_ratio": rate_ratio,
        "rate_ratio_ci_lo": rr_lo,
        "rate_ratio_ci_hi": rr_hi,
    }


# ---------------------------------------------------------------------------
# Role assignment
# ---------------------------------------------------------------------------

def compute_candidate_yield_by_role(
    candidate_df: pd.DataFrame,
    matched_pairs_df: pd.DataFrame,
) -> dict[str, Any]:
    """Count candidates by target/control role using matched-pairs membership.

    Matches candidate tic_ids against target_tic_id and control_tic_id lists
    from matched_pairs.csv.  Candidates not in either list are labelled "unknown".

    Parameters
    ----------
    candidate_df:
        Vetted candidate event DataFrame.
    matched_pairs_df:
        matched_pairs.csv DataFrame.

    Returns
    -------
    dict
        Keys: target_candidates, control_candidates, unknown_candidates,
        target_exposure, control_exposure, candidate_tic_ids_target,
        candidate_tic_ids_control.
    """
    if matched_pairs_df is None or matched_pairs_df.empty:
        logger.warning("matched_pairs_df is empty; cannot assign candidate roles.")
        n = len(candidate_df)
        return {
            "target_candidates": n,
            "control_candidates": 0,
            "unknown_candidates": 0,
            "target_exposure": 1.0,
            "control_exposure": 1.0,
            "candidate_tic_ids_target": [],
            "candidate_tic_ids_control": [],
        }

    target_tics = set(matched_pairs_df["target_tic_id"].dropna().astype(int))
    control_tics = set(matched_pairs_df["control_tic_id"].dropna().astype(int))

    if "tic_id" not in candidate_df.columns:
        logger.warning("'tic_id' column absent from candidate table.")
        n = len(candidate_df)
        return {
            "target_candidates": n,
            "control_candidates": 0,
            "unknown_candidates": 0,
            "target_exposure": float(len(target_tics) or 1),
            "control_exposure": float(len(control_tics) or 1),
            "candidate_tic_ids_target": [],
            "candidate_tic_ids_control": [],
        }

    tic_ids = pd.to_numeric(candidate_df["tic_id"], errors="coerce").dropna().astype(int)

    in_target = tic_ids[tic_ids.isin(target_tics)]
    in_control = tic_ids[tic_ids.isin(control_tics)]
    n_unknown = int((~tic_ids.isin(target_tics | control_tics)).sum())

    target_exposure = _estimate_exposure_from_pairs(matched_pairs_df, "target")
    control_exposure = _estimate_exposure_from_pairs(matched_pairs_df, "control")

    return {
        "target_candidates": int(len(in_target)),
        "control_candidates": int(len(in_control)),
        "unknown_candidates": n_unknown,
        "target_exposure": target_exposure,
        "control_exposure": control_exposure,
        "candidate_tic_ids_target": in_target.tolist(),
        "candidate_tic_ids_control": in_control.tolist(),
    }


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

def bootstrap_rate_ratio(
    candidate_df: pd.DataFrame,
    matched_pairs_df: pd.DataFrame,
    n_bootstrap: int = 1000,
    random_state: int = 42,
    confidence: float = 0.95,
) -> dict[str, Any]:
    """Bootstrap confidence interval for the target/control rate ratio.

    Resamples the candidate table with replacement and recomputes the rate
    ratio on each bootstrap replicate.

    IMPORTANT: Bootstrap CIs on very small samples (< 5 candidates per
    group) are unreliable.  Results must be interpreted with caution.

    Parameters
    ----------
    candidate_df:
        Vetted candidate event DataFrame.
    matched_pairs_df:
        matched_pairs.csv DataFrame.
    n_bootstrap:
        Number of bootstrap replicates.
    random_state:
        RNG seed for reproducibility.
    confidence:
        Confidence level for the percentile CI.

    Returns
    -------
    dict
        Keys: bootstrap_rate_ratio_median, bootstrap_ci_lo, bootstrap_ci_hi,
        n_bootstrap, n_finite_replicates, stability_warning.
    """
    rng = np.random.default_rng(random_state)
    n = len(candidate_df)

    if n == 0:
        return {
            "bootstrap_rate_ratio_median": float("nan"),
            "bootstrap_ci_lo": float("nan"),
            "bootstrap_ci_hi": float("nan"),
            "n_bootstrap": n_bootstrap,
            "n_finite_replicates": 0,
            "stability_warning": "No candidates — bootstrap not possible.",
        }

    # Determine exposures from the full catalog (fixed across replicates)
    yields = compute_candidate_yield_by_role(candidate_df, matched_pairs_df)
    t_exp = yields["target_exposure"]
    c_exp = yields["control_exposure"]

    target_tics = (
        set(matched_pairs_df["target_tic_id"].dropna().astype(int))
        if matched_pairs_df is not None and not matched_pairs_df.empty
        else set()
    )
    control_tics = (
        set(matched_pairs_df["control_tic_id"].dropna().astype(int))
        if matched_pairs_df is not None and not matched_pairs_df.empty
        else set()
    )

    tic_array = (
        pd.to_numeric(candidate_df["tic_id"], errors="coerce").fillna(-1).astype(int).values
        if "tic_id" in candidate_df.columns
        else np.full(n, -1, dtype=int)
    )

    ratios: list[float] = []
    for _ in range(n_bootstrap):
        boot_idx = rng.integers(0, n, size=n)
        boot_tics = tic_array[boot_idx]
        t_count = int(np.isin(boot_tics, list(target_tics)).sum())
        c_count = int(np.isin(boot_tics, list(control_tics)).sum())
        t_rate = t_count / max(t_exp, 1e-9)
        c_rate = c_count / max(c_exp, 1e-9)
        if c_rate > 0:
            ratios.append(t_rate / c_rate)
        else:
            ratios.append(float("nan"))

    finite = [r for r in ratios if np.isfinite(r)]
    n_finite = len(finite)

    alpha = 1.0 - confidence
    if n_finite >= 2:
        ci_lo = float(np.percentile(finite, 100 * alpha / 2))
        ci_hi = float(np.percentile(finite, 100 * (1.0 - alpha / 2)))
        median = float(np.median(finite))
    else:
        ci_lo = ci_hi = median = float("nan")

    total = len(candidate_df)
    t_count_obs = yields["target_candidates"]
    c_count_obs = yields["control_candidates"]
    stability_warning = None
    if total < MIN_CANDIDATES_FOR_STABLE_STATS:
        stability_warning = (
            f"Bootstrap CI unstable: only {total} total candidates "
            f"({t_count_obs} target, {c_count_obs} control). "
            "Results are highly preliminary. "
            "Rate statistics require a larger survey sample."
        )
        logger.warning(stability_warning)

    return {
        "bootstrap_rate_ratio_median": median,
        "bootstrap_ci_lo": ci_lo,
        "bootstrap_ci_hi": ci_hi,
        "n_bootstrap": n_bootstrap,
        "n_finite_replicates": n_finite,
        "stability_warning": stability_warning,
    }


# ---------------------------------------------------------------------------
# Fisher exact test
# ---------------------------------------------------------------------------

def fisher_exact_candidate_test(
    target_count: int,
    target_exposure: float,
    control_count: int,
    control_exposure: float,
) -> dict[str, Any]:
    """Fisher's exact test comparing target vs. control candidate counts.

    The test is applied to integer star-count proxies rounded from exposure
    values.  With very small counts, Fisher's test is conservative and
    p-values should be interpreted cautiously.

    Parameters
    ----------
    target_count, control_count:
        Observed candidate counts.
    target_exposure, control_exposure:
        Exposure (star-count proxy) for each sample.

    Returns
    -------
    dict
        Keys: odds_ratio, p_value_fisher, interpretation, caution.
    """
    t_exp_int = max(1, round(target_exposure))
    c_exp_int = max(1, round(control_exposure))

    t_no_cand = max(0, t_exp_int - target_count)
    c_no_cand = max(0, c_exp_int - control_count)

    table = [[target_count, t_no_cand], [control_count, c_no_cand]]

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        odds_ratio, p_value = scipy_stats.fisher_exact(table, alternative="two-sided")

    if p_value < 0.05:
        interpretation = "p < 0.05 (nominal significance; NOT confirmed with this sample size)"
    elif p_value < 0.10:
        interpretation = "p < 0.10 (marginal; not significant)"
    else:
        interpretation = "p >= 0.10 (no significant difference detected)"

    caution = (
        "Fisher's exact test on dev-sample counts is underpowered. "
        "p-values are not reliable for scientific claims. "
        "Full-survey data required."
    )

    return {
        "odds_ratio": float(odds_ratio),
        "p_value_fisher": float(p_value),
        "interpretation": interpretation,
        "caution": caution,
    }


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def summarize_rate_statistics(
    candidate_df: pd.DataFrame,
    matched_pairs_df: pd.DataFrame,
    n_bootstrap: int = 1000,
    random_state: int = 42,
    vetting_status_col: str = "automated_vetting_status",
    pass_value: str = "pass",
) -> pd.DataFrame:
    """Produce the full rate-ratio summary table.

    Computes rates for both the full candidate set and the post-vetting
    (automated_vetting_status == 'pass') subset.

    Parameters
    ----------
    candidate_df:
        Vetted candidate event DataFrame.
    matched_pairs_df:
        matched_pairs.csv DataFrame.
    n_bootstrap:
        Bootstrap replicates.
    random_state:
        RNG seed.
    vetting_status_col:
        Column name for automated vetting status.
    pass_value:
        Value indicating a passing candidate.

    Returns
    -------
    pd.DataFrame
        One row per subset (all_candidates, post_vetting_pass) with rate
        statistics columns.
    """
    rows: list[dict[str, Any]] = []

    subsets = {
        "all_candidates": candidate_df,
    }
    if vetting_status_col in candidate_df.columns:
        post_vet = candidate_df[candidate_df[vetting_status_col] == pass_value]
        subsets["post_vetting_pass"] = post_vet

    for subset_label, df_sub in subsets.items():
        total = len(df_sub)
        if total < MIN_CANDIDATES_FOR_STABLE_STATS:
            logger.warning(
                "[%s] Only %d candidate(s) — rate-ratio statistics are preliminary and unstable.",
                subset_label, total,
            )

        yields = compute_candidate_yield_by_role(df_sub, matched_pairs_df)
        t_count = yields["target_candidates"]
        c_count = yields["control_candidates"]
        t_exp = yields["target_exposure"]
        c_exp = yields["control_exposure"]

        rate_dict = compute_rate_ratio(t_count, t_exp, c_count, c_exp)
        fisher_dict = fisher_exact_candidate_test(t_count, t_exp, c_count, c_exp)
        boot_dict = bootstrap_rate_ratio(
            df_sub, matched_pairs_df,
            n_bootstrap=n_bootstrap,
            random_state=random_state,
        )

        row: dict[str, Any] = {
            "subset": subset_label,
            "total_candidates": total,
            "unknown_role_candidates": yields["unknown_candidates"],
            "stats_version": STATS_VERSION,
        }
        row.update(rate_dict)
        row.update(fisher_dict)
        row.update(boot_dict)

        if total < MIN_CANDIDATES_FOR_STABLE_STATS:
            row["preliminary_warning"] = (
                f"PRELIMINARY: only {total} candidates. "
                "Statistics are unstable. Full survey required."
            )
        else:
            row["preliminary_warning"] = None

        rows.append(row)

    return pd.DataFrame(rows)
