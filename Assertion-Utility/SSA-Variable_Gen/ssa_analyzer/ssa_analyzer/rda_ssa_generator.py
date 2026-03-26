"""
RDA-Compliant SSA Generator.

This module implements traditional Reaching Definition Analysis (RDA) for SSA variables:
- Backward slicing from outputs (return statements)
- Explicit def-use chain construction
- Variable resolution in RHS expressions to reaching definitions
- Control dependency tracking
- Dead code elimination (only definitions that reach outputs)

READ-ONLY analysis only - no side effects.
"""

import re
import sys
import os
from typing import List, Dict, Tuple, Optional, Set

# Handle imports for both module and direct execution
if __name__ == '__main__':
    # Running as script - use absolute imports
    # Add project root to path (two levels up from this file)
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from ssa_analyzer.ssa_analyzer.parser import (
        read_c_source, build_function_map, strip_comments,
        normalize_identifiers, normalize_expr, split_top_level_and
    )
    from ssa_analyzer.ssa_analyzer.diff_finder import (
        get_macros_from_source, get_macro_tuples, find_macro_differences,
        find_function_differences, find_macro_usage, merge_function_and_macro_diffs,
        build_macro_map, expand_macros_in_expression
    )
    from ssa_analyzer.ssa_analyzer.ssa_generator import (
        resolve_globals_to_ssa, resolve_all_variables_to_ssa,
        extract_global_variables, derive_missing_predicate_pair,
        extract_branch_structure, derive_condition_predicate_pairs,
        get_block_for_statement, map_statements_to_blocks,
        find_final_versions_per_block, generate_block_based_predicate_pairs
    )
else:
    # Running as module - use relative imports
    from .parser import (
        read_c_source, build_function_map, strip_comments,
        normalize_identifiers, normalize_expr, split_top_level_and
    )
    from .diff_finder import (
        get_macros_from_source, get_macro_tuples, find_macro_differences,
        find_function_differences, find_macro_usage, merge_function_and_macro_diffs,
        build_macro_map, expand_macros_in_expression
    )
    from .ssa_generator import (
        resolve_globals_to_ssa, resolve_all_variables_to_ssa,
        extract_global_variables, derive_missing_predicate_pair,
        extract_branch_structure, derive_condition_predicate_pairs,
        get_block_for_statement, map_statements_to_blocks,
        find_final_versions_per_block, generate_block_based_predicate_pairs
    )


def extract_variable_uses(expr: str) -> Set[str]:
    """
    Extract all variable names used in an expression.
    
    Pure function: no side effects.
    
    Args:
        expr: Expression string
        
    Returns:
        Set of variable names used in the expression
    """
    # Pattern matches C identifiers (alphanumeric + underscore, starting with letter/underscore)
    identifier_pattern = re.compile(r'\b([A-Za-z_][A-Za-z0-9_]*)\b')
    matches = identifier_pattern.findall(expr)
    
    # Filter out C keywords and function calls
    keywords = {'if', 'else', 'return', 'int', 'char', 'void', 'static', 'const', 
                'true', 'false', 'True', 'False', 'NULL', 'null'}
    
    # Remove function calls (pattern: name(...))
    func_pattern = re.compile(r'\b\w+\s*\(')
    func_calls = set(func_pattern.findall(expr))
    
    # Extract function names from calls
    func_names = set()
    for call in func_calls:
        func_name = call.split('(')[0].strip()
        func_names.add(func_name)
    
    # Filter out keywords and function names
    variables = {m for m in matches if m not in keywords and m not in func_names}
    
    return variables


def find_reaching_definitions(var_name: str, use_line_index: int, 
                              assignments: List[Dict], func_lines: List[str],
                              detect_join_points: bool = True) -> List[Dict]:
    """
    Find all reaching definitions for a variable use at a given line index.
    
    Pure function: no side effects.
    
    This implements RD-compliant analysis that returns ALL definitions that may reach
    the use point, not just the most recent one. This is critical for join points
    where multiple definitions from different branches may reach.
    
    Args:
        var_name: Variable name to find reaching definitions for
        use_line_index: Line index where variable is used
        assignments: List of assignment dictionaries with 'line_index' and 'lhs' fields
        func_lines: Function body lines (for control flow analysis)
        detect_join_points: If True, detects join points and includes definitions from all branches
        
    Returns:
        List of assignment dictionaries for all reaching definitions (may be empty)
    """
    normalized_var = normalize_identifiers(var_name)
    
    # Find all definitions of this variable before the use
    candidate_defs = []
    for assign in assignments:
        assign_lhs = assign.get('lhs', '')
        assign_line_idx = assign.get('line_index', -1)
        
        if assign_line_idx >= 0 and assign_line_idx < use_line_index:
            normalized_lhs = normalize_identifiers(assign_lhs)
            if normalized_lhs == normalized_var:
                candidate_defs.append(assign)
    
    if not candidate_defs:
        return []
    
    # If join point detection is enabled, check if we're at a join point
    if detect_join_points:
        # Detect join points: statements after if-else chains
        # A join point occurs when:
        # 1. The use is after a branch structure (if/else-if/else)
        # 2. Multiple definitions exist in different branches
        
        # Find branch structures before the use
        IF_RE = re.compile(r'^\s*if\s*\(')
        ELSE_RE = re.compile(r'^\s*else\s*[^{]*')
        
        branch_ranges = []  # List of (start_idx, end_idx) for each branch
        brace_depth = 0
        in_branch = False
        branch_start = -1
        
        for idx in range(use_line_index):
            line = func_lines[idx]
            clean = strip_comments(line).strip()
            brace_depth += line.count('{') - line.count('}')
            
            if IF_RE.match(clean):
                if in_branch and branch_start >= 0:
                    # Close previous branch
                    branch_ranges.append((branch_start, idx))
                branch_start = idx
                in_branch = True
            elif ELSE_RE.match(clean) and in_branch:
                # This is an else branch - continue the branch range
                pass
            elif in_branch and brace_depth <= 0:
                # Branch has closed
                if branch_start >= 0:
                    branch_ranges.append((branch_start, idx))
                in_branch = False
                branch_start = -1
        
        # Check if definitions come from different branches
        if branch_ranges:
            defs_by_branch = {}
            for def_stmt in candidate_defs:
                def_idx = def_stmt.get('line_index', -1)
                # Find which branch this definition belongs to
                branch_id = None
                for br_start, br_end in branch_ranges:
                    if br_start <= def_idx < br_end:
                        branch_id = (br_start, br_end)
                        break
                if branch_id:
                    if branch_id not in defs_by_branch:
                        defs_by_branch[branch_id] = []
                    defs_by_branch[branch_id].append(def_stmt)
                else:
                    # Definition is outside branches (main block)
                    if 'main' not in defs_by_branch:
                        defs_by_branch['main'] = []
                    defs_by_branch['main'].append(def_stmt)
            
            # If definitions come from multiple branches, this is a join point
            # Return ALL definitions from all branches
            if len(defs_by_branch) > 1:
                # Join point detected - return all definitions
                result = []
                for branch_defs in defs_by_branch.values():
                    result.extend(branch_defs)
                return result
    
    # Not a join point or join point detection disabled
    # Sort by line index (most recent first) and return all candidates
    # This is conservative - includes all definitions that could reach
    candidate_defs.sort(key=lambda x: x.get('line_index', -1), reverse=True)
    return candidate_defs


