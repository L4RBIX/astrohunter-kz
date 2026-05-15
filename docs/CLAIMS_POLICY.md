# Claims Policy

AstroHunter KZ is a candidate-event search and statistical-comparison project.
It does not claim professional confirmation of exocomets.

Allowed wording:

- candidate dip-like feature
- candidate asymmetric event
- exocomet-like candidate
- positive-control recovery test
- requires follow-up validation

Forbidden wording unless professional confirmation exists:

- confirmed exocomet
- discovered exocomets
- AI discovered
- NASA-level model

Every result table, figure caption, README summary, notebook, and draft paper
must make clear that detections are candidates only. Strong events may be
instrumental/systematic until quality flags, multi-sector consistency, stellar
variability checks, background contamination checks, and independent review are
complete.

## Phase 4 ML-Specific Rules

Additional forbidden wording for ML outputs:

- "the ML model confirms"
- "AI discovered exocomets"
- "the model identified real exocomets"
- "AUC of X% means X% of candidates are real"

Required wording for ML outputs:

- "the ranker is trained on synthetic injection-recovery labels"
- "the score ranks candidates for human review"
- "injection-trained metrics do not describe real-data purity"
- "all ranked candidates require vetting and follow-up"

The `final_candidate_score` column is a prioritisation aid, not a posterior
probability of exocomet detection.  Feature importance plots describe what
makes a synthetic injection recoverable, not what distinguishes real exocomets
from noise.
