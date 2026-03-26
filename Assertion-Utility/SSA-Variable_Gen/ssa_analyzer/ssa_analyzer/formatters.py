"""
Shared formatting functions for SSA analysis output.

This module provides formatting functions used by both:
- CLI tool (ssa_analyzer.cli) - for single file analysis
- Batch analysis (batch_analysis.py) - for batch processing with SMT2 mapping
"""

from typing import Dict, List, Tuple, Any


def format_cli_output(ssa_results: Dict[Tuple[str, str], Dict], 
                     output_format: str = 'text') -> str:
    """
    Format SSA results for CLI output (from get_ssa_versions_for_file).
    
    This formatter is used by the CLI tool which analyzes C code directly
    without SMT2 file mapping.
    
    Args:
        ssa_results: Dictionary from get_ssa_versions_for_file()
                    Format: {(func_name, var_name): {source_ssa: [...], mutant_ssa: [...], ...}}
        output_format: 'text' or 'json'
        
    Returns:
        Formatted output string
    """
    if output_format == 'json':
        # Convert tuple keys to strings for JSON serialization
        json_results = {}
        for (func, var), data in ssa_results.items():
            key = f"{func}.{var}"
            json_results[key] = data
        import json
        return json.dumps(json_results, indent=2)
    
    # Text format
    lines = []
    lines.append("=" * 80)
    lines.append("SSA VERSIONS FOR IMPORTANT VARIABLES")
    lines.append("=" * 80)
    lines.append("")
    
    for (func_name, var_name), data in sorted(ssa_results.items()):
        lines.append(f"Function: {func_name}")
        lines.append(f"Variable: {var_name}")
        lines.append(f"Mutant Function: {data.get('mutant_function', 'N/A')}")
        lines.append("")
        
        lines.append(f"  Source SSA versions ({len(data['source_ssa'])}):")
        for ssa in data['source_ssa']:
            lines.append(f"    Version {ssa['version']}: {ssa['ssa_name']}")
            lines.append(f"      Assignment: {ssa['assignment']}")
            lines.append(f"      Line: {ssa['line']}")
        
        lines.append("")
        lines.append(f"  Mutant SSA versions ({len(data['mutant_ssa'])}):")
        for ssa in data['mutant_ssa']:
            lines.append(f"    Version {ssa['version']}: {ssa['ssa_name']}")
            lines.append(f"      Assignment: {ssa['assignment']}")
            lines.append(f"      Line: {ssa['line']}")
            # Display predicate pair if this is a missing statement
            if 'missing_predicate_pair' in ssa:
                pair = ssa['missing_predicate_pair']
                if pair:
                    p_src, p_mut = pair
                    lines.append(f"      Missing Statement Predicate Pair: ({p_src}, {p_mut})")
        
        # Display condition predicate pairs if present
        condition_pairs = data.get('condition_predicate_pairs', [])
        if condition_pairs:
            lines.append("")
            lines.append(f"  Condition Predicate Pairs ({len(condition_pairs)}):")
            for i, (p_src, p_mut) in enumerate(condition_pairs, 1):
                lines.append(f"    Pair {i}: ({p_src}, {p_mut})")
                lines.append(f"      SAT Assertion: ({p_src} ≠ {p_mut}) ⇒ (o_src ≠ o_mut)")
        
        lines.append("")
        lines.append("-" * 80)
        lines.append("")
    
    return "\n".join(lines)


def format_batch_output(ssa_results: Dict[str, List[Dict]], 
                       c_file_name: str = "") -> str:
    """
    Format SSA results for batch analysis output (from get_ssa_variables_for_assertions).
    
    This formatter is used by batch_analysis.py which maps derived names to
    actual SSA variable names from SMT2 files.
    
    Args:
        ssa_results: Dictionary with 'source' and 'mutant' keys
                    Format: {'source': [{function, variable, ssa_variable_name, ...}], 
                            'mutant': [{...}]}
        c_file_name: Name of the C file being analyzed (optional, for context)
        
    Returns:
        Formatted string matching analysis_v*.txt format
    """
    lines = []
    lines.append("=" * 80)
    lines.append("SSA VERSIONS FOR IMPORTANT VARIABLES")
    lines.append("=" * 80)
    lines.append("")
    
    # Group by function and variable
    from collections import defaultdict
    grouped = defaultdict(lambda: {'source': [], 'mutant': []})
    
    for r in ssa_results.get('source', []):
        func = r.get('function', '')
        var = r.get('variable', '')
        key = (func, var)
        grouped[key]['source'].append(r)
    
    for r in ssa_results.get('mutant', []):
        func = r.get('function', '')
        var = r.get('variable', '')
        key = (func, var)
        grouped[key]['mutant'].append(r)
    
    # Output grouped by function/variable
    for (func_name, var_name), data in sorted(grouped.items()):
        mut_func_name = func_name + "_2" if data['mutant'] else None
        
        lines.append(f"Function: {func_name}")
        lines.append(f"Variable: {var_name}")
        if mut_func_name:
            lines.append(f"Mutant Function: {mut_func_name}")
        lines.append("")
        
        # Source SSA versions - remove duplicates
        if data['source']:
            seen_ssa = set()
            unique_source = []
            for r in data['source']:
                ssa_name = r.get('ssa_variable_name', '').strip('|')
                if ssa_name and ssa_name not in seen_ssa:
                    seen_ssa.add(ssa_name)
                    unique_source.append(r)
            
            lines.append(f"  Source SSA versions ({len(unique_source)}):")
            for r in unique_source:
                ssa_name = r.get('ssa_variable_name', 'N/A').strip('|')
                version = r.get('version', 0)
                
                assignment = r.get('assignment', '')
                line = r.get('line', '')
                
                lines.append(f"    Version {version}: {ssa_name}")
                if assignment:
                    lines.append(f"      Assignment: {assignment}")
                if line:
                    lines.append(f"      Line: {line}")
            lines.append("")
        
        # Mutant SSA versions - remove duplicates
        if data['mutant']:
            seen_ssa = set()
            unique_mutant = []
            for r in data['mutant']:
                ssa_name = r.get('ssa_variable_name', '').strip('|')
                if ssa_name and ssa_name not in seen_ssa:
                    seen_ssa.add(ssa_name)
                    unique_mutant.append(r)
            
            lines.append(f"  Mutant SSA versions ({len(unique_mutant)}):")
            for r in unique_mutant:
                ssa_name = r.get('ssa_variable_name', 'N/A').strip('|')
                version = r.get('version', 0)
                
                assignment = r.get('assignment', '')
                line = r.get('line', '')
                
                lines.append(f"    Version {version}: {ssa_name}")
                if assignment:
                    lines.append(f"      Assignment: {assignment}")
                if line:
                    lines.append(f"      Line: {line}")
                
                # Add predicate pair if available
                pair = r.get('missing_predicate_pair')
                if pair:
                    p_src, p_mut = pair
                    lines.append(f"      Missing Statement Predicate Pair: ({p_src}, {p_mut})")
            lines.append("")
        
        lines.append("-" * 80)
        lines.append("")
    
    return "\n".join(lines)