def build_def_use_chains(assignments: List[Dict], func_lines: List[str], 
                         global_vars: Set[str]) -> Dict[int, Set[int]]:
    """
    Build def-use chains: map each definition to all its uses.
    
    Pure function: creates new data structures, no side effects.
    
    Args:
        assignments: List of assignment dictionaries with 'line_index', 'lhs', 'rhs'
        func_lines: Function body lines
        global_vars: Set of global variable names
        
    Returns:
        Dictionary mapping definition line index -> set of use line indices
    """
    def_use_map = {}
    
    # For each assignment, find all uses of its LHS variable
    for assign in assignments:
        def_line_idx = assign.get('line_index', -1)
        lhs = assign.get('lhs', '')
        normalized_lhs = normalize_identifiers(lhs)
        
        if def_line_idx < 0:
            continue
        
        uses = set()
        
        # Check all subsequent assignments for uses of this variable
        for other_assign in assignments:
            other_line_idx = other_assign.get('line_index', -1)
            other_rhs = other_assign.get('rhs', '')
            
            if other_line_idx <= def_line_idx:
                continue
            
            # Extract variables used in RHS
            used_vars = extract_variable_uses(other_rhs)
            normalized_used = {normalize_identifiers(v) for v in used_vars}
            
            if normalized_lhs in normalized_used:
                uses.add(other_line_idx)
        
        # Also check return statements
        RETURN_RE = re.compile(r'^\s*return\s+(.+);')
        for idx, line in enumerate(func_lines):
            if idx <= def_line_idx:
                continue
            
            clean = strip_comments(line)
            ret_match = RETURN_RE.match(clean)
            if ret_match:
                ret_expr = ret_match.group(1)
                used_vars = extract_variable_uses(ret_expr)
                normalized_used = {normalize_identifiers(v) for v in used_vars}
                
                if normalized_lhs in normalized_used:
                    uses.add(idx)
        
        if uses:
            def_use_map[def_line_idx] = uses
    
    return def_use_map


def backward_slice_from_outputs(assignments: List[Dict], func_lines: List[str],
                                global_vars: Set[str]) -> Set[int]:
    """
    Perform backward slicing from outputs (return statements) to find all relevant definitions.
    
    Pure function: creates new data structures, no side effects.
    
    Args:
        assignments: List of assignment dictionaries
        func_lines: Function body lines
        global_vars: Set of global variable names
        
    Returns:
        Set of line indices for definitions that reach outputs
    """
    RETURN_RE = re.compile(r'^\s*return\s+(.+);')
    
    # Find all return statements (outputs)
    output_indices = set()
    for idx, line in enumerate(func_lines):
        clean = strip_comments(line)
        ret_match = RETURN_RE.match(clean)
        if ret_match:
            output_indices.add(idx)
    
    if not output_indices:
        # No return statements - include all assignments
        return {assign.get('line_index', -1) for assign in assignments if assign.get('line_index', -1) >= 0}
    
    # Build def-use chains
    def_use_map = build_def_use_chains(assignments, func_lines, global_vars)
    
    # Start from outputs and traverse backward
    relevant_defs = set()
    worklist = list(output_indices)
    visited = set()
    
    while worklist:
        use_idx = worklist.pop()
        if use_idx in visited:
            continue
        visited.add(use_idx)
        
        # Find definitions that reach this use
        for def_idx, use_set in def_use_map.items():
            if use_idx in use_set:
                if def_idx not in relevant_defs:
                    relevant_defs.add(def_idx)
                    # Add this definition's uses to worklist
                    worklist.extend(def_use_map.get(def_idx, []))
        
        # Also check if this use is a return statement - find variables in return expression
        if use_idx < len(func_lines):
            line = func_lines[use_idx]
            clean = strip_comments(line)
            ret_match = RETURN_RE.match(clean)
            if ret_match:
                ret_expr = ret_match.group(1)
                used_vars = extract_variable_uses(ret_expr)
                
                # Find reaching definitions for each used variable
                for var_name in used_vars:
                    reaching_defs = find_reaching_definitions(var_name, use_idx, assignments, func_lines, detect_join_points=True)
                    for reaching_def in reaching_defs:
                        def_idx = reaching_def.get('line_index', -1)
                        if def_idx >= 0:
                            relevant_defs.add(def_idx)
                            # Add this definition's uses to worklist
                            worklist.extend(def_use_map.get(def_idx, []))
    
    return relevant_defs


def verify_ssa_reaches_assertion(stmt: Dict, all_assignments: List[Dict], 
                                 func_lines: List[str], global_vars: Set[str]) -> bool:
    """
    Verify that the SSA version in a statement actually reaches the assertion point.
    
    This checks if the SSA version assigned to a statement is valid at the point
    where it would be used in an assertion (typically at function exit or return).
    
    Pure function: no side effects.
    
    Args:
        stmt: Statement dictionary with 'ssa_name', 'line_index'
        all_assignments: All assignments in the function
        func_lines: Function body lines
        global_vars: Set of global variable names
        
    Returns:
        True if SSA version reaches assertion point, False otherwise
    """
    ssa_name = stmt.get('ssa_name')
    stmt_line_idx = stmt.get('line_index', -1)
    
    if not ssa_name or stmt_line_idx < 0:
        return False
    
    # Extract variable name from SSA name (e.g., "func::1::x!0@1#2" -> "x")
    # SSA name format: func_name::1::var_name!0@1#version
    ssa_parts = ssa_name.split('::')
    if len(ssa_parts) >= 3:
        var_part = ssa_parts[2].split('!')[0]  # Extract "var_name" from "var_name!0@1#2"
    else:
        # Fallback: try to extract from SSA name directly
        var_part = ssa_name.split('#')[0].split('!')[0]
        if '::' in var_part:
            var_part = var_part.split('::')[-1]
    
    # Find the definition that creates this SSA version
    def_stmt = None
    for assign in all_assignments:
        if assign.get('ssa_name') == ssa_name:
            def_stmt = assign
            break
    
    if not def_stmt:
        # SSA version not found in assignments - might be global or initial value
        return True  # Assume valid for globals/initial values
    
    def_line_idx = def_stmt.get('line_index', -1)
    if def_line_idx < 0:
        return False
    
    # Check if this definition reaches any output (return statement or function end)
    RETURN_RE = re.compile(r'^\s*return\s+(.+);')
    
    # Find return statements after this definition
    for idx in range(def_line_idx + 1, len(func_lines)):
        clean = strip_comments(func_lines[idx])
        ret_match = RETURN_RE.match(clean)
        if ret_match:
            # Check if variable is used in return expression
            ret_expr = ret_match.group(1)
            used_vars = extract_variable_uses(ret_expr)
            normalized_var = normalize_identifiers(var_part)
            if normalized_var in {normalize_identifiers(v) for v in used_vars}:
                # Variable is used in return - verify definition reaches
                reaching_defs = find_reaching_definitions(var_part, idx, all_assignments, func_lines, detect_join_points=True)
                for rd in reaching_defs:
                    if rd.get('ssa_name') == ssa_name:
                        return True
    
    # Also check if this is used in any subsequent assignment or condition
    for idx in range(def_line_idx + 1, len(func_lines)):
        clean = strip_comments(func_lines[idx])
        # Check assignments
        ASSIGN_RE = re.compile(r'^\s*(\w+)\s*=\s*(.+);')
        assign_match = ASSIGN_RE.match(clean)
        if assign_match:
            rhs = assign_match.group(2)
            used_vars = extract_variable_uses(rhs)
            normalized_var = normalize_identifiers(var_part)
            if normalized_var in {normalize_identifiers(v) for v in used_vars}:
                reaching_defs = find_reaching_definitions(var_part, idx, all_assignments, func_lines, detect_join_points=True)
                for rd in reaching_defs:
                    if rd.get('ssa_name') == ssa_name:
                        return True
        
        # Check conditions
        IF_RE = re.compile(r'^\s*if\s*\((.+)\)')
        ELSE_IF_RE = re.compile(r'^\s*else\s+if\s*\((.+)\)')
        if_match = IF_RE.match(clean)
        else_if_match = ELSE_IF_RE.match(clean)
        if if_match or else_if_match:
            cond_expr = (if_match.group(1) if if_match else else_if_match.group(1)).strip()
            used_vars = extract_variable_uses(cond_expr)
            normalized_var = normalize_identifiers(var_part)
            if normalized_var in {normalize_identifiers(v) for v in used_vars}:
                reaching_defs = find_reaching_definitions(var_part, idx, all_assignments, func_lines, detect_join_points=True)
                for rd in reaching_defs:
                    if rd.get('ssa_name') == ssa_name:
                        return True
    
    # If no return statement found, assume it reaches function end
    # (conservative - may include definitions that don't actually affect output)
    return True


