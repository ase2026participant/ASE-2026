# ASE-2026 Workspace Guide

This README gives a single-place explanation of each top-level folder and the formal verification workflows used in this workspace.

## Artifact Purpose (ASE-2026)

This repository is the companion artifact for our ASE-2026 submission. It contains:

- code for CBMC/Z3-based verification experiments,
- utilities for SSA/assertion generation and SMT2 mapping,
- benchmark inputs (NTS and TCAS),
- traces, notebooks, and result files used for analysis.

The goal of this README is to help reviewers and readers quickly understand:
- where the code and data are located,
- how to set up the utility locally,
- how to reproduce representative verification runs.

## Code and Data at a Glance

- **Code**: `NTS/`, `TCAS/Driver_Programs/`, `Assertion-Utility/SSA-Variable_Gen/`
- **Data/Artifacts**: `TCAS/Traces/`, `TCAS/Driver_Programs/SMT_Files/`, `LLM Analysis/Results/`, `LLM Analysis/Notebook/`
- **Main reproducibility path**: Prerequisites -> deploy `SSA-Variable_Gen` -> run CBMC to generate SMT2 -> add/check assertions -> solve with Z3

## Prerequisites

Install and verify the following tools before running workflows in this repository:

- `python3` (recommended 3.9+)
- `pip` (for Python package installation)
- `cbmc` (for C bounded model checking and SMT2 generation)
- `z3` (for solving generated SMT2 constraints)
- POSIX shell environment (`bash`/`zsh`) on Linux/macOS

Quick checks:

```bash
python3 --version
pip --version
cbmc --version
z3 --version
```

If a command is not found, install that tool first and re-run the check.

## Folder Overview

- `NTS/`  
  Non-termination style benchmark driver programs and CBMC-ready C files for multiple subjects (`elevator`, `next_date1`, `problem_1`, `problem_2`, `problem_3`, etc.).

- `TCAS/`  
  TCAS benchmark artifacts for formal analysis.  
  - `Driver_Programs/Original/`: original TCAS driver program files (e.g., `tcas_v10.c`, `tcas_v11.c`, etc.).  
  - `Driver_Programs/SMT_Files/`: CBMC-generated SMT2 files and assertion examples (`TCAS_Multibug_Assertions.txt`).  
  - `Traces/`: execution/trace logs for TCAS variants.

- `Assertion-Utility/`  
  Assertion generation and SSA analysis utility project.  
  - `SSA-Variable_Gen/ssa_analyzer/`: core analyzer, RDA + SMT2 verification scripts, output formatters.  
  - `SSA-Variable_Gen/smt2_files/`: SMT2 files used for mapping/verification.  
  - `SSA-Variable_Gen/Original/`: source C files used by analyzer workflows.

- `LLM Analysis/`  
  Research and result organization area.  
  - `Notebook/`: notebooks for model/comparison analysis.  
  - `Results/`: generated CSVs and analysis outputs.

### Notebook Guide (2-3 lines each)

- `LLM Analysis/Notebook/GPT-4o_NTS_and_TCAS_analysis.ipynb`  
  End-to-end GPT-4o analysis notebook for NTS/TCAS benchmarks. It prepares source-mutant mappings, constructs prompts, and evaluates model responses for functional difference detection. It also tracks token usage and estimates API cost.

- `LLM Analysis/Notebook/LLM_OpenAI_GPT-5.2_bug_analysis.ipynb`  
  OpenAI GPT-5.2 focused bug-analysis workflow for source-vs-mutant C programs. It cleans code, applies structured prompts (including masking/interaction reasoning), and collects equivalence/non-equivalence decisions. The notebook is used to study model behavior on single and interacting bug scenarios.

- `LLM Analysis/Notebook/Mutliple_bug_analysis_LLM_GPT-4o.ipynb`  
  GPT-4o notebook dedicated to multiple-bug interaction analysis. It emphasizes whether one bug masks another, whether divergences propagate to outputs, and where behavioral differences remain observable. Outputs support comparative assessment against formal methods.

- `LLM Analysis/Notebook/gemini_deepseek_comparison.ipynb`  
  Comparative pipeline for Gemini and DeepSeek on source-mutant code pairs. It handles secure API configuration, batch execution, and tabular result collection in pandas. The notebook is used to compare model agreement, disagreement, and relative performance trends.

### CoT Prompt Usage in Notebooks

Some notebooks use a structured Chain-of-Thought (CoT) style prompt to improve semantic bug analysis beyond surface-level syntax differences. The prompt explicitly asks the model to reason about difference propagation, control-flow effects, output impact, and bug interaction/masking (including one-way and two-way masking).

