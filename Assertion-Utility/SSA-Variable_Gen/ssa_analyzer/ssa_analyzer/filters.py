"""SSA result filtering utilities."""

from typing import Dict, Tuple


def filter_ssa_to_first_version(ssa_results: Dict[Tuple[str, str], Dict]) -> Dict[Tuple[str, str], Dict]:
    """
    Filter SSA results to show only version 2 (first assignment) for variables with multiple versions.
    
    This addresses cases where version 2 should be shown instead of version 3.
    
    Args:
        ssa_results: Dictionary from get_ssa_versions_for_pairs() mapping 
                     (function_name, variable_name) to SSA data
        
    Returns:
        Filtered dictionary with only version 2 (first assignment) kept for each variable
    """
    filtered_results = {}
    
    for key, data in ssa_results.items():
        func_name = data['function']
        var_name = data['variable_name']
        src_ssa = data['source_ssa']
        mut_ssa = data['mutant_ssa']
        
        # If there are multiple versions, keep only version 2 (first assignment)
        if len(src_ssa) > 1 or len(mut_ssa) > 1:
            # Find version 2 in source (first assignment)
            src_version_2 = None
            for ssa in src_ssa:
                if ssa['version'] == 2:
                    src_version_2 = ssa
                    break
            
            # Find version 2 in mutant (first assignment)
            mut_version_2 = None
            for ssa in mut_ssa:
                if ssa['version'] == 2:
                    mut_version_2 = ssa
                    break
            
            # Only include if version 2 exists
            if src_version_2 and mut_version_2:
                filtered_results[key] = {
                    'function': func_name,
                    'mutant_function': data.get('mutant_function'),
                    'variable_name': var_name,
                    'source_ssa': [src_version_2],
                    'mutant_ssa': [mut_version_2]
                }
            else:
                # If version 2 doesn't exist, keep original
                filtered_results[key] = data
        else:
            # If only one version, keep as is
            filtered_results[key] = data
    
    return filtered_results