def verify_predicate_ssa_reaches(predicate: str, all_assignments: List[Dict],
                                 func_lines: List[str], global_vars: Set[str]) -> bool:
    """
    Verify that SSA versions used in a predicate expression actually reach.
    
    Pure function: no side effects.
    
    Args:
        predicate: Predicate expression string (may contain SSA versions)
        all_assignments: All assignments in the function
        func_lines: Function body lines
        global_vars: Set of global variable names
        
    Returns:
        True if all SSA versions in predicate reach, False otherwise
    """
    # Extract SSA versions from predicate (format: "func::1::var!0@1#2")
    # Pattern: identifier with # or :: separators
    ssa_pattern = re.compile(r'\b\w+(?:::\d+::\w+!0@\d+#\d+|\w*#\d+)')
    ssa_matches = ssa_pattern.findall(predicate)
    
    if not ssa_matches:
        # No SSA versions found - might be a simple expression
        return True
    
    # For each SSA version, verify it reaches
    for ssa_name in ssa_matches:
        # Find the assignment that creates this SSA version
        def_stmt = None
        for assign in all_assignments:
            if assign.get('ssa_name') == ssa_name:
                def_stmt = assign
                break
        
        if def_stmt:
            # Verify this definition reaches
            if not verify_ssa_reaches_assertion(def_stmt, all_assignments, func_lines, global_vars):
                return False
    
    return True


def _substitute_ssa_version(result: str, var_name: str, ssa_version: str) -> str:
    """
    Substitute variable name with SSA version in result string.
    
    Pure function: creates new string, no side effects.
    
    Args:
        result: Current result string
        var_name: Variable name to substitute
        ssa_version: SSA version to use
        
    Returns:
        Result string with variable substituted
    """
    if '#' in ssa_version or '::' in ssa_version:
        return re.sub(rf'\b{re.escape(var_name)}\b', ssa_version, result)
    else:
        return re.sub(rf'\b{re.escape(var_name)}\b', f"{var_name}#{ssa_version}", result)


def resolve_rhs_to_ssa(assign: Dict, ssa_env: Dict[str, str], 
                       global_vars: Set[str], assignments: List[Dict],
                       func_lines: List[str]) -> str:
    """
    Resolve all variable uses in RHS expression to their reaching SSA definitions.
    
    Pure function: creates new string, no side effects.
    
    Args:
        assign: Assignment dictionary with 'rhs', 'line_index'
        ssa_env: SSA environment mapping variable names to SSA versions
        global_vars: Set of global variable names
        assignments: List of all assignments (for finding reaching definitions)
        func_lines: Function body lines
        
    Returns:
        RHS expression with all variable uses resolved to their SSA versions
    """
    rhs = assign.get('rhs', '')
    use_line_idx = assign.get('line_index', -1)
    
    # Extract all variable uses from RHS
    used_vars = extract_variable_uses(rhs)
    
    result = rhs
    
    # Resolve each variable use to its reaching definition's SSA version
    for var_name in used_vars:
        # Check if it's a global variable
        normalized_var = normalize_identifiers(var_name)
        is_global = normalized_var in global_vars or var_name in global_vars
        
        if is_global:
            # Global variables use program-wide SSA versions
            ssa_version = ssa_env.get(var_name) or ssa_env.get(normalized_var)
            if ssa_version:
                result = _substitute_ssa_version(result, var_name, ssa_version)
        else:
            # Local variable - find reaching definitions (may be multiple at join points)
            reaching_defs = find_reaching_definitions(var_name, use_line_idx, assignments, func_lines, detect_join_points=True)
            if reaching_defs:
                # At join points, multiple definitions may reach
                # For now, use the most recent one, but mark that multiple exist
                # In full SSA form, this would require a phi-node
                if len(reaching_defs) > 1:
                    # Multiple definitions reach - use most recent but could create phi-node
                    # For now, use most recent (conservative approach)
                    reaching_def = reaching_defs[0]  # Most recent
                    reaching_ssa = reaching_def.get('ssa_name', var_name)
                    # Store information about multiple reaching definitions for verification
                    assign['_multiple_reaching_defs'] = [d.get('ssa_name') for d in reaching_defs]
                else:
                    reaching_def = reaching_defs[0]
                    reaching_ssa = reaching_def.get('ssa_name', var_name)
                result = re.sub(rf'\b{re.escape(var_name)}\b', reaching_ssa, result)
            else:
                # No reaching definition found - use from SSA environment or default
                ssa_version = ssa_env.get(var_name) or ssa_env.get(normalized_var)
                if ssa_version:
                    result = _substitute_ssa_version(result, var_name, ssa_version)
    
    return result


def _extract_regular_assignments(
    func_lines: List[str],
    func_name: str,
    var_name: str,
    start_version: int
) -> Tuple[List[Dict], int]:
    """
    Extract regular variable assignments (var = expr;).
    
    Pure function: creates new data structures, no side effects.
    
    Args:
        func_lines: List of function body lines
        func_name: Function name (for SSA name generation)
        var_name: Variable name to extract assignments for
        start_version: Starting version number
        
    Returns:
        Tuple of (assignments list, next_version number)
    """
    assignments = []
    version = start_version
    ASSIGN_RE = re.compile(r'^\s*(\w+)\s*=\s*(.+);')
    
    for idx, line in enumerate(func_lines):
        clean = strip_comments(line)
        if not clean:
            continue
        
        assign_match = ASSIGN_RE.match(clean)
        if assign_match:
            lhs = assign_match.group(1)
            rhs = assign_match.group(2)
            if normalize_identifiers(lhs) == var_name:
                ssa_name = f"{func_name}::1::{lhs}!0@1#{version}"
                assignments.append({
                    'version': version,
                    'ssa_name': ssa_name,
                    'line': line.rstrip('\n'),
                    'assignment': clean,
                    'lhs': lhs,
                    'rhs': rhs,
                    'line_index': idx
                })
                version += 1
    
    return assignments, version


