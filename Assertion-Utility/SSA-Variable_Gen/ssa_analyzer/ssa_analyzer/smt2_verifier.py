"""
SMT2 SSA Variable Verifier.

This module provides functionality to verify and merge SSA variables from utility results
with SSA variables extracted from SMT2 files. If a variable matches by function name,
variable name, and version, but the SSA name differs (e.g., different @N part), the
SMT2 version is used.

Pure function: Creates new data structures, no side effects.
"""

import re
from typing import Dict, Tuple, Optional, List
from .smt2_ssa_extractor import extract_ssa_variables_from_smt2
from .parser import normalize_identifiers


def parse_ssa_name_from_utility(ssa_name: str) -> Optional[Tuple[str, str, int, bool]]:
    """
    Parse SSA name from utility to extract (function, variable, version, is_mutant).
    
    Pure function: no side effects.
    
    Args:
        ssa_name: SSA name from utility (e.g., "alt_sep_test::1::enabled!0@1#2")
        
    Returns:
        Tuple of (function_name, variable_name, version, is_mutant) or None if parsing fails
    """
    # Pattern for regular variables: function::1::variable!0@N#version
    name_pattern = re.compile(r'^([^:]+)::1::([^!]+)!0@\d+#(\d+)$')
    
    # Pattern for return values: goto_symex::return_value::function_name!0#version
    return_value_pattern = re.compile(r'^goto_symex::return_value::([^!]+)!0#(\d+)$')
    
    # Pattern for captured returns: function::$tmp::return_value_function_name!0@N#version
    captured_return_pattern = re.compile(r'^([^:]+)::\$tmp::return_value_([^!]+)!0@\d+#(\d+)$')
    
    # Try regular variable pattern
    name_match = name_pattern.match(ssa_name)
    if name_match:
        func_part = name_match.group(1)
        var_part = name_match.group(2)
        version = int(name_match.group(3))
        
        # Check if mutant (ends with _2)
        is_mutant = func_part.endswith('_2')
        if is_mutant:
            func_name = func_part[:-2]
            var_name = var_part[:-2] if var_part.endswith('_2') else var_part
        else:
            func_name = func_part
            var_name = var_part
        
        normalized_var = normalize_identifiers(var_name)
        return (func_name, normalized_var, version, is_mutant)
    
    # Try return value pattern
    return_match = return_value_pattern.match(ssa_name)
    if return_match:
        callee_part = return_match.group(1)
        version = int(return_match.group(2))
        
        is_mutant = callee_part.endswith('_2')
        if is_mutant:
            callee_name = callee_part[:-2]
        else:
            callee_name = callee_part
        
        return ('return_value', callee_name, version, is_mutant)
    
    # Try captured return pattern
    captured_return_match = captured_return_pattern.match(ssa_name)
    if captured_return_match:
        func_part = captured_return_match.group(1)
        callee_part = captured_return_match.group(2)
        version = int(captured_return_match.group(3))
        
        is_mutant = func_part.endswith('_2')
        if is_mutant:
            func_name = func_part[:-2]
            callee_name = callee_part[:-2] if callee_part.endswith('_2') else callee_part
        else:
            func_name = func_part
            callee_name = callee_part
        
        return (func_name, f'ret_{callee_name}', version, is_mutant)
    
    return None


def extract_ssa_names_from_expression(expr: str) -> List[str]:
    """
    Extract all SSA variable names from an expression string.
    
    Pure function: no side effects.
    
    Args:
        expr: Expression string that may contain SSA names like "func::1::var!0@1#2"
        
    Returns:
        List of SSA variable names found in the expression
    """
    ssa_names = []
    
    # Pattern 1: Regular variables: function::1::variable!0@N#version
    # Matches: alt_sep_test::1::need_upward_RA!0@1#2
    pattern1 = re.compile(r'[A-Za-z_][A-Za-z0-9_]*(?:_2)?::1::[A-Za-z_][A-Za-z0-9_]*(?:_2)?!0@\d+#\d+')
    matches1 = pattern1.findall(expr)
    ssa_names.extend(matches1)
    
    # Pattern 2: Return values: goto_symex::return_value::function!0#version
    # Matches: goto_symex::return_value::Own_Above_Threat!0#1
    pattern2 = re.compile(r'goto_symex::return_value::[A-Za-z_][A-Za-z0-9_]*(?:_2)?!0#\d+')
    matches2 = pattern2.findall(expr)
    ssa_names.extend(matches2)
    
    # Pattern 3: Captured returns: function::$tmp::return_value_function!0@N#version
    # Matches: Non_Crossing_Biased_Climb::$tmp::return_value_Own_Below_Threat!0@1#2
    pattern3 = re.compile(r'[A-Za-z_][A-Za-z0-9_]*(?:_2)?::\$tmp::return_value_[A-Za-z_][A-Za-z0-9_]*(?:_2)?!0@\d+#\d+')
    matches3 = pattern3.findall(expr)
    ssa_names.extend(matches3)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_ssa_names = []
    for name in ssa_names:
        if name not in seen:
            seen.add(name)
            unique_ssa_names.append(name)
    
    return unique_ssa_names


