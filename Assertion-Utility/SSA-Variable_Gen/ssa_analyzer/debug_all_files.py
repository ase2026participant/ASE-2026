#!/usr/bin/env python3
"""
Debug and analyze all C files in the Original directory.

This script runs comprehensive analysis on all files and generates a detailed
debug document with findings, issues, and statistics.

Usage:
    python3 debug_all_files.py [output_file]
    
Examples:
    python3 debug_all_files.py
    python3 debug_all_files.py debug_report.txt
"""

import sys
import os
from datetime import datetime
from typing import Dict, List, Tuple

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from ssa_analyzer.ssa_analyzer.rda_ssa_generator import (
    get_ssa_versions_for_file_rda,
    display_blocks_in_function
)
from ssa_analyzer.ssa_analyzer.parser import read_c_source, build_function_map
from ssa_analyzer.ssa_analyzer.ssa_generator import get_unique_function_variable_pairs


def analyze_function_blocks(func_lines: List[str], func_name: str) -> Dict:
    """Analyze blocks in a function."""
    try:
        output = display_blocks_in_function(func_lines, func_name)
        lines = output.split('\n')
        
        # Extract block information
        blocks = {}
        current_block = None
        
        for line in lines:
            if line.startswith('Block:'):
                current_block = line.split('Block:')[1].strip()
                blocks[current_block] = {'lines': [], 'condition': None}
            elif line.startswith('  Condition:'):
                if current_block:
                    blocks[current_block]['condition'] = line.split('Condition:')[1].strip()
            elif line.strip().startswith('[') and current_block:
                blocks[current_block]['lines'].append(line.strip())
        
        return {
            'block_count': len(blocks),
            'blocks': blocks,
            'display_output': output
        }
    except Exception as e:
        return {'error': str(e)}


def analyze_file(c_file_path: str) -> Dict:
    """Analyze a single C file comprehensively."""
    results = {
        'file_path': c_file_path,
        'file_name': os.path.basename(c_file_path),
        'timestamp': datetime.now().isoformat(),
        'errors': [],
        'warnings': [],
        'statistics': {},
        'functions': {},
        'ssa_analysis': {}
    }
    
    try:
        # Read source
        source_lines = read_c_source(c_file_path)
        func_map = build_function_map(source_lines)
        
        results['statistics']['total_lines'] = len(source_lines)
        results['statistics']['function_count'] = len(func_map)
        results['statistics']['function_names'] = list(func_map.keys())
        
        # Analyze each function
        for func_name, func_lines in func_map.items():
            func_info = {
                'line_count': len(func_lines),
                'blocks': analyze_function_blocks(func_lines, func_name),
                'has_nested_blocks': False
            }
            
            # Check for nested blocks
            if func_info['blocks'].get('block_count', 0) > 0:
                block_names = list(func_info['blocks'].get('blocks', {}).keys())
                nested_blocks = [b for b in block_names if 'nested' in b.lower()]
                func_info['has_nested_blocks'] = len(nested_blocks) > 0
                func_info['nested_block_count'] = len(nested_blocks)
            
            results['functions'][func_name] = func_info
        
        # Run RDA SSA analysis
        try:
            ssa_results = get_ssa_versions_for_file_rda(c_file_path)
            results['ssa_analysis'] = {
                'pair_count': len(ssa_results),
                'pairs': {}
            }
            
            for (func_name, var_name), data in ssa_results.items():
                pair_key = f"{func_name}.{var_name}"
                results['ssa_analysis']['pairs'][pair_key] = {
                    'source_ssa_count': len(data.get('source_ssa', [])),
                    'mutant_ssa_count': len(data.get('mutant_ssa', [])),
                    'condition_pairs_count': len(data.get('condition_predicate_pairs', [])),
                    'mutant_function': data.get('mutant_function', 'N/A')
                }
        except Exception as e:
            results['errors'].append(f"SSA Analysis failed: {str(e)}")
            results['ssa_analysis']['error'] = str(e)
        
        # Get function-variable pairs
        try:
            pairs = get_unique_function_variable_pairs(c_file_path)
            results['statistics']['pair_count'] = len(pairs)
            results['statistics']['pairs'] = pairs
        except Exception as e:
            results['warnings'].append(f"Could not get pairs: {str(e)}")
        
    except Exception as e:
        results['errors'].append(f"File analysis failed: {str(e)}")
        import traceback
        results['traceback'] = traceback.format_exc()
    
    return results