def _extract_return_statements(
    func_lines: List[str],
    func_name: str,
    start_version: int
) -> Tuple[List[Dict], int]:
    """
    Extract return statements (return expr;).
    
    Pure function: creates new data structures, no side effects.
    
    Args:
        func_lines: List of function body lines
        func_name: Function name (for SSA name generation)
        start_version: Starting version number
        
    Returns:
        Tuple of (assignments list, next_version number)
    """
    assignments = []
    version = start_version
    RETURN_RE = re.compile(r'^\s*return\s+(.+);')
    
    for idx, line in enumerate(func_lines):
        clean = strip_comments(line)
        if not clean:
            continue
        
        ret_match = RETURN_RE.match(clean)
        if ret_match:
            ret_expr = ret_match.group(1).strip()
            ssa_name = f"goto_symex::return_value::{func_name}!0#{version}"
            assignments.append({
                'version': version,
                'ssa_name': ssa_name,
                'line': line.rstrip('\n'),
                'assignment': clean,
                'lhs': 'return',
                'rhs': ret_expr,
                'line_index': idx
            })
            version += 1
    
    return assignments, version


def _extract_if_conditions(
    func_lines: List[str],
    start_version: int
) -> Tuple[List[Dict], int]:
    """
    Extract if/else-if conditions (if (cond) or else if (cond)).
    
    Pure function: creates new data structures, no side effects.
    
    Args:
        func_lines: List of function body lines
        start_version: Starting version number
        
    Returns:
        Tuple of (assignments list, next_version number)
    """
    assignments = []
    version = start_version
    IF_RE = re.compile(r'^\s*if\s*\((.+)\)')
    ELSE_IF_RE = re.compile(r'^\s*else\s+if\s*\((.+)\)')
    
    for idx, line in enumerate(func_lines):
        clean = strip_comments(line)
        if not clean:
            continue
        
        if_match = IF_RE.match(clean)
        else_if_match = ELSE_IF_RE.match(clean)
        if if_match or else_if_match:
            cond_expr = (if_match.group(1) if if_match else else_if_match.group(1)).strip()
            assignments.append({
                'version': version,
                'ssa_name': f"if_condition_{version}",
                'line': line.rstrip('\n'),
                'assignment': clean,
                'lhs': 'if_condition',
                'rhs': cond_expr,
                'line_index': idx
            })
            version += 1
    
    return assignments, version


def extract_assignments_for_variable_rda(
    func_lines: List[str],
    func_name: str,
    var_name: str
) -> List[Dict]:
    """
    Extract all assignments for a specific variable from function lines.
    
    Pure function: creates new data structures, no side effects.
    
    Handles three types of assignments:
    1. Regular variable assignments: `var = expr;`
    2. Return statements: `return expr;` (when var_name == 'return')
    3. If conditions: `if (cond)` or `else if (cond)` (when var_name == 'if_condition_*')
    
    Args:
        func_lines: List of function body lines
        func_name: Function name (for SSA name generation)
        var_name: Variable name to extract assignments for
        
    Returns:
        List of assignment dictionaries with:
        {
            'version': int,
            'ssa_name': str,
            'line': str,
            'assignment': str,
            'lhs': str,
            'rhs': str,
            'line_index': int
        }
    """
    # Determine initial version number
    start_version = 2 if var_name != 'return' and not var_name.startswith('return') and \
                        var_name != 'if_condition' and not var_name.startswith('if_condition') else 1
    
    all_assignments = []
    current_version = start_version
    
    # Extract based on variable type
    if var_name == 'return' or var_name.startswith('return'):
        assignments, current_version = _extract_return_statements(func_lines, func_name, current_version)
        all_assignments.extend(assignments)
    elif var_name == 'if_condition' or var_name.startswith('if_condition'):
        assignments, current_version = _extract_if_conditions(func_lines, current_version)
        all_assignments.extend(assignments)
    else:
        # Regular variable assignments
        assignments, current_version = _extract_regular_assignments(
            func_lines, func_name, var_name, current_version
        )
        all_assignments.extend(assignments)
    
    return all_assignments


def _resolve_assignments_rhs(assignments: List[Dict], ssa_env: Dict[str, str],
                            global_vars: Set[str], func_lines: List[str]) -> None:
    """
    Resolve RHS expressions to SSA versions for a list of assignments.
    
    Pure function: modifies assignments in place by adding 'rhs_resolved' field.
    
    Args:
        assignments: List of assignment dictionaries to resolve
        ssa_env: SSA environment mapping variable names to SSA versions
        global_vars: Set of global variable names
        func_lines: Function body lines
    """
    for assign in assignments:
        rhs_resolved = resolve_rhs_to_ssa(assign, ssa_env, global_vars, assignments, func_lines)
        assign['rhs_resolved'] = rhs_resolved


def _find_condition_dependent_definitions(
    func_lines: List[str],
    assignments: List[Dict]
) -> Set[int]:
    """
    Find definition indices for assignments whose LHS variables are used in condition expressions.
    
    Pure function: creates new data structures, no side effects.
    
    Args:
        func_lines: Function body lines to scan for if/else-if conditions
        assignments: List of assignment dictionaries to check
        
    Returns:
        Set of definition line indices for assignments whose variables are used in conditions
    """
    IF_RE = re.compile(r'^\s*if\s*\((.+)\)')
    ELSE_IF_RE = re.compile(r'^\s*else\s+if\s*\((.+)\)')
    
    # Extract variables used in conditions
    condition_vars = set()
    for idx, line in enumerate(func_lines):
        clean = strip_comments(line)
        if_match = IF_RE.match(clean)
        else_if_match = ELSE_IF_RE.match(clean)
        if if_match or else_if_match:
            cond_expr = (if_match.group(1) if if_match else else_if_match.group(1)).strip()
            used_vars = extract_variable_uses(cond_expr)
            condition_vars.update(used_vars)
    
    # Find definitions of variables used in conditions
    relevant_defs = set()
    for assign in assignments:
        lhs = assign.get('lhs', '')
        normalized_lhs = normalize_identifiers(lhs)
        if normalized_lhs in condition_vars or lhs in condition_vars:
            def_idx = assign.get('line_index', -1)
            if def_idx >= 0:
                relevant_defs.add(def_idx)
    
    return relevant_defs


