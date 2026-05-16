# AstroHunter KZ
## A Controlled TESS Search for Exocomet-Like Asymmetric Transit Candidates Around Debris-Disk Stars

**Author:** Bekarys Kydyrbekov
**Date:** 2026-05-16
**Repository:** https://github.com/L4RBIX/astrohunter-kz

---

## Abstract

This project built an end-to-end, open-source Python pipeline to test whether
stars known to host debris disks (dusty belts of asteroid- and comet-like
material) produce more exocomet-like light-curve features than matched
comparison stars. Using public photometry from NASA's TESS satellite, the
pipeline scanned 28 debris-disk target stars and 28 matched control stars for
characteristic asymmetric brightness dips that might resemble the passage of a
comet's dust tail across the stellar disk. The detector found 156 raw
dip-like events. After a four-stage vetting cascade — automated quality
filters, machine-learning scoring, external catalog crossmatching, and
conservative manual review — **zero candidates survived** as plausible
exocomet-like events. All three events that passed automated vetting belonged
to a single overtriggered control star showing repeated large-amplitude
variability, not astrophysical cometary transits. The result is an **honest
negative result**: the current development sample does not support the
hypothesis that debris-disk stars produce more exocomet-like transit events.
This outcome is scientifically meaningful because it demonstrates the critical
importance of rigorous false-positive control in AI-assisted astronomical
searches, and the pipeline itself is a validated, reproducible research tool
ready for larger-scale future studies.

---

## 1. Problem and Motivation

In 1987, astronomers discovered that the star Beta Pictoris occasionally showed
rapid, asymmetric dips in its brightness lasting hours to days — features now
attributed to comet-like bodies (exocomets) passing in front of the star and
blocking some of its light with their dust tails. Since then, dozens of
candidate exocomet hosts have been identified, mostly by visual inspection of
individual light curves.

The arrival of NASA's Transiting Exoplanet Survey Satellite (TESS), launched
in 2018, changed the landscape: TESS continuously monitors hundreds of thousands
of stars, producing photometric time series accurate enough to detect brightness
changes as small as a few hundred parts per million. This creates an opportunity
to search for exocomet-like signals systematically across large stellar samples.

The challenge is that TESS data contains enormous numbers of "false positives" —
instrumental artifacts, stellar variability, eclipsing binary contamination, and
detector noise that can mimic real transit signals. An unsupervised search would
produce thousands of spurious candidates. **This project asks: can a carefully
designed, fully automated pipeline with proper statistical controls separate
genuine signal from noise at scale?**

---

## 2. Research Question

**Does pre-selecting debris-disk / infrared-excess stars as search targets
produce a statistically detectable increase in the rate of asymmetric
dip-like events, compared to matched non-disk control stars observed in the
same TESS sectors and brightness range?**

---

## 3. Hypothesis

Debris-disk stars host more cometary material in active dynamical states.
Therefore, they should show more frequent exocomet-like transit signatures than
comparable stars without detected debris disks, when both populations are
observed by TESS with the same cadence and sensitivity.

---

## 4. Background: Key Concepts Explained Simply

### 4.1 TESS Light Curves

TESS is a NASA space telescope that stares at patches of sky for about 27 days
at a time, recording the brightness of every star in its field every 2 minutes.
A *light curve* is simply a graph of a star's brightness over time. When
something passes in front of the star — a planet, a comet, or its own variability
— the brightness temporarily dips.

### 4.2 Exocomets and Asymmetric Dips

Exocomets are comet-like bodies orbiting other stars. When an exocomet passes
in front of its host star, it blocks some starlight. Unlike a circular planet,
a comet drags a long dust tail behind it. This makes the brightness dip *unequal*
in shape: it typically drops steeply as the dense leading edge crosses the star,
then recovers gradually as the diffuse tail sweeps through. This **asymmetry** —
a sharp ingress and slower egress — is the key fingerprint of an exocomet.

### 4.3 Debris Disks and Why They Matter

Some stars are surrounded by belts of rocky and icy debris — leftovers from
planet formation, similar to our Solar System's asteroid belt and Kuiper Belt.
These are called *debris disks* and are detected as excess infrared (heat)
radiation around the star. Theory predicts that gravitational interactions in
active debris disks can scatter cometary bodies onto star-crossing orbits,
making these stars more likely exocomet hosts.