def generate_debug_document(all_results: List[Dict], output_file: str = None) -> str:
    """Generate comprehensive debug document."""
    lines = []
    
    # Header
    lines.append("=" * 100)
    lines.append("COMPREHENSIVE DEBUG REPORT - ALL ORIGINAL FILES")
    lines.append("=" * 100)
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Total files analyzed: {len(all_results)}")
    lines.append("")
    
    # Summary statistics
    lines.append("=" * 100)
    lines.append("SUMMARY STATISTICS")
    lines.append("=" * 100)
    
    total_functions = sum(len(r.get('statistics', {}).get('function_names', [])) for r in all_results)
    total_pairs = sum(r.get('statistics', {}).get('pair_count', 0) for r in all_results)
    total_errors = sum(len(r.get('errors', [])) for r in all_results)
    total_warnings = sum(len(r.get('warnings', [])) for r in all_results)
    
    lines.append(f"Total functions found: {total_functions}")
    lines.append(f"Total function-variable pairs: {total_pairs}")
    lines.append(f"Total errors: {total_errors}")
    lines.append(f"Total warnings: {total_warnings}")
    lines.append("")
    
    # Per-file analysis
    for result in all_results:
        lines.append("=" * 100)
        lines.append(f"FILE: {result['file_name']}")
        lines.append("=" * 100)
        lines.append(f"Path: {result['file_path']}")
        lines.append(f"Analyzed: {result['timestamp']}")
        lines.append("")
        
        # Statistics
        stats = result.get('statistics', {})
        lines.append("Statistics:")
        lines.append(f"  Total lines: {stats.get('total_lines', 'N/A')}")
        lines.append(f"  Functions: {stats.get('function_count', 'N/A')}")
        lines.append(f"  Function-variable pairs: {stats.get('pair_count', 'N/A')}")
        lines.append("")
        
        # Functions
        if result.get('functions'):
            lines.append("Functions Analysis:")
            for func_name, func_info in result['functions'].items():
                lines.append(f"  {func_name}:")
                lines.append(f"    Lines: {func_info.get('line_count', 'N/A')}")
                
                blocks_info = func_info.get('blocks', {})
                if 'error' in blocks_info:
                    lines.append(f"    Block analysis error: {blocks_info['error']}")
                else:
                    lines.append(f"    Blocks: {blocks_info.get('block_count', 0)}")
                    if func_info.get('has_nested_blocks'):
                        lines.append(f"    Has nested blocks: Yes ({func_info.get('nested_block_count', 0)} nested)")
                    
                    # List block types
                    block_names = list(blocks_info.get('blocks', {}).keys())
                    if block_names:
                        lines.append(f"    Block types: {', '.join(block_names[:5])}")
                        if len(block_names) > 5:
                            lines.append(f"      ... and {len(block_names) - 5} more")
            lines.append("")
        
        # SSA Analysis
        ssa_analysis = result.get('ssa_analysis', {})
        if ssa_analysis:
            lines.append("SSA Analysis:")
            lines.append(f"  Pairs analyzed: {ssa_analysis.get('pair_count', 0)}")
            
            if 'error' in ssa_analysis:
                lines.append(f"  Error: {ssa_analysis['error']}")
            else:
                pairs_info = ssa_analysis.get('pairs', {})
                if pairs_info:
                    lines.append("  Pair details:")
                    for pair_key, pair_data in list(pairs_info.items())[:10]:  # Show first 10
                        lines.append(f"    {pair_key}:")
                        lines.append(f"      Source SSA: {pair_data.get('source_ssa_count', 0)}")
                        lines.append(f"      Mutant SSA: {pair_data.get('mutant_ssa_count', 0)}")
                        lines.append(f"      Condition pairs: {pair_data.get('condition_pairs_count', 0)}")
                        lines.append(f"      Mutant function: {pair_data.get('mutant_function', 'N/A')}")
                    if len(pairs_info) > 10:
                        lines.append(f"    ... and {len(pairs_info) - 10} more pairs")
            lines.append("")
        
        # Errors and warnings
        if result.get('errors'):
            lines.append("Errors:")
            for error in result['errors']:
                lines.append(f"  ✗ {error}")
            lines.append("")
        
        if result.get('warnings'):
            lines.append("Warnings:")
            for warning in result['warnings']:
                lines.append(f"  ⚠ {warning}")
            lines.append("")
        
        # Detailed block information for first function with nested blocks
        if result.get('functions'):
            for func_name, func_info in result['functions'].items():
                if func_info.get('has_nested_blocks'):
                    blocks_info = func_info.get('blocks', {})
                    if 'display_output' in blocks_info:
                        lines.append(f"Detailed Block Analysis for {func_name}:")
                        lines.append("-" * 100)
                        # Show first 50 lines of block display
                        block_lines = blocks_info['display_output'].split('\n')[:50]
                        lines.extend(block_lines)
                        if len(blocks_info['display_output'].split('\n')) > 50:
                            lines.append("  ... (truncated)")
                        lines.append("")
                    break  # Only show first function with nested blocks
        
        lines.append("")
    
    # Issues summary
    lines.append("=" * 100)
    lines.append("ISSUES SUMMARY")
    lines.append("=" * 100)
    
    all_errors = []
    all_warnings = []
    for result in all_results:
        for error in result.get('errors', []):
            all_errors.append(f"{result['file_name']}: {error}")
        for warning in result.get('warnings', []):
            all_warnings.append(f"{result['file_name']}: {warning}")
    
    if all_errors:
        lines.append("Errors:")
        for error in all_errors:
            lines.append(f"  ✗ {error}")
        lines.append("")
    else:
        lines.append("No errors found!")
        lines.append("")
    
    if all_warnings:
        lines.append("Warnings:")
        for warning in all_warnings:
            lines.append(f"  ⚠ {warning}")
        lines.append("")
    else:
        lines.append("No warnings found!")
        lines.append("")
    
    # Nested blocks summary
    lines.append("=" * 100)
    lines.append("NESTED BLOCKS ANALYSIS")
    lines.append("=" * 100)
    
    files_with_nested = []
    for result in all_results:
        for func_name, func_info in result.get('functions', {}).items():
            if func_info.get('has_nested_blocks'):
                files_with_nested.append({
                    'file': result['file_name'],
                    'function': func_name,
                    'nested_count': func_info.get('nested_block_count', 0)
                })
    
    if files_with_nested:
        lines.append(f"Found {len(files_with_nested)} functions with nested blocks:")
        for item in files_with_nested:
            lines.append(f"  {item['file']}::{item['function']} ({item['nested_count']} nested blocks)")
    else:
        lines.append("No functions with nested blocks found.")
    
    lines.append("")
    lines.append("=" * 100)
    lines.append("END OF REPORT")
    lines.append("=" * 100)
    
    document = "\n".join(lines)
    
    # Write to file if specified
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(document)
        print(f"✓ Debug document written to: {output_file}")
    
    return document


