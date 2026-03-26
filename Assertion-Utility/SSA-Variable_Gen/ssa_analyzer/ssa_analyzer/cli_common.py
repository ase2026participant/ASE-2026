"""
Common CLI functionality shared between standard and RDA CLI tools.
"""

import argparse
import sys
from typing import Dict, Tuple, Callable


def create_cli_parser(description: str) -> argparse.ArgumentParser:
    """Create a common argument parser for CLI tools."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        'file_path',
        help='Path to the C source file'
    )
    parser.add_argument(
        '--filter-version-2',
        action='store_true',
        help='Filter results to show only version 2 (first assignment)'
    )
    parser.add_argument(
        '--format',
        choices=['text', 'json'],
        default='text',
        help='Output format (default: text)'
    )
    parser.add_argument(
        '--output',
        '-o',
        help='Output file (default: stdout)'
    )
    return parser


def run_cli_analysis(
    analysis_func: Callable[[str, bool], Dict[Tuple[str, str], Dict]],
    args: argparse.Namespace
) -> None:
    """
    Common CLI execution logic.
    
    Args:
        analysis_func: Function that performs the analysis (standard or RDA)
        args: Parsed command-line arguments
    """
    try:
        # Get SSA versions using the provided analysis function
        ssa_results = analysis_func(
            args.file_path,
            filter_to_version_2=args.filter_version_2
        )
        
        # Format output using CLI formatter
        from .formatters import format_cli_output
        output = format_cli_output(ssa_results, args.format)
        
        # Write output
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(output)
        else:
            print(output)
        
        sys.exit(0)
    
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

