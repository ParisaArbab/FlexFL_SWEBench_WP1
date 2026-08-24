#!/usr/bin/env bash

cd ~/FlexFL_SWEBench_WP1

source ~/miniconda3/etc/profile.d/conda.sh
conda activate flexfl-swebench

export PYTHONPATH="$PWD/scripts${PYTHONPATH:+:$PYTHONPATH}"
export JAVA_HOME="$HOME/jdk17"
export PATH="$JAVA_HOME/bin:$HOME/apache-maven-3.9.11/bin:$PATH"

BUG="sympy__sympy-13177"

echo "============================================================"
echo "13177 BOOSTN + SBIR"
echo "Started: $(date)"
echo "============================================================"

echo
echo "===== OCHIAI CHECK ====="

OFILE="FlexFL/data/FL_results/Ochiai/SWEbench/${BUG}_method-susps.csv"

if [ -s "$OFILE" ]; then
    echo "OCHIAI: SUCCESS, $(( $(wc -l < "$OFILE") - 1 )) methods"
else
    echo "OCHIAI: MISSING"
fi


echo
echo "============================================================"
echo "BOOSTN"
echo "============================================================"

python -u - <<'PY'
import generate_boostn_sympy as g

bug = "sympy__sympy-13177"

try:
    g.ensure_build()
    g.generate(bug)
except Exception:
    import traceback
    traceback.print_exc()
PY


echo
echo "============================================================"
echo "SBIR"
echo "============================================================"

python -u - <<'PY'
import generate_sbir_sympy as g

bug = "sympy__sympy-13177"

try:
    g.generate(bug)
except Exception:
    import traceback
    traceback.print_exc()
PY


echo
echo "============================================================"
echo "FINAL 13177 STATUS"
echo "============================================================"

for METHOD in Ochiai BoostN SBIR
do
    FILE="FlexFL/data/FL_results/$METHOD/SWEbench/${BUG}_method-susps.csv"

    if [ -s "$FILE" ]; then
        echo "$METHOD: SUCCESS, $(( $(wc -l < "$FILE") - 1 )) methods"
    else
        echo "$METHOD: MISSING"
    fi
done

echo
echo "Finished: $(date)"
echo "============================================================"
