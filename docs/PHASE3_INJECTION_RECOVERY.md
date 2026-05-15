# Phase 3: Injection-Recovery and Improved Asymmetric-Dip Detector

## Purpose

Phase 3 builds a reproducible injection-recovery framework to evaluate the
sensitivity of the Phase 3 improved asymmetric-dip detector.  It does NOT:

- claim real exocomet detections,
- measure the purity of real candidate events,
- confirm astrophysical signals in any TESS light curve.

All results in `results/tables/injection_recovery.csv` are sensitivity metrics
on *synthetic* signals of known amplitude injected into real TESS noise.

---

## What Injection-Recovery Means

A synthetic exocomet-like asymmetric dip of known depth, ingress duration, and
egress duration is injected at a random time into a real TESS light curve.  The
detector is then run on the injected light curve.  If the detector reports an
event within `tolerance_hours` of the injected event time, the injection is
counted as recovered.

The recovery fraction as a function of depth tells you: **given this noise level
and detector threshold, what fraction of synthetic signals can the pipeline find?**

It does not tell you how many real events the detector missed or what fraction
of real detections are genuine astrophysical events.

---

## Dip Model

The injected dip profile is a piecewise linear (triangular) asymmetric shape:

- **Ingress**: linear ramp from flux = 1 down to the dip minimum over
  `ingress_duration_hours`.
- **Egress**: linear ramp from the dip minimum back to flux = 1 over
  `egress_duration_hours`.

Egress is biased to be longer than ingress to mimic exocomet dust-tail geometry.

Parameter ranges:
- Depth: 50–5000 ppm (uniform)
- Ingress: 0.5–8 hours (uniform)
- Egress: ingress × log-uniform ratio in [1.2, 8], capped at 24 hours

---

## Improved Detector (scan_lightcurve_for_asymmetric_dips)

The Phase 3 detector extends the Phase 1 simple dip finder with:

| Feature | Description |
|---------|-------------|
| `depth_ppm` | Dip depth in parts per million |
| `local_snr` | Depth / local MAD noise |
| `fwhm_hours` | Full-width at half-maximum (linear interpolation) |
| `ingress_duration_hours` | Time from half-depth to minimum |
| `egress_duration_hours` | Time from minimum to half-depth |
| `egress_ingress_ratio` | Asymmetry proxy (>1 = comet-like) |
| `skewness` | Skewness of local flux window |
| `kurtosis` | Kurtosis of local flux window |
| `delta_chi2_asym` | χ²(symmetric) − χ²(asymmetric); positive = asymmetric fits better |
| `n_points_window` | Number of flux points in the analysis window |
| `edge_event` | True if near the light-curve edge |
| `single_point_like` | True if fewer than 2 points are below half-depth |
| `detector_version` | `phase3_v1` |

---

## Output Files

| File | Description |
|------|-------------|
| `results/tables/injection_recovery.csv` | Per-injection ground truth and recovery result |
| `results/tables/detector_candidate_events_dev.csv` | Real-data candidate scan (dev subset) |
| `results/figures/recovery_vs_depth.png` | Recovery fraction vs. injected depth |
| `results/figures/recovery_heatmap_depth_duration.png` | Recovery heatmap (depth × egress duration) |
| `results/figures/example_injected_dip.png` | Example synthetic dip superimposed on real LC |

---

## Running Phase 3

### Injection-recovery (dev subset, fast)

```bash
python scripts/run_injection_recovery.py \
  --sample catalogs/matched_pairs.csv \
  --target-catalog catalogs/target_sample_enriched.csv \
  --control-pool catalogs/control_pool.csv \
  --n-lightcurves 4 \
  --n-injections 40 \
  --max-lightcurves-per-star 1 \
  --random-seed 42
```

### Real-data scan (dev subset, 5 targets)

```bash
python scripts/run_scan.py \
  --sample catalogs/target_sample_enriched.csv \
  --max-targets 5 \
  --max-lightcurves-per-star 1 \
  --output results/tables/detector_candidate_events_dev.csv \
  --sigma-threshold 4.0 \
  --window-days 1.0
```

---

## Cache

Downloaded and processed light curves are saved as parquet files in
`cache/lightcurves/tic_{tic_id}.parquet`.  The cache directory is excluded
from git tracking.  Subsequent runs load from cache and skip re-downloading.

To force a re-download, delete the relevant `.parquet` file.

---

## Claims Policy

The injection-recovery fraction is a *pipeline sensitivity metric*, not a
statement about the rate of real exocomet events.  The real-data scan
candidates require:

1. Quality-flag filtering (TESS DQMASK)
2. Multi-sector consistency check
3. Stellar context (spectral type, known variability)
4. Instrumental systematics comparison
5. Community vetting

See also: `docs/CLAIMS_POLICY.md` and `docs/PROJECT_SCOPE.md`.

---

## Phase 4 Readiness

Phase 3 outputs are designed to feed the Phase 4 ML ranker:

- `injection_recovery.csv` provides labelled training examples
  (recovered=True/False) with feature columns aligned to the detector output.
- `detector_candidate_events_dev.csv` provides unlabelled real-data candidates
  with the same feature columns.
- The `delta_chi2_asym`, `egress_ingress_ratio`, and `local_snr` columns are
  strong Phase 4 discriminating features.

Phase 4 should NOT use the injection-recovery recovered fraction as a
direct estimate of real-event purity without additional calibration.
