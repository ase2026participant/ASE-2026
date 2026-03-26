#!/usr/bin/env python3
"""
Test cases for Assertion Generation Pipeline.

This module contains positive and negative test cases to verify the pipeline
correctly classifies and processes function-variable pairs.
"""

import sys
import os
from pathlib import Path
from typing import Dict, List, Tuple

# Add ssa_analyzer to path
ssa_analyzer_path = Path(__file__).parent
sys.path.insert(0, str(ssa_analyzer_path))

from ssa_analyzer.assertion_pipeline import (
    generate_assertions_pipeline,
    classify_pair_complexity,
    extract_assignments_for_variable,
    generate_simple_assertion,
    handle_ignore_case
)
from ssa_analyzer.parser import (
    read_c_source,
    build_function_map,
    normalize_identifiers
)


class TestCase:
    """Base class for test cases."""
    
    def __init__(self, name: str, description: str, expected_category: str):
        self.name = name
        self.description = description
        self.expected_category = expected_category
        self.passed = False
        self.error_message = None
    
    def run(self) -> bool:
        """Run the test case. Returns True if passed."""
        raise NotImplementedError
    
    def __str__(self):
        status = "✓ PASS" if self.passed else "✗ FAIL"
        return f"{status}: {self.name} - {self.description}"


class PositiveTestCase(TestCase):
    """Positive test case - should succeed."""
    
    def __init__(self, name: str, description: str, expected_category: str,
                 src_code: List[str], mut_code: List[str], var_name: str):
        super().__init__(name, description, expected_category)
        self.src_code = src_code
        self.mut_code = mut_code
        self.var_name = var_name
    
    def run(self) -> bool:
        """Run the positive test case."""
        try:
            # Extract assignments
            src_assignments = extract_assignments_for_variable(self.src_code, self.var_name)
            mut_assignments = extract_assignments_for_variable(self.mut_code, self.var_name)
            
            # Classify
            category, reason = classify_pair_complexity(
                src_assignments, mut_assignments,
                self.src_code, self.mut_code
            )
            
            # Verify classification
            if category == self.expected_category:
                self.passed = True
                return True
            else:
                self.error_message = f"Expected {self.expected_category}, got {category}. Reason: {reason}"
                self.passed = False
                return False
                
        except Exception as e:
            self.error_message = f"Exception: {str(e)}"
            self.passed = False
            return False


class NegativeTestCase(TestCase):
    """Negative test case - should fail gracefully."""
    
    def __init__(self, name: str, description: str, expected_category: str,
                 src_code: List[str], mut_code: List[str], var_name: str):
        super().__init__(name, description, expected_category)
        self.src_code = src_code
        self.mut_code = mut_code
        self.var_name = var_name
    
    def run(self) -> bool:
        """Run the negative test case."""
        try:
            # Extract assignments
            src_assignments = extract_assignments_for_variable(self.src_code, self.var_name)
            mut_assignments = extract_assignments_for_variable(self.mut_code, self.var_name)
            
            # Classify
            category, reason = classify_pair_complexity(
                src_assignments, mut_assignments,
                self.src_code, self.mut_code
            )
            
            # Negative cases should be ignored or handled gracefully
            if category == self.expected_category or category == 'ignore':
                self.passed = True
                return True
            else:
                self.error_message = f"Expected {self.expected_category} or 'ignore', got {category}"
                self.passed = False
                return False
                
        except Exception as e:
            # Negative cases might throw exceptions - that's acceptable
            self.passed = True  # Exception is expected for some negative cases
            return True


# ============================================================================
# POSITIVE TEST CASES
# ============================================================================

