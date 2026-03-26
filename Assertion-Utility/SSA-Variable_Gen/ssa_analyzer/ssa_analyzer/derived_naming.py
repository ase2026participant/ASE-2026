"""
Derived variable naming scheme that incorporates:
- Scope / Frame structure
- Call-context index
- Existing SSA version (already computed elsewhere)

READ-ONLY analysis only - no code modification.
"""

import re
from typing import List, Dict, Tuple, Optional, Set
from .parser import (
    read_c_source, build_function_map, strip_comments,
    normalize_identifiers
)
# Import locally to avoid circular dependency
# from . import get_ssa_versions_for_file


class FramePath:
    """
    Represents a frame path as a symbolic structure.
    Frames are created at: function entry, if/else if/else, ternary, short-circuit, early return.
    """
    
    def __init__(self, function_name: str):
        """Initialize frame path with function entry."""
        self.path_components: List[str] = [function_name]
    
    def add_if_then(self, line_number: int):
        """Add if.then branch to frame path."""
        self.path_components.append(f"if@L{line_number}.then")
    
    def add_if_else(self, line_number: int):
        """Add if.else branch to frame path."""
        self.path_components.append(f"if@L{line_number}.else")
    
    def add_else_if(self, line_number: int, index: int):
        """Add else-if branch to frame path."""
        self.path_components.append(f"else-if@{line_number}-{index}")
    
    def add_ternary_then(self, line_number: int):
        """Add ternary ? branch to frame path."""
        self.path_components.append(f"ternary@L{line_number}.then")
    
    def add_ternary_else(self, line_number: int):
        """Add ternary : branch to frame path."""
        self.path_components.append(f"ternary@L{line_number}.else")
    
    def add_shortcircuit_and(self, line_number: int):
        """Add short-circuit && branch to frame path."""
        self.path_components.append(f"shortcircuit-and@L{line_number}")
    
    def add_shortcircuit_or(self, line_number: int):
        """Add short-circuit || branch to frame path."""
        self.path_components.append(f"shortcircuit-or@L{line_number}")
    
    def add_early_return(self, line_number: int):
        """Add early return to frame path."""
        self.path_components.append(f"return@L{line_number}")
    
    def to_string(self) -> str:
        """Convert frame path to normalized string representation."""
        return "/".join(self.path_components)
    
    def copy(self) -> 'FramePath':
        """Create a copy of this frame path."""
        new_path = FramePath("")
        new_path.path_components = self.path_components.copy()
        return new_path


class CallContextTracker:
    """
    Tracks call-context index per frame.
    Call index resets when entering a new frame.
    """
    
    def __init__(self):
        """Initialize call context tracker."""
        self.call_index = 0
    
    def reset(self):
        """Reset call index (when entering new frame)."""
        self.call_index = 0
    
    def next_call(self) -> int:
        """Get next call index and increment."""
        current = self.call_index
        self.call_index += 1
        return current
    
    def get_current_index(self) -> int:
        """Get current call index without incrementing."""
        return self.call_index


def extract_line_number(line: str, func_lines: List[str], func_start_index: int, all_lines: List[str]) -> int:
    """
    Extract line number for a given line within a function.
    
    Args:
        line: The line content
        func_lines: Lines of the function body
        func_start_index: Index in all_lines where function starts
        all_lines: All lines from the source file
        
    Returns:
        Line number (1-indexed)
    """
    # Find the index of this line within the function
    try:
        func_index = func_lines.index(line)
        # Calculate absolute line number
        return func_start_index + func_index + 1
    except ValueError:
        # Fallback: try to find similar line
        for i, l in enumerate(func_lines):
            if line.strip() in l or l.strip() in line:
                return func_start_index + i + 1
        return func_start_index + 1


def detect_ternary(expr: str) -> bool:
    """
    Detect if expression contains a ternary operator.
    
    Args:
        expr: Expression string
        
    Returns:
        True if ternary operator found
    """
    # Simple detection: look for ? : pattern (respecting parentheses)
    depth = 0
    found_q = False
    for i, char in enumerate(expr):
        if char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
        elif char == '?' and depth == 0:
            found_q = True
        elif char == ':' and depth == 0 and found_q:
            return True
    return False


def detect_shortcircuit(expr: str) -> Tuple[bool, bool]:
    """
    Detect short-circuit operators in expression.
    
    Args:
        expr: Expression string
        
    Returns:
        Tuple of (has_and, has_or) indicating presence of && and ||
    """
    # Detect top-level && and || (respecting parentheses)
    depth = 0
    has_and = False
    has_or = False
    
    i = 0
    while i < len(expr):
        if expr[i] == '(':
            depth += 1
        elif expr[i] == ')':
            depth -= 1
        elif depth == 0:
            if i < len(expr) - 1 and expr[i:i+2] == '&&':
                has_and = True
                i += 1
            elif i < len(expr) - 1 and expr[i:i+2] == '||':
                has_or = True
                i += 1
        i += 1
    
    return (has_and, has_or)


