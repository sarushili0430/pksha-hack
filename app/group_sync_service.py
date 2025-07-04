import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set
from uuid import uuid4

from linebot.v3.messaging import AsyncApiClient, Configuration
from linebot.v3.messaging.models import GroupSummaryResponse, GroupMemberCountResponse
from linebot.v3.messaging.exceptions import OpenApiException
from supabase import Client

from app.line_user_profile_service import LineUserProfileService

logger = logging.getLogger(__name__)


class GroupSyncService:
    def __init__(self, line_channel_access_token: str, supabase: Client):
        self.line_client = AsyncApiClient(Configuration(access_token=line_channel_access_token))
        self.supabase = supabase
        self.profile_service = LineUserProfileService(line_channel_access_token, supabase)

    async def sync_group_members(self, line_group_id: str) -> Dict:
        """
        指定されたLINEグループのメンバーを同期し、データベースを更新する
        """
        try:
            # グループの存在確認・作成
            group_id = await self._get_or_create_group(line_group_id)
            
            # LINEからグループメンバーを取得
            line_member_ids = await self._get_line_group_members(line_group_id)
            
            # データベースから現在のメンバーを取得
            current_member_ids = await self._get_current_group_members(group_id)
            
            # 差分を計算
            new_members = set(line_member_ids) - set(current_member_ids)
            removed_members = set(current_member_ids) - set(line_member_ids)
            
            # 新しいメンバーを追加
            added_count = await self._add_new_members(group_id, new_members)
            
            # 削除されたメンバーを除去
            removed_count = await self._remove_old_members(group_id, removed_members)
            
            # グループ情報を更新
            await self._update_group_info(line_group_id, group_id)
            
            return {
                "success": True,
                "group_id": group_id,
                "line_group_id": line_group_id,
                "members_added": added_count,
                "members_removed": removed_count,
                "total_members": len(line_member_ids)
            }
            
        except Exception as e:
            logger.error(f"グループメンバー同期エラー: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    async def _get_line_group_members(self, line_group_id: str) -> List[str]:
        """LINEグループのメンバーIDリストを取得"""
        try:
            # グループメンバーのIDを取得
            response = await self.line_client.get_group_members_ids(line_group_id)  # type: ignore[attr-defined]
            return response.member_ids
        except OpenApiException as e:
            logger.error(f"LINEグループメンバー取得エラー: {e}")
            raise

    async def _get_or_create_group(self, line_group_id: str) -> str:
        """グループを取得または作成"""
        result = self.supabase.table("groups").select("id").eq("line_group_id", line_group_id).execute()
        
        if result.data:
            return result.data[0]["id"]
        
        # 新しいグループを作成
        group_data = {
            "line_group_id": line_group_id,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        inserted = self.supabase.table("groups").insert(group_data).execute()
        return inserted.data[0]["id"]

    async def _get_current_group_members(self, group_id: str) -> List[str]:
        """データベースから現在のグループメンバーのLINE IDを取得"""
        result = self.supabase.table("group_members").select(
            "users(line_user_id)"
        ).eq("group_id", group_id).execute()
        
        return [row["users"]["line_user_id"] for row in result.data if row.get("users")]

    async def _add_new_members(self, group_id: str, new_member_ids: Set[str]) -> int:
        """新しいメンバーをグループに追加"""
        if not new_member_ids:
            return 0
        
        # ユーザープロファイルを並行して取得・作成
        user_tasks = [self.profile_service.get_or_create_user(user_id) for user_id in new_member_ids]
        user_results = await asyncio.gather(*user_tasks, return_exceptions=True)
        
        # 正常に取得できたユーザーのみ処理
        valid_users = []
        for user_id, result in zip(new_member_ids, user_results):
            if isinstance(result, Exception):
                logger.warning(f"ユーザー {user_id} の取得に失敗: {result}")
                continue
            valid_users.append(result)
        
        # グループメンバーを一括挿入
        if valid_users:
            member_data = [
                {
                    "group_id": group_id,
                    "user_id": user["id"],
                    "joined_at": datetime.now(timezone.utc).isoformat()
                }
                for user in valid_users
            ]
            self.supabase.table("group_members").insert(member_data).execute()
        
        return len(valid_users)

    async def _remove_old_members(self, group_id: str, removed_member_ids: Set[str]) -> int:
        """削除されたメンバーをグループから除去"""
        if not removed_member_ids:
            return 0
        
        # ユーザーIDを取得
        user_result = self.supabase.table("users").select("id").in_(
            "line_user_id", list(removed_member_ids)
        ).execute()
        
        user_ids = [user["id"] for user in user_result.data]
        
        # グループメンバーから削除
        if user_ids:
            self.supabase.table("group_members").delete().eq("group_id", group_id).in_(
                "user_id", user_ids
            ).execute()
        
        return len(user_ids)

    async def _update_group_info(self, line_group_id: str, group_id: str):
        """グループ情報を更新（グループ名など）"""
        try:
            # グループサマリーを取得
            group_summary = await self.line_client.get_group_summary(line_group_id)  # type: ignore[attr-defined]
            
            # データベースを更新
            update_data = {}
            if hasattr(group_summary, 'group_name') and group_summary.group_name:
                update_data["group_name"] = group_summary.group_name
            
            if update_data:
                self.supabase.table("groups").update(update_data).eq("id", group_id).execute()
                
        except OpenApiException as e:
            logger.warning(f"グループ情報取得エラー: {e}")

    async def get_group_member_count(self, line_group_id: str) -> Optional[int]:
        """グループメンバー数を取得"""
        try:
            response = await self.line_client.get_group_member_count(line_group_id)  # type: ignore[attr-defined]
            return response.count
        except OpenApiException as e:
            logger.error(f"グループメンバー数取得エラー: {e}")
            return None

    async def sync_all_groups(self) -> Dict:
        """すべてのグループのメンバーを同期"""
        result = self.supabase.table("groups").select("line_group_id, id").execute()
        
        sync_tasks = []
        for group in result.data:
            task = self.sync_group_members(group["line_group_id"])
            sync_tasks.append(task)
        
        # 並行実行
        results = await asyncio.gather(*sync_tasks, return_exceptions=True)
        
        # 結果を集計
        successful = 0
        failed = 0
        total_added = 0
        total_removed = 0
        
        for result in results:
            if isinstance(result, Exception):
                failed += 1
                logger.error(f"グループ同期エラー: {result}")
            elif result.get("success"):
                successful += 1
                total_added += result.get("members_added", 0)
                total_removed += result.get("members_removed", 0)
            else:
                failed += 1
        
        return {
            "total_groups": len(result.data),
            "successful": successful,
            "failed": failed,
            "total_members_added": total_added,
            "total_members_removed": total_removed
        }

    async def get_group_members_info(self, line_group_id: str) -> Dict:
        """グループメンバーの詳細情報を取得"""
        try:
            group_result = self.supabase.table("groups").select("id").eq(
                "line_group_id", line_group_id
            ).execute()
            
            if not group_result.data:
                return {"error": "グループが見つかりません"}
            
            group_id = group_result.data[0]["id"]
            
            # グループメンバーと詳細情報を取得
            members_result = self.supabase.table("group_members").select(
                "joined_at, last_active_at, users(id, line_user_id, display_name, picture_url)"
            ).eq("group_id", group_id).execute()
            
            members = []
            for row in members_result.data:
                user = row.get("users")
                if user:
                    members.append({
                        "line_user_id": user["line_user_id"],
                        "display_name": user.get("display_name"),
                        "picture_url": user.get("picture_url"),
                        "joined_at": row.get("joined_at"),
                        "last_active_at": row.get("last_active_at")
                    })
            
            return {
                "group_id": group_id,
                "line_group_id": line_group_id,
                "member_count": len(members),
                "members": members
            }
            
        except Exception as e:
            logger.error(f"グループメンバー情報取得エラー: {e}")
            return {"error": str(e)}