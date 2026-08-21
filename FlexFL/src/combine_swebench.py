"""Combine suspicious methods exactly in FlexFL's source ordering.

FlexFL takes up to five methods from SBIR, then five from Ochiai, then five from
BoostN, then appends Agent4SR's Top-5. This file keeps that combination logic.
It does not substitute another ranker when a required source is absent.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

MODEL = "Llama3"
DATASET = "SWEbench"


def read_ranked_methods(path: Path, limit: int = 5) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"Required FlexFL ranking missing: {path}")
    methods = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if "Method" in row and row["Method"]:
                methods.append(row["Method"].strip())
            elif "File" in row and "Signature" in row:
                methods.append((row["File"] + "." + row["Signature"]).strip())
            if len(methods) >= limit:
                break
    return methods


def agent4sr_top5(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    content = data[-1]["content"]
    out = []
    for line in content.splitlines():
        for i in range(1, 6):
            marker = f"Top_{i} : "
            if marker in line:
                out.append(line.split(marker, 1)[1].strip().replace(", ", ",").replace(" ,", ","))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bug", default="sympy__sympy-20590")
    ap.add_argument("--root", default=None)
    ap.add_argument(
        "--condition",
        default="raw",
        choices=["raw", "rtk_static"],
    )
    args = ap.parse_args()

    src = Path(__file__).resolve().parent
    root = Path(args.root) if args.root else src.parent
    data = root / "data"
    res = root / "res"
    bug = args.bug

    combined = []
    for fl in ("SBIR", "Ochiai", "BoostN"):
        combined.extend(read_ranked_methods(data / "FL_results" / fl / DATASET / f"{bug}_method-susps.csv", 5))

    sr_file = (
        res
        / f"{MODEL}_{DATASET}_SR_{args.condition}"
        / f"{bug}.json"
    )
    if not sr_file.exists():
        raise FileNotFoundError(f"Required Agent4SR result missing: {sr_file}")
    combined.extend(agent4sr_top5(sr_file))

    out_dir = (
        data
        / "input"
        / "suspicious_methods"
        / DATASET
        / f"{MODEL}_All_{args.condition}"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{bug}.txt"
    out_path.write_text("\n".join(combined) + "\n", encoding="utf-8")
    print(f"Wrote {len(combined)} candidates to {out_path}")


if __name__ == "__main__":
    main()
