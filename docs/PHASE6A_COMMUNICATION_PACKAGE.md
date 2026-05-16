# Phase 6A: Science-Fair / Portfolio Communication Package

## Overview

Phase 6A converts the completed technical pipeline results into a polished,
honest communication package suitable for science-fair judging, research
competitions, GitHub portfolios, and public science communication.

All communication materials enforce the project's strict scientific claims
policy: no discovery claims, no overclaiming, honest negative result framing.

---

## Deliverables

| File | Purpose | Audience |
|---|---|---|
| `docs/SCIENCE_FAIR_REPORT.md` | Full science-fair written report (16 sections) | Judges, reviewers |
| `docs/PROJECT_PRESENTATION_SCRIPT.md` | 4-6 min spoken script + 8-question Q&A | Oral presentation |
| `docs/POSTER_OUTLINE.md` | 36×48" poster layout with all text blocks | Poster session |
| `docs/SOCIAL_MEDIA_POSTS.md` | LinkedIn, Threads/X, TikTok, Instagram, GitHub | Public |
| `docs/GITHUB_PORTFOLIO_SUMMARY.md` | Portfolio-quality GitHub project summary | Recruiters, peers |
| `results/tables/communication_key_messages.csv` | Approved vs. forbidden language audit | Internal policy |

---

## Scientific Claims Policy

All Phase 6A materials were written under the claims policy documented in
`docs/CLAIMS_POLICY.md` and enforced by `results/tables/final_dev_survey_claims_audit.csv`.

### Approved language

- "candidate dip-like features"
- "exocomet-like asymmetric transit candidates"
- "no candidates survived conservative manual review"
- "negative result" / "honest negative result"
- "reproducible pipeline for future searches"
- "false-positive vetting"
- "matched-sample analysis"
- "current dev sample does not support the hypothesis"
- "future larger-sample work required"

### Prohibited language

- "confirmed exocomet"
- "discovered exocomets"
- "AI discovered exocomets" / "AI detected"
- "NASA-level discovery" / "NASA-level model"
- "Kazakhstan discovered exocomets"
- "proof that debris disks host exocomets"
- "our AI found signals that astronomers missed"
- "we confirmed the existence of exocomets"

---

## Summary of Results Communicated

All materials report these exact numbers. Do not round up or reframe them.

| Metric | Value |
|---|---|
| Target stars scanned | 28 |
| Control stars scanned | 28 |
| Raw candidate events | 156 (57 target, 99 control) |
| Raw rate ratio (target/control) | 0.58 |
| Automated vetting pass | 3 (all on 1 control star, TIC 444335503) |
| Manual review keep_candidate | **0** |
| Surviving candidates | **0** |
| Automated tests passing | 453 |

---

## Document Descriptions

### SCIENCE_FAIR_REPORT.md

Full written report structured for science-fair judging panels. Sections:
Abstract, Problem, Research Question, Hypothesis, Background (5 subsections),
Data Sources, Methodology, Pipeline Architecture, ML Role, Vetting Cascade,
Results, Negative Result Interpretation, Why This Still Matters, Limitations,
Future Work, Claims Policy, Conclusion.

Key distinctions:
- Section 8 explicitly separates what ML does from what ML does NOT do
- Section 9 shows the full 156 → 3 → 0 vetting cascade table
- Section 11 explains why a negative result is a valid scientific contribution
- Section 15 documents the claims policy in a two-column approved/not-allowed table

### PROJECT_PRESENTATION_SCRIPT.md

Spoken presentation script with time-coded segments (total 4–6 minutes):
- Opening Hook (30s) — Beta Pictoris 1987, the original exocomet discovery
- The Problem (45s) — TESS data, false-positive challenge, matched-control design
- The Data (30s) — debris-disk catalogs, public MAST/lightkurve, matching
- What I Built (60s) — six pipeline stages, 453 tests, no private data
- The Result (60s) — exact numbers, TIC 444335503, zero surviving candidates
- Why No Discovery Claim (45s) — what a real detection would require
- Why This Still Matters (45s) — pipeline value, documented failure mode, honest science
- Future Work (30s) — detector tuning, larger sample, expert review
- Closing (30s)

