"""
LINE User Profile Service
LINEユーザープロフィール情報を取得するサービス
"""
import asyncio
from typing import Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor

from linebot.v3.messaging import Configuration, ApiClient, MessagingApi
from linebot.v3.messaging.rest import ApiException
from supabase import Client


class LineUserProfileService:
    """LINE User Profile Service"""
    
    def __init__(self, line_access_token: str, supabase_client: Client):
        """
        Args:
            line_access_token: LINE チャンネルアクセストークン
            supabase_client: Supabase クライアント
        """
        self.line_access_token = line_access_token
        self.supabase_client = supabase_client
        self.executor = ThreadPoolExecutor(max_workers=5)
        
        # LINE API クライアントを初期化
        self.line_config = Configuration(access_token=line_access_token)
    
    async def get_user_profile(self, line_user_id: str) -> Optional[Dict[str, Any]]:
        """
        LINE ユーザーのプロフィール情報を取得
        
        Args:
            line_user_id: LINE ユーザーID (例: U1234567890abcdef)
            
        Returns:
            ユーザープロフィール情報の辞書、または None（エラー時）
            {
                "user_id": "U1234567890abcdef",
                "display_name": "表示名",
                "picture_url": "プロフィール画像URL",
                "status_message": "ステータスメッセージ",
                "language": "言語コード"
            }
        """
        try:
            # LINE API を非同期で呼び出し
            loop = asyncio.get_event_loop()
            profile = await loop.run_in_executor(
                self.executor,
                self._get_user_profile_sync,
                line_user_id
            )
            
            if profile:
                # プロフィール情報を辞書形式で返す
                return {
                    "user_id": profile.user_id,
                    "display_name": profile.display_name,
                    "picture_url": getattr(profile, 'picture_url', None),
                    "status_message": getattr(profile, 'status_message', None),
                    "language": getattr(profile, 'language', None)
                }
            
            return None
            
        except Exception as e:
            print(f"Error getting user profile for {line_user_id}: {e}")
            return None
    
    def _get_user_profile_sync(self, line_user_id: str):
        """
        同期的にLINE APIからユーザープロフィールを取得
        """
        try:
            with ApiClient(self.line_config) as api_client:
                line_bot_api = MessagingApi(api_client)
                return line_bot_api.get_profile(line_user_id)
        except ApiException as e:
            print(f"LINE API error: {e}")
            return None
        except Exception as e:
            print(f"Unexpected error: {e}")
            return None
    
    async def save_user_profile_to_db(self, line_user_id: str, profile_data: Dict[str, Any]) -> bool:
        """
        ユーザープロフィール情報をデータベースに保存
        
        Args:
            line_user_id: LINE ユーザーID
            profile_data: プロフィール情報
            
        Returns:
            保存成功: True, 失敗: False
        """
        try:
            # 既存のユーザーを検索
            existing_user = self.supabase_client.table("users").select("*").eq("line_user_id", line_user_id).execute()
            
            if existing_user.data:
                # 既存ユーザーの情報を更新（基本的なカラムのみ）
                updated_data = {
                    "display_name": profile_data.get("display_name"),
                    "last_profile_sync": "now()"
                }
                
                # 追加のカラムがある場合のみ更新
                try:
                    # テーブルスキーマをチェックして、カラムが存在するかどうかを確認
                    if profile_data.get("picture_url"):
                        updated_data["picture_url"] = profile_data.get("picture_url")
                    if profile_data.get("status_message"):
                        updated_data["status_message"] = profile_data.get("status_message")
                    if profile_data.get("language"):
                        updated_data["language"] = profile_data.get("language")
                        
                    self.supabase_client.table("users").update(updated_data).eq("line_user_id", line_user_id).execute()
                    print(f"Updated user profile for {line_user_id}")
                except Exception as schema_error:
                    # スキーマエラーの場合は基本的な情報のみ更新
                    print(f"Schema error, updating basic info only: {schema_error}")
                    basic_data = {
                        "display_name": profile_data.get("display_name"),
                        "last_profile_sync": "now()"
                    }
                    self.supabase_client.table("users").update(basic_data).eq("line_user_id", line_user_id).execute()
                    print(f"Updated basic user profile for {line_user_id}")
            else:
                # 新規ユーザーを作成（基本的なカラムのみ）
                new_user_data = {
                    "line_user_id": line_user_id,
                    "display_name": profile_data.get("display_name"),
                    "last_profile_sync": "now()"
                }
                
                # 追加のカラムがある場合のみ追加
                try:
                    if profile_data.get("picture_url"):
                        new_user_data["picture_url"] = profile_data.get("picture_url")
                    if profile_data.get("status_message"):
                        new_user_data["status_message"] = profile_data.get("status_message")
                    if profile_data.get("language"):
                        new_user_data["language"] = profile_data.get("language")
                        
                    self.supabase_client.table("users").insert(new_user_data).execute()
                    print(f"Created new user profile for {line_user_id}")
                except Exception as schema_error:
                    # スキーマエラーの場合は基本的な情報のみ作成
                    print(f"Schema error, creating basic info only: {schema_error}")
                    basic_data = {
                        "line_user_id": line_user_id,
                        "display_name": profile_data.get("display_name"),
                        "last_profile_sync": "now()"
                    }
                    self.supabase_client.table("users").insert(basic_data).execute()
                    print(f"Created basic user profile for {line_user_id}")
            
            return True
            
        except Exception as e:
            print(f"Error saving user profile to database: {e}")
            return False
    
    async def get_user_profile_from_db(self, line_user_id: str) -> Optional[Dict[str, Any]]:
        """
        データベースからユーザープロフィール情報を取得
        
        Args:
            line_user_id: LINE ユーザーID
            
        Returns:
            データベースに保存されているユーザー情報、または None
        """
        try:
            result = self.supabase_client.table("users").select("*").eq("line_user_id", line_user_id).execute()
            
            if result.data:
                return result.data[0]
            
            return None
            
        except Exception as e:
            print(f"Error getting user profile from database: {e}")
            return None
    
    async def get_user_profile_with_cache(self, line_user_id: str, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """
        キャッシュを使用してユーザープロフィール情報を取得
        
        Args:
            line_user_id: LINE ユーザーID
            force_refresh: True の場合、キャッシュを無視してLINE APIから取得
            
        Returns:
            ユーザープロフィール情報
        """
        try:
            # キャッシュから取得を試行（force_refresh が False の場合）
            if not force_refresh:
                cached_profile = await self.get_user_profile_from_db(line_user_id)
                if cached_profile and cached_profile.get("display_name"):
                    return cached_profile
            
            # LINE API から最新情報を取得
            fresh_profile = await self.get_user_profile(line_user_id)
            
            if fresh_profile:
                # データベースに保存
                await self.save_user_profile_to_db(line_user_id, fresh_profile)
                
                # データベースから完全な情報を取得して返す
                return await self.get_user_profile_from_db(line_user_id)
            
            # LINE API から取得できない場合は、キャッシュから返す
            return await self.get_user_profile_from_db(line_user_id)
            
        except Exception as e:
            print(f"Error in get_user_profile_with_cache: {e}")
            return None


# シングルトンインスタンスを作成するためのファクトリー関数
_line_user_profile_service_instance = None

def get_line_user_profile_service(line_access_token: str, supabase_client: Client) -> LineUserProfileService:
    """
    LineUserProfileService のシングルトンインスタンスを取得
    """
    global _line_user_profile_service_instance
    if _line_user_profile_service_instance is None:
        _line_user_profile_service_instance = LineUserProfileService(line_access_token, supabase_client)
    return _line_user_profile_service_instance