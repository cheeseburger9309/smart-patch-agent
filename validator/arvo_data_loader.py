# validator/arvo_data_loader.py - FINAL VERSION (Matches Your Schema)

from .ssh_client import run_remote_command, ARVO_DB_PATH
import json
import re
from typing import Dict, Any, Optional

def load_bug_data(local_id: int) -> Optional[Dict[str, Any]]:
    """
    Queries the ARVO DB on the remote VM via SSH and returns comprehensive bug entry.
    
    Schema-verified columns (from your database):
    - localId, project, reproducer_vul, reproducer_fix, fix_commit, repo_addr
    - sanitizer, crash_type, crash_output, severity, report, language
    - fuzz_target, fuzz_engine, patch_url, patch_located, verified
    """
    
    # Query ALL relevant fields from your actual schema
    query = f"""SELECT 
        localId,
        project,
        repo_addr,
        fix_commit,
        reproducer_vul,
        reproducer_fix,
        sanitizer,
        crash_type,
        crash_output,
        language,
        severity,
        report,
        patch_url,
        fuzz_target,
        fuzz_engine
    FROM arvo 
    WHERE localId={local_id};"""
    
    # Use SQLite's -json output for easy parsing
    remote_cmd = f"sqlite3 -json {ARVO_DB_PATH} \"{query}\""
    
    print(f"[DATA LOADER] Querying ARVO DB for bug {local_id}...")
    exit_code, stdout, stderr = run_remote_command(remote_cmd)
    
    if exit_code != 0:
        print(f"ERROR: Failed to query ARVO DB remotely.")
        print(f"   Exit Code: {exit_code}")
        print(f"   Stderr: {stderr}")
        return None
    
    try:
        # Parse JSON result
        data = json.loads(stdout)
        
        if not data:
            print(f"ERROR: No data found for bug ID {local_id}")
            return None
        
        bug_entry = data[0]
        
        # Add derived/helper fields
        bug_entry['bug_id'] = str(local_id)
        
        # Extract detailed crash context from crash_output
        if bug_entry.get('crash_output'):
            crash_context = extract_crash_context(bug_entry['crash_output'])
            bug_entry['extracted_file_path'] = crash_context['file_path']
            bug_entry['extracted_line_number'] = crash_context['line_number']
            bug_entry['bug_category'] = crash_context['bug_category']
        else:
            # Fallback to crash_type if no crash_output
            bug_entry['extracted_file_path'] = 'unknown'
            bug_entry['extracted_line_number'] = '0'
            bug_entry['bug_category'] = classify_bug_type(bug_entry.get('crash_type', ''))
        
        # Log what we successfully loaded
        print(f"[DATA LOADER] ✅ Successfully loaded bug data:")
        print(f"   Project: {bug_entry.get('project', 'unknown')}")
        print(f"   Language: {bug_entry.get('language', 'unknown')}")
        print(f"   Repo: {bug_entry.get('repo_addr', 'unknown')[:60]}...")
        print(f"   Sanitizer: {bug_entry.get('sanitizer', 'unknown')}")
        print(f"   Crash Type: {bug_entry.get('crash_type', 'unknown')}")
        print(f"   Crash Output: {len(bug_entry.get('crash_output', ''))} characters")
        print(f"   Extracted File: {bug_entry.get('extracted_file_path', 'unknown')}")
        print(f"   Extracted Line: {bug_entry.get('extracted_line_number', 'unknown')}")
        print(f"   Bug Category: {bug_entry.get('bug_category', 'unknown')}")
        
        return bug_entry
        
    except json.JSONDecodeError as e:
        print(f"ERROR: Could not parse JSON data from DB query.")
        print(f"   Error: {e}")
        print(f"   Raw Output: {stdout[:500]}...")
        return None
    except Exception as e:
        print(f"ERROR: Unexpected error loading bug data: {e}")
        import traceback
        traceback.print_exc()
        return None


