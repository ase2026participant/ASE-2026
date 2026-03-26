"""
Extract SSA variable names from SMT2 files and map them to derived names.
"""

import re
from typing import Dict, List, Tuple, Optional
from .parser import normalize_identifiers, read_c_source, strip_comments


def extract_ssa_variables_from_smt2(smt2_file_path: str) -> Dict[str, Dict]:
    """
    Extract SSA variable definitions from an SMT2 file.
    
    Args:
        smt2_file_path: Path to SMT2 file
        
    Returns:
        Dictionary mapping SSA variable names to metadata:
        {
            "ssa_name": str,  # Full SSA name like "alt_sep_test::1::enabled!0@1#2"
            "function": str,  # Function name (e.g., "alt_sep_test")
            "variable": str,  # Variable name (e.g., "enabled")
            "version": int,   # SSA version number (e.g., 2)
            "is_mutant": bool # True if from mutant function (_2 suffix)
        }
    """
    ssa_vars = {}
    
    # Pattern to match SSA variable definitions with full information
    # Format: (define-fun |function::1::variable!0@1#version| () (type) (expression))
    # Or: (declare-fun |function::1::variable!0@1#version| () (type))
    ssa_pattern = re.compile(
        r'\((?:define-fun|declare-fun)\s+\|([^|]+)\|'
    )
    
    # Pattern to extract type and expression from define-fun
    # Matches: (define-fun |name| () (type) (expr))
    define_fun_pattern = re.compile(
        r'\(define-fun\s+\|([^|]+)\|\s+\(\)\s+\(([^)]+)\)\s+(.+)\)'
    )
    
    # Pattern to extract function, variable, and version from SSA name
    # Format: function::1::variable!0@1#version
    # Or: function_2::1::variable_2!0@1#version (mutant)
    # Or: goto_symex::return_value::function_name!0#version (return values)
    # Or: function::$tmp::return_value_function_name!0@1#version (captured return values)
    name_pattern = re.compile(
        r'^([^:]+)::1::([^!]+)!0@\d+#(\d+)$'
    )
    return_value_pattern = re.compile(
        r'^goto_symex::return_value::([^!]+)!0#(\d+)$'
    )
    captured_return_pattern = re.compile(
        r'^([^:]+)::\$tmp::return_value_([^!]+)!0@\d+#(\d+)$'
    )
    
    try:
        with open(smt2_file_path, 'r', encoding='utf-8') as f:
            for line in f:
                # Try to extract full definition (type and expression) from single line
                # Pattern: (define-fun |name| () (type) (expression))
                define_match = define_fun_pattern.search(line)
                if define_match:
                    ssa_name = define_match.group(1)
                    var_type = define_match.group(2).strip()
                    expression = define_match.group(3).strip()
                else:
                    # Fallback to simple pattern match (for declare-fun or incomplete lines)
                    match = ssa_pattern.search(line)
                    if match:
                        ssa_name = match.group(1)
                        var_type = None
                        expression = None
                    else:
                        continue
                
                if ssa_name:
                    
                    # Parse the SSA name - try different patterns
                    name_match = name_pattern.match(ssa_name)
                    return_match = return_value_pattern.match(ssa_name)
                    captured_return_match = captured_return_pattern.match(ssa_name)
                    
                    if name_match:
                        # Regular variable: function::1::variable!0@N#version
                        # Note: @N can vary (e.g., @1, @2) but version (#N) is what matters
                        func_part = name_match.group(1)
                        var_part = name_match.group(2)
                        version = int(name_match.group(3))
                        
                        # Check if mutant (ends with _2)
                        is_mutant = func_part.endswith('_2')
                        if is_mutant:
                            func_name = func_part[:-2]  # Remove _2 suffix
                            var_name = var_part[:-2] if var_part.endswith('_2') else var_part
                        else:
                            func_name = func_part
                            var_name = var_part
                        
                        # Normalize variable name (remove _2 suffix if present)
                        normalized_var = normalize_identifiers(var_name)
                        
                        # Store with multiple keys for lookup
                        # Use version as primary key (ignore @N part)
                        key = (func_name, normalized_var, version, is_mutant)
                        
                        # If key already exists, prefer the one with @1 (first occurrence)
                        if key not in ssa_vars or '@1#' in ssa_name:
                            ssa_vars[key] = {
                                'ssa_name': ssa_name,
                                'full_ssa_name': f"|{ssa_name}|",  # With pipes for SMT2
                                'function': func_name,
                                'variable': normalized_var,
                                'version': version,
                                'is_mutant': is_mutant,
                                'type': 'variable',
                                'smt2_type': var_type,  # SMT2 type (e.g., "_ BitVec 32")
                                'smt2_expression': expression  # SMT2 expression/definition
                            }
                    
                    elif return_match:
                        # Return value: goto_symex::return_value::function_name!0#version
                        callee_part = return_match.group(1)
                        version = int(return_match.group(2))
                        
                        # Check if mutant
                        is_mutant = callee_part.endswith('_2')
                        if is_mutant:
                            callee_name = callee_part[:-2]
                        else:
                            callee_name = callee_part
                        
                        # Store return value
                        key = ('return_value', callee_name, version, is_mutant)
                        ssa_vars[key] = {
                            'ssa_name': ssa_name,
                            'full_ssa_name': f"|{ssa_name}|",
                            'function': callee_name,
                            'variable': 'return',
                            'version': version,
                            'is_mutant': is_mutant,
                            'type': 'return_value',
                            'callee': callee_name,
                            'smt2_type': var_type,
                            'smt2_expression': expression
                        }
                    
                    elif captured_return_match:
                        # Captured return: function::$tmp::return_value_function_name!0@1#version
                        func_part = captured_return_match.group(1)
                        callee_part = captured_return_match.group(2)
                        version = int(captured_return_match.group(3))
                        
                        # Check if mutant
                        is_mutant = func_part.endswith('_2')
                        if is_mutant:
                            func_name = func_part[:-2]
                            callee_name = callee_part[:-2] if callee_part.endswith('_2') else callee_part
                        else:
                            func_name = func_part
                            callee_name = callee_part
                        
                        # Store captured return (used in assignments)
                        key = (func_name, f'ret_{callee_name}', version, is_mutant)
                        ssa_vars[key] = {
                            'ssa_name': ssa_name,
                            'full_ssa_name': f"|{ssa_name}|",
                            'function': func_name,
                            'variable': f'ret_{callee_name}',
                            'version': version,
                            'is_mutant': is_mutant,
                            'type': 'captured_return',
                            'callee': callee_name,
                            'smt2_type': var_type,
                            'smt2_expression': expression
                        }
    except FileNotFoundError:
        pass
    
    return ssa_vars


