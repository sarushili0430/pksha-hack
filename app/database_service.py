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
    
    async def save_message(self, line_user_id: str, message_text: str, message_type: str = "text", 
                          line_group_id: Optional[str] = None, webhook_payload: Optional[Dict[Any, Any]] = None) -> bool:
        """
        メッセージをデータベースに保存
        """
        try:
            # ユーザーが存在しない場合は作成
            user_uuid = await self._ensure_user_exists(line_user_id)
            
            group_uuid = None
            # グループメッセージの場合はグループとメンバーシップを確認
            if line_group_id:
                group_uuid = await self._ensure_group_exists(line_group_id)
                await self._ensure_group_membership(user_uuid, group_uuid)
            
            # メッセージを保存
            message_data = {
                "user_id": user_uuid,
                "message_type": message_type,
                "text_content": message_text,
                "group_id": group_uuid,
                "raw_payload": webhook_payload
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
    
    async def _ensure_user_exists(self, line_user_id: str) -> str:
        """
        ユーザーが存在しない場合は作成し、UUIDを返す
        """
        try:
            result = self.supabase.table("users").select("id").eq("line_user_id", line_user_id).execute()
            
            if not result.data:
                user_data = {
                    "line_user_id": line_user_id,
                    "created_at": datetime.now().isoformat()
                }
                insert_result = self.supabase.table("users").insert(user_data).execute()
                logger.info(f"Created new user: {line_user_id}")
                return insert_result.data[0]["id"]
            else:
                return result.data[0]["id"]
                
        except Exception as e:
            logger.error(f"Error ensuring user exists: {e}")
            raise
    
    async def _ensure_group_exists(self, line_group_id: str) -> str:
        """
        グループが存在しない場合は作成し、UUIDを返す。存在していて group_name が空の場合は LINE API から取得して補完。
        """
        try:
            result = self.supabase.table("groups").select("id, group_name").eq("line_group_id", line_group_id).execute()
            if not result.data:
                # 初めて見るグループ。LINE API から名前を取得
                from .line_utils import line_utils  # 遅延 import で循環回避
                summary = await line_utils.get_group_summary(line_group_id)
                group_name = summary.get("group_name") if summary else None

                group_data = {
                    "line_group_id": line_group_id,
                    "group_name": group_name,
                    "created_at": datetime.now().isoformat()
                }
                insert_result = self.supabase.table("groups").insert(group_data).execute()
                logger.info(f"Created new group: {line_group_id} (name={group_name})")
                return insert_result.data[0]["id"]
            else:
                group_uuid = result.data[0]["id"]
                current_name = result.data[0].get("group_name")
                if not current_name:
                    # 既存だが名前が空 → 取得して更新
                    from .line_utils import line_utils
                    summary = await line_utils.get_group_summary(line_group_id)
                    new_name = summary.get("group_name") if summary else None
                    if new_name:
                        self.supabase.table("groups").update({"group_name": new_name}).eq("id", group_uuid).execute()
                        logger.info(f"Updated group name for {line_group_id} -> {new_name}")
                return group_uuid
        except Exception as e:
            logger.error(f"Error ensuring group exists: {e}")
            raise
    
    async def _ensure_group_membership(self, user_uuid: str, group_uuid: str) -> None:
        """
        グループメンバーシップが存在しない場合は作成し、last_active_atを更新
        """
        try:
            result = self.supabase.table("group_members").select("*").eq("user_id", user_uuid).eq("group_id", group_uuid).execute()
            
            if not result.data:
                membership_data = {
                    "user_id": user_uuid,
                    "group_id": group_uuid,
                    "joined_at": datetime.now().isoformat(),
                    "last_active_at": datetime.now().isoformat()
                }
                self.supabase.table("group_members").insert(membership_data).execute()
                logger.info(f"Created group membership: {user_uuid} in {group_uuid}")
            else:
                # 既存のメンバーシップのlast_active_atを更新
                self.supabase.table("group_members").update({
                    "last_active_at": datetime.now().isoformat()
                }).eq("user_id", user_uuid).eq("group_id", group_uuid).execute()
                logger.debug(f"Updated last_active_at for user {user_uuid} in group {group_uuid}")
                
        except Exception as e:
            logger.error(f"Error ensuring group membership: {e}")
    
    async def save_message_from_webhook(self, event_data: Dict[Any, Any], webhook_payload: Dict[Any, Any]) -> None:
        """
        Webhookイベントデータからメッセージを保存
        """
        try:
            line_user_id = event_data.get("source", {}).get("userId")
            message_text = event_data.get("message", {}).get("text")
            line_group_id = event_data.get("source", {}).get("groupId")
            
            if line_user_id and message_text:
                await self.save_message(
                    line_user_id=line_user_id,
                    message_text=message_text,
                    message_type="text",
                    line_group_id=line_group_id,
                    webhook_payload=webhook_payload
                )
        except Exception as e:
            logger.error(f"Error saving message from webhook: {e}")

# シングルトンインスタンス
database_service = DatabaseService()