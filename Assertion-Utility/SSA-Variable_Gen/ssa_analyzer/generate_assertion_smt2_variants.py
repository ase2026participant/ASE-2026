#!/usr/bin/env python3
"""
Generate one SMT2 file per assertion block.

This utility:
1) Reads a base SMT2 file (e.g., out.tcas_v15.smt2)
2) Extracts all `(assert ...)` blocks from an assertions source file
3) Creates one SMT2 copy per assertion
4) Inserts each assertion before the first `(check-sat)` in the base SMT2
   (or appends `(check-sat)` if missing)
5) Writes a manifest file with generated paths
"""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import re
from typing import List, Optional


def extract_assert_blocks(text: str) -> List[str]:
    """Extract balanced `(assert ...)` blocks from arbitrary text."""
    blocks: List[str] = []
    i = 0
    n = len(text)

    while i < n:
        start = text.find("(assert", i)
        if start == -1:
            break

        depth = 0
        j = start
        while j < n:
            ch = text[j]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    j += 1
                    break
            j += 1

        if j <= n:
            candidate = text[start:j].strip()
            if candidate.startswith("(assert") and candidate not in blocks:
                blocks.append(candidate)
        i = j

    return blocks


def insert_assertion(base_text: str, assertion_block: str) -> str:
    """Insert assertion before first check-sat; ensure check-sat exists."""
    marker = "(check-sat)"
    idx = base_text.find(marker)
    insertion = assertion_block.rstrip() + "\n\n"

    if idx != -1:
        return base_text[:idx] + insertion + base_text[idx:]

    text = base_text.rstrip() + "\n\n" + insertion + marker + "\n"
    return text


def infer_bug_count_from_analysis(analysis_text: str) -> int:
    """
    Infer bug count from SSA analyzer output.

    Current heuristic: count unique "Function:" headers in the analysis report.
    """
    funcs = re.findall(r"^Function:\s+(.+)$", analysis_text, flags=re.MULTILINE)
    unique = {f.strip() for f in funcs if f.strip()}
    return len(unique)


def choose_assertion_limit(
    assert_blocks: List[str],
    explicit_bug_count: Optional[int],
    analysis_file: Optional[Path],
) -> int:
    """Compute final number of assertions to generate."""
    if explicit_bug_count is not None:
        return max(1, min(explicit_bug_count, len(assert_blocks)))

    if analysis_file is not None:
        if not analysis_file.exists():
            raise FileNotFoundError(f"Analysis file not found: {analysis_file}")
        inferred = infer_bug_count_from_analysis(
            analysis_file.read_text(encoding="utf-8", errors="ignore")
        )
        if inferred > 0:
            return min(inferred, len(assert_blocks))

    return len(assert_blocks)


def classify_masking_from_solver_result(result: str) -> str:
    """
    Map solver result to masking interpretation.

    Convention used in this artifact:
    - unsat -> masked
    - sat -> unmasked
    - unknown/other -> inconclusive
    """
    r = result.strip().lower()
    if r == "unsat":
        return "masked"
    if r == "sat":
        return "unmasked"
    return "inconclusive"


def run_z3_and_write_status(out_dir: Path, prefix: str, count: int) -> Path:
    """Run Z3 for generated variants and write bug-level status CSV."""
    status_lines = ["bug_index,file,solver_result,masking_status"]

    for idx in range(1, count + 1):
        smt2_file = out_dir / f"{prefix}{idx}.smt2"
        result_file = out_dir / f"{prefix}{idx}.result.txt"

        proc = subprocess.run(
            ["z3", str(smt2_file)],
            text=True,
            capture_output=True,
            check=False,
        )

        output_text = (proc.stdout or "").strip()
        result_file.write_text(output_text + ("\n" if output_text else ""), encoding="utf-8")

        first_line = output_text.splitlines()[0].strip() if output_text else "no-result"
        if first_line not in {"sat", "unsat", "unknown"}:
            first_line = "unknown"

        masking_status = classify_masking_from_solver_result(first_line)
        status_lines.append(f"{idx},{smt2_file.name},{first_line},{masking_status}")

    status_path = out_dir / "bug_masking_status.csv"
    status_path.write_text("\n".join(status_lines) + "\n", encoding="utf-8")
    return status_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create one SMT2 file per assertion block."
    )
    parser.add_argument("--base-smt2", required=True, help="Path to base SMT2 file")
    parser.add_argument(
        "--assertions-file",
        required=True,
        help="Path to file containing assertion blocks",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory to write per-assertion SMT2 files",
    )
    parser.add_argument(
        "--prefix",
        default="out.tcas_v15.assert",
        help="Prefix for generated file names",
    )
    parser.add_argument(
        "--bug-count",
        type=int,
        default=None,
        help="Generate only this many assertions (typically number of bugs)",
    )
    parser.add_argument(
        "--analysis-file",
        default=None,
        help=(
            "SSA analysis output file to infer bug count automatically "
            "(e.g., analysis_tcas_v15_rda_smt2.txt)"
        ),
    )
    parser.add_argument(
        "--run-z3",
        action="store_true",
        help="Run Z3 on generated variants and emit bug_masking_status.csv",
    )
    args = parser.parse_args()

    base_path = Path(args.base_smt2)
    assertions_path = Path(args.assertions_file)
    out_dir = Path(args.output_dir)
    analysis_file = Path(args.analysis_file) if args.analysis_file else None

    if not base_path.exists():
        raise FileNotFoundError(f"Base SMT2 file not found: {base_path}")
    if not assertions_path.exists():
        raise FileNotFoundError(f"Assertions file not found: {assertions_path}")

    out_dir.mkdir(parents=True, exist_ok=True)

    base_text = base_path.read_text(encoding="utf-8", errors="ignore")
    assertions_text = assertions_path.read_text(encoding="utf-8", errors="ignore")
    assert_blocks = extract_assert_blocks(assertions_text)

    if not assert_blocks:
        raise ValueError(
            "No `(assert ...)` blocks found. "
            "Provide a file that contains SMT2 assertion blocks."
        )

    limit = choose_assertion_limit(assert_blocks, args.bug_count, analysis_file)
    selected_blocks = assert_blocks[:limit]

    manifest_lines = ["index,file,assertion_preview"]

    for idx, block in enumerate(selected_blocks, start=1):
        out_file = out_dir / f"{args.prefix}{idx}.smt2"
        variant = insert_assertion(base_text, block)
        out_file.write_text(variant, encoding="utf-8")

        preview = " ".join(block.splitlines())[:120].replace(",", ";")
        manifest_lines.append(f"{idx},{out_file.name},{preview}")

    manifest_path = out_dir / "manifest.csv"
    manifest_path.write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")

    print(f"Extracted assertion blocks: {len(assert_blocks)}")
    print(f"Generated assertion variants: {len(selected_blocks)}")
    print(f"Manifest: {manifest_path}")

    if args.run_z3:
        status_path = run_z3_and_write_status(out_dir, args.prefix, len(selected_blocks))
        print(f"Z3 status summary: {status_path}")


if __name__ == "__main__":
    main()

