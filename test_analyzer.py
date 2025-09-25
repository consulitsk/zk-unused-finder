import unittest
import os
import shutil
from collections import defaultdict
from unittest.mock import patch, mock_open

# Import the functions from the script to be tested
from analyze_viewmodels import (
    analyze_java_files,
    find_zul_usages,
    analyze_java_usages,
    run_analysis,
    generate_report,
    get_unused_methods,
    ViewModelInfo,
    MethodInfo,
    extract_viewmodels_from_ast,
    parse_java_file,
    log_debug
)

# Global setup for tests
SAMPLE_PROJECT_PATH = "sample_project"
log_debug("Starting tests")

class TestViewModelAnalyzer(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Set up the test environment once for all tests."""
        # This is where we can run the analysis once and reuse the results
        cls.view_models, cls.asts = analyze_java_files(SAMPLE_PROJECT_PATH)
        cls.zul_usages = find_zul_usages(SAMPLE_PROJECT_PATH, partial_match=True)
        analyze_java_usages(cls.asts, cls.view_models)
        run_analysis(cls.view_models, cls.zul_usages)

    def test_java_parsing_finds_all_viewmodels(self):
        """Tests if all ViewModel classes are found."""
        self.assertEqual(len(self.view_models), 12)
        # Check for a few specific ViewModels
        self.assertIn("com.example.OrderViewModel", self.view_models)
        self.assertIn("com.example.UserViewModel", self.view_models)
        self.assertIn("com.example.CompletelyUnusedViewModel", self.view_models)
        self.assertIn("com.example.AdvancedViewModel", self.view_models)

    def test_zul_parsing_finds_viewmodel_usages(self):
        """Tests if the ZUL parser correctly identifies ViewModel usages."""
        # Check that the zul_usages dictionary is not empty
        self.assertTrue(self.zul_usages)
        # Check for specific ViewModel usages
        self.assertIn("com.example.OrderViewModel", self.zul_usages)
        self.assertIn("com.example.UserViewModel", self.zul_usages)
        self.assertIn("com.example.NestedMainViewModel", self.zul_usages)
        self.assertIn("com.example.NestedDetailViewModel", self.zul_usages)

    def test_unused_method_identification(self):
        """Tests that unused methods are correctly identified."""
        unused_vms = get_unused_methods(self.view_models)

        # Find the OrderViewModel
        order_vm_info = self.view_models.get("com.example.OrderViewModel")
        self.assertIsNotNone(order_vm_info)

        # Check for the specific unused method in OrderViewModel
        self.assertTrue(any(not m.is_used() and m.name == "unusedMethod" for m in order_vm_info.methods.values()))

        # Check CompletelyUnusedViewModel
        completely_unused_vm = self.view_models.get("com.example.CompletelyUnusedViewModel")
        self.assertIsNotNone(completely_unused_vm)
        self.assertFalse(completely_unused_vm.is_used())

        # Check that all methods in CompletelyUnusedViewModel are unused
        for method in completely_unused_vm.methods.values():
            self.assertFalse(method.is_used())

    def test_report_generation(self):
        """Tests the report generation."""
        report = generate_report(self.view_models)

        # Check for the completely unused ViewModel
        self.assertIn("CompletelyUnusedViewModel", report)

        # Check for the unused method in OrderViewModel
        self.assertIn("OrderViewModel", report)
        self.assertIn("unusedMethod", report)

if __name__ == '__main__':
    unittest.main()