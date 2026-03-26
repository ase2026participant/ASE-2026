"""
Batch analysis script to process all C files and generate SSA variable analysis.

This script:
1. Analyzes C source code using get_ssa_versions_for_file()
2. Maps derived names to actual SSA variable names from SMT2 files
3. Generates analysis_second_phase.txt with SMT2 SSA variable names

This is different from the CLI tool (cli.py) which only analyzes C code
without SMT2 file mapping.

Usage:
    python3 ssa_analyzer/batch_analysis.py
"""

import os
import sys
import glob

# Add parent directory to path to allow imports
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from ssa_analyzer.ssa_analyzer.smt2_ssa_extractor import get_ssa_variables_for_assertions
from ssa_analyzer.ssa_analyzer.formatters import format_batch_output


def main():
    """Process all C files in Original directory."""
    # Get paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    original_dir = os.path.join(project_root, 'Original')
    smt2_dir = os.path.join(project_root, 'smt2_files')
    results_dir = os.path.join(script_dir, 'results')
    
    # Create results directory if it doesn't exist
    os.makedirs(results_dir, exist_ok=True)
    output_file = os.path.join(results_dir, 'analysis_second_phase.txt')
    
    # Find all C files
    c_files = sorted(glob.glob(os.path.join(original_dir, '*.c')))
    
    if not c_files:
        print(f"No C files found in {original_dir}")
        sys.exit(1)
    
    print(f"Found {len(c_files)} C files to process")
    print(f"Output will be written to: {output_file}")
    print()
    
    all_output = []
    
    for c_file_path in c_files:
        c_file_name = os.path.basename(c_file_path)
        print(f"Processing {c_file_name}...", end=' ', flush=True)
        
        # Find corresponding SMT2 file
        # Pattern: out.tcas_v10.smt2 for tcas_v10.c
        base_name = os.path.splitext(c_file_name)[0]
        smt2_file = os.path.join(smt2_dir, f'out.{base_name}.smt2')
        
        if not os.path.exists(smt2_file):
            print(f"SKIPPED (SMT2 file not found: {smt2_file})")
            continue
        
        try:
            # Get SSA variables for assertions
            ssa_results = get_ssa_variables_for_assertions(
                c_file_path, smt2_file, only_diff_variables=True
            )
            
            # Format output using batch formatter (maps to SMT2 SSA variables)
            file_output = format_batch_output(ssa_results, c_file_name)
            
            # Add file header
            all_output.append(f"\n{'=' * 80}")
            all_output.append(f"FILE: {c_file_name}")
            all_output.append(f"{'=' * 80}\n")
            all_output.append(file_output)
            
            print(f"DONE ({len(ssa_results['source'])} source, {len(ssa_results['mutant'])} mutant variables)")
            
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback
            all_output.append(f"\n{'=' * 80}")
            all_output.append(f"FILE: {c_file_name}")
            all_output.append(f"{'=' * 80}\n")
            all_output.append(f"ERROR processing {c_file_name}: {e}\n")
            all_output.append(traceback.format_exc())
            all_output.append("\n")
    
    # Write all results to file
    print(f"\nWriting results to {output_file}...")
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("\n".join(all_output))
    
    print(f"Done! Results written to {output_file}")


if __name__ == '__main__':
    main()

