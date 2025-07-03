"""
メッセージ履歴管理サービス

Supabaseから過去メッセージを取得し、LLM用にフォーマットする機能を提供します。
"""

from typing import List, Dict, Optional
from supabase import Client
from datetime import datetime, timezone


class MessageService:
    """
    メッセージ履歴管理サービス
    
    Supabaseからグループの過去メッセージを取得し、
    LLMプロンプト用にフォーマットします。
    """
    
    def __init__(self, supabase_client: Client):
        """
        MessageServiceを初期化
        
        Args:
            supabase_client: Supabaseクライアント
        """
        self.supabase = supabase_client
    
    async def get_group_message_history(
        self, 
        group_id: str, 
        limit: Optional[int] = None,
        exclude_current_message: bool = False
    ) -> List[Dict]:
        """
        グループの過去メッセージを取得
        
        Args:
            group_id: グループのUUID
            limit: 取得する最大件数（Noneなら全件）
            exclude_current_message: 最新メッセージを除外するか
            
        Returns:
            メッセージリスト（古い順）
        """
        try:
            query = (
                self.supabase
                    .table("messages")
                    .select("text_content, message_type, created_at")
                    .eq("group_id", group_id)
                    .order("created_at")
            )
            
            # 件数制限がある場合
            if limit:
                query = query.limit(limit)
            
            result = query.execute()
            messages = result.data
            
            # テキストメッセージのみフィルタ
            text_messages = [
                msg for msg in messages 
                if msg.get("message_type") == "text" and msg.get("text_content")
            ]
            
            # 最新メッセージを除外する場合
            if exclude_current_message and text_messages:
                text_messages = text_messages[:-1]
            
            print(f"Retrieved {len(text_messages)} historical messages for group {group_id}")
            return text_messages
            
        except Exception as e:
            print(f"Failed to fetch message history for group {group_id}: {e}")
            return []
    
    def format_history_for_llm(self, messages: List[Dict]) -> str:
        """
        メッセージリストをLLMプロンプト用にフォーマット
        
        Args:
            messages: メッセージリスト
            
        Returns:
            フォーマット済み履歴文字列
        """
        if not messages:
            return "（過去の会話履歴はありません）"
        
        formatted_lines = []
        for msg in messages:
            text_content = msg.get("text_content", "").strip()
            if text_content:
                # 簡潔なフォーマット（発言者情報は省略）
                formatted_lines.append(f"- {text_content}")
        
        if not formatted_lines:
            return "（過去の会話履歴はありません）"
        
        return "\n".join(formatted_lines)
    
    async def get_recent_messages_for_llm(
        self, 
        group_id: str, 
        max_messages: int = 20
    ) -> str:
        """
        LLM用に最近のメッセージ履歴を取得・フォーマット
        
        Args:
            group_id: グループのUUID
            max_messages: 最大取得件数（トークン制限対策）
            
        Returns:
            LLMプロンプト用の履歴文字列
        """
        try:
            # 最近のメッセージを取得（降順で取得して件数制限後、昇順に戻す）
            result = (
                self.supabase
                    .table("messages")
                    .select("text_content, message_type, created_at")
                    .eq("group_id", group_id)
                    .order("created_at", desc=True)
                    .limit(max_messages)
                    .execute()
            )
            
            recent_messages = result.data
            
            # 古い順に戻す
            recent_messages.reverse()
            
            # テキストメッセージのみフィルタ
            text_messages = [
                msg for msg in recent_messages 
                if msg.get("message_type") == "text" and msg.get("text_content")
            ]
            
            return self.format_history_for_llm(text_messages)
            
        except Exception as e:
            print(f"Failed to get recent messages for LLM: {e}")
            return "（メッセージ履歴の取得に失敗しました）"
    
    async def save_message(
        self, 
        user_id: str, 
        group_id: Optional[str], 
        message_type: str, 
        text_content: str, 
        raw_payload: dict
    ):
        """
        メッセージをSupabaseに保存
        
        Args:
            user_id: 送信者のユーザーID
            group_id: グループID（1対1の場合はNone）
            message_type: メッセージタイプ
            text_content: テキスト内容
            raw_payload: LINEからの生データ
        """
        try:
            message_data = {
                "user_id": user_id,
                "group_id": group_id,
                "message_type": message_type,
                "text_content": text_content,
                "raw_payload": raw_payload,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            self.supabase.table("messages").insert(message_data).execute()
            print(f"Message saved: {message_type} in group {group_id}")
            
        except Exception as e:
            print(f"Error saving message: {e}")
            raise


# シングルトンインスタンス（main.pyで使用）
_message_service: Optional[MessageService] = None

def get_message_service(supabase_client: Client) -> MessageService:
    """
    MessageServiceのシングルトンインスタンスを取得
    
    Args:
        supabase_client: Supabaseクライアント
        
    Returns:
        MessageServiceインスタンス
    """
    global _message_service
    if _message_service is None:
        _message_service = MessageService(supabase_client)
    return _message_service
