#!/usr/bin/env python3
"""
Test that file path cleaning works correctly
"""

def test_path_cleaning():
    """Test the path cleaning logic"""
    
    test_cases = [
        {
            'input': '/src/skia/out/Fuzz/../../src/codec/SkSwizzler.cpp',
            'expected': 'src/codec/SkSwizzler.cpp'
        },
        {
            'input': '../src/codec/SkSwizzler.cpp',
            'expected': 'src/codec/SkSwizzler.cpp'
        },
        {
            'input': '/src/codec/SkSwizzler.cpp',
            'expected': 'codec/SkSwizzler.cpp'
        },
        {
            'input': 'src/codec/SkSwizzler.cpp',
            'expected': 'src/codec/SkSwizzler.cpp'
        }
    ]
    
    print("Testing file path cleaning...")
    print("="*80)
    
    all_passed = True
    
    for test in test_cases:
        file_path = test['input']
        expected = test['expected']
        
        # Apply the cleaning logic
        if '/../' in file_path:
            parts = file_path.split('/../')
            file_path = parts[-1]
        
        if file_path.startswith('/src/'):
            file_path = file_path[5:]
        
        file_path = file_path.lstrip('/')
        
        while file_path.startswith('../'):
            file_path = file_path[3:]
        
        # Check result
        if file_path == expected:
            print(f"✅ PASS: {test['input']}")
            print(f"   → {file_path}")
        else:
            print(f"❌ FAIL: {test['input']}")
            print(f"   Expected: {expected}")
            print(f"   Got: {file_path}")
            all_passed = False
        print()
    
    return all_passed


if __name__ == "__main__":
    if test_path_cleaning():
        print("="*80)
        print("✅ All path cleaning tests passed!")
        print("\nNow update workflow/nodes.py and try again:")
        print("  python3 run_agent.py")
    else:
        print("="*80)
        print("❌ Some tests failed")