def find_function_start_index(func_name: str, all_source_lines: List[str]) -> int:
    """
    Find the starting line index of a function in the source.
    
    Args:
        func_name: Function name
        all_source_lines: All lines from source file
        
    Returns:
        Index (0-based) where function starts
    """
    FUNC_HEADER_RE = re.compile(
        r'^\s*(?:static\s+|inline\s+|extern\s+)?[\w\*\s]+?\s+'
        rf'{re.escape(func_name)}\s*\('
    )
    
    for i, line in enumerate(all_source_lines):
        if FUNC_HEADER_RE.search(line):
            return i
    return 0


def extract_function_calls(expr: str) -> List[str]:
    """
    Extract function call names from an expression.
    
    Args:
        expr: Expression string
        
    Returns:
        List of function names being called
    """
    # Pattern: identifier followed by (
    func_pattern = re.compile(r'\b([A-Za-z_][A-Za-z0-9_]*)\s*\(')
    matches = func_pattern.findall(expr)
    return matches


def build_frame_paths_for_function(
    func_lines: List[str],
    func_name: str,
    func_start_index: int,
    all_source_lines: List[str]
) -> List[Tuple[FramePath, int, str]]:
    """
    Build frame paths for all statements in a function.
    
    Args:
        func_lines: Lines of the function body
        func_name: Name of the function
        func_start_index: Index in all_source_lines where function starts
        all_source_lines: All lines from source file (for line numbers)
        
    Returns:
        List of (frame_path, line_number, line_content) tuples
    """
    ASSIGN_RE = re.compile(r'^\s*(\w+)\s*=\s*(.+);')
    RETURN_RE = re.compile(r'^\s*return\s+(.+);')
    IF_RE = re.compile(r'^\s*if\s*\((.+)\)')
    ELSE_IF_RE = re.compile(r'^\s*else\s+if\s*\((.+)\)')
    ELSE_RE = re.compile(r'^\s*else\s*[^{]*')
    
    frame_paths = []
    # Use a stack to track nested control structures
    frame_stack = [FramePath(func_name)]
    brace_depth = 0
    else_if_index = 0
    pending_if_line = None
    
    for line in func_lines:
        clean = strip_comments(line)
        if not clean:
            continue
        
        line_num = extract_line_number(line, func_lines, func_start_index, all_source_lines)
        
        # Track brace depth
        brace_depth += line.count('{') - line.count('}')
        
        # Get current frame from stack
        current_frame = frame_stack[-1]
        
        # Check for if statement
        if_match = IF_RE.match(clean)
        if if_match:
            # Create new frame for if.then branch
            then_frame = current_frame.copy()
            then_frame.add_if_then(line_num)
            frame_stack.append(then_frame)
            pending_if_line = line_num
            else_if_index = 0
            continue
        
        # Check for else-if
        else_if_match = ELSE_IF_RE.match(clean)
        if else_if_match:
            # Pop the current frame (which should be if.then or previous else-if)
            if len(frame_stack) > 1:
                frame_stack.pop()
            # Create new frame for else-if branch
            else_if_frame = frame_stack[-1].copy()
            else_if_frame.add_else_if(line_num, else_if_index)
            frame_stack.append(else_if_frame)
            else_if_index += 1
            continue
        
        # Check for else
        else_match = ELSE_RE.match(clean)
        if else_match:
            # Pop the current frame (which should be if.then or else-if)
            if len(frame_stack) > 1:
                frame_stack.pop()
            # Create new frame for else branch
            else_frame = frame_stack[-1].copy()
            else_frame.add_if_else(line_num)
            frame_stack.append(else_frame)
            continue
        
        # Check if we're exiting a control structure
        # When brace_depth returns to 0 after being > 0, we've exited a block
        # But we need to be careful - only pop if we were in a control structure
        # For now, we'll track this more carefully by checking when we close braces
        # that match the opening of control structures
        
        # Get current frame (may have changed due to control structures)
        current_frame = frame_stack[-1]
        
        # Check for return statement
        return_match = RETURN_RE.match(clean)
        if return_match:
            # Early return creates a new frame
            return_frame = current_frame.copy()
            return_frame.add_early_return(line_num)
            frame_paths.append((return_frame, line_num, line))
            continue
        
        # Get current frame (may have changed due to control structures)
        current_frame = frame_stack[-1]
        
        # Check for assignments
        assign_match = ASSIGN_RE.match(clean)
        if assign_match:
            lhs = assign_match.group(1)
            rhs = assign_match.group(2)
            
            # Check for ternary in RHS
            if detect_ternary(rhs):
                # Create frames for ternary branches
                then_frame = current_frame.copy()
                then_frame.add_ternary_then(line_num)
                else_frame = current_frame.copy()
                else_frame.add_ternary_else(line_num)
                # Add both frames (representing both execution paths)
                frame_paths.append((then_frame, line_num, line))
                frame_paths.append((else_frame, line_num, line))
            else:
                # Check for short-circuit operators
                has_and, has_or = detect_shortcircuit(rhs)
                if has_and:
                    sc_frame = current_frame.copy()
                    sc_frame.add_shortcircuit_and(line_num)
                    frame_paths.append((sc_frame, line_num, line))
                elif has_or:
                    sc_frame = current_frame.copy()
                    sc_frame.add_shortcircuit_or(line_num)
                    frame_paths.append((sc_frame, line_num, line))
                else:
                    # Regular assignment
                    frame_paths.append((current_frame, line_num, line))
    
    return frame_paths