def main():
    """Main entry point."""
    # Get output file from command line or use default
    output_file = sys.argv[1] if len(sys.argv) > 1 else None
    
    if not output_file:
        # Default: create in results directory
        results_dir = os.path.join(os.path.dirname(__file__), 'results')
        os.makedirs(results_dir, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = os.path.join(results_dir, f'debug_report_{timestamp}.txt')
    
    # Get project root and Original directory
    project_root = os.path.dirname(os.path.dirname(__file__))
    original_dir = os.path.join(project_root, 'Original')
    
    if not os.path.exists(original_dir):
        print(f"Error: Original directory not found at {original_dir}")
        sys.exit(1)
    
    # Find all C files
    c_files = sorted([f for f in os.listdir(original_dir) if f.endswith('.c')])
    
    if not c_files:
        print(f"No C files found in {original_dir}")
        sys.exit(1)
    
    print(f"Found {len(c_files)} C files to analyze")
    print(f"Output will be written to: {output_file}")
    print()
    
    # Analyze each file
    all_results = []
    for idx, c_file_name in enumerate(c_files, 1):
        c_file_path = os.path.join(original_dir, c_file_name)
        print(f"[{idx}/{len(c_files)}] Analyzing {c_file_name}...", end=' ', flush=True)
        
        result = analyze_file(c_file_path)
        all_results.append(result)
        
        if result.get('errors'):
            print(f"✗ ({len(result['errors'])} errors)")
        elif result.get('warnings'):
            print(f"⚠ ({len(result['warnings'])} warnings)")
        else:
            print("✓")
    
    print()
    print("Generating debug document...")
    
    # Generate document
    document = generate_debug_document(all_results, output_file)
    
    print(f"✓ Analysis complete!")
    print(f"  Files analyzed: {len(c_files)}")
    print(f"  Total functions: {sum(len(r.get('statistics', {}).get('function_names', [])) for r in all_results)}")
    print(f"  Total pairs: {sum(r.get('statistics', {}).get('pair_count', 0) for r in all_results)}")
    print(f"  Report saved to: {output_file}")


if __name__ == '__main__':
    main()
