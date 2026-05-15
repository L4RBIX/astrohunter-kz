# Control Pool Guide

Phase 2B does not fabricate matched controls. A real control pool must come from
TIC/Gaia/MAST metadata or another documented public source, with IR-excess /
debris-disk targets excluded.

## Required Columns

Provide a CSV with these columns, or obvious aliases that the normalizer can map:

- `tic_id`
- `ra_deg`
- `dec_deg`
- `tmag`
- `bp_rp` or `teff`
- `parallax`
- `n_tess_products`
- `has_tess_lightcurve`
- `ir_excess_flag`

`ir_excess_flag` must be `False` for candidate controls. Rows with
`has_tess_lightcurve != True` are not useful for matched TESS searches.

## How To Obtain A Real Pool

One valid workflow is:

1. Query TIC for stars in the same broad sky/sector/magnitude regime as the
   target sample.
2. Crossmatch those TIC rows to Gaia DR3 for parallax and color/temperature
   metadata.
3. Remove known debris-disk / IR-excess sources using the Phase 2 target catalogs
   and any additional IR-excess flags.
4. Use MAST/lightkurve metadata searches to count TESS light-curve products.
5. Save the resulting non-disk pool as CSV.

Large survey-scale pulls should be kept outside Git. Commit only small
development pools when they are documented and reproducible.

## Normalize A User CSV

```bash
python scripts/build_control_pool_from_user_csv.py path/to/user_control_pool.csv \
  --output catalogs/control_pool.csv
```

## Build Matched Controls

```bash
python scripts/build_catalogs.py \
  --dev \
  --max-targets 20 \
  --output-dir catalogs \
  --enrich-tess \
  --max-enrich-targets 20 \
  --build-controls \
  --control-ratio 3 \
  --control-pool-csv catalogs/control_pool.csv
```

If the pool is missing `tmag`, `bp_rp`/`teff`, or `parallax`, the matcher skips
that criterion with a warning. If no controls satisfy the available criteria, it
does not write `control_sample.csv` or `matched_pairs.csv`.