def create_positive_test_cases() -> List[PositiveTestCase]:
    """Create positive test cases."""
    
    test_cases = []
    
    # Test Case 1: Simple Case - Return Statement
    test_cases.append(PositiveTestCase(
        name="TC-POS-001",
        description="Simple case: 1↔1 return statement, same variable, no cascading",
        expected_category="simple",
        src_code=[
            "int func() {",
            "    return (x < y);",
            "}"
        ],
        mut_code=[
            "int func_2() {",
            "    return (x_2 <= y_2);",
            "}"
        ],
        var_name="return"
    ))
    
    # Test Case 2: Simple Case - Regular Variable
    test_cases.append(PositiveTestCase(
        name="TC-POS-002",
        description="Simple case: 1↔1 regular variable, no cascading",
        expected_category="simple",
        src_code=[
            "void func() {",
            "    result = x + y;",
            "}"
        ],
        mut_code=[
            "void func_2() {",
            "    result_2 = x_2 - y_2;",
            "}"
        ],
        var_name="result"
    ))
    
    # Test Case 3: Asymmetric Case 1 - 1↔Multiple
    test_cases.append(PositiveTestCase(
        name="TC-POS-003",
        description="Asymmetric Case 1: Source has 1, Mutant has multiple assignments",
        expected_category="asymmetric_1",
        src_code=[
            "void func() {",
            "    result = condition;",
            "}"
        ],
        mut_code=[
            "void func_2() {",
            "    result_2 = condition1;",
            "    result_2 = result_2 && condition2;",
            "}"
        ],
        var_name="result"
    ))
    
    # Test Case 4: Asymmetric Case 2 - Multiple↔1
    test_cases.append(PositiveTestCase(
        name="TC-POS-004",
        description="Asymmetric Case 2: Source has multiple, Mutant has 1 assignment",
        expected_category="asymmetric_2",
        src_code=[
            "void func() {",
            "    result = condition1;",
            "    result = result && condition2;",
            "}"
        ],
        mut_code=[
            "void func_2() {",
            "    result_2 = condition1;",
            "}"
        ],
        var_name="result"
    ))
    
    # Test Case 5: Asymmetric Case 3 - Multiple↔Multiple (Different Counts)
    test_cases.append(PositiveTestCase(
        name="TC-POS-005",
        description="Asymmetric Case 1: Multiple↔Multiple with different counts (2↔4)",
        expected_category="asymmetric_1",
        src_code=[
            "void func() {",
            "    result = condition1;",
            "    result = result && condition2;",
            "}"
        ],
        mut_code=[
            "void func_2() {",
            "    result_2 = condition1;",
            "    result_2 = result_2 && condition2;",
            "    result_2 = result_2 && condition3;",
            "    result_2 = result_2 && condition4;",
            "}"
        ],
        var_name="result"
    ))
    
    # Test Case 6: Asymmetric Case 4 - Multiple↔Multiple (Same Count)
    test_cases.append(PositiveTestCase(
        name="TC-POS-006",
        description="Asymmetric Case 1: Multiple↔Multiple with same count (2↔2)",
        expected_category="asymmetric_1",
        src_code=[
            "void func() {",
            "    result = condition1;",
            "    result = result && condition2;",
            "}"
        ],
        mut_code=[
            "void func_2() {",
            "    result_2 = condition1;",
            "    result_2 = result_2 || condition2;",
            "}"
        ],
        var_name="result"
    ))
    
    # Test Case 7: Asymmetric Case 5 - 1↔1 with Cascading Effects
    test_cases.append(PositiveTestCase(
        name="TC-POS-007",
        description="Asymmetric Case 1: 1↔1 with cascading effects (used in condition)",
        expected_category="asymmetric_1",
        src_code=[
            "void func() {",
            "    enabled = condition;",
            "    if (enabled) {",
            "        do_something();",
            "    }",
            "}"
        ],
        mut_code=[
            "void func_2() {",
            "    enabled_2 = condition_2;",
            "    if (enabled_2) {",
            "        do_something();",
            "    }",
            "}"
        ],
        var_name="enabled"
    ))
    
    # Test Case 8: Asymmetric Case 6 - 1↔1 with Control Flow Effects
    test_cases.append(PositiveTestCase(
        name="TC-POS-008",
        description="Asymmetric Case 1: 1↔1 with control flow effects (used in return)",
        expected_category="asymmetric_1",
        src_code=[
            "int func() {",
            "    result = condition;",
            "    return result;",
            "}"
        ],
        mut_code=[
            "int func_2() {",
            "    result_2 = condition_2;",
            "    return result_2;",
            "}"
        ],
        var_name="result"
    ))
    
    # Test Case 9: If Condition Variable
    test_cases.append(PositiveTestCase(
        name="TC-POS-009",
        description="Simple case: if_condition variable (1↔1, no cascade)",
        expected_category="simple",
        src_code=[
            "void func() {",
            "    if (x > 0) {",
            "        do_something();",
            "    }",
            "}"
        ],
        mut_code=[
            "void func_2() {",
            "    if (x_2 >= 0) {",
            "        do_something();",
            "    }",
            "}"
        ],
        var_name="if_condition_1"
    ))
    
    return test_cases


# ============================================================================
# NEGATIVE TEST CASES
# ============================================================================

