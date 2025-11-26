#!/usr/bin/env python3
"""
Test script to debug Codestral API connection
"""

import os
import sys

print("=" * 80)
print("CODESTRAL API DIAGNOSIS")
print("=" * 80)

# Step 1: Check environment variable
print("\n1. Checking environment variable...")
api_key = os.environ.get("MISTRAL_API_KEY")

if not api_key:
    print("ERROR: MISTRAL_API_KEY not set in environment")
    print("Run: export MISTRAL_API_KEY='your_key_here'")
    sys.exit(1)

# Clean the key
api_key = api_key.strip().strip('"').strip("'")

print(f"   API Key found: {len(api_key)} characters")
print(f"   First 10 chars: {api_key[:10]}")
print(f"   Last 5 chars: ...{api_key[-5:]}")

# Step 2: Try importing Mistral
print("\n2. Importing Mistral SDK...")
try:
    from mistralai import Mistral
    print("   SUCCESS: Mistral SDK imported")
except ImportError as e:
    print(f"   ERROR: Could not import Mistral SDK: {e}")
    print("   Run: pip install mistralai")
    sys.exit(1)

# Step 3: Initialize client
print("\n3. Initializing Mistral client...")
try:
    client = Mistral(api_key=api_key)
    print("   SUCCESS: Client initialized")
except Exception as e:
    print(f"   ERROR: Could not initialize client: {e}")
    sys.exit(1)

# Step 4: Test with different models
models_to_test = [
    'codestral-latest',
    'codestral-2405',
    'codestral-mamba-latest'
]

for model in models_to_test:
    print(f"\n4. Testing with model: {model}")
    try:
        response = client.chat.complete(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": "Write a single line comment in C++ saying hello"
                }
            ],
            temperature=0.1,
            max_tokens=50
        )
        
        if response and response.choices:
            content = response.choices[0].message.content
            print(f"   SUCCESS with {model}!")
            print(f"   Response: {content[:100]}")
            print(f"\n✓ Use this model: {model}")
            break
        else:
            print(f"   FAILED: Empty response from {model}")
            
    except Exception as e:
        error_msg = str(e)
        print(f"   FAILED with {model}: {error_msg[:200]}")
        
        # Check for specific errors
        if "401" in error_msg or "Unauthorized" in error_msg:
            print("\n   Diagnosis: API key is not valid or not authorized for this model")
            print("   Solutions:")
            print("   1. Verify your API key at https://console.mistral.ai/")
            print("   2. Check if your account has access to Codestral")
            print("   3. Make sure you're using a Codestral-specific API key")
        elif "404" in error_msg:
            print(f"   Diagnosis: Model '{model}' not found")
        elif "429" in error_msg:
            print("   Diagnosis: Rate limit exceeded")

print("\n" + "=" * 80)
print("DIAGNOSIS COMPLETE")
print("=" * 80)