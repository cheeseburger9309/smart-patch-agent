# run_agent.py

# Import from the installed library
from langgraph.graph import START, END, StateGraph 

# Import from your custom package 
from workflow.graph_builder import build_patch_agent_graph
from workflow.state import AgentState, PatchAttempt

# --- 1. Define Mock Input Data ---
initial_state_input: AgentState = {
    # Use a real ARVO ID to test remote database loading
    "bug_id": "40096184", 
    "initial_crash_log": "Placeholder log, actual log loaded from DB.",
    "buggy_code_snippet": "Placeholder snippet, actual code fetched on VM.",
    "max_retries": 3, 
    
    # Initialize dynamic/complex fields (must match state.py definition)
    "bug_data": {},  # Will be populated by Input Processor Node
    "all_patches": [],
    "current_patch": "",
    "validation_result": {},
    "failure_reason": "",
    "lsp_context": "",
    "retry_count": 0,
}


# --- 2. Main Execution Function ---
def run_test_workflow():
    """Builds the graph, generates the visualization, and executes the workflow."""
    
    print("--- Starting LangGraph Patch Agent Test ---")
    
    # Build the compiled LangGraph application
    app = build_patch_agent_graph()
    
    # --- Generate Visualization (Mermaid Format) ---
    try:
        graph_object = app.get_graph()
        mermaid_text = graph_object.draw_mermaid()
        
        mermaid_filename = "patch_agent_workflow.mermaid"
        with open(mermaid_filename, "w") as f:
            f.write(mermaid_text)
            
        print("\n Successfully generated graph visualization in Mermaid format:")
        print(f"   Saved to: {mermaid_filename}")
        
    except Exception as e:
        print(f"\n Could not generate graph image in Mermaid format. Error: {e}")
        
    # --- End Visualization ---

    inputs = initial_state_input.copy()

    print(f"Initial State Input: Bug ID {inputs['bug_id']}, Max Retries: {inputs['max_retries']}\n")
    
    try:
        # Run the workflow
        final_state = app.invoke(inputs)
        
        print("\n==================================================")
        print("        WORKFLOW FINISHED")
        print("==================================================")
        
        # Verify the final outcome
        if not final_state['validation_result'].get('poc_crash_detected', True):
            print("Status: SUCCESS (Final patch passed validation)")
        else:
            print(f"Status: FAILED (Gave up after {final_state['retry_count']} attempts, or failed setup)")
            
        print(f"Total Patch Attempts: {len(final_state['all_patches'])}")
        
    except Exception as e:
        print(f"\n A critical error occurred during graph execution: {e}")

# --- 3. Execute the Script ---
if __name__ == "__main__":
    run_test_workflow()