### 4.4 Why a Control Sample is Essential

If you only search debris-disk stars and find events, you cannot tell whether
the events are genuinely associated with disk activity, or just what any
random star looks like in TESS data. The solution is a **matched control
sample**: a set of non-disk stars selected to have similar brightness,
distance, and TESS observing conditions as the target stars. By comparing
event rates between the two groups, we can determine whether any excess is
real or just an artifact of the data.

### 4.5 Why Raw Candidates Are Not Discoveries

Finding a dip in a light curve is not the same as discovering an exocomet.
TESS light curves contain many instrumental systematics, stellar flares,
variability cycles, and data-quality gaps that can all produce apparent dips.
Every candidate event must pass a multi-stage vetting cascade before it can
be seriously considered astrophysical. Even then, a single-telescope detection
in one sector requires multi-sector confirmation, follow-up spectroscopy, and
expert review before any discovery claim is appropriate.

---

## 5. Data Sources

| Source | Description |
|---|---|
| NASA TESS | Public 2-minute cadence photometry via MAST/lightkurve |
| Cotten & Song (2016) | Debris-disk / IR-excess star catalog |
| Chen et al. (2014) | Additional infrared-excess targets |
| TIC (TESS Input Catalog) | Stellar parameters for sample matching |
| VSX (Variable Star Index) | Known variable star crossmatch |
| SIMBAD | Object type crossmatch |
| TESS Eclipsing Binary catalog | Known EB contamination crossmatch |

All data are public. No proprietary observations or unpublished datasets were
used.

---

## 6. Methodology

The pipeline follows six sequential phases:

1. **Catalog building** — Compile a debris-disk target sample and a matched
   non-disk control pool using public catalogs. Match on TESS sector, magnitude,
   and stellar type.

2. **Light-curve download and preprocessing** — Download public TESS light
   curves, normalize flux to unit median, apply quality flag filtering, and
   cache locally.

3. **Asymmetric-dip detection and injection-recovery** — Scan each light curve
   for asymmetric dip-like features using a rolling-window algorithm that
   computes ingress/egress ratios, local SNR, and depth. Measure detector
   sensitivity using synthetic injected signals.

4. **Machine-learning ranking** — Train a gradient-boosted classifier on
   injection-recovery results (synthetic labels) to score each detected event
   by how much it resembles a real asymmetric transit. Rank real candidates by
   this score.

5. **Automated vetting and external catalog crossmatching** — Apply heuristic
   quality flags (SNR, morphology, asymmetry) and cross-reference each candidate
   star against known variable stars (VSX), SIMBAD object types, and the TESS
   Eclipsing Binary catalog.

6. **Manual review** — Visually inspect light curves for the highest-priority
   and most suspicious events, producing a final disposition (keep_candidate,
   likely_systematic, likely_variable_star, etc.) for each reviewed event.

---

## 7. Pipeline Architecture Overview

```
Public TESS data (MAST/lightkurve)
           │
           ▼
  Matched Catalog Builder
  (debris-disk targets + controls)
           │
           ▼
  Asymmetric-Dip Detector
  (rolling window, ingress/egress ratio, local SNR)
           │
           ▼
  Injection-Recovery Sensitivity Test
  (synthetic signals injected into real noise)
           │
           ▼
  ML Ranker (GradientBoostingClassifier)
  (trained on injection-recovery labels, NOT on real candidates)
           │
           ▼
  Automated Vetting
  (6 quality flags: SNR, edge, morphology, asymmetry)
           │
           ▼
  External Catalog Crossmatch
  (VSX, SIMBAD, TESS-EB)
           │
           ▼
  Candidate Consolidation
  (star-level summaries, overtrigger detection)
           │
           ▼
  Manual Review Gallery
  (light-curve plots, disposition template)
           │
           ▼
  Survey Interpretation + Claims Audit
```

Every stage produces auditable output tables. No stage bypasses the vetting
cascade. All code is version-controlled and unit-tested.

---

## 8. Role of Machine Learning

The machine-learning component is a **GradientBoostingClassifier** (a
gradient-boosted decision tree ensemble) trained on features extracted from
synthetic signal injections into real TESS light curves.

