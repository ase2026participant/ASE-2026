"""
Selective RDA Analysis Pipeline for Assertion Generation.

This module implements a pipeline that:
1. Classifies function-variable pairs into categories
2. Routes simple cases to direct assertion generation
3. Routes asymmetric cases to RDA analysis with compliance checking
4. Ignores other cases with appropriate messages

All functions are side-effect free (pure functions).
"""

import re
from typing import Dict, List, Tuple, Any, Optional, Set
from .parser import (
    read_c_source, build_function_map, extract_assignments,
    normalize_identifiers, strip_comments
)
from .diff_finder import expand_macros_in_expression
from .rda_ssa_generator import (
    get_ssa_versions_for_pairs_rda,
    verify_ssa_reaches_assertion,
    verify_predicate_ssa_reaches,
    extract_variable_uses
)
from .ssa_generator import (
    get_unique_function_variable_pairs,
    extract_global_variables,
    resolve_all_variables_to_ssa
)
from .diff_finder import (
    get_macros_from_source,
    get_macro_tuples,
    build_macro_map
)


def _build_ssa_environment_for_function(
    func_lines: List[str],
    func_name: str,
    global_vars: Set[str],
    macro_map: Dict[str, str],
    is_mutant: bool = False
) -> Dict[str, str]:
    """
    Build SSA environment for all variables in a function.
    
    Pure function: Creates new data structures, no side effects.
    
    Args:
        func_lines: Function body lines
        func_name: Function name
        global_vars: Set of global variable names
        macro_map: Macro mapping dictionary
        is_mutant: Whether this is a mutant function
        
    Returns:
        Dictionary mapping variable names to their SSA versions
    """
    ssa_env = {}
    ASSIGN_RE = re.compile(r'^\s*(\w+)\s*=\s*(.+);')
    
    # Track version numbers for each variable
    var_versions = {}
    
    for idx, line in enumerate(func_lines):
        clean = strip_comments(line)
        match = ASSIGN_RE.match(clean)
        if match:
            lhs = match.group(1)
            normalized_lhs = normalize_identifiers(lhs)
            
            # Determine initial version (2 for regular vars, 1 for return/if_condition)
            if normalized_lhs not in var_versions:
                var_versions[normalized_lhs] = 2
            else:
                var_versions[normalized_lhs] += 1
            
            version = var_versions[normalized_lhs]
            ssa_name = f"{func_name}::1::{lhs}!0@1#{version}"
            
            # Store both original and normalized names
            ssa_env[lhs] = ssa_name
            ssa_env[normalized_lhs] = ssa_name
    
    # Add global variables
    for global_var in global_vars:
        for suffix in ['', '_2'] if is_mutant else ['']:
            var_name = f"{global_var}{suffix}"
            ssa_env[var_name] = f"{var_name}#2"
            normalized_var = normalize_identifiers(var_name)
            ssa_env[normalized_var] = f"{var_name}#2"
    
    return ssa_env


