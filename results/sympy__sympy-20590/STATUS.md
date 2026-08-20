# sympy__sympy-20590 status

Current state: **FlexFL adaptation prepared, localization result not yet generated.**

What is preserved from FlexFL:
- Agent4SR first stage
- 10 function-call budget
- Top-5 method output
- SBIR + Ochiai + BoostN + Agent4SR candidate combination
- Agent4LR refinement stage
- Llama-3-8B-Instruct default model settings, temperature 0, top_p 1.0

SWE-bench-only adaptations:
- dataset loader and checkout
- Python AST method corpus generation
- Python source navigation while keeping the original FlexFL tool API
- SWE-bench gold-patch evaluation

A true final FlexFL ranking is intentionally not written yet because the required SWE-bench SBIR, Ochiai, and BoostN method-suspiciousness inputs and Llama-3-8B-Instruct inference have not yet run. No synthetic/fake ranking is used.
