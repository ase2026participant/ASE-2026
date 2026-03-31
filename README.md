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

### Get the artifact code
Option 1 (recommended):
```bash
git clone https://github.com/ase2026participant/ASE-2026.git
cd ASE-2026
```

Option 2:
- Download ZIP from the GitHub repository page and extract it locally.
- Open a terminal in the extracted `ASE-2026` folder before running commands below.

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

## 1. Single-bug Localization (NTS)

### Steps
1. Pick one NTS driver program from `NTS/NTS_driver_Program/`.
2. Run CBMC on the product driver with bounded unwind and slicing flags.
3. Inspect assertion results to identify whether source/mutant localization condition is satisfied.

### One example execution using NTS
```bash
cbmc NTS/NTS_driver_Program/problem_1/Problem1_v2_driver.c \
  --function main \
  --unwind 10 \
  --no-unwinding-assertions \
  --slice-formula \
  --reachability-slice
```

## 2. Multiple-bug Localization (TCAS)

Important scope note:
- The assertion utility workflow in this artifact is intended for **multi-bug mutants in TCAS only**.
- It is not intended as a generic workflow for NTS benchmarks or single-bug mutant pipelines.

### 2.a) Steps
1. Generate SMT2 from TCAS source (`tcas_v15.c`).
2. Run SSA/analysis utility to produce analysis output for assertion selection.
3. Generate one assertion-specific SMT2 per bug and solve each using Z3.
4. Collect per-bug masking/localization result from `bug_masking_status.csv`.

### 2.b) One example execution using TCAS
```bash
cbmc TCAS/Driver_Programs/Original/tcas_v15.c --smt2 --unwind 5 --outfile out.tcas_v15.smt2
```

The CBMC command above generates the bounded SMT2 model for TCAS v15, which is the input for downstream SSA/RDA and per-assertion analysis.
The next utility command produces `analysis_tcas_v15_rda_smt2.txt`, used to map assertions to bug-relevant syntactic changes.

```bash
cd Assertion-Utility/SSA-Variable_Gen
./ssa_analyzer/run_rda_smt2.sh Original/tcas_v15.c smt2_files/out.tcas_v15.smt2 ssa_analyzer/results/analysis_tcas_v15_rda_smt2.txt
```

The `generate_assertion_smt2_variants.py` command below is associated with analysis of all syntactic changes corresponding to the respective multi-bug mutant.
It generates assertion-specific SMT2 variants so each syntactic change/bug condition can be checked independently and then summarized jointly.
The resulting per-assertion Z3 outcomes provide bug-wise masking/localization evidence for the full multi-bug mutant.

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

### 2.c) Running all the test cases
Use the same pipeline for all available TCAS multi-bug cases by repeating the steps above per target driver/SMT2 pair.
For each run, verify the generated outputs and aggregate bug status:

- `tcas_v15_assertion_runs/manifest.csv`
- `tcas_v15_assertion_runs/bug_masking_status.csv`

Quick checks:
```bash
cat tcas_v15_assertion_runs/bug_masking_status.csv
grep ",masked," tcas_v15_assertion_runs/bug_masking_status.csv
grep ",unmasked," tcas_v15_assertion_runs/bug_masking_status.csv
```

Result interpretation (`bug_masking_status.csv`):
- `solver_result = sat` -> `masking_status = unmasked`
- `solver_result = unsat` -> `masking_status = masked`
- `solver_result = unknown` or `error` -> `masking_status = inconclusive`

## 3. CoT Prompts (Used in LLM Notebooks)

The primary prompt used for reported paper results is the main prompt described in the paper.
The CoT prompting setup below is an additional, optional analysis layer provided for deeper behavioral diagnosis.
It is intended as a good-to-have extension for qualitative reasoning about masking and bug interactions.

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

### Prompt Template (JSON-first masking analysis)

Use this stricter prompt pair when you want machine-parseable output and explicit masking/interaction reasoning for multi-bug comparisons.

System Prompt:

