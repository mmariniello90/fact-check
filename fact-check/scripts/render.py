#!/usr/bin/env python3
"""Validate a fact-check report JSON and render it into a self-contained HTML page.

Usage:
    python3 render.py REPORT.json [-o OUT.html] [--check-only] [--pages DIR]

Steps:
  1. Validate REPORT.json against references/schema.json (JSON Schema Draft 2020-12).
  2. Check every rule in the schema's x-invariants (T1-T3, C1-C12, S1-S4, V0-V2).
     The verdict status is recomputed here (rule V1), never trusted.
  3. Only if everything passes: inject the JSON into assets/report.html and write
     the final HTML.

On any failure the script prints one line per failure, "FAIL <rule-id>: <detail>",
and exits with code 1 (schema errors use the id SCHEMA). Nothing is written.
On success it prints "OK <status>" and exits 0.

--pages DIR (optional): a folder with the plain text of each fetched page, one file
per source named <source_id>.txt (e.g. s1.txt). When given, rule C10 also checks
that every excerpt appears verbatim in its page text (whitespace-normalised).
Without it, C10 checks word count and that the deep link's fragment points
inside the excerpt; the verbatim check is then the verifier's responsibility.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

SKILL_DIR = Path(__file__).resolve().parent.parent
SCHEMA_PATH = SKILL_DIR / "references" / "schema.json"
TEMPLATE_PATH = SKILL_DIR / "assets" / "report.html"

UNCHECKABLE_KINDS = {"synthesis", "opinion"}
OUTCOMES = ["supported", "partial", "unsupported", "contradicted", "unverifiable", "not_checkable"]


# --------------------------------------------------------------------------- schema

def validate_schema(report, schema):
    try:
        from jsonschema import Draft202012Validator, FormatChecker
    except ImportError:
        print("ERROR: render.py needs jsonschema 4.18 or later (Draft 2020-12 support). "
              "Install it with: pip install --upgrade 'jsonschema>=4.18'", file=sys.stderr)
        sys.exit(3)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = []
    for err in sorted(validator.iter_errors(report), key=lambda e: list(e.absolute_path)):
        path = "/".join(str(p) for p in err.absolute_path) or "(root)"
        errors.append(("SCHEMA", f"{path}: {err.message}"))
    return errors


# --------------------------------------------------------------------------- helpers

def norm_ws(s):
    return re.sub(r"\s+", " ", s).strip()


def fragment_texts(deep_link):
    """Return the text-start / text-end strings of a #:~:text= fragment."""
    frag = deep_link.split("#:~:text=", 1)[1]
    frag = frag.split("&", 1)[0]  # ignore further directives
    parts = [unquote(p) for p in frag.split(",")]
    # drop prefix- / -suffix context terms
    parts = [p for p in parts if not p.endswith("-") and not p.startswith("-")] or parts
    return parts


def supports_evidence(claim):
    return [e for e in claim["evidence"] if e["relation"] == "supports"]


def low_only(claim, src_by_id):
    """True when the claim has supporting evidence and all of it is from low-reliability sources."""
    sup = supports_evidence(claim)
    if not sup:
        return False
    return all(src_by_id.get(e["source_id"], {}).get("reliability", {}).get("level") == "low"
               for e in sup)


def compute_verdict(claims, src_by_id):
    """Apply rule V1. Returns (status, triggers, flagged).

    triggers = claims that make the applied rule fire (problematic) or that
    prevent 'reliable' (needs_review). flagged = every claim with a visible
    problem; verdict.basis may list these in addition to the triggers.
    """
    critical = [c for c in claims if c["critical"]]
    checkable = [c for c in claims if c["kind"] not in UNCHECKABLE_KINDS]

    flagged = set()
    for c in claims:
        if c["outcome"] in {"partial", "unsupported", "contradicted", "unverifiable"}:
            flagged.add(c["id"])
        if low_only(c, src_by_id):
            flagged.add(c["id"])
        if c["critical"] and c["kind"] not in UNCHECKABLE_KINDS and c["independent_source_count"] < 2:
            flagged.add(c["id"])

    # Rule 1: problematic
    r1 = [c["id"] for c in critical
          if c["outcome"] in {"unsupported", "contradicted"} or low_only(c, src_by_id)]
    if r1:
        return "problematic", r1, flagged | set(r1)

    # Rule 2: reliable (collect the claims that block it)
    if not checkable:
        ids = [c["id"] for c in claims]
        return "needs_review", ids, set(ids)
    blockers = []
    for c in claims:
        blocks = False
        if c["critical"] and (c["outcome"] != "supported" or c["independent_source_count"] < 2):
            blocks = True
        if c["outcome"] in {"contradicted", "unsupported", "unverifiable"}:
            blocks = True
        if c["outcome"] == "supported" and low_only(c, src_by_id):
            blocks = True
        if blocks:
            blockers.append(c["id"])
    if not any(c["outcome"] == "supported" for c in claims):
        # nothing in the text is actually backed by a source: never reliable
        blockers += [c["id"] for c in checkable if c["id"] not in blockers]
    if not blockers:
        return "reliable", [], set()

    # Rule 3: needs_review
    return "needs_review", blockers, flagged | set(blockers)