def _find_relevant_assignments_rda(
    var_name: str,
    src_assignments_all: List[Dict],
    mut_assignments_all: List[Dict],
    src_func_lines: List[str],
    mut_func_lines: List[str],
    global_vars: Set[str]
) -> Tuple[List[Dict], List[Dict]]:
    """
    Find relevant assignments using backward slicing from outputs.
    
    Pure function: creates new data structures, no side effects.
    
    Args:
        var_name: Variable name being analyzed
        src_assignments_all: All source assignments for the variable
        mut_assignments_all: All mutant assignments for the variable
        src_func_lines: Source function lines
        mut_func_lines: Mutant function lines
        global_vars: Set of global variables
        
    Returns:
        Tuple of (relevant_source_assignments, relevant_mutant_assignments)
    """
    # For return statements and if_conditions, always include them (they are outputs themselves)
    if var_name == 'return' or var_name.startswith('return') or \
       var_name == 'if_condition' or var_name.startswith('if_condition'):
        return src_assignments_all, mut_assignments_all
    
    # For regular variables, perform backward slicing
    has_source_assignments = len(src_assignments_all) > 0
    has_mutant_assignments = len(mut_assignments_all) > 0
    
    if not (has_source_assignments or has_mutant_assignments):
        return [], []
    
    # Perform backward slicing from outputs
    src_relevant_defs = backward_slice_from_outputs(src_assignments_all, src_func_lines, global_vars)
    mut_relevant_defs = backward_slice_from_outputs(mut_assignments_all, mut_func_lines, global_vars) if mut_func_lines else set()
    
    # Also find definitions of variables used in conditions (if statements)
    src_relevant_defs.update(_find_condition_dependent_definitions(src_func_lines, src_assignments_all))
    
    if mut_func_lines:
        mut_relevant_defs.update(_find_condition_dependent_definitions(mut_func_lines, mut_assignments_all))
    
    # Filter assignments to those that reach outputs OR are used in conditions
    src_assignments = [a for a in src_assignments_all if a.get('line_index', -1) in src_relevant_defs]
    mut_assignments = [a for a in mut_assignments_all if a.get('line_index', -1) in mut_relevant_defs]
    
    return src_assignments, mut_assignments


def _build_ssa_environment_rda(
    func_lines: List[str],
    func_name: str,
    global_vars: Set[str]
) -> Dict[str, str]:
    """
    Build comprehensive SSA environment for ALL variables in a function.
    
    Pure function: creates new data structures, no side effects.
    
    Args:
        func_lines: Function body lines
        func_name: Function name
        global_vars: Set of global variable names
        
    Returns:
        Dictionary mapping variable names to their SSA versions
    """
    ssa_env = {}
    var_versions = {}  # Track version per variable
    ASSIGN_RE = re.compile(r'^\s*(\w+)\s*=\s*(.+);')
    
    for idx, line in enumerate(func_lines):
        clean = strip_comments(line)
        if not clean:
            continue
        
        assign_match = ASSIGN_RE.match(clean)
        if assign_match:
            lhs = assign_match.group(1)
            normalized_lhs = normalize_identifiers(lhs)
            
            # Track version for this variable
            if normalized_lhs not in var_versions:
                var_versions[normalized_lhs] = 2
            else:
                var_versions[normalized_lhs] += 1
            
            version = var_versions[normalized_lhs]
            ssa_name = f"{func_name}::1::{lhs}!0@1#{version}"
            ssa_env[lhs] = ssa_name
            ssa_env[normalized_lhs] = ssa_name
    
    # Add global variables to environment
    for global_var in global_vars:
        for var_suffix in ['', '_2']:
            var_name = f"{global_var}{var_suffix}"
            ssa_version = f"{var_name}#2"
            ssa_env[var_name] = ssa_version
            normalized_var = normalize_identifiers(var_name)
            ssa_env[normalized_var] = ssa_version
    
    return ssa_env


def _build_pattern_ssa_env(
    src_assignments_all: List[Dict],
    mut_assignments_all: List[Dict],
    mut_stmt: Dict,
    global_vars: Set[str]
) -> Dict[str, str]:
    """
    Build SSA environment for missing predicate pair derivation.
    
    Pure function: creates new data structures, no side effects.
    
    Args:
        src_assignments_all: All source assignments
        mut_assignments_all: All mutant assignments
        mut_stmt: Current mutant statement
        global_vars: Set of global variables
        
    Returns:
        SSA environment dictionary for pattern matching
    """
    pattern_ssa_env = {}
    
    # Add all source assignments
    for prev_src_stmt in src_assignments_all:
        if 'lhs' in prev_src_stmt:
            prev_lhs = prev_src_stmt['lhs']
            prev_ssa_name = prev_src_stmt.get('ssa_name', prev_lhs)
            pattern_ssa_env[prev_lhs] = prev_ssa_name
            normalized_prev_lhs = normalize_identifiers(prev_lhs)
            pattern_ssa_env[normalized_prev_lhs] = prev_ssa_name
    
    # Add previous mutant assignments for the same variable
    mut_lhs = mut_stmt.get('lhs', '')
    if mut_lhs:
        prev_mut_version = None
        for prev_stmt in mut_assignments_all:
            if prev_stmt == mut_stmt:
                break
            if prev_stmt.get('lhs') == mut_lhs:
                prev_mut_version = prev_stmt.get('ssa_name', mut_lhs)
        
        if prev_mut_version:
            pattern_ssa_env[mut_lhs] = prev_mut_version
            normalized_mut_lhs = normalize_identifiers(mut_lhs)
            pattern_ssa_env[normalized_mut_lhs] = prev_mut_version
    
    # Add global variables
    for global_var in global_vars:
        pattern_ssa_env[global_var] = f"{global_var}#2"
        pattern_ssa_env[f"{global_var}_2"] = f"{global_var}#2"
    
    return pattern_ssa_env


def _check_missing_statement_pattern(
    mut_stmt: Dict,
    macro_map: Dict[str, str]
) -> bool:
    """
    Check if a mutant statement matches the missing statement pattern.
    
    Pure function: no side effects.
    
    Args:
        mut_stmt: Mutant statement dictionary
        macro_map: Macro mapping dictionary
        
    Returns:
        True if statement matches missing pattern (var = var && ... or var = var || ...)
    """
    mut_lhs = mut_stmt.get('lhs', '')
    mut_rhs = mut_stmt.get('rhs', '')
    mut_rhs_expanded = expand_macros_in_expression(mut_rhs, macro_map, is_mutant=True)
    mut_rhs_normalized_ws = ' '.join(mut_rhs_expanded.split())
    
    and_pattern = re.compile(rf'^{re.escape(mut_lhs)}\s*&&\s*(.+)$', re.IGNORECASE)
    or_pattern = re.compile(rf'^{re.escape(mut_lhs)}\s*\|\|\s*(.+)$', re.IGNORECASE)
    
    return bool(and_pattern.match(mut_rhs_normalized_ws) or or_pattern.match(mut_rhs_normalized_ws))


def _add_predicate_pairs_to_stmt(
    stmt: Dict,
    block_predicate_pairs: Dict[str, Tuple[str, str]],
    src_assignments_all: List[Dict],
    mut_assignments_all: List[Dict],
    macro_map: Dict[str, str],
    global_vars: Set[str]
) -> None:
    """
    Add predicate pairs to a statement if applicable.
    
    Pure function: modifies statement in place by adding 'missing_predicate_pair' field.
    
    Args:
        stmt: Statement dictionary to add predicate pairs to
        block_predicate_pairs: Dictionary mapping SSA names to predicate pairs
        src_assignments_all: All source assignments (for pattern matching)
        mut_assignments_all: All mutant assignments (for pattern matching)
        macro_map: Macro mapping dictionary
        global_vars: Set of global variables
    """
    mut_ssa_name = stmt.get('ssa_name')
    if mut_ssa_name and mut_ssa_name in block_predicate_pairs:
        stmt['missing_predicate_pair'] = block_predicate_pairs[mut_ssa_name]
        return
    
    # Check for missing statement pattern
    if _check_missing_statement_pattern(stmt, macro_map):
        pattern_ssa_env = _build_pattern_ssa_env(
            src_assignments_all, mut_assignments_all, stmt, global_vars
        )
        pair = derive_missing_predicate_pair(stmt, pattern_ssa_env, global_vars, macro_map)
        if pair is not None:
            stmt['missing_predicate_pair'] = pair