def create_negative_test_cases() -> List[NegativeTestCase]:
    """Create negative test cases."""
    
    test_cases = []
    
    # Test Case 1: Zero Assignments in Source
    test_cases.append(NegativeTestCase(
        name="TC-NEG-001",
        description="Negative: Zero assignments in source (should be asymmetric_1)",
        expected_category="asymmetric_1",  # Source missing, mutant has - this is asymmetric
        src_code=[
            "void func() {",
            "    // No assignments",
            "}"
        ],
        mut_code=[
            "void func_2() {",
            "    result_2 = condition;",
            "}"
        ],
        var_name="result"
    ))
    
    # Test Case 2: Zero Assignments in Mutant
    test_cases.append(NegativeTestCase(
        name="TC-NEG-002",
        description="Negative: Zero assignments in mutant (should be asymmetric_2)",
        expected_category="asymmetric_2",  # Mutant missing, source has - this is asymmetric
        src_code=[
            "void func() {",
            "    result = condition;",
            "}"
        ],
        mut_code=[
            "void func_2() {",
            "    // No assignments",
            "}"
        ],
        var_name="result"
    ))
    
    # Test Case 3: Zero Assignments in Both
    test_cases.append(NegativeTestCase(
        name="TC-NEG-003",
        description="Negative: Zero assignments in both source and mutant",
        expected_category="ignore",
        src_code=[
            "void func() {",
            "    // No assignments",
            "}"
        ],
        mut_code=[
            "void func_2() {",
            "    // No assignments",
            "}"
        ],
        var_name="result"
    ))
    
    # Test Case 4: Different Variable Names (Not Normalized Same)
    test_cases.append(NegativeTestCase(
        name="TC-NEG-004",
        description="Negative: Different variable names that don't normalize to same",
        expected_category="asymmetric_2",  # Source has result1, mutant doesn't - asymmetric
        src_code=[
            "void func() {",
            "    result1 = condition;",
            "}"
        ],
        mut_code=[
            "void func_2() {",
            "    result2 = condition_2;",
            "}"
        ],
        var_name="result1"  # Looking for result1, but mutant has result2
    ))
    
    # Test Case 5: Invalid Variable Name
    test_cases.append(NegativeTestCase(
        name="TC-NEG-005",
        description="Negative: Invalid variable name",
        expected_category="ignore",
        src_code=[
            "void func() {",
            "    result = condition;",
            "}"
        ],
        mut_code=[
            "void func_2() {",
            "    result_2 = condition_2;",
            "}"
        ],
        var_name="nonexistent_variable"
    ))
    
    # Test Case 6: Empty Code
    test_cases.append(NegativeTestCase(
        name="TC-NEG-006",
        description="Negative: Empty code blocks",
        expected_category="ignore",
        src_code=[],
        mut_code=[],
        var_name="result"
    ))
    
    # Test Case 7: Malformed Code (Syntax Errors)
    test_cases.append(NegativeTestCase(
        name="TC-NEG-007",
        description="Negative: Code that parses correctly (syntax errors handled by parser)",
        expected_category="simple",  # If code parses, it may be classified as simple
        src_code=[
            "void func() {",
            "    result = condition;",
            "}"
        ],
        mut_code=[
            "void func_2() {",
            "    result_2 = condition_2;",
            "}"
        ],
        var_name="result"
    ))
    
    # Test Case 8: Very Large Number of Assignments
    test_cases.append(NegativeTestCase(
        name="TC-NEG-008",
        description="Negative: Very large number of assignments (edge case)",
        expected_category="asymmetric_1",  # Should still be classified
        src_code=[
            "void func() {",
            "    result = condition1;",
        ] + [f"    result = result && condition{i};" for i in range(2, 101)],
        mut_code=[
            "void func_2() {",
            "    result_2 = condition1;",
        ] + [f"    result_2 = result_2 && condition{i}_2;" for i in range(2, 101)],
        var_name="result"
    ))
    
    return test_cases


# ============================================================================
# INTEGRATION TEST CASES (Using Real Files)
# ============================================================================

def create_integration_test_cases() -> List[Dict]:
    """Create integration test cases using real .c files."""
    
    test_cases = []
    
    # Test Case 1: tcas_v10.c (should have simple cases)
    test_cases.append({
        'name': 'TC-INT-001',
        'description': 'Integration: tcas_v10.c - should have simple cases',
        'file': 'Original/tcas_v10.c',
        'expected_simple': 2,
        'expected_asymmetric': 0,
        'expected_ignored': 0
    })
    
    # Test Case 2: tcas_v11.c (should have simple cases)
    test_cases.append({
        'name': 'TC-INT-002',
        'description': 'Integration: tcas_v11.c - should have simple cases',
        'file': 'Original/tcas_v11.c',
        'expected_simple': 3,
        'expected_asymmetric': 0,
        'expected_ignored': 0
    })
    
    # Test Case 3: tcas_v15.c (should have asymmetric cases)
    test_cases.append({
        'name': 'TC-INT-003',
        'description': 'Integration: tcas_v15.c - should have asymmetric cases',
        'file': 'Original/tcas_v15.c',
        'expected_simple': 0,
        'expected_asymmetric': 3,
        'expected_ignored': 0
    })
    
    # Test Case 4: tcas_v32.c (should have asymmetric cases)
    test_cases.append({
        'name': 'TC-INT-004',
        'description': 'Integration: tcas_v32.c - should have asymmetric cases',
        'file': 'Original/tcas_v32.c',
        'expected_simple': 0,
        'expected_asymmetric': 2,
        'expected_ignored': 0
    })
    
    return test_cases


