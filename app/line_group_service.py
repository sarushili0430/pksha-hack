"""
LINE Group Service
LINEグループ情報を取得するサービス
"""
import asyncio
from typing import Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from linebot.v3.messaging import Configuration, ApiClient, MessagingApi
from linebot.v3.messaging.rest import ApiException
from supabase import Client


class LineGroupService:
    """LINE Group Service"""
    
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
    
    async def get_group_summary(self, line_group_id: str) -> Optional[Dict[str, Any]]:
        """
        LINE グループの情報を取得
        
        Args:
            line_group_id: LINE グループID (例: C1234567890abcdef1234567890abcdef0)
            
        Returns:
            グループ情報の辞書、または None（エラー時）
            {
                "group_id": "C1234567890abcdef1234567890abcdef0",
                "group_name": "グループ名",
                "picture_url": "グループ画像URL"
            }
        """
        try:
            # LINE API を非同期で呼び出し
            loop = asyncio.get_event_loop()
            group_summary = await loop.run_in_executor(
                self.executor,
                self._get_group_summary_sync,
                line_group_id
            )
            
            if group_summary:
                return {
                    "group_id": group_summary.group_id,
                    "group_name": group_summary.group_name,
                    "picture_url": group_summary.picture_url
                }
            else:
                return None
                
        except Exception as e:
            print(f"Error getting group summary for {line_group_id}: {e}")
            return None
    
    def _get_group_summary_sync(self, line_group_id: str):
        """
        同期的にグループ情報を取得（内部メソッド）
        """
        try:
            with ApiClient(self.line_config) as api_client:
                api_instance = MessagingApi(api_client)
                group_summary = api_instance.get_group_summary(line_group_id)
                return group_summary
        except ApiException as e:
            print(f"LINE API Exception: {e}")
            return None
        except Exception as e:
            print(f"Unexpected error: {e}")
            return None
    
    async def get_group_summary_with_cache(
        self, 
        line_group_id: str, 
        force_refresh: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        キャッシュ機能付きでグループ情報を取得
        
        Args:
            line_group_id: LINE グループID
            force_refresh: True の場合、キャッシュを無視してLINE APIから取得
            
        Returns:
            グループ情報の辞書、または None（エラー時）
        """
        cache_key = f"group_summary_{line_group_id}"
        
        # キャッシュから取得を試行（force_refresh が False の場合）
        if not force_refresh:
            try:
                # 1時間以内のキャッシュを取得
                one_hour_ago = datetime.now(timezone.utc).replace(
                    minute=0, second=0, microsecond=0
                ).isoformat()
                
                cached_result = self.supabase_client.table("line_group_cache") \
                    .select("*") \
                    .eq("line_group_id", line_group_id) \
                    .gte("updated_at", one_hour_ago) \
                    .order("updated_at", desc=True) \
                    .limit(1) \
                    .execute()
                
                if cached_result.data:
                    cached_data = cached_result.data[0]
                    print(f"Using cached group summary for {line_group_id}")
                    return {
                        "group_id": cached_data["line_group_id"],
                        "group_name": cached_data["group_name"],
                        "picture_url": cached_data["picture_url"]
                    }
                    
            except Exception as e:
                print(f"Error reading from cache: {e}")
        
        # LINE API から取得
        group_summary = await self.get_group_summary(line_group_id)
        
        if group_summary:
            # キャッシュに保存
            try:
                now = datetime.now(timezone.utc).isoformat()
                cache_data = {
                    "line_group_id": line_group_id,
                    "group_name": group_summary["group_name"],
                    "picture_url": group_summary["picture_url"],
                    "updated_at": now
                }
                
                # Upsert でキャッシュを更新
                self.supabase_client.table("line_group_cache") \
                    .upsert(cache_data, on_conflict="line_group_id") \
                    .execute()
                    
                print(f"Cached group summary for {line_group_id}")
                
            except Exception as e:
                print(f"Error saving to cache: {e}")
        
        return group_summary


# Singleton instance
_line_group_service: Optional[LineGroupService] = None

def get_line_group_service(line_access_token: str, supabase_client: Client) -> LineGroupService:
    """
    LineGroupService のシングルトンインスタンスを取得
    
    Args:
        line_access_token: LINE チャンネルアクセストークン
        supabase_client: Supabase クライアント
        
    Returns:
        LineGroupService インスタンス
    """
    global _line_group_service
    if _line_group_service is None:
        _line_group_service = LineGroupService(line_access_token, supabase_client)
    return _line_group_service