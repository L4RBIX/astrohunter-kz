# Phase 5C: External Catalog Crossmatch Vetting

Phase 5C enriches the vetted candidate table by querying three external
catalogs to identify candidate host stars that are known variable stars,
eclipsing binaries, or astrophysically problematic object types.

## Scientific Constraints

**Read this section before interpreting any external catalog result.**

- External catalog checks **reduce false-positive contamination** but do
  **NOT confirm exocomet detections**.
- A catalog match indicates **possible contamination**; it is **NOT** a
  definitive false-positive verdict. Known variables can still host comets.
- Lack of an external catalog match does **NOT prove astrophysical validity**.
  Many real variables and EBs are missing from these catalogs.
- Remote catalog failures (`status = failed`) must be reported transparently.
  A failed query **does not** mean "not found"; it means the check was
  inconclusive and must be re-run with network access.
- **Manual inspection** of every candidate remains mandatory regardless of
  external catalog results.
- External flags are heuristic classifiers, not scientific verdicts.
- Rate statistics derived from externally-checked candidates remain
  preliminary until full-survey scanning, manual vetting, and multi-sector
  confirmation are complete.

## External Sources

| Catalog | Query service | Search radius | Purpose |
|---|---|---|---|
| AAVSO VSX | VizieR B/vsx/vsx | `--radius-arcsec` (default 10″) | Known variable stars |
| SIMBAD | astroquery.simbad | `--radius-arcsec` (default 10″) | Object type classification |
| TESS Eclipsing Binary (Prsa et al. 2022) | VizieR J/ApJS/258/16 | 3× radius (default 30″) | Known TESS EBs (TESS pixel ~21″/px) |

## Status Values

Each catalog produces a `*_check_status` column with one of:

| Value | Meaning |
|---|---|
| `matched` | A source was found within the search radius |
| `not_found` | Query succeeded but no source found within radius |
| `failed` | Query raised an exception (network, timeout, API error) |
| `not_attempted` | Query was skipped (no coordinates, or `--skip-*` flag) |

## False-Positive Flag Labels

The `external_false_positive_flag` column summarises the combined result:

| Flag | Meaning |
|---|---|
| `possible_eclipsing_binary_match` | TESS-EB catalog match, or VSX type is EA/EB/EW/CV/RR |
| `known_variable_match` | VSX match with variable type (but not a clear EB type) |
| `simbad_nonstellar_or_problematic_type` | SIMBAD otype in concern list (EB*, CV*, Mira, etc.) |
| `no_external_match` | All queried catalogs returned no match |
| `external_check_failed` | No matches found, but at least one catalog query failed |

**A `possible_eclipsing_binary_match` or `known_variable_match` flag demotes
the candidate's `automated_vetting_status` from `pass` to `flagged` and sets
`flag_external_catalog_match = True`.**  This is a precautionary demotion,
not a rejection.

## Output Columns

After running Phase 5C, the candidate table gains:

| Column | Description |
|---|---|
| `vsx_check_status` | VSX query status |
| `vsx_match_name` | VSX source name |
| `vsx_variable_type` | VSX variability type (e.g., EA, RRAB) |
| `vsx_sep_arcsec` | Angular separation to VSX match |
| `simbad_check_status` | SIMBAD query status |
| `simbad_main_id` | SIMBAD primary identifier |
| `simbad_otype` | SIMBAD primary object type |
| `simbad_otypes` | SIMBAD all object types |
| `simbad_sep_arcsec` | Angular separation to SIMBAD match |
| `tess_eb_check_status` | TESS-EB catalog query status |
| `tess_eb_match_id` | TESS-EB catalog TIC ID of matched EB |
| `tess_eb_sep_arcsec` | Angular separation to TESS-EB match |
| `external_false_positive_flag` | Summary flag (see table above) |
| `external_vetting_notes` | Free-text notes from matched sources |
| `flag_external_catalog_match` | True if any concern flag triggered |
| `external_vetter_version` | Version stamp for reproducibility |

## How to Run