def extract_crash_context(crash_output: str) -> Dict[str, str]:
    """
    Parse crash_output to extract file path, line number, and bug category.
    
    ASAN output typically looks like:
    ==12345==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x...
    #0 0x... in function_name /path/to/file.cpp:123:45
    #1 0x... in caller_function /path/to/caller.cpp:456:78
    ...
    """
    
    context = {
        'file_path': 'unknown',
        'line_number': '0',
        'bug_category': 'UNKNOWN',
        'function_name': 'unknown'
    }
    
    if not crash_output:
        return context
    
    # Extract file path and line number from stack trace
    # Pattern 1: /path/to/file.cpp:123:45 (ASAN format)
    file_match = re.search(r'([/\w\-_.]+\.(cpp|cc|c|h|hpp|java|py)):\d+:\d+', crash_output)
    if file_match:
        full_path = file_match.group(1)
        # Extract just the filename from the full path for simpler matching
        # But keep the relative path if it's there
        context['file_path'] = full_path
    
    # Extract line number
    line_match = re.search(r':(\d+):\d+', crash_output)
    if line_match:
        context['line_number'] = line_match.group(1)
    
    # Extract function name from stack trace
    # Pattern: #0 0x... in function_name /path/to/file.cpp:123
    func_match = re.search(r'#\d+\s+0x[\da-f]+\s+in\s+([^\s/]+)', crash_output)
    if func_match:
        context['function_name'] = func_match.group(1)
    
    # Classify bug type from ASAN error message
    crash_lower = crash_output.lower()
    
    if 'heap-buffer-overflow' in crash_lower:
        context['bug_category'] = 'HEAP_BUFFER_OVERFLOW'
    elif 'stack-buffer-overflow' in crash_lower:
        context['bug_category'] = 'STACK_BUFFER_OVERFLOW'
    elif 'global-buffer-overflow' in crash_lower:
        context['bug_category'] = 'GLOBAL_BUFFER_OVERFLOW'
    elif 'use-after-free' in crash_lower:
        context['bug_category'] = 'USE_AFTER_FREE'
    elif 'heap-use-after-free' in crash_lower:
        context['bug_category'] = 'USE_AFTER_FREE'
    elif 'double-free' in crash_lower:
        context['bug_category'] = 'DOUBLE_FREE'
    elif 'null' in crash_lower or 'nullptr' in crash_lower:
        context['bug_category'] = 'NULL_POINTER'
    elif 'segv' in crash_lower or 'segmentation fault' in crash_lower:
        context['bug_category'] = 'SEGMENTATION_FAULT'
    elif 'stack-overflow' in crash_lower:
        context['bug_category'] = 'STACK_OVERFLOW'
    elif 'integer-overflow' in crash_lower:
        context['bug_category'] = 'INTEGER_OVERFLOW'
    elif 'undefined behavior' in crash_lower:
        context['bug_category'] = 'UNDEFINED_BEHAVIOR'
    elif 'assertion' in crash_lower or 'assert' in crash_lower:
        context['bug_category'] = 'ASSERTION_FAILURE'
    
    return context


def classify_bug_type(crash_type: str) -> str:
    """
    Fallback classification based on crash_type field (if crash_output is unavailable).
    """
    if not crash_type:
        return 'UNKNOWN'
    
    crash_lower = crash_type.lower()
    
    if 'heap-buffer-overflow' in crash_lower:
        return 'HEAP_BUFFER_OVERFLOW'
    elif 'stack-buffer-overflow' in crash_lower:
        return 'STACK_BUFFER_OVERFLOW'
    elif 'use-after-free' in crash_lower:
        return 'USE_AFTER_FREE'
    elif 'null' in crash_lower:
        return 'NULL_POINTER'
    elif 'segv' in crash_lower:
        return 'SEGMENTATION_FAULT'
    else:
        return crash_type.upper().replace('-', '_').replace(' ', '_')


def get_fix_hint(bug_category: str) -> str:
    """
    Provide a hint for fixing each bug category.
    """
    hints = {
        'HEAP_BUFFER_OVERFLOW': 'Add bounds check before array/buffer access',
        'STACK_BUFFER_OVERFLOW': 'Add bounds check or increase buffer size',
        'GLOBAL_BUFFER_OVERFLOW': 'Add bounds check for global array access',
        'USE_AFTER_FREE': 'Check pointer validity before use or use smart pointers',
        'DOUBLE_FREE': 'Ensure pointer is only freed once or set to NULL after free',
        'NULL_POINTER': 'Add null pointer check before dereferencing',
        'SEGMENTATION_FAULT': 'Add pointer validation before access',
        'STACK_OVERFLOW': 'Limit recursion depth or reduce stack allocation',
        'INTEGER_OVERFLOW': 'Add overflow checks before arithmetic operations',
        'UNDEFINED_BEHAVIOR': 'Follow language standards for the operation',
        'ASSERTION_FAILURE': 'Ensure assertion condition is satisfied',
    }
    
    return hints.get(bug_category, 'Analyze crash log to determine appropriate fix')