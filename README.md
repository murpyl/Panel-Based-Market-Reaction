# Deviation-from-Baseline Rhetoric as a Predictor of Abnormal Market Reactions

A pre-registered study testing whether a public figure's departure from their own typical
posting style (measured as embedding distance from a rolling personal centroid) predicts
abnormal market volatility in the minutes following a post. 
The pre-registered statement can be found at `PREREGISTRATION.MD`.

**Result:** the pre-registered primary test (15-minute
horizon) was directionally consistent and nominally significant before correction
(p = 0.0202), but **did not survive Bonferroni correction** for the pre-specified 3-horizon
comparison family (corrected p = 0.0606). The full results, including a secondary pattern
that's more consistent with the study's own null hypothesis than its main one, are below./

Please reach out if you wish to see the data.

---

## 1. The question

> Deviation-from-baseline is tested as a predictive feature for abnormal volatility/volume,
> against the explicit alternative hypothesis that it is a proxy for exogenous news
> co-occurrence rather than an independent signal from the post's content itself.

This is **not** a claim that a post *causes* a market reaction. The design tests whether
"how unusual is this post for this specific author" carries predictive information about
what happens to their company's stock in the following minutes, above and beyond the
possibility that unusual posts simply coincide with real news that would have moved the
stock regardless.

## 2. Data and panel

| Account | Ticker | Role | Data window | Notes |
|---|---|---|---|---|
| Satya Nadella | MSFT | Null baseline | Jan 2024–Jul 2026 (full) | Only account with no API cap hit |
| Marc Benioff | CRM | Confirmatory | Jun 2025–Jul 2026 | Sets the shared window boundary |
| Aaron Levie | BOX | Confirmatory | Jun 2025–Jul 2026 | Documented low bar-coverage limitation (~51%) |
| Cristiano Amon | QCOM | Confirmatory | Jun 2025–Jul 2026 | |
| Vlad Tenev | HOOD | Confirmatory | Jun 2025–Jul 2026 | Highest posting rate in the confirmatory group |
| Tobias Lütke | SHOP | Exploratory only | Dec 2025–Jul 2026 | Demoted — see below |
| Elon Musk | TSLA | Dropped | — | See below |

**Panel construction decisions:**
- **Musk dropped entirely** — the X API's 3,200-post hard cap limited his reachable history
  to ~6 months regardless of budget, and independent of that constraint, his current posting
  mix appears dominated by political/personal content rather than business commentary,
  undermining the "stable baseline rhetoric" assumption the core feature depends on. In short,
  he tweets too much. 
- **Tobi (SHOP) demoted to exploratory-only** — the same structural cap limited his history
  to ~7 months, which would have forced the entire panel's shared window down to 7 months.
  Dropping him and anchoring on Benioff's boundary instead yields a 13-month window with
  more total data. His data was moved to the lower-rigor tier.
- **BOX's low bar coverage (~51% vs. 80–93% for the other tickers)** was diagnosed via
  time-of-day gap clustering and volume correlation, and is consistent with genuine thin
  liquidity on IEX rather than a data-pull artifact. Documented as an accepted limitation.

## 3. Methodology