The CoT workflow is used to classify source-mutant pairs as equivalent/non-equivalent (or conditionally divergent) with more transparent reasoning. In GPT-5.2 analysis notebooks, the response is constrained to a structured JSON schema so outputs can be parsed, compared, and aggregated consistently across experiments.

#### Summarized CoT System Prompt

- Role setup: model acts as an expert in program analysis and formal verification.
- Core objective: determine observational equivalence of source vs mutant for all feasible inputs.
- Required reasoning: identify semantic differences, trace forward propagation, and check masking at assignment, control-flow, and output levels.
- Multi-bug requirement: analyze interactions between bugs (amplification, cancellation, one-way masking, two-way masking) before final verdict.

#### Summarized CoT User Prompt

- Input payload: full source program and mutant program text.
- Step-by-step request: list differences, map affected variables/conditions, propagate effects, perform masking + path-sensitive analysis, and assess output divergence.
- Final decision request: classify as equivalent / non-equivalent / conditionally non-equivalent / masked divergence, with witness condition when available.
- Output format: strict structured response (JSON in GPT-5.2 notebook) for reproducible parsing and result aggregation.

---

## Deploy `SSA-Variable_Gen` on Local Setup

Run these once on a new machine:

### 1) Go to utility package directory

```bash
cd Assertion-Utility/SSA-Variable_Gen/ssa_analyzer
```

### 2) Create and activate Python virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3) Install the utility in editable mode

```bash
pip install -r requirements.txt
pip install -e .
```

Notes:
- `requirements.txt` contains minimal packaging dependency (`setuptools`).
- The analyzer runtime logic itself uses Python standard library modules.
- Editable install lets you update utility code without reinstalling each time.

### 4) Quick installation check

```bash
python3 -m ssa_analyzer.ssa_analyzer.cli --help
```

### 5) Smoke test (C + SMT2)

Run from `Assertion-Utility/SSA-Variable_Gen` (not from repo root):

```bash
cd Assertion-Utility/SSA-Variable_Gen
./ssa_analyzer/run_rda_smt2.sh Original/tcas_v15.c smt2_files/out.tcas_v15.smt2
```

If this command prints analysis output (or writes output when a file path is given), deployment is successful.

---

## Detailed Workflow: Identify Masking Bug from `tcas_v15.c`

This section gives a complete command-level flow to:
- generate SMT2 from `tcas_v15.c`,
- generate assertion candidates using the SSA utility,
- create one SMT2 copy per assertion,
- insert each assertion into the correct SMT2 location,
- run Z3 per assertion and record `sat`/`unsat`.

### Reviewer quick run (copy/paste)

If you are evaluating the artifact and want a direct runnable sequence:

```bash
cd "/path/to/ASE-2026"

# 1) Generate base SMT2
cbmc TCAS/Driver_Programs/Original/tcas_v15.c --smt2 --unwind 5 --outfile out.tcas_v15.smt2

# 2) Run SSA/assertion utility
cd Assertion-Utility/SSA-Variable_Gen
./ssa_analyzer/run_rda_smt2.sh Original/tcas_v15.c smt2_files/out.tcas_v15.smt2 ssa_analyzer/results/analysis_tcas_v15_rda_smt2.txt

# 3) Generate one SMT2 variant per assertion
cd "/path/to/ASE-2026"
python3 Assertion-Utility/SSA-Variable_Gen/ssa_analyzer/generate_assertion_smt2_variants.py \
  --base-smt2 out.tcas_v15.smt2 \
  --assertions-file TCAS/Driver_Programs/SMT_Files/TCAS_Multibug_Assertions.txt \
  --analysis-file Assertion-Utility/SSA-Variable_Gen/ssa_analyzer/results/analysis_tcas_v15_rda_smt2.txt \
  --output-dir tcas_v15_assertion_runs \
  --prefix out.tcas_v15.assert \
  --run-z3

# 4) View bug-wise masking status (generated automatically)
cd tcas_v15_assertion_runs
cat bug_masking_status.csv

# 5) Show masked/unmasked bug IDs quickly
echo "Masked bugs:"
awk -F, 'NR>1 && $4=="masked" {print "bug_"$1}' bug_masking_status.csv
echo "Unmasked bugs:"
awk -F, 'NR>1 && $4=="unmasked" {print "bug_"$1}' bug_masking_status.csv
```