# --------------------------------------------------------------------------- invariants

def check_invariants(r, pages_dir=None):
    errs = []

    def fail(rule, msg):
        errs.append((rule, msg))

    claims = r["claims"]
    sources = r["sources"]
    groups = r["origin_groups"]
    segments = r["text"]["segments"]
    claim_by_id = {}
    for c in claims:
        claim_by_id.setdefault(c["id"], c)
    src_by_id = {}
    for s in sources:
        src_by_id.setdefault(s["id"], s)

    # ---- T1
    joined = "".join(seg["text"] for seg in segments)
    if joined != r["text"]["original"]:
        i = next((k for k, (a, b) in enumerate(zip(joined, r["text"]["original"])) if a != b),
                 min(len(joined), len(r["text"]["original"])))
        fail("T1", f"segments do not reproduce text.original (first difference at char {i}: "
                   f"{joined[i:i+25]!r} vs {r['text']['original'][i:i+25]!r})")

    # ---- T2
    seg_claims = [seg["claim_id"] for seg in segments if seg["claim_id"] is not None]
    for c in claims:
        n = seg_claims.count(c["id"])
        if n != 1:
            fail("T2", f"claim {c['id']} appears in {n} segments (expected exactly 1)")
        else:
            seg = next(s for s in segments if s["claim_id"] == c["id"])
            if seg["text"] != c["text"]:
                fail("T2", f"claim {c['id']}: text differs from its segment text")

    # ---- T3
    refs = [("text.segments", cid) for cid in seg_claims]
    refs += [("verdict.basis", cid) for cid in r["verdict"]["basis"]]
    refs += [("follow_ups", f["claim_id"]) for f in r["follow_ups"] if f["claim_id"] is not None]
    for where, cid in refs:
        if cid not in claim_by_id:
            fail("T3", f"{where} references unknown claim {cid}")

    # ---- C1
    ids = [c["id"] for c in claims]
    if len(ids) != len(set(ids)):
        fail("C1", "claim ids are not unique")
    expected = [f"c{i + 1}" for i in range(len(claims))]
    if ids != expected:
        fail("C1", f"claim ids must be {expected} in order, got {ids}")
    first_seen = []
    for cid in seg_claims:
        if cid not in first_seen:
            first_seen.append(cid)
    if [cid for cid in first_seen if cid in claim_by_id] != [cid for cid in ids if cid in first_seen]:
        fail("C1", f"claims are not numbered in order of appearance in the text: {first_seen}")

    for c in claims:
        cid = c["id"]
        rel = [e["relation"] for e in c["evidence"]]
        # ---- C2
        unchk = c["kind"] in UNCHECKABLE_KINDS
        if unchk != (c["outcome"] == "not_checkable"):
            fail("C2", f"{cid}: kind={c['kind']} requires "
                       f"{'outcome=not_checkable' if unchk else 'an outcome other than not_checkable'}")
        if unchk and (c["evidence"] or c["issues"] or c["cited_source_ids"]):
            fail("C2", f"{cid}: synthesis/opinion claims must have empty evidence, issues, cited_source_ids")
        # ---- C3
        if c["critical"] and not c["critical_reason"]:
            fail("C3", f"{cid}: critical=true requires critical_reason")
        if not c["critical"] and c["critical_reason"] is not None:
            fail("C3", f"{cid}: critical=false requires critical_reason=null")
        # ---- C12
        if c["critical"] and unchk:
            fail("C12", f"{cid}: kind={c['kind']} cannot be critical (it is not checkable)")
        if c["kind"] == "number" and not c["critical"]:
            fail("C12", f"{cid}: kind=number must be critical")
        o = c["outcome"]
        # ---- C4
        if o == "supported":
            if "supports" not in rel:
                fail("C4", f"{cid}: supported needs at least one 'supports' evidence")
            if "contradicts" in rel:
                fail("C4", f"{cid}: supported cannot have 'contradicts' evidence")
            if c["issues"]:
                fail("C4", f"{cid}: supported must have no issues")
        # ---- C5
        if o == "partial" and "qualifies" not in rel and not c["issues"]:
            fail("C5", f"{cid}: partial needs a 'qualifies' evidence or at least one issue")
        # ---- C6
        if o == "contradicted" and "contradicts" not in rel:
            fail("C6", f"{cid}: contradicted needs at least one 'contradicts' evidence")
        # ---- C7
        if o == "unsupported" and "supports" in rel:
            fail("C7", f"{cid}: unsupported cannot have 'supports' evidence")
        # ---- C8
        if o == "unverifiable":
            bad = [s for s in c["cited_source_ids"]
                   if src_by_id.get(s, {}).get("access", {}).get("status") != "failed"]
            if bad:
                fail("C8", f"{cid}: unverifiable but cited sources {bad} were readable")
            if "source_unreachable" not in c["issues"]:
                fail("C8", f"{cid}: unverifiable requires issue source_unreachable")
        # ---- C9
        grp = {src_by_id[e["source_id"]]["origin_group_id"]
               for e in supports_evidence(c) if e["source_id"] in src_by_id}
        if c["independent_source_count"] != len(grp):
            fail("C9", f"{cid}: independent_source_count={c['independent_source_count']} "
                       f"but supporting evidence spans {len(grp)} origin group(s)")
        for k, e in enumerate(c["evidence"]):
            # ---- C10
            words = len(e["excerpt"].split())
            if words > 15:
                fail("C10", f"{cid} evidence {k}: excerpt has {words} words (max 15)")
            if "#:~:text=" in e["deep_link"]:
                ex = norm_ws(e["excerpt"]).lower()
                for part in fragment_texts(e["deep_link"]):
                    if norm_ws(part).lower() not in ex:
                        fail("C10", f"{cid} evidence {k}: text fragment {part!r} is not part of the excerpt")
            if pages_dir is not None:
                page = Path(pages_dir) / f"{e['source_id']}.txt"
                if page.exists():
                    if norm_ws(e["excerpt"]) not in norm_ws(page.read_text(encoding="utf-8")):
                        fail("C10", f"{cid} evidence {k}: excerpt not found verbatim in {page.name}")
                else:
                    fail("C10", f"{cid} evidence {k}: no page text {page.name} to check the excerpt against")
            # ---- C11
            src = src_by_id.get(e["source_id"])
            if src is not None:
                base = src["url"].split("#", 1)[0]
                if e["deep_link"].split("#", 1)[0] != base or not e["deep_link"].startswith(base + "#:~:text="):
                    fail("C11", f"{cid} evidence {k}: deep_link must be the url of {e['source_id']} "
                                f"(without any #anchor) followed by #:~:text=")

    # ---- S1
    sids = [s["id"] for s in sources]
    if len(sids) != len(set(sids)):
        fail("S1", "source ids are not unique")
    sref = []
    for c in claims:
        sref += [(f"{c['id']}.cited_source_ids", s) for s in c["cited_source_ids"]]
        sref += [(f"{c['id']}.evidence", e["source_id"]) for e in c["evidence"]]
    for g in groups:
        sref += [(f"origin_groups.{g['id']}", s) for s in g["source_ids"]]
    for k, om in enumerate(r["omissions"]):
        sref += [(f"omissions[{k}]", s) for s in om["source_ids"]]
    for where, s in sref:
        if s not in src_by_id:
            fail("S1", f"{where} references unknown source {s}")

    # ---- S2
    gids = [g["id"] for g in groups]
    if len(gids) != len(set(gids)):
        fail("S2", "origin group ids are not unique")
    for s in sources:
        holders = [g["id"] for g in groups if s["id"] in g["source_ids"]]
        if len(holders) != 1:
            fail("S2", f"source {s['id']} is in {len(holders)} origin groups (expected exactly 1)")
        elif holders[0] != s["origin_group_id"]:
            fail("S2", f"source {s['id']}: origin_group_id={s['origin_group_id']} "
                       f"but it is listed in {holders[0]}")
    for g in groups:
        if not g["source_ids"]:
            fail("S2", f"origin group {g['id']} is empty")

    # ---- S3
    for s in sources:
        full = s["access"]["status"] == "full"
        if full != (s["access"]["issue"] is None):
            fail("S3", f"source {s['id']}: access.status=full must go with issue=null, and vice versa")

    # ---- S4
    used = set()
    for c in claims:
        used.update(c["cited_source_ids"])
        used.update(e["source_id"] for e in c["evidence"])
    for s in sources:
        if s["id"] not in used:
            fail("S4", f"source {s['id']} is not used by any claim")

    # ---- V0
    tally = {k: 0 for k in OUTCOMES}
    for c in claims:
        tally[c["outcome"]] += 1
    if tally != r["verdict"]["counts"]:
        fail("V0", f"verdict.counts {r['verdict']['counts']} does not match claims {tally}")

    # ---- V1 / V2
    status, triggers, flagged = compute_verdict(claims, src_by_id)
    declared = r["verdict"]["status"]
    if status != declared:
        fail("V1", f"declared status '{declared}' but the rules give '{status}' "
                   f"(triggered by {triggers or 'no claim'})")
    basis = r["verdict"]["basis"]
    if status == "reliable":
        if basis:
            fail("V2", f"status is reliable, so verdict.basis must be empty (got {basis})")
    else:
        if not basis:
            fail("V2", f"verdict.basis is empty; it must list the claims that triggered the rule: {triggers}")
        missing = [t for t in triggers if t not in basis]
        if missing:
            fail("V2", f"verdict.basis is missing triggering claims {missing}")
        extra = [b for b in basis if b in claim_by_id and b not in flagged]
        if extra:
            fail("V2", f"verdict.basis lists claims with no problem: {extra}")

    return errs, status


