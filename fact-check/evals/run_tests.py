#!/usr/bin/env python3
"""Run render.py on every fixture and check the expected result.

    python evals/run_tests.py [--out DIR]

Valid fixtures must render with the expected status; invalid fixtures must be
rejected with (at least) the expected rule id. Rendered HTML goes to DIR
(default: evals/out/).
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RENDER = HERE.parent / "scripts" / "render.py"
FIX = HERE / "fixtures"

VALID = {
    "example.json": "needs_review",
    "case1-reliable.json": "reliable",
    "case2-number-distorted.json": "problematic",
    "case3-same-press-release.json": "needs_review",
    "live-webb.json": "needs_review",  # real run by an independent agent, 14/11/2026
}
INVALID = {
    "invalid/T1-segments.json": "T1",
    "invalid/C3-critical-reason.json": "C3",
    "invalid/S3-access.json": "S3",
    "invalid/V1-status.json": "V1",
}


def run(path, out=None):
    cmd = [sys.executable, str(RENDER), str(path)]
    cmd += ["-o", str(out)] if out else ["--check-only"]
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "out"))
    out_dir = Path(ap.parse_args().out)
    out_dir.mkdir(parents=True, exist_ok=True)
    failures = 0

    for name, status in VALID.items():
        out = out_dir / (Path(name).stem + ".html")
        code, text = run(FIX / name, out)
        ok = code == 0 and text.startswith(f"OK {status}")
        extra = ""
        if name == "case2-number-distorted.json":
            r = json.loads((FIX / name).read_text(encoding="utf-8"))
            ok = ok and any("number_distorted" in c["issues"] for c in r["claims"])
            extra = " + issue number_distorted"
        if name == "case3-same-press-release.json":
            r = json.loads((FIX / name).read_text(encoding="utf-8"))
            ok = ok and len(r["origin_groups"]) == 1 and r["claims"][0]["independent_source_count"] == 1
            extra = " + 1 origin group, independent_source_count=1"
        failures += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {name}: expected {status}{extra}; got: {text.strip().splitlines()[0]}")

    for name, rule in INVALID.items():
        code, text = run(FIX / name)
        rules = {line.split()[1].rstrip(":") for line in text.splitlines() if line.startswith("FAIL ")}
        ok = code != 0 and rule in rules
        failures += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {name}: expected rejection {rule}; got exit {code}, rules {sorted(rules)}")

    print(f"\n{'All tests passed' if not failures else f'{failures} test(s) failed'}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
