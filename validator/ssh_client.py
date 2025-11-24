# validator/ssh_client.py (Corrected Channel Opening)

import paramiko
import os
from typing import Tuple, Optional, Any

# --- Final Configuration (Using your verified details) ---
FINAL_HOST = "cs-mir.cs.uic.edu" 
FINAL_USER = "sai"         
FINAL_PORT = 2027
ARVO_DB_PATH = "/home/sai/smart_patch_agent/data/arvo.db" 

# Jump Host 1 Details
JUMP_HOST_NAME = "bertvm.cs.uic.edu"
JUMP_HOST_USER = "vjann3"
JUMP_HOST_PASSWORD = "wsyKE4Q*$G3i" 

# Password for the final user 'sai' on the target host
FINAL_PASSWORD = "ubuntu" 

# Target Workspace on the final host
VM_WORKSPACE = "/home/sai/patch_agent_workspace" 


def create_final_ssh_client(
    jump_host: str, jump_user: str, jump_pass: str, 
    target_host: str, target_port: int, target_user: str, target_pass: str
) -> Optional[paramiko.SSHClient]:
    """
    Establishes a multi-hop SSH connection and returns a ready-to-use SSHClient object.
    """
    print(f"SSH: Establishing connection via {jump_host}...")
    
    # 1. Connect to the initial Jump Host (bertvm)
    jump_client = paramiko.SSHClient()
    jump_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        jump_client.connect(hostname=jump_host, port=22, username=jump_user, 
                            password=jump_pass, timeout=30)
    except Exception as e:
        print(f"SSH ERROR: Failed to connect to jump host ({jump_host}): {e}")
        return None

    # 2. Open a direct TCP/IP tunnel channel to the final target host
    dest_addr = (target_host, target_port)
    local_addr = ('', 0) # Use ('', 0) for automatic selection of local port on jump host

    final_channel = None
    try:
        transport = jump_client.get_transport()
        if transport is None:
            print(f"SSH ERROR: No transport available from jump host ({jump_host}).")
            jump_client.close()
            return None
        # Use transport.open_channel to request a direct-tcpip channel to the final host
        final_channel = transport.open_channel(
            "direct-tcpip",
            dest_addr,
            local_addr
        )
    except Exception as e:
        print(f"SSH ERROR: Failed to open tunnel channel: {e}")
        jump_client.close()
        return None
    
    # 3. Create a new SSHClient using the channel and authenticate on the final host
    final_client = paramiko.SSHClient()
    final_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        # Use the established channel as the socket for the final connection
        final_client.connect(
            hostname='', # Hostname is irrelevant since we're using a channel
            username=target_user,
            password=target_pass,
            sock=final_channel, 
            timeout=30
        )
        print("SSH: Authentication successful on final host.")
        return final_client
    except Exception as e:
        print(f"SSH ERROR: Authentication failed on final host ({target_user}): {e}")
        # Close the channel and the jump client if authentication fails
        if final_channel: final_channel.close()
        jump_client.close()
        return None


def run_remote_command(command: str) -> Tuple[int, str, str]:
    """Executes a command on the remote VM (cs-mir) via the bertvm jump host."""
    
    # Create the final client connection
    ssh_client = create_final_ssh_client(
        JUMP_HOST_NAME, JUMP_HOST_USER, JUMP_HOST_PASSWORD,
        FINAL_HOST, FINAL_PORT, FINAL_USER, FINAL_PASSWORD
    )
    
    if ssh_client is None:
        return 1, "", "Connection to final host failed during creation."
    
    print(f"SSH: Executing remote command: {command[:80]}...")
    
    try:
        # Execute the command on the final client
        # Note: We are using a higher timeout (180s) for compilation/docker runs
        stdin, stdout, stderr = ssh_client.exec_command(command, timeout=180) 
        
        output = stdout.read().decode().strip()
        error = stderr.read().decode().strip()
        exit_code = stdout.channel.recv_exit_status()
        
        return exit_code, output, error

    except Exception as e:
        print(f"SSH ERROR: Failed to execute command on final host: {e}")
        return 1, "", str(e)
    
    finally:
        # Ensure the client and all associated channels are closed
        ssh_client.close()