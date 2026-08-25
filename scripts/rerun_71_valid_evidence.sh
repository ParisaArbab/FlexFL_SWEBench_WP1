#!/usr/bin/env bash

set -u
set -o pipefail

PROJECT="$HOME/FlexFL_SWEBench_WP1"
SRC="$PROJECT/FlexFL/src"
LIST="$PROJECT/configs/chunks/all_71_fl_ready.txt"
LOGDIR="$PROJECT/logs/71bugs_valid_evidence"

SCRATCH="/scratch/parbab/FlexFL_SWEBench_WP1"
TMPBASE="$SCRATCH/tmp"
CACHEBASE="$SCRATCH/cache"

mkdir -p "$LOGDIR" "$TMPBASE" "$CACHEBASE/tiktoken"

export LLAMA3_CKPT_DIR="$SRC/Meta-Llama-3-8B-Instruct/original"
export LLAMA3_TOKENIZER="$LLAMA3_CKPT_DIR/tokenizer.model"

export TMPDIR="$TMPBASE"
export TMP="$TMPBASE"
export TEMP="$TMPBASE"
export TIKTOKEN_CACHE_DIR="$CACHEBASE/tiktoken"
export XDG_CACHE_HOME="$CACHEBASE"

export CUDA_VISIBLE_DEVICES=1

PY="$HOME/miniconda3/envs/flexfl-swebench/bin/python"

TOTAL=$(grep -cve '^[[:space:]]*$' "$LIST")

echo "============================================================"
echo "CORRECT 71-BUG RAW VS RTK RUN"
echo "Uses real RAW/RTK terminal evidence"
echo "============================================================"
echo "Total bugs : $TOTAL"
echo "GPU        : $CUDA_VISIBLE_DEVICES"
echo "Started    : $(date)"
echo "============================================================"

# ----------------------------------------------------------
# Archive old LLM outputs so they cannot accidentally be reused
# ----------------------------------------------------------

STAMP=$(date +%Y%m%d_%H%M%S)
ARCHIVE="$PROJECT/results/pre_valid_evidence_llm_$STAMP"

mkdir -p "$ARCHIVE/res" "$ARCHIVE/evaluations"

echo
echo "===== ARCHIVE OLD LLM RESULTS ====="

for D in \
    Llama3_SWEbench_SR_raw \
    Llama3_SWEbench_SR_rtk_static \
    Llama3_SWEbench_All_raw \
    Llama3_SWEbench_All_rtk_static
do
    if [ -d "$PROJECT/FlexFL/res/$D" ]; then
        mv "$PROJECT/FlexFL/res/$D" "$ARCHIVE/res/$D"
        echo "Archived: $D"
    fi
done

mkdir -p \
    "$PROJECT/FlexFL/res/Llama3_SWEbench_SR_raw" \
    "$PROJECT/FlexFL/res/Llama3_SWEbench_SR_rtk_static" \
    "$PROJECT/FlexFL/res/Llama3_SWEbench_All_raw" \
    "$PROJECT/FlexFL/res/Llama3_SWEbench_All_rtk_static"

# Move ONLY old evaluation files.
# Keep pytest_output.txt because that is the new valid evidence.
while IFS= read -r BUG; do
    [ -z "$BUG" ] && continue

    for COND in raw rtk_static; do
        OLD="$PROJECT/results/$BUG/$COND/evaluation_lr.json"

        if [ -f "$OLD" ]; then
            mkdir -p "$ARCHIVE/evaluations/$BUG/$COND"
            mv "$OLD" "$ARCHIVE/evaluations/$BUG/$COND/"
        fi
    done
done < "$LIST"

echo "Old LLM results archived at:"
echo "$ARCHIVE"

# ----------------------------------------------------------
# Verify evidence
# ----------------------------------------------------------

echo
echo "===== EVIDENCE CHECK ====="

BAD=0

while IFS= read -r BUG; do
    [ -z "$BUG" ] && continue

    RAW="$PROJECT/results/$BUG/raw/pytest_output.txt"
    RTK="$PROJECT/results/$BUG/rtk_static/pytest_output.txt"

    if [ ! -s "$RAW" ] || [ ! -s "$RTK" ]; then
        echo "MISSING EVIDENCE: $BUG"
        BAD=$((BAD+1))
    fi
done < "$LIST"

echo "Evidence problems: $BAD"

