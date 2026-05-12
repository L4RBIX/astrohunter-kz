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
