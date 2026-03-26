"""C source code parsing utilities."""

import re
from typing import List, Dict, Tuple


def read_c_source(file_path: str) -> List[str]:
    """
    Read a C source file and return lines as a list.
    
    Args:
        file_path: Path to the C source file
        
    Returns:
        List of lines from the file
        
    Raises:
        FileNotFoundError: If the file doesn't exist
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return [line for line in file]
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {file_path}")


def strip_comments(line: str) -> str:
    """
    Remove C-style comments from a line.
    
    Args:
        line: Source code line
        
    Returns:
        Line with comments removed and stripped
    """
    line = re.sub(r'/\*.*?\*/', '', line)
    line = re.sub(r'//.*$', '', line)
    return line.strip()


def normalize_identifiers(s: str) -> str:
    """
    Normalize identifiers by removing _2 suffix from mutant names.
    
    Example: "result_2" -> "result"
    
    Args:
        s: String containing identifiers
        
    Returns:
        String with normalized identifiers
    """
    return re.sub(r'\b(\w+)_2\b', r'\1', s)


def build_function_map(lines: List[str]) -> Dict[str, List[str]]:
    """
    Build a map of function names to their body lines.
    
    Args:
        lines: List of source code lines
        
    Returns:
        Dictionary mapping function names to their body lines
    """
    FUNC_HEADER_RE = re.compile(
        r'''
        ^\s*
        (?:static\s+|inline\s+|extern\s+)?   # optional qualifiers
        [\w\*\s]+?                            # return type
        \s+
        (?P<name>[A-Za-z_]\w*)                # function name
        \s*
        \([^;]*\)                             # parameters
        \s*$
        ''',
        re.VERBOSE
    )
    
    functions = {}
    i = 0
    n = len(lines)
    
    while i < n:
        line = lines[i]
        m = FUNC_HEADER_RE.match(line)
        if not m:
            i += 1
            continue
        
        fname = m.group("name")
        body = [line]
        brace_depth = 0
        i += 1
        
        # Move until opening brace
        while i < n and "{" not in lines[i]:
            body.append(lines[i])
            i += 1
        
        if i >= n:
            continue
        
        # Opening brace line
        brace_depth += lines[i].count("{")
        brace_depth -= lines[i].count("}")
        body.append(lines[i])
        i += 1
        
        # Collect body until braces close
        while i < n and brace_depth > 0:
            brace_depth += lines[i].count("{")
            brace_depth -= lines[i].count("}")
            body.append(lines[i])
            i += 1
        
        functions[fname] = body
    
    return functions


def extract_assignments(func_lines: List[str]) -> List[Dict[str, str]]:
    """
    Extract assignments from function lines, preserving order.
    
    Args:
        func_lines: List of function body lines
        
    Returns:
        List of assignment dictionaries with 'lhs', 'rhs', and 'line' keys
    """
    ASSIGN_RE = re.compile(r'^\s*(\w+)\s*=\s*(.+);')
    assigns = []
    
    for line in func_lines:
        clean = strip_comments(line)
        if not clean:
            continue
        m = ASSIGN_RE.match(clean)
        if m:
            lhs, rhs = m.group(1), m.group(2)
            # Strip trailing semicolons and whitespace from RHS
            # (handles cases like "expr;;" where double semicolons exist)
            rhs = rhs.rstrip(';').strip()
            assigns.append({
                "lhs": lhs,
                "rhs": rhs,
                "line": line.rstrip("\n")
            })
    return assigns


def split_top_level_and(expr: str) -> List[str]:
    """
    Split expression by top-level && operators (respecting parentheses).
    
    Args:
        expr: Expression string
        
    Returns:
        List of expression parts
    """
    parts, cur, depth, i = [], [], 0, 0
    while i < len(expr):
        if expr[i] == '(':
            depth += 1
        elif expr[i] == ')':
            depth -= 1
        if depth == 0 and expr[i:i+2] == '&&':
            parts.append(''.join(cur).strip())
            cur = []
            i += 2
            continue
        cur.append(expr[i])
        i += 1
    if cur:
        parts.append(''.join(cur).strip())
    return parts


def normalize_expr(expr: str) -> str:
    """
    Normalize expression by normalizing identifiers but preserving operators and structure.
    
    Args:
        expr: Expression string
        
    Returns:
        Normalized expression string
    """
    expr = expr.strip()
    # Remove outer parentheses if present (but preserve inner structure)
    while expr.startswith('(') and expr.endswith(')'):
        # Check if it's balanced parentheses
        depth = 0
        balanced = True
        for i, char in enumerate(expr):
            if char == '(':
                depth += 1
            elif char == ')':
                depth -= 1
                if depth == 0 and i < len(expr) - 1:
                    balanced = False
                    break
        if balanced:
            expr = expr[1:-1].strip()
        else:
            break
    # Normalize identifiers (x_2 -> x) but keep operators unchanged
    expr = normalize_identifiers(expr)
    # Normalize whitespace
    expr = ' '.join(expr.split())
    return expr

