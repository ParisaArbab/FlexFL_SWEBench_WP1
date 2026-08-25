#!/usr/bin/env bash

# Resumable SWE-bench Lite SymPy RAW-vs-RTK experiment.
# Uses configs/chunks/next_sympy_batch.txt and continues past failed bugs.

set -u

PROJECT="$HOME/FlexFL_SWEBench_WP1"
SRC="$PROJECT/FlexFL/src"
DATA="$PROJECT/FlexFL/data"
BATCH="$PROJECT/configs/chunks/next_sympy_batch.txt"
VALID_BATCH="$PROJECT/configs/chunks/next_sympy_valid.txt"
LOGDIR="$PROJECT/logs/71bugs"

mkdir -p "$LOGDIR" "$HOME/tmp" "$HOME/.cache/tiktoken"

export FLEXFL_BUG_LIST="$BATCH"
export FLEXFL_TEST_PYTHON="$HOME/miniconda3/envs/flexfl-sympy38/bin/python"
export LLAMA3_CKPT_DIR="$SRC/Meta-Llama-3-8B-Instruct/original"
export LLAMA3_TOKENIZER="$LLAMA3_CKPT_DIR/tokenizer.model"
export TMPDIR="$HOME/tmp"
export TMP="$HOME/tmp"
export TEMP="$HOME/tmp"
export TIKTOKEN_CACHE_DIR="$HOME/.cache/tiktoken"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-1}"
export JAVA_HOME="$HOME/jdk17"
export PATH="$JAVA_HOME/bin:$HOME/apache-maven-3.9.11/bin:$PATH"

if [ ! -s "$BATCH" ]; then
    echo "ERROR: missing batch file: $BATCH"
    exit 2
fi

TOTAL=$(grep -cve '^\s*$' "$BATCH")
echo "============================================================"
echo "71-BUG SYMPY RAW VS RTK RUN"
echo "Batch: $BATCH"
echo "Instances: $TOTAL"
echo "GPU: $CUDA_VISIBLE_DEVICES"
echo "Started: $(date)"
echo "============================================================"

echo
echo "===== PRE-FLIGHT ====="
df -h "$HOME" || true
"$HOME/miniconda3/envs/flexfl-swebench/bin/python" --version
"$FLEXFL_TEST_PYTHON" --version || true
ls -lh "$LLAMA3_CKPT_DIR/consolidated.00.pth" "$LLAMA3_TOKENIZER" || exit 3

# -----------------------------------------------------------------------------
# 1. Prepare every missing SWE-bench instance.
# -----------------------------------------------------------------------------
echo
echo "===== STAGE 1/5: PREPARE INSTANCES ====="
PREP_OK=0
PREP_FAIL=0
INDEX=0

while IFS= read -r BUG; do
    [ -z "$BUG" ] && continue
    INDEX=$((INDEX + 1))
    SUMMARY="$DATA/instances/$BUG/prepare_summary.json"
    REPO="$DATA/repos/$BUG/.git"
    CORPUS="$DATA/input/buggy_program/SWEbench/${BUG}.corpusRawMethodLevelGranularity"

    echo "[$INDEX/$TOTAL] PREPARE $BUG"

    if [ -s "$SUMMARY" ] && [ -d "$REPO" ] && [ -s "$CORPUS" ]; then
        echo "  SKIP: already prepared"
        PREP_OK=$((PREP_OK + 1))
        continue
    fi

    if "$HOME/miniconda3/envs/flexfl-swebench/bin/python" \
        "$PROJECT/swebench_adapter/prepare_instance.py" \
        --instance "$BUG" \
        --out "$DATA" \
        > "$LOGDIR/${BUG}_prepare.log" 2>&1; then
        echo "  PREPARED"
        PREP_OK=$((PREP_OK + 1))
    else
        echo "  PREPARE FAILED. See $LOGDIR/${BUG}_prepare.log"
        PREP_FAIL=$((PREP_FAIL + 1))
    fi
done < "$BATCH"

echo "Preparation: OK=$PREP_OK FAILED=$PREP_FAIL"

# -----------------------------------------------------------------------------
# 2. Traditional FL. Each generator is already resumable and skips valid output.
# -----------------------------------------------------------------------------
echo
echo "===== STAGE 2/5: OCHIAI ====="
cd "$PROJECT"
"$HOME/miniconda3/envs/flexfl-swebench/bin/python" -u scripts/generate_ochiai_sympy.py \
    > "$LOGDIR/ochiai.log" 2>&1 || true
echo "Ochiai finished. See $LOGDIR/ochiai.log"

echo
echo "===== STAGE 3/5: BOOSTN ====="
"$HOME/miniconda3/envs/flexfl-swebench/bin/python" -u scripts/generate_boostn_sympy.py \
    > "$LOGDIR/boostn.log" 2>&1 || true
echo "BoostN finished. See $LOGDIR/boostn.log"

echo
echo "===== STAGE 4/5: SBIR ====="
"$HOME/miniconda3/envs/flexfl-swebench/bin/python" -u scripts/generate_sbir_sympy.py \
    > "$LOGDIR/sbir.log" 2>&1 || true
echo "SBIR finished. See $LOGDIR/sbir.log"

# Build a list containing only bugs with all three required FL rankings.
: > "$VALID_BATCH"
while IFS= read -r BUG; do
    [ -z "$BUG" ] && continue
    O="$DATA/FL_results/Ochiai/SWEbench/${BUG}_method-susps.csv"
    B="$DATA/FL_results/BoostN/SWEbench/${BUG}_method-susps.csv"
    S="$DATA/FL_results/SBIR/SWEbench/${BUG}_method-susps.csv"
    if [ -s "$O" ] && [ -s "$B" ] && [ -s "$S" ]; then
        echo "$BUG" >> "$VALID_BATCH"
    else
        echo "SKIP LLM $BUG: missing one or more FL rankings"
    fi
done < "$BATCH"

VALID_TOTAL=$(grep -cve '^\s*$' "$VALID_BATCH" 2>/dev/null || echo 0)
echo "Valid for FlexFL LLM stage: $VALID_TOTAL / $TOTAL"
echo "Saved valid list: $VALID_BATCH"

# -----------------------------------------------------------------------------
# 3. RAW/RTK Agent4SR + combine + Agent4LR + file-level evaluation.
#    One GPU, sequential, resumable.
# -----------------------------------------------------------------------------
echo
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
