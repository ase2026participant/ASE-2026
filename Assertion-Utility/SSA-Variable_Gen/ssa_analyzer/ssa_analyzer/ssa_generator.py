"""SSA version generation for variables."""

import re
from typing import List, Dict, Tuple, Optional, Set
from .parser import (
    read_c_source, build_function_map, strip_comments,
    normalize_identifiers, normalize_expr, split_top_level_and
)
from .diff_finder import (
    get_macros_from_source, get_macro_tuples, find_macro_differences,
    find_function_differences, find_macro_usage, merge_function_and_macro_diffs,
    build_macro_map, expand_macros_in_expression
)


def resolve_globals_to_ssa(expr: str, ssa_env: Dict[str, str], global_vars: Set[str]) -> str:
    """
    Resolve global variables in an expression to their SSA versions.
    
    CBMC-style: Global variables use program-wide SSA versions (e.g., g#2).
    This function replaces raw global variable names with their SSA versions.
    
    Args:
        expr: Expression string that may contain global variables
        ssa_env: SSA environment mapping variable names to their latest SSA versions
                 Format: var_name -> var_name#version or var_name::scope#version
        global_vars: Set of global variable names (without _2 suffix)
    
    Returns:
        Expression with global variables resolved to SSA versions
    """
    result = expr
    # Extract all identifiers from the expression
    # Pattern matches C identifiers (alphanumeric + underscore, starting with letter/underscore)
    identifier_pattern = re.compile(r'\b([A-Za-z_][A-Za-z0-9_]*)\b')
    
    def replace_var(match):
        var_name = match.group(1)
        # Check if this is a global variable (or its mutant version)
        normalized_var = normalize_identifiers(var_name)
        
        if normalized_var in global_vars:
            # This is a global variable - resolve to SSA version
            # Check both normalized and original name in SSA environment
            ssa_version = ssa_env.get(var_name) or ssa_env.get(normalized_var)
            
            if ssa_version:
                # If SSA version is in format "var#N" or "var::scope#N", use it directly
                if '#' in ssa_version:
                    return ssa_version
                # Otherwise, construct SSA version: var#version
                return f"{var_name}#{ssa_version}" if ssa_version.isdigit() else ssa_version
            else:
                # No SSA version found - use #0 (initial version) for globals
                return f"{var_name}#0"
        
        return var_name
    
    # Replace all global variable occurrences with their SSA versions
    result = identifier_pattern.sub(replace_var, result)
    return result


def resolve_all_variables_to_ssa(expr: str, ssa_env: Dict[str, str], global_vars: Optional[Set[str]] = None) -> str:
    """
    Resolve ALL variables (both local and global) in an expression to their SSA versions.
    
    CBMC-style: 
    - Global variables use program-wide SSA versions (e.g., g#2)
    - Local variables use function-scoped SSA versions from ssa_env
    
    Args:
        expr: Expression string that may contain variables
        ssa_env: SSA environment mapping variable names to their latest SSA versions
                 Format: var_name -> var_name#version or var_name::scope#version
                 Contains both local and global variable SSA versions
        global_vars: Optional set of global variable names (without _2 suffix)
                    If provided, globals are resolved with program-wide versions
    
    Returns:
        Expression with all variables resolved to SSA versions
    """
    result = expr
    # Extract all identifiers from the expression
    identifier_pattern = re.compile(r'\b([A-Za-z_][A-Za-z0-9_]*)\b')
    
    def replace_var(match):
        var_name = match.group(1)
        normalized_var = normalize_identifiers(var_name)
        
        # First check if variable is in SSA environment (local variables or already resolved)
        ssa_version = ssa_env.get(var_name) or ssa_env.get(normalized_var)
        
        if ssa_version:
            # Variable found in SSA environment - use its SSA version
            # If already in format "var#N" or "var::scope#N", use directly
            if '#' in ssa_version or '::' in ssa_version:
                return ssa_version
            # Otherwise, construct SSA version: var#version
            return f"{var_name}#{ssa_version}" if ssa_version.isdigit() else ssa_version
        
        # If not in SSA environment, check if it's a global variable
        if global_vars and normalized_var in global_vars:
            # Global variable not yet in environment - use #0 (initial version)
            return f"{var_name}#0"
        
        # Variable not found - return as-is (might be a function call, constant, etc.)
        return var_name
    
    # Replace all variable occurrences with their SSA versions
    result = identifier_pattern.sub(replace_var, result)
    return result


def extract_global_variables(c_file_path: str) -> Set[str]:
    """
    Extract global variable declarations from C source file.
    
    CBMC-style: Only variables declared at file scope (outside functions) are globals.
    Local variables declared inside functions are excluded.
    
    Args:
        c_file_path: Path to the C source file
    
    Returns:
        Set of global variable names (normalized, without _2 suffix)
    """
    source_lines = read_c_source(c_file_path)
    global_vars = set()
    
    # Track whether we're inside a function (between { and })
    brace_depth = 0
    in_function = False
    
    # Pattern to match global variable declarations: type var_name; or type var_name[...];
    # Excludes function declarations and definitions
    global_decl_pattern = re.compile(
        r'^\s*(?:static\s+|extern\s+)?'  # optional storage class
        r'(?:int|bool|char|float|double|void|\w+\s*\*)\s+'  # type
        r'(\w+)'  # variable name
        r'(?:\s*\[[^\]]*\])?'  # optional array brackets
        r'\s*;',  # semicolon
        re.MULTILINE
    )
    
    for line in source_lines:
        # Track brace depth to detect function boundaries
        brace_depth += line.count('{')
        brace_depth -= line.count('}')
        in_function = brace_depth > 0
        
        # Only process declarations outside functions (global scope)
        if in_function:
            continue
        
        # Skip function definitions (lines with parentheses before semicolon)
        if '(' in line and ')' in line and ';' in line:
            # Check if it's a function call or declaration
            if re.search(r'\w+\s*\([^)]*\)\s*;', line):
                continue
        
        matches = global_decl_pattern.findall(line)
        for var_name in matches:
            # Normalize (remove _2 suffix if present)
            normalized = normalize_identifiers(var_name)
            global_vars.add(normalized)
    
    return global_vars


