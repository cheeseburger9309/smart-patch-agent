#!/usr/bin/env python3
import os
import json
import time
from typing import List
from validator.ssh_client import run_remote_command, ARVO_DB_PATH
from workflow.graph_builder import build_patch_agent_graph

# Configuration
LIMIT = 10
OUTPUT_FILE = "batch_results.json"

def get_testable_bug_ids(limit: int) -> List[int]:
    """Fetch bug IDs from ARVO that have a reproducer script."""
    print(f"[BATCH] Fetching {limit} testable bugs from DB...")
    
    # Query for bugs that have a reproduction command (reproducer_vul)
    # We sort by localId to get a consistent set
    query = f"""
    SELECT localId FROM arvo 
    WHERE reproducer_vul IS NOT NULL 
    AND reproducer_vul != ''
    ORDER BY localId DESC
    LIMIT {limit};
    """
    
    cmd = f"sqlite3 -json {ARVO_DB_PATH} \"{query}\""
    exit_code, stdout, stderr = run_remote_command(cmd)
    
    if exit_code != 0:
        print(f"[BATCH] Error fetching bugs: {stderr}")
        return []
        
    try:
        data = json.loads(stdout)
        return [item['localId'] for item in data]
    except json.JSONDecodeError:
        print("[BATCH] Failed to parse DB response")
        return []

def run_batch():
    bug_ids = get_testable_bug_ids(LIMIT)
    
    if not bug_ids:
        print("[BATCH] No bugs found to test.")
        return

    print(f"[BATCH] Found {len(bug_ids)} bugs: {bug_ids}")
    
    # Initialize the graph once
    app = build_patch_agent_graph()
    
    results = []
    
    for i, bug_id in enumerate(bug_ids):
        print(f"\n{'='*60}")
        print(f"PROCESSING BUG {i+1}/{len(bug_ids)}: ID {bug_id}")
        print(f"{'='*60}")
        
        start_time = time.time()
        
        initial_state = {
            "bug_id": str(bug_id),
            "initial_crash_log": "",
            "buggy_code_snippet": "",
            "max_retries": 3,
            "bug_data": {},
            "all_patches": [],
            "current_patch": "",
            "validation_result": {},
            "failure_reason": "",
            "lsp_context": "",
            "retry_count": 0,
        }
        
        try:
            # Execute Workflow
            final_state = app.invoke(initial_state)
            
            # Analyze Result
            val_result = final_state.get('validation_result', {})
            success = (not val_result.get('poc_crash_detected', True) and 
                       val_result.get('functional_tests_passed', False))
            
            status = "SUCCESS" if success else "FAILED"
            print(f"\n[BATCH] Bug {bug_id} Finished: {status}")
            
            results.append({
                "bug_id": bug_id,
                "status": status,
                "attempts": final_state.get('retry_count', 0),
                "duration": round(time.time() - start_time, 2),
                "failure_reason": final_state.get('failure_reason', ''),
                "final_patch": final_state.get('current_patch', '')
            })
            
        except Exception as e:
            print(f"[BATCH] Critical Error on Bug {bug_id}: {e}")
            results.append({
                "bug_id": bug_id,
                "status": "ERROR",
                "error": str(e)
            })

    # Save Results
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(results, f, indent=2)
        
    # Print Summary
    print(f"\n{'='*60}")
    print("BATCH EXECUTION SUMMARY")
    print(f"{'='*60}")
    success_count = sum(1 for r in results if r['status'] == 'SUCCESS')
    print(f"Total Bugs: {len(results)}")
    print(f"Success:    {success_count}")
    print(f"Failed:     {len(results) - success_count}")
    print(f"Results saved to: {OUTPUT_FILE}")

if __name__ == "__main__":
    run_batch()