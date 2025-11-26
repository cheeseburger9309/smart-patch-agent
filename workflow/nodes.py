# workflow/nodes.py - CODESTRAL VERSION

from mistralai import Mistral
from typing import Dict
from .state import AgentState 
import os 
import json 
import re
from validator.validator_interface import run_validation

# Initialize the Mistral Client with Codestral
client = None
api_key = None

try:
    api_key = os.environ.get("MISTRAL_API_KEY")
    client = Mistral(api_key=api_key)

except Exception as e:
    print(f"Warning: Could not initialize Mistral client. Details: {e}")
    client = None
    api_key = None
    
MODEL = 'codestral-latest'  # Use specific version instead of latest
PROMPTS_DIR = 'prompts' 

def load_prompt(filename):
    """Loads a prompt template from the prompts directory."""
    try:
        with open(os.path.join(PROMPTS_DIR, filename), 'r') as f:
            return f.read()
    except FileNotFoundError:
        raise FileNotFoundError(f"Prompt file not found: {os.path.join(PROMPTS_DIR, filename)}")


def analyze_bug_from_data(bug_data: Dict) -> Dict[str, str]:
    """Extract key information from bug data."""
    file_path = bug_data.get('extracted_file_path', 'unknown')
    line_number = bug_data.get('extracted_line_number', '0')
    bug_category = bug_data.get('bug_category', 'UNKNOWN')
    language = bug_data.get('language', 'C++')
    
    from validator.arvo_data_loader import get_fix_hint
    fix_hint = get_fix_hint(bug_category)
    
    # Clean up file path properly
    if '/../' in file_path:
        parts = file_path.split('/../')
        file_path = parts[-1]
    
    if file_path.startswith('/src/'):
        file_path = file_path[5:]
    
    file_path = file_path.lstrip('/')
    while file_path.startswith('../'):
        file_path = file_path[3:]
    
    return {
        'file_path': file_path,
        'line_number': line_number,
        'bug_type': bug_category,
        'fix_hint': fix_hint,
        'language': language
    }


def fetch_code_from_repo(bug_data: Dict, line_number: int, context_lines: int = 20) -> str:
    """Fetch actual code from repository."""
    from validator.ssh_client import run_remote_command, VM_WORKSPACE
    
    bug_id = bug_data.get('bug_id', 'unknown')
    repo_url = bug_data.get('repo_addr')
    commit_hash = bug_data.get('fix_commit')
    file_path = bug_data.get('extracted_file_path', '')
    
    if not all([repo_url, commit_hash, file_path]):
        return None
    
    # Clean file path properly
    if '/../' in file_path:
        parts = file_path.split('/../')
        file_path = parts[-1]
    
    file_path = file_path.lstrip('/')
    
    while file_path.startswith('../'):
        file_path = file_path[3:]
    
    workspace = f"{VM_WORKSPACE}/{bug_id}"
    
    print(f"[CODE FETCH] Clean file path: {file_path}")
    
    fetch_cmd = f"""
        mkdir -p {workspace} &&
        cd {workspace} &&
        
        if [ ! -d "repo_dir" ]; then
            echo "Cloning repository..."
            git clone {repo_url} repo_dir 2>&1 | head -10
        else
            echo "Repository already exists"
        fi &&
        
        cd repo_dir &&
        
        echo "Checking out commit {commit_hash}~1..." &&
        git checkout {commit_hash}~1 2>&1 | head -5 || git checkout {commit_hash} 2>&1 | head -5 &&
        
        echo "Checking if file exists: {file_path}" &&
        if [ ! -f "{file_path}" ]; then
            echo "ERROR: File not found: {file_path}"
            echo "Files in directory:"
            ls -la $(dirname "{file_path}") 2>&1 | head -10
            exit 1
        fi &&
        
        echo "Extracting code..." &&
        total_lines=$(wc -l < "{file_path}") &&
        start_line=$(({line_number} - {context_lines})) &&
        end_line=$(({line_number} + {context_lines})) &&
        
        if [ $start_line -lt 1 ]; then start_line=1; fi &&
        if [ $end_line -gt $total_lines ]; then end_line=$total_lines; fi &&
        
        sed -n "${{start_line}},${{end_line}}p" "{file_path}" | nl -v $start_line -w 4 -s " | "
    """
    
    print(f"[CODE FETCH] Executing fetch command...")
    exit_code, stdout, stderr = run_remote_command(fetch_cmd)
    
    print(f"[CODE FETCH] Exit code: {exit_code}")
    print(f"[CODE FETCH] Output length: {len(stdout)} chars")
    
    if exit_code != 0:
        print(f"[CODE FETCH] Command failed")
        print(f"[CODE FETCH] Stderr: {stderr[:500]}")
        print(f"[CODE FETCH] Stdout: {stdout[:500]}")
        return None
    
    if not stdout or len(stdout.strip()) < 10:
        print(f"[CODE FETCH] No code returned")
        return None
    
    # Extract just the code lines (remove echo messages)
    lines = stdout.splitlines()
    code_lines = [line for line in lines if '|' in line]
    
    if not code_lines:
        print(f"[CODE FETCH] No code lines found in output")
        return None
    
    result = '\n'.join(code_lines)
    print(f"[CODE FETCH] Got {len(code_lines)} lines of code")
    return result


