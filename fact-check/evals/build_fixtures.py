#!/usr/bin/env python3
"""Build the test fixtures for render.py.

Valid cases (expected verdict in the file name's comment below):
  case1-reliable.json       independent primary sources            -> reliable
  case2-number-distorted.json  number changed vs cited source      -> problematic, number_distorted
  case3-same-press-release.json three articles, one press release  -> needs_review, 1 origin group
  case4-unsupported-minor.json  case1 with a minor claim unsupported -> needs_review
Invalid cases, each breaking one rule (the file name starts with the rule id):
  derived from example.json, case1 and live-webb.json; see the bottom of this file.

Run:  python3 evals/build_fixtures.py   (writes into evals/fixtures/)
"""
import copy
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent / "fixtures"


def dump(name, obj):
    p = HERE / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def counts(claims):
    keys = ["supported", "partial", "unsupported", "contradicted", "unverifiable", "not_checkable"]
    return {k: sum(c["outcome"] == k for c in claims) for k in keys}


def src(id, url, title, publisher, type, level, reason, lateral, group, published="2025-02-10",
        author=None, coi=None, cited=True, access=("full", None)):
    return {"id": id, "url": url, "title": title, "publisher": publisher, "author": author,
            "published_at": published, "cited_in_original": cited,
            "access": {"status": access[0], "issue": access[1]}, "type": type,
            "reliability": {"level": level, "reason": reason, "lateral_check": lateral},
            "conflict_of_interest": coi, "origin_group_id": group}


def ev(source, rel, excerpt, url, frag=None):
    from urllib.parse import quote
    frag = frag or excerpt
    return {"source_id": source, "relation": rel, "excerpt": excerpt,
            "deep_link": url + "#:~:text=" + quote(frag, safe="'")}


def claim(id, text, kind, outcome, reason, critical_reason=None, issues=(), cited=(), evidence=(), isc=0):
    return {"id": id, "text": text, "kind": kind, "critical": critical_reason is not None,
            "critical_reason": critical_reason, "outcome": outcome, "reason": reason,
            "issues": list(issues), "cited_source_ids": list(cited), "evidence": list(evidence),
            "independent_source_count": isc}


# ---------------------------------------------------------------- case 1: reliable (en)
U1 = "https://transport-authority.example.org/annual-report-2025"
U2 = "https://stats-office.example.gov/urban-mobility-2025"
c1_segments = [
    ("The Riverside tram line opened on 4 March 2024", "c1"), (" and ", None),
    ("carried 2.1 million passengers in its first year.", "c2"), (" ", None),
    ("It is a model other mid-sized cities should follow.", "c3"),
]
case1 = {
    "schema_version": "1.0",
    "meta": {"checked_at": "2026-11-14T08:00:00+00:00", "language": "en", "scope": "full_response",
             "verifier_mode": "independent_agent", "original_had_citations": True},
    "verdict": {"status": "reliable",
                "headline": "Both facts match their sources, and the ridership figure is confirmed by two independent primary sources.",
                "basis": []},
    "text": {"original": "".join(t for t, _ in c1_segments),
             "segments": [{"text": t, "claim_id": c} for t, c in c1_segments]},
    "claims": [
        claim("c1", "The Riverside tram line opened on 4 March 2024", "date", "supported",
              "The authority's report gives the same opening date.", cited=["s1"],
              evidence=[ev("s1", "supports", "The Riverside line entered service on 4 March 2024", U1)], isc=1),
        claim("c2", "carried 2.1 million passengers in its first year.", "number", "supported",
              "Both the operator and the statistics office report 2.1 million trips.",
              critical_reason="It is the key figure of the answer.", cited=["s1"],
              evidence=[ev("s1", "supports", "2.1 million passenger trips in the first twelve months", U1),
                        ev("s2", "supports", "Riverside line: 2.1 million boardings (Mar 2024 - Feb 2025)", U2,
                           frag="Riverside line: 2.1 million boardings")], isc=2),
        claim("c3", "It is a model other mid-sized cities should follow.", "opinion", "not_checkable",
              "A recommendation by the model, not a fact from a source."),
    ],
    "sources": [
        src("s1", U1, "Annual report 2025", "City Transport Authority", "primary", "high",
            "Operator's own ridership data from ticket validations.",
            "Public body; its figures are audited by the regional court of auditors.", "g1",
            coi="Operates the line: has an interest in good figures."),
        src("s2", U2, "Urban mobility statistics 2025", "National Statistics Office", "primary", "high",
            "Official statistics with published methodology.",
            "Cited as the reference source by universities and the press.", "g2", cited=False,
            published="2025-09"),
    ],
    "origin_groups": [{"id": "g1", "label": "City Transport Authority annual report", "source_ids": ["s1"]},
                      {"id": "g2", "label": "National Statistics Office", "source_ids": ["s2"]}],
    "omissions": [],
    "follow_ups": [{"text": "Compare ridership with the forecast in the original business case", "claim_id": "c2"}],
}
case1["verdict"]["counts"] = counts(case1["claims"])

