# workflow/input_processor.py - UPDATED VERSION

from workflow.state import AgentState
from validator.arvo_data_loader import load_bug_data
from typing import Dict, Any

def input_processor_node(state: AgentState) -> AgentState:
    """
    Loads necessary bug data from the remote ARVO DB and updates the state.
    
    Now properly extracts and formats all available information.
    """
    bug_id = state['bug_id']
    print(f"--- NODE: Input Processor (Loading data for {bug_id}) ---")
    
    # 1. Ensure bug_id is an integer and fetch data remotely
    try:
        bug_id_int = int(bug_id)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid bug_id '{bug_id}'; expected an integer or a string convertible to int.")
    
    bug_data = load_bug_data(bug_id_int)
    
    if bug_data is None:
        raise Exception(f"CRITICAL ERROR: Failed to load bug data for ID {bug_id} from remote DB.")

    # 2. Store the complete bug data in state
    state['bug_data'] = bug_data 
    
    # 3. Update the crash log and code snippet with actual data
    # The crash_output field contains the full ASAN/sanitizer output
    crash_output = bug_data.get('crash_output', '')
    
    if crash_output:
        # Truncate if too long (keep first 3000 chars for context)
        state['initial_crash_log'] = crash_output[:3000]
    else:
        state['initial_crash_log'] = f"No crash output available. Crash type: {bug_data.get('crash_type', 'unknown')}"
    
    # 4. For buggy_code_snippet, we'll need to fetch it from the repository
    # For now, use a placeholder (will be fetched by LSP or during validation)
    file_path = bug_data.get('extracted_file_path', 'unknown')
    line_num = bug_data.get('extracted_line_number', '0')
    
    state['buggy_code_snippet'] = f"""// File: {file_path}
// Line: {line_num}
// Bug Category: {bug_data.get('bug_category', 'UNKNOWN')}
// 
// Note: Full code context will be fetched from repository during patch generation.
// This is a placeholder. The actual buggy code will be obtained by:
//   1. Cloning the repository at the buggy commit
//   2. Extracting the function containing line {line_num} from {file_path}
"""

    # Log summary
    project_name = bug_data.get('project', '<unknown project>')
    repo_addr = bug_data.get('repo_addr') or ''
    repo_preview = repo_addr[:50] if repo_addr else "<no repo address>"
    
    print(f"✅ Data Loaded Successfully:")
    print(f"   Project: {project_name}")
    print(f"   Repository: {repo_preview}...")
    print(f"   Language: {bug_data.get('language', 'unknown')}")
    print(f"   Bug Category: {bug_data.get('bug_category', 'UNKNOWN')}")
    print(f"   Target File: {file_path}")
    print(f"   Target Line: {line_num}")
    
    return state