# Social Media Posts — AstroHunter KZ

All posts must be honest about the scientific result.
No discovery claims. No overclaiming.

---

## DO NOT SAY — Across All Platforms

These phrases are prohibited in any public communication about this project:

- "I discovered exocomets"
- "AI found exocomets"
- "AI detected planets"
- "NASA-level discovery"
- "confirmed exocomet"
- "Kazakhstan discovered exocomets"
- "my model proved that debris disks host exocomets"
- "our AI found signals that astronomers missed"
- "we confirmed the existence of exocomets around these stars"
- "the machine learning algorithm discovered astrophysical events"

If you are asked about these claims: "The project found no confirmed candidates.
The result is a negative result — and that is what I am presenting."

---

## 1. LinkedIn Post

*(Professional tone, 400–600 words, suitable for a tech/science professional audience)*

---

**I built an open-source exocomet search pipeline — and it found nothing. Here's why that's the point.**

For the past several months I've been building AstroHunter KZ: a fully
automated, end-to-end Python pipeline that searches NASA TESS photometry for
exocomet-like asymmetric transit candidates around debris-disk stars.

Here's what the pipeline does:

→ Downloads public TESS 2-minute light curves from the MAST archive
→ Runs a rolling-window asymmetric-dip detector (looking for the sharp-ingress,
   slow-egress shape that characterizes a comet's dust tail crossing a star)
→ Measures detector sensitivity using injection-recovery tests (synthetic signals
   injected into real TESS noise)
→ Trains a GradientBoostingClassifier on injection labels to score real events
→ Applies six automated vetting flags and three external catalog crossmatches
   (VSX, SIMBAD, TESS-EB)
→ Produces a manual review gallery with per-event light-curve inspection plots

And the result from our first matched-sample development run?

28 debris-disk target stars and 28 matched control stars scanned.
156 raw candidate events detected.
3 events passed automated vetting — all on a single overtriggered control star.
0 candidates survived conservative manual review.

That's a negative result. And I'm presenting it exactly as that.

Why does this matter? Because the most tempting thing to do with 156 "candidates"
is to select the most impressive-looking ones and stop there. The three events
that passed automated vetting had signal-to-noise ratios up to 34 and ML scores
of 0.85 — genuinely impressive numbers. But they were all on a control star that
produced 20 events — a strong indicator of repeated stellar variability, not
astrophysical comets. Without a matched control sample, those three events might
have become a headline. With the controls, they were correctly rejected as false
positives.

This is what rigorous science looks like in practice:
→ 453 automated tests covering every pipeline stage
→ A matched control sample to benchmark the detector's false-alarm rate
→ Multi-stage vetting: quality flags + ML ranking + catalog crossmatching + visual review
→ An explicit claims audit table documenting every claim the project can and cannot make
→ Full reproducibility from a fresh git clone — no private data, no proprietary APIs

The hypothesis — that debris-disk stars show more exocomet-like events — was not
supported in this development run. That's a real scientific contribution: it
shows the detector overtriggers on variable stars and needs tuning, and it
demonstrates what a rigorous null result looks like in automated astronomical
search pipelines.

Next steps: detector tuning, larger matched sample, multi-sector confirmation,
and expert visual review.

All code is public on GitHub. All results are auditable. No discovery claims.

If you're interested in exocomet searches, matched-sample photometric analysis,
or reproducible pipelines for time-domain astronomy — I'd love to connect.

[link to github.com/L4RBIX/astrohunter-kz]

#astronomy #openscience #python #machinelearning #TESS #exoplanets #reproducibleresearch

---

## 2. Threads / X Short Post

*(280 characters or under — punchy, honest)*

---

**Version A (result-focused):**

> I built an open-source pipeline to search 56 stars in NASA TESS data for
> exocomet-like signals. Found 156 raw events. After rigorous vetting: 0
> survived. Honest negative result. The false-positive control worked exactly
> as designed. Code is public.
> github.com/L4RBIX/astrohunter-kz

---

**Version B (process-focused):**

> The most important thing my pipeline produced wasn't a candidate — it was a
> rejection. Three high-SNR events on a control star correctly caught by the
> matched-sample design before anyone could overclaim them. That's what good
> science looks like.

---

**Version C (for a thread):**

> I spent months building AstroHunter KZ: a TESS exocomet search with matched
> controls, ML ranking, and catalog crossmatching.
>
> Result: 0 confirmed candidates.
>
> Thread on why that's actually the correct and important result. 🧵

*(Thread continues with 4–6 follow-up posts explaining the methodology and result in plain language)*

---

## 3. TikTok Video Script

*(60–90 seconds, casual and accessible tone)*

---

**[Opening — 0–5 seconds, hook visual: light curve with a dip]**

"NASA's TESS telescope watches hundreds of thousands of stars and records their
brightness every two minutes. When something passes in front of a star, the
brightness dips. I wrote a program to look for a very specific kind of dip."

**[5–20 seconds, explain the signal]**

"Exocomets — comets around other stars — leave a very distinctive fingerprint.
The dip is steep on the way in and gradual on the way out, because the comet's
dust tail sweeps slowly across the star. That asymmetric shape is what I'm
looking for."

**[20–35 seconds, explain the method]**

"I selected 28 stars known to have dusty debris disks — places where comets are
likely to exist — and compared them to 28 similar stars with no debris disk.
If exocomets are real and associated with disk activity, the first group should
show more of these dips. My pipeline automatically downloads the light curves,
runs a detector, uses machine learning to rank events, and checks each candidate
against astronomy databases."

**[35–50 seconds, the result]**

"The detector found 156 events. After all the checking? Zero survived. The three
best-looking events all came from a single control star — meaning a star that
was NOT supposed to show this signal — and that star had 20 events, which is a
classic sign of stellar variability, not comets."

**[50–65 seconds, the honest framing]**

"And here's the thing: that's actually a good result. Not because I found
exocomets — I didn't — but because my system correctly caught those false
positives. Without the matched control group, those three events might have
looked like real detections. With the controls, they were immediately suspicious."

**[65–80 seconds, close]**

"So the headline is: the search found nothing. And I'm presenting it honestly as
a negative result, not hiding it or overclaiming. The code is all public on
GitHub. The next step is a bigger sample and a better-tuned detector.

If you want to run an exocomet search yourself, the whole pipeline is there."

**[Text overlay throughout:** "No confirmed exocomets. Honest science." ]

---

## 4. Instagram Caption

*(Visual: the pipeline flowchart or a light-curve plot with event marker)*

---

**Caption:**

Built an end-to-end Python pipeline to search NASA TESS data for exocomet-like
signals around 56 stars. Six pipeline stages. 156 raw events. Automated flags.
Machine learning ranking. Catalog crossmatching. Manual review.

Final result: zero surviving candidates.

That's an honest negative result — and exactly what the matched-control design
was built to produce when the data doesn't support a claim.

The three most impressive-looking events? All on a single control star. Caught
and correctly rejected. Without the controls, those might have been reported as
candidates.

No discoveries claimed. All code public. 453 tests passing.

Science is knowing when not to overclaim.

🔭 github.com/L4RBIX/astrohunter-kz

#astronomy #astrophysics #tess #python #openscience #datascience #machinelearning #exoplanets #coding #stem

---

## 5. GitHub Repository Description (one-line and extended)

**One-line description (for the GitHub "About" field):**

> Open-source matched-sample TESS pipeline for exocomet-like asymmetric transit search. Dev run: 0 surviving candidates after rigorous vetting. Honest negative result.

**Extended description (for the README badge or "About" section):**

> AstroHunter KZ is an end-to-end, fully tested Python pipeline for searching
> NASA TESS photometry for exocomet-like asymmetric transit candidates using a
> matched target/control design. The development survey scanned 28 debris-disk
> target stars and 28 matched control stars, found 156 raw candidates, and
> retained zero after conservative automated and manual vetting. This is an
> honest negative result with a validated, reproducible research tool.
>
> 453 automated tests | No private data | No discovery claims | Fully reproducible

---

## Usage Notes

1. Always link to the repository so people can verify the methodology.
2. If asked about a "discovery": "The project found no confirmed exocomet
   candidates. The result is a negative result."
3. Do not round up the result to "we found signals" or "we identified candidates."
   The final result is zero surviving candidates.
4. The machine-learning component is a ranking tool, not a detection engine.
   Never say "AI detected" or "AI discovered."
5. The project's value is in the pipeline, the methodology, and the honest
   negative result — not in any astrophysical claim.
