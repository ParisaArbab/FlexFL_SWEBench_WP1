#!/usr/bin/env bash
set -euo pipefail

BUG=${1:-sympy__sympy-20590}

# 0. Prepare SWE-bench inputs and Python method corpus.
python ../../swebench_adapter/prepare_instance.py --instance "$BUG" --out ../data

# 1. Agent4SR, same first stage as FlexFL.
python pipeline_swebench.py --dataset SWEbench --stage SR --bug "$BUG"

# 2. Combine SBIR + Ochiai + BoostN + Agent4SR, same FlexFL ordering.
python combine_swebench.py --bug "$BUG"

# 3. Agent4LR refinement.
python pipeline_swebench.py --dataset SWEbench --stage LR --rank All --bug "$BUG"

# 4. Evaluate final Top-5 against SWE-bench gold changed files.
python eval_swebench.py --bug "$BUG" --stage LR --rank All
