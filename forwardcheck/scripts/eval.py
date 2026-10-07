"""Run the pipeline on a labelled test set and report accuracy, citation rate and latency.

Usage:  .venv/bin/python scripts/eval.py tests/testset.csv

CSV columns: id,input_type,language,input,expected_label,notes
  input_type: text | url | image | audio | pdf
  input:      the message text, the URL, or a file path (relative to the CSV)
  expected_label: VERIFIED | FALSE | OUTDATED | PARTLY_SUPPORTED | CANNOT_BE_CONFIRMED
Only put claims whose answers YOU verified from official sources into the answer key.
A row's expected label is compared with the verdict of the FIRST (most check-worthy) claim.
"""
from __future__ import annotations

import asyncio
import csv
import mimetypes
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.llm import LLM  # noqa: E402
from app.pipeline import run_check  # noqa: E402

LABELS = ["VERIFIED", "FALSE", "OUTDATED", "PARTLY_SUPPORTED", "CANNOT_BE_CONFIRMED"]


async def main(path: str) -> None:
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    llm, base = LLM(), Path(path).parent
    confusion: dict[str, Counter] = defaultdict(Counter)
    correct = cited = total = 0
    times: list[int] = []
    for r in rows:
        kind, inp = r["input_type"].strip(), r["input"].strip()
        kwargs: dict = {}
        if kind == "text":
            kwargs["text"] = inp
        elif kind == "url":
            kwargs["url"] = inp
        else:
            f = base / inp
            kwargs["file"] = (f.read_bytes(), f.name, mimetypes.guess_type(f.name)[0] or "")
        try:
            res = await run_check(llm, **kwargs)
        except Exception as e:  # keep going so one failure doesn't hide the rest
            print(f"[{r['id']}] ERROR: {e}")
            continue
        total += 1
        times.append(res.elapsed_ms)
        got = res.results[0].verdict.label.value if res.results else "NO_CLAIM"
        exp = r["expected_label"].strip()
        confusion[exp][got] += 1
        ok = got == exp
        correct += ok
        if res.results and (res.results[0].verdict.evidence_ids or got == "CANNOT_BE_CONFIRMED"):
            cited += 1
        print(f"[{r['id']}] {r['input_type']:<5} {r['language']:<3} expected={exp:<20} got={got:<20} {'OK' if ok else 'MISS'} ({res.elapsed_ms} ms)")
    if not total:
        print("No rows evaluated.")
        return
    print("\nConfusion (rows = expected, columns = got)")
    cols = LABELS + ["NO_CLAIM"]
    print(f"{'':<22}" + "".join(f"{c[:8]:>10}" for c in cols))
    for exp in LABELS:
        print(f"{exp:<22}" + "".join(f"{confusion[exp][c]:>10}" for c in cols))
    print(f"\nAccuracy: {correct}/{total} = {100 * correct / total:.0f}%")
    print(f"Verdicts backed by cited evidence (or an honest 'cannot be confirmed'): {cited}/{total}")
    print(f"Average latency: {sum(times) / len(times) / 1000:.1f} s")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "tests/testset.csv"))