**Primary feature — deviation from personal centroid.** Each post is embedded
(`sentence-transformers/all-mpnet-base-v2`, run locally for reproducibility), and compared
via cosine distance against the mean embedding of that same author's posts in the trailing
180 calendar days — strictly prior posts only, point-in-time correct. A minimum of 20 prior
posts is required in-window, or the post is excluded as having insufficient history (this
only affects the first few weeks of each account's data).

**Labels.**
- *Return*: market-adjusted (net of SPY over the same window), not raw price movement.
- *Abnormal volatility*: realized volatility of the window compared against that specific
  ticker's own historical distribution for the same 30-minute time-of-day bucket, using an
  **empirical 90th-percentile threshold** rather than a parametric z-score — volatility is
  right-skewed, so a Gaussian cutoff would misstate the true tail probability. Baseline
  windows that overlap any actual post's measurement window are excluded from that baseline,
  to avoid the "normal" distribution partially absorbing the effect being measured.

**Confound exclusion.** Posts whose measurement window overlaps a scheduled macro release
(FOMC, CPI, jobs report) or that ticker's earnings window are excluded from the confirmatory
test, checked as a full interval overlap rather than a single point-in-time check.

**Windows.** Primary horizon: 15 minutes (pre-registered, latency-justified — a ~30–45
second pipeline latency budget is a much smaller fraction of a 15-minute window than a
5-minute one). 5-minute and 60-minute horizons are pre-registered as **exploratory-only**.
Posts with incomplete bar coverage in their window are still included if a majority of the
window's bars are present (scaled proportionally per horizon), otherwise excluded.

**Statistical design.**
- *Primary confirmatory test*: one pooled logistic regression (`abnormal_volatility_flag ~
  deviation_score`) across all confirmatory-eligible rows (4 accounts), with cluster-robust
  standard errors clustered by author — accounting for within-author correlation.
- *Multiple-comparison correction*: plain Bonferroni across the 3 pre-registered horizons
  (5-min, 15-min, 60-min).
- *Out-of-fold validation*: leave-one-account-out cross-validation combined with walk-forward
  time splitting — for each held-out account, every prediction is made using only data from
  the other 3 accounts that occurred strictly before that specific post, refit per test
  point. This is descriptive/diagnostic, not the inferential test itself.
- *Model*: logistic regression as primary, a shallow gradient-boosted tree run alongside for
  comparison — deliberately simple, matched to a sample size in the low thousands.

## 4. Results

### 4.1 Primary test across all three horizons

| Horizon | n | Coefficient (per SD) | Cluster-robust SE | z | Raw p | Bonferroni-corrected p | Significant at α=0.05? |
|---|---|---|---|---|---|---|---|
| 5-min (exploratory) | 1,179 | 0.0439 | 0.0806 | 0.545 | 0.5858 | 1.0000 | No |
| **15-min (primary)** | 1,058 | **0.2229** | 0.0960 | 2.323 | **0.0202** | **0.0606** | **No** |
| 60-min (exploratory) | 1,146 | 0.4467 | 0.1197 | 3.731 | 0.0002 | 0.0006 | Yes |

**The pre-registered primary hypothesis is not confirmed.** At the pre-specified 15-minute
horizon, after correcting for the planned 3-horizon comparison family, the effect does not
reach significance. It is directionally consistent with the hypothesis and was nominally
significant uncorrected — but reporting the uncorrected number as the headline result would
be exactly the kind of post-hoc cherry-picking the correction exists to prevent.

### 4.2 Out-of-fold cross-validation (descriptive, not inferential)

| Model | Overall AUC |
|---|---|
| Logistic regression | 0.610 |
| Shallow GBT | 0.642 |

Per-account AUC reveals meaningful heterogeneity that the pooled test can't distinguish from
a uniform effect: two accounts show AUC in the 0.73–0.78 range (a real signal), while the
other two sit at 0.57–0.60 (barely above chance). The primary test's pooled coefficient is
consistent with either "a real, modest, uniform effect across the panel" or "a real effect in
half the accounts and near-nothing in the other half" — these are different scientific claims
that this design cannot separate without a follow-up interaction test (not run here; flagged
as a natural next step, not part of the pre-registered design).

### 4.3 A pattern worth taking seriously against the study's own hypothesis

The effect is essentially absent at 5 minutes, modest and fragile at 15 minutes, and
strongest — and still climbing — at 60 minutes. If a post's content were directly driving a
market reaction, the expected shape is closer to the opposite: strongest immediately after
the post, flat or decaying over the following hour. A signal that's weak immediately and
only emerges strongly an hour later is more consistent with something slower-moving during
that window — a story spreading, other outlets picking it up — which is close to a paraphrase
of this study's own pre-registered alternative hypothesis (exogenous news co-occurrence)
rather than its main one. This pattern doesn't prove the alternative explanation, but it's
a genuine reason for caution before treating the 60-minute result as a stronger version of
the same finding, rather than a caveated, separate result — it's exploratory-only for exactly
this reason.

## 5. Limitations

- **Only 4 clusters (accounts)** for the cluster-robust standard error in the primary test.
  Cluster-robust inference is an asymptotic (large-sample) result; with 4 clusters the SE
  should be treated as indicative, not precise.
- **BOX's ~51% bar coverage** is a documented, accepted limitation, not fully solved —
  volatility/return measurements for BOX posts rest on thinner underlying data than the
  other 3 confirmatory tickers.
- **Different horizons have different effective sample sizes and base rates** (positive rate
  ranges from 7.5% at 60 min to 20.9% at 5 min), because each horizon's abnormal-volatility
  threshold is calibrated independently against its own baseline. Cross-horizon comparisons
  should be read with that in mind, not treated as fully apples-to-apples.
- **This design tests prediction, not causation.** Even a fully confirmed result would not
  establish that the post itself caused the reaction — only that deviation-from-baseline
  carries predictive information beyond what the confound-exclusion windows control for.
  The GDELT news-co-occurrence check (below) is the tool that would move closer to a causal
  claim, and was not implemented.
- **Small, non-random panel.** 4 confirmatory accounts were selected by data availability
  (API caps) as much as by design and are not a representative sample of "public company
  executives" in any statistical sense.

## 6. Possible next steps

1. **GDELT news-co-occurrence control** (pre-registered as optional stretch scope, not
   required) — now more valuable than originally scoped, given the 60-minute pattern above.
   Bucketing flagged events into "high deviation + co-occurring news" vs. "high deviation +
   no detected co-occurring news" would directly test whether the signal survives once
   likely news confounds are accounted for.
2. **Deviation x account interaction test** — to formally check whether the per-account AUC
   heterogeneity reflects a real difference in effect size across accounts, or is consistent
   with sampling noise around one true effect.
3. **A larger, more representative panel** — the current 4 accounts were shaped as much by
   API access constraints as by deliberate sampling design.

## 7. Repository structure and how to run

Pipeline order (each stage's output feeds the next):

| Order | Script | Purpose |
|---|---|---|
| 1 | `build_confound_calendar.py` | Generates `confound_calendar.csv` (FOMC, CPI, jobs, earnings) |
| 2 | `pull_bars.py` | Pulls and session-tags 1-min bars for all tickers + SPY |
| 3 | `pull_tweets.py` | Pulls posts per account, retry/resume-aware |
| 4 | `tag_data.py` | Descriptive-only market-relevance tagging |
| 5 | `combine_tickers`, `join_together`, `multi_join_together` | Join step | Resolves each post to its reaction window; timestamp/timezone sanity-checked by hand on one account first |
| 6 | `reaction_labels.py` | Market-adjusted return, abnormal-volatility label, confound exclusion |
| 7 | `compute_deviation.py` | Embedding-centroid deviation feature, point-in-time correct |
| 8 | `assemble_final_panel.py` | Merges labels + features, applies tier and eligibility rules |
| 9 | `build_confirmatory_model.py` | Primary confirmatory test + LOAO walk-forward CV |

To reproduce the Bonferroni table above, run steps 6–10 three times with the window
parameters set to 5/15/60 minutes respectively, then combine the three primary-test p-values
as shown in Section 4.1.

## Disclaimer

This project is for personal research and educational purposes only. It does not constitute financial advice, and no output from this project is provided to, or intended for use by, anyone other than the author.