def map_derived_names_to_ssa_variables(
    derived_names: List[Dict],
    smt2_file_path: str,
    is_mutant: bool = False,
    c_file_path: Optional[str] = None
) -> List[Dict]:
    """
    Map derived names to actual SSA variable names from SMT2 file.
    
    Args:
        derived_names: List of derived name dictionaries from generate_derived_names()
        smt2_file_path: Path to SMT2 file
        is_mutant: If True, map to mutant SSA variables (with _2 suffix)
        c_file_path: Optional path to C source file for extracting assignment text
        
    Returns:
        List of dictionaries with SSA variable names:
        {
            "derived_name": str,
            "ssa_variable_name": str,  # Full SSA name for assertions
            "original_variable": str (if assignment),
            "callee": str (if function return),
            "function": str,
            "source_line": int,
            "frame_path": str,
            "ssa_version": str,
            "is_mutant": bool
        }
    """
    # Extract SSA variables from SMT2 file
    ssa_vars = extract_ssa_variables_from_smt2(smt2_file_path)
    
    results = []
    
    for derived in derived_names:
        func_name = derived['function']
        ssa_version_str = derived.get('ssa_version', 'v0')
        
        # Extract version number from "v2" format
        version_match = re.match(r'v(\d+)', ssa_version_str)
        if not version_match:
            continue
        
        version = int(version_match.group(1))
        
        # Determine if we're looking for mutant or source
        target_is_mutant = is_mutant
        
        # Look up SSA variable
        if 'original_variable' in derived:
            # Variable assignment
            var_name = normalize_identifiers(derived['original_variable'])
            key = (func_name, var_name, version, target_is_mutant)
            
            if key in ssa_vars:
                ssa_info = ssa_vars[key]
                result = derived.copy()
                result['ssa_variable_name'] = ssa_info['full_ssa_name']
                result['is_mutant'] = target_is_mutant
                
                # Extract assignment text from source if available
                if c_file_path and 'source_line' in derived:
                    source_lines = read_c_source(c_file_path)
                    line_num = derived['source_line']
                    if 0 < line_num <= len(source_lines):
                        line = source_lines[line_num - 1]
                        clean = strip_comments(line)
                        # Try to extract assignment
                        assign_match = re.match(r'^\s*(\w+)\s*=\s*(.+);', clean)
                        if assign_match:
                            result['assignment'] = clean.strip()
                        result['line'] = line.rstrip('\n')
                
                results.append(result)
        
        elif 'callee' in derived:
            # Function return usage
            callee = derived['callee']
            if callee:
                # First try to find captured return value (used in assignments)
                # Format: function::$tmp::return_value_callee!0@1#version
                func_name = derived['function']
                captured_key = (func_name, f'ret_{callee}', version, target_is_mutant)
                
                if captured_key in ssa_vars:
                    ssa_info = ssa_vars[captured_key]
                    result = derived.copy()
                    result['ssa_variable_name'] = ssa_info['full_ssa_name']
                    result['is_mutant'] = target_is_mutant
                    
                    # Extract assignment text from source if available
                    if c_file_path and 'source_line' in derived:
                        source_lines = read_c_source(c_file_path)
                        line_num = derived['source_line']
                        if 0 < line_num <= len(source_lines):
                            line = source_lines[line_num - 1]
                            clean = strip_comments(line)
                            # Try to extract assignment
                            assign_match = re.match(r'^\s*(\w+)\s*=\s*(.+);', clean)
                            if assign_match:
                                result['assignment'] = clean.strip()
                            result['line'] = line.rstrip('\n')
                    
                    results.append(result)
                else:
                    # Fallback: look for goto_symex return value
                    return_key = ('return_value', callee, version, target_is_mutant)
                    if return_key in ssa_vars:
                        ssa_info = ssa_vars[return_key]
                        result = derived.copy()
                        result['ssa_variable_name'] = ssa_info['full_ssa_name']
                        result['is_mutant'] = target_is_mutant
                        
                        # Extract return statement from source if available
                        if c_file_path and 'source_line' in derived:
                            source_lines = read_c_source(c_file_path)
                            line_num = derived['source_line']
                            if 0 < line_num <= len(source_lines):
                                line = source_lines[line_num - 1]
                                clean = strip_comments(line)
                                return_match = re.match(r'^\s*return\s+(.+);', clean)
                                if return_match:
                                    result['assignment'] = f"return {return_match.group(1).strip()};"
                                result['line'] = line.rstrip('\n')
                        
                        results.append(result)
    
    return results


