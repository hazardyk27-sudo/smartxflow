# SmartXFlow Agent Rules

**Repository:** `hazardyk27-sudo/smartxflow`

This file is the short common bootstrap for the active specialized learning workflow. Keep it in session context after one read.

## Canonical instruction branch

- For `PREDICTOR` and `DEVELOPMENT` conversations, `preview` is the canonical source of active specialized role instructions and Current Milestones.
- `main:/AGENTS.md` remains the repository/release/safety supplement and must also be respected.
- Do not fall back to stale role definitions on `main` when the active files exist on `preview`.

## Executable Predictor policy — HARD PRECEDENCE

Predictor workflow invariants are machine-readable and code-validated under:

- `predictor_policy/policy.json` — canonical executable rule registry;
- `predictor_policy/validator.py` — deterministic Stage 1/2/3 and price-truth validator;
- `predictor_policy/stage_comparison.py` — Stage 1 baseline vs Stage 3 final-preference comparison.

For Predictor workflow behavior, these executable rules control over conflicting or stale wording in lower-level markdown summaries. Markdown remains human-readable explanation. A Predictor stage must not be treated as valid when the corresponding validator would reject its structured payload. Rule violations must be surfaced by rule ID; do not silently relax, skip or reinterpret a hard rule to complete a task faster.

## Session loading

There are exactly two conversational SmartXFlow roles for this workflow:

- `PREDICTOR` — researches selected matches, publishes formal decisions, settles them, and automatically preserves selected cases.
- `DEVELOPMENT` — builds/maintains archive integrity, datasets, features, tests, models and controlled improvements.

At the start of a specialized session read once, in this order:
1. `main:/AGENTS.md`
2. `preview:/AGENTS.md`
3. only your own `preview:/.agents/roles/<ROLE>.md`
4. only your own `preview:/.agents/milestones/<ROLE>.md`

For every Predictor workflow, also load `predictor_policy/policy.json` once and treat it as executable truth. Do not routinely reread the remaining instruction files. Open detailed contracts only when the active task requires them.

## Shared learning rules

1. Existing SmartXFlow systems remain the source of live/stored SXF snapshots. Do not build a second scraper for learning.
2. Archive only matches materially researched by Predictor and formalized as `BET` or `WATCH` with a concrete non-empty market and selection. A match with no defensible formal action is omitted from the formal case archive rather than stored as a fake `PASS` case.
3. **The final prediction diary and the Learning Archive case store are separate mandatory artifacts. Individual case folders, `manifest.jsonl` events, settlements, captures or postmatch addenda NEVER count as the daily diary and must never be described as if they do.**
4. `prediction_at` is the immutable PRE/POST cutoff.
5. External evidence is PRE only when actual `observed_at <= prediction_at`; publication time alone is insufficient.
6. Historical prediction, rationale, counterargument, confidence, result, raw snapshots and evidence timestamps are never silently rewritten. Corrections are append-only.
7. POST information may be used for settlement/diagnosis/labels, never as PRE training input for that prediction.
8. Poly/Polymarket intelligence is excluded from this Learning Engine.
9. A win/loss is evidence, not proof. New rules require repeated evidence and time-ordered validation.
10. No model/method silently changes production. Candidate -> historical test -> shadow -> review -> controlled promotion/rejection.
11. Enforce critical rules in code/tests where practical.

## Stage 1 source universe vs candidate set — HARD RULE

The user's date/time/named-match request defines the **source universe to scan**, not a requirement to dump every fixture into the report.