def extract_assignments_for_variable(func_lines: List[str], var_name: str) -> List[Dict]:
    """
    Extract assignments for a specific variable from function lines.
    
    Handles:
    - Regular assignments: x = ...
    - Return statements: return ... (for var_name == 'return')
    - If conditions: if (...) (for var_name starting with 'if_condition')
    
    Pure function: Creates new data structures, no side effects.
    
    Args:
        func_lines: Function body lines
        var_name: Variable name to extract assignments for
        
    Returns:
        List of assignment dictionaries with 'lhs', 'rhs', 'line', 'line_index'
    """
    assignments = []
    ASSIGN_RE = re.compile(r'^\s*(\w+)\s*=\s*(.+);')
    RETURN_RE = re.compile(r'^\s*return\s+(.+);')
    IF_RE = re.compile(r'^\s*if\s*\((.+)\)')
    
    normalized_var = normalize_identifiers(var_name)
    
    # Handle return statements
    if normalized_var == 'return':
        for idx, line in enumerate(func_lines):
            match = RETURN_RE.match(strip_comments(line))
            if match:
                assignments.append({
                    'lhs': 'return',
                    'rhs': match.group(1),
                    'line': line.strip(),
                    'line_index': idx
                })
        return assignments
    
    # Handle if_condition variables
    if var_name.startswith('if_condition'):
        # Extract condition number from var_name (e.g., 'if_condition_2' -> 2)
        condition_num_match = re.search(r'if_condition_(\d+)', var_name)
        condition_num = condition_num_match.group(1) if condition_num_match else None
        
        if_count = 0
        for idx, line in enumerate(func_lines):
            match = IF_RE.match(strip_comments(line))
            if match:
                if_count += 1
                # Match the specific condition number
                if condition_num is None or if_count == int(condition_num):
                    assignments.append({
                        'lhs': var_name,
                        'rhs': match.group(1),
                        'line': line.strip(),
                        'line_index': idx
                    })
        return assignments
    
    # Handle regular assignments
    for idx, line in enumerate(func_lines):
        match = ASSIGN_RE.match(strip_comments(line))
        if match:
            lhs = match.group(1)
            rhs = match.group(2)
            
            # Normalize for comparison
            normalized_lhs = normalize_identifiers(lhs)
            
            if normalized_lhs == normalized_var:
                assignments.append({
                    'lhs': lhs,
                    'rhs': rhs,
                    'line': line.strip(),
                    'line_index': idx
                })
    
    return assignments


def has_cascading_effects(
    var_name: str,
    src_func_lines: List[str],
    mut_func_lines: List[str]
) -> bool:
    """
    Check if changed variable is used in other assignments (cascading effects).
    
    Pure function: No side effects.
    
    Returns True if:
    - Variable is used in RHS of other assignments
    - Variable affects return statements
    - Variable is used in conditions
    """
    all_lines = src_func_lines + mut_func_lines
    
    # Extract all assignments
    ASSIGN_RE = re.compile(r'^\s*(\w+)\s*=\s*(.+);')
    RETURN_RE = re.compile(r'^\s*return\s+(.+);')
    IF_RE = re.compile(r'^\s*if\s*\((.+)\)')
    
    normalized_var = normalize_identifiers(var_name)
    
    for line in all_lines:
        clean = strip_comments(line)
        
        # Check RHS of assignments
        assign_match = ASSIGN_RE.match(clean)
        if assign_match:
            rhs = assign_match.group(2)
            used_vars = extract_variable_uses(rhs)
            if any(normalize_identifiers(v) == normalized_var for v in used_vars):
                return True
        
        # Check return statements
        return_match = RETURN_RE.match(clean)
        if return_match:
            ret_expr = return_match.group(1)
            used_vars = extract_variable_uses(ret_expr)
            if any(normalize_identifiers(v) == normalized_var for v in used_vars):
                return True
        
        # Check conditions
        if_match = IF_RE.match(clean)
        if if_match:
            cond_expr = if_match.group(1)
            used_vars = extract_variable_uses(cond_expr)
            if any(normalize_identifiers(v) == normalized_var for v in used_vars):
                return True
    
    return False


def affects_control_flow(
    src_assign: Dict,
    mut_assign: Dict,
    src_func_lines: List[str],
    mut_func_lines: List[str]
) -> bool:
    """
    Check if assignment differences affect control flow.
    
    Pure function: No side effects.
    
    Returns True if:
    - Assignments are in different blocks
    - Assignments affect condition variables
    """
    # Simple check: if assignments are at different line positions relative to if statements
    # This is a simplified check - full CFG analysis would be more accurate
    
    src_line_idx = src_assign.get('line_index', -1)
    mut_line_idx = mut_assign.get('line_index', -1)
    
    if src_line_idx < 0 or mut_line_idx < 0:
        return False
    
    # Check if variable is used in conditions
    src_var = normalize_identifiers(src_assign.get('lhs', ''))
    
    IF_RE = re.compile(r'^\s*if\s*\((.+)\)')
    for line in src_func_lines + mut_func_lines:
        match = IF_RE.match(strip_comments(line))
        if match:
            cond_expr = match.group(1)
            used_vars = extract_variable_uses(cond_expr)
            if any(normalize_identifiers(v) == src_var for v in used_vars):
                return True
    
    return False


