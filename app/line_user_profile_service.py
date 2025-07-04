"""LINEユーザープロフィールを取得・キャッシュするサービス

このファイルでは、LINE Messaging API からユーザーのプロフィール
（表示名・アイコン等）を取得し、Supabase の users テーブルへ保存する
ユーティリティを提供する。

主な用途:
1. DB に display_name が未登録の場合に API から取得して補完
2. GroupSyncService などが新規メンバーを登録する際の get_or_create_user
3. その他サービスがユーザー名を必要とするときの簡易キャッシュ取得

※AsyncApiClient を用いた非同期実装としている。
    """

import os
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from linebot.v3.messaging import AsyncApiClient, Configuration
from linebot.v3.messaging.exceptions import OpenApiException
from supabase import create_client, Client

logger = logging.getLogger(__name__)


class LineUserProfileService:
    """LINE プロフィール取得 & キャッシュサービス"""

    def __init__(self, line_channel_access_token: str, supabase: Client):
        self.line_client = AsyncApiClient(Configuration(access_token=line_channel_access_token))
        self.supabase = supabase

    async def _fetch_profile_from_line(self, line_user_id: str) -> Optional[Dict[str, Any]]:
        """LINE API からプロフィールを取得

        Args:
            line_user_id: LINE のユーザー ID
        Returns:
            dict | None: 取得したプロフィール情報（取得失敗時は None）
        """
        try:
            profile = await self.line_client.get_profile(line_user_id)
            return {
                "line_user_id": line_user_id,
                "display_name": getattr(profile, "display_name", None),
                "picture_url": getattr(profile, "picture_url", None),
                "status_message": getattr(profile, "status_message", None),
                # 言語フィールドは v3 SDK には無いが、将来拡張を考慮
            }
        except OpenApiException as e:
            logger.warning(f"LINE profile fetch failed for {line_user_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching LINE profile: {e}")
            return None

    async def save_user_profile_to_db(self, line_user_id: str, profile_data: Dict[str, Any]) -> bool:
        """取得したプロフィールを Supabase に保存

        Args:
            line_user_id: LINE のユーザー ID
            profile_data: _fetch_profile_from_line で取得した dict
        Returns:
            bool: 保存成功
        """
        try:
            # users テーブルの該当行を取得（存在保証はしない）
            user_res = self.supabase.table("users").select("id").eq("line_user_id", line_user_id).execute()
            if not user_res.data:
                logger.warning(f"User {line_user_id} not found when saving profile")
                return False
            user_id = user_res.data[0]["id"]

            update_fields = {k: v for k, v in profile_data.items() if k != "line_user_id" and v}
            if not update_fields:
                return False

            self.supabase.table("users").update(update_fields).eq("id", user_id).execute()
            logger.info(f"Saved profile for {line_user_id}: {update_fields}")
            return True
        except Exception as e:
            logger.error(f"Error saving profile to DB for {line_user_id}: {e}")
            return False

    async def get_user_profile_with_cache(self, line_user_id: str, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """DB から表示名を取得し、無い場合は LINE API から補完して返す

        Args:
            line_user_id: LINE のユーザー ID
            force_refresh: True の場合は常に API を叩いて更新
        Returns:
            dict | None: プロフィール情報
        """
        try:
            # まず DB を確認
            user_res = self.supabase.table("users").select("id, display_name, picture_url, status_message").eq("line_user_id", line_user_id).execute()
            row = user_res.data[0] if user_res.data else None

            if row and row.get("display_name") and not force_refresh:
                return row

            # API から取得
            profile = await self._fetch_profile_from_line(line_user_id)
            if profile and profile.get("display_name"):
                await self.save_user_profile_to_db(line_user_id, profile)
                if row:
                    row.update(profile)
                else:
                    row = profile
            return row
        except Exception as e:
            logger.error(f"Error in get_user_profile_with_cache: {e}")
            return None

    async def get_or_create_user(self, line_user_id: str) -> Dict[str, Any]:
        """GroupSyncService 用: ユーザーを DB に作成しプロフィールも補完

        Returns:
            dict: users テーブルの行情報（最低限 id, line_user_id, display_name）
        """
        try:
            # 既存チェック
            user_res = self.supabase.table("users").select("id, display_name").eq("line_user_id", line_user_id).execute()
            if user_res.data:
                user_row = user_res.data[0]
                # display_name が無ければプロフィール取得
                if not user_row.get("display_name"):
                    await self.get_user_profile_with_cache(line_user_id, force_refresh=True)
                return user_row

            # 無ければ新規作成
            new_user_data = {
                "line_user_id": line_user_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            insert_res = self.supabase.table("users").insert(new_user_data).execute()
            user_row = insert_res.data[0]
            # プロフィールを取得して保存
            await self.get_user_profile_with_cache(line_user_id, force_refresh=True)
            return user_row
        except Exception as e:
            logger.error(f"Error in get_or_create_user: {e}")
            return {"line_user_id": line_user_id}


# シングルトンインスタンスを作成
_SUPABASE_URL = os.getenv("SUPABASE_URL")
_SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY")
_LINE_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")

if not (_SUPABASE_URL and _SUPABASE_KEY and _LINE_TOKEN):
    # 環境変数が不足している場合はロガーのみ初期化し、None をセット
    logger.warning("Required env vars missing for LineUserProfileService initialization")
    line_user_profile_service: Optional[LineUserProfileService] = None
else:
    line_user_profile_service = LineUserProfileService(_LINE_TOKEN, create_client(_SUPABASE_URL, _SUPABASE_KEY)) 