- Stage 1 must internally inspect every valid fixture that satisfies the user's explicit scope criteria.
- Stage 1 then selects and reports only matches with analytically useful, attention-worthy SXF behavior: meaningful money/price interaction, divergence, persistence, acceleration, reversal, cross-market confirmation or another defensible SXF reason.
- A screened-out fixture is not a prediction row and does not need a user-visible preference.
- Every reported Stage 1 candidate must preserve a concrete frozen native `SXF PREFERENCE` and at least one explicit attention reason.
- The exact reported Stage 1 candidate set becomes the default carry-forward set for Stage 2 and Stage 3 unless the user changes it.
- Do not confuse **screening** with an arbitrary eligibility filter. The full requested source universe is still scanned; only the useful candidates are surfaced.
- If the user explicitly requests every scanned match to be shown, show them all; otherwise the default is scan-all, report-candidates.

## HARD INVARIANT — EVERY VISIBLE MATCH HAS ONE CONCRETE PREFERENCE

This rule is absolute for every valid match that is actually shown in Predictor output, including reported Stage 1 candidates, Stage 2 carry-forward summaries, Stage 3, recap tables and non-archived `Gelecek Günler` reports.

### Preference and action are different fields

Every visible match MUST always have both concepts kept separate:

1. **PREFERENCE / TERCIH** = the single best-current analytical market + exact selection for that match.
2. **ACTION / KARAR** = whether that preference is currently strong enough to act on (`BET/AL`, `WATCH/IZLE`, `PASS/GEC`, or the applicable workflow label).

The action label may change or downgrade. **The preference may never disappear from a visible prediction row.**

### Exceptionless output requirement

For every valid match row shown to the user:

- `preference.market` MUST be concrete and non-empty;
- `preference.selection` MUST be concrete and non-empty;
- user-facing wording MUST state the selection explicitly, e.g. `Fulham kazanir`, `Beraberlik`, `2.5 Alt`, `Lyon kaybetmez (X2)`, `Frosinone +1.5`;
- if the current real price is known, show it;
- if a non-native execution market is preferred but its real price is unknown, keep the market/selection and say `fiyat dogrulanmadi` or state a clearly labeled minimum acceptable threshold; never invent odds.

The following are forbidden in any preference/selection field:

- `Bahis yok`
- `Tercih yok`
- `No pick`
- `None`
- `N/A`
- `—`
- empty/null selection
- wording whose practical meaning is “I refuse to choose a side/market”

### PASS / GEC can NEVER mean “no preference”

`PASS` / `GEC` has exactly one permitted meaning:

> **A concrete analytical preference exists, but current confidence/risk/value/evidence quality is not strong enough for formal action or archive.**

Therefore:

- `Tercih: Atletico Madrid kazanir @1.91 | Karar: GEC` = VALID.
- `Tercih: Barcelona kazanir @1.10 | Karar: GEC` = VALID.
- `Tercih: Bahis yok | Karar: GEC` = INVALID.
- `Tercih: — | Karar: PASS` = INVALID.
- `PASS because no defensible formal bet exists` MUST still retain the best-current analytical preference.
- `no formal case`, `not archived`, `C grade`, `low confidence`, `mixed evidence`, `contradicted research`, `unknown alternative price`, or `material reversal` MUST NOT be interpreted as permission to blank/remove the preference.

### Stage-specific enforcement

- **Stage 1:** every **reported candidate** has one frozen native `SXF PREFERENCE` with exact market + exact selection. Screened-out fixtures are not prediction rows and may be omitted from the user-facing Stage 1 report.
- **Stage 2:** the exact reported Stage 1 candidate set carries forward by default. Stage 1 preference remains visible/frozen; research may confirm or contradict it but may not erase it. If Stage 2 suggests a better future execution expression, record that separately without deleting the frozen preference.
- **Stage 3:** every carried candidate must end with one concrete best-current execution preference **before** assigning `BET/WATCH/PASS`. Grade/action is applied to that preference; it is not a substitute for it.
- **Gelecek Gunler:** every listed match must have one concrete best-current preference even when the report labels it `AL`, `IZLE`, or `GEC`.

### Precedence / anti-misinterpretation rule

This invariant controls the interpretation of every lower-level phrase such as:

- `PASS / no formal case`;
- `if no formal selection is defensible`;
- `do not force a bet`;
- `downgrade to WATCH/PASS`;
- `omit from archive/diary`.

Those phrases govern action/archive eligibility only. They NEVER authorize an empty user-visible preference.

If another Predictor instruction can be read in two ways, always choose the interpretation that preserves:

`ONE VISIBLE MATCH -> ONE CONCRETE PREFERENCE -> SEPARATE ACTION LABEL`

Do not ask the user to choose between candidate preferences merely because confidence is low. The Predictor must rank the available evidence and name its single best-current preference while honestly downgrading the action/confidence if necessary.

A truly invalid/unresolvable fixture identity is not a prediction row: report it explicitly as an identity/data error rather than disguising it as `PASS`, `GEC`, or an empty preference.

## User-supplied execution prices — HARD RULE

SmartXFlow does not natively store every execution market. The user may supply a real observed price for an exact non-native market/selection, e.g. `Frosinone +1.5 @1.72`.

- Store origin/source as `USER_SUPPLIED`.
- Preserve the exact market, exact selection and exact numeric price supplied by the user.
- `observed_at` is the user's explicitly stated observation time when provided; otherwise use the message receipt time.
- A clear `USER_SUPPLIED` observed price is valid price evidence and does not require independent web verification.
- Never alter the user's number, transfer it to another market/selection, synthesize a new price, or silently refresh it later.
- If the price is ambiguous or stale, mark it `STALE` / `NEEDS_CONFIRMATION` or use it only as a conditional threshold; it cannot support a formal priced BET while stale.
- A threshold is never actual odds.

## Stage 1 vs Stage 3 performance comparison — MANDATORY LEARNING OUTPUT

The system must measure whether later research/execution logic actually improves the initial SXF baseline.

For every settled Stage 1 candidate:

1. Preserve the frozen Stage 1 market/selection as the baseline.
2. Grade that Stage 1 baseline against the real result, even when Stage 3 later changes the preference or action becomes PASS.
3. Separately grade the final Stage 3 best-current preference hypothetically, regardless of BET/WATCH/PASS action.
4. Compare both on the **same matched case set** and report:
   - Stage 1 baseline hit rate;
   - Stage 3 final-preference hit rate;
   - hit-rate delta;
   - changed vs unchanged preference count;
   - `IMPROVED / WORSENED / SAME / UNRESOLVED` transitions;
   - one-unit hypothetical ROI for each stage only where real observed prices exist.
5. Treat this delta as evidence about Stage 2/Stage 3 added value. Never claim that external research helps merely because selected anecdotes won.
6. Development must use the matched comparison to test whether Stage 2 information and execution transformations improve, worsen or merely reshuffle Stage 1 performance.

Canonical implementation: `predictor_policy/stage_comparison.py`.

## Learning Archive

- No separate repository is used.
- Canonical repository: `hazardyk27-sudo/smartxflow`.
- Canonical data branch: `learning-archive`.
- Canonical data folder: `/learning_archive_data/`.
- Application/source development remains on `preview`; archive data commits remain isolated on `learning-archive` and are never deployed/promoted to production.
- Predictor automatically creates the immutable case plus first stored-history capture when a formal selected case is published; later prematch revisits append captures; settlement writes the final package.
- Development reads the same archive folder.
- No archive-specific GitHub repository or token may be required. Durable programmatic writes may reuse normal SmartXFlow repository GitHub credentials/connector.
- Writing files only into a runtime/worktree is not durable and must never be reported as `DONE`. `DONE` requires validator PASS, checksum/manifest verification and a confirmed GitHub commit/reference on the archive data branch.
- Re-running identical writes is idempotent. Same case/event with materially different historical payload fails closed; factual corrections use append-only addenda/versioned records.
- Never place secrets in archive payloads, manifests, captures, evidence, logs or addenda.

## Daily Prediction Diary — exactly two separate mandatory artifacts