def classify_pair_complexity(
    src_assignments: List[Dict],
    mut_assignments: List[Dict],
    src_func_lines: List[str],
    mut_func_lines: List[str]
) -> Tuple[str, str]:
    """
    Classify a function-variable pair into one of four categories.
    
    Pure function: Creates new data structures, no side effects.
    
    Returns:
        (category: str, reason: str)
        Categories:
        - 'simple': 1↔1, same variable, no cascading effects
        - 'asymmetric_1': 1↔multiple (missing statements in source)
        - 'asymmetric_2': multiple↔1 (missing statements in mutant)
        - 'ignore': Other cases
    """
    src_count = len(src_assignments)
    mut_count = len(mut_assignments)
    
    # Simple case: Both have exactly 1 assignment
    if src_count == 1 and mut_count == 1:
        src_var = normalize_identifiers(src_assignments[0].get('lhs', ''))
        mut_var = normalize_identifiers(mut_assignments[0].get('lhs', ''))
        
        if src_var == mut_var:
            if not has_cascading_effects(src_var, src_func_lines, mut_func_lines):
                if not affects_control_flow(src_assignments[0], mut_assignments[0], 
                                           src_func_lines, mut_func_lines):
                    return 'simple', "Single line change, same variable, no cascading effects"
    
    # Asymmetric Case 1: Source has 1, Mutant has multiple
    if src_count == 1 and mut_count > 1:
        return 'asymmetric_1', f"Source has 1 assignment, Mutant has {mut_count} assignments"
    
    # Asymmetric Case 2: Source has multiple, Mutant has 1
    if src_count > 1 and mut_count == 1:
        return 'asymmetric_2', f"Source has {src_count} assignments, Mutant has 1 assignment"
    
    # Multiple assignments on both sides: Treat as asymmetric (need RDA to track which definitions reach)
    # If counts differ, it's asymmetric; if same count but different assignments, still need RDA
    if src_count > 1 and mut_count > 1:
        if src_count != mut_count:
            # Different counts - asymmetric
            if src_count < mut_count:
                return 'asymmetric_1', f"Source has {src_count} assignments, Mutant has {mut_count} assignments"
            else:
                return 'asymmetric_2', f"Source has {src_count} assignments, Mutant has {mut_count} assignments"
        else:
            # Same count but multiple assignments - need RDA to track data-flow
            return 'asymmetric_1', f"Multiple assignments on both sides (src: {src_count}, mut: {mut_count}) - requires RDA"
    
    # 1↔1 but different variables or cascading effects: Treat as asymmetric (need RDA)
    if src_count == 1 and mut_count == 1:
        src_var = normalize_identifiers(src_assignments[0].get('lhs', ''))
        mut_var = normalize_identifiers(mut_assignments[0].get('lhs', ''))
        if src_var != mut_var:
            return 'asymmetric_1', f"Different variables changed (src: {src_var}, mut: {mut_var}) - requires RDA"
        
        # Same variable but has cascading effects - need RDA
        if has_cascading_effects(src_var, src_func_lines, mut_func_lines):
            return 'asymmetric_1', f"Variable {src_var} has cascading effects - requires RDA"
        
        # Same variable but affects control flow - need RDA
        if affects_control_flow(src_assignments[0], mut_assignments[0], src_func_lines, mut_func_lines):
            return 'asymmetric_1', f"Variable {src_var} affects control flow - requires RDA"
    
    # Edge case: one side has zero assignments
    if src_count == 0 or mut_count == 0:
        if src_count == 0 and mut_count > 0:
            return 'asymmetric_1', f"Variable missing in source, present in mutant ({mut_count} assignments)"
        elif src_count > 0 and mut_count == 0:
            return 'asymmetric_2', f"Variable present in source ({src_count} assignments), missing in mutant"
    
    return 'ignore', f"Unsupported case (src: {src_count}, mut: {mut_count})"