def derive_missing_predicate_pair(stmt_mut: Dict, ssa_env: Dict, global_vars: Optional[Set[str]] = None, macro_map: Optional[Dict[str, str]] = None) -> Optional[Tuple[str, str]]:
    """
    Derive predicate pair (p_src, p_mut) for a missing statement.
    
    Models missing statements as identity transformations on state:
    - When a statement is missing in source but present in mutant, source is treated as identity
    - When a statement is missing in mutant but present in source, mutant is treated as identity
    
    CBMC-style: Global variables in expressions are resolved to their SSA versions (e.g., g#2).
    Macros are expanded before pattern matching and comparison.
    
    Supported patterns:
    - x = x && φ → p_src = True (identity), p_mut = φ (with macros expanded and globals resolved)
    - x = x || φ → p_src = False (identity), p_mut = φ (with macros expanded and globals resolved)
    - x = φ → p_src = x_old (identity), p_mut = φ (with macros expanded and globals resolved)
    
    Args:
        stmt_mut: Dictionary containing mutant statement info with keys:
                  'lhs' (variable name), 'rhs' (right-hand side expression), 
                  'assignment' (full assignment string)
        ssa_env: Dictionary containing SSA environment with previous versions of variables
                 Key format: variable_name -> previous SSA version/value
                 For globals: should contain entries like 'Own_Tracked_Alt' -> 'Own_Tracked_Alt#2'
        global_vars: Optional set of global variable names (normalized, without _2 suffix)
                    If None, globals won't be resolved to SSA versions
        macro_map: Optional dictionary mapping macro_name -> macro_value for macro expansion
    
    Returns:
        Tuple (p_src, p_mut) representing the predicate pair, or None if statement
        cannot be safely classified. Global variables in p_mut are resolved to SSA versions.
    """
    if not stmt_mut or 'rhs' not in stmt_mut or 'lhs' not in stmt_mut:
        return None
    
    lhs = stmt_mut['lhs']
    rhs = stmt_mut['rhs'].strip()
    
    # Expand macros before pattern matching (mutant statement, so is_mutant=True)
    rhs_expanded = expand_macros_in_expression(rhs, macro_map or {}, is_mutant=True)
    
    # Normalize whitespace for pattern matching
    rhs_normalized = ' '.join(rhs_expanded.split())
    
    # Pattern 1: x = x && φ
    # When missing in source: source does identity (True), mutant does φ
    # Match RHS: "x && ..." (RHS already contains everything after '=')
    and_pattern = re.compile(rf'^{re.escape(lhs)}\s*&&\s*(.+)$', re.IGNORECASE)
    and_match = and_pattern.match(rhs_normalized)
    if and_match:
        phi = and_match.group(1).strip()
        # Remove outer parentheses if present
        phi = phi.strip('()')
        # Resolve global variables to SSA versions in φ
        if global_vars:
            phi = resolve_globals_to_ssa(phi, ssa_env, global_vars)
        # Source is identity (True) when statement is missing
        # Mutant evaluates the condition φ
        return ('True', phi)
    
    # Pattern 2: x = x || φ
    # When missing in source: source does identity (False), mutant does φ
    # Match RHS: "x || ..." (RHS already contains everything after '=')
    or_pattern = re.compile(rf'^{re.escape(lhs)}\s*\|\|\s*(.+)$', re.IGNORECASE)
    or_match = or_pattern.match(rhs_normalized)
    if or_match:
        phi = or_match.group(1).strip()
        # Remove outer parentheses if present
        phi = phi.strip('()')
        # Resolve global variables to SSA versions in φ
        if global_vars:
            phi = resolve_globals_to_ssa(phi, ssa_env, global_vars)
        # Source is identity (False) when statement is missing
        # Mutant evaluates the condition φ
        return ('False', phi)
    
    # Pattern 3: x = φ (general assignment, not x = x && or x = x ||)
    # When statements differ: compare variable SSA versions (not expression vs old value)
    # Match RHS: anything that's not x itself and not x && or x ||
    # Skip if this matches pattern 1 or 2 (already handled)
    if not (and_match or or_match):
        # Check if RHS is just the variable itself (identity)
        if rhs_normalized.strip() == lhs:
            # Pure identity assignment - if missing, both sides are identity
            # Use variable SSA versions for comparison
            mut_ssa_name = stmt_mut.get('ssa_name')
            if mut_ssa_name:
                # Get source variable name (normalize mutant name to get source name)
                normalized_lhs = normalize_identifiers(lhs)
                src_ssa_name = ssa_env.get(normalized_lhs) or ssa_env.get(lhs)
                if src_ssa_name:
                    return (str(src_ssa_name), str(mut_ssa_name))
                else:
                    # Source variable not found - use identity (previous version)
                    x_old = ssa_env.get(lhs, lhs)
                    return (str(x_old), str(mut_ssa_name))
            else:
                # Fallback: use previous version
                x_old = ssa_env.get(lhs, lhs)
                return (str(x_old), str(x_old))
        else:
            # This is a general assignment x = φ
            # Compare variable SSA versions: p_src = source variable SSA, p_mut = mutant variable SSA
            mut_ssa_name = stmt_mut.get('ssa_name')
            if mut_ssa_name:
                # Get source variable name (normalize mutant name to get source name)
                # Mutant variable might be 'need_upward_RA_2', source is 'need_upward_RA'
                normalized_lhs = normalize_identifiers(lhs)
                
                # Look up source variable's SSA version from environment
                # Try normalized name first, then original name
                src_ssa_name = ssa_env.get(normalized_lhs) or ssa_env.get(lhs)
                
                if src_ssa_name:
                    # Both source and mutant have SSA versions - compare them
                    return (str(src_ssa_name), str(mut_ssa_name))
                else:
                    # Source variable not found in environment - use previous version (identity)
                    # This happens when source doesn't have this assignment
                    x_old = ssa_env.get(lhs, lhs)
                    return (str(x_old), str(mut_ssa_name))
            else:
                # Fallback: mutant SSA name not available, use expression
                phi = rhs_normalized
                # Resolve global variables to SSA versions in φ
                if global_vars:
                    phi = resolve_globals_to_ssa(phi, ssa_env, global_vars)
                # Get previous version of variable from SSA environment
                x_old = ssa_env.get(lhs, lhs)
                return (str(x_old), phi)
    
    # Cannot safely classify this statement pattern
    return None


def extract_branch_structure(func_lines: List[str], macro_map: Optional[Dict[str, str]] = None, is_mutant: bool = False) -> List[Dict]:
    """
    Extract branch structure (if/else if/else) from function body.
    
    CBMC-style: Each branch has a reachability predicate.
    Branches are ordered by structural position (if, else-if-0, else-if-1, ..., else).
    
    Side-effect free: Returns new data structures without modifying inputs.
    
    Args:
        func_lines: List of function body lines
        macro_map: Optional dictionary mapping macro_name -> macro_value for macro expansion
        is_mutant: If True, indicates this is a mutant function (for macro expansion)
    
    Returns:
        Ordered list of branch dictionaries with:
            - branch_id: str ('if', 'else-if-0', 'else-if-1', ..., 'else')
            - reachability_predicate: str (condition expression with macros expanded, or 'True' for else)
            - line: str (original line)
    """
    IF_RE = re.compile(r'^\s*if\s*\((.+)\)')
    ELSE_IF_RE = re.compile(r'^\s*else\s+if\s*\((.+)\)')
    ELSE_RE = re.compile(r'^\s*else\s*[^{]*')
    
    branches = []
    else_if_index = 0
    
    for line in func_lines:
        clean = strip_comments(line)
        if not clean:
            continue
        
        if_match = IF_RE.match(clean)
        if if_match:
            # First if statement
            cond = if_match.group(1).strip()
            # Expand macros in condition
            cond_expanded = expand_macros_in_expression(cond, macro_map or {}, is_mutant)
            branches.append({
                'branch_id': 'if',
                'reachability_predicate': cond_expanded,
                'line': line.rstrip('\n')
            })
            else_if_index = 0  # Reset else-if counter
        else:
            else_if_match = ELSE_IF_RE.match(clean)
            if else_if_match:
                # else-if branch
                cond = else_if_match.group(1).strip()
                # Expand macros in condition
                cond_expanded = expand_macros_in_expression(cond, macro_map or {}, is_mutant)
                branches.append({
                    'branch_id': f'else-if-{else_if_index}',
                    'reachability_predicate': cond_expanded,
                    'line': line.rstrip('\n')
                })
                else_if_index += 1
            else:
                else_match = ELSE_RE.match(clean)
                if else_match:
                    # else branch (no condition, always reachable when previous branches are false)
                    branches.append({
                        'branch_id': 'else',
                        'reachability_predicate': 'True',  # Identity: always reachable when other branches fail
                        'line': line.rstrip('\n')
                    })
    
    return branches


