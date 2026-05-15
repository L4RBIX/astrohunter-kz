#!/usr/bin/env python
"""Build Phase 2 development target/control catalog files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from astrohunter.catalogs import (
    build_clean_target_table,
    build_target_sample,
    crossmatch_targets_with_gaia,
    crossmatch_targets_with_tic,
    enrich_targets_with_basic_gaia_like_columns,
    enrich_targets_with_tess_availability,
    normalize_control_pool_columns,
    save_catalog,
)
from astrohunter.crossmatch import match_controls_to_targets
from astrohunter.plotting import plot_target_control_balance


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build small real Phase 2 development catalogs from public VizieR "
            "debris-disk / IR-excess sources."
        )
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Build a lightweight development sample.",
    )
    parser.add_argument("--max-targets", type=int, default=20)
    parser.add_argument("--output-dir", default="catalogs")
    parser.add_argument("--enrich-tess", action="store_true")
    parser.add_argument("--max-enrich-targets", type=int, default=None)
    parser.add_argument("--build-controls", action="store_true")
    parser.add_argument("--control-ratio", type=int, default=3)
    parser.add_argument("--control-pool-csv", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-remote", action="store_true")
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--crossmatch-tic", action="store_true")
    parser.add_argument("--crossmatch-gaia", action="store_true")
    parser.add_argument("--max-crossmatch-targets", type=int, default=None)
    return parser.parse_args()


def _load_or_prepare_control_pool(args: argparse.Namespace, output_dir: Path) -> pd.DataFrame:
    source_path = None
    if args.control_pool_csv:
        source_path = Path(args.control_pool_csv)
    elif (output_dir / "control_pool.csv").exists():
        source_path = output_dir / "control_pool.csv"

    if source_path is None:
        print(
            "Warning: no real control pool was provided. Use --control-pool-csv "
            "or create catalogs/control_pool.csv from real TIC/Gaia/MAST metadata. "
            "See docs/CONTROL_POOL_GUIDE.md."
        )
        return pd.DataFrame()

    if not source_path.exists():
        print(f"Warning: requested control pool does not exist: {source_path}")
        return pd.DataFrame()

    print(f"Loading real control pool from {source_path}")
    pool = normalize_control_pool_columns(pd.read_csv(source_path))
    return pool


def _write_optional_controls(
    targets: pd.DataFrame,
    output_dir: Path,
    args: argparse.Namespace,
) -> None:
    """Attempt control-sample output only when a real pool is available."""
    candidate_pool = _load_or_prepare_control_pool(args, output_dir)
    if candidate_pool.empty:
        return

    controls, pairs = match_controls_to_targets(
        targets,
        candidate_pool,
        control_ratio=args.control_ratio,
    )

    if controls.empty or pairs.empty:
        print(
            "Warning: matched controls were not written because no real controls "
            "satisfied the available matching criteria."
        )
        return

    if args.dry_run:
        print(
            f"Dry run: would save {len(candidate_pool)} control-pool rows, "
            f"{len(controls)} controls, and {len(pairs)} matched pairs."
        )
        return

    control_pool_path = save_catalog(candidate_pool, output_dir / "control_pool.csv")
    control_path = save_catalog(controls, output_dir / "control_sample.csv")
    pairs_path = save_catalog(pairs, output_dir / "matched_pairs.csv")
    print(f"Saved control pool: {control_pool_path}")
    print(f"Saved controls: {control_path}")
    print(f"Saved matched pairs: {pairs_path}")

    balance_columns = ["tmag", "bp_rp", "teff", "parallax", "n_tess_products"]
    fig = plot_target_control_balance(
        targets,
        controls,
        balance_columns,
        output_path=Path("results") / "figures" / "target_control_balance.png",
    )
    plt.close(fig)
    print("Saved balance figure: results/figures/target_control_balance.png")


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("AstroHunter KZ Phase 2 catalog builder")
    print("This builds preliminary development samples, not final science catalogs.")
    print(f"dev mode: {args.dev}")
    print(f"max targets: {args.max_targets}")
    print(f"output dir: {output_dir}")
    print(f"skip remote: {args.skip_remote}")

    if args.skip_remote and (output_dir / "target_sample.csv").exists():
        print(f"Loading existing target sample: {output_dir / 'target_sample.csv'}")
        targets = pd.read_csv(output_dir / "target_sample.csv")
    elif args.skip_remote:
        print("Warning: --skip-remote requested and no target_sample.csv exists.")
        targets = pd.DataFrame()
    else:
        targets = build_target_sample(dev=args.dev, max_targets=args.max_targets)

    target_path = output_dir / "target_sample.csv"
    if args.dry_run:
        print(f"Dry run: would save target sample to {target_path}")
    else:
        target_path = save_catalog(targets, target_path)

    print("\nTarget sample summary")
    print(f"  rows: {len(targets)}")
    if "source_catalog" in targets.columns and not targets.empty:
        counts = targets["source_catalog"].value_counts(dropna=False)
        for source, count in counts.items():
            print(f"  {source}: {count}")
    print(f"  saved target sample: {target_path}")

    if args.enrich_tess:
        enriched = enrich_targets_with_basic_gaia_like_columns(targets)
        if args.skip_remote:
            print("Warning: --skip-remote set; TESS availability search skipped.")
            enriched["tess_query_status"] = "skipped_remote_disabled"
        else:
            enriched = enrich_targets_with_tess_availability(
                enriched,
                max_targets=args.max_enrich_targets,
            )
        enriched_path = output_dir / "target_sample_enriched.csv"
        if args.dry_run:
            print(f"Dry run: would save enriched target sample to {enriched_path}")
        else:
            enriched_path = save_catalog(enriched, enriched_path)
        targets = enriched
        print(f"  saved enriched target sample: {enriched_path}")

    if args.crossmatch_tic:
        if args.skip_remote:
            print("Warning: --skip-remote set; TIC crossmatch skipped.")
            targets["tic_query_status"] = "not_attempted"
        else:
            targets = crossmatch_targets_with_tic(
                targets,
                max_targets=args.max_crossmatch_targets,
            )
            if not args.dry_run:
                save_catalog(targets, output_dir / "target_sample_enriched.csv")

    if args.crossmatch_gaia:
        if args.skip_remote:
            print("Warning: --skip-remote set; Gaia crossmatch skipped.")
            targets["gaia_query_status"] = "not_attempted"
        else:
            targets = crossmatch_targets_with_gaia(
                targets,
                max_targets=args.max_crossmatch_targets,
            )
            if not args.dry_run:
                save_catalog(targets, output_dir / "target_sample_enriched.csv")

    if args.clean:
        clean = build_clean_target_table(targets)
        clean_path = output_dir / "target_sample_clean.csv"
        if args.dry_run:
            print(f"Dry run: would save clean target sample to {clean_path}")
        else:
            clean_path = save_catalog(clean, clean_path)
        print(f"  saved clean target sample: {clean_path}")

    if args.build_controls:
        _write_optional_controls(targets, output_dir, args)
    else:
        print(
            "Control matching not requested. Use --build-controls with a real "
            "--control-pool-csv or catalogs/control_pool.csv."
        )

    print(
        "\nScientific caution: Phase 2/2B target/control files are preliminary "
        "development samples. They are not candidate-event results and do not "
        "claim confirmed exocomet discovery."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
