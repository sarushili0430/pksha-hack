"""
プッシュメッセージ送信サービス

LINE Bot SDK v3を使用して、特定のユーザーやグループに
プッシュメッセージを送信する機能を提供します。
"""

import os
from typing import Optional, List
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    PushMessageRequest,
    TextMessage,
    TextMessageV2,
    MentionSubstitutionObject,
    UserMentionTarget,
    FlexMessage,
    FlexContainer
)
from linebot.v3.messaging.rest import ApiException
from supabase import Client


class PushService:
    """
    プッシュメッセージ送信サービス
    
    LINE Bot SDK v3を使用してプッシュメッセージを送信し、
    データベースからuser_idの変換も行います。
    """
    
    def __init__(self, line_token: str, supabase_client: Client):
        """
        PushServiceを初期化
        
        Args:
            line_token: LINE Bot のアクセストークン
            supabase_client: Supabaseクライアント
        """
        self.configuration = Configuration(access_token=line_token)
        self.supabase = supabase_client
    
    async def send_to_user(self, user_id: str, message: str) -> bool:
        """
        特定のユーザーにテキストメッセージを送信
        
        Args:
            user_id: 送信先のユーザーID（内部ID）
            message: 送信するテキストメッセージ
            
        Returns:
            送信成功時True、失敗時False
        """
        try:
            # 内部user_idからLINE user_idを取得
            line_user_id = await self._get_line_user_id(user_id)
            if not line_user_id:
                print(f"User not found: {user_id}")
                return False
            
            return await self._send_push_message(line_user_id, message)
            
        except Exception as e:
            print(f"Error sending message to user {user_id}: {e}")
            return False
    
    async def send_to_line_user(self, line_user_id: str, message: str) -> bool:
        """
        LINE User IDに直接テキストメッセージを送信
        
        Args:
            line_user_id: 送信先のLINE User ID
            message: 送信するテキストメッセージ
            
        Returns:
            送信成功時True、失敗時False
        """
        try:
            return await self._send_push_message(line_user_id, message)
            
        except Exception as e:
            print(f"Error sending message to LINE user {line_user_id}: {e}")
            return False
    
    async def send_to_group(self, group_id: str, message: str) -> bool:
        """
        特定のグループにテキストメッセージを送信
        
        Args:
            group_id: 送信先のグループID（内部ID）
            message: 送信するテキストメッセージ
            
        Returns:
            送信成功時True、失敗時False
        """
        try:
            # 内部group_idからLINE group_idを取得
            line_group_id = await self._get_line_group_id(group_id)
            if not line_group_id:
                print(f"Group not found: {group_id}")
                return False
            
            return await self._send_push_message(line_group_id, message)
            
        except Exception as e:
            print(f"Error sending message to group {group_id}: {e}")
            return False
    
    async def send_to_line_group(self, line_group_id: str, message: str) -> bool:
        """
        LINE Group IDに直接テキストメッセージを送信
        
        Args:
            line_group_id: 送信先のLINE Group ID
            message: 送信するテキストメッセージ
            
        Returns:
            送信成功時True、失敗時False
        """
        try:
            return await self._send_push_message(line_group_id, message)
            
        except Exception as e:
            print(f"Error sending message to LINE group {line_group_id}: {e}")
            return False
    
    async def send_to_line_group_with_mentions(self, line_group_id: str, message: str, mention_targets: List[UserMentionTarget]) -> bool:
        """
        LINE Group IDに直接メンション付きテキストメッセージを送信
        
        Args:
            line_group_id: 送信先のLINE Group ID
            message: 送信するテキストメッセージ（{member0}, {member1}, ..., {member5}のような置換キーを含む）
            mention_targets: メンション対象のリスト（最大6名）
            
        Returns:
            送信成功時True、失敗時False
        """
        try:
            return await self._send_push_message_with_mentions(line_group_id, message, mention_targets)
            
        except Exception as e:
            print(f"Error sending mention message to LINE group {line_group_id}: {e}")
            return False
    
    async def send_flex_message(self, target_id: str, alt_text: str, flex_content: FlexContainer) -> bool:
        """
        Flexメッセージを送信
        
        Args:
            target_id: 送信先のID（LINE User ID または LINE Group ID）
            alt_text: Flexメッセージの代替テキスト
            flex_content: Flexメッセージの内容
            
        Returns:
            送信成功時True、失敗時False
        """
        try:
            with ApiClient(self.configuration) as api_client:
                messaging_api = MessagingApi(api_client)
                
                flex_message = FlexMessage(alt_text=alt_text, contents=flex_content)
                push_request = PushMessageRequest(
                    to=target_id,
                    messages=[flex_message]
                )
                
                messaging_api.push_message(push_request)
                print(f"Flex message sent successfully to {target_id}")
                return True
                
        except ApiException as e:
            print(f"LINE API error sending flex message: {e}")
            return False
        except Exception as e:
            print(f"Error sending flex message: {e}")
            return False
    
    async def send_multiple_messages(self, target_id: str, messages: List[str]) -> bool:
        """
        複数のテキストメッセージを一度に送信
        
        Args:
            target_id: 送信先のID（LINE User ID または LINE Group ID）
            messages: 送信するメッセージのリスト（最大5件）
            
        Returns:
            送信成功時True、失敗時False
        """
        try:
            if len(messages) > 5:
                print("Warning: LINE API allows maximum 5 messages per request")
                messages = messages[:5]
            
            with ApiClient(self.configuration) as api_client:
                messaging_api = MessagingApi(api_client)
                
                text_messages = [TextMessage(text=msg) for msg in messages]
                push_request = PushMessageRequest(
                    to=target_id,
                    messages=text_messages
                )
                
                messaging_api.push_message(push_request)
                print(f"Multiple messages sent successfully to {target_id}")
                return True
                
        except ApiException as e:
            print(f"LINE API error sending multiple messages: {e}")
            return False
        except Exception as e:
            print(f"Error sending multiple messages: {e}")
            return False
    
    async def _send_push_message(self, target_id: str, message: str) -> bool:
        """
        プッシュメッセージ送信の内部実装
        
        Args:
            target_id: 送信先のID（LINE User ID または LINE Group ID）
            message: 送信するテキストメッセージ
            
        Returns:
            送信成功時True、失敗時False
        """
        try:
            with ApiClient(self.configuration) as api_client:
                messaging_api = MessagingApi(api_client)
                
                text_message = TextMessage(text=message)
                push_request = PushMessageRequest(
                    to=target_id,
                    messages=[text_message]
                )
                
                messaging_api.push_message(push_request)
                print(f"Push message sent successfully to {target_id}")
                return True
                
        except ApiException as e:
            print(f"LINE API error: {e}")
            return False
        except Exception as e:
            print(f"Error sending push message: {e}")
            return False
    
    async def _send_push_message_with_mentions(self, target_id: str, message: str, mention_targets: List[UserMentionTarget]) -> bool:
        """
        メンション付きプッシュメッセージ送信の内部実装
        
        Args:
            target_id: 送信先のID（LINE User ID または LINE Group ID）
            message: 送信するテキストメッセージ（{member0}, {member1}, ..., {member5}のような置換キーを含む）
            mention_targets: メンション対象のリスト（最大6名）
            
        Returns:
            送信成功時True、失敗時False
        """
        try:
            with ApiClient(self.configuration) as api_client:
                messaging_api = MessagingApi(api_client)
                
                # メンション置換オブジェクトを作成
                substitution_objects = []
                for i, target in enumerate(mention_targets):
                    # デバッグ用：メンション対象の情報をログ出力
                    print(f"DEBUG: Creating substitution - key: member{i}, user_id: {target.user_id}")
                    if not target.user_id or not target.user_id.startswith('U'):
                        print(f"ERROR: Invalid LINE user ID: {target.user_id}")
                    
                    substitution_objects.append(
                        MentionSubstitutionObject(
                            key=f"member{i}",
                            target=target
                        )
                    )
                
                # TextMessageV2を使用してメンション付きメッセージを作成
                text_message_v2 = TextMessageV2(
                    text=message,
                    substitution_objects=substitution_objects
                )
                
                push_request = PushMessageRequest(
                    to=target_id,
                    messages=[text_message_v2]
                )
                
                messaging_api.push_message(push_request)
                print(f"Push message with mentions sent successfully to {target_id}")
                return True
                
        except ApiException as e:
            print(f"LINE API error sending mention message: {e}")
            print("Falling back to regular message without mentions")
            return await self._send_push_message(target_id, message)
        except Exception as e:
            print(f"Error sending mention push message: {e}")
            print("Falling back to regular message without mentions")
            return await self._send_push_message(target_id, message)
    
    async def _get_line_user_id(self, user_id: str) -> Optional[str]:
        """
        内部user_idからLINE user_idを取得
        
        Args:
            user_id: 内部ユーザーID
            
        Returns:
            LINE User ID、見つからない場合None
        """
        try:
            result = self.supabase.table("users").select("line_user_id").eq("id", user_id).execute()
            if result.data:
                return result.data[0]["line_user_id"]
            return None
            
        except Exception as e:
            print(f"Error getting LINE user ID: {e}")
            return None
    
    async def _get_line_group_id(self, group_id: str) -> Optional[str]:
        """
        内部group_idからLINE group_idを取得
        
        Args:
            group_id: 内部グループID
            
        Returns:
            LINE Group ID、見つからない場合None
        """
        try:
            result = self.supabase.table("groups").select("line_group_id").eq("id", group_id).execute()
            if result.data:
                return result.data[0]["line_group_id"]
            return None
            
        except Exception as e:
            print(f"Error getting LINE group ID: {e}")
            return None


# シングルトンインスタンス（main.pyで使用）
_push_service: Optional[PushService] = None

def get_push_service(line_token: str, supabase_client: Client) -> PushService:
    """
    PushServiceのシングルトンインスタンスを取得
    
    Args:
        line_token: LINE Bot のアクセストークン
        supabase_client: Supabaseクライアント
        
    Returns:
        PushServiceインスタンス
    """
    global _push_service
    if _push_service is None:
        _push_service = PushService(line_token, supabase_client)
    return _push_service