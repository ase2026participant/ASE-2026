"""Function and macro difference detection."""

import re
from typing import List, Dict, Tuple, Optional
from .parser import (
    read_c_source, build_function_map, extract_assignments,
    normalize_identifiers, split_top_level_and, strip_comments
)


def get_macros_from_source(source_lines: List[str]) -> List[str]:
    """
    Extract #define macros from source lines.
    
    Args:
        source_lines: List of source code lines
        
    Returns:
        List of macro definition lines
    """
    return [line for line in source_lines if line.startswith("#define")]


def get_macro_tuples(macros: List[str]) -> List[Tuple[str, str]]:
    """
    Parse macro definitions into (name, value) tuples.
    
    Args:
        macros: List of macro definition lines
        
    Returns:
        List of (macro_name, macro_value) tuples
    """
    def get_macro_component_tuple(macro_components: List[str]) -> Tuple[str, str]:
        """Extract macro name and value from components."""
        macro_strs = ' '.join([component for component in macro_components if component]).split(" ")
        if len(macro_strs) >= 2:
            return (macro_strs[0], macro_strs[1])
        return (macro_strs[0], '') if macro_strs else ('', '')
    
    macro_tuples = []
    for macro in macros:
        macro_without_comments = re.sub(r"/\*.*?\*/", "", macro.strip("'")).rstrip()
        macro_components = macro_without_comments.split(" ")[1:]
        if macro_components:
            macro_tuple = get_macro_component_tuple(macro_components)
            if macro_tuple[0]:
                macro_tuples.append(macro_tuple)
    return macro_tuples