# ---------------------------------------------------------------- case 2: number distorted (it)
V1 = "https://ente-statistico.example.it/comunicato-lavoro-2024"
V2 = "https://quotidiano.example.it/economia/disoccupazione-giovani"
c2_segments = [
    ("Nel 2024 la disoccupazione giovanile in Italia è scesa al 18%,", "c1"), (" ", None),
    ("il valore più basso dal 2007.", "c2"), (" ", None),
    ("Un segnale che il mercato del lavoro si è ripreso.", "c3"),
]
case2 = {
    "schema_version": "1.0",
    "meta": {"checked_at": "2026-11-14T08:05:00+01:00", "language": "it", "scope": "selection",
             "verifier_mode": "same_session_refetch", "original_had_citations": True},
    "verdict": {"status": "problematic",
                "headline": "Il dato principale è sbagliato: la fonte citata indica il 20,5%, non il 18%.",
                "basis": ["c1"]},
    "text": {"original": "".join(t for t, _ in c2_segments),
             "segments": [{"text": t, "claim_id": c} for t, c in c2_segments]},
    "claims": [
        claim("c1", "Nel 2024 la disoccupazione giovanile in Italia è scesa al 18%,", "number", "contradicted",
              "La fonte citata riporta il 20,5% per i 15-24 anni; il 18% non compare.",
              critical_reason="È il numero su cui si regge tutta la risposta.",
              issues=["number_distorted"], cited=["s1"],
              evidence=[ev("s1", "contradicts", "il tasso di disoccupazione giovanile (15-24 anni) si attesta al 20,5%", V1,
                           frag="il tasso di disoccupazione giovanile")]),
        claim("c2", "il valore più basso dal 2007.", "fact", "supported",
              "Sia l'ente sia il quotidiano indicano il minimo dal 2007.", cited=["s1"],
              evidence=[ev("s1", "supports", "il livello più basso dal 2007", V1),
                        ev("s2", "supports", "mai così bassa dal 2007", V2)], isc=1),
        claim("c3", "Un segnale che il mercato del lavoro si è ripreso.", "synthesis", "not_checkable",
              "È un'interpretazione del modello, non un dato attribuito a una fonte."),
    ],
    "sources": [
        src("s1", V1, "Occupati e disoccupati – anno 2024", "Ente statistico nazionale", "primary", "high",
            "Dato ufficiale con nota metodologica.",
            "Ente pubblico di statistica, citato come riferimento da Banca d'Italia.", "g1", published="2025-03-04"),
        src("s2", V2, "Giovani, la disoccupazione ai minimi dal 2007", "Quotidiano nazionale", "secondary", "medium",
            "Riprende il comunicato dell'ente aggiungendo commenti.",
            "Testata nazionale con direttore responsabile e policy di rettifica.", "g1", published="2025-03-04",
            author="Redazione economia", cited=False),
    ],
    "origin_groups": [{"id": "g1", "label": "Comunicato dell'ente statistico del 04/03/2025", "source_ids": ["s1", "s2"]}],
    "omissions": [{"type": "missing_context",
                   "description": "Il calo è in parte dovuto alla riduzione dei giovani attivi, come nota l'ente.",
                   "source_ids": ["s1"]}],
    "follow_ups": [{"text": "Correggi il dato al 20,5% citando il comunicato dell'ente", "claim_id": "c1"},
                   {"text": "Verifica il tasso di inattività giovanile nello stesso comunicato", "claim_id": None}],
}
case2["verdict"]["counts"] = counts(case2["claims"])

