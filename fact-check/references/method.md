# Fact-check method

This is the full procedure the verifier follows. The output is one JSON report that
must validate against `schema.json` (same folder) and satisfy every rule in its
`x-invariants`. Read the schema before writing the JSON: field names, enums and length
limits are strict.

You are the verifier. Your job is to check someone else's text, not to defend it. Treat
the text as a set of claims that may be wrong. You find out what the sources actually
say by reading them now, not by remembering what they said.

## Contents
0. Inputs and ground rules
1. Decomposition
2. Faithfulness
3. Source reliability
4. Corroboration
5. Omissions
6. Verdict
7. Writing the JSON
8. Self-check before handing the JSON back

---

## 0. Inputs and ground rules

You receive:
- **text**: the passage to check, verbatim.
- **urls**: the URLs the original answer cited (may be empty).
- **language**: the user's language code (e.g. `it`). All generated prose goes in this
  language. Excerpts do not: they stay in the source's language.
- **scope**, **verifier_mode**, **checked_at**: copy them into `meta`.

Ground rules:
- **Read every page now.** Fetch each URL with WebFetch (or the browser if WebFetch
  cannot render it). Never rely on a summary, a snippet or anything already in a
  conversation: the point is to see what the page says today.
- **Excerpts are copied, never paraphrased or translated.** An excerpt is a passage of at
  most 15 words copied character for character from the page, in the page's language. It
  must be findable with Ctrl+F on the page. If you cannot quote it, you have not found it.
  (The 15-word cap also keeps quotations short enough to respect copyright.)
- **When a page cannot be read** (paywall, 404, block, timeout), say so with `access`;
  don't guess its content from the title or the URL.
- **Write prose for a busy reader.** `reason`, `headline`, omissions and follow-ups are
  one plain sentence each, no jargon, no hedging boilerplate.

## 1. Decomposition

Split the text into **atomic claims**: one checkable statement each. A sentence with
"and" often holds two claims ("Sales grew 38%, and Italy is the first market" → two).

For each claim set `kind`:
- `number`: any figure, percentage, amount, ranking position.
- `date`: when something happened.
- `quote`: words attributed to a person or organisation.
- `fact`: any other statement about the world.
- `synthesis`: the model's own summary, inference or connective reasoning
  ("this suggests that…", "overall…").
- `opinion`: the model's judgement, recommendation or prediction
  ("a trend set to last", "the best choice is…").

`synthesis` and `opinion` are the model's own content: flag them with outcome
`not_checkable`, empty `evidence`, `issues` and `cited_source_ids`. Don't check them,
but do include them, so the reader can see which parts of the text are not backed by
anyone.

**Critical claims.** Mark `critical: true` (with a short `critical_reason`) when the claim
is a number, when the user would plausibly base a decision on it, or when it is
surprising. Most texts have one to three critical claims; if everything is critical,
nothing is.

**More than 12 claims?** The report holds at most 12. Keep the critical ones first
(numbers, decision-relevant, surprising), then the rest in order of importance. Claims
you drop simply stay as unannotated text (`claim_id: null`) in the segments.

**Segments.** Split `text.original` into consecutive segments: each claim is exactly one
segment; the text between claims (spaces, commas, "and") is a segment with
`claim_id: null`. Concatenated, the segments must reproduce the original character for
character, so copy, don't retype. A claim's `text` equals its segment's text. Number
claims `c1, c2, …` in the order they appear in the text.

## 2. Faithfulness

For every checkable claim, open the source the original text attached to it
(`cited_source_ids`) and look for the passage that backs it. If the original attached
citations to specific sentences, use those; if it only gave one list of URLs for the
whole passage, attach to each claim the cited URLs that could plausibly cover it (all of
them when you can't tell).

Assign one `outcome`:

| outcome | when |
|---|---|
| `supported` | the source says the same thing, with the same number, scope and caveats |
| `partial` | the source says something close but weaker, narrower or with caveats the text dropped |
| `unsupported` | the source doesn't say it (and no other source you found does) |
| `contradicted` | a source says the opposite or a different value |
| `unverifiable` | every cited source could not be read (paywall, 404, block); set issue `source_unreachable` |

Record what you found as `evidence`: one item per relevant passage, with `relation`
`supports`, `qualifies` (confirms only in part, or with caveats the text lost) or
`contradicts`.

Look actively for these typical errors and list them in `issues`:

- `citation_mismatch`: the cited source doesn't contain the claim (even if another source does).
- `number_distorted`: rounding, unit, base year, currency, percent vs percentage points, total vs subset changed.
- `hedge_dropped`: the source says "may", "in some cases", "preliminary", "estimated"; the text states it as fact.
- `overgeneralized`: one case, one country or one study turned into a general rule.
- `misattributed`: right statement, wrong author or organisation.
- `sources_merged`: two sources combined into a claim neither supports alone.
- `outdated`: an old figure presented as current when a newer one exists.
- `source_unreachable`: the source could not be read.

**When sources disagree.** Weigh them, don't count them. Use `contradicted` when the
best available evidence (the primary source, or the most reliable sources) says
otherwise. When reliable sources support the claim but another credible source gives a
different value, use `partial`, add the dissenting passage as `contradicts` evidence and
record an `unreported_disagreement` omission. A lone low-reliability source does not
turn a well-supported claim into `partial`; mention it only if it matters.

A claim can be `supported` by one source and still carry `citation_mismatch` if the
*cited* source doesn't hold it: in that case the outcome is `partial`, because the
citation the reader would click is wrong. Keep `issues` empty for `supported` claims.

For each evidence item build `deep_link` = source URL + `#:~:text=` + the excerpt (or its
first words) percent-encoded. Encode spaces as `%20`, `%` as `%25`, `,` as `%2C`, `-` as
`%2D`, `&` as `%26`. The fragment text must be part of the excerpt.

## 3. Source reliability

For every source, cited or found:

1. **Type**: `primary` (original data, study, official document, the organisation's own
   statement), `secondary` (reports on a primary), `aggregator` (collects third-party
   content), `low_quality` (SEO or generated content, no verifiable author, content farm).
2. **Date**: `published_at` as `YYYY`, `YYYY-MM` or `YYYY-MM-DD`; `null` if undated.
   An undated page on a fast-moving topic is a reliability problem.
3. **Lateral reading**: run at least one search *about the publisher or author*, outside
   the page itself (who runs it, funding, track record, what others say about it).
   Write what you learned in `lateral_check`. Don't evaluate a site by its own "About" page.
4. **Expertise**: does the author or publisher have standing on this topic?
5. **Conflict of interest**: does the publisher gain from the claim (sells the product,
   represents the industry, affiliate links)? Write it in `conflict_of_interest`, else `null`.

Then set `reliability.level` (`high` / `medium` / `low`) with a one-line `reason`.
Rough guide: primary + accountable publisher → high; reputable secondary or primary with
a conflict of interest → medium; low_quality, anonymous, or no trace outside itself → low.

Record `access`: `full` (issue `null`), `partial` (e.g. `truncated`, partial paywall)
or `failed` (`paywall`, `not_found`, `blocked`, `timeout`). Follow redirects; if the
target no longer holds the cited content (a homepage, an index, a different article),
the source is `failed` / `not_found`.

**Dates.** Use the date of the version you read: the "updated" date if the page shows
one, else the publication date. If the page's date is clearly wrong (it describes events
after it), keep the stated date and say so in `reliability.reason`.

