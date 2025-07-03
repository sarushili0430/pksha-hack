import os
import logging
from typing import List, Optional
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi
from linebot.v3.messaging.models import TextMessage, PushMessageRequest
from linebot.v3.messaging.exceptions import OpenApiException
from supabase import create_client, Client
from .line_utils import line_utils

logger = logging.getLogger(__name__)

class MessageService:
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

    async def send_message_to_user(self, user_id: str, message: str) -> bool:
        """
        個人ユーザーにメッセージを送信
        
        Args:
            user_id: 送信先のLINE User ID
            message: 送信するメッセージテキスト
            
        Returns:
            bool: 送信成功の場合True、失敗の場合False
        """
        try:
            text_message = TextMessage(text=message)
            push_request = PushMessageRequest(to=user_id, messages=[text_message])
            
            self.messaging_api.push_message(push_request)
            logger.info(f"Message sent successfully to user {user_id}")
            return True
            
        except OpenApiException as e:
            logger.error(f"LINE API error when sending message to user {user_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error sending message to user {user_id}: {e}")
            return False

    async def send_message_to_group(self, group_id: str, message: str) -> bool:
        """
        グループにメッセージを送信
        
        Args:
            group_id: 送信先のLINE Group ID
            message: 送信するメッセージテキスト
            
        Returns:
            bool: 送信成功の場合True、失敗の場合False
        """
        try:
            text_message = TextMessage(text=message)
            push_request = PushMessageRequest(to=group_id, messages=[text_message])
            
            self.messaging_api.push_message(push_request)
            logger.info(f"Message sent successfully to group {group_id}")
            return True
            
        except OpenApiException as e:
            logger.error(f"LINE API error when sending message to group {group_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error sending message to group {group_id}: {e}")
            return False

    async def send_message_to_user_by_internal_id(self, internal_user_id: str, message: str) -> bool:
        """
        内部ユーザーID（データベースのID）を使用してユーザーにメッセージを送信
        
        Args:
            internal_user_id: データベースのuser_id
            message: 送信するメッセージテキスト
            
        Returns:
            bool: 送信成功の場合True、失敗の場合False
        """
        try:
            # データベースからLINE User IDを取得
            result = self.supabase.table("users").select("line_user_id").eq("id", internal_user_id).execute()
            
            if not result.data:
                logger.warning(f"User not found in database: {internal_user_id}")
                return False
            
            line_user_id = result.data[0]["line_user_id"]
            return await self.send_message_to_user(line_user_id, message)
            
        except Exception as e:
            logger.error(f"Error sending message to user by internal ID {internal_user_id}: {e}")
            return False

    async def send_message_to_group_by_internal_id(self, internal_group_id: str, message: str) -> bool:
        """
        内部グループID（データベースのID）を使用してグループにメッセージを送信
        
        Args:
            internal_group_id: データベースのgroup_id
            message: 送信するメッセージテキスト
            
        Returns:
            bool: 送信成功の場合True、失敗の場合False
        """
        try:
            # データベースからLINE Group IDを取得
            result = self.supabase.table("groups").select("line_group_id").eq("id", internal_group_id).execute()
            
            if not result.data:
                logger.warning(f"Group not found in database: {internal_group_id}")
                return False
            
            line_group_id = result.data[0]["line_group_id"]
            return await self.send_message_to_group(line_group_id, message)
            
        except Exception as e:
            logger.error(f"Error sending message to group by internal ID {internal_group_id}: {e}")
            return False

    async def send_messages_to_multiple_users(self, user_ids: List[str], message: str) -> List[bool]:
        """
        複数のユーザーにメッセージを送信
        
        Args:
            user_ids: 送信先のLINE User IDリスト
            message: 送信するメッセージテキスト
            
        Returns:
            List[bool]: 各ユーザーへの送信結果のリスト
        """
        results = []
        for user_id in user_ids:
            result = await self.send_message_to_user(user_id, message)
            results.append(result)
        
        successful_sends = sum(results)
        logger.info(f"Sent message to {successful_sends}/{len(user_ids)} users")
        return results

    async def send_message_to_group_members(self, line_group_id: str, message: str, exclude_user_ids: Optional[List[str]] = None) -> List[bool]:
        """
        グループメンバー全員に個別メッセージを送信
        
        Args:
            line_group_id: 対象のLINE Group ID
            message: 送信するメッセージテキスト
            exclude_user_ids: 除外するユーザーIDのリスト（オプション）
            
        Returns:
            List[bool]: 各メンバーへの送信結果のリスト
        """
        try:
            # グループメンバーを取得
            member_ids = await line_utils.get_group_members(line_group_id)
            
            if not member_ids:
                logger.warning(f"No members found for group {line_group_id}")
                return []
            
            # 除外するユーザーIDがある場合はフィルタリング
            if exclude_user_ids:
                member_ids = [user_id for user_id in member_ids if user_id not in exclude_user_ids]
            
            # 全メンバーにメッセージを送信
            return await self.send_messages_to_multiple_users(member_ids, message)
            
        except Exception as e:
            logger.error(f"Error sending message to group members {line_group_id}: {e}")
            return []

# シングルトンインスタンス
message_service = MessageService()