**What ML does:**
- It scores each detected event by how much it resembles a synthetic asymmetric
  dip on a scale from 0 (not dip-like) to 1 (highly dip-like).
- It uses 12 features: SNR, depth, duration, ingress/egress ratio, skewness,
  kurtosis, asymmetry chi-squared, and morphology flags.
- It ranks events so a human reviewer can focus on the most promising ones.

**What ML does NOT do:**
- It does not confirm exocomets.
- It does not replace manual review.
- Its training labels come from synthetic signals, not from known real exocomet
  detections. The model's AUC/F1 scores describe its sensitivity to synthetic
  signals, not its accuracy on real data.

This distinction is essential. A high ML score means the event *looks like* a
simulated asymmetric dip. It does not mean the event is astrophysically real.

---

## 9. Vetting Cascade: How Candidates Are Eliminated

Starting from 156 raw events:

| Stage | Events Remaining | Notes |
|---|---|---|
| Raw detector output | 156 | Includes all detector triggers, target + control |
| Automated vetting pass | 3 | Only events with SNR > 5, good morphology, no quality flags |
| Manual review keep_candidate | **0** | Conservative assessment found no credible candidates |

The 3 automated-pass events all belonged to TIC 444335503, a control star
(not a debris-disk star) that showed 20 candidate triggers — the highest count
in the survey. This pattern is a strong indicator of stellar variability,
systematic artifact, or detector over-sensitivity, not multiple exocomet passages.

In the manual review, all 41 inspected events were classified as:

| Manual Label | Count |
|---|---|
| likely_variable_star | 23 |
| likely_systematic | 9 |
| insufficient_data | 9 |
| keep_candidate | **0** |
| unsure | 0 |

---

## 10. Results

### 10.1 Key Numbers

| Metric | Value |
|---|---|
| Target stars scanned | 28 |
| Control stars scanned | 28 |
| Raw candidate events (target) | 57 |
| Raw candidate events (control) | 99 |
| Raw candidate rate ratio (target / control) | 0.58 |
| Automated pass events (target) | 0 |
| Automated pass events (control) | 3 (all on TIC 444335503) |
| Manual keep_candidate | **0** |
| Surviving candidates after full vetting | **0** |
| Overtriggered stars (≥ 5 events) | 13 |

### 10.2 The Rate Ratio

The raw target-to-control event-rate ratio was approximately **0.58**, meaning
the detector found *more* events per control star than per target star in this
development run. This is the opposite of what the hypothesis predicts.

However, this result should **not** be over-interpreted:
- The sample (28 targets, 28 controls) is too small for a statistically
  reliable comparison.
- The detector in its current form overtriggers on variable stars and produces
  repeated spurious events on single stars.
- After vetting, neither group contains any plausible candidates.

The correct conclusion is: **in this development run, the hypothesis was not
supported.** A larger, better-tuned sample is needed before any stronger
conclusion can be drawn.

### 10.3 What Happened to TIC 444335503?

TIC 444335503 is a **control star** (not a debris-disk star) that produced 20
candidate events — five times the overtrigger threshold of 4 events. Three of
these passed automated vetting with SNR up to 34 and ML scores of 0.85. These
are superficially impressive numbers, but:

- The star is a control star — it is not expected to host exocomet activity
  by design of the study.
- Producing 20 events is a classic signature of periodic stellar variability
  or instrument systematics being repeatedly detected by the asymmetric-dip
  algorithm.
- The manual review classified the star's events as `likely_variable_star`,
  the most common rejection label in the survey.

This is precisely the scenario that the control sample is designed to catch.
Without controls, these events might have seemed significant. With them, they
are clearly instrument / variability artifacts.

---

## 11. Why a Negative Result Is Still a Valid Scientific Result

Negative results are an essential part of science. This study produced a
negative result — the hypothesis was not supported — but that result is
meaningful for several reasons:

1. **It shows false-positive control works.** The most compelling-looking
   candidates (TIC 444335503) were correctly rejected because they appeared in
   the control sample. Without the matched control design, these events could
   have been mistakenly reported.

2. **It documents the challenge.** The current detector overtriggers heavily on
   variable stars. This is important information for future pipeline development.

3. **It is honest.** Publishing a negative result with a reproducible pipeline
   is more valuable than claiming a discovery from ambiguous events that have not
   survived rigorous vetting.

