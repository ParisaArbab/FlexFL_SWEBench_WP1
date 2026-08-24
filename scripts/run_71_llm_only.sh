#!/usr/bin/env bash

set -u

PROJECT="$HOME/FlexFL_SWEBench_WP1"
SRC="$PROJECT/FlexFL/src"
DATA="$PROJECT/FlexFL/data"

VALID_BATCH="$PROJECT/configs/chunks/all_71_fl_ready.txt"
LOGDIR="$PROJECT/logs/71bugs"

mkdir -p "$LOGDIR" "$HOME/tmp" "$HOME/.cache/tiktoken"

export LLAMA3_CKPT_DIR="$SRC/Meta-Llama-3-8B-Instruct/original"
export LLAMA3_TOKENIZER="$LLAMA3_CKPT_DIR/tokenizer.model"

export TMPDIR="$HOME/tmp"
export TMP="$HOME/tmp"
export TEMP="$HOME/tmp"
export TIKTOKEN_CACHE_DIR="$HOME/.cache/tiktoken"

export CUDA_VISIBLE_DEVICES=1

VALID_TOTAL=$(grep -cve '^[[:space:]]*$' "$VALID_BATCH")

echo "============================================================"
echo "71-BUG FLEXFL RAW VS RTK - LLM ONLY"
echo "============================================================"
echo "Bugs: $VALID_TOTAL"
echo "GPU: $CUDA_VISIBLE_DEVICES"
echo "Model: $LLAMA3_CKPT_DIR"
echo "Started: $(date)"
echo "============================================================"

echo
echo "===== MODEL CHECK ====="
ls -lh "$LLAMA3_CKPT_DIR/consolidated.00.pth"
ls -lh "$LLAMA3_TOKENIZER"

echo "===== STAGE 5/5: FLEXFL RAW VS RTK ====="

run_logged () {
    NAME="$1"
    OUTFILE="$2"
    shift 2
    echo "  $NAME"
    "$@" >> "$OUTFILE" 2>&1
    CODE=$?
    if [ $CODE -ne 0 ]; then
        echo "  FAILED: $NAME exit=$CODE"
        return $CODE
    fi
    echo "  SUCCESS: $NAME"
    return 0
}

LLM_INDEX=0
COMPLETE=0
FAILED=0

while IFS= read -r BUG; do
    [ -z "$BUG" ] && continue
    LLM_INDEX=$((LLM_INDEX + 1))
    BUGLOG="$LOGDIR/${BUG}_flexfl.log"
    RAW_EVAL="$PROJECT/results/$BUG/raw/evaluation_lr.json"
    RTK_EVAL="$PROJECT/results/$BUG/rtk_static/evaluation_lr.json"

    echo
echo "################################################################"
    echo "[$LLM_INDEX/$VALID_TOTAL] FLEXFL $BUG"
    echo "################################################################"

    if [ -s "$RAW_EVAL" ] && [ -s "$RTK_EVAL" ]; then
        echo "SKIP: RAW and RTK evaluations already exist"
        COMPLETE=$((COMPLETE + 1))
        continue
    fi

    BASE=$((32000 + LLM_INDEX * 10))

    cd "$SRC"

    if [ ! -s "$SRC/../res/Llama3_SWEbench_SR_raw/${BUG}.json" ]; then
        run_logged "RAW Agent4SR" "$BUGLOG" \
            torchrun --nproc_per_node=1 --master_port=$((BASE + 1)) \
            pipeline_swebench.py --dataset SWEbench --stage SR --bug "$BUG" --condition raw \
            || { FAILED=$((FAILED + 1)); continue; }
    else
        echo "  SKIP RAW Agent4SR: result exists"
    fi

    if [ ! -s "$SRC/../res/Llama3_SWEbench_SR_rtk_static/${BUG}.json" ]; then
        run_logged "RTK Agent4SR" "$BUGLOG" \
            torchrun --nproc_per_node=1 --master_port=$((BASE + 2)) \
            pipeline_swebench.py --dataset SWEbench --stage SR --bug "$BUG" --condition rtk_static \
            || { FAILED=$((FAILED + 1)); continue; }
    else
        echo "  SKIP RTK Agent4SR: result exists"
    fi

    run_logged "RAW combine" "$BUGLOG" \
        "$HOME/miniconda3/envs/flexfl-swebench/bin/python" combine_swebench.py --bug "$BUG" --condition raw \
        || { FAILED=$((FAILED + 1)); continue; }

    run_logged "RTK combine" "$BUGLOG" \
        "$HOME/miniconda3/envs/flexfl-swebench/bin/python" combine_swebench.py --bug "$BUG" --condition rtk_static \
        || { FAILED=$((FAILED + 1)); continue; }

    if [ ! -s "$SRC/../res/Llama3_SWEbench_All_raw/${BUG}.json" ]; then
        run_logged "RAW Agent4LR" "$BUGLOG" \
            torchrun --nproc_per_node=1 --master_port=$((BASE + 3)) \
            pipeline_swebench.py --dataset SWEbench --stage LR --rank All --bug "$BUG" --condition raw \
            || { FAILED=$((FAILED + 1)); continue; }
    else
        echo "  SKIP RAW Agent4LR: result exists"
    fi

    if [ ! -s "$SRC/../res/Llama3_SWEbench_All_rtk_static/${BUG}.json" ]; then
        run_logged "RTK Agent4LR" "$BUGLOG" \
            torchrun --nproc_per_node=1 --master_port=$((BASE + 4)) \
            pipeline_swebench.py --dataset SWEbench --stage LR --rank All --bug "$BUG" --condition rtk_static \
            || { FAILED=$((FAILED + 1)); continue; }
    else
        echo "  SKIP RTK Agent4LR: result exists"
    fi

    mkdir -p "$PROJECT/results/$BUG/raw" "$PROJECT/results/$BUG/rtk_static"

    run_logged "RAW file evaluation" "$BUGLOG" \
        "$HOME/miniconda3/envs/flexfl-swebench/bin/python" eval_swebench.py --bug "$BUG" --stage LR --rank All --condition raw \
        || { FAILED=$((FAILED + 1)); continue; }

    run_logged "RTK file evaluation" "$BUGLOG" \
        "$HOME/miniconda3/envs/flexfl-swebench/bin/python" eval_swebench.py --bug "$BUG" --stage LR --rank All --condition rtk_static \
        || { FAILED=$((FAILED + 1)); continue; }

    echo "$BUG COMPLETE"
    COMPLETE=$((COMPLETE + 1))
