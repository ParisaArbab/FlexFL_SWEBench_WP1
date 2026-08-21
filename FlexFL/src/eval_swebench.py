"""Evaluate FlexFL RAW/RTK Top-5 predictions at FILE LEVEL for SWE-bench."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_top5(result_file: Path) -> list[str]:
    data = json.loads(result_file.read_text(encoding="utf-8"))

    content = ""
    for item in reversed(data):
        if isinstance(item, dict) and item.get("role", "").lower() == "assistant":
            text = item.get("content", "")
            if "Top_1" in text:
                content = text
                break

    if not content:
        raise RuntimeError(f"Could not find Top-5 prediction in {result_file}")

    predictions = []

    for line in content.splitlines():
        line = line.strip()

        for rank in range(1, 6):
            marker = f"Top_{rank} :"

            if marker in line:
                pred = line.split(marker, 1)[1].strip()
                predictions.append(pred)

    return predictions[:5]


def gold_file_to_module(path: str) -> str:
    """
    sympy/printing/ccode.py
        ->
    sympy.printing.ccode
    """
    path = path.replace("\\", "/")

    if path.endswith(".py"):
        path = path[:-3]

    return path.replace("/", ".")


def prediction_hits_file(prediction: str, gold_file: str) -> bool:
    """
    Example:

    prediction:
      sympy.printing.ccode.CCodePrinter._print_Piecewise()

    gold:
      sympy/printing/ccode.py

    module:
      sympy.printing.ccode

    This is a HIT because the prediction starts with:
      sympy.printing.ccode.
    """

    pred = prediction.replace("$", ".")
    pred = pred.split("(", 1)[0].strip()

    gold_module = gold_file_to_module(gold_file)

    return (
        pred == gold_module
        or pred.startswith(gold_module + ".")
    )


def evaluate(result_file: Path, gold_files: list[str]) -> dict:
    predictions = parse_top5(result_file)

    ranked = []
    first_hit = None
    matched_gold = None

    for rank, prediction in enumerate(predictions, start=1):

        matched = None

        for gold_file in gold_files:
            if prediction_hits_file(prediction, gold_file):
                matched = gold_file
                break

        hit = matched is not None

        if hit and first_hit is None:
            first_hit = rank
            matched_gold = matched

        ranked.append(
            {
                "rank": rank,
                "prediction": prediction,
                "file_hit": hit,
                "matched_gold_file": matched,
            }
        )

    return {
        "top5": predictions,
        "predictions": ranked,
        "file_hit": first_hit is not None,
        "file_rank": first_hit,
        "matched_gold_file": matched_gold,
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--bug", required=True)

    parser.add_argument(
        "--condition",
        required=True,
        choices=["raw", "rtk_static"],
    )

    parser.add_argument(
        "--stage",
        default="LR",
        choices=["SR", "LR"],
    )

    parser.add_argument(
        "--rank",
        default="All",
    )

    args = parser.parse_args()

    flexfl_root = Path(__file__).resolve().parents[1]
    project_root = flexfl_root.parent

    meta_file = (
        flexfl_root
        / "data"
        / "instances"
        / args.bug
        / "metadata.json"
    )

    metadata = json.loads(meta_file.read_text(encoding="utf-8"))

    gold_files = (
        metadata.get("gold_changed_python_files")
        or metadata.get("changed_python_files")
        or []
    )

    if not gold_files:
        raise RuntimeError(
            f"No gold changed Python files found for {args.bug}"
        )

    if args.stage == "SR":
        result_file = (
            flexfl_root
            / "res"
            / f"Llama3_SWEbench_SR_{args.condition}"
            / f"{args.bug}.json"
        )
    else:
        result_file = (
            flexfl_root
            / "res"
            / f"Llama3_SWEbench_{args.rank}_{args.condition}"
            / f"{args.bug}.json"
        )

    if not result_file.exists():
        raise FileNotFoundError(result_file)

    result = evaluate(result_file, gold_files)

    output = {
        "instance_id": args.bug,
        "condition": args.condition,
        "stage": args.stage,
        "metric_level": "file",
        "gold_changed_python_files": gold_files,
        **result,
    }

    out_dir = (
        project_root
        / "results"
        / args.bug
        / args.condition
    )

    out_dir.mkdir(parents=True, exist_ok=True)

    out_file = out_dir / f"evaluation_{args.stage.lower()}.json"

    out_file.write_text(
        json.dumps(output, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(output, indent=2))
    print()
    print("=" * 60)
    print(f"{args.bug} | {args.condition.upper()} | {args.stage}")
    print("=" * 60)
    print("Gold files:", ", ".join(gold_files))
    print("FILE HIT:", result["file_hit"])
    print("FILE RANK:", result["file_rank"])
    print("Saved:", out_file)


if __name__ == "__main__":
    main()
