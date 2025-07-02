import os
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from supabase import create_client, Client
from datetime import datetime, timezone

# ------ LINE v3 SDK ------
from linebot.v3 import WebhookHandler          # 署名検証 & ルーティング
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
)
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
)

# ------ LangChain ------
from langchain_openai import ChatOpenAI        # OpenAI ラッパー
from langchain.prompts import ChatPromptTemplate
from langchain.chains import LLMChain

# =========================
# 0. 環境変数
# =========================
load_dotenv()
SECRET  = os.getenv("LINE_CHANNEL_SECRET")
TOKEN   = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
OPENAI  = os.getenv("OPENAI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY")

print(f"SECRET exists: {bool(SECRET)}")
print(f"TOKEN exists: {bool(TOKEN)}")
print(f"OPENAI exists: {bool(OPENAI)}")
print(f"SUPABASE_URL exists: {bool(SUPABASE_URL)}")
print(f"SUPABASE_KEY exists: {bool(SUPABASE_KEY)}")

if not (SECRET and TOKEN and OPENAI and SUPABASE_URL and SUPABASE_KEY):
    raise RuntimeError(".env の必須キーが不足しています")

# =========================
# Supabase接続
# =========================
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# =========================
# 1. LINE SDK v3 初期化
# =========================
cfg      = Configuration(access_token=TOKEN)
handler   = WebhookHandler(SECRET)          # 署名検証用
# MessagingApi はリクエスト時にだけ生成（接続を最小化）
# with ApiClient(cfg) as api_client:
#     messaging_api = MessagingApi(api_client)

# =========================
# 2. LangChain セットアップ
# =========================
llm = ChatOpenAI(
    model_name="gpt-4.1-2025-04-14",     # もちろん gpt-4o / 3.5 も可
    temperature=0.7,
    openai_api_key=OPENAI
)

system_prompt = "あなたは親切なアシスタントです。"
prompt = ChatPromptTemplate.from_messages([
    ("system", system_prompt),
    ("human", "{input}"),
])
chat_chain = LLMChain(llm=llm, prompt=prompt)

# =========================
# 3. FastAPI アプリ
# =========================
app = FastAPI()

@app.get("/")
async def health():
    return {"status": "ok"}

@app.post("/api/webhook")
async def callback(request: Request):
    signature = request.headers.get("X-Line-Signature", "")
    body      = (await request.body()).decode("utf-8")

    # LINE 署名検証 & ルーティング（handler 内でデコレータに飛ぶ）
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    return "OK"


# =========================
# 4. LINE Webhook ハンドラ
# =========================
def get_or_create_user(line_user_id: str):
    try:
        result = supabase.table("users").select("id").eq("line_user_id", line_user_id).execute()
        
        if result.data:
            return result.data[0]["id"]
        
        user_data = {
            "line_user_id": line_user_id,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        result = supabase.table("users").insert(user_data).execute()
        return result.data[0]["id"]
    except Exception as e:
        print(f"Error in get_or_create_user: {e}")
        raise

def get_or_create_group(line_group_id: str):
    try:
        result = supabase.table("groups").select("id").eq("line_group_id", line_group_id).execute()
        
        if result.data:
            return result.data[0]["id"]
        
        group_data = {
            "line_group_id": line_group_id,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        result = supabase.table("groups").insert(group_data).execute()
        return result.data[0]["id"]
    except Exception as e:
        print(f"Error in get_or_create_group: {e}")
        raise

def save_message(user_id: str, group_id: str, message_type: str, text_content: str, raw_payload: dict):
    try:
        message_data = {
            "user_id": user_id,
            "group_id": group_id,
            "message_type": message_type,
            "text_content": text_content,
            "raw_payload": raw_payload,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        supabase.table("messages").insert(message_data).execute()
    except Exception as e:
        print(f"Error in save_message: {e}")
        raise

@handler.add(MessageEvent, message=TextMessageContent)
def on_message(event: MessageEvent):
    try:
        user_text = event.message.text
        print(f"Received message: {user_text}")
        
        # ユーザー情報を取得・作成
        line_user_id = event.source.user_id
        user_id = get_or_create_user(line_user_id)
        
        # グループメッセージかどうかチェック
        group_id = None
        if hasattr(event.source, 'group_id') and event.source.group_id:
            line_group_id = event.source.group_id
            group_id = get_or_create_group(line_group_id)
        
        # メッセージをSupabaseに保存
        raw_payload = {
            "type": event.type,
            "message": {
                "id": event.message.id,
                "type": event.message.type,
                "text": event.message.text
            },
            "timestamp": event.timestamp,
            "source": event.source.__dict__,
            "reply_token": event.reply_token
        }
        
        save_message(user_id, group_id, "text", user_text, raw_payload)

        # LangChain で応答生成
        response = chat_chain.invoke({"input": user_text})
        reply_text = response["text"]  # LLMChainの結果から"text"キーを取得
        print(f"Generated reply: {reply_text}")

        # LINE へ返信
        with ApiClient(cfg) as api_client:
            MessagingApi(api_client).reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=reply_text)]
                )
            )
        print("Reply sent successfully")
    
    except Exception as e:
        print(f"Error in on_message: {e}")
        # エラー時の返信
        with ApiClient(cfg) as api_client:
            MessagingApi(api_client).reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text="申し訳ございません。エラーが発生しました。")]
                )
            )
