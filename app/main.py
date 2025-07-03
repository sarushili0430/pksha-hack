"""
LINE Bot + LangChain + Supabase 統合アプリケーション

このアプリケーションは、LINEメッセージを受信してOpenAI GPT-4で応答を生成し、
Supabaseデータベースにユーザー・グループ・メッセージ情報を保存するシステムです。

【メッセージ受信からLLM呼び出しまでの処理フロー】

1. Webhookエンドポイント (/api/webhook)
   ↓ LINEからのメッセージWebhookを受信
   
2. メッセージイベントハンドラ (@handler.add デコレータ)
   ↓ on_message() - LINE SDKによるルーティング
   
3. 非同期メッセージ処理 
   ↓ process_message_async() - 並列処理でタスクを実行
   
4. LLM応答生成
   ↓ generate_response_async() - OpenAI GPT-4への実際の呼び出し
   
5. LangChainチェーン実行
   ↓ chat_chain.invoke() - プロンプトテンプレートでGPT-4実行

【並列処理の特徴】
- ユーザー作成、グループ作成、LLM呼び出しを同時実行
- エラーハンドリングでデフォルト応答を保証
- run_in_executor()で同期処理を非同期化

【データベース構造】
- users: LINEユーザー情報
- groups: LINEグループ情報  
- group_members: グループとユーザーの多対多関係
- messages: メッセージログとLINE生データ
"""

import os
import asyncio
import json  # ★ADD: JSON パース用
from typing import Optional
from datetime import datetime, timezone, timedelta  # ★ADD: timedelta
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from supabase import create_client, Client

# ------ LINE v3 SDK ------
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    PushMessageRequest,  # ★ADD: Push 用
    TextMessage,
)
from linebot.v3.messaging.rest import ApiException

# ------ 分離されたサービス ------
from app.ai_service import get_ai_service
from app.message_service import get_message_service
from app.push_service import get_push_service
from app.line_user_profile_service import get_line_user_profile_service

# =========================
# 0. 環境変数
# =========================
load_dotenv()
SECRET       = os.getenv("LINE_CHANNEL_SECRET")
TOKEN        = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
OPENAI       = os.getenv("OPENAI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY")

if not all([SECRET, TOKEN, OPENAI, SUPABASE_URL, SUPABASE_KEY]):
    raise RuntimeError(".env の必須キーが不足しています")

# =========================
# Supabase 接続
# =========================
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# MessageService を初期化
message_service = get_message_service(supabase)

# =========================
# LINE SDK v3 初期化
# =========================
cfg     = Configuration(access_token=TOKEN)
handler = WebhookHandler(SECRET)

# =========================
# AIService 初期化
# =========================
ai_service = get_ai_service(OPENAI)

# =========================
# PushService 初期化
# =========================
push_service = get_push_service(TOKEN, supabase)

# =========================
# LINE User Profile Service 初期化
# =========================
line_user_profile_service = get_line_user_profile_service(TOKEN, supabase)

# =========================
# FastAPI アプリ
# =========================
app = FastAPI()

@app.get("/")
async def health():
    return {"status": "ok"}

# =========================
# プッシュメッセージ送信API
# =========================
@app.post("/api/push-message")
async def send_push_message(request: dict):
    """
    プッシュメッセージ送信API
    
    Body:
        {
            "type": "user" | "group" | "line_user" | "line_group",
            "id": "送信先ID",
            "message": "送信するメッセージ"
        }
    """
    try:
        message_type = request.get("type")
        target_id = request.get("id")
        message = request.get("message")
        
        if not all([message_type, target_id, message]):
            return {"success": False, "error": "Missing required fields"}
        
        success = False
        if message_type == "user":
            success = await push_service.send_to_user(target_id, message)
        elif message_type == "group":
            success = await push_service.send_to_group(target_id, message)
        elif message_type == "line_user":
            success = await push_service.send_to_line_user(target_id, message)
        elif message_type == "line_group":
            success = await push_service.send_to_line_group(target_id, message)
        else:
            return {"success": False, "error": "Invalid message type"}
        
        return {"success": success}
        
    except Exception as e:
        return {"success": False, "error": str(e)}


