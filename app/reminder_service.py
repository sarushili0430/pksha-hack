import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import List, Dict, Any
from app.database_service import database_service
from app.message_service import message_service

logger = logging.getLogger(__name__)

class ReminderService:
    def __init__(self):
        self.running = False
        self.check_interval = 15  # 15秒ごとにチェック
    
    async def start_reminder_loop(self):
        """リマインダーループを開始"""
        self.running = True
        logger.info("Starting reminder loop...")
        
        while self.running:
            try:
                await self.process_due_reminders()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Error in reminder loop: {e}")
                await asyncio.sleep(self.check_interval)
    
    def stop_reminder_loop(self):
        """リマインダーループを停止"""
        self.running = False
        logger.info("Stopping reminder loop...")
    
    async def process_due_reminders(self):
        """期限が来たリマインダーを処理"""
        try:
            # 現在時刻を取得
            now = datetime.now(timezone.utc)
            now_iso = now.isoformat()
            
            # 期限が来た支払いリクエストを取得
            due_requests = database_service.supabase.table("money_requests") \
                .select("*") \
                .lte("remind_at", now_iso) \
                .is_("reminded_at", "null") \
                .execute()
            
            # 質問リマインダーも毎分実行
            await self.process_question_reminders()
            
            if not due_requests.data:
                return
            
            logger.info(f"Found {len(due_requests.data)} due payment reminders")
            
            # 各リマインダーを処理
            for request in due_requests.data:
                await self.send_payment_reminder(request)
                
        except Exception as e:
            logger.error(f"Error processing due reminders: {e}")
    
    async def send_payment_reminder(self, request: Dict[str, Any]):
        """支払いリマインダーメッセージを送信"""
        try:
            request_id = request["id"]
            group_id = request["group_id"]
            requester_user_id = request["requester_user_id"]
            amount = request["amount"]
            
            # グループ情報を取得
            group_info = database_service.supabase.table("groups") \
                .select("line_group_id") \
                .eq("id", group_id) \
                .execute()
            
            if not group_info.data:
                logger.error(f"Group not found: {group_id}")
                return
            
            line_group_id = group_info.data[0]["line_group_id"]
            
            # リクエスト者の情報を取得
            requester_info = database_service.supabase.table("users") \
                .select("display_name") \
                .eq("id", requester_user_id) \
                .execute()
            
            requester_name = "誰か"
            if requester_info.data:
                requester_name = requester_info.data[0]["display_name"] or "誰か"
            
            # リマインダーメッセージを作成
            reminder_message = f"\n\n{requester_name}さんから{amount}円の支払いリクエストがあります。\n\n忘れずに支払いをお願いします！"
            
            # LINEメッセージを送信
            await message_service.send_message_to_group(line_group_id, reminder_message)
            
            # reminded_atを更新
            now = datetime.now(timezone.utc)
            database_service.supabase.table("money_requests") \
                .update({"reminded_at": now.isoformat()}) \
                .eq("id", request_id) \
                .execute()
            
            logger.info(f"Payment reminder sent for request {request_id}")
            
        except Exception as e:
            logger.error(f"Error sending payment reminder: {e}")
    
    async def process_question_reminders(self):
        """質問リマインダーを処理"""
        try:
            # 質問リマインダーサービスを動的インポート（循環インポート回避）
            from app.question_reminder_service import question_reminder_service
            
            # デモ用: 2分非アクティブなユーザーに質問リマインダーを送信（5分間隔で再送）
            result = await question_reminder_service.process_all_inactive_users(hours_threshold=2/60, reminder_interval_hours=5/60)
            
            if result.get("reminders_sent", 0) > 0:
                logger.info(f"Question reminders sent: {result}")
            
        except Exception as e:
            logger.error(f"Error processing question reminders: {e}")

# シングルトンインスタンス
reminder_service = ReminderService()