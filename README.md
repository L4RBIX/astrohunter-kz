# AstroHunter KZ

*A student-built pipeline for testing whether debris-disk / IR-excess stars produce more exocomet-like dips in NASA TESS light curves than matched non-disk control stars.*

---

## Why I Built This

I'm a student based in Almaty. I got interested in exocomet searches after reading about the asymmetric dips detected around Beta Pictoris — the star where this whole field started in the 1980s — and the wave of follow-up work now possible with TESS data.

Most exocomet searches I read about were looking at individual stars or running large blind searches without a clear false-positive baseline. The question that kept bothering me was: if you specifically pick stars known to have dusty debris disks (where comets are theoretically more likely), does that actually improve your detection rate? Or does it just produce the same noise as any other TESS search?

I built AstroHunter KZ to test that question with a matched control sample. Every debris-disk / IR-excess target star is paired with a control star from the same TESS sector, similar brightness, and similar spectral type. If the detector is just picking up variability and systematics, you'd expect it to trigger equally on both groups. If disk activity genuinely correlates with comet-like signals, you'd see more events in the target sample.

## What It Does

The pipeline downloads public TESS 2-minute photometry via the MAST archive, runs a rolling-window asymmetric dip detector (looking for the sharp-ingress, slow-egress shape that a comet's dust tail would produce), and measures detector sensitivity using injection-recovery tests — injecting thousands of synthetic comet-like signals into real TESS noise and counting how many get recovered. Candidate events are then ranked by a gradient-boosting classifier trained on those synthetic injections, filtered through six automated quality flags, and crossmatched against three external catalogs (VSX for known variables, SIMBAD for object types, the TESS Eclipsing Binary catalog for contamination). The highest-priority events go into a manual review gallery: per-event zoom plots and full light curves, with a CSV template for recording dispositions.

The ML component is deliberately limited. It ranks events by how much they resemble synthetic injections — it says nothing about whether an event is real. A high ML score means the morphology looks like a simulated asymmetric dip, not that there's a comet.

## Current Result

The development survey scanned 28 debris-disk / IR-excess targets and 28 matched controls. The detector found 156 raw dip-like events. After automated vetting, three events survived — all on the same star, TIC 444335503, which triggered 20 events total. That star is a control star, not a debris-disk target. Twenty triggers on one star is a strong indicator of stellar variability or systematic artifact, not repeated comet transits.

After manual inspection of 41 high-priority events, zero candidates were kept. The dispositions were: 23 likely variable star, 9 likely systematic, 9 insufficient data. The raw event rate ratio — target detections per star versus control detections per star — was 0.58, meaning controls triggered more often than targets. That's the opposite of what the hypothesis predicts.

**The hypothesis was not supported. The result is a negative result. No exocomet discovery claim is made.**

The clearest takeaway from TIC 444335503 is about method, not about exocomets: without the matched control sample, those three high-SNR automated-pass events could have looked like a finding. The fact that they came from a control star with 20 triggers made them immediately suspicious. The control design worked the way it was supposed to — by catching false positives before they became false claims.

## Why a Negative Result Still Matters

The pipeline correctly identified and rejected all false positives. That's harder than it sounds; a lot of automated searches stop at the "candidates" stage without the vetting machinery to evaluate them.

The failure mode is documented. The detector overtriggers on variable stars — 13 out of 36 candidate-producing stars crossed the overtrigger threshold. That's specific, actionable information about what needs to change before a larger survey would be meaningful.

Every number, every table, every plot is reproducible from a fresh clone with no private data.

## Technical Overview

- **Data:** Public TESS 2-minute photometry, downloaded via lightkurve/MAST and cached locally as Parquet files.
- **Detector:** Rolling-window scanner computing ingress/egress ratio, local SNR, and dip depth. Designed to flag asymmetric dips, not symmetric planet-like transits.
- **Injection-recovery:** Synthetic asymmetric signals injected into real TESS noise to measure how sensitive the detector actually is at different depths and durations.
- **ML ranking:** GradientBoostingClassifier trained on injection-recovery labels. Used only to prioritize events for manual review — not used to confirm or reject candidates.
- **Automated vetting:** Six quality flags covering SNR threshold, edge-of-window detections, morphology shape, and repeated-event suppression logic.
- **External checks:** VSX variable star crossmatch, SIMBAD object type check, TESS-EB eclipsing binary catalog.
- **Manual review:** Per-TIC gallery folders with full light curves and event zoom panels. Dispositions recorded in a CSV template with controlled label options.

All pipeline modules are in `src/astrohunter/`. Each stage has a standalone CLI script under `scripts/`. The full pipeline runs without private API keys.

## How to Reproduce

```bash
git clone https://github.com/L4RBIX/astrohunter-kz.git
cd astrohunter-kz
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m pytest
```

For the full run — catalog building, light-curve scans, injection recovery, ML ranking, external vetting, candidate consolidation, and manual review gallery — see [docs/REPRODUCIBILITY.md](docs/REPRODUCIBILITY.md).

Cached light curves live in `cache/lightcurves/` (excluded from git) and are re-downloadable from MAST. Delete a Parquet file and re-run to force a fresh download.

## What I Learned / Next Steps

The biggest lesson is that matched controls are not optional. They're the only part of the pipeline that makes the result interpretable. Without them, the TIC 444335503 events would have looked like candidates.

The detector's main problem is overtriggering on variable stars. The next version needs explicit suppression of repeated events on the same star, and probably a periodic-signal rejection step before the asymmetry check. The sample size also needs to grow — 28 per group is too small for reliable rate statistics regardless of what the detector finds.

If any candidates survived a better-tuned pipeline and a larger sample, the minimum bar for taking them seriously would be multi-sector confirmation plus expert visual review. Nothing in the current survey is close to that bar.

## Documentation

- [Science fair report](docs/SCIENCE_FAIR_REPORT.md) — full write-up of the method, results, and negative-result interpretation
- [Presentation script](docs/PROJECT_PRESENTATION_SCRIPT.md) — 4–6 minute spoken script and judge Q&A
- [Poster outline](docs/POSTER_OUTLINE.md) — poster layout and text blocks
- [Reproducibility guide](docs/REPRODUCIBILITY.md) — step-by-step commands for every pipeline stage
- [Claims policy](docs/CLAIMS_POLICY.md) — what this project can and cannot claim

---

*Author: Bekarys Kydyrbekov · Almaty · 2026*  
*Repository: [github.com/L4RBIX/astrohunter-kz](https://github.com/L4RBIX/astrohunter-kz)*