def _compare_and_generate_ssa(
    src_assignments: List[Dict],
    mut_assignments: List[Dict],
    src_assignments_all: List[Dict],
    mut_assignments_all: List[Dict],
    block_predicate_pairs: Dict[str, Tuple[str, str]],
    macro_map: Dict[str, str],
    global_vars: Set[str]
) -> Tuple[List[Dict], List[Dict]]:
    """
    Compare assignments positionally and generate SSA versions.
    
    Pure function: creates new data structures, no side effects.
    
    Args:
        src_assignments: Relevant source assignments
        mut_assignments: Relevant mutant assignments
        src_assignments_all: All source assignments (for pattern matching)
        mut_assignments_all: All mutant assignments (for pattern matching)
        block_predicate_pairs: Block-based predicate pairs
        macro_map: Macro mapping dictionary
        global_vars: Set of global variables
        
    Returns:
        Tuple of (source_ssa_list, mutant_ssa_list)
    """
    src_ssa = []
    mut_ssa = []
    
    max_len = max(len(src_assignments), len(mut_assignments))
    
    for i in range(max_len):
        src_stmt = src_assignments[i] if i < len(src_assignments) else None
        mut_stmt = mut_assignments[i] if i < len(mut_assignments) else None
        
        if src_stmt and mut_stmt:
            # Both exist - compare after macro expansion and normalization
            src_rhs_expanded = expand_macros_in_expression(src_stmt['rhs'], macro_map, is_mutant=False)
            mut_rhs_expanded = expand_macros_in_expression(mut_stmt['rhs'], macro_map, is_mutant=True)
            
            src_rhs_norm = normalize_expr(src_rhs_expanded)
            mut_rhs_norm = normalize_expr(mut_rhs_expanded)
            
            # Only include if they differ
            if src_rhs_norm != mut_rhs_norm:
                src_ssa.append(src_stmt)
                mut_ssa.append(mut_stmt)
                
                # Add predicate pairs if applicable
                _add_predicate_pairs_to_stmt(mut_stmt, block_predicate_pairs, 
                                            src_assignments_all, mut_assignments_all, 
                                            macro_map, global_vars)
        
        elif src_stmt:
            src_ssa.append(src_stmt)
        elif mut_stmt:
            mut_rhs_expanded_check = expand_macros_in_expression(mut_stmt.get('rhs', ''), macro_map, is_mutant=True)
            mut_rhs_norm_check = normalize_expr(mut_rhs_expanded_check)
            
            src_rhs_normalized_set = {normalize_expr(expand_macros_in_expression(s['rhs'], macro_map, is_mutant=False)) 
                                     for s in src_assignments_all}
            
            if mut_rhs_norm_check not in src_rhs_normalized_set:
                mut_ssa.append(mut_stmt)
                # Add predicate pairs if applicable
                _add_predicate_pairs_to_stmt(mut_stmt, block_predicate_pairs,
                                            src_assignments_all, mut_assignments_all,
                                            macro_map, global_vars)
    
    return src_ssa, mut_ssa


def _verify_ssa_list_reaches_assertions(
    ssa_list: List[Dict],
    all_assignments: List[Dict],
    func_lines: List[str],
    global_vars: Set[str]
) -> List[Dict]:
    """
    Verify that SSA versions in a list actually reach assertion points.
    
    Pure function: creates new data structures, no side effects.
    
    Args:
        ssa_list: List of SSA statements to verify
        all_assignments: All assignments in the function
        func_lines: Function body lines
        global_vars: Set of global variables
        
    Returns:
        List of verified SSA statements (all included, some with warnings)
    """
    verified_ssa = []
    for stmt in ssa_list:
        if not verify_ssa_reaches_assertion(stmt, all_assignments, func_lines, global_vars):
            stmt['_verification_warning'] = 'SSA version may not reach assertion point'
        verified_ssa.append(stmt)  # Always include, but mark with warning if needed
    return verified_ssa


def _verify_ssa_reaches_assertions(
    src_ssa: List[Dict],
    mut_ssa: List[Dict],
    src_assignments_all: List[Dict],
    mut_assignments_all: List[Dict],
    src_func_lines: List[str],
    mut_func_lines: List[str],
    global_vars: Set[str]
) -> Tuple[List[Dict], List[Dict]]:
    """
    Verify that SSA versions used in assertions actually reach assertion points.
    
    Pure function: creates new data structures, no side effects.
    
    Args:
        src_ssa: Source SSA statements
        mut_ssa: Mutant SSA statements
        src_assignments_all: All source assignments
        mut_assignments_all: All mutant assignments
        src_func_lines: Source function lines
        mut_func_lines: Mutant function lines
        global_vars: Set of global variables
        
    Returns:
        Tuple of (verified_source_ssa, verified_mutant_ssa)
    """
    verified_src_ssa = _verify_ssa_list_reaches_assertions(
        src_ssa, src_assignments_all, src_func_lines, global_vars
    )
    verified_mut_ssa = _verify_ssa_list_reaches_assertions(
        mut_ssa, mut_assignments_all, mut_func_lines, global_vars
    )
    
    return verified_src_ssa, verified_mut_ssa