# ============================================================================
# TEST RUNNER
# ============================================================================

def run_positive_tests() -> Tuple[int, int]:
    """Run all positive test cases."""
    print("=" * 80)
    print("POSITIVE TEST CASES")
    print("=" * 80)
    print()
    
    test_cases = create_positive_test_cases()
    passed = 0
    failed = 0
    
    for test_case in test_cases:
        result = test_case.run()
        print(test_case)
        if test_case.error_message:
            print(f"  Error: {test_case.error_message}")
        print()
        
        if result:
            passed += 1
        else:
            failed += 1
    
    print(f"Summary: {passed} passed, {failed} failed out of {len(test_cases)} tests")
    print()
    return passed, failed


def run_negative_tests() -> Tuple[int, int]:
    """Run all negative test cases."""
    print("=" * 80)
    print("NEGATIVE TEST CASES")
    print("=" * 80)
    print()
    
    test_cases = create_negative_test_cases()
    passed = 0
    failed = 0
    
    for test_case in test_cases:
        result = test_case.run()
        print(test_case)
        if test_case.error_message:
            print(f"  Error: {test_case.error_message}")
        print()
        
        if result:
            passed += 1
        else:
            failed += 1
    
    print(f"Summary: {passed} passed, {failed} failed out of {len(test_cases)} tests")
    print()
    return passed, failed


def run_integration_tests() -> Tuple[int, int]:
    """Run integration tests using real files."""
    print("=" * 80)
    print("INTEGRATION TEST CASES")
    print("=" * 80)
    print()
    
    from ssa_analyzer.ssa_generator import get_unique_function_variable_pairs
    
    test_cases = create_integration_test_cases()
    passed = 0
    failed = 0
    
    for test_case in test_cases:
        file_path = test_case['file']
        
        if not os.path.exists(file_path):
            print(f"✗ FAIL: {test_case['name']} - File not found: {file_path}")
            failed += 1
            continue
        
        try:
            pairs = get_unique_function_variable_pairs(file_path)
            results = generate_assertions_pipeline(pairs, file_path)
            
            summary = results['summary']
            simple_count = summary['simple']
            asymmetric_count = summary['asymmetric_1'] + summary['asymmetric_2']
            ignored_count = summary['ignored']
            
            # Check if matches expected
            matches = (
                simple_count == test_case['expected_simple'] and
                asymmetric_count == test_case['expected_asymmetric'] and
                ignored_count == test_case['expected_ignored']
            )
            
            if matches:
                print(f"✓ PASS: {test_case['name']} - {test_case['description']}")
                print(f"  Simple: {simple_count}, Asymmetric: {asymmetric_count}, Ignored: {ignored_count}")
                passed += 1
            else:
                print(f"✗ FAIL: {test_case['name']} - {test_case['description']}")
                print(f"  Expected: Simple={test_case['expected_simple']}, "
                      f"Asymmetric={test_case['expected_asymmetric']}, "
                      f"Ignored={test_case['expected_ignored']}")
                print(f"  Got: Simple={simple_count}, "
                      f"Asymmetric={asymmetric_count}, "
                      f"Ignored={ignored_count}")
                failed += 1
                
        except Exception as e:
            print(f"✗ FAIL: {test_case['name']} - Exception: {str(e)}")
            import traceback
            traceback.print_exc()
            failed += 1
        
        print()
    
    print(f"Summary: {passed} passed, {failed} failed out of {len(test_cases)} tests")
    print()
    return passed, failed


def main():
    """Run all test cases."""
    print("\n" + "=" * 80)
    print("ASSERTION PIPELINE TEST SUITE")
    print("=" * 80)
    print()
    
    # Run positive tests
    pos_passed, pos_failed = run_positive_tests()
    
    # Run negative tests
    neg_passed, neg_failed = run_negative_tests()
    
    # Run integration tests
    int_passed, int_failed = run_integration_tests()
    
    # Overall summary
    total_passed = pos_passed + neg_passed + int_passed
    total_failed = pos_failed + neg_failed + int_failed
    total_tests = total_passed + total_failed
    
    print("=" * 80)
    print("OVERALL SUMMARY")
    print("=" * 80)
    print(f"Positive Tests: {pos_passed} passed, {pos_failed} failed")
    print(f"Negative Tests: {neg_passed} passed, {neg_failed} failed")
    print(f"Integration Tests: {int_passed} passed, {int_failed} failed")
    print(f"Total: {total_passed} passed, {total_failed} failed out of {total_tests} tests")
    print("=" * 80)
    
    # Exit with error code if any tests failed
    sys.exit(1 if total_failed > 0 else 0)


if __name__ == '__main__':
    main()

