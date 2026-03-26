"""Tests for parser module."""

import unittest
from ssa_analyzer.parser import (
    normalize_identifiers, strip_comments, split_top_level_and
)


class TestParser(unittest.TestCase):
    """Test parser utilities."""
    
    def test_normalize_identifiers(self):
        """Test identifier normalization."""
        self.assertEqual(normalize_identifiers("result_2"), "result")
        self.assertEqual(normalize_identifiers("result_2_2"), "result_2")
        self.assertEqual(normalize_identifiers("MINSEP_2"), "MINSEP")
        self.assertEqual(normalize_identifiers("result"), "result")
    
    def test_strip_comments(self):
        """Test comment stripping."""
        self.assertEqual(strip_comments("int x; // comment"), "int x;")
        self.assertEqual(strip_comments("int x; /* comment */"), "int x;")
        self.assertEqual(strip_comments("int x;"), "int x;")
    
    def test_split_top_level_and(self):
        """Test splitting by top-level &&."""
        expr = "A && B && C"
        parts = split_top_level_and(expr)
        self.assertEqual(len(parts), 3)
        self.assertEqual(parts[0].strip(), "A")
        self.assertEqual(parts[1].strip(), "B")
        self.assertEqual(parts[2].strip(), "C")
        
        expr = "A && (B && C)"
        parts = split_top_level_and(expr)
        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[0].strip(), "A")
        self.assertEqual(parts[1].strip(), "(B && C)")


if __name__ == '__main__':
    unittest.main()

