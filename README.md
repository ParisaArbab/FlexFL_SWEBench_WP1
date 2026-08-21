# FlexFL on SWE-bench, WP1

This repository adapts the original FlexFL replication pipeline to SWE-bench for Work Package 1.

## First bug

`sympy__sympy-20590`

## Goal

Keep the FlexFL localization method as unchanged as possible while replacing only the dataset/language interface needed for SWE-bench Python projects.

## Preserved FlexFL flow

```text
Bug report + trigger test
        |
     Agent4SR
        |
SBIR + Ochiai + BoostN + Agent4SR
        |
   combined candidate list
        |
     Agent4LR
        |
 final Top-5 culprit methods
```

Preserved details include:

- SR and LR stages
- 10 function-call budget
- iterative source-code tool calls
- Top-5 method ranking
- combination order used by FlexFL
- Llama-3-8B-Instruct as the default model
- temperature = 0
- top_p = 1.0

## SWE-bench-only adaptations

- download a SWE-bench Lite instance
- checkout its `base_commit`
- convert Python source code into the method-level corpus expected by FlexFL
- keep the original source-navigation tool API for Python
- evaluate predictions using the SWE-bench gold patch

## Run one bug

From `FlexFL/src`:

```bash
bash run_swebench.sh sympy__sympy-20590
```

The intended sequence is:

```text
prepare_instance.py
pipeline_swebench.py --stage SR
combine_swebench.py
pipeline_swebench.py --stage LR
eval_swebench.py
```

## Important fidelity rule

This repository does not invent replacement results for missing FlexFL components. A complete FlexFL run requires SWE-bench method rankings from SBIR, Ochiai, and BoostN plus the Agent4SR result before Agent4LR can run.

See `results/sympy__sympy-20590/STATUS.md` for the current experiment state.