def create_patch_prompt(code: str, file_path: str, line_number: str, bug_type: str, language: str) -> str:
    """
    Create a prompt for Codestral to generate a patch.
    Codestral is specifically trained for code generation and is less sensitive than Gemini.
    """
    
    # Map bug types to fix descriptions
    fix_descriptions = {
        'HEAP_BUFFER_OVERFLOW': 'add bounds checking before array access',
        'STACK_BUFFER_OVERFLOW': 'add bounds checking before buffer access',
        'NULL_POINTER': 'add null pointer check before dereferencing',
        'USE_AFTER_FREE': 'add pointer validation before use',
        'DOUBLE_FREE': 'prevent duplicate free operations',
        'INTEGER_OVERFLOW': 'add overflow checking for arithmetic operations',
    }
    
    fix_description = fix_descriptions.get(bug_type, 'add safety validation')
    
    # Highlight the target line
    code_lines = code.splitlines()
    highlighted_code = []
    for line in code_lines:
        if f" {line_number} |" in line or f"{line_number} |" in line:
            highlighted_code.append(f">>> {line}  // <- BUG IS HERE")
        else:
            highlighted_code.append(f"    {line}")
    
    formatted_code = '\n'.join(highlighted_code)
    
    prompt = f"""You are an expert C/C++ code repair specialist. Your task is to fix a {bug_type} bug.

FILE: {file_path}
BUG LINE: {line_number}
BUG TYPE: {bug_type}
FIX NEEDED: {fix_description}

BUGGY CODE:
```{language.lower()}
{formatted_code}
```

INSTRUCTIONS:
1. Focus on line {line_number} (marked with "BUG IS HERE")
2. Generate a minimal fix that {fix_description}
3. Output ONLY a unified diff patch in this exact format:

--- a/{file_path}
+++ b/{file_path}
@@ -oldline,count +newline,count @@
 context line (unchanged)
 context line (unchanged)
-old buggy line (if modified)
+fixed line with safety check
+additional safety check lines
 context line (unchanged)
 context line (unchanged)

REQUIREMENTS:
- Output ONLY the patch (no explanations, no markdown fences, no ```)
- Start directly with "--- a/"
- Include 3-5 lines of context before and after the change
- The patch must be applicable with the 'patch -p1' command

Generate the patch now:"""
    
    return prompt


def clean_codestral_response(response_text: str) -> str:
    """Clean up Codestral's response to extract just the patch."""
    if not response_text:
        return ""
    
    # Remove markdown fences
    cleaned = re.sub(r'```diff\s*\n', '', response_text)
    cleaned = re.sub(r'```\s*\n', '', cleaned)
    cleaned = re.sub(r'```', '', cleaned)
    
    # Find patch start
    lines = cleaned.splitlines()
    patch_start = -1
    
    for i, line in enumerate(lines):
        if line.startswith('---') or line.startswith('diff --git'):
            patch_start = i
            break
    
    if patch_start == -1:
        return cleaned.strip()
    
    # Extract from patch start to end (or until explanation text)
    patch_lines = []
    for i in range(patch_start, len(lines)):
        line = lines[i]
        
        # Stop if we hit explanatory text
        if i > patch_start + 5 and line and not any([
            line.startswith('---'),
            line.startswith('+++'),
            line.startswith('@@'),
            line.startswith('+'),
            line.startswith('-'),
            line.startswith(' '),
            line.startswith('diff'),
            line.strip() == ''
        ]):
            break
        
        patch_lines.append(line)
    
    return '\n'.join(patch_lines).strip()


