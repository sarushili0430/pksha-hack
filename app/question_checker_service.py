import logging
import os
import json
from datetime import datetime, timedelta
from app.ai_service import get_ai_service
from app.database_service import database_service

logger = logging.getLogger(__name__)

class QuestionCheckerService:
    def __init__(self):
        self.ai_service = None
        self._initialize_ai_service()
    
    def _initialize_ai_service(self):
        """AI サービスを初期化"""
        try:
            openai_api_key = os.getenv("OPENAI_API_KEY")
            if openai_api_key:
                self.ai_service = get_ai_service(openai_api_key)
            else:
                logger.warning("OPENAI_API_KEY not found, question detection will be disabled")
        except Exception as e:
            logger.error(f"Error initializing AI service: {e}")
    
    async def detect_question(self, message_text: str) -> dict:
        """
        メッセージが質問かどうかを判定する（支払い要求は除外）
        
        Args:
            message_text: 判定するメッセージテキスト
            
        Returns:
            dict: 判定結果と詳細情報
        """
        if not self.ai_service:
            return {"is_question": False, "reason": "AI service not available"}
        
        try:           
            # AIを使用した詳細判定
            prompt = f"""
            以下のメッセージは、相手から最後に送られてきたメッセージです。
            あなたは、このメッセージに対して、返信する必要があるかどうかを判定してください。
            その際、そう判断した理由と以下の質問の種類を判定してください。

            メッセージ: "{message_text}"

            質問の種類:
            - 疑問符：（？、?）が含まれている
            - 疑問詞：（何、どう、いつ、どこ、誰、なぜ、どの等）が含まれている
            - 情報要求：その他、返信が必要な場合
            - null：返信が不要な場合
            
            注意
            支払いや金銭に関する要求は質問として扱わない（別途実装しているため）

            以下のJSON形式で回答してください:
            {{
                "is_question": true/false,
                "question_type": "疑問符" | "疑問詞" | "情報要求" | null,
                "reason": "判定理由"
            }}
            """
            
            response = await self.ai_service.quick_call(prompt)
            
            # JSONパースを試行
            try:
                result = json.loads(response)
                return result
            except json.JSONDecodeError:
                # JSONパースに失敗した場合は簡単な判定
                has_question_mark = "？" in message_text or "?" in message_text
                
                return {
                    "is_question": has_question_mark,
                    "question_type": "疑問符" if has_question_mark else None,
                    "reason": "Fallback detection with regex"
                }
                
        except Exception as e:
            logger.error(f"Error in question detection: {e}")
            return {"is_question": False, "reason": f"Error: {str(e)}"}
    
    async def save_question(self, event_data: dict, message_text: str, questioner_line_user_id: str):
        """
        質問をデータベースに保存
        
        Args:
            event_data: LINEイベントデータ
            message_text: 質問メッセージテキスト
            questioner_line_user_id: 質問者のLINE User ID
        """
        try:
            source = event_data.get("source", {})
            line_group_id = source.get("groupId")
            message_id = event_data.get("message", {}).get("id")
            
            if not line_group_id:
                logger.error("Group ID not found in event data")
                return
            
            # LINE IDsをUUIDに変換
            questioner_user_uuid = await database_service._ensure_user_exists(questioner_line_user_id)
            group_uuid = await database_service._ensure_group_exists(line_group_id)
            
            # 60秒後にリマインドを設定
            remind_at = datetime.now() + timedelta(seconds=60)
            
            # questionsテーブルに保存
            question_data = {
                "group_id": group_uuid,
                "questioner_user_id": questioner_user_uuid,
                "question_text": message_text,
                "message_id": message_id,
                "remind_at": remind_at.isoformat()
            }
            
            result = database_service.supabase.table("questions").insert(question_data).execute()
            
            if result.data:
                logger.info(f"Question saved: {result.data[0]['id']}")
                logger.info(
                    f"[SCHEDULE] Question reminder at {remind_at.isoformat()} for group {line_group_id} question='{message_text[:40]}'"
                )
                return result.data[0]['id']
            else:
                logger.error("Failed to save question")
                return None
                
        except Exception as e:
            logger.error(f"Error saving question: {e}")
            return None
    
    async def process_group_message(self, event_data: dict):
        """
        グループメッセージの処理（質問判定）
        
        Args:
            event_data: LINEイベントデータ
        """
        try:
            # メッセージタイプとテキストを取得
            message_type = event_data.get("type")
            if message_type != "message":
                return
                
            message = event_data.get("message", {})
            if message.get("type") != "text":
                return
                
            message_text = message.get("text", "")
            user_id = event_data.get("source", {}).get("userId")
            
            if not message_text or not user_id:
                logger.warning("Missing message text or user ID")
                return
            
            # 質問かどうかを判定
            detection_result = await self.detect_question(message_text)
            
            logger.info(f"Question detection result: {detection_result}")
            
            # 質問の場合、DBに保存
            if detection_result.get("is_question"):
                question_id = await self.save_question(event_data, message_text, user_id)
                if question_id:
                    logger.info(f"Question processed and saved: {question_id} from user {user_id}")
                else:
                    logger.error(f"Failed to save question from user {user_id}")
            
        except Exception as e:
            logger.error(f"Error processing group message: {e}")

# シングルトンインスタンス
question_checker_service = QuestionCheckerService()