done < "$VALID_BATCH"

cd "$PROJECT"

# -----------------------------------------------------------------------------
# 4. Final file-level Compression Tax summary for this 71-bug batch.
# -----------------------------------------------------------------------------
"$HOME/miniconda3/envs/flexfl-swebench/bin/python" - <<'PY'
import csv, json
from pathlib import Path

project = Path.home() / "FlexFL_SWEBench_WP1"
batch = project / "configs/chunks/next_sympy_batch.txt"
rows = []

for bug in [x.strip() for x in batch.read_text().splitlines() if x.strip()]:
    raw_path = project / f"results/{bug}/raw/evaluation_lr.json"
    rtk_path = project / f"results/{bug}/rtk_static/evaluation_lr.json"

    if not raw_path.exists() or not rtk_path.exists():
        rows.append({"bug": bug, "raw_hit": "", "raw_rank": "", "rtk_hit": "", "rtk_rank": "", "classification": "INCOMPLETE"})
        continue

    raw = json.loads(raw_path.read_text())
    rtk = json.loads(rtk_path.read_text())
    rh = bool(raw.get("file_hit"))
    th = bool(rtk.get("file_hit"))

    if rh and not th:
        c = "COMPRESSION TAX"
    elif rh and th:
        c = "NO TAX - BOTH HIT"
    elif (not rh) and th:
        c = "RTK IMPROVEMENT"
    else:
        c = "NO TAX - BOTH MISS"

    rows.append({
        "bug": bug,
        "raw_hit": rh,
        "raw_rank": raw.get("file_rank"),
        "rtk_hit": th,
        "rtk_rank": rtk.get("file_rank"),
        "classification": c,
    })

out = project / "results/wp1_71bug_file_level_summary.csv"
out.parent.mkdir(parents=True, exist_ok=True)
with out.open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["bug","raw_hit","raw_rank","rtk_hit","rtk_rank","classification"])
    w.writeheader()
    w.writerows(rows)

complete = [r for r in rows if r["classification"] != "INCOMPLETE"]
tax = [r for r in complete if r["classification"] == "COMPRESSION TAX"]
improve = [r for r in complete if r["classification"] == "RTK IMPROVEMENT"]
both_hit = [r for r in complete if r["classification"] == "NO TAX - BOTH HIT"]
both_miss = [r for r in complete if r["classification"] == "NO TAX - BOTH MISS"]

print("\n============================================================")
print("71-BUG FILE-LEVEL SUMMARY")
print("============================================================")
print("Complete:", len(complete))
print("Incomplete:", len(rows) - len(complete))
print("Compression Tax:", len(tax))
print("RTK Improvement:", len(improve))
print("Both hit:", len(both_hit))
print("Both miss:", len(both_miss))
if complete:
    print("Compression Tax rate:", f"{len(tax)/len(complete):.2%}")
print("Saved:", out)
PY

echo
echo "============================================================"
echo "RUN FINISHED: $(date)"
echo "LLM complete/skipped: $COMPLETE"
echo "LLM failed: $FAILED"
echo "Summary: $PROJECT/results/wp1_71bug_file_level_summary.csv"
echo "============================================================"
