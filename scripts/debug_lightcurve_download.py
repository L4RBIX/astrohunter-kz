#!/usr/bin/env python3
"""Diagnostic script for TESS light-curve download failures.

Prints full tracebacks, dependency versions, sys.path, and search/download
results so that the exact failure point can be identified.

Usage:
    python scripts/debug_lightcurve_download.py --tic-id 368404959 --verbose
"""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

# Ensure the src package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Diagnose TESS light-curve download failures for a TIC ID.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--tic-id", required=True, type=int,
                   help="TIC ID to diagnose.")
    p.add_argument("--max-lightcurves", type=int, default=1,
                   help="Maximum number of products to attempt downloading.")
    p.add_argument("--author-preference", nargs="+",
                   default=["SPOC", "QLP"],
                   help="Pipeline authors to try first.")
    p.add_argument("--verbose", action="store_true",
                   help="Print extended sys.path and additional details.")
    return p.parse_args(argv)


def _print_sep(label: str = "") -> None:
    if label:
        print(f"\n{'=' * 20} {label} {'=' * 20}")
    else:
        print("=" * 60)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    _print_sep("ENVIRONMENT")
    print(f"Python executable : {sys.executable}")
    print(f"Python version    : {sys.version}")
    print(f"TIC ID            : {args.tic_id}")
    print(f"Max lightcurves   : {args.max_lightcurves}")
    print(f"Author preference : {args.author_preference}")

    if args.verbose:
        _print_sep("SYS.PATH")
        for i, p in enumerate(sys.path[:20]):
            print(f"  [{i:2d}] {p}")
        if len(sys.path) > 20:
            print(f"  ... and {len(sys.path) - 20} more entries")

    # ------------------------------------------------------------------ lightkurve
    _print_sep("LIGHTKURVE IMPORT")
    lk = None
    try:
        import lightkurve as lk
        print(f"lightkurve version: {lk.__version__}")
        print("lightkurve import: OK")
    except Exception:
        print("lightkurve import FAILED:")
        traceback.print_exc()
        print("\nCannot continue — fix lightkurve import first.")
        return 2

    # ------------------------------------------------------------------ astroquery
    _print_sep("ASTROQUERY IMPORT")
    try:
        import astroquery
        print(f"astroquery version: {astroquery.__version__}")
        print("astroquery import: OK")
    except Exception:
        print("astroquery import FAILED:")
        traceback.print_exc()

    # ------------------------------------------------------------------ search
    _print_sep("MAST SEARCH")
    target_str = f"TIC {args.tic_id}"
    search_result = None

    for author in args.author_preference + [None]:
        label = author or "any"
        print(f"\nSearching: {target_str!r}  author={label!r} …")
        try:
            kwargs = {"mission": "TESS"}
            if author is not None:
                kwargs["author"] = author
            sr = lk.search_lightcurve(target_str, **kwargs)
            n = len(sr) if sr is not None else 0
            print(f"  → {n} product(s) found.")
            if n > 0:
                search_result = sr
                print("  Products:")
                for row in sr.table[:5]:
                    exp = row.get("exptime", "?")
                    mission = row.get("mission", "?")
                    print(f"    {mission}  exptime={exp}s")
                if n > 5:
                    print(f"    ... and {n - 5} more")
                break
        except Exception:
            print(f"  Search FAILED (author={label!r}):")
            traceback.print_exc()

    if search_result is None or len(search_result) == 0:
        print(f"\nNo products found for TIC {args.tic_id}.")
        print("Possible causes: star not in TESS footprint, network issue, MAST outage.")
        return 1

    # ------------------------------------------------------------------ download
    _print_sep("DOWNLOAD")
    n_download = min(args.max_lightcurves, len(search_result))
    print(f"Attempting to download {n_download} product(s) …")
    collection = None
    try:
        collection = search_result[:n_download].download_all()
        n_lc = len(collection) if collection is not None else 0
        print(f"Download: OK — {n_lc} light curve(s) returned.")
    except Exception:
        print("Download FAILED:")
        traceback.print_exc()
        return 1

    if collection is None or len(collection) == 0:
        print("Download returned no light curves.")
        return 1

    # ------------------------------------------------------------------ inspect
    _print_sep("LIGHT CURVE INSPECTION")
    for i, lc in enumerate(collection):
        print(f"\n  LC {i + 1}:")
        print(f"    type        : {type(lc).__name__}")
        print(f"    label       : {getattr(lc, 'label', '?')}")
        try:
            t = lc.time.value if hasattr(lc.time, "value") else lc.time
            f = lc.flux.value if hasattr(lc.flux, "value") else lc.flux
            import numpy as np
            finite_t = np.isfinite(t).sum()
            finite_f = np.isfinite(f).sum()
            print(f"    n_points    : {len(t)}  ({finite_t} finite time, {finite_f} finite flux)")
        except Exception as exc:
            print(f"    inspection failed: {exc}")

    # ------------------------------------------------------------------ cache path
    _print_sep("CACHE PATH")
    cache_dir = Path("cache/lightcurves")
    cache_path = cache_dir / f"tic_{args.tic_id}.parquet"
    print(f"Cache dir : {cache_dir.resolve()}")
    print(f"Cache file: {cache_path}")
    print(f"Exists    : {cache_path.exists()}")

    _print_sep("RESULT")
    print(f"TIC {args.tic_id}: download appears successful.")
    print("If the full pipeline still fails, re-run with --verbose and check")
    print("the MAST SEARCH section for product details.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
