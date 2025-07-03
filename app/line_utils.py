import os
import logging
from typing import List, Optional
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi
from linebot.v3.messaging.models import GroupMemberCountResponse, MembersIdsResponse
from linebot.v3.messaging.exceptions import OpenApiException
from supabase import create_client, Client

logger = logging.getLogger(__name__)

class LineUtils:
    def __init__(self):
        LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
        
        if not LINE_CHANNEL_ACCESS_TOKEN:
            raise ValueError("LINE_CHANNEL_ACCESS_TOKEN must be set")
        
        configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
        self.api_client = ApiClient(configuration)
        self.messaging_api = MessagingApi(self.api_client)
        
        # Supabaseクライアントの初期化
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_ANON_KEY")
        
        if not supabase_url or not supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_ANON_KEY must be set")
        
        self.supabase: Client = create_client(supabase_url, supabase_key)
    
    async def get_group_members_from_line(self, group_id: str) -> List[str]:
        """
        LINE APIからグループメンバーのユーザーIDリストを取得
        """
        try:
            response: MembersIdsResponse = self.messaging_api.get_group_member_user_ids(group_id)
            member_ids = response.member_ids
            
            logger.info(f"Retrieved {len(member_ids)} members from LINE API for group {group_id}")
            return member_ids
            
        except OpenApiException as e:
            logger.error(f"LINE API error when getting group members: {e}")
            return []
        except Exception as e:
            logger.error(f"Error getting group members from LINE: {e}")
            return []
    
    async def get_group_members_from_db(self, line_group_id: str) -> List[str]:
        """
        データベースからグループメンバーのLINE User IDリストを取得
        """
        try:
            # LINE Group IDからUUIDを取得
            group_result = self.supabase.table("groups").select("id").eq("line_group_id", line_group_id).execute()
            if not group_result.data:
                logger.info(f"Group not found in database: {line_group_id}")
                return []
            
            group_uuid = group_result.data[0]["id"]
            
            # グループメンバーのUUIDを取得してLINE User IDに変換
            result = self.supabase.table("group_members").select(
                "users(line_user_id)"
            ).eq("group_id", group_uuid).execute()
            
            if result.data:
                member_ids = [row["users"]["line_user_id"] for row in result.data if row["users"]]
                logger.info(f"Retrieved {len(member_ids)} members from database for group {line_group_id}")
                return member_ids
            else:
                logger.info(f"No members found in database for group {line_group_id}")
                return []
                
        except Exception as e:
            logger.error(f"Error getting group members from database: {e}")
            return []
    
    async def get_group_members(self, line_group_id: str, force_refresh: bool = False) -> List[str]:
        """
        グループメンバーのLINE User IDリストを取得
        デフォルトはデータベースから取得し、force_refreshがTrueの場合はLINE APIから取得
        """
        if force_refresh:
            # LINE APIから最新情報を取得
            members = await self.get_group_members_from_line(line_group_id)
            
            # データベースを更新
            if members:
                await self._sync_group_members_to_db(line_group_id, members)
            
            return members
        else:
            # データベースから取得
            members = await self.get_group_members_from_db(line_group_id)
            
            # データベースにメンバーがいない場合はLINE APIから取得
            if not members:
                members = await self.get_group_members_from_line(line_group_id)
                if members:
                    await self._sync_group_members_to_db(line_group_id, members)
            
            return members
    
    async def _sync_group_members_to_db(self, line_group_id: str, line_member_ids: List[str]) -> None:
        """
        グループメンバー情報をデータベースに同期
        """
        try:
            # Import database_service here to avoid circular imports
            from .database_service import database_service
            
            # LINE Group IDをUUIDに変換
            group_uuid = await database_service._ensure_group_exists(line_group_id)
            
            # 既存のメンバーを削除
            self.supabase.table("group_members").delete().eq("group_id", group_uuid).execute()
            
            # 新しいメンバーを追加
            if line_member_ids:
                members_data = []
                for line_user_id in line_member_ids:
                    # LINE User IDをUUIDに変換
                    user_uuid = await database_service._ensure_user_exists(line_user_id)
                    members_data.append({"user_id": user_uuid, "group_id": group_uuid})
                
                self.supabase.table("group_members").insert(members_data).execute()
                logger.info(f"Synced {len(line_member_ids)} members to database for group {line_group_id}")
                
        except Exception as e:
            logger.error(f"Error syncing group members to database: {e}")
    
    async def get_group_member_count(self, line_group_id: str) -> Optional[int]:
        """
        グループのメンバー数を取得
        """
        try:
            response: GroupMemberCountResponse = self.messaging_api.get_group_members_count(line_group_id)
            count = response.count
            
            logger.info(f"Group {line_group_id} has {count} members")
            return count
            
        except OpenApiException as e:
            logger.error(f"LINE API error when getting group member count: {e}")
            return None
        except Exception as e:
            logger.error(f"Error getting group member count: {e}")
            return None
    
    def is_group_chat_webhook(self, event_data: dict) -> bool:
        """
        受け取ったWebhookがGroup Chatのものかを判定する
        
        Args:
            event_data: LINE Webhookイベントデータ
            
        Returns:
            bool: Group ChatのWebhookの場合True、それ以外はFalse
        """
        source = event_data.get("source", {})
        source_type = source.get("type")
        group_id = source.get("groupId")
        
        # sourceのtypeが"group"かつgroupIdが存在する場合はグループチャット
        return source_type == "group" and group_id is not None


# シングルトンインスタンス
line_utils = LineUtils()