def get_ssa_variables_for_assertions(
    c_file_path: str,
    smt2_file_path: str,
    only_diff_variables: bool = True
) -> Dict[str, List[Dict]]:
    """
    Get SSA variable names for assertions, using the same logic as get_ssa_versions_for_file.
    
    Args:
        c_file_path: Path to C source file
        smt2_file_path: Path to corresponding SMT2 file
        only_diff_variables: If True, only include variables that differ
        
    Returns:
        Dictionary with 'source' and 'mutant' keys, each containing lists of
        SSA variable mappings matching the format of get_ssa_versions_for_file
    """
    # Use the same logic as the existing analysis
    from . import get_ssa_versions_for_file
    from .parser import read_c_source
    
    # Get SSA results using existing logic
    ssa_results = get_ssa_versions_for_file(c_file_path)
    
    # Extract SSA variables from SMT2 file
    ssa_vars = extract_ssa_variables_from_smt2(smt2_file_path)
    
    source_lines = read_c_source(c_file_path)
    
    source_ssa = []
    mutant_ssa = []
    
    # Process each diff variable
    for (func_name, var_name), data in ssa_results.items():
        mut_func_name = data.get('mutant_function')
        
        # Process source SSA versions
        for ssa_entry in data.get('source_ssa', []):
            version = ssa_entry.get('version', 0)
            ssa_name = ssa_entry.get('ssa_name', '')
            
            # Look up in SMT2 file
            # For regular variables: func_name::1::var_name!0@1#version
            # For return values: goto_symex::return_value::func_name!0#version
            if var_name == 'return':
                key = ('return_value', func_name, version, False)
            else:
                key = (func_name, var_name, version, False)
            
            # Try to find matching SSA variable in SMT2 file
            # Match by function, variable, version (ignore @N part)
            found_ssa = None
            for ssa_key, ssa_info in ssa_vars.items():
                if (ssa_key[0] == func_name and 
                    ssa_key[1] == var_name and 
                    ssa_key[2] == version and 
                    ssa_key[3] == False):
                    found_ssa = ssa_info
                    break
            
            if found_ssa:
                source_ssa.append({
                    'function': func_name,
                    'variable': var_name,
                    'ssa_variable_name': found_ssa['full_ssa_name'],
                    'version': version,
                    'assignment': ssa_entry.get('assignment', ''),
                    'line': ssa_entry.get('line', ''),
                    'is_mutant': False
                })
            else:
                # Fallback: use the SSA name from entry (from get_ssa_versions_for_file)
                source_ssa.append({
                    'function': func_name,
                    'variable': var_name,
                    'ssa_variable_name': f"|{ssa_name}|",
                    'version': version,
                    'assignment': ssa_entry.get('assignment', ''),
                    'line': ssa_entry.get('line', ''),
                    'is_mutant': False
                })
        
        # Process mutant SSA versions
        for ssa_entry in data.get('mutant_ssa', []):
            version = ssa_entry.get('version', 0)
            ssa_name = ssa_entry.get('ssa_name', '')
            
            # Try to find matching SSA variable in SMT2 file
            found_ssa = None
            for ssa_key, ssa_info in ssa_vars.items():
                if var_name == 'return':
                    # For return values, match by return_value, function name, version
                    if (ssa_key[0] == 'return_value' and 
                        ssa_key[1] == func_name and 
                        ssa_key[2] == version and 
                        ssa_key[3] == True):
                        found_ssa = ssa_info
                        break
                else:
                    # For regular variables, match by function, variable, version
                    if (ssa_key[0] == func_name and 
                        ssa_key[1] == var_name and 
                        ssa_key[2] == version and 
                        ssa_key[3] == True):
                        found_ssa = ssa_info
                        break
            
            if found_ssa:
                # Use SSA name from SMT2 file, but preserve predicate pair from entry
                pair = ssa_entry.get('missing_predicate_pair')
                # Update predicate pair to use SSA names from SMT2 if available
                if pair:
                    p_src, p_mut = pair
                    # Try to find source SSA name for predicate pair
                    src_ssa_name = None
                    for src_entry in data.get('source_ssa', []):
                        if src_entry.get('version') == version:
                            src_ssa_name = src_entry.get('ssa_name', '')
                            break
                    if src_ssa_name:
                        # Use the SSA name from get_ssa_versions_for_file for predicate pair
                        pair = (src_ssa_name, ssa_name)
                
                mutant_ssa.append({
                    'function': func_name,
                    'variable': var_name,
                    'ssa_variable_name': found_ssa['full_ssa_name'],
                    'version': version,
                    'assignment': ssa_entry.get('assignment', ''),
                    'line': ssa_entry.get('line', ''),
                    'is_mutant': True,
                    'missing_predicate_pair': pair
                })
            else:
                # Fallback: use the SSA name from entry
                mutant_ssa.append({
                    'function': func_name,
                    'variable': var_name,
                    'ssa_variable_name': f"|{ssa_name}|",
                    'version': version,
                    'assignment': ssa_entry.get('assignment', ''),
                    'line': ssa_entry.get('line', ''),
                    'is_mutant': True,
                    'missing_predicate_pair': ssa_entry.get('missing_predicate_pair')
                })
    
    return {
        'source': source_ssa,
        'mutant': mutant_ssa
    }

