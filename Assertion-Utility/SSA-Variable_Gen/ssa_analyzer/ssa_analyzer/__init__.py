"""
SSA Analyzer - A utility for analyzing SSA versions of important variables in C source code.

Main API:
    get_ssa_versions_for_file: Main entry point to get SSA versions for all important variables
    filter_ssa_to_first_version: Filter results to show only version 2
"""

from .ssa_generator import get_unique_function_variable_pairs, get_ssa_versions_for_pairs
from .filters import filter_ssa_to_first_version
from .derived_naming import get_derived_names_for_file, generate_derived_names
from .formatters import format_cli_output, format_batch_output
from .smt2_verifier import verify_and_merge_ssa_with_smt2, verify_ssa_versions_for_file
from typing import Dict, Tuple


def get_ssa_versions_for_file(c_file_path: str, 
                              filter_to_version_2: bool = False) -> Dict[Tuple[str, str], Dict]:
    """
    Main entry point: Get SSA versions for all important variables in a C file.
    
    Args:
        c_file_path: Path to the C source file
        filter_to_version_2: If True, filter results to show only version 2 (first assignment)
        
    Returns:
        Dictionary mapping (function_name, variable_name) tuples to SSA data:
        {
            (function_name, variable_name): {
                'function': str,
                'mutant_function': str,
                'variable_name': str,
                'source_ssa': [
                    {
                        'version': int,
                        'ssa_name': str,
                        'line': str,
                        'assignment': str,
                        'lhs': str,
                        'rhs': str
                    },
                    ...
                ],
                'mutant_ssa': [...]
            },
            ...
        }
        
    Example:
        >>> ssa_results = get_ssa_versions_for_file('Original/tcas_v15.c')
        >>> for (func, var), data in ssa_results.items():
        ...     print(f"{func}.{var}: {len(data['source_ssa'])} source versions")
    """
    pairs = get_unique_function_variable_pairs(c_file_path)
    ssa_results = get_ssa_versions_for_pairs(pairs, c_file_path)
    
    if filter_to_version_2:
        ssa_results = filter_ssa_to_first_version(ssa_results)
    
    return ssa_results


__all__ = [
    'get_ssa_versions_for_file',
    'get_unique_function_variable_pairs',
    'get_ssa_versions_for_pairs',
    'filter_ssa_to_first_version',
    'get_derived_names_for_file',
    'generate_derived_names',
    'format_cli_output',
    'format_batch_output',
    'verify_and_merge_ssa_with_smt2',
    'verify_ssa_versions_for_file',
]

__version__ = '0.1.0'

