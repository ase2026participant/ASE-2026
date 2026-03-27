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
from typing import List


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
    args = parser.parse_args()

    base_path = Path(args.base_smt2)
    assertions_path = Path(args.assertions_file)
    out_dir = Path(args.output_dir)

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

    manifest_lines = ["index,file,assertion_preview"]

    for idx, block in enumerate(assert_blocks, start=1):
        out_file = out_dir / f"{args.prefix}{idx}.smt2"
        variant = insert_assertion(base_text, block)
        out_file.write_text(variant, encoding="utf-8")

        preview = " ".join(block.splitlines())[:120].replace(",", ";")
        manifest_lines.append(f"{idx},{out_file.name},{preview}")

    manifest_path = out_dir / "manifest.csv"
    manifest_path.write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")

    print(f"Generated {len(assert_blocks)} SMT2 variants in: {out_dir}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()

