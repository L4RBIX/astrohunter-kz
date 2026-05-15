# Data Sources

AstroHunter KZ Phase 2 uses public catalogs to build preliminary development
samples. These catalogs are inputs for target selection, not candidate-event
results.

## Cotten & Song 2016

- Paper: Cotten & Song 2016, ApJS 225, 15
- VizieR ID: `J/ApJS/225/15`
- Use: primary debris-disk / infrared-excess source for development targets.
- Limitation: catalog metadata and coordinates must be crossmatched carefully to
  TIC/Gaia before survey-scale analysis.

## Chen et al. 2014

- Paper: Chen et al. 2014, ApJS 211, 25
- VizieR ID: `J/ApJS/211/25`
- Use: Spitzer IRS debris-disk catalog and complementary target source.
- Limitation: not every source will have useful TESS coverage or sufficient
  photometric precision for transit-like event searches.

## McDonald et al. 2017

- Paper: McDonald et al. 2017, MNRAS 471, 770
- VizieR ID: `J/MNRAS/471/770`
- Use: secondary/cautionary IR-excess source only.
- Limitation: this catalog must be filtered carefully because IR excess can be
  associated with evolved stars, YSOs, contamination, or non-debris-disk
  phenomena. It should not be treated as a clean debris-disk target list without
  additional vetting.

## TIC, Gaia DR3, SIMBAD, and TESS Availability

Future Phase 2 refinement should add real crossmatches to TIC, Gaia DR3, SIMBAD,
and TESS light-curve availability metadata. If these remote queries fail or are
not yet implemented, the repository must leave placeholder columns empty and
state that crossmatching is incomplete.

Phase 2B implements TESS availability enrichment using lightkurve/MAST search
metadata only. It records counts such as `n_tess_products` and does not download
light curves during catalog building.

Gaia/TIC enrichment currently provides safe placeholder columns when no real
crossmatch has been performed. Missing Gaia/TIC fields must not be interpreted
as measured values.

Phase 2C adds optional TIC/Gaia crossmatch hooks:

- TIC: `astroquery.mast.Catalogs.query_region` around target RA/Dec.
- Gaia: `astroquery.gaia.Gaia.cone_search_async` around target RA/Dec.
- Default radius: 5 arcsec.

If these queries fail or return no match, scientific columns such as `tic_id`,
`gaia_dr3_source_id`, `tmag`, `bp_rp`, and `parallax` remain empty. Query
outcomes are recorded only in status columns:

- `tic_query_status`: `not_attempted`, `matched`, `not_found`, or `failed`
- `gaia_query_status`: `not_attempted`, `matched`, `not_found`, or `failed`

The clean derived table `catalogs/target_sample_clean.csv` keeps only useful
research columns and must not contain placeholder values in scientific fields.

## Real Control Pools

Control samples must come from real non-disk metadata, such as TIC rows
crossmatched to Gaia and checked for TESS light-curve availability. See
`docs/CONTROL_POOL_GUIDE.md` for required columns and workflow. The repository
does not fabricate controls from the target catalogs.

## Data Policy

Do not fabricate target samples, control samples, candidate lists, or paper
results. Development samples should be small and reproducible. Large raw catalog
dumps and downloaded light curves should remain outside Git.
