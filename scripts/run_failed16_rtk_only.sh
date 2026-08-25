#!/usr/bin/env bash
set -u

PROJECT="$HOME/FlexFL_SWEBench_WP1"
SRC="$PROJECT/FlexFL/src"
LIST="$PROJECT/configs/chunks/failed16_rtk_only.txt"
LOGDIR="$PROJECT/logs/71bugs"

export LLAMA3_CKPT_DIR="$SRC/Meta-Llama-3-8B-Instruct/original"
export LLAMA3_TOKENIZER="$LLAMA3_CKPT_DIR/tokenizer.model"

export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-1}"

export TMPDIR="/scratch/parbab/FlexFL_SWEBench_WP1/tmp"
export TMP="$TMPDIR"
export TEMP="$TMPDIR"
export TIKTOKEN_CACHE_DIR="/scratch/parbab/FlexFL_SWEBench_WP1/tiktoken_cache"


mkdir -p "$LOGDIR"

TOTAL=$(grep -cve '^[[:space:]]*$' "$LIST")
INDEX=0
SUCCESS=0
FAILED=0

echo "============================================================"
echo "FAILED-16 RTK-ONLY RECOVERY"
echo "Started: $(date)"
echo "Total: $TOTAL"
echo "GPU: $CUDA_VISIBLE_DEVICES"
echo "Llama context limit remains unchanged."
echo "============================================================"

while IFS= read -r BUG
do
    [ -z "$BUG" ] && continue

    INDEX=$((INDEX + 1))

    BUGLOG="$LOGDIR/${BUG}_rtk_recovery.log"

    SR="$PROJECT/FlexFL/res/Llama3_SWEbench_SR_rtk_static/${BUG}.json"
    LR="$PROJECT/FlexFL/res/Llama3_SWEbench_All_rtk_static/${BUG}.json"
    EVAL="$PROJECT/results/$BUG/rtk_static/evaluation_lr.json"

    BASE=$((45000 + INDEX * 10))

    echo
    echo "################################################################"
    echo "[$INDEX/$TOTAL] $BUG"
    echo "################################################################"

    cd "$SRC"

    # ---------------------------------------------------------
    # RTK Agent4SR
    # ---------------------------------------------------------
    if [ -s "$SR" ]; then
        echo "RTK Agent4SR: SKIP, already exists"
    else
        echo "RTK Agent4SR: RUNNING"

        torchrun \
          --nproc_per_node=1 \
          --master_port=$((BASE + 1)) \
          pipeline_swebench.py \
          --dataset SWEbench \
          --stage SR \
          --bug "$BUG" \
          --condition rtk_static \
          2>&1 | tee -a "$BUGLOG"

        CODE=${PIPESTATUS[0]}

        if [ "$CODE" -ne 0 ] || [ ! -s "$SR" ]; then
            echo "RTK Agent4SR: FAILED"
            FAILED=$((FAILED + 1))
            continue
        fi

        echo "RTK Agent4SR: SUCCESS"
    fi

    # ---------------------------------------------------------
    # RTK combine
    # ---------------------------------------------------------
    echo "RTK combine: RUNNING"

    "$HOME/miniconda3/envs/flexfl-swebench/bin/python" \
        combine_swebench.py \
        --bug "$BUG" \
        --condition rtk_static \
        2>&1 | tee -a "$BUGLOG"

    CODE=${PIPESTATUS[0]}

    if [ "$CODE" -ne 0 ]; then
        echo "RTK combine: FAILED"
        FAILED=$((FAILED + 1))
        continue
    fi

    echo "RTK combine: SUCCESS"

    # ---------------------------------------------------------
    # RTK Agent4LR
    # ---------------------------------------------------------
    if [ -s "$LR" ]; then
        echo "RTK Agent4LR: SKIP, already exists"
    else
        echo "RTK Agent4LR: RUNNING"

        torchrun \
          --nproc_per_node=1 \
          --master_port=$((BASE + 2)) \
          pipeline_swebench.py \
          --dataset SWEbench \
          --stage LR \
          --rank All \
          --bug "$BUG" \
          --condition rtk_static \
          2>&1 | tee -a "$BUGLOG"

        CODE=${PIPESTATUS[0]}

        if [ "$CODE" -ne 0 ] || [ ! -s "$LR" ]; then
            echo "RTK Agent4LR: FAILED"
            FAILED=$((FAILED + 1))
            continue
        fi

        echo "RTK Agent4LR: SUCCESS"
    fi

    # ---------------------------------------------------------
    # RTK file evaluation
    # ---------------------------------------------------------
    mkdir -p "$PROJECT/results/$BUG/rtk_static"

    echo "RTK evaluation: RUNNING"

    "$HOME/miniconda3/envs/flexfl-swebench/bin/python" \
        eval_swebench.py \
        --bug "$BUG" \
        --stage LR \
        --rank All \
        --condition rtk_static \
        2>&1 | tee -a "$BUGLOG"

    CODE=${PIPESTATUS[0]}

    if [ "$CODE" -ne 0 ] || [ ! -s "$EVAL" ]; then
        echo "RTK evaluation: FAILED"
        FAILED=$((FAILED + 1))
        continue
    fi

    echo "RTK evaluation: SUCCESS"
    echo "$BUG : RTK RECOVERY COMPLETE"

    SUCCESS=$((SUCCESS + 1))

done < "$LIST"

echo
echo "============================================================"
echo "RTK RECOVERY FINISHED"
echo "Success: $SUCCESS / $TOTAL"
echo "Failed:  $FAILED / $TOTAL"
echo "Finished: $(date)"
echo "============================================================"
