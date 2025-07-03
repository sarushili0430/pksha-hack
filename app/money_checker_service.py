import logging
import os
import re
import json
from datetime import datetime, timedelta
from app.database_service import database_service
from app.ai_service import get_ai_service

logger = logging.getLogger(__name__)

class MoneyCheckerService:
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
                logger.warning("OPENAI_API_KEY not found, payment detection will be disabled")
        except Exception as e:
            logger.error(f"Error initializing AI service: {e}")
    
    async def detect_payment_request(self, message_text: str) -> dict:
        """
        メッセージが支払いリクエストかどうかを判定し、詳細を抽出
        
        Args:
            message_text: 判定するメッセージテキスト
            
        Returns:
            dict: 判定結果と詳細情報
        """
        if not self.ai_service:
            return {"is_payment_request": False, "reason": "AI service not available"}
        
        try:        
            # AIを使用した詳細判定
            prompt = f"""
                    あなたは、LINE上のお金の支払いや返済を求めるメッセージを判定するAIです。
                    以下のメッセージが「お金の支払いや返済を求めるメッセージ」かどうかを判定してください。
                    「1人5000ずつねー」など、明示的にお金であることが書かれていなくても、LINEのメッセージとして通常支払いを求めているな、
                    と判断した場合は、支払いリクエストとして判定してください。
                    また、「５人で10000円」など、人数と金額が明示的に書かれている場合は、その人数で割った金額を1人あたりの支払い金額として判定してください。

                    メッセージ: "{message_text}"

                    想定するケース:
                    - 飲み会、食事、買い物などの費用の請求
                    - 借りたお金の返済要求
                    - 割り勘の請求

                    以下のJSON形式で回答してください:
                    {{
                        "is_payment_request": true/false,
                        "amount": 1人あたりが支払うべき金額（数値のみ、不明な場合はnull）,
                        "reason": "判定理由"
                    }}
                    """
            
            response = await self.ai_service.quick_call(prompt)
            
            # JSONパースを試行
            try:
                result = json.loads(response)
                return result
            except json.JSONDecodeError:
                # JSONパースに失敗した場合は正規表現で金額を抽出
                amount_match = re.search(r'(\d+)\s*円', message_text)
                amount = int(amount_match.group(1)) if amount_match else None
                
                return {
                    "is_payment_request": True,
                    "amount": amount,
                    "reason": "Fallback detection with regex"
                }
                
        except Exception as e:
            logger.error(f"Error in payment detection: {e}")
            return {"is_payment_request": False, "reason": f"Error: {str(e)}"}
    
    async def save_payment_request(self, event_data: dict, amount: int, requester_line_user_id: str):
        """
        支払いリクエストをデータベースに保存
        
        Args:
            event_data: LINEイベントデータ
            amount: 請求金額
            requester_line_user_id: 請求者のLINE User ID
        """
        try:
            source = event_data.get("source", {})
            line_group_id = source.get("groupId")
            
            if not line_group_id:
                logger.error("Group ID not found in event data")
                return
            
            # LINE IDsをUUIDに変換
            requester_user_uuid = await database_service._ensure_user_exists(requester_line_user_id)
            group_uuid = await database_service._ensure_group_exists(line_group_id)
            
            # 60秒後にリマインドを設定
            remind_at = datetime.now() + timedelta(seconds=60)
            
            # データベースに保存
            money_request_data = {
                "group_id": group_uuid,
                "requester_user_id": requester_user_uuid,
                "amount": amount,
                "remind_at": remind_at.isoformat()
            }
            
            result = database_service.supabase.table("money_requests").insert(money_request_data).execute()
            
            if result.data:
                logger.info(f"Payment request saved: {result.data[0]['id']}")
                logger.info(
                    f"[SCHEDULE] Payment reminder at {remind_at.isoformat()} for group {line_group_id} amount={amount}円"
                )
            else:
                logger.error("Failed to save payment request")
                
        except Exception as e:
            logger.error(f"Error saving payment request: {e}")
    
    async def process_group_message(self, event_data: dict):
        """
        グループメッセージの処理（支払いリクエスト判定）
        
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
            
            # 支払いリクエストかどうかを判定
            detection_result = await self.detect_payment_request(message_text)
            
            logger.info(f"Payment detection result: {detection_result}")
            
            # 支払いリクエストの場合、DBに保存
            if detection_result.get("is_payment_request") and detection_result.get("amount"):
                await self.save_payment_request(event_data, detection_result["amount"], user_id)
                logger.info(f"Payment request processed: {detection_result['amount']} yen from user {user_id}")
            
        except Exception as e:
            logger.error(f"Error processing group message: {e}")

# シングルトンインスタンス
money_checker_service = MoneyCheckerService()