def derive_condition_predicate_pairs(src_branches: List[Dict], mut_branches: List[Dict], 
                                     ssa_env: Dict[str, str], global_vars: Optional[Set[str]] = None,
                                     src_ssa_env: Optional[Dict[str, str]] = None,
                                     mut_ssa_env: Optional[Dict[str, str]] = None) -> List[Tuple[str, str]]:
    """
    Derive predicate pairs (p_src, p_mut) for condition-related differences.
    
    Conceptual model: Treat if/else-if/else as a partition of state space.
    Each branch is associated with a reachability predicate.
    Missing branches are modeled as unreachable (False).
    Missing conditions are modeled as identity guards (True).
    
    CBMC-style: Global variables in predicates are resolved to SSA versions.
    
    Args:
        src_branches: Ordered list of source branch objects with:
                     - branch_id: str ('if', 'else-if-0', 'else-if-1', ..., 'else')
                     - reachability_predicate: str (boolean SSA expr)
                     - line: str
        mut_branches: Ordered list of mutant branch objects (same structure)
        ssa_env: SSA environment for resolving global variables
        global_vars: Optional set of global variable names for SSA resolution
        src_ssa_env: Optional separate SSA environment for source predicates
        mut_ssa_env: Optional separate SSA environment for mutant predicates
    
    Returns:
        List of (p_src, p_mut) predicate pairs suitable for
        (p_src ≠ p_mut) ⇒ (o_src ≠ o_mut)
        
        Behavior:
        - Align branches by structural position (branch_id)
        - For each branch:
            * present in both: emit (p_src, p_mut) if predicates differ syntactically
            * only in source: emit (p_src, False) - mutant branch is unreachable
            * only in mutant: emit (False, p_mut) - source branch is unreachable
        - Skip branches where predicates are syntactically identical
        - Skip reordered or structurally ambiguous branches (only align by position)
        - Must be pure and side-effect free
    """
    pairs = []
    
    # Build index by branch_id for alignment
    src_by_id = {branch['branch_id']: branch for branch in src_branches}
    mut_by_id = {branch['branch_id']: branch for branch in mut_branches}
    
    # Get all unique branch IDs (union of source and mutant)
    all_branch_ids = set(src_by_id.keys()) | set(mut_by_id.keys())
    
    # Process branches in structural order: if, else-if-0, else-if-1, ..., else
    branch_order = ['if'] + [f'else-if-{i}' for i in range(10)] + ['else']
    
    for branch_id in branch_order:
        if branch_id not in all_branch_ids:
            continue
        
        src_branch = src_by_id.get(branch_id)
        mut_branch = mut_by_id.get(branch_id)
        
        if src_branch and mut_branch:
            # Both branches exist - compare predicates
            src_pred = src_branch['reachability_predicate']
            mut_pred = mut_branch['reachability_predicate']
            
            # Normalize predicates (including identifiers) to detect actual semantic differences
            # If predicates normalize to the same form, they're semantically identical
            src_pred_normalized = normalize_expr(src_pred)
            mut_pred_normalized = normalize_expr(mut_pred)
            
            if src_pred_normalized != mut_pred_normalized:
                # Predicates differ syntactically - emit pair
                # Resolve ALL variables (local and global) to SSA versions
                # Use separate environments for source and mutant to ensure correct SSA names
                env_src = src_ssa_env if src_ssa_env else ssa_env
                env_mut = mut_ssa_env if mut_ssa_env else ssa_env
                src_pred_resolved = resolve_all_variables_to_ssa(src_pred, env_src, global_vars)
                mut_pred_resolved = resolve_all_variables_to_ssa(mut_pred, env_mut, global_vars)
                
                pairs.append((src_pred_resolved, mut_pred_resolved))
        
        elif src_branch and not mut_branch:
            # Branch only in source - mutant branch is unreachable (False)
            src_pred = src_branch['reachability_predicate']
            
            # Resolve ALL variables (local and global) to SSA versions
            env_src = src_ssa_env if src_ssa_env else ssa_env
            src_pred_resolved = resolve_all_variables_to_ssa(src_pred, env_src, global_vars)
            
            pairs.append((src_pred_resolved, 'False'))
        
        elif mut_branch and not src_branch:
            # Branch only in mutant - source branch is unreachable (False)
            mut_pred = mut_branch['reachability_predicate']
            
            # Resolve ALL variables (local and global) to SSA versions
            env_mut = mut_ssa_env if mut_ssa_env else ssa_env
            mut_pred_resolved = resolve_all_variables_to_ssa(mut_pred, env_mut, global_vars)
            
            pairs.append(('False', mut_pred_resolved))
        
        elif src_branch and not mut_branch:
            # Branch only in source - mutant branch is unreachable (False)
            src_pred = src_branch['reachability_predicate']
            
            # Resolve global variables to SSA versions
            if global_vars:
                src_pred_resolved = resolve_globals_to_ssa(src_pred, ssa_env, global_vars)
            else:
                src_pred_resolved = src_pred
            
            pairs.append((src_pred_resolved, 'False'))
        
        elif mut_branch and not src_branch:
            # Branch only in mutant - source branch is unreachable (False)
            mut_pred = mut_branch['reachability_predicate']
            
            # Resolve global variables to SSA versions
            if global_vars:
                mut_pred_resolved = resolve_globals_to_ssa(mut_pred, ssa_env, global_vars)
            else:
                mut_pred_resolved = mut_pred
            
            pairs.append(('False', mut_pred_resolved))
    
    return pairs


def get_unique_function_variable_pairs(c_file_path: str) -> List[Dict]:
    """
    Extract unique function-variable pairs with source and mutant variables from a C file.
    Only returns pairs that have actual differences.
    
    Args:
        c_file_path: Path to the C source file
        
    Returns:
        List of dictionaries with function-variable pairs and their source/mutant variable names
    """
    # Get results from standard function (for differences in assignments and macros)
    source_lines = read_c_source(c_file_path)
    
    # Extract macros and find differences
    macros = get_macros_from_source(source_lines)
    macro_tuples = get_macro_tuples(macros)
    diff_micros_tuples = find_macro_differences(macro_tuples)
    macro_map = build_macro_map(macro_tuples)
    
    # Build function map
    func_map = build_function_map(source_lines)
    
    # Find function differences (with macro expansion)
    func_diffs = find_function_differences(func_map, macro_map)
    
    # Find macro usage
    macro_hits = find_macro_usage(func_map, diff_micros_tuples)
    
    # Merge results
    results = merge_function_and_macro_diffs(func_diffs, macro_hits)
    
    # Extract unique pairs
    pairs = []
    seen = set()
    
    for result in results:
        func_name = result.get('function', '')
        mut_func_name = result.get('mutant', None)
        
        # Extract from function_diff
        func_diff = result.get('function_diff')
        if func_diff:
            var_name = func_diff.get('variable')
            if var_name:
                unique_key = (func_name, var_name)
                if unique_key not in seen:
                    seen.add(unique_key)
                    pairs.append({
                        'function': func_name,
                        'mutant_function': mut_func_name,
                        'variable_name': var_name,
                        'source_variable': var_name,
                        'mutant_variable': f"{var_name}_2" if mut_func_name else None
                    })
        
        # Extract from macro_diff
        macro_diff = result.get('macro_diff')
        if macro_diff:
            var_src = macro_diff.get('variable_src')
            var_mut = macro_diff.get('variable_mut')
            
            if var_src:
                var_name = var_src
            elif var_mut:
                var_name = var_mut[:-2] if var_mut.endswith('_2') else var_mut
            else:
                var_name = None
            
            if var_name:
                unique_key = (func_name, var_name)
                if unique_key not in seen:
                    seen.add(unique_key)
                    pairs.append({
                        'function': func_name,
                        'mutant_function': mut_func_name,
                        'variable_name': var_name,
                        'source_variable': var_src if var_src else None,
                        'mutant_variable': var_mut if var_mut else None
                    })
    
    # Also check for return statement and if condition differences
    RETURN_RE = re.compile(r'^\s*return\s+(.+);')
    IF_RE = re.compile(r'^\s*if\s*\((.+)\)')
    ELSE_IF_RE = re.compile(r'^\s*else\s+if\s*\((.+)\)')
    
    # Process all source functions that have mutant versions
    for fname, src_lines in func_map.items():
        if fname.endswith("_2"):
            continue
        
        mutant = fname + "_2"
        if mutant not in func_map:
            continue
        
        # Extract return statements
        src_returns = []
        mut_returns = []
        
        # Extract if conditions
        src_if_conditions = []
        mut_if_conditions = []
        
        for line in src_lines:
            clean = strip_comments(line)
            if not clean:
                continue
            ret_match = RETURN_RE.match(clean)
            if ret_match:
                ret_expr = ret_match.group(1).strip()
                src_returns.append(ret_expr)
            else:
                if_match = IF_RE.match(clean)
                if if_match:
                    if_cond = if_match.group(1).strip()
                    src_if_conditions.append(if_cond)
                else:
                    else_if_match = ELSE_IF_RE.match(clean)
                    if else_if_match:
                        else_if_cond = else_if_match.group(1).strip()
                        src_if_conditions.append(else_if_cond)
        
        for line in func_map[mutant]:
            clean = strip_comments(line)
            if not clean:
                continue
            ret_match = RETURN_RE.match(clean)
            if ret_match:
                ret_expr = ret_match.group(1).strip()
                mut_returns.append(ret_expr)
            else:
                if_match = IF_RE.match(clean)
                if if_match:
                    if_cond = if_match.group(1).strip()
                    mut_if_conditions.append(if_cond)
                else:
                    else_if_match = ELSE_IF_RE.match(clean)
                    if else_if_match:
                        else_if_cond = else_if_match.group(1).strip()
                        mut_if_conditions.append(else_if_cond)
        
        # Check return statements for differences
        # Handle cases where one has more returns than the other
        if src_returns or mut_returns:
            max_len = max(len(src_returns), len(mut_returns))
            for i in range(max_len):
                src_ret = src_returns[i] if i < len(src_returns) else None
                mut_ret = mut_returns[i] if i < len(mut_returns) else None
                
                # If one side is missing, it's a difference
                if src_ret is None or mut_ret is None:
                    var_name = 'return'
                    if max_len > 1:
                        var_name = f'return_{i+1}'
                    
                    if (fname, var_name) not in seen:
                        seen.add((fname, var_name))
                        pairs.append({
                            'function': fname,
                            'mutant_function': mutant,
                            'variable_name': var_name,
                            'source_variable': f'return({src_ret})' if src_ret else None,
                            'mutant_variable': f'return({mut_ret})' if mut_ret else None
                        })
                else:
                    # Both exist, check if they differ
                    src_ret_norm = normalize_expr(src_ret)
                    mut_ret_norm = normalize_expr(mut_ret)
                    
                    if src_ret_norm != mut_ret_norm:
                        var_name = 'return'
                        if max_len > 1:
                            var_name = f'return_{i+1}'
                        
                        if (fname, var_name) not in seen:
                            seen.add((fname, var_name))
                            pairs.append({
                                'function': fname,
                                'mutant_function': mutant,
                                'variable_name': var_name,
                                'source_variable': f'return({src_ret})',
                                'mutant_variable': f'return({mut_ret})'
                            })
        
        # Check if conditions for differences
        # Handle cases where one has more conditions than the other
        if src_if_conditions or mut_if_conditions:
            max_len = max(len(src_if_conditions), len(mut_if_conditions))
            for i in range(max_len):
                src_if = src_if_conditions[i] if i < len(src_if_conditions) else None
                mut_if = mut_if_conditions[i] if i < len(mut_if_conditions) else None
                
                # If one side is missing, it's a difference
                if src_if is None or mut_if is None:
                    var_name = 'if_condition'
                    if max_len > 1:
                        var_name = f'if_condition_{i+1}'
                    
                    if (fname, var_name) not in seen:
                        seen.add((fname, var_name))
                        pairs.append({
                            'function': fname,
                            'mutant_function': mutant,
                            'variable_name': var_name,
                            'source_variable': f'if({src_if})' if src_if else None,
                            'mutant_variable': f'if({mut_if})' if mut_if else None
                        })
                else:
                    # Both exist, check if they differ
                    src_if_norm = normalize_expr(src_if)
                    mut_if_norm = normalize_expr(mut_if)
                    
                    if src_if_norm != mut_if_norm:
                        var_name = 'if_condition'
                        if max_len > 1:
                            var_name = f'if_condition_{i+1}'
                        
                        if (fname, var_name) not in seen:
                            seen.add((fname, var_name))
                            pairs.append({
                                'function': fname,
                                'mutant_function': mutant,
                                'variable_name': var_name,
                                'source_variable': f'if({src_if})',
                                'mutant_variable': f'if({mut_if})'
                            })
    
    # Sort by function name, then variable name
    pairs.sort(key=lambda x: (x['function'], x['variable_name']))
    
    return pairs


