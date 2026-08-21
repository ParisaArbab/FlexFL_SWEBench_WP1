#!/usr/bin/env bash

set -u

PROJECT="$HOME/FlexFL_SWEBench_WP1"
SRC="$PROJECT/FlexFL/src"

export LLAMA3_CKPT_DIR="$SRC/Meta-Llama-3-8B-Instruct/original"
export LLAMA3_TOKENIZER="$LLAMA3_CKPT_DIR/tokenizer.model"

export TMPDIR="$HOME/tmp"
export TMP="$HOME/tmp"
export TEMP="$HOME/tmp"
export TIKTOKEN_CACHE_DIR="$HOME/.cache/tiktoken"

export CUDA_VISIBLE_DEVICES=1

BUGS=(
    "sympy__sympy-11870"
    "sympy__sympy-11897"
    "sympy__sympy-12171"
    "sympy__sympy-12236"
)

mkdir -p "$PROJECT/logs/4bugs"

run_step () {
    NAME="$1"
    shift

    echo
    echo "============================================================"
    echo "$NAME"
    echo "============================================================"

    "$@"
    CODE=$?

    if [ $CODE -ne 0 ]; then
        echo "FAILED: $NAME, exit=$CODE"
        return $CODE
    fi

    echo "SUCCESS: $NAME"
    return 0
}

INDEX=0

for BUG in "${BUGS[@]}"; do

    INDEX=$((INDEX + 1))

    RAW_SR_PORT=$((29700 + INDEX * 10 + 1))
    RTK_SR_PORT=$((29700 + INDEX * 10 + 2))
    RAW_LR_PORT=$((29700 + INDEX * 10 + 3))
    RTK_LR_PORT=$((29700 + INDEX * 10 + 4))

    BUGLOG="$PROJECT/logs/4bugs/${BUG}.log"

    echo
    echo "################################################################"
    echo "STARTING $BUG"
    echo "################################################################"

    (
        cd "$SRC"

        # ---------------------------------------------------------
        # 1. RAW Agent4SR
        # ---------------------------------------------------------
        run_step "RAW Agent4SR: $BUG" \
            torchrun \
            --nproc_per_node=1 \
            --master_port="$RAW_SR_PORT" \
            pipeline_swebench.py \
            --dataset SWEbench \
            --stage SR \
            --bug "$BUG" \
            --condition raw \
        || exit 11

        # ---------------------------------------------------------
        # 2. RTK Agent4SR
        # ---------------------------------------------------------
        run_step "RTK Agent4SR: $BUG" \
            torchrun \
            --nproc_per_node=1 \
            --master_port="$RTK_SR_PORT" \
            pipeline_swebench.py \
            --dataset SWEbench \
            --stage SR \
            --bug "$BUG" \
            --condition rtk_static \
        || exit 12

        # ---------------------------------------------------------
        # 3. Build RAW candidate list
        # ---------------------------------------------------------
        run_step "RAW combine: $BUG" \
            python combine_swebench.py \
            --bug "$BUG" \
            --condition raw \
        || exit 13

        # ---------------------------------------------------------
        # 4. Build RTK candidate list
        # ---------------------------------------------------------
        run_step "RTK combine: $BUG" \
            python combine_swebench.py \
            --bug "$BUG" \
            --condition rtk_static \
        || exit 14

        # ---------------------------------------------------------
        # 5. RAW Agent4LR
        # ---------------------------------------------------------
        run_step "RAW Agent4LR: $BUG" \
            torchrun \
            --nproc_per_node=1 \
            --master_port="$RAW_LR_PORT" \
            pipeline_swebench.py \
            --dataset SWEbench \
            --stage LR \
            --rank All \
            --bug "$BUG" \
            --condition raw \
        || exit 15

        # ---------------------------------------------------------
        # 6. RTK Agent4LR
        # ---------------------------------------------------------
        run_step "RTK Agent4LR: $BUG" \
            torchrun \
            --nproc_per_node=1 \
            --master_port="$RTK_LR_PORT" \
            pipeline_swebench.py \
            --dataset SWEbench \
            --stage LR \
            --rank All \
            --bug "$BUG" \
            --condition rtk_static \
        || exit 16

        # ---------------------------------------------------------
        # 7. RAW file-level evaluation
        # ---------------------------------------------------------
        run_step "RAW evaluation: $BUG" \
            python eval_swebench.py \
            --bug "$BUG" \
            --stage LR \
            --rank All \
            --condition raw \
        || exit 17

        # ---------------------------------------------------------
        # 8. RTK file-level evaluation
        # ---------------------------------------------------------
        run_step "RTK evaluation: $BUG" \
            python eval_swebench.py \
            --bug "$BUG" \
            --stage LR \
            --rank All \
            --condition rtk_static \
        || exit 18

        echo
        echo "################################################################"
        echo "FINISHED $BUG"
        echo "################################################################"

    ) > "$BUGLOG" 2>&1

    CODE=$?

    if [ $CODE -eq 0 ]; then
        echo "$BUG : COMPLETE"
    else
        echo "$BUG : FAILED, code=$CODE"
        echo "Check: $BUGLOG"
    fi

done

echo
echo "============================================================"
echo "ALL 4 BUG ATTEMPTS FINISHED"
echo "============================================================"

cd "$PROJECT"

python - <<'PY'
import csv
import json
from pathlib import Path

bugs = [
    "sympy__sympy-11400",
    "sympy__sympy-11870",
    "sympy__sympy-11897",
    "sympy__sympy-12171",
    "sympy__sympy-12236",
]

rows = []

for bug in bugs:

    raw_file = Path(f"results/{bug}/raw/evaluation_lr.json")
    rtk_file = Path(f"results/{bug}/rtk_static/evaluation_lr.json")

    if not raw_file.exists() or not rtk_file.exists():
        rows.append({
            "bug": bug,
            "raw_hit": "",
            "raw_rank": "",
            "rtk_hit": "",
            "rtk_rank": "",
            "classification": "INCOMPLETE",
        })
        continue

    raw = json.loads(raw_file.read_text())
    rtk = json.loads(rtk_file.read_text())

    raw_hit = raw["file_hit"]
    rtk_hit = rtk["file_hit"]

    if raw_hit and not rtk_hit:
        classification = "COMPRESSION TAX"
    elif raw_hit and rtk_hit:
        classification = "NO TAX - BOTH HIT"
    elif not raw_hit and rtk_hit:
        classification = "RTK IMPROVEMENT"
    else:
        classification = "NO TAX - BOTH MISS"

    rows.append({
        "bug": bug,
        "raw_hit": raw_hit,
        "raw_rank": raw["file_rank"],
        "rtk_hit": rtk_hit,
        "rtk_rank": rtk["file_rank"],
        "classification": classification,
    })

out = Path("results/wp1_5bug_file_level_summary.csv")

with out.open("w", newline="") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "bug",
            "raw_hit",
            "raw_rank",
            "rtk_hit",
            "rtk_rank",
            "classification",
        ],
    )
    writer.writeheader()
    writer.writerows(rows)

print()
print("=" * 100)
print("FINAL 5-BUG FILE-LEVEL COMPRESSION TAX")
print("=" * 100)

for r in rows:
    print(
        f"{r['bug']:25} "
        f"RAW={str(r['raw_hit']):5} "
        f"RANK={str(r['raw_rank']):4} "
        f"RTK={str(r['rtk_hit']):5} "
        f"RANK={str(r['rtk_rank']):4} "
        f"{r['classification']}"
    )

print()
print("Saved:", out)
PY
