# ASE-2026 Quick Guide

This file is a lightweight guide for reviewers/users.
For full documentation, see `DETAILED_READ_ME`.

## Resource Locations

- NTS driver programs: `NTS/NTS_driver_Program/`
- TCAS drivers: `TCAS/Driver_Programs/Original/`
- TCAS SMT2 files: `TCAS/Driver_Programs/SMT_Files/`
- Assertion utility project: `Assertion-Utility/SSA-Variable_Gen/`
- SSA analyzer package: `Assertion-Utility/SSA-Variable_Gen/ssa_analyzer/`
- LLM notebooks: `LLM Analysis/Notebook/`
- LLM result CSV files: `LLM Analysis/Results/`

## Prerequisites

### Languages and runtime
- Python: `3.9+` (recommended)
- Shell: `bash` or `zsh` (commands are shell-based)

### Required tools
- `cbmc` (for C to SMT2 generation and bounded model checking)
- `z3` (for SMT solving and sat/unsat classification)

Quick checks:

```bash
python3 --version
cbmc --version
z3 --version
```

### Python libraries (for SSA utility)
From `Assertion-Utility/SSA-Variable_Gen/ssa_analyzer`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

## CoT Prompts (Used in LLM Notebooks)

The notebooks in `LLM Analysis/Notebook/` use Chain-of-Thought (CoT) style prompting for semantic equivalence and masking-bug reasoning.

### CoT System Prompt (summary)

- Role: expert in program analysis and formal verification.
- Goal: determine observational equivalence between source and mutant code.
- Required reasoning: difference detection, propagation tracking, masking checks (overwrite/control-flow/output), and multi-bug interaction analysis.
- Decision labels: equivalent / non-equivalent / conditionally non-equivalent / masked divergence.

Template:

```text
You are an expert in program analysis and formal verification.
Determine observational equivalence between source and mutant programs.
Reason about semantic effects, propagation, masking, and bug interactions.
Return a conservative final verdict based on feasible input behavior.
```

### CoT User Prompt (summary)

- Input: full source program and mutant program text.
- Steps requested: identify semantic differences, trace propagation, analyze masking and interaction effects, and determine whether outputs diverge.
- Output format: strict structured output (JSON in GPT-5.2 notebook workflow) for reproducible parsing.

Template:

```text
Task:
Compare source and mutant programs for observational equivalence.
1) Identify semantic differences.
2) Trace propagation to outputs.
3) Analyze masking and multi-bug interactions.
4) Provide final verdict and witness condition (if any).
Return structured output only.
```

## Example Execution: NTS

```bash
cbmc NTS/NTS_driver_Program/problem_1/Problem1_v2_driver.c \
  --function main \
  --unwind 10 \
  --no-unwinding-assertions \
  --slice-formula \
  --reachability-slice
```

## Example Execution: TCAS v15 (SMT2 generation)

```bash
cbmc TCAS/Driver_Programs/Original/tcas_v15.c --smt2 --unwind 5 --outfile out.tcas_v15.smt2
```

## Example Execution: Assertion Generation Utility

Important scope note:
- The assertion utility workflow in this artifact is intended for **multi-bug mutants in TCAS only**.
- It is not intended as a generic workflow for NTS benchmarks or single-bug mutant pipelines.

```bash
cd Assertion-Utility/SSA-Variable_Gen
./ssa_analyzer/run_rda_smt2.sh Original/tcas_v15.c smt2_files/out.tcas_v15.smt2 ssa_analyzer/results/analysis_tcas_v15_rda_smt2.txt
```

## Example Execution: Per-Bug Masking Classification

This workflow does the following automatically:
1. Reads a base SMT2 model for `tcas_v15`.
2. Reads candidate `(assert ...)` blocks from `TCAS_Multibug_Assertions.txt`.
3. Uses analysis output (`analysis_tcas_v15_rda_smt2.txt`) to infer bug count.
4. Generates one SMT2 variant per bug (instead of all assertion blocks).
5. Runs Z3 on each generated variant and writes a per-bug masking status table.

```bash
cd "/path/to/ASE-2026"
python3 Assertion-Utility/SSA-Variable_Gen/ssa_analyzer/generate_assertion_smt2_variants.py \
  --base-smt2 out.tcas_v15.smt2 \
  --assertions-file TCAS/Driver_Programs/SMT_Files/TCAS_Multibug_Assertions.txt \
  --analysis-file Assertion-Utility/SSA-Variable_Gen/ssa_analyzer/results/analysis_tcas_v15_rda_smt2.txt \
  --output-dir tcas_v15_assertion_runs \
  --prefix out.tcas_v15.assert \
  --run-z3
```

Expected generated files in `tcas_v15_assertion_runs/`:
- `out.tcas_v15.assert1.smt2`, `out.tcas_v15.assert2.smt2`, ...
- `out.tcas_v15.assert1.result.txt`, `out.tcas_v15.assert2.result.txt`, ...
- `manifest.csv` (generated assertion index/file mapping)
- `bug_masking_status.csv` (final per-bug classification)

View bug-wise masking output:

```bash
cat tcas_v15_assertion_runs/bug_masking_status.csv
```

Result interpretation (`bug_masking_status.csv`):
- `solver_result = sat` -> `masking_status = unmasked`
- `solver_result = unsat` -> `masking_status = masked`
- `solver_result = unknown` or `error` -> `masking_status = inconclusive`

Quick filter examples:

```bash
# Show masked bug rows only
grep ",masked," tcas_v15_assertion_runs/bug_masking_status.csv

# Show unmasked bug rows only
grep ",unmasked," tcas_v15_assertion_runs/bug_masking_status.csv
```