def get_block_for_statement(stmt: Dict, branches: List[Dict], func_lines: List[str]) -> str:
    """
    Determine which branch/block a statement belongs to based on line number and brace depth.
    
    Pure function: No side effects, returns block identifier.
    
    Args:
        stmt: Statement dictionary with 'line' field
        branches: List of branch dictionaries from extract_branch_structure()
        func_lines: Function body lines for line number extraction
    
    Returns:
        branch_id: str ('if', 'else-if-0', 'else', or 'main' for statements outside branches)
    """
    stmt_line = stmt.get('line', '')
    if not stmt_line:
        return 'main'
    
    # Find line index of statement in function
    stmt_line_idx = None
    for idx, line in enumerate(func_lines):
        # More robust matching - check if statement line content matches
        stmt_clean = stmt_line.strip()
        line_clean = line.strip()
        if stmt_clean and (stmt_clean in line_clean or line_clean in stmt_clean or 
                          stmt_clean.replace('\t', '    ') == line_clean.replace('\t', '    ')):
            stmt_line_idx = idx
            break
    
    if stmt_line_idx is None:
        return 'main'
    
    # Track brace depth and current block
    current_block = 'main'
    brace_depth = 0
    active_branch = None
    branch_brace_depth = {}
    
    # First pass: find branch start positions and their brace depths
    for branch in branches:
        branch_line = branch.get('line', '')
        branch_line_idx = None
        for idx, line in enumerate(func_lines):
            branch_clean = branch_line.strip()
            line_clean = line.strip()
            if branch_clean and (branch_clean in line_clean or line_clean in branch_clean):
                branch_line_idx = idx
                break
        
        if branch_line_idx is not None:
            # Calculate brace depth at branch start
            depth = 0
            for i in range(branch_line_idx):
                depth += func_lines[i].count('{') - func_lines[i].count('}')
            branch_brace_depth[branch['branch_id']] = depth
    
    # Second pass: determine which block contains the statement
    depth = 0
    for idx in range(stmt_line_idx + 1):
        line = func_lines[idx]
        depth += line.count('{') - line.count('}')
        
        # Check if we're entering a branch block
        for branch in branches:
            branch_line = branch.get('line', '')
            branch_clean = branch_line.strip()
            line_clean = line.strip()
            if branch_clean and (branch_clean in line_clean or line_clean in branch_clean):
                # This is a branch line - check if statement is inside this branch's block
                branch_depth = branch_brace_depth.get(branch['branch_id'], 0)
                # Statement is in this branch if it's after the branch line and at same or deeper brace depth
                if idx < stmt_line_idx and depth >= branch_depth:
                    active_branch = branch['branch_id']
        
        # Update current block based on active branch
        if active_branch:
            current_block = active_branch
    
    return current_block


def _is_join_point(line_idx: int, func_lines: List[str]) -> bool:
    """
    Check if a line is at a join point (after an if-else chain).
    
    A join point occurs when:
    - The line is after a complete if-else chain
    - The brace depth has returned to the level before the if statement
    
    Args:
        line_idx: Line index to check
        func_lines: Function body lines
        
    Returns:
        True if this is a join point, False otherwise
    """
    if line_idx <= 0 or line_idx >= len(func_lines):
        return False
    
    IF_RE = re.compile(r'^\s*if\s*\(')
    ELSE_RE = re.compile(r'^\s*else\s*[^{]*')
    
    # Track brace depth and branch structure
    brace_depth = 0
    branch_start_depth = -1
    in_branch = False
    
    for idx in range(line_idx):
        line = func_lines[idx]
        clean = strip_comments(line).strip()
        brace_depth += line.count('{') - line.count('}')
        
        if IF_RE.match(clean):
            if not in_branch:
                branch_start_depth = brace_depth
            in_branch = True
        elif ELSE_RE.match(clean) and in_branch:
            # Continue in branch
            pass
        elif in_branch and brace_depth <= branch_start_depth:
            # Branch has closed - this could be a join point
            # Check if there are more branches after this
            in_branch = False
            branch_start_depth = -1
    
    # If we're at or below the starting brace depth and were in a branch, it's a join point
    return not in_branch and branch_start_depth == -1 and brace_depth <= 0


def _build_line_to_block_map(func_lines: List[str]) -> Dict[int, str]:
    """
    Build a map from line index to block_id by tracking active branches.
    
    Pure function: creates new data structures, no side effects.
    
    Args:
        func_lines: Function body lines
        
    Returns:
        Dictionary mapping line_index -> block_id ('main', 'if', 'else-if-N', 'else', 'join_point')
    """
    line_to_block = {}
    current_block = 'main'
    brace_depth = 0
    in_branch_block = False
    
    IF_RE = re.compile(r'^\s*if\s*\(')
    ELSE_IF_RE = re.compile(r'^\s*else\s+if\s*\(')
    ELSE_RE = re.compile(r'^\s*else\s*[^{]*')
    
    # Track branch structures to detect join points
    # Each entry: (branch_id, start_idx, start_brace_depth)
    branch_stack = []
    previous_brace_depth = 0
    
    # Track active if-else chain contexts (for nested if statements)
    # Maps brace_depth -> block_prefix (e.g., 'if', 'if-nested')
    block_contexts = {}
    
    for idx, line in enumerate(func_lines):
        clean = strip_comments(line)
        if not clean:
            continue
        
        # Track brace depth BEFORE processing this line
        brace_depth_before = brace_depth
        brace_depth += line.count('{') - line.count('}')
        
        # Check for branch keywords
        is_if = IF_RE.match(clean)
        is_else_if = ELSE_IF_RE.match(clean)
        is_else = ELSE_RE.match(clean)
        
        # Determine if this is a nested if (inside another if-else block)
        # A nested if occurs when we see an if statement while already inside a branch block
        # (i.e., when branch_stack is not empty, meaning we're inside another if-else chain)
        is_nested = len(branch_stack) > 0 and (is_if or is_else_if or is_else)
        
        # Detect when we exit a branch (join point)
        if previous_brace_depth > 0 and brace_depth < previous_brace_depth:
            # Check if we've closed a branch
            while branch_stack:
                branch_id, start_idx, start_depth = branch_stack[-1]
                if brace_depth <= start_depth:
                    # We've exited this branch - mark as join point
                    branch_stack.pop()
                    # Remove block context when we exit
                    if start_depth in block_contexts:
                        del block_contexts[start_depth]
                    # Update current_block to join_point for subsequent lines
                    # (will be applied when we map this line below)
                    if not branch_stack:  # Only set to join_point if we've exited all branches
                        current_block = 'join_point'
                else:
                    break
        
        # Check for branch keywords
        if is_if:
            if is_nested:
                # Nested if - create nested block context
                # Use brace_depth_before as the key for this nesting level
                block_prefix = f'if-nested'
                block_contexts[brace_depth_before] = block_prefix
                current_block = block_prefix
            else:
                current_block = 'if'
                block_contexts[brace_depth_before] = 'if'
            in_branch_block = True
            branch_stack.append((current_block, idx, brace_depth_before))
        elif is_else_if:
            # Find which else-if this is
            else_if_idx = 0
            # Look for else-if statements at the same nesting level
            for prev_idx in range(idx):
                prev_clean = strip_comments(func_lines[prev_idx])
                if prev_clean and ELSE_IF_RE.match(prev_clean):
                    # Check if it's at the same nesting level
                    prev_brace_depth = 0
                    for check_idx in range(prev_idx):
                        prev_brace_depth += func_lines[check_idx].count('{') - func_lines[check_idx].count('}')
                    if prev_brace_depth == brace_depth_before:
                        else_if_idx += 1
            
            if is_nested:
                # Use the block context from the parent if
                parent_prefix = block_contexts.get(brace_depth_before, 'if-nested')
                current_block = f'{parent_prefix}-else-if-{else_if_idx}'
            else:
                current_block = f'else-if-{else_if_idx}'
            in_branch_block = True
            branch_stack.append((current_block, idx, brace_depth_before))
        elif is_else:
            if is_nested:
                # Use the block context from the parent if
                parent_prefix = block_contexts.get(brace_depth_before, 'if-nested')
                current_block = f'{parent_prefix}-else'
            else:
                current_block = 'else'
            in_branch_block = True
            branch_stack.append((current_block, idx, brace_depth_before))
        
        # Map this line to current block
        line_to_block[idx] = current_block
        
        # Update previous brace depth
        previous_brace_depth = brace_depth
        
        # If we've closed all braces and were in a branch, we're at a join point
        if brace_depth <= 0 and in_branch_block and not branch_stack:
            in_branch_block = False
            current_block = 'join_point'
            block_contexts.clear()
    
    return line_to_block


