# validator/arvo_data_loader.py

from .ssh_client import run_remote_command, ARVO_DB_PATH
import json
from typing import Dict, Any, Optional

def load_bug_data(local_id: int) -> Optional[Dict[str, Any]]:
    """
    Queries the ARVO DB on the remote VM via SSH and returns a structured bug entry.
    """
    
    # We query the essential fields needed for checkout and validation
    query = f"SELECT project, reproducer_vul, fix_commit, repo_addr, sanitizer, crash_type FROM arvo WHERE localId={local_id};"
    
    # Use SQLite's -json output for easy parsing
    remote_cmd = f"sqlite3 -json {ARVO_DB_PATH} \"{query}\""
    
    exit_code, stdout, stderr = run_remote_command(remote_cmd)
    
    if exit_code != 0:
        print(f"ERROR: Failed to query ARVO DB remotely. SSH Exit Code: {exit_code}\nStderr: {stderr}")
        return None
    
    try:
        # The output is a JSON array string containing the result
        data = json.loads(stdout)
        if data:
            # We assume the first entry is the desired one
            return data[0]
        return None
    except json.JSONDecodeError as e:
        print(f"ERROR: Could not parse JSON data from DB query. Error: {e}")
        print(f"Raw Output: {stdout[:200]}...")
        return None