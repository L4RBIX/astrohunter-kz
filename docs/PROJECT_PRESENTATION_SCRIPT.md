# Project Presentation Script
## AstroHunter KZ — Science-Fair / Competition Presentation

**Target duration:** 4–6 minutes spoken at a comfortable pace
**Audience:** Science-fair judges, research competition panels, or interested non-specialists
**Format:** Can be delivered as a stand-alone talk or alongside a poster

---

## SPOKEN SCRIPT

---

### Opening Hook (30 seconds)

"In 1987, astronomers noticed something strange about the star Beta Pictoris.
Its brightness would sometimes dip suddenly — and then recover slowly, like
something was casting an asymmetric shadow across it. We now believe those
shadows are comets. Dusty comet tails blocking starlight as they orbit the star.

The question I asked was: can I build a machine to search for those signals
across hundreds of stars — automatically — and can I do it rigorously enough
to actually trust the results?"

---

### The Problem (45 seconds)

"NASA's TESS satellite has been watching hundreds of thousands of stars since
2018. Every two minutes, it records the brightness of each star it observes.
That's an enormous dataset — and it's completely public.

The challenge is that TESS data is full of noise. Stellar variability,
instrument artifacts, background stars, cosmic rays — all of these can look
like a dip in a light curve if you're not careful. An automatic search run
without proper controls will produce thousands of false alarms.

So my first design decision was: don't just search. Compare. Pick a group of
target stars — specifically stars known to have dusty debris disks, like the
material left over from planet formation — and compare them to a matched set
of similar stars with no debris disk. If exocomets are real and associated
with disk activity, the target stars should show more events."

---

### The Data (30 seconds)

"I used public debris-disk catalogs — stars confirmed by their excess infrared
emission — and matched them to similar non-disk control stars from the same
TESS observing fields, similar brightness, and similar stellar types.

All light curves came from the public MAST archive through the lightkurve
Python library. No private data. No proprietary observations. Everything is
openly reproducible from a fresh code clone."

---

### What I Built (60 seconds)

"I built a six-stage pipeline in Python:

Stage one: Download and clean TESS light curves.

Stage two: Run an asymmetric-dip detector. This scans each light curve for
brightness dips that are sharper on the way in than on the way out — the
signature shape of a comet's dust tail sweeping across a star.

Stage three: Injection-recovery testing. I inject thousands of synthetic comet
signals into real TESS noise and measure how many the detector catches. This
tells me the detector's sensitivity.

Stage four: Machine learning ranking. I trained a gradient-boosted classifier
on the injection results to score real candidates by how comet-like they look.
This is ML as a *triage tool*, not a discovery tool.

Stage five: Automated vetting. Six quality filters flag events that are likely
noise — low signal, edge artifacts, flare-like morphology.

Stage six: External catalog crossmatching and manual review. I checked each
candidate star against three professional astronomical databases to identify
known variables and eclipsing binaries. Then I inspected the highest-priority
events visually.

The whole system has 453 automated tests, runs from a fresh clone without
private API keys, and produces fully auditable output tables."

---

### The Result (60 seconds)

"Here are the exact numbers.

I scanned 28 debris-disk target stars and 28 matched control stars. The
detector found 156 raw dip-like events across both groups.

After automated vetting: 3 events passed. All three were on the same star —
a control star called TIC 444335503 — which produced 20 candidate triggers.
That's already suspicious. No debris-disk target passed automated vetting.

After manual review of 41 high-priority events: zero candidates were retained
as keep_candidate. The three automated-pass events on TIC 444335503 were
labelled likely variable star — the light curve shows repeated large dips
consistent with stellar variability, not single rare comet transits.

The raw event rate ratio was 0.58 target-to-control, meaning the controls
actually triggered more events than the targets. That's the opposite of what
the hypothesis predicts.

The conclusion: this development run produced a negative result. The hypothesis
was not supported."

---

### Why No Discovery Claim (45 seconds)

"I want to be explicit about why I am not claiming to have found anything.

A single detection in one TESS sector is not enough. You need multi-sector
consistency. You need expert review. Ideally you need follow-up spectroscopy.
And most importantly, you need a candidate that survived rigorous vetting —
which none of mine did.

The three events that looked most impressive turned out to be from a control
star with obvious variability. That's exactly what the control design is for:
to catch false alarms before they become false claims.

I believe science is done a disservice when automated tools produce lists of
'candidates' without the honest vetting work to back them up. This project
shows the full pipeline — including the part where everything gets rejected."

---

### Why This Still Matters (45 seconds)

"A negative result with a working pipeline is still genuinely valuable.

First: the pipeline is real and it works. Any astronomer or student can clone
it, point it at their own TESS targets, and use it. That's the value of
open-source reproducible science.