def _normalize_and_verify_block_id(block_id: str, line_idx: int, func_lines: List[str]) -> str:
    """
    Verify and normalize block_id, especially for join_point cases.
    
    Pure function: no side effects.
    
    Args:
        block_id: Block ID from line_to_block map
        line_idx: Line index
        func_lines: Function body lines
        
    Returns:
        Verified block_id (may change 'join_point' to 'main' if not actually a join point)
    """
    if block_id == 'join_point':
        if _is_join_point(line_idx, func_lines):
            return 'join_point'
        else:
            return 'main'
    return block_id


def _match_statement_to_line_exact(
    stmt_norm: str, 
    func_lines: List[str], 
    line_to_block: Dict[int, str]
) -> Optional[Tuple[int, str]]:
    """
    Try exact match of normalized statement to function lines.
    
    Pure function: no side effects.
    
    Args:
        stmt_norm: Normalized statement string
        func_lines: Function body lines
        line_to_block: Map from line index to block_id
        
    Returns:
        Tuple of (line_index, block_id) if match found, None otherwise
    """
    for idx, line in enumerate(func_lines):
        line_clean = strip_comments(line).strip()
        if not line_clean:
            continue
        
        line_norm = ' '.join(line_clean.split())
        if stmt_norm == line_norm:
            block_id = line_to_block.get(idx, 'main')
            block_id = _normalize_and_verify_block_id(block_id, idx, func_lines)
            return (idx, block_id)
    
    return None


def _match_statement_to_line_substring(
    stmt_norm: str, 
    func_lines: List[str], 
    line_to_block: Dict[int, str]
) -> Optional[Tuple[int, str]]:
    """
    Try substring match of normalized statement to function lines.
    
    Pure function: no side effects.
    
    Args:
        stmt_norm: Normalized statement string
        func_lines: Function body lines
        line_to_block: Map from line index to block_id
        
    Returns:
        Tuple of (line_index, block_id) if match found, None otherwise
    """
    # Only try substring match for substantial strings
    if len(stmt_norm) <= 10:
        return None
    
    for idx, line in enumerate(func_lines):
        line_clean = strip_comments(line).strip()
        if not line_clean:
            continue
        
        line_norm = ' '.join(line_clean.split())
        if len(line_norm) <= 10:
            continue
        
        if stmt_norm in line_norm or line_norm in stmt_norm:
            block_id = line_to_block.get(idx, 'main')
            block_id = _normalize_and_verify_block_id(block_id, idx, func_lines)
            return (idx, block_id)
    
    return None


def _match_statement_to_line_by_assignment(
    stmt_line: str, 
    func_lines: List[str], 
    line_to_block: Dict[int, str]
) -> Optional[Tuple[int, str]]:
    """
    Try matching statement to line by assignment variable name.
    
    Pure function: no side effects.
    
    Args:
        stmt_line: Statement line string
        func_lines: Function body lines
        line_to_block: Map from line index to block_id
        
    Returns:
        Tuple of (line_index, block_id) if match found, None otherwise
    """
    if '=' not in stmt_line:
        return None
    
    assign_part = stmt_line.split('=')[0].strip()
    if not assign_part:
        return None
    
    for idx, line in enumerate(func_lines):
        line_clean = strip_comments(line).strip()
        if '=' not in line_clean:
            continue
        
        line_assign_part = line_clean.split('=')[0].strip()
        if assign_part == line_assign_part:
            block_id = line_to_block.get(idx, 'main')
            block_id = _normalize_and_verify_block_id(block_id, idx, func_lines)
            return (idx, block_id)
    
    return None


def _find_block_for_statement(
    stmt: Dict, 
    func_lines: List[str], 
    line_to_block: Dict[int, str]
) -> str:
    """
    Find which block a statement belongs to using multiple matching strategies.
    
    Pure function: no side effects.
    
    Args:
        stmt: Statement dictionary with 'line' field
        func_lines: Function body lines
        line_to_block: Map from line index to block_id
        
    Returns:
        Block ID for the statement
    """
    stmt_line = stmt.get('line', '').strip()
    if not stmt_line:
        return 'main'
    
    stmt_norm = ' '.join(stmt_line.split())
    
    # Strategy 1: Exact match
    match_result = _match_statement_to_line_exact(stmt_norm, func_lines, line_to_block)
    if match_result:
        return match_result[1]
    
    # Strategy 2: Substring match
    match_result = _match_statement_to_line_substring(stmt_norm, func_lines, line_to_block)
    if match_result:
        return match_result[1]
    
    # Strategy 3: Assignment pattern match
    match_result = _match_statement_to_line_by_assignment(stmt_line, func_lines, line_to_block)
    if match_result:
        return match_result[1]
    
    # Default: main block
    return 'main'


def map_statements_to_blocks(
    statements: List[Dict], 
    branches: List[Dict], 
    func_lines: List[str]
) -> Dict[str, List[Dict]]:
    """
    Map statements to their enclosing blocks by tracking active branch while iterating.
    
    Pure function: Creates new data structures, no side effects.
    
    Args:
        statements: List of statement dictionaries with 'line' field
        branches: List of branch dictionaries from extract_branch_structure()
        func_lines: Function body lines
    
    Returns:
        Dictionary mapping block_id -> list of statements in that block
    """
    # Build line-to-block mapping
    line_to_block = _build_line_to_block_map(func_lines)
    
    # Map each statement to its block
    statements_by_block = {}
    for stmt in statements:
        block_id = _find_block_for_statement(stmt, func_lines, line_to_block)
        
        if block_id not in statements_by_block:
            statements_by_block[block_id] = []
        statements_by_block[block_id].append(stmt)
    
    return statements_by_block


def find_final_versions_per_block(statements_by_block: Dict[str, List[Dict]]) -> Dict[str, Dict]:
    """
    Find final version of variable in each block.
    
    Pure function: Creates new data structures, no side effects.
    
    Args:
        statements_by_block: Dictionary from map_statements_to_blocks()
    
    Returns:
        Dictionary mapping block_id -> final statement dictionary
    """
    final_by_block = {}
    
    for block_id, stmts in statements_by_block.items():
        if stmts:
            # Find statement with maximum version number
            final_stmt = max(stmts, key=lambda s: s.get('version', 0))
            final_by_block[block_id] = final_stmt
    
    return final_by_block


def generate_block_based_predicate_pairs(
    src_final_by_block: Dict[str, Dict],
    mut_final_by_block: Dict[str, Dict],
    src_statements: List[Dict],
    mut_statements: List[Dict]
) -> Dict[str, Tuple[str, str]]:
    """
    Generate predicate pairs only for final versions per matched block.
    
    Pure function: Creates new data structures, no side effects.
    
    Args:
        src_final_by_block: Final statements per block for source
        mut_final_by_block: Final statements per block for mutant
        src_statements: All source statements (for indexing)
        mut_statements: All mutant statements (for indexing)
    
    Returns:
        Dictionary mapping mut_ssa_name -> predicate_pair
        This allows us to mark which statements should have predicate pairs
    """
    predicate_pairs = {}
    
    # Match blocks between source and mutant by branch_id
    all_block_ids = set(src_final_by_block.keys()) | set(mut_final_by_block.keys())
    
    for block_id in all_block_ids:
        src_final = src_final_by_block.get(block_id)
        mut_final = mut_final_by_block.get(block_id)
        
        if src_final and mut_final:
            # Both source and mutant have this block - compare final versions
            src_ssa_name = src_final.get('ssa_name')
            mut_ssa_name = mut_final.get('ssa_name')
            
            if src_ssa_name and mut_ssa_name:
                # Use SSA name as key (unique identifier)
                predicate_pairs[mut_ssa_name] = (src_ssa_name, mut_ssa_name)
    
    return predicate_pairs