def verify_ssa_name_in_smt2(ssa_name: str, smt2_lookup: Dict) -> Optional[str]:
    """
    Verify a single SSA name against SMT2 and return verified name if different.
    
    Pure function: no side effects.
    
    Args:
        ssa_name: SSA name to verify
        smt2_lookup: Lookup dictionary from extract_ssa_variables_from_smt2()
        
    Returns:
        Verified SSA name (from SMT2 if different, original if same, None if not found)
    """
    parsed = parse_ssa_name_from_utility(ssa_name)
    if not parsed:
        return None
    
    func, var, version, is_mutant = parsed
    lookup_key = (func, var, version, is_mutant)
    
    if lookup_key in smt2_lookup:
        smt2_ssa_name = smt2_lookup[lookup_key].get('ssa_name', '')
        if smt2_ssa_name and smt2_ssa_name != ssa_name:
            return smt2_ssa_name
        return ssa_name  # Match found, names are same
    return None  # Not found in SMT2


def verify_and_merge_ssa_with_smt2(
    utility_results: Dict[Tuple[str, str], Dict],
    smt2_file_path: str
) -> Dict[Tuple[str, str], Dict]:
    """
    Verify utility SSA variables against SMT2 file and merge information.
    
    Pure function: Creates new data structures, no side effects.
    
    For each SSA variable in utility results:
    1. Extract (function, variable, version) from utility SSA name
    2. Look up matching variable in SMT2 file by (function, variable, version)
    3. If match found:
       - If SSA name differs (e.g., different @N part), use SMT2 SSA name
       - Store SMT2 type and expression as additional metadata
       - Prefer SMT2 values when they differ from utility values
    4. Verify all SSA variables used in assertions (predicate pairs)
    5. Preserve utility information (assignment, line, etc.) alongside SMT2 data
    
    When mismatches occur (other than name and version), SMT2 values are preferred:
    - SSA name: If different, use SMT2 version
    - Type: Store SMT2 type as `_smt2_type`
    - Expression: Store SMT2 expression as `_smt2_expression`
    - Both utility and SMT2 information are preserved for comparison
    
    Args:
        utility_results: Dictionary from get_ssa_versions_for_pairs() or get_ssa_versions_for_pairs_rda()
                         Format: {(func_name, var_name): {
                             'source_ssa': [...],
                             'mutant_ssa': [...],
                             'mutant_function': str,
                             'condition_predicate_pairs': [...]
                         }}
        smt2_file_path: Path to corresponding SMT2 file
        
    Returns:
        New dictionary with same structure as utility_results, but with:
        - SSA names updated from SMT2 when they differ
        - SMT2 type and expression stored as `_smt2_type` and `_smt2_expression`
        - Verification status in `_smt2_verified`, `_smt2_match`, `_smt2_updated`
        - Assertion verification status in `_assertion_verification_status`
    """
    # Extract SSA variables from SMT2 file
    smt2_vars = extract_ssa_variables_from_smt2(smt2_file_path)
    
    # Build lookup map: (function, variable, version, is_mutant) -> SMT2 SSA info
    smt2_lookup = {}
    for key, ssa_info in smt2_vars.items():
        # key is (function, variable, version, is_mutant)
        smt2_lookup[key] = ssa_info
    
    # Create new results dictionary (side-effect free)
    verified_results = {}
    
    for (func_name, var_name), data in utility_results.items():
        # Create new data dictionary
        new_data = {
            'source_ssa': [],
            'mutant_ssa': [],
            'mutant_function': data.get('mutant_function'),
            'condition_predicate_pairs': data.get('condition_predicate_pairs', [])
        }
        
        # Process source SSA versions
        for ssa_entry in data.get('source_ssa', []):
            # Create new entry (copy all fields)
            new_entry = ssa_entry.copy()
            
            utility_ssa_name = ssa_entry.get('ssa_name', '')
            if utility_ssa_name:
                # Parse utility SSA name
                parsed = parse_ssa_name_from_utility(utility_ssa_name)
                
                if parsed:
                    func, var, version, is_mutant = parsed
                    
                    # Use parsed result directly as lookup key (source is not mutant, so is_mutant=False)
                    # parse_ssa_name_from_utility already handles return values correctly:
                    # - goto_symex returns: ('return_value', callee_name, version, is_mutant)
                    # - captured returns: (func_name, 'ret_callee', version, is_mutant)
                    # - regular vars: (func_name, var_name, version, is_mutant)
                    lookup_key = (func, var, version, False)  # Source is not mutant
                    
                    if lookup_key in smt2_lookup:
                        smt2_info = smt2_lookup[lookup_key]
                        smt2_ssa_name = smt2_info.get('ssa_name', '')
                        
                        # Prefer SMT2 values when they differ
                        updated = False
                        
                        # If SSA names differ (e.g., different @N part), use SMT2 version
                        if smt2_ssa_name and smt2_ssa_name != utility_ssa_name:
                            new_entry['ssa_name'] = smt2_ssa_name
                            new_entry['_original_ssa_name'] = utility_ssa_name
                            updated = True
                        
                        # Prefer SMT2 type if available and different
                        smt2_type = smt2_info.get('smt2_type')
                        if smt2_type:
                            new_entry['_smt2_type'] = smt2_type
                            # Compare with utility type if available
                            utility_type = new_entry.get('type')
                            if utility_type and utility_type != smt2_type:
                                new_entry['_original_type'] = utility_type
                                updated = True
                        
                        # Prefer SMT2 expression if available
                        smt2_expr = smt2_info.get('smt2_expression')
                        if smt2_expr:
                            new_entry['_smt2_expression'] = smt2_expr
                            # Note: Utility stores C assignment, SMT2 stores SMT2 expression
                            # These are different formats, so we store both
                        
                        new_entry['_smt2_verified'] = True
                        if updated:
                            new_entry['_smt2_updated'] = True
                        else:
                            new_entry['_smt2_match'] = True
                    else:
                        # No match found in SMT2
                        new_entry['_smt2_verified'] = False
                else:
                    # Could not parse SSA name
                    new_entry['_smt2_verified'] = False
            else:
                # No SSA name in entry
                new_entry['_smt2_verified'] = False
            
            new_data['source_ssa'].append(new_entry)
        
        # Process mutant SSA versions
        mut_func_name = data.get('mutant_function')
        for ssa_entry in data.get('mutant_ssa', []):
            # Create new entry (copy all fields)
            new_entry = ssa_entry.copy()
            
            utility_ssa_name = ssa_entry.get('ssa_name', '')
            if utility_ssa_name:
                # Parse utility SSA name
                parsed = parse_ssa_name_from_utility(utility_ssa_name)
                
                if parsed:
                    func, var, version, is_mutant = parsed
                    
                    # Use parsed result directly as lookup key (mutant has is_mutant=True)
                    # parse_ssa_name_from_utility already handles return values correctly
                    lookup_key = (func, var, version, True)  # Mutant is_mutant=True
                    
                    if lookup_key in smt2_lookup:
                        smt2_info = smt2_lookup[lookup_key]
                        smt2_ssa_name = smt2_info.get('ssa_name', '')
                        
                        # Prefer SMT2 values when they differ
                        updated = False
                        
                        # If SSA names differ, use SMT2 version
                        if smt2_ssa_name and smt2_ssa_name != utility_ssa_name:
                            new_entry['ssa_name'] = smt2_ssa_name
                            new_entry['_original_ssa_name'] = utility_ssa_name
                            updated = True
                            
                            # Update predicate pair if it contains the old SSA name
                            if 'missing_predicate_pair' in new_entry:
                                pair = new_entry['missing_predicate_pair']
                                if pair and isinstance(pair, tuple) and len(pair) == 2:
                                    p_src, p_mut = pair
                                    # If predicate contains old SSA name, update it
                                    if utility_ssa_name in p_mut:
                                        updated_p_mut = p_mut.replace(utility_ssa_name, smt2_ssa_name)
                                        new_entry['missing_predicate_pair'] = (p_src, updated_p_mut)
                        
                        # Prefer SMT2 type if available and different
                        smt2_type = smt2_info.get('smt2_type')
                        if smt2_type:
                            new_entry['_smt2_type'] = smt2_type
                            # Compare with utility type if available
                            utility_type = new_entry.get('type')
                            if utility_type and utility_type != smt2_type:
                                new_entry['_original_type'] = utility_type
                                updated = True
                        
                        # Prefer SMT2 expression if available
                        smt2_expr = smt2_info.get('smt2_expression')
                        if smt2_expr:
                            new_entry['_smt2_expression'] = smt2_expr
                            # Note: Utility stores C assignment, SMT2 stores SMT2 expression
                            # These are different formats, so we store both
                        
                        new_entry['_smt2_verified'] = True
                        if updated:
                            new_entry['_smt2_updated'] = True
                        else:
                            new_entry['_smt2_match'] = True
                    else:
                        # No match found in SMT2
                        new_entry['_smt2_verified'] = False
                else:
                    # Could not parse SSA name
                    new_entry['_smt2_verified'] = False
            else:
                # No SSA name in entry
                new_entry['_smt2_verified'] = False
            
            new_data['mutant_ssa'].append(new_entry)
        
        # Process condition predicate pairs - verify SSA variables in assertions
        updated_condition_pairs = []
        assertion_verification_status = []
        
        for pair in data.get('condition_predicate_pairs', []):
            if isinstance(pair, tuple) and len(pair) == 2:
                src_pred, mut_pred = pair
                
                # Extract SSA names from both predicates
                src_ssa_names = extract_ssa_names_from_expression(src_pred)
                mut_ssa_names = extract_ssa_names_from_expression(mut_pred)
                
                # Verify and update SSA names in predicates
                updated_src_pred = src_pred
                updated_mut_pred = mut_pred
                all_verified = True
                any_updated = False
                
                for ssa_name in src_ssa_names:
                    verified_name = verify_ssa_name_in_smt2(ssa_name, smt2_lookup)
                    if verified_name is None:
                        all_verified = False
                        assertion_verification_status.append({
                            'ssa_name': ssa_name,
                            'predicate': 'source',
                            'status': 'not_found_in_smt2'
                        })
                    elif verified_name != ssa_name:
                        updated_src_pred = updated_src_pred.replace(ssa_name, verified_name)
                        any_updated = True
                        assertion_verification_status.append({
                            'ssa_name': ssa_name,
                            'verified_name': verified_name,
                            'predicate': 'source',
                            'status': 'updated'
                        })
                    else:
                        assertion_verification_status.append({
                            'ssa_name': ssa_name,
                            'predicate': 'source',
                            'status': 'verified'
                        })
                
                for ssa_name in mut_ssa_names:
                    verified_name = verify_ssa_name_in_smt2(ssa_name, smt2_lookup)
                    if verified_name is None:
                        all_verified = False
                        assertion_verification_status.append({
                            'ssa_name': ssa_name,
                            'predicate': 'mutant',
                            'status': 'not_found_in_smt2'
                        })
                    elif verified_name != ssa_name:
                        updated_mut_pred = updated_mut_pred.replace(ssa_name, verified_name)
                        any_updated = True
                        assertion_verification_status.append({
                            'ssa_name': ssa_name,
                            'verified_name': verified_name,
                            'predicate': 'mutant',
                            'status': 'updated'
                        })
                    else:
                        assertion_verification_status.append({
                            'ssa_name': ssa_name,
                            'predicate': 'mutant',
                            'status': 'verified'
                        })
                
                # Use updated predicates if any SSA names were updated
                if any_updated:
                    updated_condition_pairs.append((updated_src_pred, updated_mut_pred))
                else:
                    updated_condition_pairs.append(pair)
            else:
                updated_condition_pairs.append(pair)
        
        new_data['condition_predicate_pairs'] = updated_condition_pairs
        if assertion_verification_status:
            new_data['_assertion_verification_status'] = assertion_verification_status
        
        # Process missing_predicate_pair in source_ssa and mutant_ssa entries
        # (This is already handled above when processing entries, but we should also verify them)
        for entry in new_data['source_ssa']:
            if 'missing_predicate_pair' in entry:
                pair = entry['missing_predicate_pair']
                if isinstance(pair, tuple) and len(pair) == 2:
                    p_src, p_mut = pair
                    
                    # Extract and verify SSA names
                    src_ssa_names = extract_ssa_names_from_expression(p_src)
                    mut_ssa_names = extract_ssa_names_from_expression(p_mut)
                    
                    updated_p_src = p_src
                    updated_p_mut = p_mut
                    
                    for ssa_name in src_ssa_names:
                        verified_name = verify_ssa_name_in_smt2(ssa_name, smt2_lookup)
                        if verified_name and verified_name != ssa_name:
                            updated_p_src = updated_p_src.replace(ssa_name, verified_name)
                    
                    for ssa_name in mut_ssa_names:
                        verified_name = verify_ssa_name_in_smt2(ssa_name, smt2_lookup)
                        if verified_name and verified_name != ssa_name:
                            updated_p_mut = updated_p_mut.replace(ssa_name, verified_name)
                    
                    if updated_p_src != p_src or updated_p_mut != p_mut:
                        entry['missing_predicate_pair'] = (updated_p_src, updated_p_mut)
        
        for entry in new_data['mutant_ssa']:
            if 'missing_predicate_pair' in entry:
                pair = entry['missing_predicate_pair']
                if isinstance(pair, tuple) and len(pair) == 2:
                    p_src, p_mut = pair
                    
                    # Extract and verify SSA names
                    src_ssa_names = extract_ssa_names_from_expression(p_src)
                    mut_ssa_names = extract_ssa_names_from_expression(p_mut)
                    
                    updated_p_src = p_src
                    updated_p_mut = p_mut
                    
                    for ssa_name in src_ssa_names:
                        verified_name = verify_ssa_name_in_smt2(ssa_name, smt2_lookup)
                        if verified_name and verified_name != ssa_name:
                            updated_p_src = updated_p_src.replace(ssa_name, verified_name)
                    
                    for ssa_name in mut_ssa_names:
                        verified_name = verify_ssa_name_in_smt2(ssa_name, smt2_lookup)
                        if verified_name and verified_name != ssa_name:
                            updated_p_mut = updated_p_mut.replace(ssa_name, verified_name)
                    
                    if updated_p_src != p_src or updated_p_mut != p_mut:
                        entry['missing_predicate_pair'] = (updated_p_src, updated_p_mut)
        
        verified_results[(func_name, var_name)] = new_data
    
    return verified_results


