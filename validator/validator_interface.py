# validator/validator_interface.py

from typing import Dict, Any, Literal
from .ssh_client import run_remote_command, VM_WORKSPACE
import re # Used for parsing PoC output

ValidatorResult = Dict[str, Any]

def run_validation(
    bug_id: str,
    repo_addr: str,
    patch_diff: str,
    buggy_commit: str,
    reproducer_vul: str
) -> ValidatorResult:
    """
    Coordinates the remote validation process on the VM.
    
    Args:
        bug_id (str): The unique ARVO identifier.
        repo_addr (str): Git URL for cloning the project.
        patch_diff (str): The unified diff text to apply.
        buggy_commit (str): The specific commit hash to checkout.
        reproducer_vul (str): The full Docker command (from ARVO DB).

    Returns:
        ValidatorResult: A dictionary containing the structured validation results.
    """
    print(f"\n[VALIDATOR INTERFACE]: Starting remote validation for {bug_id}...")
    
    workspace_path = f"{VM_WORKSPACE}/{bug_id}"
    repo_path = f"{workspace_path}/repo_dir"
    
    # --- Helper function for returning a critical failure state ---
    def critical_failure(reason: str, log: str) -> ValidatorResult:
        print(f"CRITICAL VALIDATION FAILURE: {reason}")
        return {
            'compiled': False,
            'poc_crash_detected': True, # Treat setup failure as a crash for routing
            'functional_tests_passed': False,
            'poc_output': log,
            'compile_log': log
        }

    # --- 1. SETUP: Clean Workspace, Clone, and Checkout ---
    setup_and_checkout_cmd = f"""
    # Create and navigate to the project workspace
    mkdir -p {workspace_path} && cd {workspace_path} && 
    
    # Clean up old repo if it exists
    rm -rf repo_dir && 
    
    # Clone and Checkout Buggy Commit
    git clone {repo_addr} {repo_path} &&
    cd {repo_path} &&
    git checkout {buggy_commit}
    """
    exit_code, stdout, stderr = run_remote_command(setup_and_checkout_cmd)
    if exit_code != 0:
        return critical_failure(
            "Git Checkout Failed",
            f"Git clone/checkout failed. Exit Code: {exit_code}. Stderr: {stderr}"
        )

    # --- 2. PATCH APPLICATION (Embedding the patch string) ---
    # Pipe the patch diff directly to the patch command
    # NOTE: patch_diff content must be escaped for the shell command
    patch_diff_clean = patch_diff.replace('```diff', '').replace('```', '').strip() # NEW CLEANING STEP
    escaped_patch_diff = patch_diff_clean.replace('"', '\\"')
    
    apply_patch_cmd = f"""
    cd {repo_path} &&
    echo -e "{escaped_patch_diff}" | patch -p1 --batch --forward
    """
    patch_exit_code, patch_stdout, patch_stderr = run_remote_command(apply_patch_cmd)
    
    if patch_exit_code != 0 and 'succeeded' not in patch_stdout:
        return critical_failure(
            "Patch Apply Failed",
            f"Patch failed to apply cleanly. Stderr: {patch_stderr}"
        )
        
    # --- 3. DOCKER EXECUTION (Build and Run PoC) ---
    # The ARVO command is executed, mounting the patched repo into the container at /src
    docker_cmd = reproducer_vul.replace("arvo:", "arvo-vul ")
    
    full_docker_command = f"""
    cd {workspace_path} && 
    # Adjust the Docker command to mount the patched repo
    {docker_cmd} --rm -v {repo_path}:/src 
    """
    
    # Execute the command (this runs the compilation AND the crash test)
    # The timeout is handled in ssh_client.py (180s)
    docker_exit_code, docker_output, docker_stderr = run_remote_command(full_docker_command)
    
    # --- 4. RESULT ANALYSIS ---
    
    # Check for crash markers in the combined output
    full_output = docker_output + docker_stderr
    poc_crash_detected = bool(re.search(r'(AddressSanitizer|UndefinedBehaviorSanitizer|Segmentation fault|SIGSEGV|ERROR)', full_output, re.IGNORECASE))
    
    # Assume compilation failed if Docker exited with an error code > 0 and no crash was found
    # (Crash detection usually means compilation succeeded)
    compiled_successfully = docker_exit_code == 0 or poc_crash_detected 
    
    # Assume functional test passed if NO crash was detected
    functional_tests_passed = not poc_crash_detected
    
    final_result: ValidatorResult = {
        'compiled': compiled_successfully,
        'compile_log': docker_stderr,
        'poc_crash_detected': poc_crash_detected,
        'functional_tests_passed': functional_tests_passed,
        'poc_output': full_output,
        'duration_seconds': 0.0 # Placeholder for time tracking
    }
    
    print("[VALIDATOR INTERFACE]: Validation complete.")
    return final_result