def generate_simple_assertion(
    src_assignment: Dict,
    mut_assignment: Dict,
    func_name: str,
    var_name: str,
    src_ssa_name: Optional[str] = None,
    mut_ssa_name: Optional[str] = None,
    src_ssa_env: Optional[Dict[str, str]] = None,
    mut_ssa_env: Optional[Dict[str, str]] = None,
    global_vars: Optional[Set[str]] = None
) -> Dict:
    """
    Generate assertion directly for simple case without RDA.
    
    Pure function: Creates new data structures, no side effects.
    
    Args:
        src_assignment: Source assignment dictionary
        mut_assignment: Mutant assignment dictionary
        func_name: Function name
        var_name: Variable name
        src_ssa_name: Optional pre-computed SSA name for source
        mut_ssa_name: Optional pre-computed SSA name for mutant
        src_ssa_env: Optional SSA environment for source (for resolving if_condition variables)
        mut_ssa_env: Optional SSA environment for mutant (for resolving if_condition variables)
        global_vars: Optional set of global variables
        
    Returns:
        Dictionary with assertion information
    """
    # Special handling for if_condition variables: resolve condition expressions to actual SSA variables
    if var_name.startswith('if_condition'):
        src_condition_expr = src_assignment.get('rhs', '')
        mut_condition_expr = mut_assignment.get('rhs', '')
        
        # Resolve variables in condition expressions to their actual SSA versions
        if src_ssa_env and global_vars is not None:
            src_predicate = resolve_all_variables_to_ssa(src_condition_expr, src_ssa_env, global_vars)
        else:
            src_predicate = src_condition_expr
        
        if mut_ssa_env and global_vars is not None:
            mut_predicate = resolve_all_variables_to_ssa(mut_condition_expr, mut_ssa_env, global_vars)
        else:
            mut_predicate = mut_condition_expr
        
        # Use resolved expressions as predicate pair
        predicate_pair = (src_predicate, mut_predicate)
        assertion = f"({src_predicate} ≠ {mut_predicate}) ⇒ (final_src ≠ final_mut)"
        
        return {
            'type': 'simple',
            'category': 'simple',
            'function': func_name,
            'variable': var_name,
            'predicate_pair': predicate_pair,
            'assertion': assertion,
            'source_ssa': [{
                **src_assignment,
                'ssa_name': src_predicate,  # Use resolved expression
                'version': 2
            }],
            'mutant_ssa': [{
                **mut_assignment,
                'ssa_name': mut_predicate,  # Use resolved expression
                'version': 2
            }],
            'reason': 'Direct assertion generation for simple case (if_condition resolved to actual SSA variables)'
        }
    
    # Regular variables: Use provided SSA names or generate simple ones
    if not src_ssa_name:
        src_ssa_name = f"{func_name}::1::{var_name}!0@1#2"
    if not mut_ssa_name:
        mut_func_name = f"{func_name}_2"
        mut_ssa_name = f"{mut_func_name}::1::{var_name}_2!0@1#2"
    
    # Generate predicate pair
    predicate_pair = (src_ssa_name, mut_ssa_name)
    
    # Generate assertion
    assertion = f"({src_ssa_name} ≠ {mut_ssa_name}) ⇒ (final_src ≠ final_mut)"
    
    return {
        'type': 'simple',
        'category': 'simple',
        'function': func_name,
        'variable': var_name,
        'predicate_pair': predicate_pair,
        'assertion': assertion,
        'source_ssa': [{
            **src_assignment,
            'ssa_name': src_ssa_name,
            'version': 2
        }],
        'mutant_ssa': [{
            **mut_assignment,
            'ssa_name': mut_ssa_name,
            'version': 2
        }],
        'reason': 'Direct assertion generation for simple case'
    }