def get_ssa_version_from_existing(
    var_name: str,
    func_name: str,
    ssa_results: Dict[Tuple[str, str], Dict],
    assignment_line: str
) -> Optional[str]:
    """
    Extract SSA version from existing SSA results.
    
    Args:
        var_name: Variable name
        func_name: Function name
        ssa_results: Results from get_ssa_versions_for_file()
        assignment_line: The assignment line to match
        
    Returns:
        SSA version string (e.g., "v2") or None if not found
    """
    key = (func_name, var_name)
    if key not in ssa_results:
        return None
    
    data = ssa_results[key]
    
    # Try to match by line content
    for ssa_entry in data.get('source_ssa', []):
        if 'line' in ssa_entry and assignment_line.strip() in ssa_entry['line']:
            version = ssa_entry.get('version', 0)
            return f"v{version}"
    
    # Fallback: use first version
    if data.get('source_ssa'):
        version = data['source_ssa'][0].get('version', 0)
        return f"v{version}"
    
    return None


def generate_derived_names(
    c_file_path: str,
    ssa_results: Optional[Dict[Tuple[str, str], Dict]] = None,
    only_diff_variables: bool = True
) -> List[Dict]:
    """
    Generate derived variable names for assignments and function returns.
    
    Args:
        c_file_path: Path to C source file
        ssa_results: Optional pre-computed SSA results. If None, will compute them.
        only_diff_variables: If True, only include variables that differ between source and mutant.
                           Default: True (only diff variables)
        
    Returns:
        List of dictionaries with derived name metadata:
        For variable assignments:
        {
            "derived_name": str,
            "original_variable": str,
            "function": str,
            "source_line": int,
            "frame_path": str,
            "ssa_version": str
        }
        For function returns:
        {
            "derived_name": str,
            "callee": str,
            "function": str,
            "source_line": int,
            "frame_path": str,
            "call_context_index": int,
            "ssa_version": str
        }
    """
    if ssa_results is None:
        # Import locally to avoid circular dependency
        from . import get_ssa_versions_for_file
        ssa_results = get_ssa_versions_for_file(c_file_path)
    
    # Build set of (function, variable) pairs that have differences
    diff_variable_set = set(ssa_results.keys()) if only_diff_variables else None
    
    # Also build a set of function names that have differences (for return statements)
    diff_function_set = set()
    if diff_variable_set:
        for func_name, var_name in diff_variable_set:
            diff_function_set.add(func_name)
    
    source_lines = read_c_source(c_file_path)
    func_map = build_function_map(source_lines)
    
    ASSIGN_RE = re.compile(r'^\s*(\w+)\s*=\s*(.+);')
    RETURN_RE = re.compile(r'^\s*return\s+(.+);')
    
    results = []
    
    # Process each function (skip mutant functions ending with _2)
    for func_name, func_lines in func_map.items():
        if func_name.endswith("_2"):
            continue
        
        # Skip functions that don't have differences if filtering is enabled
        if only_diff_variables and func_name not in diff_function_set:
            continue
        
        # Find function start index
        func_start_index = find_function_start_index(func_name, source_lines)
        
        # Build frame paths for this function
        frame_statements = build_frame_paths_for_function(
            func_lines, func_name, func_start_index, source_lines
        )
        
        # Track call context per frame
        call_contexts: Dict[str, CallContextTracker] = {}
        
        for frame_path, line_num, line in frame_statements:
            clean = strip_comments(line)
            if not clean:
                continue
            
            frame_key = frame_path.to_string()
            if frame_key not in call_contexts:
                call_contexts[frame_key] = CallContextTracker()
            
            call_tracker = call_contexts[frame_key]
            
            # Check for assignment
            assign_match = ASSIGN_RE.match(clean)
            if assign_match:
                lhs = assign_match.group(1)
                rhs = assign_match.group(2)
                
                # Check if RHS contains function calls (function return usage)
                func_calls = extract_function_calls(rhs)
                
                if func_calls:
                    # Track function return values used in assignment
                    # Only include if the assignment variable is in diff set
                    var_key = (func_name, lhs)
                    if not only_diff_variables or var_key in diff_variable_set:
                        for callee in func_calls:
                            call_index = call_tracker.next_call()
                            
                            # Get SSA version for the return value
                            # Try to find return variable in SSA results for the callee
                            ssa_version = "v1"  # Default
                            ret_key = (callee, "return")
                            if ret_key in ssa_results:
                                ret_data = ssa_results[ret_key]
                                if ret_data.get('source_ssa'):
                                    version = ret_data['source_ssa'][0].get('version', 1)
                                    ssa_version = f"v{version}"
                            
                            # Build derived name for function return usage
                            derived_name = (
                                f"ret_{callee}__FP={frame_key}__CI=call{call_index}__SSA={ssa_version}"
                            )
                            
                            results.append({
                                "derived_name": derived_name,
                                "callee": callee,
                                "function": func_name,
                                "source_line": line_num,
                                "frame_path": frame_key,
                                "call_context_index": call_index,
                                "ssa_version": ssa_version
                            })
                
                # Also track the variable assignment itself
                # Only include if this variable is in the diff set
                var_key = (func_name, lhs)
                if not only_diff_variables or var_key in diff_variable_set:
                    # Get SSA version
                    ssa_version = get_ssa_version_from_existing(
                        lhs, func_name, ssa_results, line
                    ) or "v0"
                    
                    # Build derived name
                    derived_name = f"{lhs}__FP={frame_key}__SSA={ssa_version}"
                    
                    results.append({
                        "derived_name": derived_name,
                        "original_variable": lhs,
                        "function": func_name,
                        "source_line": line_num,
                        "frame_path": frame_key,
                        "ssa_version": ssa_version
                    })
            
            # Check for return statement
            # Only include if this function's return is in the diff set
            return_match = RETURN_RE.match(clean)
            if return_match:
                ret_key = (func_name, "return")
                if not only_diff_variables or ret_key in diff_variable_set:
                    ret_expr = return_match.group(1).strip()
                    
                    # Extract function calls from return expression
                    func_calls = extract_function_calls(ret_expr)
                    
                    if func_calls:
                        # Process each function call in the return
                        for callee in func_calls:
                            call_index = call_tracker.next_call()
                            
                            # Get SSA version for return value
                            # Try to find return variable in SSA results
                            ssa_version = "v1"  # Default for returns
                            if ret_key in ssa_results:
                                ret_data = ssa_results[ret_key]
                                if ret_data.get('source_ssa'):
                                    version = ret_data['source_ssa'][0].get('version', 1)
                                    ssa_version = f"v{version}"
                            
                            # Build derived name for return
                            derived_name = (
                                f"ret_{callee}__FP={frame_key}__CI=call{call_index}__SSA={ssa_version}"
                            )
                            
                            results.append({
                                "derived_name": derived_name,
                                "callee": callee,
                                "function": func_name,
                                "source_line": line_num,
                                "frame_path": frame_key,
                                "call_context_index": call_index,
                                "ssa_version": ssa_version
                            })
                    else:
                        # Return without function call - treat as regular return
                        ssa_version = "v1"
                        if ret_key in ssa_results:
                            ret_data = ssa_results[ret_key]
                            if ret_data.get('source_ssa'):
                                version = ret_data['source_ssa'][0].get('version', 1)
                                ssa_version = f"v{version}"
                        
                        derived_name = f"ret__FP={frame_key}__SSA={ssa_version}"
                        
                        results.append({
                            "derived_name": derived_name,
                            "callee": None,
                            "function": func_name,
                            "source_line": line_num,
                            "frame_path": frame_key,
                            "call_context_index": None,
                            "ssa_version": ssa_version
                        })
            
    
    return results


def get_derived_names_for_file(c_file_path: str, only_diff_variables: bool = True) -> List[Dict]:
    """
    Main entry point: Get derived variable names for a C file.
    
    Args:
        c_file_path: Path to C source file
        only_diff_variables: If True, only include variables that differ between source and mutant.
                           Default: True (only diff variables)
        
    Returns:
        List of dictionaries with derived name metadata
    """
    return generate_derived_names(c_file_path, only_diff_variables=only_diff_variables)