def generate_fallback_patch(analysis: Dict, code: str) -> str:
    """
    Generate a simple template patch when LLM fails.
    Uses the actual code context.
    """
    file_path = analysis['file_path']
    line_num = int(analysis['line_number']) if analysis['line_number'].isdigit() else 100
    bug_type = analysis['bug_type']
    
    # Try to find the actual buggy line from code
    target_line_content = ""
    if code:
        for line in code.splitlines():
            if f" {line_num} |" in line:
                # Extract just the code part
                parts = line.split('|', 1)
                if len(parts) > 1:
                    target_line_content = parts[1].strip()
                break
    
    # Generate patch based on bug type
    if bug_type == 'HEAP_BUFFER_OVERFLOW' or bug_type == 'STACK_BUFFER_OVERFLOW':
        patch = f"""--- a/{file_path}
+++ b/{file_path}
@@ -{line_num},4 +{line_num},7 @@
     // Context before
+    if (index < 0 || index >= size) {{
+        return;
+    }}
     {target_line_content if target_line_content else '// Array access here'}
     // Context after
"""
    
    elif bug_type == 'NULL_POINTER':
        patch = f"""--- a/{file_path}
+++ b/{file_path}
@@ -{line_num},3 +{line_num},6 @@
     // Context before
+    if (ptr == nullptr) {{
+        return;
+    }}
     {target_line_content if target_line_content else '// Pointer use here'}
"""
    
    else:
        patch = f"""--- a/{file_path}
+++ b/{file_path}
@@ -{line_num},3 +{line_num},6 @@
     // Context before
+    if (!validate()) {{
+        return;
+    }}
     {target_line_content if target_line_content else '// Risky operation here'}
"""
    
    return patch.strip()


def lightweight_patch_generator_node(state: AgentState) -> AgentState:
    print("--- NODE 1: Lightweight Patch Generator (Codestral) ---")
    
    bug_data = state.get('bug_data', {})
    analysis = analyze_bug_from_data(bug_data)
    
    print(f"[PATCH GEN] Target: {analysis['file_path']}:{analysis['line_number']}")
    print(f"[PATCH GEN] Bug type: {analysis['bug_type']}")
    
    # Step 1: Fetch real code
    line_num = int(analysis['line_number']) if analysis['line_number'].isdigit() else 0
    actual_code = fetch_code_from_repo(bug_data, line_num, context_lines=15)
    
    if not actual_code:
        print("[PATCH GEN] Could not fetch code, using fallback")
        fallback_patch = generate_fallback_patch(analysis, None)
        state['current_patch'] = fallback_patch
        print(f"[PATCH GEN] Generated fallback patch ({len(fallback_patch)} chars)")
        return state
    
    # Step 2: Try Codestral
    if client is None:
        print("[PATCH GEN] No Mistral client, using fallback")
        fallback_patch = generate_fallback_patch(analysis, actual_code)
        state['current_patch'] = fallback_patch
        return state
    
    # Step 3: Create prompt
    prompt = create_patch_prompt(
        code=actual_code,
        file_path=analysis['file_path'],
        line_number=analysis['line_number'],
        bug_type=analysis['bug_type'],
        language=analysis['language']
    )
    
    print(f"[PATCH GEN] Created prompt ({len(prompt)} chars)")
    
    try:
        print("[PATCH GEN] Calling Codestral...")
        print(f"[PATCH GEN] Using model: {MODEL}")
        print(f"[PATCH GEN] API key present: {bool(api_key)}")
        if api_key:
            print(f"[PATCH GEN] API key starts with: {api_key[:10]}...")
        
        # Call Codestral using Mistral SDK
        response = client.chat.complete(
            model=MODEL,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.3,
            max_tokens=2000
        )
        
        print("[PATCH GEN] API call successful")
        
        if not response or not response.choices:
            print("[PATCH GEN] Codestral returned empty response, using fallback")
            fallback_patch = generate_fallback_patch(analysis, actual_code)
            state['current_patch'] = fallback_patch
            return state
        
        raw_patch = response.choices[0].message.content
        
        if not raw_patch:
            print("[PATCH GEN] Codestral returned None, using fallback")
            fallback_patch = generate_fallback_patch(analysis, actual_code)
            state['current_patch'] = fallback_patch
            return state
        
        # Clean the response
        cleaned_patch = clean_codestral_response(raw_patch)
        
        print(f"[PATCH GEN] Codestral generated patch ({len(cleaned_patch)} chars)")
        print(f"[PATCH GEN] Preview: {cleaned_patch[:200]}...")
        
        state['current_patch'] = cleaned_patch
        
    except Exception as e:
        print(f"[PATCH GEN] Error: {e}")
        print("[PATCH GEN] Using fallback patch")
        fallback_patch = generate_fallback_patch(analysis, actual_code)
        state['current_patch'] = fallback_patch
    
    return state