def validate_rda_compliant_results(
    rda_data: Dict,
    pair: Dict,
    global_vars: Set[str],
    src_func_lines: List[str],
    mut_func_lines: List[str],
    src_assignments_all: List[Dict],
    mut_assignments_all: List[Dict]
) -> Tuple[bool, List[str]]:
    """
    Validate that RDA results are compliant.
    
    Pure function: No side effects.
    
    Checks:
    1. All SSA versions reach their assertion points
    2. No verification warnings
    
    Returns:
        (is_compliant: bool, violations: List[str])
    """
    violations = []
    
    # Check 1: SSA versions reach assertion points
    for stmt in rda_data.get('source_ssa', []):
        if '_verification_warning' in stmt:
            violations.append(f"Source SSA {stmt.get('ssa_name')} may not reach assertion point")
        else:
            # Verify explicitly
            if not verify_ssa_reaches_assertion(stmt, src_assignments_all, src_func_lines, global_vars):
                violations.append(f"Source SSA {stmt.get('ssa_name')} does not reach assertion point")
    
    for stmt in rda_data.get('mutant_ssa', []):
        if '_verification_warning' in stmt:
            violations.append(f"Mutant SSA {stmt.get('ssa_name')} may not reach assertion point")
        else:
            # Verify explicitly
            if not verify_ssa_reaches_assertion(stmt, mut_assignments_all, mut_func_lines, global_vars):
                violations.append(f"Mutant SSA {stmt.get('ssa_name')} does not reach assertion point")
    
    # Check 2: Condition predicate pairs reach
    for pair_tuple in rda_data.get('condition_predicate_pairs', []):
        src_pred, mut_pred = pair_tuple
        if not verify_predicate_ssa_reaches(src_pred, src_assignments_all, src_func_lines, global_vars):
            violations.append(f"Source predicate {src_pred} contains SSA that doesn't reach")
        if not verify_predicate_ssa_reaches(mut_pred, mut_assignments_all, mut_func_lines, global_vars):
            violations.append(f"Mutant predicate {mut_pred} contains SSA that doesn't reach")
    
    return len(violations) == 0, violations


def extract_predicate_pairs(rda_data: Dict) -> List[Tuple[str, str]]:
    """
    Extract predicate pairs from RDA data.
    
    Pure function: Creates new data structures, no side effects.
    """
    pairs = []
    
    # Extract from missing_predicate_pair
    for stmt in rda_data.get('source_ssa', []) + rda_data.get('mutant_ssa', []):
        if 'missing_predicate_pair' in stmt:
            pair = stmt['missing_predicate_pair']
            if isinstance(pair, tuple) and len(pair) == 2:
                pairs.append(pair)
    
    # Extract condition predicate pairs
    pairs.extend(rda_data.get('condition_predicate_pairs', []))
    
    return pairs


def generate_assertions_from_rda(rda_data: Dict) -> List[str]:
    """
    Generate assertion strings from RDA data.
    
    Pure function: Creates new data structures, no side effects.
    """
    assertions = []
    
    # Generate from predicate pairs
    predicate_pairs = extract_predicate_pairs(rda_data)
    
    for p_src, p_mut in predicate_pairs:
        assertion = f"({p_src} ≠ {p_mut}) ⇒ (final_src ≠ final_mut)"
        assertions.append(assertion)
    
    return assertions


def process_asymmetric_with_rda(
    pair: Dict,
    c_file_path: str,
    category: str,
    func_map: Dict[str, List[str]],
    global_vars: Set[str],
    macro_map: Dict[str, str]
) -> Optional[Dict]:
    """
    Process asymmetric case using RDA analysis.
    
    Pure function: Creates new data structures, no side effects.
    
    Returns:
        Dictionary with assertion information if RDA-compliant, None otherwise
    """
    # Run RDA analysis on the pair
    rda_results = get_ssa_versions_for_pairs_rda([pair], c_file_path)
    
    # Extract results for this pair
    func_name = pair['function']
    var_name = pair['variable_name']
    key = (func_name, var_name)
    
    if key not in rda_results:
        return None
    
    rda_data = rda_results[key]
    
    # Get all assignments for validation
    src_func_lines = func_map.get(func_name, [])
    mut_func_name = pair.get('mutant_function')
    mut_func_lines = func_map.get(mut_func_name, []) if mut_func_name else []
    
    # Extract all assignments (not just for this variable)
    ASSIGN_RE = re.compile(r'^\s*(\w+)\s*=\s*(.+);')
    src_assignments_all = []
    mut_assignments_all = []
    
    for idx, line in enumerate(src_func_lines):
        match = ASSIGN_RE.match(strip_comments(line))
        if match:
            src_assignments_all.append({
                'lhs': match.group(1),
                'rhs': match.group(2),
                'line': line.strip(),
                'line_index': idx
            })
    
    for idx, line in enumerate(mut_func_lines):
        match = ASSIGN_RE.match(strip_comments(line))
        if match:
            mut_assignments_all.append({
                'lhs': match.group(1),
                'rhs': match.group(2),
                'line': line.strip(),
                'line_index': idx
            })
    
    # Check RDA compliance
    is_compliant, violations = validate_rda_compliant_results(
        rda_data, pair, global_vars,
        src_func_lines, mut_func_lines,
        src_assignments_all, mut_assignments_all
    )
    
    if not is_compliant:
        # Not RDA-compliant - return None
        return None
    
    # Generate assertions from RDA results
    assertions = generate_assertions_from_rda(rda_data)
    predicate_pairs = extract_predicate_pairs(rda_data)
    
    return {
        'type': 'rda',
        'category': category,
        'function': func_name,
        'variable': var_name,
        'rda_compliant': True,
        'predicate_pairs': predicate_pairs,
        'assertions': assertions,
        'source_ssa': rda_data.get('source_ssa', []),
        'mutant_ssa': rda_data.get('mutant_ssa', []),
        'condition_predicate_pairs': rda_data.get('condition_predicate_pairs', []),
        'violations': []
    }