if [ "$BAD" -ne 0 ]; then
    echo "STOP: evidence is incomplete."
    exit 1
fi

echo "All 71 bugs have RAW and RTK evidence."

run_cmd () {
    NAME="$1"
    OUTFILE="$2"
    shift 2

    echo
    echo "----- $NAME -----"

    "$@" 2>&1 | tee -a "$OUTFILE"
    CODE=${PIPESTATUS[0]}

    if [ "$CODE" -eq 0 ]; then
        echo "SUCCESS: $NAME"
    else
        echo "FAILED: $NAME exit=$CODE"
    fi

    return "$CODE"
}

INDEX=0

while IFS= read -r BUG; do

    [ -z "$BUG" ] && continue
    INDEX=$((INDEX+1))

    BUGLOG="$LOGDIR/${BUG}.log"
    BASE=$((41000 + INDEX * 10))

    echo
    echo "################################################################"
    echo "[$INDEX/$TOTAL] $BUG"
    echo "################################################################"

    cd "$SRC"

    RAW_SR=0
    RTK_SR=0
    RAW_LR=0
    RTK_LR=0

    # ============================
    # RAW Agent4SR
    # ============================

    if run_cmd \
        "RAW Agent4SR" "$BUGLOG" \
        torchrun \
        --nproc_per_node=1 \
        --master_port=$((BASE+1)) \
        pipeline_swebench.py \
        --dataset SWEbench \
        --stage SR \
        --bug "$BUG" \
        --condition raw
    then
        RAW_SR=1
    fi

    # ============================
    # RTK Agent4SR
    # IMPORTANT: runs even if RAW failed
    # ============================

    if run_cmd \
        "RTK Agent4SR" "$BUGLOG" \
        torchrun \
        --nproc_per_node=1 \
        --master_port=$((BASE+2)) \
        pipeline_swebench.py \
        --dataset SWEbench \
        --stage SR \
        --bug "$BUG" \
        --condition rtk_static
    then
        RTK_SR=1
    fi

    # ============================
    # RAW combine + Agent4LR
    # ============================

    if [ "$RAW_SR" -eq 1 ]; then

        if run_cmd \
            "RAW combine" "$BUGLOG" \
            "$PY" combine_swebench.py \
            --bug "$BUG" \
            --condition raw
        then

            if run_cmd \
                "RAW Agent4LR" "$BUGLOG" \
                torchrun \
                --nproc_per_node=1 \
                --master_port=$((BASE+3)) \
                pipeline_swebench.py \
                --dataset SWEbench \
                --stage LR \
                --rank All \
                --bug "$BUG" \
                --condition raw
            then
                RAW_LR=1
            fi
        fi
    fi

    # ============================
    # RTK combine + Agent4LR
    # ============================

    if [ "$RTK_SR" -eq 1 ]; then

        if run_cmd \
            "RTK combine" "$BUGLOG" \
            "$PY" combine_swebench.py \
            --bug "$BUG" \
            --condition rtk_static
        then

            if run_cmd \
                "RTK Agent4LR" "$BUGLOG" \
                torchrun \
                --nproc_per_node=1 \
                --master_port=$((BASE+4)) \
                pipeline_swebench.py \
                --dataset SWEbench \
                --stage LR \
                --rank All \
                --bug "$BUG" \
                --condition rtk_static
            then
                RTK_LR=1
            fi
        fi
    fi

    cd "$PROJECT"

    mkdir -p \
        "results/$BUG/raw" \
        "results/$BUG/rtk_static"

    # ============================
    # Evaluate independently
    # ============================

    cd "$SRC"

    if [ "$RAW_LR" -eq 1 ]; then
        run_cmd \
            "RAW evaluation" "$BUGLOG" \
            "$PY" eval_swebench.py \
            --bug "$BUG" \
            --stage LR \
            --rank All \
            --condition raw || true
    fi

    if [ "$RTK_LR" -eq 1 ]; then
        run_cmd \
            "RTK evaluation" "$BUGLOG" \
            "$PY" eval_swebench.py \
            --bug "$BUG" \
            --stage LR \
            --rank All \
            --condition rtk_static || true
    fi

done < "$LIST"

cd "$PROJECT"

echo
echo "============================================================"
echo "71-BUG CORRECTED LLM RUN FINISHED"
echo "Finished: $(date)"
echo "============================================================"