# --------------------------------------------------------------------------- render

def render(report, template):
    data = json.dumps(report, ensure_ascii=False, indent=None, separators=(",", ":"))
    # keep the JSON inert inside <script>: neutralise "</" and HTML comment openers
    data = data.replace("</", "<\\/").replace("<!--", "<\\!--")
    lang = report["meta"]["language"]
    if "__FC_DATA__" not in template:
        raise SystemExit("ERROR: template has no __FC_DATA__ placeholder")
    return template.replace("__FC_LANG__", lang).replace("__FC_DATA__", data)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("report")
    ap.add_argument("-o", "--out", help="output HTML path (default: REPORT with .html)")
    ap.add_argument("--check-only", action="store_true", help="validate only, do not write HTML")
    ap.add_argument("--pages", help="folder with <source_id>.txt page texts for the verbatim excerpt check")
    args = ap.parse_args()

    try:
        report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"FAIL JSON: not valid JSON: {e}")
        sys.exit(1)
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    errors = validate_schema(report, schema)
    if errors:
        for rule, msg in errors:
            print(f"FAIL {rule}: {msg}")
        print(f"\n{len(errors)} schema error(s). Fix the JSON and run again; invariants were not checked.")
        sys.exit(1)

    errors, status = check_invariants(report, args.pages)
    if errors:
        for rule, msg in errors:
            print(f"FAIL {rule}: {msg}")
        rules = sorted({r for r, _ in errors}, key=lambda x: (x[0], int(x[1:]) if x[1:].isdigit() else 0))
        print(f"\n{len(errors)} invariant failure(s): {', '.join(rules)}. Fix the JSON and run again.")
        sys.exit(1)

    if not args.check_only:
        out = Path(args.out) if args.out else Path(args.report).with_suffix(".html")
        html = render(report, TEMPLATE_PATH.read_text(encoding="utf-8"))
        out.write_text(html, encoding="utf-8")
        print(f"OK {status} -> {out}")
    else:
        print(f"OK {status}")


if __name__ == "__main__":
    main()
