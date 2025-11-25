# workflow/nodes.py

from google import genai 
from typing import Dict
from .state import AgentState 
import os 
import json 
import re
from validator.validator_interface import run_validation

client = None
try:
    client = genai.Client() 
except Exception as e:
    print(f"Warning: Could not initialize Gemini client. Details: {e}")
    client = None
    
MODEL = 'gemini-2.5-flash' 
PROMPTS_DIR = 'prompts' 

def load_prompt(filename):
    """Loads a prompt template from the prompts directory."""
    try:
        with open(os.path.join(PROMPTS_DIR, filename), 'r') as f:
            return f.read()
    except FileNotFoundError:
        raise FileNotFoundError(f"Prompt file not found: {os.path.join(PROMPTS_DIR, filename)}")


def generate_realistic_patch(analysis: Dict[str, str], bug_data: Dict, actual_code: str = None, actual_file_path: str = None) -> str:
    """
    Generate a realistic patch based on actual code context.
    
    Uses actual code if available, otherwise generates a pattern-based patch.
    """
    bug_type = analysis['bug_type']
    
    # Use the actual file path from code fetcher if available
    if actual_file_path:
        file_path = actual_file_path
    else:
        from workflow.code_fetcher import clean_file_path
        file_path = clean_file_path(analysis['file_path'])
    
    line_num = int(analysis['line_number']) if analysis['line_number'].isdigit() else 100
    
    if actual_code:
        # Parse actual code to generate realistic patch
        lines = actual_code.splitlines()
        
        # Find the target line
        target_line_content = None
        target_index = -1
        actual_line_num = line_num
        
        for i, line in enumerate(lines):
            # Extract line number from formatted code
            if '|' in line:
                parts = line.split('|', 1)
                try:
                    current_line_num = int(parts[0].strip())
                    if current_line_num == line_num:
                        target_index = i
                        target_line_content = parts[1].rstrip()
                        actual_line_num = current_line_num
                        break
                except ValueError:
                    continue
        
        if target_index >= 0 and target_line_content:
            # Get context lines (without line numbers)
            context_before = []
            context_after = []
            
            for i in range(max(0, target_index - 3), target_index):
                if '|' in lines[i]:
                    line_content = lines[i].split('|', 1)[1].rstrip()
                    context_before.append(line_content)
            
            for i in range(target_index + 1, min(len(lines), target_index + 4)):
                if '|' in lines[i]:
                    line_content = lines[i].split('|', 1)[1].rstrip()
                    context_after.append(line_content)
            
            # Generate patch based on bug type
            if bug_type == 'HEAP_BUFFER_OVERFLOW':
                # Look for array/buffer access in target line
                if '[' in target_line_content and ']' in target_line_content:
                    # Extract indentation
                    indent = len(target_line_content) - len(target_line_content.lstrip())
                    indent_str = ' ' * indent
                    
                    # Try to extract variable names
                    match = re.search(r'(\w+)\[([^\]]+)\]', target_line_content)
                    if match:
                        array_name = match.group(1)
                        index_expr = match.group(2)
                        
                        # Build patch with bounds check
                        patch = f"""--- a/{file_path}
+++ b/{file_path}
@@ -{actual_line_num},6 +{actual_line_num},9 @@"""
                        
                        for line in context_before:
                            patch += f"\n {line}"
                        
                        patch += f"\n+{indent_str}if ({index_expr} >= 0 && static_cast<size_t>({index_expr}) < {array_name}_size) {{"
                        patch += f"\n {target_line_content}"
                        patch += f"\n+{indent_str}}}"
                        
                        for line in context_after[:2]:
                            patch += f"\n {line}"
                        
                        return patch.strip()
            
            # Generic fix for any bug type
            indent = len(target_line_content) - len(target_line_content.lstrip())
            indent_str = ' ' * indent
            
            patch = f"""--- a/{file_path}
+++ b/{file_path}
@@ -{actual_line_num},6 +{actual_line_num},9 @@"""
            
            for line in context_before:
                patch += f"\n {line}"
            
            patch += f"\n+{indent_str}// Add safety check here"
            patch += f"\n {target_line_content}"
            
            for line in context_after[:2]:
                patch += f"\n {line}"
            
            return patch.strip()
    
    # Fallback to minimal template-based patch
    if bug_type == 'HEAP_BUFFER_OVERFLOW':
        patch = f"""--- a/{file_path}
+++ b/{file_path}
@@ -{line_num},5 +{line_num},8 @@
     // Context line before
+    if (index >= 0 && static_cast<size_t>(index) < buffer_size) {{
         buffer[index] = value;
+    }}
     // Context line after"""
    
    elif bug_type == 'NULL_POINTER':
        patch = f"""--- a/{file_path}
+++ b/{file_path}
@@ -{line_num},5 +{line_num},8 @@
     // Context line before
+    if (ptr != nullptr) {{
         ptr->member = value;
+    }}
     // Context line after"""
    
    elif bug_type == 'USE_AFTER_FREE':
        patch = f"""--- a/{file_path}
+++ b/{file_path}
@@ -{line_num},5 +{line_num},8 @@
     // Context line before
+    if (ptr != nullptr) {{
         ptr->member = value;
+    }}
     // Context line after"""
    
    else:
        patch = f"""--- a/{file_path}
+++ b/{file_path}
@@ -{line_num},5 +{line_num},8 @@
     // Context line before
+    // Add safety check
     risky_operation();
     // Context line after"""
    
    return patch.strip()