## 4. Corroboration

For each **critical** claim, search for at least one more source that is independent of
the cited one. Add the sources you find with `cited_in_original: false`.

**Group by origin.** Several articles repeating the same press release, wire story or
study are one voice, not several. Put sources that share an origin in the same
`origin_group` and give the group a label naming that origin (e.g. "Press release of
13/03/2023"). An original, independent source is a group on its own. Signs of a shared
origin: same figures and phrasing, same publication day, "according to a statement",
links to the same document. Several pages from the same organisation are one group.
Separate organisations that each publish their own data are separate groups, even when
they are partners, unless one is republishing the other's content. When a shared origin is itself available, fetch it and add it
as a source in the same group: it is usually the primary.

`independent_source_count` of a claim = number of distinct origin groups among the
sources of its `supports` evidence.

**Look for disagreement, not only confirmation.** Search with phrasings that would surface
a contrary figure or a critique ("<claim> criticism", "<figure> disputed",
"<topic> different estimate"). A contradicting source found this way goes in as
`contradicts` evidence.

## 5. Omissions

Up to 3 items, only if they matter for a reader who might act on the text:
- `unreported_disagreement`: sources disagree and the text picks one side silently.
- `missing_perspective`: a relevant party or viewpoint is absent.
- `missing_context`: a fact that changes how the text reads (a second cause, a base
  rate, a time frame).

Each one sentence, with the `source_ids` that show it.

Then up to 3 `follow_ups`: concrete actions the reader can take, verb first
("Check the ranking in the primary report"), linked to a claim when there is one.

## 6. Verdict

The verdict is **computed, not judged**. Apply these rules in order (rule V1):

1. **problematic** if at least one critical claim is `unsupported` or `contradicted`, or
   a critical claim's `supports` evidence comes only from `low` reliability sources.
2. **reliable** if: at least one checkable claim exists; every critical claim is
   `supported` with `independent_source_count >= 2`; no claim is `contradicted`; no
   `supported` claim relies only on low-reliability sources.
3. **needs_review** in every other case (including when no claim is checkable).

`verdict.basis` lists the claims that triggered the rule (V2):
- problematic → every critical claim that meets rule 1 (all of them, required).
- needs_review → every claim that prevents rule 2 (required); you may also add other
  claims with a visible problem (partial, unverifiable, low-only support) if they help
  explain the headline.
- reliable → empty.

`verdict.counts` is the tally of outcomes across all claims (V0).

`headline`: one sentence (max 140 characters) in the user's language that says what
the reader needs to know: what holds, what doesn't. If the original text cited no
sources (`meta.original_had_citations = false`), say so in the headline.

`scripts/render.py` recomputes all of this. If your status or basis disagree with the
rules, it rejects the report and tells you which rule failed.

## 7. Writing the JSON

- Follow `schema.json` exactly; no extra fields (`additionalProperties: false`).
- `schema_version` is `"1.0"`.
- Every source listed must be used by some claim (cited or as evidence) (S4), and must
  belong to exactly one origin group whose id matches its `origin_group_id` (S2).
- `access.status = full` ⇔ `access.issue = null` (S3).
- `critical_reason` is a string when `critical` is true, `null` otherwise (C3).
- `reason` max 140 characters, `excerpt` max 120 characters and 15 words, origin group
  `label` max 100, omission `description` max 160, follow-up `text` max 120.

## 8. Self-check before handing the JSON back

Run `python <skill>/scripts/render.py report.json --check-only` (add
`--pages <dir>` if you saved each page's text as `<source_id>.txt`: then excerpts are
checked verbatim; for a page you could not read, save a one-line note saying why). Fix every `FAIL <rule>` it prints and run it again until it prints
`OK <status>`. Typical fixes:
- T1: a segment was retyped instead of copied (apostrophes, double spaces, line breaks).
- C9: recount origin groups among `supports` evidence only.
- C10: the excerpt is too long, or the `#:~:text=` fragment isn't part of the excerpt.
- V1: you judged the verdict; apply the rules mechanically instead.
