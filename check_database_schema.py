#!/usr/bin/env python3
"""
Check what columns actually exist in the ARVO database
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from validator.ssh_client import run_remote_command, ARVO_DB_PATH

def check_database_schema():
    """Query the database schema to see available columns"""
    
    print("="*80)
    print("CHECKING ARVO DATABASE SCHEMA")
    print("="*80)
    
    # Get table schema
    schema_cmd = f"sqlite3 {ARVO_DB_PATH} '.schema arvo'"
    
    print("\n1. Getting table schema...")
    exit_code, stdout, stderr = run_remote_command(schema_cmd)
    
    if exit_code == 0:
        print("✅ Schema retrieved successfully:\n")
        print(stdout)
    else:
        print(f"❌ Failed to get schema: {stderr}")
        return
    
    # Get column names using PRAGMA
    pragma_cmd = f"sqlite3 {ARVO_DB_PATH} 'PRAGMA table_info(arvo);'"
    
    print("\n2. Getting column information...")
    exit_code, stdout, stderr = run_remote_command(pragma_cmd)
    
    if exit_code == 0:
        print("✅ Columns available:\n")
        print(stdout)
    else:
        print(f"❌ Failed to get columns: {stderr}")
        return
    
    # Get a sample row to see what data looks like
    sample_cmd = f"sqlite3 -json {ARVO_DB_PATH} 'SELECT * FROM arvo WHERE localId=40096184 LIMIT 1;'"
    
    print("\n3. Getting sample data for bug 40096184...")
    exit_code, stdout, stderr = run_remote_command(sample_cmd)
    
    if exit_code == 0:
        print("✅ Sample data retrieved:\n")
        import json
        try:
            data = json.loads(stdout)
            if data:
                # Pretty print the first entry
                print("Available fields:")
                for key in data[0].keys():
                    value = data[0][key]
                    if isinstance(value, str) and len(value) > 100:
                        print(f"  - {key}: (string, {len(value)} chars)")
                    else:
                        print(f"  - {key}: {type(value).__name__}")
        except json.JSONDecodeError:
            print(stdout)
    else:
        print(f"❌ Failed to get sample data: {stderr}")
    
    print("\n" + "="*80)
    print("RECOMMENDATION:")
    print("="*80)
    print("Based on the available columns above, update arvo_data_loader.py")
    print("to query only the columns that exist.")

if __name__ == "__main__":
    check_database_schema()