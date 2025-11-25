# workflow/code_fetcher.py
"""
Fetch actual source code from the repository to provide real context.
"""

from validator.ssh_client import run_remote_command, VM_WORKSPACE
from typing import Dict, Optional

def fetch_code_context(bug_data: Dict, line_number: int, context_lines: int = 15) -> Optional[str]:
    """
    Fetch actual code from the repository at the buggy commit.
    
    Args:
        bug_data: Bug information including repo and commit
        line_number: Line number where bug occurs
        context_lines: Number of lines before and after to fetch
        
    Returns:
        String containing the code with line numbers, or None if fetch fails
    """
    bug_id = bug_data.get('bug_id', 'unknown')
    repo_url = bug_data.get('repo_addr')
    commit_hash = bug_data.get('fix_commit')  # We'll checkout one commit before this
    file_path = bug_data.get('extracted_file_path', '')
    
    if not repo_url or not commit_hash or not file_path:
        print(f"[CODE FETCHER] Missing required fields for code fetch")
        return None
    
    # Clean up file path (remove build artifacts like /src/skia/out/Fuzz/../../)
    if '/../' in file_path:
        file_path = file_path.split('/../')[-1]
    
    # Remove leading slash if present
    file_path = file_path.lstrip('/')
    
    workspace = f"{VM_WORKSPACE}/{bug_id}"
    repo_dir = f"{workspace}/repo_dir"
    
    print(f"[CODE FETCHER] Fetching code from {file_path} at line {line_number}")
    
    # Command to:
    # 1. Clone repo if needed
    # 2. Checkout the buggy commit (parent of fix commit)
    # 3. Extract lines around the bug
    fetch_cmd = f"""
        # Setup workspace
        mkdir -p {workspace} &&
        cd {workspace} &&
        
        # Clone repo if not exists
        if [ ! -d "repo_dir" ]; then
            git clone {repo_url} repo_dir
        fi &&
        
        cd repo_dir &&
        
        # Checkout the buggy version (parent of fix commit)
        git checkout {commit_hash}~1 2>/dev/null || git checkout {commit_hash} &&
        
        # Check if file exists
        if [ ! -f "{file_path}" ]; then
            echo "ERROR: File not found: {file_path}"
            exit 1
        fi &&
        
        # Extract lines with context
        # Use sed to extract line_number +/- context_lines with line numbers
        total_lines=$(wc -l < "{file_path}") &&
        start_line=$(({line_number} - {context_lines})) &&
        end_line=$(({line_number} + {context_lines})) &&
        
        # Ensure bounds
        if [ $start_line -lt 1 ]; then start_line=1; fi &&
        if [ $end_line -gt $total_lines ]; then end_line=$total_lines; fi &&
        
        # Extract and number the lines
        sed -n "${{start_line}},${{end_line}}p" "{file_path}" | nl -v $start_line -w 4 -s " | "
    """
    
    exit_code, stdout, stderr = run_remote_command(fetch_cmd)
    
    if exit_code != 0:
        print(f"[CODE FETCHER] Failed to fetch code: {stderr}")
        return None
    
    if not stdout or len(stdout.strip()) < 10:
        print(f"[CODE FETCHER] No code returned")
        return None
    
    print(f"[CODE FETCHER] ✅ Successfully fetched {len(stdout.splitlines())} lines")
    return stdout


def format_code_for_prompt(code_with_lines: str, target_line: int) -> str:
    """
    Format the code nicely for inclusion in the Gemini prompt.
    Highlights the target line.
    """
    lines = code_with_lines.splitlines()
    formatted_lines = []
    
    for line in lines:
        # Check if this is the target line
        if f" {target_line} |" in line or f"{target_line} |" in line:
            formatted_lines.append(f">>> {line}  <<<< BUG HERE")
        else:
            formatted_lines.append(f"    {line}")
    
    return '\n'.join(formatted_lines)