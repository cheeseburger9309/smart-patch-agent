#!/usr/bin/env python3
"""
Quick test to verify the workaround is working
"""

import sys
import os

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test that all imports work"""
    print("="*80)
    print("TEST 1: Imports")
    print("="*80)
    
    try:
        from workflow.graph_builder import build_patch_agent_graph
        print("✅ graph_builder imported")
    except Exception as e:
        print(f"❌ graph_builder failed: {e}")
        return False
    
    try:
        from workflow.state import AgentState
        print("✅ state imported")
    except Exception as e:
        print(f"❌ state failed: {e}")
        return False
    
    try:
        from validator.arvo_data_loader import load_bug_data
        print("✅ arvo_data_loader imported")
    except Exception as e:
        print(f"❌ arvo_data_loader failed: {e}")
        return False
    
    try:
        from validator.ssh_client import run_remote_command
        print("✅ ssh_client imported")
    except Exception as e:
        print(f"❌ ssh_client failed: {e}")
        return False
    
    return True


def test_gemini_client():
    """Test Gemini client initialization"""
    print("\n" + "="*80)
    print("TEST 2: Gemini Client")
    print("="*80)
    
    try:
        from google import genai
        client = genai.Client()
        print("✅ Gemini client initialized")
        
        # Try a simple, safe request
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents="Say 'hello' in JSON format: {\"greeting\": \"hello\"}",
            config={'temperature': 0, 'max_output_tokens': 50}
        )
        
        if response.text:
            print(f"✅ Gemini API responding: {response.text[:50]}")
            return True
        else:
            print("⚠️  Gemini returned None (might be blocked)")
            return False
            
    except Exception as e:
        print(f"❌ Gemini client failed: {e}")
        return False


def test_database_connection():
    """Test database loading"""
    print("\n" + "="*80)
    print("TEST 3: Database Connection")
    print("="*80)
    
    try:
        from validator.arvo_data_loader import load_bug_data
        
        print("Loading bug 40096184...")
        bug_data = load_bug_data(40096184)
        
        if bug_data:
            print(f"✅ Bug data loaded: {bug_data.get('project', 'unknown')}")
            print(f"   File: {bug_data.get('extracted_file_path', 'unknown')}")
            print(f"   Line: {bug_data.get('extracted_line_number', 'unknown')}")
            print(f"   Type: {bug_data.get('bug_category', 'unknown')}")
            return True
        else:
            print("❌ No bug data returned")
            return False
            
    except Exception as e:
        print(f"❌ Database test failed: {e}")
        return False


def test_patch_generation():
    """Test the new safe prompt generation"""
    print("\n" + "="*80)
    print("TEST 4: Safe Prompt Generation")
    print("="*80)
    
    try:
        from workflow.nodes import create_safe_prompt
        
        sample_code = """  235 | void swizzle_index_to_n32(...) {
  236 |     for (int i = 0; i < count; i++) {
  237 |         dst[i] = colorTable[src[i]];
  238 |     }
  239 | }"""
        
        prompt = create_safe_prompt(
            code=sample_code,
            file_path="src/codec/SkSwizzler.cpp",
            line_number="237",
            bug_type="HEAP_BUFFER_OVERFLOW",
            language="C++"
        )
        
        print(f"✅ Generated safe prompt ({len(prompt)} chars)")
        
        # Check that it doesn't contain risky terms
        risky_terms = ['overflow', 'exploit', 'vulnerability', 'crash', 'asan']
        found_risky = [term for term in risky_terms if term.lower() in prompt.lower()]
        
        if found_risky:
            print(f"⚠️  Warning: Prompt contains potentially risky terms: {found_risky}")
        else:
            print("✅ Prompt is clean (no risky security terms)")
        
        print(f"\nPrompt preview:\n{prompt[:200]}...")
        return True
        
    except Exception as e:
        print(f"❌ Prompt generation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_fallback_patch():
    """Test fallback patch generation"""
    print("\n" + "="*80)
    print("TEST 5: Fallback Patch Generation")
    print("="*80)
    
    try:
        from workflow.nodes import generate_fallback_patch
        
        analysis = {
            'file_path': 'src/codec/SkSwizzler.cpp',
            'line_number': '237',
            'bug_type': 'HEAP_BUFFER_OVERFLOW',
            'language': 'C++'
        }
        
        sample_code = """  237 |         dst[i] = colorTable[src[i]];"""
        
        patch = generate_fallback_patch(analysis, sample_code)
        
        print(f"✅ Generated fallback patch ({len(patch)} chars)")
        print(f"\nPatch preview:\n{patch[:300]}")
        
        # Check basic format
        if '---' in patch and '+++' in patch and '@@' in patch:
            print("✅ Patch has correct unified diff format")
            return True
        else:
            print("⚠️  Patch may be missing required headers")
            return False
            
    except Exception as e:
        print(f"❌ Fallback patch generation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_all_tests():
    """Run all tests"""
    print("\n" + "="*80)
    print("🧪 QUICK TEST SUITE - SMART PATCH AGENT")
    print("="*80)
    
    results = {}
    
    results['imports'] = test_imports()
    results['gemini'] = test_gemini_client()
    results['database'] = test_database_connection()
    results['prompt'] = test_patch_generation()
    results['fallback'] = test_fallback_patch()
    
    # Summary
    print("\n" + "="*80)
    print("📊 TEST SUMMARY")
    print("="*80)
    
    total = len(results)
    passed = sum(results.values())
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Ready to run full workflow.")
        print("\nNext step: python3 run_agent.py")
    else:
        print("\n⚠️  Some tests failed. Review errors above.")
    
    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)