# ---------------------------------------------------------------- case 3: same press release (en)
P = ["https://tech-news-a.example.com/voltix-battery",
     "https://daily-b.example.com/science/voltix-ten-minute-charge",
     "https://gadget-c.example.net/voltix-80-percent"]
c3_segments = [
    ("Voltix's new solid-state battery charges from 10% to 80% in 10 minutes,", "c1"), (" ", None),
    ("and it will be in cars by 2027.", "c2"),
]
case3 = {
    "schema_version": "1.0",
    "meta": {"checked_at": "2026-11-14T08:10:00+00:00", "language": "en", "scope": "full_response",
             "verifier_mode": "independent_agent", "original_had_citations": True},
    "verdict": {"status": "needs_review",
                "headline": "The articles agree, but all three repeat the same company press release: no independent confirmation.",
                "basis": ["c1"]},
    "text": {"original": "".join(t for t, _ in c3_segments),
             "segments": [{"text": t, "claim_id": c} for t, c in c3_segments]},
    "claims": [
        claim("c1", "Voltix's new solid-state battery charges from 10% to 80% in 10 minutes,", "number", "supported",
              "All three articles give the figure, but they quote the same press release.",
              critical_reason="Surprising performance claim, central to the answer.", cited=["s1", "s2", "s3"],
              evidence=[ev("s1", "supports", "from 10 to 80 percent in just 10 minutes", P[0]),
                        ev("s2", "supports", "a 10-80% charge takes ten minutes, the company said", P[1],
                           frag="a 10-80% charge takes ten minutes"),
                        ev("s3", "supports", "10% to 80% in 10 minutes", P[2])], isc=1),
        claim("c2", "and it will be in cars by 2027.", "date", "partial",
              "The release says it aims for 2027, a target, not a commitment.",
              issues=["hedge_dropped"], cited=["s1"],
              evidence=[ev("s1", "qualifies", "aims to begin supplying automakers in 2027", P[0])]),
    ],
    "sources": [
        src("s1", P[0], "Voltix unveils ten-minute solid-state battery", "Tech News A", "secondary", "medium",
            "Tech site; rewrites the press release without own tests.",
            "Established tech outlet; editorial staff named on its masthead.", "g1", published="2026-10-02"),
        src("s2", P[1], "Ten-minute charging: Voltix's bold claim", "Daily B", "secondary", "medium",
            "General newspaper; quotes the company only.",
            "National daily with a public corrections policy.", "g1", published="2026-10-02", author="Science desk"),
        src("s3", P[2], "Voltix battery hits 80% in 10 minutes", "Gadget C", "aggregator", "low",
            "Republishes press releases, no bylines.",
            "No coverage of the site by other outlets; anonymous ownership.", "g1", published="2026-10-03"),
    ],
    "origin_groups": [{"id": "g1", "label": "Voltix press release of 02/10/2026", "source_ids": ["s1", "s2", "s3"]}],
    "omissions": [{"type": "missing_perspective",
                   "description": "No independent lab or expert has tested the charging claim; only the company is quoted.",
                   "source_ids": ["s1", "s2"]}],
    "follow_ups": [{"text": "Look for an independent test or peer-reviewed paper on the battery", "claim_id": "c1"},
                   {"text": "Check which automakers have actually signed supply deals", "claim_id": "c2"}],
}
case3["verdict"]["counts"] = counts(case3["claims"])

dump("case1-reliable.json", case1)
dump("case2-number-distorted.json", case2)
dump("case3-same-press-release.json", case3)

# ---------------------------------------------------------------- invalid cases (from example.json)
example = json.loads((HERE / "example.json").read_text(encoding="utf-8"))

t = copy.deepcopy(example)  # T1: a connecting segment retyped with a double space
t["text"]["segments"][1]["text"] = "  "
dump("invalid/T1-segments.json", t)

