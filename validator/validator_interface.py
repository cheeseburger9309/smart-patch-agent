# validator/validator_interface.py

from typing import Dict, Any, Literal
from .ssh_client import run_remote_command, VM_WORKSPACE
import re
import base64

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
    
    def critical_failure(reason: str, log: str) -> ValidatorResult:
        print(f"CRITICAL VALIDATION FAILURE: {reason}")
        return {
            'compiled': False,
            'poc_crash_detected': True,
            'functional_tests_passed': False,
            'poc_output': log,
            'compile_log': log
        }

    # SETUP: Clean Workspace, Clone, and Checkout
    setup_and_checkout_cmd = f"""
    mkdir -p {workspace_path} && cd {workspace_path} && 
    
    rm -rf repo_dir && 
    
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

    # PATCH APPLICATION
    # Clean the patch diff
    patch_diff_clean = patch_diff.replace('```diff', '').replace('```', '').strip()
    
    # Write patch to a temp file on the VM to avoid shell escaping issues
    patch_file = f"{workspace_path}/current.patch"
    
    # Encode patch as base64 to safely transfer
    import base64
    patch_b64 = base64.b64encode(patch_diff_clean.encode()).decode()
    
    write_patch_cmd = f"""
    echo "{patch_b64}" | base64 -d > {patch_file}
    """
    
    write_exit, write_out, write_err = run_remote_command(write_patch_cmd)
    if write_exit != 0:
        return critical_failure(
            "Patch Write Failed",
            f"Could not write patch file. Stderr: {write_err}"
        )
    
    # Apply the patch
    apply_patch_cmd = f"""
    cd {repo_path} &&
    patch -p1 --batch --forward < {patch_file}
    """
    patch_exit_code, patch_stdout, patch_stderr = run_remote_command(apply_patch_cmd)
    
    # Check if patch applied successfully
    if patch_exit_code != 0 and 'succeeded' not in patch_stdout.lower():
        # Try with different strip level
        apply_patch_cmd_p0 = f"""
        cd {repo_path} &&
        patch -p0 --batch --forward < {patch_file}
        """
        patch_exit_code, patch_stdout, patch_stderr = run_remote_command(apply_patch_cmd_p0)
        
        if patch_exit_code != 0 and 'succeeded' not in patch_stdout.lower():
            return critical_failure(
                "Patch Apply Failed",
                f"Patch failed to apply cleanly.\nStdout: {patch_stdout}\nStderr: {patch_stderr}"
            )
        
    # DOCKER EXECUTION (Build and Run PoC)
    docker_cmd = reproducer_vul.replace("arvo:", "arvo-vul ")
    
    full_docker_command = f"""
    cd {workspace_path} && 
    {docker_cmd} --rm -v {repo_path}:/src 
    """
    
    docker_exit_code, docker_output, docker_stderr = run_remote_command(full_docker_command)
    
    # RESULT ANALYSIS
    full_output = docker_output + docker_stderr
    poc_crash_detected = bool(re.search(r'(AddressSanitizer|UndefinedBehaviorSanitizer|Segmentation fault|SIGSEGV|ERROR)', full_output, re.IGNORECASE))
    
    compiled_successfully = docker_exit_code == 0 or poc_crash_detected 
    
    functional_tests_passed = not poc_crash_detected
    
    final_result: ValidatorResult = {
        'compiled': compiled_successfully,
        'compile_log': docker_stderr,
        'poc_crash_detected': poc_crash_detected,
        'functional_tests_passed': functional_tests_passed,
        'poc_output': full_output,
        'duration_seconds': 0.0
    }
    
    print("[VALIDATOR INTERFACE]: Validation complete.")
    return final_result