Quick interpretation for reviewers:
- `sat`: assertion-specific divergence is feasible under current unwind/constraints (classified as `unmasked`).
- `unsat`: assertion-specific divergence is not feasible for that bug assertion (classified as `masked`).
- `unknown`: solver could not conclude; rerun with adjusted settings if needed.

### Step 1) Generate base SMT2 with CBMC

From repo root:

```bash
cd "/path/to/ASE-2026"
cbmc TCAS/Driver_Programs/Original/tcas_v15.c --smt2 --unwind 5 --outfile out.tcas_v15.smt2
```

This creates a baseline file: `out.tcas_v15.smt2`.
If you want to skip regeneration and use the shipped SMT2 artifact, use:
`TCAS/Driver_Programs/SMT_Files/out.tcas_v15.smt2` as `--base-smt2` in Step 3.

### Step 2) Run assertion generation utility (SSA + SMT2 mapping)

```bash
cd Assertion-Utility/SSA-Variable_Gen
./ssa_analyzer/run_rda_smt2.sh Original/tcas_v15.c smt2_files/out.tcas_v15.smt2 ssa_analyzer/results/analysis_tcas_v15_rda_smt2.txt
```

Use:
- `ssa_analyzer/results/analysis_tcas_v15_rda_smt2.txt` (generated predicate/SSA hints)
- `TCAS/Driver_Programs/SMT_Files/TCAS_Multibug_Assertions.txt` (assertion templates/examples)

### Step 3) Auto-generate one SMT2 copy per assertion

Use the helper script (added in this artifact) to:
- extract all `(assert ...)` blocks from an assertions source file,
- create one SMT2 variant per assertion,
- insert each assertion before `(check-sat)` automatically.

```bash
cd "/path/to/ASE-2026"
python3 Assertion-Utility/SSA-Variable_Gen/ssa_analyzer/generate_assertion_smt2_variants.py \
  --base-smt2 out.tcas_v15.smt2 \
  --assertions-file TCAS/Driver_Programs/SMT_Files/TCAS_Multibug_Assertions.txt \
  --analysis-file Assertion-Utility/SSA-Variable_Gen/ssa_analyzer/results/analysis_tcas_v15_rda_smt2.txt \
  --output-dir tcas_v15_assertion_runs \
  --prefix out.tcas_v15.assert
```

Notes:
- `--analysis-file` limits generated assertions to the inferred bug count from the utility report (for `tcas_v15`, this is typically 3).
- If you prefer manual control, use `--bug-count <N>` to force exactly `N` generated SMT2 variants.
- Add `--run-z3` to automatically execute Z3 and write `bug_masking_status.csv` with per-bug `masked/unmasked/inconclusive` status.

Generated outputs:
- `tcas_v15_assertion_runs/out.tcas_v15.assert1.smt2`
- `tcas_v15_assertion_runs/out.tcas_v15.assert2.smt2`
- ...
- `tcas_v15_assertion_runs/manifest.csv` (index -> file mapping + assertion preview)

`manifest.csv` is the reviewer-facing index for reproducibility:
- `index`: assertion sequence number used in generated file names,
- `file`: SMT2 variant file generated for that assertion,
- `assertion_preview`: first part of inserted assertion for quick mapping.

### Step 4) (Optional) Manual assertion file format

If you want full control, create your own assertions file containing pure SMT2 blocks:

```smt2
(assert (=> 
  (not (= |predicate_src_ssa| |predicate_mut_ssa|))
  (not (= |final_src_ssa| |final_mut_ssa|))
))

(assert (not (= |predicate_src_ssa| |predicate_mut_ssa|)))
```

Then pass that file as `--assertions-file`.

### Step 5) Ensure solver query lines

The script preserves existing `(check-sat)` and inserts assertions before it.
If your base SMT2 has no `(check-sat)`, the script appends one automatically.

Optional for model extraction in SAT cases, append to individual files:

```smt2
(get-model)
```

### Step 6) Run Z3 on each SMT2 copy

```bash
cd "/path/to/ASE-2026/tcas_v15_assertion_runs"
for f in out.tcas_v15.assert*.smt2; do
  echo "=== $f ==="
  z3 "$f" | tee "${f%.smt2}.result.txt"
done
```

Or run `--run-z3` in Step 3 to generate results automatically.

### Step 7) Summarize `sat`/`unsat` results

```bash
cd "/path/to/ASE-2026/tcas_v15_assertion_runs"
setopt nonomatch 2>/dev/null || true
shopt -s nullglob 2>/dev/null || true
for r in *.result.txt; do
  [ -e "$r" ] || continue
  printf "%s: " "$r"
  grep -E '^(sat|unsat|unknown)$' "$r" | head -n 1 || echo "no-result"
done
```