def clean_gemini_patch_output(raw_output: str) -> str:
    """
    Aggressively clean Gemini's output to extract only the valid patch.
    """
    cleaned = re.sub(r'```diff\s*\n', '', raw_output)
    cleaned = re.sub(r'```\s*\n', '', cleaned)
    cleaned = re.sub(r'```', '', cleaned)
    
    lines = cleaned.splitlines()
    patch_start = -1
    patch_end = len(lines)
    
    for i, line in enumerate(lines):
        if line.startswith('---') and not line.startswith('---EXPLANATION'):
            patch_start = i
            break
        elif line.startswith('diff --git'):
            patch_start = i
            break
    
    if patch_start >= 0:
        for i in range(patch_start + 1, len(lines)):
            line = lines[i].strip()
            if line and not any([
                line.startswith('---'),
                line.startswith('+++'),
                line.startswith('@@'),
                line.startswith('+'),
                line.startswith('-'),
                line.startswith(' '),
                line.startswith('diff --git'),
                line == ''
            ]):
                patch_end = i
                break
    
    if patch_start == -1:
        print("WARNING: Could not find patch start marker (---)")
        return raw_output.strip()
    
    patch_lines = lines[patch_start:patch_end]
    return '\n'.join(patch_lines).strip()


def validate_patch_format(patch: str) -> tuple[bool, list[str]]:
    """
    Validate that a patch follows unified diff format.
    """
    errors = []
    
    if not patch.strip():
        errors.append("Patch is empty")
        return False, errors
    
    lines = patch.splitlines()
    
    has_minus_header = any(line.startswith('---') for line in lines)
    has_plus_header = any(line.startswith('+++') for line in lines)
    has_hunk = any(line.startswith('@@') for line in lines)
    
    if not has_minus_header:
        errors.append("Missing '---' file header")
    if not has_plus_header:
        errors.append("Missing '+++' file header")
    if not has_hunk:
        errors.append("Missing '@@ hunk header")
    
    if '```' in patch:
        errors.append("Contains markdown code blocks (```)")
    
    for i, line in enumerate(lines[:5]):
        if line and not any([
            line.startswith('---'),
            line.startswith('+++'),
            line.startswith('diff --git'),
            line.startswith('index '),
            line.strip() == ''
        ]):
            errors.append(f"Line {i+1}: Unexpected content before patch: '{line[:50]}'")
    
    is_valid = len(errors) == 0
    return is_valid, errors


def analyze_bug_from_data(bug_data: Dict) -> Dict[str, str]:
    """
    Extract key information from bug data for better patch generation.
    """
    file_path = bug_data.get('extracted_file_path', 'unknown')
    line_number = bug_data.get('extracted_line_number', '0')
    bug_category = bug_data.get('bug_category', 'UNKNOWN')
    language = bug_data.get('language', 'C++')
    
    from validator.arvo_data_loader import get_fix_hint
    fix_hint = get_fix_hint(bug_category)
    
    if file_path.startswith('/'):
        path_parts = file_path.split('/')
        if 'src' in path_parts:
            idx = path_parts.index('src')
            file_path = '/'.join(path_parts[idx:])
        elif 'include' in path_parts:
            idx = path_parts.index('include')
            file_path = '/'.join(path_parts[idx:])
        else:
            file_path = '/'.join(path_parts[-3:]) if len(path_parts) >= 3 else path_parts[-1]
    
    return {
        'file_path': file_path,
        'line_number': line_number,
        'bug_type': bug_category,
        'fix_hint': fix_hint,
        'language': language
    }