# =========================
# LINE User Profile API
# =========================
@app.get("/api/line-user-profile/{line_user_id}")
async def get_line_user_profile(line_user_id: str, force_refresh: bool = False):
    """
    LINE ユーザーのプロフィール情報を取得
    
    Args:
        line_user_id: LINE ユーザーID (例: U1234567890abcdef)
        force_refresh: True の場合、キャッシュを無視してLINE APIから取得
        
    Returns:
        {
            "success": True/False,
            "data": {
                "user_id": "U1234567890abcdef",
                "display_name": "表示名",
                "picture_url": "プロフィール画像URL",
                "status_message": "ステータスメッセージ",
                "language": "言語コード"
            },
            "error": "エラーメッセージ（エラー時のみ）"
        }
    """
    try:
        # LINE User ID の形式チェック
        if not line_user_id.startswith('U') or len(line_user_id) != 33:
            return {
                "success": False,
                "error": "Invalid LINE user ID format. Expected format: U + 32 characters"
            }
        
        # プロフィール情報を取得
        profile = await line_user_profile_service.get_user_profile_with_cache(
            line_user_id, force_refresh=force_refresh
        )
        
        if profile:
            return {
                "success": True,
                "data": profile
            }
        else:
            return {
                "success": False,
                "error": "User profile not found or LINE API error"
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


# ★DEL: /api/sync-group-members と関連メンバー同期ロジックをすべて削除


# =========================
# Webhook エンドポイント
# =========================
@app.post("/api/webhook")
async def callback(request: Request):
    signature = request.headers.get("X-Line-Signature", "")
    body      = (await request.body()).decode("utf-8")
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    return "OK"


# =========================
# ユーザー／グループ作成
# =========================
async def get_or_create_user(line_user_id: str) -> str:
    result = supabase.table("users").select("id").eq("line_user_id", line_user_id).execute()
    if result.data:
        return result.data[0]["id"]
    user_data = {"line_user_id": line_user_id, "created_at": datetime.now(timezone.utc).isoformat()}
    inserted = supabase.table("users").insert(user_data).execute()
    return inserted.data[0]["id"]

async def get_or_create_group(line_group_id: str) -> str:
    result = supabase.table("groups").select("id").eq("line_group_id", line_group_id).execute()
    if result.data:
        return result.data[0]["id"]
    group_data = {"line_group_id": line_group_id, "created_at": datetime.now(timezone.utc).isoformat()}
    inserted = supabase.table("groups").insert(group_data).execute()
    return inserted.data[0]["id"]


# ★ADD: money_requests 登録用
async def create_money_request(
    group_id: str,
    requester_id: str,
    amount: int,
    delay_sec: int = 20
):
    remind_at = datetime.now(timezone.utc) + timedelta(seconds=delay_sec)
    # 重複ガード
    dup = supabase.table("money_requests") \
        .select("id") \
        .eq("group_id", group_id) \
        .eq("requester_user_id", requester_id) \
        .gt("remind_at", datetime.now(timezone.utc).isoformat()) \
        .execute()
    if dup.data:
        print("★ADD: Duplicate money request ignored")
        return
    supabase.table("money_requests").insert({
        "group_id": group_id,
        "requester_user_id": requester_id,
        "amount": amount,
        "remind_at": remind_at.isoformat()
    }).execute()
    print("★ADD: Money request saved")


# ★ADD: リマインド送信ループ
async def reminder_loop():
    while True:
        now_iso = datetime.now(timezone.utc).isoformat()
        print(f"★DEBUG: Checking money_requests at {now_iso}")
        
        due = supabase.table("money_requests") \
            .select("id, group_id, requester_user_id, amount, remind_at") \
            .lte("remind_at", now_iso) \
            .execute().data
        
        print(f"★DEBUG: Found {len(due)} due reminders")
        
        for row in due:
            try:
                # LINE Group IDを個別に取得
                group_result = supabase.table("groups").select("line_group_id").eq("id", row["group_id"]).execute()
                if not group_result.data:
                    print(f"Group not found: {row['group_id']}")
                    continue
                    
                line_group_id = group_result.data[0]["line_group_id"]
                
                # リマインドメッセージを作成
                text = (
                    f"💰 お金の催促リマインド\n"
                    f"請求者への {row['amount']}円の支払いはお済みですか？\n"
                    f"まだの方は忘れずにお支払いください。"
                )
                
                # push_serviceを使用してメッセージ送信
                success = await push_service.send_to_line_group(line_group_id, text)
                
                if success:
                    # 送信成功時のみ削除
                    supabase.table("money_requests").delete().eq("id", row["id"]).execute()
                    print(f"★ADD: Sent reminder for {row['id']}")
                else:
                    print(f"★ADD: Failed to send reminder for {row['id']}")
                    
            except Exception as e:
                print(f"Reminder processing failed: {e}")
        await asyncio.sleep(60)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(reminder_loop())


# =========================
# メッセージイベントハンドラ
# =========================
@handler.add(MessageEvent, message=TextMessageContent)
def on_message(event: MessageEvent):
    asyncio.create_task(process_message_async(event))


# =========================
# 非同期メッセージ処理
# =========================
async def process_message_async(event: MessageEvent):
    # テキスト以外はスキップ
    if not isinstance(event.message, TextMessageContent):
        return

    user_text = event.message.text
    line_user_id  = event.source.user_id
    line_group_id = getattr(event.source, "group_id", None)
    reply_token   = event.reply_token

    # ユーザー＆グループ取得
    user_id  = await get_or_create_user(line_user_id)
    group_id = None
    if line_group_id:
        group_id = await get_or_create_group(line_group_id)

    # 会話履歴取得
    history = ""
    if group_id:
        history = await message_service.get_recent_messages_for_llm(group_id, max_messages=50)

    # AI 応答生成
    reply_text = await ai_service.generate_response_async(user_text, history)

    # メッセージ保存＆返信
    raw_payload = {
        "type": event.type,
        "message": {"id": event.message.id, "type": event.message.type, "text": user_text},
        "timestamp": event.timestamp,
        "source": event.source.__dict__,
        "reply_token": reply_token
    }
    save_task  = message_service.save_message(user_id, group_id, "text", user_text, raw_payload)
    reply_req  = ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text=reply_text)])
    # ★DEL: run_in_executor 不要化
    async def do_reply():
        with ApiClient(cfg) as api_client:
            MessagingApi(api_client).reply_message(reply_req)

    # ★ADD: 請求判定タスク
    async def detect_money_request():
        # グループメッセージでない場合はスキップ
        if not group_id:
            return
            
        prompt = (
            "あなたは会計係です。\n"
            "この発言が誰かに具体的な金額を請求している場合のみ、"
            '{"yes": true, "amount": <金額>}をJSONで返してください。'
            "それ以外は{\"yes\": false}を返してください。\n"
            f"### 発言\n{user_text}"
        )
        try:
            resp = await ai_service.generate_response_async(prompt, "")
            # JSONパースを安全に実行
            try:
                data = json.loads(resp.strip())
                if data.get("yes") and "amount" in data:
                    amount = int(data["amount"])
                    if amount > 0:
                        await create_money_request(group_id, user_id, amount)
            except (json.JSONDecodeError, ValueError, KeyError) as json_err:
                print(f"JSON parsing failed: {json_err}, response: {resp}")
        except Exception as e:
            print(f"Money detection failed: {e}")

    # 並列実行
    await asyncio.gather(save_task, do_reply(), detect_money_request(), return_exceptions=True)
