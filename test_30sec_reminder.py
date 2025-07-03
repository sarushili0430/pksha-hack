#!/usr/bin/env python3
"""Test 30-second reminder functionality for hackathon demo"""

from supabase import create_client
from dotenv import load_dotenv
import os
import asyncio
from datetime import datetime, timezone, timedelta
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

async def test_30_second_reminder():
    """Test 30-second reminder creation"""
    print("=== Testing 30-Second Reminder Setup ===")
    
    # Get existing users and groups
    users = supabase.table('users').select('id, line_user_id').limit(2).execute()
    groups = supabase.table('groups').select('id, line_group_id').limit(1).execute()
    
    if not users.data or not groups.data:
        print("Error: No users or groups found")
        return
    
    user1_id = users.data[0]['id']
    user2_id = users.data[1]['id'] if len(users.data) > 1 else user1_id
    group_id = groups.data[0]['id']
    
    print(f"Using questioner: {user1_id}")
    print(f"Using target: {user2_id}")
    print(f"Using group: {group_id}")
    
    # Ensure group members exist
    try:
        supabase.table('group_members').upsert({
            'group_id': group_id,
            'user_id': user1_id,
            'joined_at': datetime.now(timezone.utc).isoformat()
        }).execute()
        
        if user2_id != user1_id:
            supabase.table('group_members').upsert({
                'group_id': group_id,
                'user_id': user2_id,
                'joined_at': datetime.now(timezone.utc).isoformat()
            }).execute()
    except Exception as e:
        print(f"Error setting up group members: {e}")
    
    # Create a test question with 30-second reminder
    question_text = "【ハッカソンデモ】みんなランチどこ行く？30秒でリマインドされるテストです"
    target_user_ids = [user2_id] if user2_id != user1_id else [user1_id]
    
    try:
        question_id = await question_service.create_question_record(
            group_id=group_id,
            questioner_user_id=user1_id,
            question_text=question_text,
            target_user_ids=target_user_ids,
            message_id="demo_test_123",
            remind_seconds=30  # 30秒リマインド
        )
        
        if question_id:
            print(f"✅ Question created: {question_id}")
            
            # Verify remind_at time
            question = supabase.table('questions').select('*').eq('id', question_id).execute()
            if question.data:
                remind_at = datetime.fromisoformat(question.data[0]['remind_at'].replace('Z', '+00:00'))
                now = datetime.now(timezone.utc)
                time_diff = (remind_at - now).total_seconds()
                
                print(f"✅ Remind time set: {remind_at}")
                print(f"✅ Time until reminder: {time_diff:.1f} seconds")
                
                if 25 <= time_diff <= 35:  # Allow some margin
                    print("✅ 30-second reminder timing is correct!")
                else:
                    print(f"⚠️ Warning: Expected ~30 seconds, got {time_diff:.1f}")
                
                # Show targets
                targets = supabase.table('question_targets').select('*').eq('question_id', question_id).execute()
                print(f"✅ Question targets: {len(targets.data)} records")
                
                return question_id
        else:
            print("❌ Failed to create question")
            
    except Exception as e:
        print(f"❌ Error creating question: {e}")
        
    return None

async def monitor_reminder_processing():
    """Monitor when the reminder gets processed"""
    print("\n=== Monitoring Reminder Processing ===")
    print("Checking every 5 seconds for reminder processing...")
    print("(Reminder loop now runs every 15 seconds)")
    
    for i in range(24):  # Check for 2 minutes max
        print(f"\nCheck #{i+1} (at {datetime.now().strftime('%H:%M:%S')})")
        
        # Check for due questions
        now_iso = datetime.now(timezone.utc).isoformat()
        due_questions = supabase.table('questions') \
            .select('*') \
            .lte('remind_at', now_iso) \
            .is_('resolved_at', 'null') \
            .execute()
        
        print(f"Due questions: {len(due_questions.data)}")
        
        for q in due_questions.data:
            remind_time = datetime.fromisoformat(q['remind_at'].replace('Z', '+00:00'))
            age = (datetime.now(timezone.utc) - remind_time).total_seconds()
            print(f"  Question {q['id'][:8]}... - Due {age:.1f}s ago")
            print(f"  Text: {q['question_text'][:50]}...")
        
        await asyncio.sleep(5)
    
    print("\nMonitoring complete.")

async def main():
    """Run 30-second reminder test"""
    print("=== 30-Second Reminder Test for Hackathon ===\n")
    
    # Clean up old test questions first
    try:
        old_questions = supabase.table('questions') \
            .select('id') \
            .ilike('question_text', '%ハッカソンデモ%') \
            .execute()
        
        if old_questions.data:
            for q in old_questions.data:
                supabase.table('questions').delete().eq('id', q['id']).execute()
            print(f"Cleaned up {len(old_questions.data)} old test questions\n")
    except Exception as e:
        print(f"Error cleaning up: {e}\n")
    
    # Create test question
    question_id = await test_30_second_reminder()
    
    if question_id:
        print(f"\n🎯 Question created successfully!")
        print(f"🕐 Reminder will be sent in ~30 seconds")
        print(f"📱 Check your LINE for the reminder message")
        print(f"\n💡 The reminder loop runs every 15 seconds, so actual")
        print(f"   delivery may take up to 45 seconds after the due time.")
        
        # Optional: Monitor the processing
        await monitor_reminder_processing()
    else:
        print("\n❌ Test failed - could not create question")

if __name__ == "__main__":
    asyncio.run(main())