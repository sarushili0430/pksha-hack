#!/usr/bin/env python3
"""
Test script for LINE message service functions
"""

import asyncio
import os
from app.message_service import message_service

async def test_message_service():
    """
    Test the LINE message service functions
    """
    print("Testing LINE message service functions...")
    
    # Test data
    test_user_id = "test_user_id"
    test_group_id = "test_group_id"
    test_message = "Hello! This is a test message."
    
    print("\n1. Testing send_message_to_user...")
    try:
        result = await message_service.send_message_to_user(test_user_id, test_message)
        print(f"   Result: {result}")
    except Exception as e:
        print(f"   Error: {e}")
    
    print("\n2. Testing send_message_to_group...")
    try:
        result = await message_service.send_message_to_group(test_group_id, test_message)
        print(f"   Result: {result}")
    except Exception as e:
        print(f"   Error: {e}")
    
    print("\n3. Testing send_messages_to_multiple_users...")
    try:
        test_user_ids = ["user1", "user2", "user3"]
        results = await message_service.send_messages_to_multiple_users(test_user_ids, test_message)
        print(f"   Results: {results}")
    except Exception as e:
        print(f"   Error: {e}")
    
    print("\n4. Testing send_message_to_group_members...")
    try:
        results = await message_service.send_message_to_group_members(test_group_id, test_message)
        print(f"   Results: {results}")
    except Exception as e:
        print(f"   Error: {e}")
    
    print("\n5. Testing internal ID functions...")
    try:
        # These will likely fail due to test IDs, but we can verify the code structure
        result = await message_service.send_message_to_user_by_internal_id("1", test_message)
        print(f"   User by internal ID result: {result}")
    except Exception as e:
        print(f"   User by internal ID error: {e}")
    
    try:
        result = await message_service.send_message_to_group_by_internal_id("1", test_message)
        print(f"   Group by internal ID result: {result}")
    except Exception as e:
        print(f"   Group by internal ID error: {e}")
    
    print("\nTest completed!")

if __name__ == "__main__":
    print("LINE Utils Test Script")
    print("=" * 50)
    
    # Check if environment variables are set
    required_env_vars = [
        "LINE_CHANNEL_ACCESS_TOKEN",
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY"
    ]
    
    missing_vars = []
    for var in required_env_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print(f"Missing required environment variables: {', '.join(missing_vars)}")
        print("Please set these variables before running the test.")
        exit(1)
    
    asyncio.run(test_message_service())