Interpretation:
- `sat`: assertion constraints are satisfiable (witness exists under current encoding/unwind).
- `unsat`: assertion constraints are inconsistent for that encoding/unwind.
- `unknown`: solver could not decide with current constraints/settings.

Optional CSV summary for paper tables:

```bash
cd "/path/to/ASE-2026/tcas_v15_assertion_runs"
setopt nonomatch 2>/dev/null || true
shopt -s nullglob 2>/dev/null || true
printf "file,result\n" > z3_summary.csv
for r in *.result.txt; do
  [ -e "$r" ] || continue
  res=$(grep -E '^(sat|unsat|unknown)$' "$r" | head -n 1)
  [ -z "$res" ] && res="no-result"
  printf "%s,%s\n" "$r" "$res" >> z3_summary.csv
done
```

Bug-wise masking table generated by script (`--run-z3`):

```bash
cd "/path/to/ASE-2026/tcas_v15_assertion_runs"
cat bug_masking_status.csv
```

### Troubleshooting notes (reviewers)

- If Step 3 says base SMT2 not found, confirm you generated `out.tcas_v15.smt2` in repo root (Step 1), or use the shipped file path in `TCAS/Driver_Programs/SMT_Files/`.
- If `cbmc`/`z3` commands are not found, install prerequisites from the `Prerequisites` section.
- If no assertion variants are generated, verify the assertions source file contains valid balanced `(assert ...)` blocks.
- If `bug_masking_status.csv` shows all `unknown`, run Z3 in SMT2 mode and capture stderr (some setups print parser/solver messages to stderr):

```bash
cd "/path/to/ASE-2026/tcas_v15_assertion_runs"
for f in out.tcas_v15.assert*.smt2; do
  z3 -smt2 "$f" > "${f%.smt2}.result.txt" 2>&1
done
```

Then rebuild bug-wise status from these result files:

```bash
cd "/path/to/ASE-2026/tcas_v15_assertion_runs"
printf "bug_index,file,solver_result,masking_status\n" > bug_masking_status.csv
i=1
for r in out.tcas_v15.assert*.result.txt; do
  [ -e "$r" ] || continue
  solver=$(grep -E '^(sat|unsat|unknown)$' "$r" | head -n 1)
  [ -z "$solver" ] && solver="unknown"

  if [ "$solver" = "unsat" ]; then
    status="masked"
  elif [ "$solver" = "sat" ]; then
    status="unmasked"
  else
    status="inconclusive"
  fi

  smt="${r%.result.txt}.smt2"
  printf "%s,%s,%s,%s\n" "$i" "$(basename "$smt")" "$solver" "$status" >> bug_masking_status.csv
  i=$((i+1))
done
```

---

## NTS: CBMC Verification Command (main/test_driver)

Use this template:

```bash
cbmc driver.c \
  --function main
```

or, if the entry point in the driver is `test_driver`:

```bash
cbmc driver.c \
  --function test_driver \
  --unwind <LOOP_COUNT> \
  --no-unwinding-assertions \
  --slice-formula \
  --reachability-slice
```

### Meaning of each option

- `--function main/test_driver`  
  Selects verification entry function. Use the exact function name present in the driver.

- `--unwind <LOOP_COUNT>`  
  Unrolls loops up to the specified bound. Increase this when loops need deeper exploration.

- `--no-unwinding-assertions`  
  Disables automatic assertions that fail when unwind bound is insufficient. Useful for bounded bug-hunting runs.

- `--slice-formula`  
  Simplifies the generated formula by removing irrelevant constraints.

- `--reachability-slice`  
  Keeps only constraints relevant to reachable assertions/targets, reducing SMT complexity.

Example (`program1_v2`):

```bash
cbmc NTS/NTS_driver_Program/problem_1/Problem1_v2_driver.c \
  --function main \
  --unwind 10 \
  --no-unwinding-assertions \
  --slice-formula \
  --reachability-slice
```

---

## TCAS Multibug Analysis with Assertion Utility

The utility can analyze a `.c` file and map SSA variables against a `.smt2` file.

### 1) Run assertion utility with C + SMT2

From `Assertion-Utility/SSA-Variable_Gen`:

```bash
./ssa_analyzer/run_rda_smt2.sh <path/to/file.c> <path/to/file.smt2> [output_file]
```

Example:

```bash
cd Assertion-Utility/SSA-Variable_Gen
./ssa_analyzer/run_rda_smt2.sh Original/tcas_v15.c smt2_files/out.tcas_v15.smt2 ssa_analyzer/results/analysis_tcas_v15_rda_smt2.txt
```

What this gives:
- RDA-compliant SSA extraction
- SSA variable verification against SMT2 symbols
- predicate pair data for assertion construction

### 2) Use generated assertions for multibug checks

- Start from templates in `TCAS/Driver_Programs/SMT_Files/TCAS_Multibug_Assertions.txt`.
- Match generated SSA names to symbols in your target SMT2 file.
- Add assertion blocks near the end of SMT2 constraints (before solver checks), for example:

```smt2
(assert (=> 
  (not (= |src_ssa| |mut_ssa|))
  (not (= |main_return_src| |main_return_mut|))
))
```

---

## Examine TCAS SMT2 for Masking Bug (SSA Generation + Z3)

### Step 1: Generate SMT2 from CBMC

```bash
cbmc tcas_v15.c --smt2 --unwind 5 --outfile out.tcas_v15.smt2
```

This exports CBMC SSA constraints to `out.tcas_v15.smt2`.

### Step 2: Inspect SSA symbols

Open `out.tcas_v15.smt2` and check for:
- differing source/mutant SSA symbols (often `_2` suffixed mutant names)
- return-value SSA symbols (`goto_symex::return_value::...`)
- assertion-relevant intermediate SSA variables from utility output

### Step 3: Add utility-generated assertion(s)

Insert the generated assertion block(s) into the SMT2 file you want to solve (for example `out.tcas_v15.smt2`).

Recommended pattern:

```smt2
(assert (=> 
  (not (= |predicate_src_ssa| |predicate_mut_ssa|))
  (not (= |final_src_ssa| |final_mut_ssa|))
))
```

Optional strengthening check:

```smt2
(assert (not (= |predicate_src_ssa| |predicate_mut_ssa|)))
```

### Step 4: Run solver on generated SSA

```bash
z3 out.tcas_v15.smt2
```

Interpretation:
- `sat`: there exists a model satisfying constraints + your assertion setup (potential masking/behavioral divergence witness).
- `unsat`: constraints plus your added assertion are inconsistent under current unwind/slicing setup.

---

## Practical End-to-End Command Set

```bash
# 1) Generate SMT2 from CBMC
cbmc tcas_v15.c --smt2 --unwind 5 --outfile out.tcas_v15.smt2

# 2) Run assertion utility using .c + .smt2 inputs
cd Assertion-Utility/SSA-Variable_Gen
./ssa_analyzer/run_rda_smt2.sh Original/tcas_v15.c smt2_files/out.tcas_v15.smt2 ssa_analyzer/results/analysis_tcas_v15_rda_smt2.txt

# 3) Copy/generated assertion clauses into your target SMT2 (e.g., out.tcas_v15.smt2), then solve
z3 out.tcas_v15.smt2
```

If needed, increase `--unwind` and rerun both CBMC and solver for deeper path coverage.

---

## Two Concrete Examples

### 1) TCAS Masking Example (`tcas_v15`)

Goal: check whether internal source-mutant SSA differences are masked before final observable output divergence.

```bash
# Generate SMT2 for V15
cbmc TCAS/Driver_Programs/Original/tcas_v15.c --smt2 --unwind 5 --outfile out.tcas_v15.smt2

# (Optional but recommended) get SSA/predicate hints from assertion utility
cd Assertion-Utility/SSA-Variable_Gen
./ssa_analyzer/run_rda_smt2.sh Original/tcas_v15.c smt2_files/out.tcas_v15.smt2 ssa_analyzer/results/analysis_tcas_v15_rda_smt2.txt

# Solve after adding assertion block(s) to out.tcas_v15.smt2
z3 out.tcas_v15.smt2
```

How to read result:
- `sat` suggests a feasible witness exists for the current constraints/assertions (potential non-masked divergence).
- `unsat` suggests the asserted divergence condition is not satisfiable under current unwind/assertion setup (possible masking or over-constraint).

### 2) NTS Simple Case (`Problem1_v2`)

Goal: run a straightforward bounded check on one NTS driver with slicing enabled.

```bash
cbmc NTS/NTS_driver_Program/problem_1/Problem1_v2_driver.c \
  --function main \
  --unwind 10 \
  --no-unwinding-assertions \
  --slice-formula \
  --reachability-slice
```

# ASE-2026