Second: the failure mode is documented. The detector overtriggers on variable
stars. I now know exactly what needs to be fixed. That's a concrete result, not
a dead end.

Third: false-positive control worked. Without the matched control sample, TIC
444335503's three pass events could have been reported as exocomet candidates.
With the controls, they were instantly recognized as suspicious.

And fourth: this demonstrates that rigorous, honest analysis of large
astronomical datasets is something a student can do — using publicly available
tools, open data, and careful engineering."

---

### Future Work (30 seconds)

"If I continue this work, the next steps are:

One: tune the detector to suppress repeated events on the same star.
Two: expand the sample to 100+ stars per group.
Three: require multi-sector consistency before any event is taken seriously.
Four: bring in an expert collaborator for the manual review step.

The scientific question — do debris-disk stars show more exocomet-like transit
events? — is still open. This project built the tool to answer it properly.
The answer just needs more data and a better-calibrated detector."

---

### Closing (30 seconds)

"I started this project because I wanted to search for exocomets using real
NASA data and real software engineering. I ended up with something more
interesting than a list of candidates: a complete, tested, honest pipeline
that found nothing — and knew why it found nothing.

In science, knowing why you found nothing is the beginning of knowing where
to look next. The code is public. The data is public. The result is
documented and defensible.

Thank you."

---

## JUDGE Q&A SECTION

*Prepare for these questions. Practice answering in 20–30 seconds each.*

---

**Q1: Did you discover an exocomet?**

"No. The project found zero surviving candidates after conservative vetting.
The three automated-pass events all came from a control star showing repeated
variability. A discovery claim would require surviving multi-stage vetting,
multi-sector confirmation, and expert review. None of those conditions were
met. The honest result is a negative result."

---

**Q2: Why is a negative result still useful?**

"Several reasons. It shows the pipeline works — the false-positive control
design correctly caught and rejected the most suspicious-looking events.
It documents a specific failure mode in the detector: overtriggering on
variable stars. And it produces a validated, reproducible tool that future
researchers can build on. Negative results are not failures; they redirect
effort in the right direction."

---

**Q3: Why do you compare target stars to control stars?**

"Without controls, you can't tell whether a candidate event is associated with
the thing you're looking for, or just a property of TESS data in general. If
I only searched debris-disk stars and found dips, I couldn't know whether any
star in that part of the sky shows similar dips. By matching controls on
brightness, TESS sector, and stellar type, I can isolate any excess signal
to the debris-disk property specifically. In this run, there was no excess —
controls showed more raw events than targets."

---

**Q4: What did machine learning actually do?**

"The ML model was a gradient-boosted classifier trained on synthetic comet
signals injected into real TESS noise. It learned to distinguish injection-like
patterns from random noise. For real data, it scores each detected event from
0 to 1. But the training labels come from synthetic data, not from confirmed
real exocomets. So the model ranks events by how comet-like they *look*, not
whether they are real. It's a triage tool, not a discovery engine."

---

**Q5: How do you know the candidates are not real?**

"Several lines of evidence. First, all three automated-pass events came from
a single star — not what you'd expect from rare, random comet transits.
Second, that star is a control star not selected for disk activity. Third, the
pattern of events — repeated, with similar shape and depth — is more consistent
with periodic stellar variability than single comet passages. Fourth, the
event rate on this star is twenty times higher than any other star in the
survey. And fifth, manual inspection of the light curves showed no convincing
single-transit asymmetric morphology."

---

**Q6: What would you do next?**

"Three things. First, tune the detector to add explicit overtrigger suppression
and periodic-variability rejection. Second, expand the sample size — 28 stars
per group is too small to draw statistical conclusions. Third, require multi-sector
confirmation, meaning a candidate must appear in independently observed TESS
sectors months apart before it's considered at all. With those improvements,
the pipeline could produce results that are actually publication-ready."

---

**Q7: Why is TIC 444335503 important?**

"TIC 444335503 is actually the most important star in this study — but for
the opposite reason from what you'd expect. It's a control star that produced
20 candidate events, three of which passed automated vetting with impressive
signal-to-noise ratios. If this project had no control sample, those three
events might have been called exocomet candidates. Instead, because it's a
control star in a matched-sample design, its high event count immediately
flagged it as an overtriggered false positive. The control design worked
exactly as intended."

---

**Q8: What makes this project different from just using AI?**

"The AI — the machine-learning part — is actually a small component of the
pipeline. Most of the work is about building a system that rigorously controls
for false positives: matched controls, six automated vetting flags, external
catalog crossmatching against three professional databases, manual review with
documented disposition labels, and an explicit claims audit. AI without that
infrastructure would have produced a long list of impressive-looking candidates
with no way to evaluate which are real. This project shows that the vetting
framework matters more than the detection algorithm."

---

*End of script and Q&A*
