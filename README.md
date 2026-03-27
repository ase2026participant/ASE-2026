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

```bash
cd Assertion-Utility/SSA-Variable_Gen
./ssa_analyzer/run_rda_smt2.sh Original/tcas_v15.c smt2_files/out.tcas_v15.smt2 ssa_analyzer/results/analysis_tcas_v15_rda_smt2.txt
```

## Example Execution: Per-Bug Masking Classification

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

View bug-wise masking output:

```bash
cat tcas_v15_assertion_runs/bug_masking_status.csv
```
