# workflow/input_processor.py

from workflow.state import AgentState
from validator.arvo_data_loader import load_bug_data
from typing import Dict, Any

def input_processor_node(state: AgentState) -> AgentState:
    """
    Loads necessary bug data from the remote ARVO DB and updates the state.
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

    # 2. Store the essential remote data in the state (CRITICAL FIX)
    state['bug_data'] = bug_data 
    
    # 3. Update the crash log/snippet placeholders with real data
    # (These fields are used by the LLM in NODE 1)
    state['initial_crash_log'] = bug_data.get('crash_output', "ARVO output placeholder: Run Docker to get full crash log.")
    state['buggy_code_snippet'] = "Code snippet around the crash (to be fetched by a separate LSP query later)."

    # Safely handle a missing repo address (avoid slicing None)
    repo_addr = str(bug_data.get('repo_addr') or "")
    repo_preview = repo_addr[:30] if repo_addr else "<no repo address>"
    project_name = bug_data.get('project', '<unknown project>')
    print(f"Data Loaded: Project {project_name}, Repo {repo_preview}...")
    return state