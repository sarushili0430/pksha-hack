import os
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException

# ------ LINE v3 SDK ------
from langchain_openai.chat_models.base import OpenAIRefusalError
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
if not (SECRET and TOKEN and OPENAI):
    raise RuntimeError(".env の必須キーが不足しています")

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
@handler.add(MessageEvent, message=TextMessageContent)
def on_message(event: MessageEvent):
    user_text = event.message.text

    # LangChain で応答生成
    reply_text = chat_chain.invoke({"input": user_text})

    # LINE へ返信
    with ApiClient(cfg) as api_client:
        MessagingApi(api_client).reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=reply_text)]
            )
        )
