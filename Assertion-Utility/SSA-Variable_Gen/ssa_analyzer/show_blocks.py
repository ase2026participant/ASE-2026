#!/usr/bin/env python3
"""
Standalone script to display control-flow blocks in a C function.

Usage:
    python3 show_blocks.py <c_file_path> <function_name> [variable_name]
    
Examples:
    # Show all blocks in a function
    python3 show_blocks.py Original/tcas_v11.c Alt_Sep_Test
    
    # Show blocks with assignments for a specific variable
    python3 show_blocks.py Original/tcas_v11.c Alt_Sep_Test Own_Tracked_Alt
"""

import sys
import os

# Add project root to path (one level up from ssa_analyzer/)
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from ssa_analyzer.ssa_analyzer.rda_ssa_generator import display_blocks_in_function
from ssa_analyzer.ssa_analyzer.parser import read_c_source, build_function_map
from ssa_analyzer.ssa_analyzer.rda_ssa_generator import extract_assignments_for_variable_rda


def list_functions(c_file_path: str) -> None:
    """List all functions found in the C file."""
    try:
        source_lines = read_c_source(c_file_path)
        func_map = build_function_map(source_lines)
        
        print("=" * 80)
        print(f"Functions found in {c_file_path}:")
        print("=" * 80)
        for idx, func_name in enumerate(sorted(func_map.keys()), 1):
            func_lines = func_map[func_name]
            line_count = len(func_lines)
            print(f"  [{idx}] {func_name} ({line_count} lines)")
        print("=" * 80)
    except Exception as e:
        print(f"Error reading file: {e}")
        sys.exit(1)


def show_blocks(c_file_path: str, func_name: str, var_name: str = None) -> None:
    """Display blocks for a specific function."""
    try:
        source_lines = read_c_source(c_file_path)
        func_map = build_function_map(source_lines)
        
        if func_name not in func_map:
            print(f"Error: Function '{func_name}' not found in {c_file_path}")
            print("\nAvailable functions:")
            list_functions(c_file_path)
            sys.exit(1)
        
        func_lines = func_map[func_name]
        assignments = None
        
        if var_name:
            assignments = extract_assignments_for_variable_rda(func_lines, func_name, var_name)
            print(f"\nShowing blocks for function '{func_name}' with variable '{var_name}':")
        else:
            print(f"\nShowing blocks for function '{func_name}':")
        
        output = display_blocks_in_function(func_lines, func_name, assignments)
        print(output)
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def main():
    """Main entry point."""
    if len(sys.argv) < 3:
        print(__doc__)
        print("\nUsage:")
        print("  python3 show_blocks.py <c_file_path> <function_name> [variable_name]")
        print("  python3 show_blocks.py <c_file_path> --list")
        print("\nExamples:")
        print("  python3 show_blocks.py Original/tcas_v11.c Alt_Sep_Test")
        print("  python3 show_blocks.py Original/tcas_v11.c Alt_Sep_Test Own_Tracked_Alt")
        print("  python3 show_blocks.py Original/tcas_v11.c --list")
        sys.exit(1)
    
    c_file_path = sys.argv[1]
    
    # Check if file exists
    if not os.path.exists(c_file_path):
        print(f"Error: File '{c_file_path}' not found.")
        sys.exit(1)
    
    # Handle --list option
    if sys.argv[2] == '--list':
        list_functions(c_file_path)
        sys.exit(0)
    
    func_name = sys.argv[2]
    var_name = sys.argv[3] if len(sys.argv) > 3 else None
    
    show_blocks(c_file_path, func_name, var_name)


if __name__ == '__main__':
    main()