c = copy.deepcopy(example)  # C3: critical=false but critical_reason set
c["claims"][1]["critical_reason"] = "Spiega la causa della crescita."
dump("invalid/C3-critical-reason.json", c)

s = copy.deepcopy(example)  # S3: access full but with an issue
s["sources"][0]["access"] = {"status": "full", "issue": "paywall"}
dump("invalid/S3-access.json", s)

v = copy.deepcopy(example)  # V1: declares reliable although c3 is contradicted
v["verdict"]["status"] = "reliable"
dump("invalid/V1-status.json", v)

# ---------------------------------------------------------------- case 4 and more invalid cases
def recount(r):
    r["verdict"]["counts"] = counts(r["claims"])
    return r

c4 = copy.deepcopy(case1)  # a minor claim nobody supports: must block "reliable"
c4["claims"][0].update(outcome="unsupported", issues=["citation_mismatch"], evidence=[],
                       independent_source_count=0,
                       reason="The report gives no opening date; none of the sources does.")
c4["verdict"].update(status="needs_review", basis=["c1"],
                     headline="The ridership figure holds up, but the opening date is not in any source.")
dump("case4-unsupported-minor.json", recount(c4))

bad = copy.deepcopy(c4)  # V1: the old rule called this reliable (unsupported minor claim)
bad["verdict"].update(status="reliable", basis=[])
dump("invalid/V1-unsupported-minor.json", bad)

bad = copy.deepcopy(c4)  # V1: no claim is supported at all, none critical
bad["claims"] = [bad["claims"][0], bad["claims"][2]]
bad["text"]["segments"] = [{"text": "The Riverside tram line opened on 4 March 2024", "claim_id": "c1"},
                           {"text": " and carried 2.1 million passengers in its first year. ", "claim_id": None},
                           {"text": "It is a model other mid-sized cities should follow.", "claim_id": "c2"}]
bad["claims"][1]["id"] = "c2"
bad["sources"], bad["origin_groups"] = bad["sources"][:1], bad["origin_groups"][:1]
bad["follow_ups"] = []
bad["verdict"].update(status="reliable", basis=[])
dump("invalid/V1-nothing-supported.json", recount(bad))

bad = copy.deepcopy(case1)  # C12: a number claim marked not critical
bad["claims"][1].update(critical=False, critical_reason=None)
dump("invalid/C12-number-not-critical.json", bad)

bad = copy.deepcopy(case1)  # C12: an opinion marked critical
bad["claims"][2].update(critical=True, critical_reason="Recommendation the reader may act on.")
dump("invalid/C12-opinion-critical.json", bad)

bad = copy.deepcopy(case1)  # C11: the source url carries an #anchor before the text fragment
bad["sources"][0]["url"] = U1 + "#ridership"
for c in bad["claims"]:
    for e in c["evidence"]:
        if e["source_id"] == "s1":
            e["deep_link"] = e["deep_link"].replace(U1, U1 + "#ridership")
dump("invalid/C11-anchor.json", bad)

bad = copy.deepcopy(case1)  # C9: independent_source_count does not match the groups
bad["claims"][1]["independent_source_count"] = 3
dump("invalid/C9-count.json", bad)

bad = copy.deepcopy(case1)  # S4: a source no claim uses
bad["sources"].append(src("s3", "https://unused.example.com/page", "Unused page", "Unused", "secondary",
                          "medium", "Never cited.", "Nothing known about it.", "g3"))
bad["origin_groups"].append({"id": "g3", "label": "Unused page", "source_ids": ["s3"]})
dump("invalid/S4-unused-source.json", bad)

bad = copy.deepcopy(case1)  # V0: counts do not match the claims
bad["verdict"]["counts"]["supported"] = 1
dump("invalid/V0-counts.json", bad)

live = json.loads((HERE / "live-webb.json").read_text(encoding="utf-8"))
bad = copy.deepcopy(live)  # C10 (with --pages): an excerpt that is not on the page
for c in bad["claims"]:
    if c["evidence"]:
        e = c["evidence"][0]
        e["excerpt"] = "words that never appeared on " + e["excerpt"]
        break
dump("invalid/C10-not-on-page.json", bad)

print("fixtures written to", HERE)
