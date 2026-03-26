#!/usr/bin/env python3
"""
Generate new RDA analysis output files without modifying existing ones.

This script runs RDA analysis with the nested block detection fix and creates
new output files with a suffix to preserve existing files.

Usage:
    python3 generate_new_output.py [c_file] [smt2_file]
    
Examples:
    # Generate new output for tcas_v11
    python3 generate_new_output.py Original/tcas_v11.c smt2_files/out.tcas_v11.smt2
    
    # Generate new output for all files
    python3 generate_new_output.py --all
"""

import sys
import os
from datetime import datetime

# Add project root to path
project_root = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from ssa_analyzer.ssa_analyzer.rda_ssa_generator import get_ssa_versions_for_file_rda
from ssa_analyzer.ssa_analyzer.formatters import format_cli_output
from ssa_analyzer.ssa_analyzer.smt2_verifier import verify_ssa_versions_for_file


def generate_output_file(c_file_path: str, smt2_file_path: str = None, 
                        output_suffix: str = "_nested_blocks") -> str:
    """
    Generate new output file for RDA analysis.
    
    Args:
        c_file_path: Path to C source file
        smt2_file_path: Optional path to SMT2 file for verification
        output_suffix: Suffix to add to output filename
        
    Returns:
        Path to generated output file
    """
    # Get base name for output file
    c_file_name = os.path.basename(c_file_path)
    base_name = os.path.splitext(c_file_name)[0]
    
    # Create results directory if it doesn't exist
    results_dir = os.path.join(os.path.dirname(__file__), 'results')
    os.makedirs(results_dir, exist_ok=True)
    
    # Generate output filename with suffix
    output_filename = f"analysis_{base_name}_rda{output_suffix}.txt"
    output_path = os.path.join(results_dir, output_filename)
    
    print(f"Processing: {c_file_path}")
    if smt2_file_path:
        print(f"  SMT2 file: {smt2_file_path}")
    print(f"  Output file: {output_path}")
    
    try:
        # Run RDA analysis
        if smt2_file_path and os.path.exists(smt2_file_path):
            # With SMT2 verification
            results = verify_ssa_versions_for_file(c_file_path, smt2_file_path, use_rda=True)
        else:
            # RDA only
            results = get_ssa_versions_for_file_rda(c_file_path)
        
        # Format output
        output = format_cli_output(results, 'text')
        
        # Add header with timestamp and note about nested blocks
        header = f"""
{'=' * 80}
RDA Analysis Output - Generated with Nested Block Detection Fix
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
File: {c_file_path}
{'=' * 80}

"""
        
        full_output = header + output
        
        # Write to file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(full_output)
        
        print(f"✓ Successfully generated: {output_path}")
        print(f"  Found {len(results)} function-variable pairs\n")
        
        return output_path
        
    except Exception as e:
        print(f"✗ Error processing {c_file_path}: {e}")
        import traceback
        traceback.print_exc()
        return None


def process_all_files():
    """Process all C files in Original directory."""
    project_root = os.path.dirname(os.path.dirname(__file__))
    original_dir = os.path.join(project_root, 'Original')
    smt2_dir = os.path.join(project_root, 'smt2_files')
    
    # Find all C files
    c_files = sorted([f for f in os.listdir(original_dir) if f.endswith('.c')])
    
    if not c_files:
        print(f"No C files found in {original_dir}")
        return
    
    print(f"Found {len(c_files)} C files to process\n")
    
    successful = 0
    failed = 0
    
    for c_file_name in c_files:
        c_file_path = os.path.join(original_dir, c_file_name)
        
        # Find corresponding SMT2 file
        base_name = os.path.splitext(c_file_name)[0]
        smt2_file = os.path.join(smt2_dir, f'out.{base_name}.smt2')
        
        if not os.path.exists(smt2_file):
            smt2_file = None
            print(f"Note: SMT2 file not found for {c_file_name}, running RDA only")
        
        result = generate_output_file(c_file_path, smt2_file)
        if result:
            successful += 1
        else:
            failed += 1
    
    print(f"\n{'=' * 80}")
    print(f"Summary: {successful} successful, {failed} failed")
    print(f"{'=' * 80}")


def main():
    """Main entry point."""
    if len(sys.argv) > 1 and sys.argv[1] == '--all':
        process_all_files()
    elif len(sys.argv) >= 2:
        c_file = sys.argv[1]
        smt2_file = sys.argv[2] if len(sys.argv) > 2 else None
        
        if not os.path.exists(c_file):
            print(f"Error: C file not found: {c_file}")
            sys.exit(1)
        
        generate_output_file(c_file, smt2_file)
    else:
        print(__doc__)
        print("\nUsage:")
        print("  python3 generate_new_output.py <c_file> [smt2_file]")
        print("  python3 generate_new_output.py --all")
        print("\nExamples:")
        print("  python3 generate_new_output.py Original/tcas_v11.c smt2_files/out.tcas_v11.smt2")
        print("  python3 generate_new_output.py --all")
        sys.exit(1)


if __name__ == '__main__':
    main()
