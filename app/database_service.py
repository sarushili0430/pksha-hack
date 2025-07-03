import os
import logging
from supabase import create_client, Client
from datetime import datetime
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class DatabaseService:
    def __init__(self):
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_ANON_KEY")
        
        if not supabase_url or not supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_ANON_KEY must be set")
        
        self.supabase: Client = create_client(supabase_url, supabase_key)
    
    async def save_message(self, user_id: str, message_text: str, message_type: str = "text", 
                          group_id: Optional[str] = None, webhook_payload: Optional[Dict[Any, Any]] = None) -> bool:
        """
        メッセージをデータベースに保存
        """
        try:
            # ユーザーが存在しない場合は作成
            await self._ensure_user_exists(user_id)
            
            # グループメッセージの場合はグループとメンバーシップを確認
            if group_id:
                await self._ensure_group_exists(group_id)
                await self._ensure_group_membership(user_id, group_id)
            
            # メッセージを保存
            message_data = {
                "user_id": user_id,
                "message_text": message_text,
                "message_type": message_type,
                "group_id": group_id,
                "webhook_payload": webhook_payload,
                "created_at": datetime.now().isoformat()
            }
            
            result = self.supabase.table("messages").insert(message_data).execute()
            
            if result.data:
                logger.info(f"Message saved successfully: {result.data[0]['id']}")
                return True
            else:
                logger.error("Failed to save message")
                return False
                
        except Exception as e:
            logger.error(f"Error saving message: {e}")
            return False
    
    async def _ensure_user_exists(self, user_id: str) -> None:
        """
        ユーザーが存在しない場合は作成
        """
        try:
            result = self.supabase.table("users").select("id").eq("id", user_id).execute()
            
            if not result.data:
                user_data = {
                    "id": user_id,
                    "created_at": datetime.now().isoformat()
                }
                self.supabase.table("users").insert(user_data).execute()
                logger.info(f"Created new user: {user_id}")
                
        except Exception as e:
            logger.error(f"Error ensuring user exists: {e}")
    
    async def _ensure_group_exists(self, group_id: str) -> None:
        """
        グループが存在しない場合は作成
        """
        try:
            result = self.supabase.table("groups").select("id").eq("id", group_id).execute()
            
            if not result.data:
                group_data = {
                    "id": group_id,
                    "created_at": datetime.now().isoformat()
                }
                self.supabase.table("groups").insert(group_data).execute()
                logger.info(f"Created new group: {group_id}")
                
        except Exception as e:
            logger.error(f"Error ensuring group exists: {e}")
    
    async def _ensure_group_membership(self, user_id: str, group_id: str) -> None:
        """
        グループメンバーシップが存在しない場合は作成
        """
        try:
            result = self.supabase.table("group_members").select("*").eq("user_id", user_id).eq("group_id", group_id).execute()
            
            if not result.data:
                membership_data = {
                    "user_id": user_id,
                    "group_id": group_id,
                    "created_at": datetime.now().isoformat()
                }
                self.supabase.table("group_members").insert(membership_data).execute()
                logger.info(f"Created group membership: {user_id} in {group_id}")
                
        except Exception as e:
            logger.error(f"Error ensuring group membership: {e}")
    
    async def save_message_from_webhook(self, event_data: Dict[Any, Any], webhook_payload: Dict[Any, Any]) -> None:
        """
        Webhookイベントデータからメッセージを保存
        """
        try:
            user_id = event_data.get("source", {}).get("userId")
            message_text = event_data.get("message", {}).get("text")
            group_id = event_data.get("source", {}).get("groupId")
            
            if user_id and message_text:
                await self.save_message(
                    user_id=user_id,
                    message_text=message_text,
                    message_type="text",
                    group_id=group_id,
                    webhook_payload=webhook_payload
                )
        except Exception as e:
            logger.error(f"Error saving message from webhook: {e}")

# シングルトンインスタンス
database_service = DatabaseService()