def handle_ignore_case(
    pair: Dict,
    reason: str
) -> Dict:
    """
    Handle cases that should be ignored.
    
    Pure function: Creates new data structures, no side effects.
    """
    func_name = pair['function']
    var_name = pair['variable_name']
    
    message = (
        f"[IGNORE] Function: {func_name}, Variable: {var_name}\n"
        f"  Reason: {reason}\n"
        f"  Action: Skipping assertion generation for this pair\n"
    )
    
    return {
        'type': 'ignore',
        'reason': reason,
        'message': message,
        'function': func_name,
        'variable': var_name
    }


def generate_assertions_pipeline(
    pairs: List[Dict],
    c_file_path: str
) -> Dict[str, Any]:
    """
    Main pipeline for selective assertion generation.
    
    Pure function: Creates new data structures, no side effects.
    
    Pipeline:
    1. Classify each pair
    2. Route to appropriate handler:
       - Simple → Direct assertion generation
       - Asymmetric → RDA analysis → Compliance check → Assertion generation
       - Ignore → Print ignore message
    3. Collect all results
    
    Returns:
        Dictionary with:
        {
            'simple_assertions': [...],
            'rda_assertions': [...],
            'ignored': [...],
            'summary': {...}
        }
    """
    results = {
        'simple_assertions': [],
        'rda_assertions': [],
        'ignored': [],
        'summary': {
            'total': len(pairs),
            'simple': 0,
            'asymmetric_1': 0,
            'asymmetric_2': 0,
            'ignored': 0,
            'rda_compliant': 0,
            'rda_non_compliant': 0
        }
    }
    
    # Read function lines once
    source_lines = read_c_source(c_file_path)
    func_map = build_function_map(source_lines)
    
    # Extract globals and macros once
    global_vars = extract_global_variables(c_file_path)
    macros = get_macros_from_source(source_lines)
    macro_tuples = get_macro_tuples(macros)
    macro_map = build_macro_map(macro_tuples)
    
    for pair in pairs:
        func_name = pair['function']
        var_name = pair['variable_name']
        
        # Extract assignments for this variable
        src_func_lines = func_map.get(func_name, [])
        mut_func_name = pair.get('mutant_function')
        mut_func_lines = func_map.get(mut_func_name, []) if mut_func_name else []
        
        src_assignments = extract_assignments_for_variable(src_func_lines, var_name)
        mut_assignments = extract_assignments_for_variable(mut_func_lines, var_name)
        
        # Classify pair
        category, reason = classify_pair_complexity(
            src_assignments, mut_assignments,
            src_func_lines, mut_func_lines
        )
        
        # Route to appropriate handler
        if category == 'simple':
            # Simple case: Direct assertion generation
            # For if_condition variables, build SSA environments to resolve condition expressions
            src_ssa_env = None
            mut_ssa_env = None
            
            if var_name.startswith('if_condition'):
                # Build SSA environments for resolving variables in condition expressions
                src_ssa_env = _build_ssa_environment_for_function(
                    src_func_lines, func_name, global_vars, macro_map, is_mutant=False
                )
                mut_ssa_env = _build_ssa_environment_for_function(
                    mut_func_lines, mut_func_name or f"{func_name}_2", global_vars, macro_map, is_mutant=True
                )
            
            assertion = generate_simple_assertion(
                src_assignments[0], mut_assignments[0],
                func_name, var_name,
                src_ssa_env=src_ssa_env,
                mut_ssa_env=mut_ssa_env,
                global_vars=global_vars
            )
            results['simple_assertions'].append(assertion)
            results['summary']['simple'] += 1
            
        elif category in ['asymmetric_1', 'asymmetric_2']:
            # Asymmetric case: RDA analysis
            rda_result = process_asymmetric_with_rda(
                pair, c_file_path, category,
                func_map, global_vars, macro_map
            )
            
            if rda_result and rda_result.get('rda_compliant'):
                # RDA-compliant: Generate assertions
                results['rda_assertions'].append(rda_result)
                results['summary'][category] += 1
                results['summary']['rda_compliant'] += 1
            else:
                # Not RDA-compliant: Ignore
                ignore_result = handle_ignore_case(
                    pair,
                    f"RDA analysis failed or non-compliant for {category}"
                )
                results['ignored'].append(ignore_result)
                results['summary']['ignored'] += 1
                results['summary']['rda_non_compliant'] += 1
                
        else:  # category == 'ignore'
            # Other cases: Ignore with printf
            ignore_result = handle_ignore_case(pair, reason)
            results['ignored'].append(ignore_result)
            results['summary']['ignored'] += 1
    
    return results