def lightweight_patch_generator_node(state: AgentState) -> AgentState:
    print("--- NODE 1: Lightweight Patch Generator (Gemini Call) ---")
    
    bug_data = state.get('bug_data', {})
    analysis = analyze_bug_from_data(bug_data)
    
    print("[PATCH GEN] Fetching actual code from repository...")
    from workflow.code_fetcher import fetch_code_context, format_code_for_prompt
    
    line_num = int(analysis['line_number']) if analysis['line_number'].isdigit() else 0
    code_result = fetch_code_context(bug_data, line_num, context_lines=20)
    
    actual_file_path = None
    actual_code = None
    
    if code_result:
        if isinstance(code_result, tuple):
            actual_code, actual_file_path = code_result
        else:
            actual_code = code_result
        
        formatted_code = format_code_for_prompt(actual_code, line_num)
        print(f"[PATCH GEN] Successfully fetched {len(actual_code.splitlines())} lines of actual code")
        if actual_file_path:
            print(f"[PATCH GEN] Actual file path: {actual_file_path}")
    else:
        formatted_code = "// Code fetch failed - using template"
        print(f"[PATCH GEN] Could not fetch code, will use template")
    
    if client is None:
        print("Gemini client not initialized, using template patch")
        template_patch = generate_realistic_patch(analysis, bug_data, actual_code, actual_file_path)
        state['current_patch'] = template_patch
        print(f"\nGenerated Template Patch:\n{template_patch}\n")
        return state
    
    # Create very generic prompt
    generic_prompt = f"""You are a code repair assistant. Generate a patch to fix a bug.

FILE: {actual_file_path if actual_file_path else analysis['file_path']}
LINE: {analysis['line_number']}

CODE:
```
{formatted_code}
```

TASK: Add a safety check at line {analysis['line_number']} to prevent array access issues.

OUTPUT: Unified diff format only (no explanations).

Example:
--- a/path/file.cpp
+++ b/path/file.cpp
@@ -10,6 +10,9 @@
+    if (index >= 0 && index < size) {{
         array[index] = value;
+    }}

NOW OUTPUT THE PATCH:
"""
    
    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=generic_prompt,
            config={
                'temperature': 0.2,
                'top_p': 0.95,
                'max_output_tokens': 2000
            }
        )
        
        if response.text is None:
            print("WARNING: Gemini blocked prompt")
            print("Falling back to template-based patch generation")
            
            template_patch = generate_realistic_patch(analysis, bug_data, actual_code, actual_file_path)
            state['current_patch'] = template_patch
            print(f"\nGenerated Template Patch:\n{template_patch}\n")
            print(f"Generated template patch for {analysis['bug_type']}")
            return state
        
        raw_patch = response.text
        cleaned_patch = clean_gemini_patch_output(raw_patch)
        
        print(f"\nRaw Gemini Output ({len(raw_patch)} chars):")
        print("─" * 80)
        print(raw_patch[:300])
        print("─" * 80)
        
        print(f"\nCleaned Patch ({len(cleaned_patch)} chars):")
        print("─" * 80)
        print(cleaned_patch[:300])
        print("─" * 80)
        
        is_valid, errors = validate_patch_format(cleaned_patch)
        
        if not is_valid:
            print(f"\nWARNING: Generated patch has format issues:")
            for error in errors:
                print(f"   - {error}")
            print("\nFalling back to template patch")
            template_patch = generate_realistic_patch(analysis, bug_data, actual_code, actual_file_path)
            state['current_patch'] = template_patch
            print(f"\nGenerated Template Patch:\n{template_patch}\n")
        else:
            print("\nPatch format validated successfully")
            state['current_patch'] = cleaned_patch
        
    except Exception as e:
        print(f"\nLLM Generation Failed: {e}")
        print("Falling back to template patch")
        template_patch = generate_realistic_patch(analysis, bug_data, actual_code, actual_file_path)
        state['current_patch'] = template_patch
        print(f"\nGenerated Template Patch:\n{template_patch}\n")
    
    print(f"Generated patch: Attempt {state['retry_count'] + 1}")
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
    print("--- NODE 5: Refinement Patch Generator (Gemini Call) ---")
    
    bug_data = state.get('bug_data', {})
    analysis = analyze_bug_from_data(bug_data)
    
    if client is None:
        print("Gemini client not initialized, generating improved template")
        
        from workflow.code_fetcher import fetch_code_context
        line_num = int(analysis['line_number']) if analysis['line_number'].isdigit() else 0
        code_result = fetch_code_context(bug_data, line_num, context_lines=20)
        
        actual_file_path = None
        actual_code = None
        
        if code_result:
            if isinstance(code_result, tuple):
                actual_code, actual_file_path = code_result
            else:
                actual_code = code_result
        
        improved_patch = generate_realistic_patch(analysis, bug_data, actual_code, actual_file_path)
        state['current_patch'] = improved_patch
        print(f"\nGenerated Improved Template Patch:\n{improved_patch}\n")
        return state

    prompt_template = load_prompt('patch_refinement.txt')
    
    validation_error = state['validation_result'].get('logs', 'Unknown error')[:1000]
    
    full_prompt = f"""{prompt_template}

PREVIOUS FAILURE
{state['failure_reason']}

PREVIOUS PATCH (FAILED)
{state['current_patch']}

VALIDATION ERROR
{validation_error}

LSP CONTEXT
{state['lsp_context']}

NOW OUTPUT IMPROVED PATCH (unified diff format only):
"""
    
    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=full_prompt,
            config={'temperature': 0.2, 'max_output_tokens': 2000}
        )
        
        if response.text is None:
            print("WARNING: Gemini blocked refinement prompt")
            print("Generating improved template patch")
            
            from workflow.code_fetcher import fetch_code_context
            line_num = int(analysis['line_number']) if analysis['line_number'].isdigit() else 0
            code_result = fetch_code_context(bug_data, line_num, context_lines=20)
            
            actual_file_path = None
            actual_code = None
            
            if code_result:
                if isinstance(code_result, tuple):
                    actual_code, actual_file_path = code_result
                else:
                    actual_code = code_result
            
            improved_patch = generate_realistic_patch(analysis, bug_data, actual_code, actual_file_path)
            state['current_patch'] = improved_patch
            print(f"\nGenerated Improved Template Patch:\n{improved_patch}\n")
            return state
        
        raw_patch = response.text
        cleaned_patch = clean_gemini_patch_output(raw_patch)
        
        print(f"\nRefined Patch ({len(cleaned_patch)} chars):")
        print("─" * 80)
        print(cleaned_patch[:300])
        print("─" * 80)
        
        is_valid, errors = validate_patch_format(cleaned_patch)
        if not is_valid:
            print(f"WARNING: Refined patch still has issues: {errors}")
            print("Using improved template instead")
            
            from workflow.code_fetcher import fetch_code_context
            line_num = int(analysis['line_number']) if analysis['line_number'].isdigit() else 0
            code_result = fetch_code_context(bug_data, line_num, context_lines=20)
            
            actual_file_path = None
            actual_code = None
            
            if code_result:
                if isinstance(code_result, tuple):
                    actual_code, actual_file_path = code_result
                else:
                    actual_code = code_result
            
            improved_patch = generate_realistic_patch(analysis, bug_data, actual_code, actual_file_path)
            state['current_patch'] = improved_patch
            print(f"\nGenerated Improved Template Patch:\n{improved_patch}\n")
        else:
            state['current_patch'] = cleaned_patch
        
    except Exception as e:
        print(f"Refinement failed: {e}")
        print("Generating improved template patch")
        
        from workflow.code_fetcher import fetch_code_context
        line_num = int(analysis['line_number']) if analysis['line_number'].isdigit() else 0
        code_result = fetch_code_context(bug_data, line_num, context_lines=20)
        
        actual_file_path = None
        actual_code = None
        
        if code_result:
            if isinstance(code_result, tuple):
                actual_code, actual_file_path = code_result
            else:
                actual_code = code_result
        
        improved_patch = generate_realistic_patch(analysis, bug_data, actual_code, actual_file_path)
        state['current_patch'] = improved_patch
        print(f"\nGenerated Improved Template Patch:\n{improved_patch}\n")
    
    print("Generated refinement patch. Preparing for re-validation.")
    return state