def find_macro_differences(macro_tuples: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """
    Find macros that differ between source and mutant versions.
    
    Args:
        macro_tuples: List of (macro_name, macro_value) tuples
        
    Returns:
        List of (source_macro_name, mutant_macro_name) tuples for differing macros
    """
    diff_micros_tuples = []
    macro_hash = {}
    
    for macro_tuple in macro_tuples:
        key = macro_tuple[0].split("_2")[0]
        if key in macro_hash:
            if macro_hash[key] != macro_tuple[1]:
                diff_micros_tuples.append((key, macro_tuple[0]))
        else:
            macro_hash[macro_tuple[0]] = macro_tuple[1]
    
    return diff_micros_tuples


def build_macro_map(macro_tuples: List[Tuple[str, str]]) -> Dict[str, str]:
    """
    Build a mapping from macro names to their values.
    
    Side-effect free: Returns a new dictionary without modifying input.
    
    Args:
        macro_tuples: List of (macro_name, macro_value) tuples
        
    Returns:
        Dictionary mapping macro_name -> macro_value
    """
    macro_map = {}
    for macro_name, macro_value in macro_tuples:
        macro_map[macro_name] = macro_value
    return macro_map


def expand_macros_in_expression(expr: str, macro_map: Dict[str, str], is_mutant: bool = False) -> str:
    """
    Expand macro names in an expression to their values.
    
    Side-effect free: Returns a new string without modifying input.
    
    This function replaces macro names with their values. For mutant functions,
    it expands both source macros (without _2) and mutant macros (with _2).
    
    Args:
        expr: Expression string that may contain macro names
        macro_map: Dictionary mapping macro_name -> macro_value
        is_mutant: If True, also expand source macros (without _2 suffix)
                   by looking for their mutant versions (with _2 suffix)
        
    Returns:
        Expression with macros expanded to their values
    """
    if not expr or not macro_map:
        return expr
    
    result = expr
    # Pattern to match macro names (word boundaries to avoid partial matches)
    identifier_pattern = re.compile(r'\b([A-Za-z_][A-Za-z0-9_]*)\b')
    
    def replace_macro(match):
        macro_name = match.group(1)
        
        # Direct lookup: check if macro_name exists in macro_map
        if macro_name in macro_map:
            return macro_map[macro_name]
        
        # For mutant functions: try to expand source macros by looking for _2 version
        if is_mutant:
            # If this is a source macro name (without _2), try to find mutant version
            mutant_macro_name = macro_name + "_2"
            if mutant_macro_name in macro_map:
                return macro_map[mutant_macro_name]
        
        # For source functions: try to expand mutant macros by removing _2
        if not is_mutant and macro_name.endswith("_2"):
            source_macro_name = macro_name[:-2]
            if source_macro_name in macro_map:
                return macro_map[source_macro_name]
        
        # Macro not found, return original
        return macro_name
    
    # Replace all macro occurrences
    result = identifier_pattern.sub(replace_macro, result)
    return result


def find_function_differences(func_map: Dict[str, List[str]], macro_map: Optional[Dict[str, str]] = None) -> List[Dict]:
    """
    Find assignment differences between source and mutant functions.
    
    Side-effect free: Returns new data structures without modifying inputs.
    
    Args:
        func_map: Dictionary mapping function names to their body lines
        macro_map: Optional dictionary mapping macro_name -> macro_value for macro expansion
        
    Returns:
        List of difference dictionaries
    """
    func_diffs = []
    
    for fname, src_lines in func_map.items():
        if fname.endswith("_2"):
            continue
        
        mutant = fname + "_2"
        if mutant not in func_map:
            continue
        
        src_assigns = extract_assignments(src_lines)
        mut_assigns = extract_assignments(func_map[mutant])
        
        # Build index of assignments by normalized LHS for quick lookup
        src_by_norm_lhs = {}
        for idx, src_data in enumerate(src_assigns):
            norm_lhs = normalize_identifiers(src_data["lhs"])
            if norm_lhs not in src_by_norm_lhs:
                src_by_norm_lhs[norm_lhs] = []
            src_by_norm_lhs[norm_lhs].append((idx, src_data))
        
        mut_by_norm_lhs = {}
        for idx, mut_data in enumerate(mut_assigns):
            norm_lhs = normalize_identifiers(mut_data["lhs"])
            if norm_lhs not in mut_by_norm_lhs:
                mut_by_norm_lhs[norm_lhs] = []
            mut_by_norm_lhs[norm_lhs].append((idx, mut_data))
        
        # Compare assignments: for each normalized LHS, compare all assignments positionally
        # Also detect when one side has more assignments than the other
        all_norm_lhs = set(src_by_norm_lhs.keys()) | set(mut_by_norm_lhs.keys())
        
        for norm_lhs in all_norm_lhs:
            src_list = src_by_norm_lhs.get(norm_lhs, [])
            mut_list = mut_by_norm_lhs.get(norm_lhs, [])
            
            # If variable exists in one but not the other, it's a difference
            if not src_list and mut_list:
                # Variable only in mutant
                for mut_idx, mut_data in mut_list:
                    func_diffs.append({
                        "function": fname,
                        "mutant": mutant,
                        "variable": norm_lhs,
                        "source_line": None,
                        "mutant_line": mut_data["line"]
                    })
                continue
            elif src_list and not mut_list:
                # Variable only in source
                for src_idx, src_data in src_list:
                    func_diffs.append({
                        "function": fname,
                        "mutant": mutant,
                        "variable": norm_lhs,
                        "source_line": src_data["line"],
                        "mutant_line": None
                    })
                continue
            
            # Compare corresponding assignments (by position)
            max_len = max(len(src_list), len(mut_list))
            for i in range(max_len):
                if i < len(src_list) and i < len(mut_list):
                    # Both exist, compare them
                    src_idx, src_data = src_list[i]
                    mut_idx, mut_data = mut_list[i]
                    
                    # Expand macros before normalization and comparison
                    src_rhs_expanded = expand_macros_in_expression(src_data["rhs"], macro_map or {}, is_mutant=False)
                    mut_rhs_expanded = expand_macros_in_expression(mut_data["rhs"], macro_map or {}, is_mutant=True)
                    
                    src_rhs_n = normalize_identifiers(src_rhs_expanded)
                    mut_rhs_n = normalize_identifiers(mut_rhs_expanded)
                    
                    src_terms = set(split_top_level_and(src_rhs_n))
                    mut_terms = set(split_top_level_and(mut_rhs_n))
                    
                    if src_terms != mut_terms:
                        func_diffs.append({
                            "function": fname,
                            "mutant": mutant,
                            "variable": norm_lhs,
                            "source_line": src_data["line"],
                            "mutant_line": mut_data["line"]
                        })
                elif i < len(src_list):
                    # Source has more assignments
                    src_idx, src_data = src_list[i]
                    func_diffs.append({
                        "function": fname,
                        "mutant": mutant,
                        "variable": norm_lhs,
                        "source_line": src_data["line"],
                        "mutant_line": None
                    })
                elif i < len(mut_list):
                    # Mutant has more assignments
                    mut_idx, mut_data = mut_list[i]
                    func_diffs.append({
                        "function": fname,
                        "mutant": mutant,
                        "variable": norm_lhs,
                        "source_line": None,
                        "mutant_line": mut_data["line"]
                    })
    
    return func_diffs


def find_macro_usage(func_map: Dict[str, List[str]], 
                     diff_micros_tuples: List[Tuple[str, str]]) -> List[Dict]:
    """
    Find where differing macros are used in functions.
    
    Args:
        func_map: Dictionary mapping function names to their body lines
        diff_micros_tuples: List of (source_macro, mutant_macro) tuples
        
    Returns:
        List of macro usage dictionaries
    """
    ASSIGN_LHS_RE = re.compile(r'^\s*(\w+)\s*=')
    IF_GUARD_RE = re.compile(r'^\s*if\s*\((.*)\)')
    
    def extract_assigned_variable(line: str) -> Optional[str]:
        m = ASSIGN_LHS_RE.match(line)
        if m:
            return m.group(1)
        if IF_GUARD_RE.match(line):
            return "<if-guard>"
        return None
    
    macro_res = []
    for src_m, mut_m in diff_micros_tuples:
        macro_res.append((
            src_m,
            re.compile(rf'\b{re.escape(src_m)}\b'),
            mut_m,
            re.compile(rf'\b{re.escape(mut_m)}\b')
        ))
    
    macro_hits = []
    for fname, lines in func_map.items():
        is_mutant_func = fname.endswith("_2")
        
        for line in lines:
            clean = strip_comments(line)
            if not clean.strip():
                continue
            
            var = extract_assigned_variable(clean)
            
            for src_m, src_rx, mut_m, mut_rx in macro_res:
                if not is_mutant_func and src_rx.search(clean):
                    macro_hits.append({
                        "function": fname,
                        "side": "source",
                        "macro": src_m,
                        "line": line.rstrip("\n"),
                        "variable": var
                    })
                
                if is_mutant_func and mut_rx.search(clean):
                    macro_hits.append({
                        "function": fname,
                        "side": "mutant",
                        "macro": mut_m,
                        "line": line.rstrip("\n"),
                        "variable": var
                    })
    
    return macro_hits


def merge_function_and_macro_diffs(func_diffs: List[Dict], 
                                   macro_hits: List[Dict]) -> List[Dict]:
    """
    Merge function differences and macro usage into unified results.
    
    Args:
        func_diffs: List of function difference dictionaries
        macro_hits: List of macro usage dictionaries
        
    Returns:
        List of merged result dictionaries
    """
    def index_function_diffs(func_diffs):
        idx = {}
        for fd in func_diffs:
            idx.setdefault(fd["function"], []).append(fd)
        return idx
    
    def index_macro_hits_by_function(macro_hits):
        idx = {}
        for h in macro_hits:
            fname = h["function"]
            idx.setdefault(fname, {"source": [], "mutant": []})
            idx[fname][h["side"]].append({
                "macro": h["macro"],
                "line": h["line"],
                "variable": h["variable"]
            })
        return idx
    
    func_idx = index_function_diffs(func_diffs)
    macro_idx = index_macro_hits_by_function(macro_hits)
    
    results = []
    
    # Collect all source function names
    source_funcs = set()
    for fname in func_idx.keys():
        source_funcs.add(fname)
    for fname in macro_idx.keys():
        if fname.endswith("_2"):
            source_funcs.add(fname[:-2])
        else:
            source_funcs.add(fname)
    
    # Process source functions
    for src_func in source_funcs:
        mut_func = src_func + "_2"
        
        fds = func_idx.get(src_func, [None])
        src_macros = macro_idx.get(src_func, {}).get("source", [])
        mut_macros = macro_idx.get(mut_func, {}).get("mutant", [])
        
        if not src_macros and not mut_macros:
            macro_pairs = [(None, None)]
        elif src_macros and mut_macros:
            macro_pairs = list(zip(src_macros, mut_macros))
        else:
            macro_pairs = [(src_macros[0] if src_macros else None,
                            mut_macros[0] if mut_macros else None)]
        
        # If no function diffs, still create entries for macro diffs
        if not fds:
            fds = [None]
        
        for fd in fds:
            for sm, mm in macro_pairs:
                results.append({
                    "function": src_func,
                    "mutant": mut_func if (mut_func in macro_idx or fd) else None,
                    "function_diff": (
                        {
                            "variable": fd["variable"],
                            "source_line": fd["source_line"],
                            "mutant_line": fd["mutant_line"]
                        } if fd else None
                    ),
                    "macro_diff": (
                        {
                            "function_src": src_func,
                            "function_mut": mut_func,
                            "macro_src": sm.get("macro") if sm else None,
                            "macro_mut": mm.get("macro") if mm else None,
                            "variable_src": sm.get("variable") if sm else None,
                            "variable_mut": mm.get("variable") if mm else None,
                            "source_line": sm.get("line") if sm else None,
                            "mutant_line": mm.get("line") if mm else None
                        } if sm or mm else None
                    )
                })
    
    return results