def validation_node(state: AgentState) -> AgentState:
    print("--- NODE 2: Validation Node (VM Execution) ---")
    
    bug_data = state.get('bug_data')
    if not bug_data:
        raise Exception("Validation Node failed: Required 'bug_data' not found in state.")

    result = run_validation(
        state['bug_id'],
        bug_data['repo_addr'],
        state['current_patch'],
        bug_data['fix_commit'],
        bug_data['reproducer_vul'] 
    )
    
    is_compiled = result.get('compiled', False)
    poc_crash = result.get('poc_crash_detected', True) 
    tests_passed = result.get('functional_tests_passed', False)

    if not is_compiled:
        is_successful = False
    elif poc_crash or not tests_passed:
        is_successful = False
    else:
        is_successful = True
        
    state['validation_result'] = {
        'compiled': is_compiled,
        'poc_crash_detected': poc_crash,
        'functional_tests_passed': tests_passed,
        'logs': result.get('poc_output', result.get('compile_log', 'Unknown Error'))
    }
    
    if not is_successful:
        state['retry_count'] += 1

    print(f"Validation result: {'SUCCESS' if is_successful else 'FAILURE'}.")
    return state


def failure_analyzer_node(state: AgentState) -> AgentState:
    print("--- NODE 3: Failure Analyzer ---")
    
    validation_log = state['validation_result']['logs']
    
    if "still crashing" in validation_log.lower() or "asan error" in validation_log.lower():
        reason = "CRASH_PERSISTS"
    elif "syntax error" in validation_log.lower() or not state['validation_result']['compiled']:
        reason = "COMPILE_ERROR"
    else:
        reason = "LOGIC_ERROR"
        
    state['failure_reason'] = reason
    print(f"Failure diagnosed: {reason}.")
    return state


def lsp_context_gatherer_node(state: AgentState) -> AgentState:
    print("--- NODE 4: LSP Context Gatherer ---")
    
    failure_reason = state['failure_reason']
    
    if "CRASH_PERSISTS" in failure_reason:
        lsp_output = "LSP_CONTEXT: Found bounds issue with array access."
    else:
        lsp_output = "LSP_CONTEXT: Generic context gathered."
        
    state['lsp_context'] = lsp_output
    print("Gathered static context for refinement.")
    return state


def refinement_patch_generator_node(state: AgentState) -> AgentState:
    print("--- NODE 5: Refinement Patch Generator (Codestral) ---")
    
    bug_data = state.get('bug_data', {})
    analysis = analyze_bug_from_data(bug_data)
    
    # Fetch code again
    line_num = int(analysis['line_number']) if analysis['line_number'].isdigit() else 0
    actual_code = fetch_code_from_repo(bug_data, line_num, context_lines=15)
    
    if not actual_code or client is None:
        print("[PATCH GEN] Using fallback for refinement")
        refined_patch = generate_fallback_patch(analysis, actual_code)
        state['current_patch'] = refined_patch
        return state
    
    # Create refinement prompt with failure context
    validation_error = state['validation_result'].get('logs', 'Unknown error')[:500]
    previous_patch = state['current_patch']
    
    refinement_prompt = f"""You are refining a patch that failed validation.

FILE: {analysis['file_path']}
LINE: {analysis['line_number']}
BUG TYPE: {analysis['bug_type']}

PREVIOUS PATCH (FAILED):
{previous_patch}

FAILURE REASON: {state['failure_reason']}

VALIDATION ERROR:
{validation_error}

ORIGINAL CODE:
```
{actual_code}
```

Generate an IMPROVED patch that fixes the issue. Output ONLY the unified diff patch (no explanations).

--- a/{analysis['file_path']}
+++ b/{analysis['file_path']}
@@ -line,count +line,count @@
 context
+improved fix
 context

Patch:"""
    
    try:
        print("[PATCH GEN] Calling Codestral for refinement...")
        
        response = client.chat.complete(
            model=MODEL,
            messages=[
                {
                    "role": "user",
                    "content": refinement_prompt
                }
            ],
            temperature=0.4,
            max_tokens=2000
        )
        
        if response and response.choices:
            raw_patch = response.choices[0].message.content
            if raw_patch:
                cleaned_patch = clean_codestral_response(raw_patch)
                print(f"[PATCH GEN] Codestral refined patch ({len(cleaned_patch)} chars)")
                state['current_patch'] = cleaned_patch
                return state
        
        print("[PATCH GEN] Codestral refinement failed, using fallback")
        
    except Exception as e:
        print(f"[PATCH GEN] Refinement error: {e}")
    
    # Fallback
    refined_patch = generate_fallback_patch(analysis, actual_code)
    state['current_patch'] = refined_patch
    print("Generated fallback refinement patch.")
    return state