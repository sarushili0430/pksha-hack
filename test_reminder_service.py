#!/usr/bin/env python3
"""Test payment reminder service"""

import asyncio
import os
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from app.reminder_service import reminder_service
from app.database_service import database_service

load_dotenv()

async def test_reminder_service():
    """リマインダーサービスのテスト"""
    print("=== Payment Reminder Service Test ===")
    
    # 既存のグループとユーザーを取得
    groups = database_service.supabase.table('groups').select('id, line_group_id').limit(1).execute()
    users = database_service.supabase.table('users').select('id, line_user_id, display_name').limit(1).execute()
    
    if not groups.data or not users.data:
        print("❌ No groups or users found in database")
        return
    
    group_id = groups.data[0]['id']
    user_id = users.data[0]['id']
    
    print(f"Using group: {group_id}")
    print(f"Using user: {user_id}")
    
    # テスト用の支払いリクエストを作成（10秒後にリマインド）
    now = datetime.now(timezone.utc)
    remind_at = now + timedelta(seconds=10)
    
    test_request = {
        "group_id": group_id,
        "requester_user_id": user_id,
        "amount": 1000,
        "remind_at": remind_at.isoformat()
    }
    
    # データベースに保存
    result = database_service.supabase.table("money_requests").insert(test_request).execute()
    
    if result.data:
        request_id = result.data[0]['id']
        print(f"✅ Test payment request created: {request_id}")
        print(f"✅ Reminder time: {remind_at}")
        print(f"✅ Amount: 1000 yen")
        print(f"✅ Will be reminded in 10 seconds")
        
        # 1回だけリマインダー処理をテスト
        print("\n=== Testing reminder processing ===")
        
        # 15秒待つ（リマインダー時間を過ぎるのを待つ）
        print("Waiting 15 seconds for reminder time to pass...")
        await asyncio.sleep(15)
        
        # リマインダー処理を実行
        print("Processing due reminders...")
        await reminder_service.process_due_reminders()
        
        # リマインダーが送信されたか確認
        updated_request = database_service.supabase.table("money_requests") \
            .select("*") \
            .eq("id", request_id) \
            .execute()
        
        if updated_request.data:
            reminded_at = updated_request.data[0].get("reminded_at")
            if reminded_at:
                print(f"✅ Reminder sent at: {reminded_at}")
                print("✅ Test completed successfully!")
            else:
                print("❌ Reminder was not sent")
        else:
            print("❌ Could not find updated request")
            
    else:
        print("❌ Failed to create test payment request")

if __name__ == "__main__":
    asyncio.run(test_reminder_service())