def display_blocks_in_function(func_lines: List[str], func_name: str = "", 
                               assignments: Optional[List[Dict]] = None) -> str:
    """
    Display blocks present in a function in a readable format.
    
    Pure function: creates new string, no side effects.
    
    Args:
        func_lines: Function body lines
        func_name: Optional function name for display
        assignments: Optional list of assignments to show per block
        
    Returns:
        Formatted string showing blocks and their contents
    """
    from .ssa_generator import _build_line_to_block_map, map_statements_to_blocks
    from .ssa_generator import extract_branch_structure
    
    lines = []
    lines.append("=" * 80)
    if func_name:
        lines.append(f"Blocks in function: {func_name}")
    else:
        lines.append("Blocks in function")
    lines.append("=" * 80)
    lines.append("")
    
    # Build line-to-block mapping
    line_to_block = _build_line_to_block_map(func_lines)
    
    # Group lines by block
    blocks_content = {}
    for idx, line in enumerate(func_lines):
        block_id = line_to_block.get(idx, 'main')
        if block_id not in blocks_content:
            blocks_content[block_id] = []
        blocks_content[block_id].append((idx, line.rstrip('\n')))
    
    # Extract branch structures for context
    branches = extract_branch_structure(func_lines)
    branch_info = {b['branch_id']: b.get('reachability_predicate', '') for b in branches}
    
    # Display blocks in order: main, if, else-if-*, else, nested blocks, join_point
    block_order = ['main']
    
    # Add if branch
    if 'if' in blocks_content:
        block_order.append('if')
    
    # Add else-if branches in order (non-nested)
    else_if_blocks = sorted([b for b in blocks_content.keys() if b.startswith('else-if-') and 'nested' not in b],
                           key=lambda x: int(x.split('-')[-1]) if x.split('-')[-1].isdigit() else 0)
    block_order.extend(else_if_blocks)
    
    # Add else branch (non-nested)
    if 'else' in blocks_content:
        block_order.append('else')
    
    # Add nested blocks (if-nested, else-if-*-nested, else-nested)
    nested_blocks = sorted([b for b in blocks_content.keys() if 'nested' in b])
    block_order.extend(nested_blocks)
    
    # Add join_point
    if 'join_point' in blocks_content:
        block_order.append('join_point')
    
    # Display each block
    for block_id in block_order:
        if block_id not in blocks_content:
            continue
            
        lines.append(f"Block: {block_id.upper()}")
        if block_id in branch_info:
            lines.append(f"  Condition: {branch_info[block_id]}")
        lines.append("-" * 80)
        
        for line_idx, line_content in blocks_content[block_id]:
            # Show line number and content
            indent = "    " if line_content.strip().startswith(('{', '}')) else "  "
            lines.append(f"{indent}[{line_idx:3d}] {line_content}")
        
        # If assignments provided, show assignments in this block
        if assignments:
            from .ssa_generator import map_statements_to_blocks
            assignments_by_block = map_statements_to_blocks(assignments, branches, func_lines)
            if block_id in assignments_by_block:
                lines.append("")
                lines.append(f"  Assignments in this block ({len(assignments_by_block[block_id])}):")
                for assign in assignments_by_block[block_id]:
                    ssa_name = assign.get('ssa_name', 'N/A')
                    lhs = assign.get('lhs', 'N/A')
                    rhs = assign.get('rhs', 'N/A')
                    lines.append(f"    {ssa_name}: {lhs} = {rhs}")
        
        lines.append("")
    
    # Summary
    lines.append("=" * 80)
    lines.append(f"Summary: {len(blocks_content)} unique blocks found")
    for block_id in block_order:
        if block_id in blocks_content:
            line_count = len(blocks_content[block_id])
            lines.append(f"  {block_id}: {line_count} line(s)")
    lines.append("=" * 80)
    
    return "\n".join(lines)


def get_ssa_versions_for_pairs_rda(pairs: List[Dict], c_file_path: str) -> Dict[Tuple[str, str], Dict]:
    """
    RDA-compliant version of get_ssa_versions_for_pairs.
    
    This function implements traditional Reaching Definition Analysis:
    - Backward slicing from outputs
    - Def-use chain construction
    - Variable resolution in RHS expressions
    - Dead code elimination
    
    Pure function: creates new data structures, no side effects.
    
    Args:
        pairs: List of function-variable pairs from get_unique_function_variable_pairs
        c_file_path: Path to C source file
        
    Returns:
        Dictionary with same format as get_ssa_versions_for_pairs:
        {(func_name, var_name): {
            'source_ssa': [...],
            'mutant_ssa': [...],
            'mutant_function': str,
            'condition_predicate_pairs': [...]
        }}
    """
    source_lines = read_c_source(c_file_path)
    func_map = build_function_map(source_lines)
    
    # Extract macros and build macro map
    macros = get_macros_from_source(source_lines)
    macro_tuples = get_macro_tuples(macros)
    macro_map = build_macro_map(macro_tuples)
    
    # Extract global variables
    global_vars = extract_global_variables(c_file_path)
    
    ASSIGN_RE = re.compile(r'^\s*(\w+)\s*=\s*(.+);')
    RETURN_RE = re.compile(r'^\s*return\s+(.+);')
    IF_RE = re.compile(r'^\s*if\s*\((.+)\)')
    ELSE_IF_RE = re.compile(r'^\s*else\s+if\s*\((.+)\)')
    
    ssa_results = {}
    
    for pair in pairs:
        func_name = pair['function']
        mut_func_name = pair.get('mutant_function')
        var_name = pair['variable_name']
        
        key = (func_name, var_name)
        
        # Collect ALL assignments first (for RDA analysis)
        # Extract source function assignments
        if func_name in func_map:
            src_assignments_all = extract_assignments_for_variable_rda(
                func_map[func_name], func_name, var_name
            )
        else:
            src_assignments_all = []
        
        # Extract mutant function assignments
        if mut_func_name and mut_func_name in func_map:
            mut_assignments_all = extract_assignments_for_variable_rda(
                func_map[mut_func_name], mut_func_name, var_name
            )
        else:
            mut_assignments_all = []
        
        # RDA STEP 1: Backward slice from outputs to find relevant definitions
        src_func_lines = func_map.get(func_name, [])
        mut_func_lines = func_map.get(mut_func_name, []) if mut_func_name else []
        
        src_assignments, mut_assignments = _find_relevant_assignments_rda(
            var_name, src_assignments_all, mut_assignments_all,
            src_func_lines, mut_func_lines, global_vars
        )
        
        # RDA STEP 2: Build comprehensive SSA environments for ALL variables in the function
        src_ssa_env = _build_ssa_environment_rda(src_func_lines, func_name, global_vars) if src_func_lines else {}
        mut_ssa_env = _build_ssa_environment_rda(mut_func_lines, mut_func_name, global_vars) if mut_func_lines else {}
        
        # RDA STEP 3: Resolve RHS expressions to SSA versions
        _resolve_assignments_rhs(src_assignments, src_ssa_env, global_vars, src_func_lines)
        _resolve_assignments_rhs(mut_assignments, mut_ssa_env, global_vars, mut_func_lines)
        
        # Extract branch structures for block-based analysis
        src_branches = extract_branch_structure(src_func_lines, macro_map, is_mutant=False)
        mut_branches = extract_branch_structure(mut_func_lines, macro_map, is_mutant=True) if mut_func_lines else []
        
        # Map statements to blocks
        src_by_block = map_statements_to_blocks(src_assignments, src_branches, src_func_lines)
        mut_by_block = map_statements_to_blocks(mut_assignments, mut_branches, mut_func_lines) if mut_func_lines else {}
        
        # Find final versions per block
        src_final_by_block = find_final_versions_per_block(src_by_block)
        mut_final_by_block = find_final_versions_per_block(mut_by_block)
        
        # Generate block-based predicate pairs
        block_predicate_pairs = generate_block_based_predicate_pairs(
            src_final_by_block, mut_final_by_block,
            src_assignments, mut_assignments
        )
        
        # Compare assignments positionally and generate SSA versions
        src_ssa, mut_ssa = _compare_and_generate_ssa(
            src_assignments, mut_assignments,
            src_assignments_all, mut_assignments_all,
            block_predicate_pairs, macro_map, global_vars
        )
        
        # Derive condition predicate pairs
        condition_pairs = derive_condition_predicate_pairs(
            src_branches, mut_branches,
            src_ssa_env, global_vars,
            src_ssa_env, mut_ssa_env
        )
        
        # Verify that SSA versions used in assertions actually reach assertion points
        verified_src_ssa, verified_mut_ssa = _verify_ssa_reaches_assertions(
            src_ssa, mut_ssa,
            src_assignments_all, mut_assignments_all,
            src_func_lines, mut_func_lines, global_vars
        )
        
        # Verify condition predicate pairs (always include, verification is informational)
        verified_condition_pairs = condition_pairs
        
        ssa_results[key] = {
            'source_ssa': verified_src_ssa,
            'mutant_ssa': verified_mut_ssa,
            'mutant_function': mut_func_name,
            'condition_predicate_pairs': verified_condition_pairs
        }
    
    return ssa_results


