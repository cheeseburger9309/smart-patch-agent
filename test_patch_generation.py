#!/usr/bin/env python3
"""
Complete test suite for debugging the patch generation pipeline.

Tests in order:
1. Test SSH connection to VM
2. Test ARVO database query
3. Test patch format validation
4. Test patch cleaning function
5. Test Gemini prompt (if API key available)
6. Test full workflow with detailed logging
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from validator.ssh_client import create_final_ssh_client, JUMP_HOST_NAME, JUMP_HOST_USER, JUMP_HOST_PASSWORD, FINAL_HOST, FINAL_PORT, FINAL_USER, FINAL_PASSWORD
from validator.arvo_data_loader import load_bug_data
from workflow.nodes import clean_gemini_patch_output, validate_patch_format, analyze_bug_from_data

# --- TEST 1: SSH Connection ---
def test_ssh_connection():
    """Test if we can connect to the remote VM"""
    print("\n" + "="*80)
    print("TEST 1: SSH Connection to VM")
    print("="*80)
    
    try:
        print("Attempting SSH connection...")
        client = create_final_ssh_client(
            JUMP_HOST_NAME, JUMP_HOST_USER, JUMP_HOST_PASSWORD,
            FINAL_HOST, FINAL_PORT, FINAL_USER, FINAL_PASSWORD
        )
        
        if client:
            print("✅ SSH connection successful!")
            
            # Try a simple command
            stdin, stdout, stderr = client.exec_command("hostname && whoami")
            output = stdout.read().decode().strip()
            print(f"✅ Command execution successful: {output}")
            
            client.close()
            return True
        else:
            print("❌ SSH connection failed")
            return False
            
    except Exception as e:
        print(f"❌ SSH test failed: {e}")
        return False


# --- TEST 2: Database Query ---
def test_database_query(bug_id=40096184):
    """Test if we can query the ARVO database"""
    print("\n" + "="*80)
    print(f"TEST 2: ARVO Database Query (Bug {bug_id})")
    print("="*80)
    
    try:
        print(f"Querying bug {bug_id}...")
        bug_data = load_bug_data(bug_id)
        
        if bug_data:
            print("✅ Database query successful!")
            print(f"\nRetrieved fields:")
            for key, value in bug_data.items():
                if isinstance(value, str) and len(value) > 100:
                    print(f"   {key}: {value[:100]}... ({len(value)} chars)")
                else:
                    print(f"   {key}: {value}")
            
            # Check for critical fields
            critical_fields = ['repo_addr', 'fix_commit', 'reproducer_vul']
            missing = [f for f in critical_fields if not bug_data.get(f)]
            
            if missing:
                print(f"\n⚠️  WARNING: Missing critical fields: {missing}")
            else:
                print("\n✅ All critical fields present")
            
            return True, bug_data
        else:
            print("❌ Database query returned no data")
            return False, None
            
    except Exception as e:
        print(f"❌ Database test failed: {e}")
        return False, None


# --- TEST 3: Patch Format Validation ---
def test_patch_validation():
    """Test the patch format validator"""
    print("\n" + "="*80)
    print("TEST 3: Patch Format Validation")
    print("="*80)
    
    # Test cases
    test_cases = [
        {
            'name': 'Valid Patch',
            'patch': """--- a/src/test.c
+++ b/src/test.c
@@ -10,6 +10,9 @@ void test() {
+    if (ptr == NULL) {
+        return;
+    }
     ptr->value = 42;
 }""",
            'should_pass': True
        },
        {
            'name': 'Patch with Markdown',
            'patch': """```diff
--- a/src/test.c
+++ b/src/test.c
@@ -10,6 +10,9 @@ void test() {
+    if (ptr == NULL) {
+        return;
+    }
     ptr->value = 42;
 }
```""",
            'should_pass': False
        },
        {
            'name': 'Missing Headers',
            'patch': """@@ -10,6 +10,9 @@ void test() {
+    if (ptr == NULL) {
+        return;
+    }
     ptr->value = 42;
 }""",
            'should_pass': False
        },
        {
            'name': 'Empty Patch',
            'patch': "",
            'should_pass': False
        }
    ]
    
    all_passed = True
    
    for test in test_cases:
        print(f"\nTesting: {test['name']}")
        is_valid, errors = validate_patch_format(test['patch'])
        
        if is_valid == test['should_pass']:
            print(f"✅ PASS")
        else:
            print(f"❌ FAIL - Expected valid={test['should_pass']}, got valid={is_valid}")
            all_passed = False
        
        if errors:
            print(f"   Errors: {errors}")
    
    return all_passed


# --- TEST 4: Patch Cleaning ---
def test_patch_cleaning():
    """Test the Gemini output cleaning function"""
    print("\n" + "="*80)
    print("TEST 4: Patch Cleaning Function")
    print("="*80)
    
    # Simulate various Gemini outputs
    test_cases = [
        {
            'name': 'Clean Patch (no cleaning needed)',
            'input': """--- a/src/test.c
+++ b/src/test.c
@@ -10,6 +10,9 @@ void test() {
+    if (ptr == NULL) {
+        return;
+    }
     ptr->value = 42;
 }""",
        },
        {
            'name': 'Patch with Markdown',
            'input': """```diff
--- a/src/test.c
+++ b/src/test.c
@@ -10,6 +10,9 @@ void test() {
+    if (ptr == NULL) {
+        return;
+    }
     ptr->value = 42;
 }
```""",
        },
        {
            'name': 'Patch with Explanation Before',
            'input': """Here is the patch to fix the null pointer issue:

--- a/src/test.c
+++ b/src/test.c
@@ -10,6 +10,9 @@ void test() {
+    if (ptr == NULL) {
+        return;
+    }
     ptr->value = 42;
 }""",
        },
        {
            'name': 'Patch with Explanation After',
            'input': """--- a/src/test.c
+++ b/src/test.c
@@ -10,6 +10,9 @@ void test() {
+    if (ptr == NULL) {
+        return;
+    }
     ptr->value = 42;
 }

This patch adds a null check to prevent the crash.""",
        }
    ]
    
    all_passed = True
    
    for test in test_cases:
        print(f"\nTesting: {test['name']}")
        cleaned = clean_gemini_patch_output(test['input'])
        
        # Check if cleaned output is valid
        is_valid, errors = validate_patch_format(cleaned)
        
        print(f"   Input size: {len(test['input'])} chars")
        print(f"   Output size: {len(cleaned)} chars")
        print(f"   Valid: {is_valid}")
        
        if not is_valid:
            print(f"   ⚠️  Errors: {errors}")
        else:
            print(f"   ✅ Cleaned successfully")
        
        # Show first 200 chars of cleaned output
        print(f"   Preview: {cleaned[:200]}...")
    
    return all_passed


# --- TEST 5: Bug Analysis ---
def test_bug_analysis(bug_data):
    """Test the bug analysis function"""
    print("\n" + "="*80)
    print("TEST 5: Bug Analysis")
    print("="*80)
    
    if not bug_data:
        print("⚠️  Skipping (no bug data available)")
        return False
    
    try:
        analysis = analyze_bug_from_data(bug_data)
        
        print("Analysis Results:")
        for key, value in analysis.items():
            print(f"   {key}: {value}")
        
        # Check if key fields were extracted
        if analysis['file_path'] != 'unknown.c':
            print("✅ File path extracted successfully")
        else:
            print("⚠️  Could not extract file path")
        
        if analysis['line_number'] != '0':
            print("✅ Line number extracted successfully")
        else:
            print("⚠️  Could not extract line number")
        
        print("✅ Bug analysis completed")
        return True
        
    except Exception as e:
        print(f"❌ Bug analysis failed: {e}")
        return False


# --- TEST 6: Full Workflow with Logging ---
def test_full_workflow(bug_id=40096184):
    """Test the complete workflow with detailed logging"""
    print("\n" + "="*80)
    print(f"TEST 6: Full Workflow Test (Bug {bug_id})")
    print("="*80)
    
    try:
        from workflow.graph_builder import build_patch_agent_graph
        from workflow.state import AgentState
        
        print("\n1. Building graph...")
        app = build_patch_agent_graph()
        print("✅ Graph built successfully")
        
        print("\n2. Setting up initial state...")
        initial_state = {
            "bug_id": str(bug_id),
            "initial_crash_log": "Placeholder",
            "buggy_code_snippet": "Placeholder",
            "max_retries": 1,  # Only 1 retry for testing
            "bug_data": {},
            "all_patches": [],
            "current_patch": "",
            "validation_result": {},
            "failure_reason": "",
            "lsp_context": "",
            "retry_count": 0,
        }
        print("✅ Initial state ready")
        
        print("\n3. Executing workflow (this will take a few minutes)...")
        print("-" * 80)
        
        # Run with streaming to see progress
        for i, event in enumerate(app.stream(initial_state)):
            print(f"\n--- Event {i+1} ---")
            for node_name, state in event.items():
                print(f"Node: {node_name}")
                if 'current_patch' in state and state['current_patch']:
                    print(f"Generated patch: {state['current_patch'][:200]}...")
                if 'validation_result' in state and state['validation_result']:
                    print(f"Validation: {state['validation_result']}")
        
        print("\n" + "-" * 80)
        print("✅ Workflow completed")
        return True
        
    except Exception as e:
        print(f"❌ Workflow test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


# --- MAIN TEST RUNNER ---
def run_all_tests(bug_id=40096184):
    """Run all tests in sequence"""
    print("\n" + "="*80)
    print("SMART PATCH AGENT - COMPLETE TEST SUITE")
    print("="*80)
    print(f"Testing with Bug ID: {bug_id}")
    
    results = {}
    
    # Test 1: SSH
    results['SSH Connection'] = test_ssh_connection()
    
    # Test 2: Database
    db_success, bug_data = test_database_query(bug_id)
    results['Database Query'] = db_success
    
    # Test 3: Patch Validation
    results['Patch Validation'] = test_patch_validation()
    
    # Test 4: Patch Cleaning
    results['Patch Cleaning'] = test_patch_cleaning()
    
    # Test 5: Bug Analysis
    results['Bug Analysis'] = test_bug_analysis(bug_data)
    
    # Test 6: Full Workflow (optional - takes time)
    run_full_test = input("\nRun full workflow test? This will take several minutes. (y/n): ")
    if run_full_test.lower() == 'y':
        results['Full Workflow'] = test_full_workflow(bug_id)
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    total = len(results)
    passed = sum(results.values())
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Your system is ready.")
    else:
        print("\n⚠️  Some tests failed. Review the output above.")
    
    return results


if __name__ == "__main__":
    # Allow specifying a different bug ID
    bug_id = 40096184
    if len(sys.argv) > 1:
        bug_id = int(sys.argv[1])
    
    run_all_tests(bug_id)