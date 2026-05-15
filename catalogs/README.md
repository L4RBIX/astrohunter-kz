# Catalog Outputs

This directory stores small Phase 2 development catalog products.

Expected files:

- `target_sample.csv`: preliminary debris-disk / IR-excess development target sample.
- `target_sample_enriched.csv`: target sample with metadata-only TESS availability
  enrichment and safe Gaia/TIC placeholder columns.
- `target_sample_clean.csv`: clean derived table with useful research columns
  only. Placeholder scientific values are removed; TIC/Gaia fields remain empty
  unless real crossmatches are found.
- `control_pool.csv`: normalized real non-disk control pool when supplied by the
  user from TIC/Gaia/MAST metadata.
- `control_sample.csv`: written only when a real non-disk control pool is available.
- `matched_pairs.csv`: written only when approximate target/control matching is possible.

These files are development inputs, not candidate-event results and not confirmed
exocomet catalogs. Raw large archive downloads and full catalog dumps should stay
out of Git unless there is a specific reproducibility reason and the files are
small.