def show_blocks_for_function(c_file_path: str, func_name: str, 
                             var_name: Optional[str] = None) -> None:
    """
    Display blocks present in a specific function.
    
    Helper function for debugging and visualization.
    
    Args:
        c_file_path: Path to C source file
        func_name: Function name to display blocks for
        var_name: Optional variable name to filter assignments
    """
    source_lines = read_c_source(c_file_path)
    func_map = build_function_map(source_lines)
    
    if func_name not in func_map:
        print(f"Function '{func_name}' not found in file.")
        return
    
    func_lines = func_map[func_name]
    assignments = None
    
    if var_name:
        assignments = extract_assignments_for_variable_rda(func_lines, func_name, var_name)
    
    output = display_blocks_in_function(func_lines, func_name, assignments)
    print(output)


def get_ssa_versions_for_file_rda(c_file_path: str, filter_to_version_2: bool = False) -> Dict[Tuple[str, str], Dict]:
    """
    RDA-compliant version of get_ssa_versions_for_file.
    
    This function implements traditional Reaching Definition Analysis.
    
    Pure function: creates new data structures, no side effects.
    
    Args:
        c_file_path: Path to C source file
        filter_to_version_2: If True, filter to only version 2 (first assignment)
        
    Returns:
        Dictionary with same format as get_ssa_versions_for_file
    """
    from .ssa_generator import get_unique_function_variable_pairs
    
    pairs = get_unique_function_variable_pairs(c_file_path)
    results = get_ssa_versions_for_pairs_rda(pairs, c_file_path)
    
    if filter_to_version_2:
        filtered_results = {}
        for key, data in results.items():
            filtered_src = [s for s in data['source_ssa'] if s.get('version') == 2]
            filtered_mut = [s for s in data['mutant_ssa'] if s.get('version') == 2]
            if filtered_src or filtered_mut:
                filtered_results[key] = {
                    **data,
                    'source_ssa': filtered_src,
                    'mutant_ssa': filtered_mut
                }
        return filtered_results
    
    return results


def main():
    """
    Main function for debugging and direct execution.
    
    This allows the module to be run directly for debugging:
        python3 -m ssa_analyzer.rda_ssa_generator
        python3 ssa_analyzer/ssa_analyzer/rda_ssa_generator.py
    
    Or debug in Cursor/VS Code by setting breakpoints and running this file.
    
    BREAKPOINT LOCATIONS:
    - Line ~1323: Entry point (inspect configuration)
    - Line ~1328: After getting pairs
    - Line ~1339: After getting results
    - Line ~1347: Inside results loop
    - Line ~1357: Inside pair inspection
    """
    import sys
    import os
    
    from .ssa_generator import get_unique_function_variable_pairs
    
    # Default configuration
    c_file_path = 'Original/tcas_v11.c'
    filter_to_version_2 = False
    show_blocks = False  # Set to True to display blocks for each function
    
    # Allow command-line arguments
    if len(sys.argv) > 1:
        c_file_path = sys.argv[1]
    if len(sys.argv) > 2:
        filter_to_version_2 = sys.argv[2].lower() in ('true', '1', 'yes')
    if len(sys.argv) > 3:
        show_blocks = sys.argv[3].lower() in ('true', '1', 'yes')
    
    print("=" * 80)
    print("RDA SSA Generator - Debug Mode")
    print("=" * 80)
    print(f"File: {c_file_path}")
    print(f"Filter to version 2: {filter_to_version_2}")
    print(f"Working directory: {os.getcwd()}")
    print()
    
    # BREAKPOINT LOCATION 1: Entry point
    # Set breakpoint here to inspect configuration before processing
    print("Getting function-variable pairs...")
    
    pairs = get_unique_function_variable_pairs(c_file_path)
    
    # BREAKPOINT LOCATION 2: After getting pairs
    # Set breakpoint here to inspect pairs
    print(f"Found {len(pairs)} function-variable pairs")
    for idx, pair in enumerate(pairs[:3]):
        print(f"  [{idx+1}] {pair['function']}.{pair['variable_name']}")
    print()
    
    # BREAKPOINT LOCATION 3: Before calling main function
    # Set breakpoint here to inspect pairs before processing
    print("Processing pairs with RDA...")
    results = get_ssa_versions_for_file_rda(c_file_path, filter_to_version_2=filter_to_version_2)
    
    # BREAKPOINT LOCATION 4: After getting results
    # Set breakpoint here to inspect complete results
    print(f"\nAnalysis complete!")
    print(f"Found {len(results)} function-variable pairs in results")
    print()
    
    # Process and display results
    print("Results Summary:")
    print("-" * 80)
    
    # BREAKPOINT LOCATION 5: Inside results loop
    # Set breakpoint here to debug each pair
    for idx, ((func_name, var_name), data) in enumerate(results.items()):
        print(f"\n[{idx+1}] {func_name}.{var_name}:")
        print(f"  Source SSA statements: {len(data.get('source_ssa', []))}")
        print(f"  Mutant SSA statements: {len(data.get('mutant_ssa', []))}")
        print(f"  Condition predicate pairs: {len(data.get('condition_predicate_pairs', []))}")
        
        # Display blocks if enabled
        if show_blocks:
            print("\n" + "=" * 80)
            show_blocks_for_function(c_file_path, func_name, var_name)
            print("=" * 80 + "\n")
        
        # BREAKPOINT LOCATION 6: Inside pair inspection
        # Set breakpoint here to inspect individual pairs in detail
        if data.get('source_ssa'):
            first_src = data['source_ssa'][0]
            print(f"  First source SSA: {first_src.get('ssa_name', 'N/A')}")
            print(f"    Assignment: {first_src.get('assignment', 'N/A')[:70]}...")
        
        if data.get('mutant_ssa'):
            first_mut = data['mutant_ssa'][0]
            print(f"  First mutant SSA: {first_mut.get('ssa_name', 'N/A')}")
            print(f"    Assignment: {first_mut.get('assignment', 'N/A')[:70]}...")
        
        if data.get('condition_predicate_pairs'):
            print(f"  Condition pairs:")
            for pair_idx, (src_pred, mut_pred) in enumerate(data['condition_predicate_pairs'][:2]):
                print(f"    Pair {pair_idx+1}:")
                print(f"      Source: {src_pred[:80]}...")
                print(f"      Mutant: {mut_pred[:80]}...")
    
    print("\n" + "=" * 80)
    print("Debugging complete!")
    print("=" * 80)
    
    return results


if __name__ == '__main__':
    import sys
    try:
        results = main()
        print(f"\n✓ Successfully processed {len(results)} pairs")
    except Exception as e:
        print(f"\n✗ Error occurred: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
