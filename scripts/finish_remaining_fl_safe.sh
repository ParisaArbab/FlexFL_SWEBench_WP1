#!/usr/bin/env bash

set -u

PROJECT="$HOME/FlexFL_SWEBench_WP1"
DATA="$PROJECT/FlexFL/data"
BATCH="$PROJECT/configs/chunks/remaining_sympy_fl.txt"
VALID="$PROJECT/configs/chunks/remaining_sympy_valid.txt"
ONE="$PROJECT/configs/chunks/current_one_bug.txt"
LOGDIR="$PROJECT/logs/71bugs"

PY="$HOME/miniconda3/envs/flexfl-swebench/bin/python"

export FLEXFL_TEST_PYTHON="$HOME/miniconda3/envs/flexfl-sympy38/bin/python"

export JAVA_HOME="$HOME/jdk17"
export PATH="$JAVA_HOME/bin:$HOME/apache-maven-3.9.11/bin:$PATH"

mkdir -p "$LOGDIR"
: > "$VALID"

TOTAL=$(grep -cve '^[[:space:]]*$' "$BATCH")
INDEX=0

echo "============================================================"
echo "SAFE 71-BUG FL COMPLETION"
echo "Started: $(date)"
echo "Total: $TOTAL"
echo "============================================================"

while IFS= read -r BUG
do
    [ -z "$BUG" ] && continue

    INDEX=$((INDEX + 1))

    echo
    echo "################################################################"
    echo "[$INDEX/$TOTAL] $BUG"
    echo "################################################################"

    REPO="$DATA/repos/$BUG"
    SUMMARY="$DATA/instances/$BUG/prepare_summary.json"
    CORPUS="$DATA/input/buggy_program/SWEbench/${BUG}.corpusRawMethodLevelGranularity"

    OCHIAI="$DATA/FL_results/Ochiai/SWEbench/${BUG}_method-susps.csv"
    BOOSTN="$DATA/FL_results/BoostN/SWEbench/${BUG}_method-susps.csv"
    SBIR="$DATA/FL_results/SBIR/SWEbench/${BUG}_method-susps.csv"

    # ---------------------------------------------------------
    # PREPARATION
    # ---------------------------------------------------------

    if [ ! -d "$REPO/.git" ] || [ ! -s "$SUMMARY" ] || [ ! -s "$CORPUS" ]; then

        echo "PREPARE: required"

        # Remove only an incomplete clone, if one exists
        if [ -e "$REPO" ] && [ ! -d "$REPO/.git" ]; then
            echo "Removing incomplete repository clone"
            rm -rf "$REPO"
        fi

        "$PY" "$PROJECT/swebench_adapter/prepare_instance.py" \
            --instance "$BUG" \
            --out "$DATA" \
            > "$LOGDIR/${BUG}_prepare_retry.log" 2>&1 || true
    fi

    if [ ! -d "$REPO/.git" ] || [ ! -s "$CORPUS" ]; then
        echo "PREPARE: FAILED"
        echo "See: $LOGDIR/${BUG}_prepare_retry.log"
        continue
    fi

    echo "PREPARE: OK"

    # Each generator receives ONLY this bug
    printf '%s\n' "$BUG" > "$ONE"
    export FLEXFL_BUG_LIST="$ONE"

    # ---------------------------------------------------------
    # OCHIAI
    # ---------------------------------------------------------

    if [ -s "$OCHIAI" ]; then
        ROWS=$(( $(wc -l < "$OCHIAI") - 1 ))
        echo "OCHIAI: SKIP, already exists ($ROWS methods)"
    else
        echo "OCHIAI: RUNNING"

        find "$REPO" \
            -name ".coverage*" \
            -type f \
            -delete 2>/dev/null || true

        "$PY" -u "$PROJECT/scripts/generate_ochiai_sympy.py" \
            > "$LOGDIR/${BUG}_ochiai.log" 2>&1 || true

        if [ -s "$OCHIAI" ]; then
            ROWS=$(( $(wc -l < "$OCHIAI") - 1 ))
            echo "OCHIAI: SUCCESS ($ROWS methods)"
        else
            echo "OCHIAI: FAILED"
            echo "See: $LOGDIR/${BUG}_ochiai.log"
            continue
        fi
    fi

    # ---------------------------------------------------------
    # BOOSTN
    # ---------------------------------------------------------

    if [ -s "$BOOSTN" ]; then
        ROWS=$(( $(wc -l < "$BOOSTN") - 1 ))
        echo "BOOSTN: SKIP, already exists ($ROWS methods)"
    else
        echo "BOOSTN: RUNNING"

        "$PY" -u "$PROJECT/scripts/generate_boostn_sympy.py" \
            > "$LOGDIR/${BUG}_boostn.log" 2>&1 || true

        if [ -s "$BOOSTN" ]; then
            ROWS=$(( $(wc -l < "$BOOSTN") - 1 ))
            echo "BOOSTN: SUCCESS ($ROWS methods)"
        else
            echo "BOOSTN: FAILED"
            echo "See: $LOGDIR/${BUG}_boostn.log"
            continue
        fi
    fi

    # ---------------------------------------------------------
    # SBIR
    # ---------------------------------------------------------

    if [ -s "$SBIR" ]; then
        ROWS=$(( $(wc -l < "$SBIR") - 1 ))
        echo "SBIR: SKIP, already exists ($ROWS methods)"
    else
        echo "SBIR: RUNNING"

        "$PY" -u "$PROJECT/scripts/generate_sbir_sympy.py" \
            > "$LOGDIR/${BUG}_sbir.log" 2>&1 || true

        if [ -s "$SBIR" ]; then
            ROWS=$(( $(wc -l < "$SBIR") - 1 ))
            echo "SBIR: SUCCESS ($ROWS methods)"
        else
            echo "SBIR: FAILED"
            echo "See: $LOGDIR/${BUG}_sbir.log"
            continue
        fi
    fi

    # ---------------------------------------------------------
    # READY FOR FLEXFL
    # ---------------------------------------------------------

    if [ -s "$OCHIAI" ] && [ -s "$BOOSTN" ] && [ -s "$SBIR" ]; then
        echo "$BUG" >> "$VALID"
        echo "$BUG : READY FOR FLEXFL RAW/RTK"
    fi

done < "$BATCH"

echo
echo "============================================================"
echo "FL COMPLETION FINISHED"
echo "============================================================"

READY=$(wc -l < "$VALID")

echo "Ready for FlexFL: $READY / $TOTAL"
echo "Saved:"
echo "$VALID"

echo
echo "===== RESULT COUNTS ====="

echo -n "Ochiai: "
while read -r B; do
    [ -s "$DATA/FL_results/Ochiai/SWEbench/${B}_method-susps.csv" ] && echo "$B"
done < "$BATCH" | wc -l

echo -n "BoostN: "
while read -r B; do
    [ -s "$DATA/FL_results/BoostN/SWEbench/${B}_method-susps.csv" ] && echo "$B"
done < "$BATCH" | wc -l

echo -n "SBIR: "
while read -r B; do
    [ -s "$DATA/FL_results/SBIR/SWEbench/${B}_method-susps.csv" ] && echo "$B"
done < "$BATCH" | wc -l

echo
echo "Finished: $(date)"