```text
You are an expert in program analysis and formal verification.

Your task is to determine semantic (observational) equivalence between a source program and a mutant program.
You must reason about program behavior, not just syntax.

Definition:
Two programs are observationally equivalent if, for every feasible input, their observable outputs are identical.

Critical requirements:
- Do NOT conclude non-equivalence based only on syntactic differences.
- You MUST analyze how differences propagate through the program.
- You MUST check whether differences are masked before reaching the output.
- You MUST consider interaction between multiple bugs.

You must explicitly reason about the following masking effects:
1. Overwrite masking (later assignments remove divergence)
2. Control-flow masking (divergent code not executed)
3. Output masking (internal difference does not affect output)
4. Interaction masking (one bug cancels or neutralizes another)
5. Path-specific masking (difference appears only on some paths)

For each identified difference:
- Identify affected variables or predicates
- Trace forward propagation
- Determine whether divergence survives or is masked

For multi-bug mutants:
- Analyze combined effects, not just each bug independently
- Check if bugs amplify, cancel, or hide each other

Do NOT skip propagation analysis.

Final decision rules:
- Equivalent -> no feasible input causes output difference
- Non-equivalent -> at least one feasible input causes output difference
- Conditionally non-equivalent -> only some paths diverge
- Masked divergence -> internal differences exist but do not reach output

Be precise, structured, and conservative in conclusions.
If uncertain, explicitly state limitations.
```

User Prompt:

```text
Task:
Compare the following source program (S) and mutant program (M) for observational equivalence.

Follow the required reasoning steps carefully.

Steps to perform:
1. Identify all semantic differences between S and M.
2. For each difference:
 - List directly affected variables or conditions
 - Describe immediate effect
3. Trace forward propagation:
 - How does this difference influence later computations?
 - Does it affect control flow?
 - Does it reach output variables?
4. Perform masking analysis:
 - Is the difference overwritten later?
 - Is it blocked by path conditions?
 - Is it masked at output?
5. Perform interaction analysis:
 - Do multiple differences interact?
 - Does one difference cancel or amplify another?
 - Check explicitly for one-way masking (one bug/change masks or hides the effect of another).
 - Check explicitly for two-way masking (two or more bugs/changes cancel each other so that combined behavior appears correct).
 - IMPORTANT: If any such masking occurs, you MUST say so explicitly, and identify which bugs/changes are involved.
6. Perform path-sensitive reasoning if needed.
7. Determine whether any feasible input leads to different outputs.

Output requirements (STRICT):
- Return ONLY valid JSON. No markdown, no code fences, no extra text.
- The JSON must include an upfront answer that starts with Yes/No and a one-line justification.
- That Yes/No and one-liner MUST explicitly state whether any bug/change is masked by another bug/change.
- The JSON must use these exact top-level keys:
  answer, one_liner, A_observable_output_variables, B_differences_identified,
  C_propagation_analysis, D_masking_analysis, E_interaction_analysis,
  F_surviving_divergences_reaching_output, G_final_verdict,
  H_witness_input_or_condition, I_confidence_and_limitations.

Meaning of keys:
- answer: Yes/No to "Are S and M observationally equivalent?"
- one_liner: one sentence, starting with Yes/No, explicitly mentioning masking presence/absence between bugs.
- A_observable_output_variables: list of observable output variables.
- B_differences_identified: list of semantic differences with id, description, directly_affected, immediate_effect.
- C_propagation_analysis: mapping from difference id to propagation details.
- D_masking_analysis: overwrite/control_flow/output/interaction/path_specific masking.
- E_interaction_analysis: summary of interactions between differences.
- F_surviving_divergences_reaching_output: differences that still reach outputs.
- G_final_verdict: one of Equivalent, Non-equivalent, Conditionally non-equivalent, Masked divergence.
- H_witness_input_or_condition: concrete or symbolic witness for non-equivalence.
- I_confidence_and_limitations: object with numeric confidence and textual limitations.

---

Source Program (S):
{source}

---

Mutant Program (M):
{mutant}
```

Usage note:
- In notebooks, inject program text using Python f-strings exactly as `{source}` and `{mutant}` placeholders.
- Keep temperature low (`0` to `0.2`) to improve consistency of strict JSON output.

