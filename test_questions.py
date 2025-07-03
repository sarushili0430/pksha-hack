#!/usr/bin/env python3
"""Test script for question system with production database"""

from supabase import create_client
from dotenv import load_dotenv
import os
import asyncio
from datetime import datetime, timezone
from app.question_service import get_question_service
from app.ai_service import get_ai_service

load_dotenv()
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_ANON_KEY')
openai_key = os.getenv('OPENAI_API_KEY')

# Initialize services
supabase = create_client(url, key)
ai_service = get_ai_service(openai_key)
question_service = get_question_service(supabase, ai_service)

async def setup_test_data():
    """Setup test data for question system"""
    print("Setting up test data...")
    
    # Get existing users and groups
    users = supabase.table('users').select('id, line_user_id').limit(2).execute()
    groups = supabase.table('groups').select('id, line_group_id').limit(1).execute()
    
    if users.data and groups.data:
        user1_id = users.data[0]['id']
        user2_id = users.data[1]['id'] if len(users.data) > 1 else user1_id
        group_id = groups.data[0]['id']
        
        print(f"Using users: {user1_id}, {user2_id}")
        print(f"Using group: {group_id}")
        
        # Add group members if they don't exist
        try:
            # Add first user to group
            supabase.table('group_members').upsert({
                'group_id': group_id,
                'user_id': user1_id,
                'joined_at': datetime.now(timezone.utc).isoformat()
            }).execute()
            
            # Add second user to group if different
            if user2_id != user1_id:
                supabase.table('group_members').upsert({
                    'group_id': group_id,
                    'user_id': user2_id,
                    'joined_at': datetime.now(timezone.utc).isoformat()
                }).execute()
            
            print("Group members added successfully")
            
            # Verify group members
            members = supabase.table('group_members').select('user_id').eq('group_id', group_id).execute()
            print(f"Group now has {len(members.data)} members")
            
            return group_id, user1_id, user2_id
            
        except Exception as e:
            print(f"Error adding group members: {e}")
            return None, None, None
    else:
        print("Not enough users or groups found in database")
        return None, None, None

async def test_question_detection():
    """Test question detection with real data"""
    print("\n=== Testing Question Detection ===")
    
    group_id, user1_id, user2_id = await setup_test_data()
    
    if not group_id:
        print("Failed to setup test data")
        return
    
    test_messages = [
        'みんな明日は暇？',
        '今日の会議の件どう思う？',
        'おはよう',
        'ランチ何食べたい？誰か提案して'
    ]
    
    for msg in test_messages:
        print(f"\nTesting message: '{msg}'")
        try:
            result = await question_service.detect_question_and_targets(msg, group_id)
            if result:
                is_question, targets, content = result
                print(f"  -> Question detected: {is_question}")
                print(f"  -> Targets: {len(targets)} users")
                print(f"  -> Content: {content}")
            else:
                print("  -> No question detected")
        except Exception as e:
            print(f"  -> Error: {e}")

async def test_question_creation():
    """Test question record creation"""
    print("\n=== Testing Question Creation ===")
    
    group_id, user1_id, user2_id = await setup_test_data()
    
    if not group_id:
        print("Failed to setup test data")
        return
    
    # Create a test question
    question_text = "テスト用質問: みんな明日の会議は何時から？"
    target_user_ids = [user1_id, user2_id] if user2_id != user1_id else [user1_id]
    
    try:
        question_id = await question_service.create_question_record(
            group_id=group_id,
            questioner_user_id=user1_id,
            question_text=question_text,
            target_user_ids=target_user_ids,
            message_id="test_message_123",
            remind_hours=1  # 1 hour for testing
        )
        
        if question_id:
            print(f"Question created successfully: {question_id}")
            
            # Verify question was created
            question = supabase.table('questions').select('*').eq('id', question_id).execute()
            if question.data:
                print(f"Question verified in database: {question.data[0]['question_text']}")
                
                # Check targets
                targets = supabase.table('question_targets').select('*').eq('question_id', question_id).execute()
                print(f"Question targets: {len(targets.data)} records")
                
                return question_id
        else:
            print("Failed to create question")
            
    except Exception as e:
        print(f"Error creating question: {e}")
        
    return None

async def test_response_detection():
    """Test response detection"""
    print("\n=== Testing Response Detection ===")
    
    question_id = await test_question_creation()
    
    if not question_id:
        print("No question to test response detection")
        return
    
    try:
        # Test response detection
        response_found = await question_service.check_for_responses(question_id)
        print(f"Response detection result: {response_found}")
        
        # Check question status
        question = supabase.table('questions').select('*').eq('id', question_id).execute()
        if question.data:
            resolved = question.data[0]['resolved_at']
            print(f"Question resolved: {resolved is not None}")
            
    except Exception as e:
        print(f"Error testing response detection: {e}")

async def main():
    """Run all tests"""
    print("=== Question System Test Suite ===")
    
    await test_question_detection()
    await test_question_creation()
    await test_response_detection()
    
    print("\n=== Test Complete ===")

if __name__ == "__main__":
    asyncio.run(main())