# workflow/code_fetcher.py
"""
Fetch actual source code from the repository to provide real context.
"""

from validator.ssh_client import run_remote_command, VM_WORKSPACE
from typing import Dict, Optional, Tuple
import re

def clean_file_path(file_path: str) -> str:
    """
    Clean up file paths from ASAN output.
    
    Handles patterns like:
    - /src/skia/out/Fuzz/../../src/codec/SkSwizzler.cpp
    - /out/Debug/../src/file.cpp
    """
    if not file_path:
        return ""
    
    # Remove leading /src/ if present
    if file_path.startswith('/src/'):
        file_path = file_path[5:]
    
    # Handle ../ patterns by resolving them
    parts = file_path.split('/')
    resolved = []
    
    for part in parts:
        if part == '..':
            if resolved:
                resolved.pop()
        elif part and part != '.':
            resolved.append(part)
    
    result = '/'.join(resolved)
    
    # Remove leading slash
    result = result.lstrip('/')
    
    return result


def fetch_code_context(bug_data: Dict, line_number: int, context_lines: int = 15) -> Optional[Tuple[str, str]]:
    """
    Fetch actual code from the repository at the buggy commit.
    
    Args:
        bug_data: Bug information including repo and commit
        line_number: Line number where bug occurs
        context_lines: Number of lines before and after to fetch
        
    Returns:
        Tuple of (code_with_line_numbers, actual_file_path) or None if fetch fails
    """
    bug_id = bug_data.get('bug_id', 'unknown')
    repo_url = bug_data.get('repo_addr')
    commit_hash = bug_data.get('fix_commit')
    file_path = bug_data.get('extracted_file_path', '')
    
    if not repo_url or not commit_hash or not file_path:
        print(f"[CODE FETCHER] Missing required fields for code fetch")
        return None
    
    # Clean up file path
    cleaned_path = clean_file_path(file_path)
    
    if not cleaned_path:
        print(f"[CODE FETCHER] Could not clean file path: {file_path}")
        return None
    
    workspace = f"{VM_WORKSPACE}/{bug_id}"
    repo_dir = f"{workspace}/repo_dir"
    
    print(f"[CODE FETCHER] Fetching code from {cleaned_path} at line {line_number}")
    
    # Command to:
    # 1. Clone repo if needed
    # 2. Checkout the buggy commit (parent of fix commit)
    # 3. Extract lines around the bug
    fetch_cmd = f"""
        mkdir -p {workspace} &&
        cd {workspace} &&
        
        if [ ! -d "repo_dir" ]; then
            git clone {repo_url} repo_dir 2>&1
        fi &&
        
        cd repo_dir &&
        
        git checkout {commit_hash}~1 2>/dev/null || git checkout {commit_hash} &&
        
        if [ ! -f "{cleaned_path}" ]; then
            echo "ERROR: File not found: {cleaned_path}"
            find . -name "$(basename {cleaned_path})" -type f | head -1
            exit 1
        fi &&
        
        total_lines=$(wc -l < "{cleaned_path}") &&
        start_line=$(({line_number} - {context_lines})) &&
        end_line=$(({line_number} + {context_lines})) &&
        
        if [ $start_line -lt 1 ]; then start_line=1; fi &&
        if [ $end_line -gt $total_lines ]; then end_line=$total_lines; fi &&
        
        sed -n "${{start_line}},${{end_line}}p" "{cleaned_path}" | nl -v $start_line -w 4 -s " | "
    """
    
    exit_code, stdout, stderr = run_remote_command(fetch_cmd)
    
    found_path = cleaned_path
    
    if exit_code != 0:
        print(f"[CODE FETCHER] Failed to fetch code: {stderr}")
        
        # Try to find the file by basename
        basename = cleaned_path.split('/')[-1]
        find_cmd = f"cd {repo_dir} && find . -name '{basename}' -type f | head -1"
        find_exit, find_out, find_err = run_remote_command(find_cmd)
        
        if find_exit == 0 and find_out.strip():
            found_path = find_out.strip().lstrip('./')
            print(f"[CODE FETCHER] Found file at: {found_path}, retrying...")
            
            # Retry with found path
            retry_cmd = f"""
                cd {repo_dir} &&
                total_lines=$(wc -l < "{found_path}") &&
                start_line=$(({line_number} - {context_lines})) &&
                end_line=$(({line_number} + {context_lines})) &&
                
                if [ $start_line -lt 1 ]; then start_line=1; fi &&
                if [ $end_line -gt $total_lines ]; then end_line=$total_lines; fi &&
                
                sed -n "${{start_line}},${{end_line}}p" "{found_path}" | nl -v $start_line -w 4 -s " | "
            """
            
            retry_exit, retry_out, retry_err = run_remote_command(retry_cmd)
            if retry_exit == 0:
                stdout = retry_out
                exit_code = 0
            else:
                return None
        else:
            return None
    
    if not stdout or len(stdout.strip()) < 10:
        print(f"[CODE FETCHER] No code returned")
        return None
    
    print(f"[CODE FETCHER] Successfully fetched {len(stdout.splitlines())} lines")
    return (stdout, found_path)


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