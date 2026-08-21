"""Evaluate FlexFL Top-5 method predictions against SWE-bench gold changed files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_top5(result_file: Path) -> list[str]:
    data = json.loads(result_file.read_text(encoding="utf-8"))
    content = data[-1]["content"]
    preds = []
    for line in content.splitlines():
        for i in range(1, 6):
            marker = f"Top_{i} : "
            if marker in line:
                preds.append(line.split(marker, 1)[1].strip())
    return preds


def method_to_file(method: str) -> str:
    name = method.replace("$", ".").split("(", 1)[0]
    parts = name.split(".")
    # The corpus format is module$Class.method() or module$function().
    # Find the longest prefix that can represent a Python module.
    if "$" in method:
        module = method.split("$", 1)[0]
    else:
        # LR output may normalize '$' to '.'. Use all but the final symbol as a
        # conservative module candidate, then suffix-match against gold paths.
        module = ".".join(parts[:-1])
    return module.replace(".", "/") + ".py"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bug", default="sympy__sympy-20590")
    ap.add_argument("--stage", default="LR", choices=["SR", "LR"])
    ap.add_argument("--rank", default="All")
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    meta = json.loads((root / "data" / "instances" / args.bug / "metadata.json").read_text(encoding="utf-8"))
    if args.stage == "SR":
        result_file = root / "res" / "Llama3_SWEbench_SR" / f"{args.bug}.json"
    else:
        result_file = root / "res" / f"Llama3_SWEbench_{args.rank}" / f"{args.bug}.json"

    preds = parse_top5(result_file)
    gold = meta["changed_python_files"]
    ranked = []
    first_hit = None
    for i, pred in enumerate(preds, 1):
        pred_file = method_to_file(pred)
        hit = any(g.endswith(pred_file) or pred_file.endswith(g) for g in gold)
        if hit and first_hit is None:
            first_hit = i
        ranked.append({"rank": i, "prediction": pred, "predicted_file": pred_file, "gold_file_hit": hit})

    result = {
        "instance_id": args.bug,
        "stage": args.stage,
        "gold_changed_python_files": gold,
        "predictions": ranked,
        "first_gold_file_rank": first_hit,
        "top1": first_hit == 1,
        "top3": first_hit is not None and first_hit <= 3,
        "top5": first_hit is not None and first_hit <= 5,
    }
    out = root.parent / "results" / args.bug
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"evaluation_{args.stage.lower()}.json"
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
