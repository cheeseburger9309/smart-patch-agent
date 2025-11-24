# workflow/nodes.py

from google import genai 
from typing import Dict
from .state import AgentState 
import os 
import json 
from validator.validator_interface import run_validation # Necessary import

# Initialize the Gemini Client.
client = None
try:
    # Client initialized here will attempt to use GEMINI_API_KEY from the environment
    client = genai.Client() 
except Exception as e:
    # This block handles the case where the API key is not found
    print(f"Warning: Could not initialize Gemini client. API key likely missing. Using mock patches. Details: {e}")
    client = None
    
MODEL = 'gemini-2.5-flash' 
PROMPTS_DIR = 'prompts' 

# --- Helper to load prompts ---
def load_prompt(filename):
    """Loads a prompt template from the prompts directory."""
    try:
        with open(os.path.join(PROMPTS_DIR, filename), 'r') as f:
            return f.read()
    except FileNotFoundError:
        raise FileNotFoundError(f"Prompt file not found: {os.path.join(PROMPTS_DIR, filename)}. Check your 'prompts/' directory.")

# --- Node 1: Lightweight Patch Generator ---
def lightweight_patch_generator_node(state: AgentState) -> AgentState:
    print("--- NODE 1: Lightweight Patch Generator (Gemini Call) ---")
    
    if client is None:
        print("Falling back to mock patch due to uninitialized client.")
        mock_patch = ("--- buggy_file.c\n+++ buggy_file.c\n@@ -10,6 +10,6 @@\n-    buffer[len] = '\\0';\n+    if (len < 512) buffer[len] = '\\0';\n")
        state['current_patch'] = mock_patch
        return state

    # --- REAL LLM LOGIC ---
    prompt_template = load_prompt('patch_initial.txt')
    
    prompt = prompt_template.format(
        initial_crash_log=state['initial_crash_log'],
        buggy_code_snippet=state['buggy_code_snippet']
    )
    
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt
    )
    
    # Handle NoneType response if safety filters block output
    if response.text is None:
        print("\n LLM Generation Failed: API returned NO CONTENT (Safety Block/Error).")
        # Fail gracefully by forcing a known error state to trigger the refinement loop
        raise Exception("LLM Generation Failed: API returned NoneType content.")

    state['current_patch'] = response.text.strip()
    
    print(f"Generated patch: Attempt {state['retry_count'] + 1}")
    return state


# --- Node 2: Validation Node (REAL EXECUTION) ---
def validation_node(state: AgentState) -> AgentState:
    print("--- NODE 2: Validation Node (VM Execution) ---")
    
    # CRITICAL: Safe access to the bug_data dictionary
    bug_data = state.get('bug_data')
    if not bug_data:
        raise Exception("Validation Node failed: Required 'bug_data' not found in state.")

    # 1. Call the real remote validation interface
    # This call communicates with the SSH client and Docker on the VM
    result = run_validation(
        state['bug_id'],
        bug_data['repo_addr'],
        state['current_patch'],
        bug_data['fix_commit'], # Using fix_commit as a proxy for the buggy commit base
        bug_data['reproducer_vul'] 
    )
    
    # 2. Map the robust result back to the LangGraph state
    is_compiled = result.get('compiled', False)
    poc_crash = result.get('poc_crash_detected', True) 
    tests_passed = result.get('functional_tests_passed', False)

    # Determine successful outcome for routing
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
    
    # Update retry count based on failure
    if not is_successful:
        state['retry_count'] += 1

    print(f"Validation result: {'SUCCESS' if is_successful else 'FAILURE'}.")
    return state

# --- Node 3: Failure Analyzer ---
def failure_analyzer_node(state: AgentState) -> AgentState:
    print("--- NODE 3: Failure Analyzer ---")
    
    validation_log = state['validation_result']['logs']
    
    # Simple heuristic analysis based on log keywords
    if "still crashing" in validation_log.lower() or "asan error" in validation_log.lower():
        reason = "CRASH_PERSISTS: Security vulnerability still present, possibly off-by-one error or wrong variable used."
    elif "syntax error" in validation_log.lower() or not state['validation_result']['compiled']:
        reason = "COMPILE_ERROR: Patch introduced syntax error. Need to check context for missing includes/definitions."
    else:
        reason = "LOGIC_ERROR: Functional tests failed, patch logic is incorrect (e.g., too conservative)."
        
    state['failure_reason'] = reason
    print(f"Failure diagnosed: {reason.split(':')[0]}.")
    return state

# --- Node 4: LSP Context Gatherer ---
def lsp_context_gatherer_node(state: AgentState) -> AgentState:
    print("--- NODE 4: LSP Context Gatherer ---")
    
    # NOTE: This node is currently mocked. 
    # Real implementation uses SSH to run remote LSP queries on the patched codebase.
    
    failure_reason = state['failure_reason']
    
    if "CRASH_PERSISTS" in failure_reason:
        # Placeholder for data fetched by the remote LSP client
        lsp_output = ("LSP_CONTEXT:\nFunction 'process_input' Body: Found that 'len' is derived from user input and MAX_BUFFER_SIZE is 512.\nVariable 'buffer' Type: char[512].\nData Flow: 'len' can be 512, causing index 512 to be written, which is out-of-bounds (0-511).\n")
    else:
        lsp_output = "LSP_CONTEXT: Generic context gathered (e.g., function definition and headers)."
        
    state['lsp_context'] = lsp_output
    print("Gathered static context for refinement.")
    return state

# --- Node 5: Refinement Patch Generator ---
def refinement_patch_generator_node(state: AgentState) -> AgentState:
    print("--- NODE 5: Refinement Patch Generator (Gemini Call) ---")
    
    if client is None:
        print("Falling back to mock patch due to uninitialized client.")
        mock_patch = ("--- buggy_file.c\n+++ buggy_file.c\n@@ -10,6 +10,6 @@\n-    if (len < 512) buffer[len] = '\\0';\n+    if (len > 0 && len < 512) buffer[len] = '\\0';\n")
        state['current_patch'] = mock_patch
        return state

    # --- REAL LLM LOGIC ---
    prompt_template = load_prompt('patch_refinement.txt')
    
    prompt = prompt_template.format(
        buggy_code_snippet=state['buggy_code_snippet'],
        current_patch=state['current_patch'],
        validation_result=state['validation_result'],
        failure_reason=state['failure_reason'],
        lsp_context=state['lsp_context']
    )
    
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt
    )
    
    # CRITICAL FIX: Handle NoneType response
    if response.text is None:
        print("\n LLM Generation Failed: API returned NO CONTENT (Safety Block/Error).")
        raise Exception("LLM Generation Failed: API returned NoneType content during refinement.")

    state['current_patch'] = response.text.strip()
    
    print("Generated refinement patch based on LSP context. Preparing for re-validation.")
    return state