def format_pipeline_output(results: Dict[str, Any]) -> str:
    """
    Format pipeline results with appropriate printf statements.
    
    Pure function: Creates new data structures, no side effects.
    """
    lines = []
    
    # Summary
    lines.append("=" * 80)
    lines.append("ASSERTION GENERATION PIPELINE RESULTS")
    lines.append("=" * 80)
    lines.append("")
    
    summary = results['summary']
    lines.append(f"Total pairs: {summary['total']}")
    lines.append(f"  Simple cases (direct): {summary['simple']}")
    lines.append(f"  Asymmetric Case 1 (1↔multiple): {summary['asymmetric_1']}")
    lines.append(f"  Asymmetric Case 2 (multiple↔1): {summary['asymmetric_2']}")
    lines.append(f"  RDA-compliant: {summary['rda_compliant']}")
    lines.append(f"  RDA-non-compliant: {summary['rda_non_compliant']}")
    lines.append(f"  Ignored: {summary['ignored']}")
    lines.append("")
    
    # Simple assertions
    if results['simple_assertions']:
        lines.append("=" * 80)
        lines.append("SIMPLE ASSERTIONS (Direct Generation)")
        lines.append("=" * 80)
        for assertion in results['simple_assertions']:
            lines.append(f"Function: {assertion['function']}, Variable: {assertion['variable']}")
            lines.append(f"  Assertion: {assertion['assertion']}")
            lines.append(f"  Predicate Pair: {assertion['predicate_pair']}")
            lines.append("")
    
    # RDA assertions
    if results['rda_assertions']:
        lines.append("=" * 80)
        lines.append("RDA-COMPLIANT ASSERTIONS")
        lines.append("=" * 80)
        for assertion in results['rda_assertions']:
            lines.append(f"Function: {assertion['function']}, Variable: {assertion['variable']}")
            lines.append(f"  Category: {assertion['category']}")
            for pred_pair in assertion['predicate_pairs']:
                lines.append(f"  Predicate Pair: {pred_pair}")
            for assrt in assertion['assertions']:
                lines.append(f"  Assertion: {assrt}")
            lines.append("")
    
    # Ignored cases (with printf statements)
    if results['ignored']:
        lines.append("=" * 80)
        lines.append("IGNORED CASES")
        lines.append("=" * 80)
        for ignored in results['ignored']:
            lines.append(ignored['message'])
    
    return "\n".join(lines)

