"""
RDA-Compliant Command-line interface for SSA Analyzer.

This CLI tool implements traditional Reaching Definition Analysis (RDA):
- Backward slicing from outputs
- Def-use chain construction
- Variable resolution in RHS expressions
- Dead code elimination

Usage:
    python3 -m ssa_analyzer.ssa_analyzer.cli_rda Original/tcas_v10.c -o results/analysis_v10_rda.txt
"""

from .cli_common import create_cli_parser, run_cli_analysis
from .rda_ssa_generator import get_ssa_versions_for_file_rda


def main():
    """Main CLI entry point for RDA-compliant analysis."""
    parser = create_cli_parser(
        'RDA-Compliant SSA Analyzer: Analyze SSA versions using Reaching Definition Analysis'
    )
    args = parser.parse_args()
    run_cli_analysis(get_ssa_versions_for_file_rda, args)


if __name__ == '__main__':
    main()

