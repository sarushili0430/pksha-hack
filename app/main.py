from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from contextlib import asynccontextmanager
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import Configuration
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3.exceptions import InvalidSignatureError
from app.webhook_service import webhook_service
from app.reminder_service import reminder_service
from app.question_reminder_service import question_reminder_service
import os
import logging
import json
import asyncio
from dotenv import load_dotenv

# Configure logging
load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """アプリケーションのライフサイクル管理"""
    # 起動時の処理
    logger.info("Starting reminder service...")
    reminder_task = asyncio.create_task(reminder_service.start_reminder_loop())
    yield
    # 終了時の処理
    logger.info("Stopping reminder service...")
    reminder_service.stop_reminder_loop()
    reminder_task.cancel()
    try:
        await reminder_task
    except asyncio.CancelledError:
        pass

app = FastAPI(title="LINE Bot", version="1.0.0", lifespan=lifespan)

# LINE Bot configuration
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")

if not LINE_CHANNEL_SECRET or not LINE_CHANNEL_ACCESS_TOKEN:
    raise ValueError("LINE_CHANNEL_SECRET and LINE_CHANNEL_ACCESS_TOKEN must be set")

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

@app.get("/")
async def root():
    return {"message": "LINE Bot is running"}

@app.post("/api/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    signature = request.headers.get("X-Line-Signature")
    body = await request.body()
    
    if not signature:
        raise HTTPException(status_code=400, detail="X-Line-Signature header is missing")
    
    try:
        # Webhookペイロードをパース
        webhook_payload = json.loads(body.decode("utf-8"))
        
        # 各イベントに対してバックグラウンドタスクでwebhook処理実行
        for event_data in webhook_payload.get("events", []):
            if event_data.get("type") == "message" and event_data.get("message", {}).get("type") == "text":
                background_tasks.add_task(webhook_service.process_webhook_event, event_data, webhook_payload)
        
        handler.handle(body.decode("utf-8"), signature)
    except InvalidSignatureError:
        logger.error("Invalid signature. Please check your channel secret.")
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        logger.error(f"Error handling webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    
    return "OK"

@app.post("/api/question-reminders")
async def trigger_question_reminders():
    """質問リマインダーを手動で実行"""
    try:
        result = await question_reminder_service.process_all_inactive_users()
        return {
            "success": True,
            "message": "Question reminders processed successfully",
            "data": result
        }
    except Exception as e:
        logger.error(f"Error processing question reminders: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing question reminders: {str(e)}")

@app.get("/api/question-reminders/status")
async def get_question_reminders_status():
    """質問リマインダーの対象ユーザーを確認"""
    try:
        inactive_users = await question_reminder_service.find_inactive_users_for_questions()
        return {
            "success": True,
            "inactive_users_count": len(inactive_users),
            "inactive_users": inactive_users
        }
    except Exception as e:
        logger.error(f"Error getting question reminders status: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting status: {str(e)}")

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    logger.info(f"Received message: {event.message.text}")
    # メッセージ処理ロジックをここに追加
    # DB保存は既にwebhook関数でバックグラウンドタスクとして実行されています

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)