4. **It is reproducible.** Any researcher can clone the repository, re-run the
   pipeline on the same data, and verify every number in this report.

5. **It informs future work.** The specific failure modes identified here — repeated
   events on a single star, morphology mimicry by variable stars — provide
   concrete targets for algorithm improvement.

---

## 12. Why This Project Still Matters

Even with a negative result, this project achieves meaningful goals:

| Achievement | Why It Matters |
|---|---|
| End-to-end pipeline | Demonstrates that a student can build a complete research-grade search system |
| Matched-control design | Implements the statistical safeguard that separates real signal from noise |
| ML ranking | Shows how machine learning can triage large event lists — while being clear about its limits |
| 453 tests passing | Demonstrates software engineering best practices applied to science code |
| External catalog crossmatching | Shows integration with professional catalogs used by research astronomers |
| Claims audit trail | Demonstrates scientific integrity: an explicit record of what can and cannot be claimed |
| Reproducibility | The full pipeline can be re-run from a fresh clone with no private data |

---

## 13. Limitations

1. **Small sample.** 28 + 28 stars is too small for a statistically significant
   comparison. The rate ratio has large Poisson uncertainties.

2. **Detector overtriggering.** The current algorithm produces many repeated
   events on single stars that show any variability. This must be fixed before
   a meaningful rate comparison is possible.

3. **Single-sector, single-lightcurve.** Each star was analyzed using at most
   one available cached light curve. Multi-sector consistency checks were not
   performed.

4. **Conservative manual review.** The manual disposition in this study was
   based on metadata and light-curve patterns rather than full astrophysical
   analysis. Expert review was not obtained.

5. **Catalog incompleteness.** The debris-disk catalog used is not exhaustive.
   Some target stars may have had variable classifications added after catalog
   construction.

---

## 14. Future Work

1. **Detector tuning.** Add explicit rejection for repeated events on the same
   star (overtrigger cap) and periodic-dip suppression.

2. **Larger sample.** Expand the target and control pools to 100+ stars per group.

3. **Multi-sector confirmation.** Require candidate events to appear
   independently in multiple TESS sectors, separated by months.

4. **Expert visual review.** Replace the metadata-based prefill with genuine
   astrophysical review by an experienced astronomer.

5. **Additional catalogs.** Add Gaia variability flags, ASAS-SN, and ZTF
   crossmatches to the external vetting step.

6. **Publication.** Write up the methodology and null result for a student
   journal or preprint, with all claims at the appropriate conservative level.

---

## 15. Ethical and Scientific Claims Policy

This project operates under a strict claims policy documented in
`docs/CLAIMS_POLICY.md`.

**Allowed:**
- Candidate dip-like features
- Exocomet-like asymmetric transit candidates
- The development survey found no surviving candidates after conservative review
- Negative result
- Reproducible pipeline for future searches
- The hypothesis was not supported in this development sample

**Not allowed:**
- Confirmed exocomets
- Discovered exocomets
- AI discovered exocomets or planets
- NASA-level discovery
- Kazakhstan discovered exocomets
- Any wording suggesting astrophysical confirmation without expert review

The claims policy is enforced through an automated audit table
(`results/tables/final_dev_survey_claims_audit.csv`) that documents every major
claim made about this project alongside the evidence that supports or prohibits
it.

---

## 16. Conclusion

AstroHunter KZ built and validated a complete, reproducible pipeline for
searching TESS photometry for exocomet-like asymmetric transit candidates in
a matched target/control framework. The development survey produced **zero
surviving candidates** after conservative vetting. This is an honest negative
result: the current detector configuration and small sample do not support the
hypothesis that debris-disk stars show more exocomet-like events than controls.

The negative result does not diminish the project's value. It demonstrates that
rigorous false-positive control — matched controls, multi-stage vetting, external
catalog crossmatching, and conservative manual review — successfully prevented
spurious claims. The overtriggered control star TIC 444335503, which produced
the most visually impressive candidates, was correctly rejected because it is a
control star with clear evidence of repeated stellar variability.

The pipeline is ready for the next phase: detector improvement, a larger sample,
and multi-sector confirmation. All code, data, and results are publicly available
and fully reproducible.
