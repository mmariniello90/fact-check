---
name: fact-check
description: Checks whether a text Claude generated is faithful to the web sources it cites and rests on reliable, independent sources, then shows the result as a one-screen HTML report (verdict, annotated text, claim cards, sources). Use it whenever the user types /fact-check, or asks to verify, double-check or fact-check an earlier answer or a quoted passage ("is this true?", "check your sources", "can I trust this?", "where did you get that number?"), including in Italian ("verifica le fonti", "controlla se è vero", "fact check", "è affidabile?", "controlla le fonti di questa risposta", "da dove viene questo dato?"). Use it even when the answer cited no sources.
---

# Fact-check

Checks a text Claude wrote against the web: (a) does each claim match what its cited
source actually says, and (b) do the sources deserve trust, independently of each other.
The user gets a small HTML report they can read in a few seconds to decide whether to
trust the text or dig deeper.

Files in this skill:
- `references/method.md`: the verification method, step by step. The verifier follows it.
- `references/schema.json`: the JSON contract for the report, with extra rules in `x-invariants`.
- `scripts/render.py`: validates the JSON (schema + every invariant, verdict recomputed) and renders it.
- `assets/report.html`: the report template. Never write report HTML by hand.

## 1. Work out what to check

- **Text**: the passage the user quoted in their message (`meta.scope = "selection"`);
  if they didn't quote one, your last answer in the conversation (`"full_response"`).
  Copy it verbatim: the report re-assembles it character by character.
- **Sources**: the URLs cited in that text or attached to the original answer (search
  result citations, links, "Sources:" lists). Recover them from the conversation.
- **No sources?** Set `meta.original_had_citations = false`. The check still runs: the
  verifier searches for sources from scratch, and the headline says the original cited none.
- **Language**: the language the user writes in (`meta.language`, e.g. `it`, `en`).
  Everything generated (headline, reasons, omissions, follow-ups, group labels) is in that
  language. Excerpts are never translated: they stay in the source's language, otherwise
  they can't be compared with the page and the text-fragment link breaks.
- **checked_at**: the current date-time with offset (ISO 8601).

## 2. Run the analysis in a verifier that didn't write the text

The verifier must not grade its own work: having written the answer, you will tend to
read the sources the way you remember them.

**If you can launch a separate agent** (an Agent/Task tool), hand the analysis to a
*fresh* agent: a general-purpose one, never a fork of this conversation. Set
`meta.verifier_mode = "independent_agent"`. Give it only what it needs:

```
You are an independent fact-checker. Follow the method in <skill>/references/method.md
exactly and produce a report JSON valid against <skill>/references/schema.json.
Read both files first.

Text to check (verbatim, between the markers):
<<<TEXT
...
TEXT>>>

Cited URLs: <one per line, or "none">
meta: language=<code>, scope=<selection|full_response>, verifier_mode=independent_agent,
      checked_at=<ISO date-time>, original_had_citations=<true|false>

Re-fetch every page yourself. Save the report to <work dir>/report.json, then run
  python <skill>/scripts/render.py <work dir>/report.json --check-only
and fix the JSON until it prints OK. Reply with the path of the JSON and the OK line.
```

Use absolute paths for `<skill>` and the work directory. Pass no other part of the
conversation: not your reasoning, not page contents, not what you think the answer is.

**Otherwise**, run the analysis yourself in this session, following
`references/method.md`, with `meta.verifier_mode = "same_session_refetch"`. Re-fetch
every page with WebFetch and work only from what the fetch returns, never from what is
already in the conversation.

## 3. Validate and render

```bash
python <skill>/scripts/render.py report.json -o fact-check-report.html
```

`render.py` validates against the schema (Draft 2020-12), checks every rule in
`x-invariants` (T1–T3, C1–C11, S1–S4, V0–V2) and recomputes the verdict itself. On any
failure it prints `FAIL <rule-id>: ...` lines and exits non-zero, writing nothing: fix the
JSON (or, with an independent agent, send the failures back to that same agent to fix)
and run it again. Never render an invalid report and never hand-edit the HTML: the
report has to look the same on every run. It needs `jsonschema` 4.18 or later
(`pip install --upgrade 'jsonschema>=4.18'`; exit code 3 means it is missing or too old).

If the verifier saved the text of each fetched page as `<source_id>.txt` in a folder,
add `--pages <folder>` so excerpts are also checked verbatim (rule C10).

## 4. Deliver

1. Publish `fact-check-report.html` as an artifact (the Artifact tool, publishing the file
   by path). If no artifact tool is available, send the file to the user instead.
2. In the chat, after the artifact, write **one line only**: the verdict label and the
   headline, in the user's language. For example:
   `Da verificare: Il dato principale regge, ma un'affermazione è smentita dalla sua stessa fonte.`

Labels for that line: reliable = Reliable / Affidabile; needs_review = Needs review /
Da verificare; problematic = Problematic / Problematico (other languages: translate).

## Notes

- The report is mobile-first, has light and dark mode, uses no numeric scores, and never
  uses color alone (every mark has an icon and a label). UI labels live in a dictionary
  at the top of the template's script (`LABELS`), with English and Italian; any other
  language falls back to English. To add a language, copy the `en` block.
- Claim card titles show the claim text on one line, truncated with an ellipsis; keep
  claims atomic and they stay readable.
- Test fixtures and invalid cases are in `evals/` (not packaged).
