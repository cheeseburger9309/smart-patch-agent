# workflow/state.py

from typing import TypedDict, List, Dict, Any

class PatchAttempt(TypedDict):
    """Stores the history and results of a single patch attempt."""
    patch: str
    validation_result: dict
    reason_for_failure: str
    context_used: str

class AgentState(TypedDict):
    """The central state dictionary carried by the LangGraph workflow."""
    
    # --- Input Fields ---
    bug_id: str
    initial_crash_log: str  # Will be updated by Input Processor
    buggy_code_snippet: str # Will be updated by Input Processor
    max_retries: int
    
    # --- NEW: Data loaded from ARVO DB ---
    bug_data: Dict[str, Any] # CRITICAL FIX: Holds the dictionary returned by load_bug_data
    
    # --- Core Loop Fields ---
    all_patches: List[PatchAttempt]
    current_patch: str
    validation_result: dict
    failure_reason: str
    lsp_context: str
    
    # --- Control Field ---
    retry_count: int