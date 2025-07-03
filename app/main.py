from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from contextlib import asynccontextmanager
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import Configuration
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3.exceptions import InvalidSignatureError
from app.webhook_service import webhook_service
from app.reminder_service import reminder_service
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

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    logger.info(f"Received message: {event.message.text}")
    # メッセージ処理ロジックをここに追加
    # DB保存は既にwebhook関数でバックグラウンドタスクとして実行されています

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)