For every calendar day that contains at least one formal Stage 3 `BET` or `WATCH`, Predictor MUST automatically create exactly two distinct day-level diary artifacts under:

`learning_archive_data/diaries/YYYY/MM/DD/`

They are mandatory even when every per-match Learning Archive case is already `RECORDED`/`FINALIZED`. The user must not need to remind the Agent to create them.

### Diary 1 — `predictions.md` — written when final preferences are issued

Create/update immediately after Stage 3 final preferences are given, using only information known at that prediction time.

For every formal final match include at minimum:
- match identity;
- final category: `BET`, conditional-BET/execution view, or `WATCH`;
- execution market + selection;
- actual price or explicitly labeled minimum acceptable threshold;
- confidence and immutable `prediction_at`;
- linked `case_id` / archive state;
- **`Why this prediction`**: a short 1–3 sentence note explaining why the Agent chose that prediction at that moment. It must summarize the decisive SXF signal(s), Stage 2 context and/or risk-value reasoning, plus the most relevant caution when material.

This note is a contemporaneous prediction rationale, not a post-result explanation. It must never contain later score/result knowledge.

### Diary 2 — `postmatch.md` — written after results are known

Create/update after settlement/end-of-day review.

For every diary match include at minimum:
- original immutable prediction;
- final score/result;
- WIN / LOSS / VOID, or hypothetical WIN/LOSS for WATCH;
- **`Why it won/lost`**: a short 1–3 sentence postmatch note explaining why the prediction appears to have succeeded or failed, using the final prematch SXF behavior, football context and actual match result.

The `Why it won/lost` note must be analytical, not merely repeat the score. It should identify the most plausible driver(s), for example:
- original thesis was confirmed;
- the recorded counterargument materialized;
- late money/price reversal or resistance mattered;
- execution line was too aggressive/too conservative even if the underlying thesis was sound;
- Stage 2 football context proved decisive or misleading;
- normal football variance remained the best explanation.

Never rewrite the original prediction/rationale after seeing the result. Postmatch interpretation is append-only learning.

### Hard completion rules

- `cases/YYYY/MM/DD/<case_id>/` is case evidence, not either diary.
- `manifest.jsonl` is an event index, not either diary.
- `settlement.json`, `sxf_snapshots.json.gz`, checksums and per-case addenda are case package artifacts, not either diary.
- Never say or imply “the diary exists because the cases were archived.”
- `predictions.md` and `postmatch.md` are independent mandatory artifacts; one never substitutes for the other.
- If `predictions.md` is missing, prediction-day status is `DIARY_PENDING`.
- If results are available and any match lacks its postmatch note, end-of-day status is `DIARY_PENDING`.
- A day is not end-of-day `DONE` until required case archive state and both diary artifacts with per-match notes are durable on `learning-archive`.
- WATCH outcomes remain hypothetical; never convert them into retroactive bets.
- Conditional-BET execution must not be claimed unless a qualifying real price was actually verified or explicitly supplied by the user as a current observed price.
- Diary summaries must reference immutable case truth rather than rewrite it. Corrections are append-only/versioned; never silently alter historical decisions.

See `/.agents/contracts/LEARNING_ARCHIVE.md` when archive/export/validation work requires it.

## Source and release essentials

- GitHub source/history is canonical.
- `main` = latest user-approved production SHA.
- `preview` = development/Preview branch and active specialized-agent instruction branch.
- `learning-archive` = selected-match data only; it is not deployed and does not participate in source promotion.
- Replit Preview is only a runner for the exact GitHub `preview` SHA; never use Replit Agent to edit/sync source.
- Hetzner is production runtime; never edit production files in place.
- User approval is required before promoting `preview` to `main` or deploying production.
- Never force-push, rebase, reset, cherry-pick, or improvise around divergence.
- The user's personal computer is never a work target.

For an actual release/sync/deploy task, open `/.agents/contracts/RELEASE_FLOW.md` and follow it exactly.