def verify_ssa_versions_for_file(
    c_file_path: str,
    smt2_file_path: str,
    use_rda: bool = False,
    filter_to_version_2: bool = False
) -> Dict[Tuple[str, str], Dict]:
    """
    Get SSA versions for file and verify/merge with SMT2 file.
    
    Pure function: Creates new data structures, no side effects.
    
    Args:
        c_file_path: Path to C source file
        smt2_file_path: Path to corresponding SMT2 file
        use_rda: If True, use RDA-compliant analysis
        filter_to_version_2: If True, filter to version 2 only
        
    Returns:
        Dictionary with verified SSA results (same format as get_ssa_versions_for_file)
    """
    # Get utility results
    if use_rda:
        from .rda_ssa_generator import get_ssa_versions_for_pairs_rda
        from .ssa_generator import get_unique_function_variable_pairs
        
        pairs = get_unique_function_variable_pairs(c_file_path)
        utility_results = get_ssa_versions_for_pairs_rda(pairs, c_file_path)
    else:
        from .ssa_generator import get_unique_function_variable_pairs, get_ssa_versions_for_pairs
        
        pairs = get_unique_function_variable_pairs(c_file_path)
        utility_results = get_ssa_versions_for_pairs(pairs, c_file_path)
    
    # Verify and merge with SMT2
    verified_results = verify_and_merge_ssa_with_smt2(utility_results, smt2_file_path)
    
    # Filter if requested
    if filter_to_version_2:
        from .filters import filter_ssa_to_first_version
        verified_results = filter_ssa_to_first_version(verified_results)
    
    return verified_results