```bash
python scripts/run_external_vetting.py \
  --candidate-table results/tables/vetted_candidate_events_matched_scan.csv \
  --output results/tables/vetted_candidate_events_external_checked.csv \
  --summary-output results/tables/external_crossmatch_summary.csv \
  --radius-arcsec 10
```

Offline / skip individual catalogs:

```bash
python scripts/run_external_vetting.py \
  --candidate-table results/tables/vetted_candidate_events_matched_scan.csv \
  --output results/tables/vetted_candidate_events_external_checked.csv \
  --summary-output results/tables/external_crossmatch_summary.csv \
  --skip-simbad --skip-tess-eb
```

## Coordinate Requirements

The candidate table must have `ra_deg` and `dec_deg` columns, OR the script
must be able to join coordinates from the target/control catalogs via `tic_id`.
The script automatically joins coordinates from `catalogs/target_sample_enriched.csv`
and `catalogs/control_pool.csv` unless coordinates are already present.

Candidates without resolvable coordinates receive `status = not_attempted` for
all catalogs.

## Interpreting Results with Failed Queries

If SIMBAD or VSX queries fail due to network or API issues:
- `simbad_check_status = failed` — the SIMBAD result is inconclusive.
- `external_false_positive_flag = external_check_failed` — when no catalog
  matched but at least one query failed.
- **Re-run with stable network access** before interpreting "no match".

## Dev-Run Results (5 Matched-Scan Candidates, Radius = 10″)

These are the actual results from running Phase 5C on the current dev sample.
They are preliminary and must not be interpreted as scientific conclusions.

| TIC ID | Name | Role | VSX | SIMBAD otype | TESS-EB | Flag |
|---|---|---|---|---|---|---|
| 115598451 | TIC 115598451 | control | NSV 15119 (0.8″) | `**` double star | not found | `known_variable_match` |
| 229012143 | HD 203 | target | not found | PM\* (1.2″) | not found | `no_external_match` |
| 381003375 | HD 15115 | target | not found | PM\* (1.3″) | not found | `no_external_match` |
| 12377940 | HR 9102 | target | not found | `*` star (0.2″) | not found | `no_external_match` |
| 428612809 | TIC 428612809 | control | not found | `*` star (0.0″) | not found | `no_external_match` |

**VSX:** 1 match (TIC 115598451 → NSV 15119). The VSX entry is a "New Suspected
Variable" with no type assigned. The match separation is 0.8″, well within the
10″ search radius. Flagged as `known_variable_match` as a precautionary measure.

**SIMBAD:** 5 matches. All four target candidates (HD 203, HD 15115, HR 9102,
TIC 428612809) returned PM\* (proper motion star) or generic `*` types — neither
is in the contamination concern list. TIC 115598451 returned `**` (double/multiple
star), which is also not in the concern list. SIMBAD results do not raise
contamination concerns for any of the five candidates in this dev run.

**TESS-EB:** 0 matches. None of the five candidates appear in the Prsa et al.
2022 TESS eclipsing binary catalog within a 30″ search radius.

**Automated vetting after Phase 5C:** All 5 candidates remain `flagged` status
(they were already flagged by automated morphology flags in Phase 5). The VSX
match on TIC 115598451 additionally sets `flag_external_catalog_match = True`.

**Scientific interpretation:** These results are based on 5 candidates from a
partial scan covering only 3 target and 2 control stars (those with cached TESS
data). No statistical conclusions about target-vs-control rates should be drawn
from this sample size. The VSX flag on the control candidate is a precautionary
note, not a confirmed false positive. The absence of TESS-EB matches is
consistent with the small sample, not with a statement that none of the
matched-pair stars are eclipsing binaries.

## What Still Must Be Done Before Any Astrophysical Interpretation

1. Re-run any failed queries with network access.
2. Manual inspection of every candidate, including light curve examination.
3. Multi-sector confirmation for any candidate that passes automated vetting.
4. Cross-check against additional catalogs (Gaia variability, ASAS-SN, ZTF).
5. Statistical power analysis: is the sample large enough for rate-ratio claims?
6. Full-survey scan (all 28 matched pairs).
7. Review by a qualified astrophysicist.

External catalog checking is one layer of a multi-layer vetting process.
It is not a substitute for any of the above steps.
