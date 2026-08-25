# Compression Tax Error Taxonomy

This report analyzes SWE-bench SymPy bugs for which FlexFL successfully localized the gold file using RAW terminal output but failed when the same debugging evidence was compressed with RTK.

## Compression Tax Cases

Total cases: **12**

## Taxonomy Summary

| Category | Cases |
|---|---:|
| MULTIPLE_DEBUGGING_CLUES_REMOVED | 12 |

## Per-Bug Analysis

### sympy__sympy-13773

- RAW file rank: 1
- RTK file rank: None
- RAW bytes: 2818
- RTK bytes: 671
- Reduction: 76.19%
- RAW traceback frames: 6
- RTK traceback frames: 0
- Removed source references: 5
- Removed assertion lines: 1
- Removed test names: 2
- RAW/RTK Top-5 overlap: 0/5
- Candidate taxonomy: **MULTIPLE_DEBUGGING_CLUES_REMOVED**

### sympy__sympy-13971

- RAW file rank: 1
- RTK file rank: None
- RAW bytes: 4066
- RTK bytes: 476
- Reduction: 88.29%
- RAW traceback frames: 13
- RTK traceback frames: 2
- Removed source references: 10
- Removed assertion lines: 0
- Removed test names: 2
- RAW/RTK Top-5 overlap: 0/5
- Candidate taxonomy: **MULTIPLE_DEBUGGING_CLUES_REMOVED**

### sympy__sympy-14308

- RAW file rank: 1
- RTK file rank: None
- RAW bytes: 4308
- RTK bytes: 672
- Reduction: 84.40%
- RAW traceback frames: 2
- RTK traceback frames: 0
- Removed source references: 6
- Removed assertion lines: 4
- Removed test names: 4
- RAW/RTK Top-5 overlap: 1/5
- Candidate taxonomy: **MULTIPLE_DEBUGGING_CLUES_REMOVED**

### sympy__sympy-15011

- RAW file rank: 1
- RTK file rank: None
- RAW bytes: 1280
- RTK bytes: 188
- Reduction: 85.31%
- RAW traceback frames: 2
- RTK traceback frames: 0
- Removed source references: 3
- Removed assertion lines: 0
- Removed test names: 2
- RAW/RTK Top-5 overlap: 0/5
- Candidate taxonomy: **MULTIPLE_DEBUGGING_CLUES_REMOVED**

### sympy__sympy-15346

- RAW file rank: 1
- RTK file rank: None
- RAW bytes: 1023
- RTK bytes: 175
- Reduction: 82.89%
- RAW traceback frames: 1
- RTK traceback frames: 0
- Removed source references: 2
- Removed assertion lines: 1
- Removed test names: 2
- RAW/RTK Top-5 overlap: 0/5
- Candidate taxonomy: **MULTIPLE_DEBUGGING_CLUES_REMOVED**

### sympy__sympy-16281

- RAW file rank: 1
- RTK file rank: None
- RAW bytes: 2004
- RTK bytes: 175
- Reduction: 91.27%
- RAW traceback frames: 2
- RTK traceback frames: 0
- Removed source references: 2
- Removed assertion lines: 2
- Removed test names: 3
- RAW/RTK Top-5 overlap: 0/5
- Candidate taxonomy: **MULTIPLE_DEBUGGING_CLUES_REMOVED**

### sympy__sympy-16503

- RAW file rank: 1
- RTK file rank: None
- RAW bytes: 992
- RTK bytes: 175
- Reduction: 82.36%
- RAW traceback frames: 1
- RTK traceback frames: 0
- Removed source references: 2
- Removed assertion lines: 1
- Removed test names: 2
- RAW/RTK Top-5 overlap: 0/5
- Candidate taxonomy: **MULTIPLE_DEBUGGING_CLUES_REMOVED**

### sympy__sympy-18189

- RAW file rank: 1
- RTK file rank: None
- RAW bytes: 1034
- RTK bytes: 175
- Reduction: 83.08%
- RAW traceback frames: 1
- RTK traceback frames: 0
- Removed source references: 2
- Removed assertion lines: 1
- Removed test names: 1
- RAW/RTK Top-5 overlap: 0/5
- Candidate taxonomy: **MULTIPLE_DEBUGGING_CLUES_REMOVED**

### sympy__sympy-19007

- RAW file rank: 1
- RTK file rank: None
- RAW bytes: 3557
- RTK bytes: 175
- Reduction: 95.08%
- RAW traceback frames: 4
- RTK traceback frames: 0
- Removed source references: 2
- Removed assertion lines: 4
- Removed test names: 4
- RAW/RTK Top-5 overlap: 0/5
- Candidate taxonomy: **MULTIPLE_DEBUGGING_CLUES_REMOVED**

### sympy__sympy-20154

- RAW file rank: 1
- RTK file rank: None
- RAW bytes: 1989
- RTK bytes: 175
- Reduction: 91.20%
- RAW traceback frames: 2
- RTK traceback frames: 0
- Removed source references: 2
- Removed assertion lines: 2
- Removed test names: 3
- RAW/RTK Top-5 overlap: 0/5
- Candidate taxonomy: **MULTIPLE_DEBUGGING_CLUES_REMOVED**

### sympy__sympy-20322

- RAW file rank: 2
- RTK file rank: None
- RAW bytes: 1010
- RTK bytes: 175
- Reduction: 82.67%
- RAW traceback frames: 1
- RTK traceback frames: 0
- Removed source references: 2
- Removed assertion lines: 1
- Removed test names: 2
- RAW/RTK Top-5 overlap: 0/5
- Candidate taxonomy: **MULTIPLE_DEBUGGING_CLUES_REMOVED**

### sympy__sympy-24213

- RAW file rank: 4
- RTK file rank: None
- RAW bytes: 1255
- RTK bytes: 260
- Reduction: 79.28%
- RAW traceback frames: 2
- RTK traceback frames: 0
- Removed source references: 3
- Removed assertion lines: 0
- Removed test names: 2
- RAW/RTK Top-5 overlap: 2/5
- Candidate taxonomy: **MULTIPLE_DEBUGGING_CLUES_REMOVED**

