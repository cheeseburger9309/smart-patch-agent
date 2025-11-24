# workflow/graph_builder.py

from langgraph.graph import StateGraph, START, END
from typing import Literal
from .state import AgentState 
from .nodes import (
    lightweight_patch_generator_node,
    validation_node,
    failure_analyzer_node,
    lsp_context_gatherer_node,
    refinement_patch_generator_node
)
from .input_processor import input_processor_node # Import the new data loading node

# 1. Define the Router Function (Conditional Edge)
def router_validate(state: AgentState) -> Literal["success", "refine", "give_up"]:
    """
    Decides the next node based on the validation result and retry count.
    
    This implements the conditional branching after the 'validate' node.
    """
    
    result = state.get('validation_result', {})
    
    # Success criterion: poc_crash_detected is False AND functional_tests_passed is True
    is_success = (
        not result.get('poc_crash_detected', True) and 
        result.get('functional_tests_passed', False)
    )

    if is_success:
        print("\n*** ROUTER: SUCCESS. Final patch found. ***\n")
        return "success"
        
    if state['retry_count'] > state['max_retries']:
        print("\n*** ROUTER: GIVE UP. Max retries exceeded. ***\n")
        return "give_up"
        
    print(f"\n*** ROUTER: FAILURE. Starting refinement (Attempt {state['retry_count']} of {state['max_retries']}). ***\n")
    return "refine"


# 2. Build and Compile the Graph
def build_patch_agent_graph():
    """
    Assembles the nodes and edges into the cyclical patch refinement workflow.
    
    """
    
    # Initialize the graph structure based on the AgentState
    workflow = StateGraph(AgentState)
    
    # --- Add all nodes ---
    workflow.add_node("input_process", input_processor_node)
    workflow.add_node("patch_gen_initial", lightweight_patch_generator_node)
    workflow.add_node("validate", validation_node)
    workflow.add_node("analyze_failure", failure_analyzer_node)
    workflow.add_node("gather_context", lsp_context_gatherer_node)
    workflow.add_node("patch_gen_refine", refinement_patch_generator_node)
    
    # --- Entry Path (CRITICAL FIX: Data Loading First) ---
    # 1. START -> Input Processor
    workflow.add_edge(START, "input_process")
    # 2. Input Processor -> Initial Patch Generator
    workflow.add_edge("input_process", "patch_gen_initial")

    # 3. Initial Patch Generator -> Validation
    workflow.add_edge("patch_gen_initial", "validate")
    
    # --- Conditional Routing after Validation ---
    workflow.add_conditional_edges(
        "validate",            # Source Node
        router_validate,       # Conditional Function
        {                      # Mapped Destinations
            "success": END,    # Patch found, terminate successfully
            "give_up": END,    # Max retries hit, terminate as failure
            "refine": "analyze_failure" # Failed, proceed to analysis/refinement
        }
    )
    
    # --- Refinement Loop ---
    workflow.add_edge("analyze_failure", "gather_context")
    workflow.add_edge("gather_context", "patch_gen_refine")
    workflow.add_edge("patch_gen_refine", "validate")
    
    # Compile and return the runnable graph
    app = workflow.compile()
    return app