Plus 8 Q&A pairs for judge preparation (Q: "Did you discover an exocomet?" and seven others).

### POSTER_OUTLINE.md

Science-fair poster layout for 36"×48" portrait orientation. Includes:
- ASCII layout map of all sections
- Full text for every section (research question, hypothesis, background, pipeline
  diagram, results table, claims policy table, limitations, future work, takeaway)
- Production notes (colors, fonts, prohibited words, required cautions)

The poster explicitly includes a Claims Policy Box with red border, showing
approved vs. prohibited language side by side.

### SOCIAL_MEDIA_POSTS.md

Platform-specific posts:
- **LinkedIn** (400-600 words): Professional technical audience, explains the
  matched-control design and the value of a rigorous negative result
- **Threads/X** (3 versions, ≤280 chars): Result-focused, process-focused, thread teaser
- **TikTok** (90-second script, 7 time-coded segments): Accessible science explanation
- **Instagram** (caption with hashtags): Visual-first, honest summary
- **GitHub one-line + extended description**: For repository About field

All posts include a DO NOT SAY section and 5 usage rules for consistent public messaging.

### GITHUB_PORTFOLIO_SUMMARY.md

Portfolio document for technical audiences (recruiters, collaborators, peers).
Covers: overview, technical achievements table, full architecture flowchart,
data sources, module-level component table, testing/reproducibility instructions,
results table, what was learned, future roadmap, scientific honesty statement.

### communication_key_messages.csv

Machine-readable audit of approved and prohibited messages with reasoning.
Columns: message_type, approved_message, forbidden_overclaim, reason.
Covers 10 communication scenarios aligned with the claims policy.

---

## How Phase 6A Materials Relate to the Technical Pipeline

| Technical output | Phase 6A use |
|---|---|
| `results/tables/full_matched_star_level_summary.csv` | Numbers in report, poster, social media |
| `results/tables/full_matched_manual_review_disposition_template.csv` | Disposition counts in report |
| `results/figures/full_matched_rate_ratio_plot.png` | Poster Section 9, key figure |
| `results/figures/manual_review_priority_overview.png` | Poster Section 9, key figure |
| `results/tables/final_dev_survey_claims_audit.csv` | Claims policy sections in all docs |
| `src/astrohunter/inspection.py` | Described in report Section 6, script Section 4 |

---

## What Phase 6A Does NOT Do

- Does NOT rerun the pipeline or change any results
- Does NOT relabel any disposition values
- Does NOT claim any discovery
- Does NOT force any candidate to pass vetting
- Does NOT write the final research paper (that is future work)
- Does NOT push to remote (user must do that explicitly)

---

## Running Phase 6A

Phase 6A produces documentation only — no scripts to run. The communication
package was created by reading the actual pipeline outputs and documenting them
honestly.

To verify the test suite after Phase 6A:

```bash
python -m pytest tests/ -q
```

All 453 tests should pass. Phase 6A adds no new source code and therefore does
not affect the test suite.

---

## Phase 6A Completion Checklist

- [x] `docs/SCIENCE_FAIR_REPORT.md` — 16 sections, all key numbers, claims policy
- [x] `docs/PROJECT_PRESENTATION_SCRIPT.md` — 4-6 min script + 8 Q&A pairs
- [x] `docs/POSTER_OUTLINE.md` — 13 sections, ASCII layout, production notes
- [x] `docs/SOCIAL_MEDIA_POSTS.md` — 5 platforms, DO NOT SAY section, usage notes
- [x] `docs/GITHUB_PORTFOLIO_SUMMARY.md` — Portfolio-quality summary
- [x] `docs/PHASE6A_COMMUNICATION_PACKAGE.md` — This file
- [x] `results/tables/communication_key_messages.csv` — Claims audit CSV
- [x] `README.md` — Updated with Current Scientific Result section
- [x] `docs/PROJECT_SCOPE.md` — Phase 6A entry added
- [x] `docs/REPRODUCIBILITY.md` — Phase 6A section added
