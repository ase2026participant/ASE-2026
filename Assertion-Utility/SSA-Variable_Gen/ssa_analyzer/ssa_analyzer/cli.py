"""
Command-line interface for SSA Analyzer.

This CLI tool analyzes C source code directly without requiring SMT2 files.
It uses get_ssa_versions_for_file() which analyzes the C code structure.

Usage:
    python3 -m ssa_analyzer.ssa_analyzer.cli Original/tcas_v10.c -o results/analysis_v10.txt
"""

from .cli_common import create_cli_parser, run_cli_analysis
from . import get_ssa_versions_for_file


def main():
    """Main CLI entry point."""
    parser = create_cli_parser(
        'Analyze SSA versions of important variables in C source code'
    )
    args = parser.parse_args()
    run_cli_analysis(get_ssa_versions_for_file, args)


if __name__ == '__main__':
    main()

