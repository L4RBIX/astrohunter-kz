# Science-Fair Poster Layout
## AstroHunter KZ: Controlled TESS Search for Exocomet-Like Transit Candidates

**Recommended size:** 36" × 48" portrait or 48" × 36" landscape
**Font:** Minimum 24pt body, 48pt+ section headers, 72pt+ title

---

## POSTER LAYOUT MAP (Portrait orientation)

```
┌─────────────────────────────────────────────────────────────────────┐
│                            TITLE BLOCK                              │
│  AstroHunter KZ: Searching for Exocomet Signatures in NASA TESS    │
│  Photometry Using a Matched-Control Pipeline and Machine Learning   │
│                    Author | Institution | Date                      │
├─────────────────────────────────────────────────────────────────────┤
│  ONE-SENTENCE SUMMARY (centered, large, bold)                       │
│  "An end-to-end TESS pipeline found 156 raw dip-like events but    │
│   conservative vetting eliminated all plausible candidates —        │
│   demonstrating why false-positive control is essential in          │
│   AI-assisted astronomical searches."                               │
├──────────────┬──────────────┬──────────────────────────────────────┤
│ RESEARCH Q   │ BACKGROUND   │ PIPELINE DIAGRAM                     │
│              │              │                                       │
│              │              │                                       │
├──────────────┴──────────────┤                                       │
│ HYPOTHESIS                  │                                       │
│                             │                                       │
│ DATA SOURCES                ├───────────────────────────────────────┤
│                             │ RESULTS BOX (large, prominent)       │
│                             │                                       │
├─────────────────────────────┤                                       │
│ ML ROLE (brief)             │                                       │
│                             ├───────────────────────────────────────┤
│ VETTING STAGES              │ KEY FIGURES                          │
│                             │ (rate ratio plot, event counts)      │
├─────────────────────────────┴───────────────────────────────────────┤
│ CLAIMS POLICY  │ LIMITATIONS │ FUTURE WORK  │ TAKEAWAY             │
│ (red border)   │             │              │ (bold, centered)     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## SECTION 1: TITLE

**Main title (72pt+, bold):**

> AstroHunter KZ: Searching for Exocomet-Like Signals in NASA TESS Data

**Subtitle (36pt):**

> A Matched-Sample, Multi-Stage Vetting Pipeline with Machine Learning Ranking

**Author line:** Bekarys Kydyrbek | 2026

---

## SECTION 2: ONE-SENTENCE PROJECT SUMMARY

*(Centered, bold, 32pt, placed directly under title)*

> "An end-to-end Python pipeline searched NASA TESS photometry for exocomet-like asymmetric brightness dips around debris-disk stars — and found that rigorous vetting eliminated every raw candidate, producing an honest negative result that validates the importance of matched-control design."

---

## SECTION 3: RESEARCH QUESTION

**Heading:** Research Question

**Text block:**

> Does pre-selecting debris-disk / infrared-excess stars produce a higher rate of asymmetric dip-like events in TESS light curves than matched non-disk control stars observed in the same conditions?

*(Include a small diagram: debris-disk star icon vs. control star icon with a question mark between them)*

---

## SECTION 4: HYPOTHESIS

**Heading:** Hypothesis

**Text block:**

> Debris-disk stars host more comet-like material in dynamically active orbits, so they should show more frequent short asymmetric brightness dips than similar stars without detected dust disks — if TESS is sensitive enough to detect them.

**Below the hypothesis box:**

> *(This hypothesis was not supported in the current development run.)*

---

## SECTION 5: BACKGROUND (keep brief — 3 bullet points maximum)

**Heading:** Background

**Bullet points:**

- **What is an exocomet?** A comet-like body orbiting another star. When it crosses the star's disk, its dust tail can block some light and create a rapid, asymmetric brightness dip — sharper on ingress than on egress.

- **What are debris disks?** Dusty belts of rocky and icy material orbiting a star, detected as excess infrared emission. They are thought to be sites of active comet-like body production.

- **Why TESS?** NASA's TESS satellite monitors stars every 2 minutes for 27-day sectors, producing high-precision light curves across hundreds of thousands of stars.

**Include:** A simple diagram showing a star, a comet orbit, and a schematic asymmetric dip light curve.

---

## SECTION 6: DATA SOURCES

**Heading:** Data

**Text block:**

> - **Light curves:** Public TESS 2-minute photometry via MAST/lightkurve (no private data)
> - **Target sample:** 28 debris-disk / IR-excess stars from Cotten & Song (2016) and Chen et al. (2014)
> - **Control sample:** 28 matched non-disk stars (same TESS sector, similar brightness/type)
> - **Crossmatch catalogs:** VSX (variable stars), SIMBAD (object types), TESS-EB (eclipsing binaries)

---

## SECTION 7: PIPELINE DIAGRAM (center-right column, large)

**Heading:** Six-Stage Pipeline

**Recommended visual:** A vertical flowchart with icons

```
  [TESS Public Archive]
           ↓
  [Asymmetric-Dip Detector]
  (rolling window, ingress/egress ratio, local SNR)
           ↓
  [Injection-Recovery Sensitivity Test]
  (synthetic signals in real noise)
           ↓
  [ML Ranker — GradientBoostingClassifier]
  (trained on injections, NOT on real candidates)
           ↓
  [Automated Vetting — 6 quality flags]
  (SNR, morphology, edge, asymmetry)
           ↓
  [External Catalog Crossmatch]
  (VSX + SIMBAD + TESS-EB)
           ↓
  [Manual Review]
  (light-curve inspection, disposition labels)
           ↓
  [Survey Interpretation + Claims Audit]
