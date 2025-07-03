import logging
from app.database_service import database_service

logger = logging.getLogger(__name__)

class WebhookService:
    def __init__(self):
        pass
    
    async def process_webhook_event(self, event_data: dict, webhook_payload: dict):
        """
        Webhook処理のメイン関数
        DBへの登録とLLMメッセージチェック等の処理を行う
        """
        try:
            # DBへの登録
            await database_service.save_message_from_webhook(event_data, webhook_payload)
            
            # TODO: LLMメッセージチェック等の処理をここに追加
            
        except Exception as e:
            logger.error(f"Error in webhook processing: {e}")
            raise

webhook_service = WebhookService()