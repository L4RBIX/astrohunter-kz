# Reproducibility

Phase 1 is designed to run from a clean clone without private API keys.

```bash
git clone https://github.com/L4RBIX/astrohunter-kz.git
cd astrohunter-kz
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Run the tests:

```bash
python -m pytest
```

Run the beta Pic positive-control pipeline:

```bash
python scripts/run_beta_pic_control.py --max-lightcurves 1
```

Build the Phase 2 development target catalog:

```bash
python scripts/build_catalogs.py --dev --max-targets 20 --output-dir catalogs
```

Build the Phase 2B TESS-enriched target catalog:

```bash
python scripts/build_catalogs.py \
  --dev \
  --max-targets 20 \
  --output-dir catalogs \
  --enrich-tess \
  --max-enrich-targets 20
```

Build the Phase 2C clean derived target table:

```bash
python scripts/build_catalogs.py \
  --dev \
  --max-targets 20 \
  --output-dir catalogs \
  --enrich-tess \
  --max-enrich-targets 20 \
  --clean
```

Verify a catalog:

```bash
python scripts/verify_catalogs.py --catalog catalogs/target_sample_enriched.csv
```

Normalize a real user-provided control pool:

```bash
python scripts/build_control_pool_from_user_csv.py path/to/user_control_pool.csv \
  --output catalogs/control_pool.csv
```

Attempt matched controls only after a real non-disk control pool exists:

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

Expected Phase 1 outputs:

- `results/figures/beta_pic_full_lightcurve.png`
- `results/figures/beta_pic_zoom_strongest_dip.png`
- `results/figures/beta_pic_lightcurve_with_detected_dips.png`
- `results/tables/beta_pic_candidate_dips.csv`

The script downloads public TESS light curves through `lightkurve`/MAST. Network
availability, MAST service state, and upstream archive product changes can affect
runtime and exact search-result ordering. Use `--max-lightcurves 1` for the
default lightweight positive-control run.

The generated candidate table contains candidate dip-like features only. It is
not a confirmed exocomet catalog.

The generated catalog files are preliminary development samples. Control files
are written only when a real non-disk control pool is available; missing control
outputs should not be interpreted as a completed matched-sample analysis.