```

**Caption below diagram:**

> Every stage produces auditable output tables. The ML model ranks events but does not confirm them. All code is tested (453 automated tests) and publicly available.

---

## SECTION 8: RESULTS BOX (prominent — use a colored border)

**Heading:** Results — Development Survey

**Large table:**

| Metric | Value |
|---|---|
| Target stars scanned | **28** |
| Control stars scanned | **28** |
| Raw candidate events (total) | **156** |
| Raw events on target stars | 57 |
| Raw events on control stars | 99 |
| Raw rate ratio (target / control) | **0.58** *(below 1)* |
| Events passing automated vetting | **3** (all on 1 control star) |
| Manual review keep_candidate | **0** |
| **Surviving candidates** | **0** |

**Key finding statement (bold, 28pt):**

> The development survey produced no surviving exocomet-like candidates after conservative vetting.
> This is an honest negative result.

**Explanation of TIC 444335503:**

> The only automated-pass events (3) were on TIC 444335503 — a control star, not a debris-disk target — which triggered 20 detector events. This pattern is consistent with stellar variability, not exocomet transits. The matched-control design immediately flagged this as a false positive.

---

## SECTION 9: KEY FIGURES TO INCLUDE

Include 2–3 figures selected from:

1. **Rate ratio plot** (`results/figures/full_matched_rate_ratio_plot.png`)
   - Caption: "Target vs. control candidate yield rate ratio with Poisson CI.
     Both raw and post-vetting results are shown. No statistically significant
     excess was detected."

2. **Event count bar chart** (`results/figures/full_matched_target_control_counts.png` or similar)
   - Caption: "Raw candidate events by sample role. Controls produced more raw
     events than targets. After vetting, neither group retained any candidates."

3. **Priority overview** (`results/figures/manual_review_priority_overview.png`)
   - Caption: "Manual review priority distribution. 13 TICs were flagged as
     overtriggered. No TIC achieved high priority after full vetting."

---

## SECTION 10: CLAIMS POLICY BOX

*(Use a red or orange border to make it stand out)*

**Heading:** Scientific Claims Policy

**Two-column layout:**

| Approved Language | NOT Allowed |
|---|---|
| "Candidate dip-like features" | "Confirmed exocomets" |
| "Zero surviving candidates after vetting" | "We discovered exocomets" |
| "Negative result in this dev sample" | "AI found comets" |
| "Reproducible pipeline for future searches" | "NASA-level discovery" |
| "Hypothesis not supported" | "Kazakhstan discovered exocomets" |

**Note below table:**

> All claims are documented in `results/tables/final_dev_survey_claims_audit.csv`.
> No result in this project supports an exocomet discovery claim.

---

## SECTION 11: LIMITATIONS

**Heading:** Limitations

- 28 + 28 stars is a small development sample — too small for statistical conclusions
- Detector overtriggers on variable stars (13 of 36 candidate-TICs exceeded the overtrigger threshold)
- Single-sector analysis only — no multi-sector confirmation
- Manual review was conservative and metadata-based, not expert astrophysical review
- Catalog completeness: some target stars may be misclassified in the debris-disk catalog

---

## SECTION 12: FUTURE WORK

**Heading:** Next Steps

1. Tune the detector — suppress repeated events on the same star
2. Expand to 100+ stars per group
3. Require multi-sector consistency as a candidate filter
4. Partner with an experienced astronomer for expert visual review
5. Explore Gaia, ZTF, and ASAS-SN crossmatching
6. Write up the methodology as a reproducibility-focused research note

---

## SECTION 13: TAKEAWAY MESSAGE

*(Bottom center, large font, bordered box)*

> **"Finding nothing — honestly — is a genuine scientific contribution."**
>
> This project built a real, tested, end-to-end pipeline for exocomet-like signal
> search, correctly identified and rejected all false positives using a
> matched-control design, and demonstrated that rigorous vetting produces honest
> science — even when the result is null.
>
> The code is public. Every number is documented. The next search starts here.

---

## POSTER PRODUCTION NOTES

- Use a consistent color scheme: dark blue for headers, white/light gray background, red for the claims policy box
- Include the GitHub URL on the poster: `github.com/L4RBIX/astrohunter-kz`
- All figures should have clear captions with the scientific caution: "Preliminary — development sample only"
- The pipeline diagram should be the largest single visual element
- Do not use the word "discovered" anywhere on the poster
- Do not use the phrase "AI found" or "AI detected" — use "pipeline detected" or "detector triggered"
