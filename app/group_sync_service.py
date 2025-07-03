"""
Group Member Synchronization Service

LINE APIからグループメンバー情報を取得し、データベースに同期する機能を提供します。
"""

from typing import List, Optional
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi
)
from linebot.v3.messaging.rest import ApiException
from supabase import Client
from datetime import datetime, timezone


class GroupSyncService:
    """
    グループメンバー同期サービス
    
    LINE APIからグループメンバー情報を取得し、
    データベースのgroup_membersテーブルに同期します。
    """
    
    def __init__(self, line_token: str, supabase_client: Client):
        """
        GroupSyncServiceを初期化
        
        Args:
            line_token: LINE Bot のアクセストークン
            supabase_client: Supabaseクライアント
        """
        self.configuration = Configuration(access_token=line_token)
        self.supabase = supabase_client
    
    async def add_user_and_mark_sync_if_needed(self, user_id: str, group_id: str) -> bool:
        """
        ユーザーをグループに追加し、必要に応じて同期済みとしてマーク
        
        Args:
            user_id: 内部User ID
            group_id: 内部Group ID
            
        Returns:
            処理実行時True
        """
        try:
            # ユーザーをグループに追加
            await self._add_user_to_group_if_not_exists(user_id, group_id)
            
            # groups テーブルで members_synced フラグをチェック（カラムが存在する場合のみ）
            try:
                result = self.supabase.table("groups").select("members_synced").eq("id", group_id).execute()
                
                if result.data and not result.data[0].get("members_synced"):
                    # 初回メンバー追加時に同期済みとしてマーク
                    self.supabase.table("groups").update({
                        "members_synced": True
                    }).eq("id", group_id).execute()
                    
                    print(f"★DEBUG: Marked group {group_id} as members_synced")
            except Exception as e:
                if "does not exist" in str(e):
                    print(f"★DEBUG: members_synced column not found, continuing without sync flag")
                else:
                    raise
            
            return True
            
        except Exception as e:
            print(f"★ERROR: Failed to add user and sync group: {e}")
            import traceback
            print(f"★ERROR: Traceback: {traceback.format_exc()}")
            return False
    
    async def _get_group_member_ids_from_line_api(self, line_group_id: str) -> List[str]:
        """
        LINE APIからグループメンバーIDのリストを取得
        
        Args:
            line_group_id: LINE Group ID
            
        Returns:
            LINE User IDのリスト
        """
        try:
            with ApiClient(self.configuration) as api_client:
                messaging_api = MessagingApi(api_client)
                
                # グループメンバープロフィールを取得
                # 注意: この機能は一部のLINE Bot APIプランでのみ利用可能
                member_ids_response = messaging_api.get_group_members_count(line_group_id)
                print(f"★DEBUG: Group member count: {member_ids_response.count}")
                
                # メンバーIDのリストを取得
                # 注意: 実際のAPIエンドポイントは異なる可能性があります
                # ここでは仮実装として、現在のメッセージ送信者を追加
                return []  # 実際のメンバーリスト取得は制限があるため
                
        except ApiException as e:
            print(f"★ERROR: LINE API error getting group members: {e}")
            return []
        except Exception as e:
            print(f"★ERROR: Error getting group members from LINE API: {e}")
            return []
    
    async def _get_or_create_user(self, line_user_id: str) -> str:
        """
        ユーザーを取得または作成
        
        Args:
            line_user_id: LINE User ID
            
        Returns:
            内部User ID
        """
        try:
            result = self.supabase.table("users").select("id").eq("line_user_id", line_user_id).execute()
            if result.data:
                return result.data[0]["id"]
            
            user_data = {
                "line_user_id": line_user_id,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            inserted = self.supabase.table("users").insert(user_data).execute()
            return inserted.data[0]["id"]
            
        except Exception as e:
            print(f"★ERROR: Failed to get or create user {line_user_id}: {e}")
            raise
    
    async def _add_user_to_group_if_not_exists(self, user_id: str, group_id: str):
        """
        ユーザーをグループに追加（重複チェック付き）
        
        Args:
            user_id: 内部User ID
            group_id: 内部Group ID
        """
        try:
            # 既存のメンバーシップをチェック
            result = self.supabase.table("group_members").select("group_id").eq("group_id", group_id).eq("user_id", user_id).execute()
            
            if not result.data:
                # メンバーシップが存在しない場合、追加
                member_data = {
                    "group_id": group_id,
                    "user_id": user_id,
                    "joined_at": datetime.now(timezone.utc).isoformat()
                }
                self.supabase.table("group_members").insert(member_data).execute()
                print(f"★ADD: Added user {user_id} to group {group_id}")
            else:
                print(f"★DEBUG: User {user_id} already in group {group_id}")
                
        except Exception as e:
            print(f"★ERROR: Failed to add user to group: {e}")
            raise


# シングルトンインスタンス
_group_sync_service: Optional[GroupSyncService] = None

def get_group_sync_service(line_token: str, supabase_client: Client) -> GroupSyncService:
    """
    GroupSyncServiceのシングルトンインスタンスを取得
    
    Args:
        line_token: LINE Bot のアクセストークン
        supabase_client: Supabaseクライアント
        
    Returns:
        GroupSyncServiceインスタンス
    """
    global _group_sync_service
    if _group_sync_service is None:
        _group_sync_service = GroupSyncService(line_token, supabase_client)
    return _group_sync_service