def get_ssa_versions_for_pairs(pairs: List[Dict], c_file_path: str) -> Dict[Tuple[str, str], Dict]:
    """
    Generate SSA versions for variables where syntax changes occurred.
    
    Args:
        pairs: List of dictionaries from get_unique_function_variable_pairs()
        c_file_path: Path to the C source file
        
    Returns:
        Dictionary mapping (function_name, variable_name) to SSA data
    """
    source_lines = read_c_source(c_file_path)
    func_map = build_function_map(source_lines)
    
    # Extract macros and build macro map for expansion
    macros = get_macros_from_source(source_lines)
    macro_tuples = get_macro_tuples(macros)
    macro_map = build_macro_map(macro_tuples)
    
    # Extract global variables for SSA resolution (CBMC-style: program-wide SSA chain)
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
        
        # Collect ALL assignments first
        src_ssa_all = []
        mut_ssa_all = []
        
        if func_name in func_map:
            # Determine initial version based on variable type
            if var_name == 'return' or var_name.startswith('return') or \
               var_name == 'if_condition' or var_name.startswith('if_condition'):
                version = 1
            else:
                version = 2
            
            for line in func_map[func_name]:
                clean = strip_comments(line)
                if not clean:
                    continue
                
                assign_match = ASSIGN_RE.match(clean)
                if assign_match:
                    lhs = assign_match.group(1)
                    rhs = assign_match.group(2)
                    if normalize_identifiers(lhs) == var_name:
                        # Use function-scoped format for regular variables (e.g., alt_sep_test::1::enabled!0@1#2)
                        ssa_name = f"{func_name}::1::{lhs}!0@1#{version}"
                        src_ssa_all.append({
                            'version': version,
                            'ssa_name': ssa_name,
                            'line': line.rstrip('\n'),
                            'assignment': clean,
                            'lhs': lhs,
                            'rhs': rhs
                        })
                        version += 1
                
                elif var_name == 'return' or var_name.startswith('return'):
                    ret_match = RETURN_RE.match(clean)
                    if ret_match:
                        ret_expr = ret_match.group(1).strip()
                        # Use function name for return value SSA naming (e.g., goto_symex::return_value::Own_Below_Threat!0#1)
                        ssa_name = f"goto_symex::return_value::{func_name}!0#{version}"
                        src_ssa_all.append({
                            'version': version,
                            'ssa_name': ssa_name,
                            'line': line.rstrip('\n'),
                            'assignment': clean,
                            'lhs': 'return',
                            'rhs': ret_expr
                        })
                        version += 1
                
                elif var_name == 'if_condition' or var_name.startswith('if_condition'):
                    if_match = IF_RE.match(clean)
                    else_if_match = ELSE_IF_RE.match(clean)
                    if if_match or else_if_match:
                        cond_expr = (if_match.group(1) if if_match else else_if_match.group(1)).strip()
                        src_ssa_all.append({
                            'version': version,
                            'ssa_name': f"if_condition_{version}",
                            'line': line.rstrip('\n'),
                            'assignment': clean,
                            'lhs': 'if_condition',
                            'rhs': cond_expr
                        })
                        version += 1
        
        # Get mutant function assignments
        if mut_func_name and mut_func_name in func_map:
            if var_name == 'return' or var_name.startswith('return') or \
               var_name == 'if_condition' or var_name.startswith('if_condition'):
                version = 1
            else:
                version = 2
            
            for line in func_map[mut_func_name]:
                clean = strip_comments(line)
                if not clean:
                    continue
                
                assign_match = ASSIGN_RE.match(clean)
                if assign_match:
                    lhs = assign_match.group(1)
                    rhs = assign_match.group(2)
                    if normalize_identifiers(lhs) == var_name:
                        # Use function-scoped format for mutant variables (e.g., alt_sep_test_2::1::enabled_2!0@1#2)
                        # The variable name already has _2 suffix in mutant functions
                        ssa_name = f"{mut_func_name}::1::{lhs}!0@1#{version}"
                        mut_ssa_all.append({
                            'version': version,
                            'ssa_name': ssa_name,
                            'line': line.rstrip('\n'),
                            'assignment': clean,
                            'lhs': lhs,
                            'rhs': rhs
                        })
                        version += 1
                
                elif var_name == 'return' or var_name.startswith('return'):
                    ret_match = RETURN_RE.match(clean)
                    if ret_match:
                        ret_expr = ret_match.group(1).strip()
                        # Use function name with _2 suffix for mutant return value SSA naming (e.g., goto_symex::return_value::Own_Below_Threat_2!0#1)
                        # Extract base function name (remove _2 if present)
                        base_func_name = mut_func_name.rstrip('_2') if mut_func_name.endswith('_2') else mut_func_name
                        ssa_name = f"goto_symex::return_value::{base_func_name}_2!0#{version}"
                        mut_ssa_all.append({
                            'version': version,
                            'ssa_name': ssa_name,
                            'line': line.rstrip('\n'),
                            'assignment': clean,
                            'lhs': 'return_2',
                            'rhs': ret_expr
                        })
                        version += 1
                
                elif var_name == 'if_condition' or var_name.startswith('if_condition'):
                    if_match = IF_RE.match(clean)
                    else_if_match = ELSE_IF_RE.match(clean)
                    if if_match or else_if_match:
                        cond_expr = (if_match.group(1) if if_match else else_if_match.group(1)).strip()
                        mut_ssa_all.append({
                            'version': version,
                            'ssa_name': f"if_condition_2_{version}",
                            'line': line.rstrip('\n'),
                            'assignment': clean,
                            'lhs': 'if_condition_2',
                            'rhs': cond_expr
                        })
                        version += 1
        
        # Compare and include assignments
        # Filter to only include assignments that differ after macro expansion and normalization
        src_ssa = []
        mut_ssa = []
        
        # Build normalized RHS sets for comparison (with macro expansion)
        src_rhs_normalized_set = set()
        for src_stmt in src_ssa_all:
            if 'rhs' in src_stmt:
                rhs_expanded = expand_macros_in_expression(src_stmt['rhs'], macro_map, is_mutant=False)
                rhs_norm = normalize_expr(rhs_expanded)
                src_rhs_normalized_set.add(rhs_norm)
        
        # Build normalized RHS set for checking if mutant statements match any source RHS
        # This helps identify truly unmatched statements vs statements that match a different source position
        src_rhs_normalized_set = set()
        for src_stmt in src_ssa_all:
            if 'rhs' in src_stmt:
                rhs_expanded = expand_macros_in_expression(src_stmt['rhs'], macro_map, is_mutant=False)
                rhs_norm = normalize_expr(rhs_expanded)
                src_rhs_normalized_set.add(rhs_norm)
        
        # Extract branch structures for block-based final version tracking
        src_branches = []
        mut_branches = []
        if func_name in func_map:
            src_branches = extract_branch_structure(func_map[func_name], macro_map, is_mutant=False)
        if mut_func_name and mut_func_name in func_map:
            mut_branches = extract_branch_structure(func_map[mut_func_name], macro_map, is_mutant=True)
        
        # Map statements to blocks and find final versions per block
        src_by_block = map_statements_to_blocks(src_ssa_all, src_branches, func_map.get(func_name, []))
        mut_by_block = map_statements_to_blocks(mut_ssa_all, mut_branches, func_map.get(mut_func_name, []))
        
        src_final_by_block = find_final_versions_per_block(src_by_block)
        mut_final_by_block = find_final_versions_per_block(mut_by_block)
        
        # Generate predicate pairs for final versions in matched blocks
        block_predicate_pairs = generate_block_based_predicate_pairs(
            src_final_by_block, mut_final_by_block, src_ssa_all, mut_ssa_all
        )
        
        # Debug: Ensure we have block predicate pairs for debugging
        # The block_predicate_pairs dict maps mut_ssa_name -> (src_ssa_name, mut_ssa_name)
        
        # Compare assignments positionally and only include those that differ
        # Also derive predicate pairs for matched but different statements
        max_len = max(len(src_ssa_all), len(mut_ssa_all))
        for i in range(max_len):
            src_stmt = src_ssa_all[i] if i < len(src_ssa_all) else None
            mut_stmt = mut_ssa_all[i] if i < len(mut_ssa_all) else None
            
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
                    
                    # PRIORITY 1: Check if this is a final version in a matched block
                    # Block-based predicate pairs take precedence over positional comparison and missing patterns
                    mut_ssa_name = mut_stmt.get('ssa_name')
                    if mut_ssa_name and mut_ssa_name in block_predicate_pairs:
                        # This is a final version in a matched block - use block-based predicate pair
                        mut_stmt['missing_predicate_pair'] = block_predicate_pairs[mut_ssa_name]
                        # Skip other predicate pair generation for final versions
                        continue
                    
                    # PRIORITY 2: Check for missing statement pattern (only for non-final versions)
                    # Only check for missing patterns if this is NOT a final version in a matched block
                    mut_lhs = mut_stmt.get('lhs', '')
                    mut_rhs = mut_stmt.get('rhs', '')
                    mut_rhs_expanded = expand_macros_in_expression(mut_rhs, macro_map, is_mutant=True)
                    mut_rhs_normalized_ws = ' '.join(mut_rhs_expanded.split())
                    
                    # Check for pattern: x = x && φ or x = x || φ
                    and_pattern = re.compile(rf'^{re.escape(mut_lhs)}\s*&&\s*(.+)$', re.IGNORECASE)
                    or_pattern = re.compile(rf'^{re.escape(mut_lhs)}\s*\|\|\s*(.+)$', re.IGNORECASE)
                    is_missing_pattern = bool(and_pattern.match(mut_rhs_normalized_ws) or or_pattern.match(mut_rhs_normalized_ws))
                    
                    if is_missing_pattern:
                            # This is a missing-statement pattern - use pattern matching
                            # Build SSA environment for pattern matching
                            pattern_ssa_env = {}
                            
                            # Add all source variable assignments
                            for prev_src_stmt in src_ssa_all:
                                if 'lhs' in prev_src_stmt:
                                    prev_lhs = prev_src_stmt['lhs']
                                    prev_ssa_name = prev_src_stmt.get('ssa_name', prev_lhs)
                                    pattern_ssa_env[prev_lhs] = prev_ssa_name
                                    normalized_prev_lhs = normalize_identifiers(prev_lhs)
                                    pattern_ssa_env[normalized_prev_lhs] = prev_ssa_name
                            
                            # Add previous mutant versions
                            if mut_lhs:
                                prev_mut_version = None
                                for prev_stmt in mut_ssa_all:
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
    
                                
                            # Derive predicate pair using pattern matching
                            pair = derive_missing_predicate_pair(mut_stmt, pattern_ssa_env, global_vars, macro_map)
                            if pair is not None:
                                mut_stmt['missing_predicate_pair'] = pair
                        # Note: For non-final versions in matched blocks, we don't generate predicate pairs
                        # Only final versions get predicate pairs
            elif src_stmt:
                # Only source exists - include it
                src_ssa.append(src_stmt)
            elif mut_stmt:
                # Only mutant exists at this position - check if it matches any source RHS
                # If it matches, it's not truly unmatched (just at different position) - skip it
                mut_rhs_expanded_check = expand_macros_in_expression(mut_stmt.get('rhs', ''), macro_map, is_mutant=True)
                mut_rhs_norm_check = normalize_expr(mut_rhs_expanded_check)
                
                # If this RHS matches any source RHS, skip it (not a real difference)
                if mut_rhs_norm_check in src_rhs_normalized_set:
                    continue
                
                # This is a truly unmatched statement (missing in source)
                mut_ssa.append(mut_stmt)
                
                # PRIORITY 1: Check if this is a final version in a matched block
                # Block-based predicate pairs take precedence over missing patterns
                mut_ssa_name = mut_stmt.get('ssa_name')
                if mut_ssa_name and mut_ssa_name in block_predicate_pairs:
                    # This is a final version in a matched block - use block-based predicate pair
                    mut_stmt['missing_predicate_pair'] = block_predicate_pairs[mut_ssa_name]
                    # Skip missing pattern check for final versions
                    continue
                
                # PRIORITY 2: Process it with pattern matching to derive correct predicate pair
                # Build SSA environment with previous versions for pattern matching
                # Side-effect free: create new environment dict
                unmatched_ssa_env = {}
                
                # Add all source variable assignments to environment (for identity modeling)
                for prev_src_stmt in src_ssa_all:
                    if 'lhs' in prev_src_stmt:
                        prev_lhs = prev_src_stmt['lhs']
                        prev_ssa_name = prev_src_stmt.get('ssa_name', prev_lhs)
                        unmatched_ssa_env[prev_lhs] = prev_ssa_name
                        normalized_prev_lhs = normalize_identifiers(prev_lhs)
                        unmatched_ssa_env[normalized_prev_lhs] = prev_ssa_name
                
                # Add previous mutant versions up to this point
                var_name = mut_stmt.get('lhs')
                if var_name:
                    # Find previous mutant version
                    prev_mut_version = None
                    for prev_stmt in mut_ssa_all:
                        if prev_stmt == mut_stmt:
                            break
                        if prev_stmt.get('lhs') == var_name:
                            prev_mut_version = prev_stmt.get('ssa_name', var_name)
                    
                    if prev_mut_version:
                        unmatched_ssa_env[var_name] = prev_mut_version
                        normalized_var = normalize_identifiers(var_name)
                        unmatched_ssa_env[normalized_var] = prev_mut_version
                
                # Add global variables
                for global_var in global_vars:
                    unmatched_ssa_env[global_var] = f"{global_var}#2"
                    unmatched_ssa_env[f"{global_var}_2"] = f"{global_var}#2"
                
                # Derive predicate pair using pattern matching (x = x && φ → (True, φ))
                pair = derive_missing_predicate_pair(mut_stmt, unmatched_ssa_env, global_vars, macro_map)
                if pair is not None:
                    mut_stmt['missing_predicate_pair'] = pair
        
        # If no differences found but pairs were identified, include first assignment from each side
        # This handles cases where the difference detection found something but all assignments are identical
        if len(src_ssa) == 0 and len(mut_ssa) == 0:
            if len(src_ssa_all) > 0:
                src_ssa.append(src_ssa_all[0])
            if len(mut_ssa_all) > 0:
                mut_ssa.append(mut_ssa_all[0])
        
        # Integration point: Process unmatched mutant statements for missing-statement differences
        # This applies both when counts differ AND when RHS expressions differ (even with same count)
        # Build SSA environment from source assignments for identity modeling (side-effect free)
        ssa_env = {}
        
        # Add source local variable SSA versions
        for src_stmt in src_ssa_all:
            if 'lhs' in src_stmt:
                lhs = src_stmt['lhs']
                ssa_name = src_stmt.get('ssa_name', lhs)
                # Store previous version for identity modeling
                ssa_env[lhs] = ssa_name
                # Also store normalized name for lookup (e.g., 'need_upward_RA' can be found via 'need_upward_RA_2')
                normalized_lhs = normalize_identifiers(lhs)
                ssa_env[normalized_lhs] = ssa_name
        
        # Add global variable SSA versions to environment
        # CBMC-style: Globals use program-wide SSA versions (#0, #1, #2, ...)
        # For now, we use #2 as a default (assuming they're initialized before use)
        # In a full implementation, this would track actual global SSA versions
        for global_var in global_vars:
            # Check both source and mutant versions
            for var_suffix in ['', '_2']:
                var_name = f"{global_var}{var_suffix}"
                if var_name not in ssa_env:
                    # Default to #2 (assuming initialization happened)
                    # In full CBMC-style, this would track actual versions
                    ssa_env[var_name] = f"{var_name}#2"
                    ssa_env[normalize_identifiers(var_name)] = f"{global_var}#2"
        
        # Identify unmatched mutant statements by comparing RHS expressions
        # A statement is unmatched if its RHS doesn't match any source RHS (normalized)
        # Expand macros before comparison to detect macro-related differences
        src_rhs_normalized = set()
        for src_stmt in src_ssa_all:
            if 'rhs' in src_stmt:
                # Expand macros, then normalize the RHS for comparison (remove _2 suffixes)
                rhs_expanded = expand_macros_in_expression(src_stmt['rhs'], macro_map, is_mutant=False)
                rhs_norm = normalize_expr(rhs_expanded)
                src_rhs_normalized.add(rhs_norm)
        
        # Process unmatched mutant statements (skip those already processed as matched but different)
        # Build set of already-processed mutant statements
        processed_mut_stmts = {id(stmt) for stmt in mut_ssa}
        
        for stmt_mut in mut_ssa_all:
            if 'rhs' not in stmt_mut:
                continue
            
            # Skip if already processed as matched but different
            if id(stmt_mut) in processed_mut_stmts:
                continue
            
            # Expand macros, then normalize mutant RHS for comparison
            mut_rhs_expanded = expand_macros_in_expression(stmt_mut['rhs'], macro_map, is_mutant=True)
            mut_rhs_norm = normalize_expr(mut_rhs_expanded)
            
            # Check if this RHS matches any source RHS (not just positionally)
            # If it matches, it's not truly unmatched - skip it
            is_matched = mut_rhs_norm in src_rhs_normalized
            
            if not is_matched:
                # This is an unmatched mutant statement (missing in source or different RHS)
                # Update SSA environment with previous mutant versions for identity modeling
                # Side-effect free: create new environment dict
                mut_ssa_env = ssa_env.copy()
                
                if 'lhs' in stmt_mut:
                    # Get the most recent version of this variable from mutant statements
                    var_name = stmt_mut['lhs']
                    # Find previous mutant version
                    prev_mut_version = None
                    for prev_stmt in mut_ssa_all:
                        if prev_stmt == stmt_mut:
                            break
                        if prev_stmt.get('lhs') == var_name:
                            prev_mut_version = prev_stmt.get('ssa_name', var_name)
                    
                    # Use previous mutant version or fall back to source version
                    if prev_mut_version:
                        mut_ssa_env[var_name] = prev_mut_version
                    elif var_name not in mut_ssa_env:
                        # Fallback: use normalized variable name
                        normalized_var = normalize_identifiers(var_name)
                        mut_ssa_env[var_name] = mut_ssa_env.get(normalized_var, normalized_var)
                
                # Derive predicate pair with macro expansion and global variable resolution
                pair = derive_missing_predicate_pair(stmt_mut, mut_ssa_env, global_vars, macro_map)
                if pair is not None:
                    # Store predicate pair for SAT assertion generation
                    # This hook allows external code to emit implications: (p_src ≠ p_mut) ⇒ (o_src ≠ o_mut)
                    # The pair is stored in the statement metadata for downstream processing
                    stmt_mut['missing_predicate_pair'] = pair
                    # Note: emit_implication(pair, final_output_pair) would be called here
                    # by the existing SAT assertion generation code
        
        # If there are different numbers of assignments, include all to show the difference
        if len(src_ssa_all) != len(mut_ssa_all):
            # Include all assignments from both sides to show the mismatch
            src_ssa = src_ssa_all[:]  # Copy all
            mut_ssa = mut_ssa_all[:]  # Copy all
        
        # Integration point: Process condition-related differences (if/else-if/else branches)
        # Extract branch structures and derive predicate pairs
        condition_pairs = []
        if func_name in func_map and mut_func_name and mut_func_name in func_map:
            # Extract branches with macro expansion
            src_branches = extract_branch_structure(func_map[func_name], macro_map, is_mutant=False)
            mut_branches = extract_branch_structure(func_map[mut_func_name], macro_map, is_mutant=True)
            
            # Only process if there are branches to compare
            if src_branches or mut_branches:
                # Build comprehensive SSA environment for variable resolution
                # Include all local variables from source and mutant assignments
                branch_ssa_env = ssa_env.copy()
                
                # Add all source variable assignments to environment
                for src_stmt in src_ssa_all:
                    if 'lhs' in src_stmt:
                        lhs = src_stmt['lhs']
                        ssa_name = src_stmt.get('ssa_name', lhs)
                        branch_ssa_env[lhs] = ssa_name
                        # Also add normalized version
                        normalized_lhs = normalize_identifiers(lhs)
                        branch_ssa_env[normalized_lhs] = ssa_name
                
                # Add all mutant variable assignments to environment
                for mut_stmt in mut_ssa_all:
                    if 'lhs' in mut_stmt:
                        lhs = mut_stmt['lhs']
                        ssa_name = mut_stmt.get('ssa_name', lhs)
                        branch_ssa_env[lhs] = ssa_name
                        # Also add normalized version
                        normalized_lhs = normalize_identifiers(lhs)
                        branch_ssa_env[normalized_lhs] = ssa_name
                
                # Extract all variable assignments from function bodies for local variables
                # This ensures variables used in conditions are in the SSA environment
                # Generate SSA names for all local variables in the function
                ASSIGN_RE = re.compile(r'^\s*(\w+)\s*=\s*(.+);')
                
                # Track version numbers for each variable in source function
                # Regular variables start at version 2 (matching main SSA generation logic)
                src_var_versions = {}
                for line in func_map[func_name]:
                    clean = strip_comments(line)
                    if not clean:
                        continue
                    assign_match = ASSIGN_RE.match(clean)
                    if assign_match:
                        lhs = assign_match.group(1)
                        # Initialize version counter for this variable
                        # Regular variables start at version 2 (not 1) to match main SSA generation
                        if lhs not in src_var_versions:
                            src_var_versions[lhs] = 2
                        else:
                            src_var_versions[lhs] += 1
                        
                        version = src_var_versions[lhs]
                        # Generate SSA name: func_name::1::var_name!0@1#version
                        ssa_name = f"{func_name}::1::{lhs}!0@1#{version}"
                        
                        # Add to environment with source variable name as key
                        branch_ssa_env[lhs] = ssa_name
                        normalized_lhs = normalize_identifiers(lhs)
                        branch_ssa_env[normalized_lhs] = ssa_name
                        # Also add with source function prefix for disambiguation
                        branch_ssa_env[f"{func_name}::{lhs}"] = ssa_name
                
                # Track version numbers for each variable in mutant function
                # Regular variables start at version 2 (matching main SSA generation logic)
                mut_var_versions = {}
                for line in func_map[mut_func_name]:
                    clean = strip_comments(line)
                    if not clean:
                        continue
                    assign_match = ASSIGN_RE.match(clean)
                    if assign_match:
                        lhs = assign_match.group(1)
                        # Initialize version counter for this variable
                        # Regular variables start at version 2 (not 1) to match main SSA generation
                        if lhs not in mut_var_versions:
                            mut_var_versions[lhs] = 2
                        else:
                            mut_var_versions[lhs] += 1
                        
                        version = mut_var_versions[lhs]
                        # Generate SSA name: mut_func_name::1::var_name!0@1#version
                        ssa_name = f"{mut_func_name}::1::{lhs}!0@1#{version}"
                        
                        # Add to environment with mutant variable name as key
                        branch_ssa_env[lhs] = ssa_name
                        normalized_lhs = normalize_identifiers(lhs)
                        branch_ssa_env[normalized_lhs] = ssa_name
                        # Also add with mutant function prefix for disambiguation
                        branch_ssa_env[f"{mut_func_name}::{lhs}"] = ssa_name
                
                # Create separate SSA environments for source and mutant predicates
                # This ensures source predicates use source SSA names and mutant predicates use mutant SSA names
                src_ssa_env = {}
                mut_ssa_env = {}
                
                # Build source SSA environment (source function variables)
                for lhs, version in src_var_versions.items():
                    ssa_name = f"{func_name}::1::{lhs}!0@1#{version}"
                    src_ssa_env[lhs] = ssa_name
                    normalized_lhs = normalize_identifiers(lhs)
                    src_ssa_env[normalized_lhs] = ssa_name
                
                # Build mutant SSA environment (mutant function variables)
                for lhs, version in mut_var_versions.items():
                    ssa_name = f"{mut_func_name}::1::{lhs}!0@1#{version}"
                    mut_ssa_env[lhs] = ssa_name
                    normalized_lhs = normalize_identifiers(lhs)
                    mut_ssa_env[normalized_lhs] = ssa_name
                
                # Add globals to both environments
                for global_var in global_vars:
                    for var_suffix in ['', '_2']:
                        var_name = f"{global_var}{var_suffix}"
                        ssa_version = branch_ssa_env.get(var_name, f"{var_name}#2")
                        src_ssa_env[var_name] = ssa_version
                        mut_ssa_env[var_name] = ssa_version
                        normalized_var = normalize_identifiers(var_name)
                        src_ssa_env[normalized_var] = ssa_version
                        mut_ssa_env[normalized_var] = ssa_version
                
                # Derive condition predicate pairs
                # Pass separate SSA environments for source and mutant to ensure correct SSA names
                pairs = derive_condition_predicate_pairs(src_branches, mut_branches, branch_ssa_env, global_vars,
                                                         src_ssa_env, mut_ssa_env)
                
                # Store condition predicate pairs for SAT assertion generation
                # Each pair represents (p_src ≠ p_mut) ⇒ (o_src ≠ o_mut)
                if pairs:
                    condition_pairs = pairs
                    # Note: emit_implication((p_src, p_mut), final_output_pair) would be called here
                    # for each pair by the existing SAT assertion generation code
        
        ssa_results[key] = {
            'function': func_name,
            'mutant_function': mut_func_name,
            'variable_name': var_name,
            'source_ssa': src_ssa,
            'mutant_ssa': mut_ssa,
            'condition_predicate_pairs': condition_pairs  # New field for condition differences
        }
    
    return ssa_results

