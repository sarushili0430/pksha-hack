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
from typing import Optional, List
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from supabase import create_client, Client
from datetime import datetime, timezone
import time

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
from linebot.v3.messaging.rest import ApiException

# ------ 分離されたサービス ------
from ai_service import get_ai_service
from message_service import get_message_service

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

# MessageService を初期化
message_service = get_message_service(supabase)

# =========================
# 1. LINE SDK v3 初期化
# =========================
cfg      = Configuration(access_token=TOKEN)
handler   = WebhookHandler(SECRET)          # 署名検証用
# MessagingApi はリクエスト時にだけ生成（接続を最小化）
# with ApiClient(cfg) as api_client:
#     messaging_api = MessagingApi(api_client)

# =========================
# 2. 分離されたサービスの初期化
# =========================
# AIService（LLM処理）とMessageService（履歴管理）を初期化
ai_service = get_ai_service(OPENAI)
# message_service は supabase 初期化後に設定

# =========================
# 3. FastAPI アプリ
# =========================
app = FastAPI()

@app.get("/")
async def health():
    return {"status": "ok"}

@app.post("/api/sync-group-members")
async def sync_group_members_endpoint(request: Request, background_tasks: BackgroundTasks):
    """
    手動でグループメンバーを同期するためのエンドポイント（非同期処理）
    """
    try:
        data = await request.json()
        line_group_id = data.get("line_group_id")
        force_sync = data.get("force_sync", False)
        
        if not line_group_id:
            raise HTTPException(status_code=400, detail="line_group_id is required")
        
        # グループを取得または作成
        group_id = await get_or_create_group(line_group_id)
        
        # 強制同期の場合はキャッシュをクリア
        if force_sync and line_group_id in _group_sync_cache:
            del _group_sync_cache[line_group_id]
        
        # バックグラウンドでメンバー同期を実行
        background_tasks.add_task(sync_group_members_background, line_group_id, group_id)
        
        return {
            "status": "success", 
            "message": f"Group member sync started for {line_group_id}",
            "force_sync": force_sync
        }
        
    except Exception as e:
        print(f"Error in sync_group_members_endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# =========================
# 【フロー1】Webhookエンドポイント
# =========================
@app.post("/api/webhook")
async def callback(request: Request):
    """
    LINEからのメッセージWebhookを受信するエンドポイント
    署名検証後、LINE SDKのhandlerにルーティングする
    """
    signature = request.headers.get("X-Line-Signature", "")
    body      = (await request.body()).decode("utf-8")

    # LINE 署名検証 & ルーティング（handler 内でデコレータに飛ぶ）
    try:
        handler.handle(body, signature)  # → 【フロー2】on_message() へ
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    return "OK"


# =========================
# 4. LINE Webhook ハンドラ
# =========================
async def get_or_create_user(line_user_id: str):
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

async def get_or_create_group(line_group_id: str):
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

# save_message 関数は message_service.save_message() に移行済み

async def get_group_members(line_group_id: str):
    """
    LINEグループのメンバーIDリストを取得
    """
    try:
        with ApiClient(cfg) as api_client:
            messaging_api = MessagingApi(api_client)
            response = messaging_api.get_group_members_ids(line_group_id)
            return response.member_ids
    except ApiException as e:
        print(f"Error getting group members for {line_group_id}: {e}")
        raise
    except Exception as e:
        print(f"Unexpected error getting group members: {e}")
        raise

# グループメンバー同期の頻度制御用キャッシュ
_group_sync_cache = {}
SYNC_COOLDOWN_SECONDS = 300  # 5分間のクールダウン

async def sync_group_members(line_group_id: str, group_id: str):
    """
    LINEグループのメンバーをgroup_membersテーブルに同期（頻度制御付き）
    """
    try:
        # 頻度制御チェック
        current_time = time.time()
        last_sync = _group_sync_cache.get(line_group_id, 0)
        
        if current_time - last_sync < SYNC_COOLDOWN_SECONDS:
            print(f"Skipping sync for group {line_group_id} - too frequent (last: {int(current_time - last_sync)}s ago)")
            return
        
        # LINEからメンバーIDリストを取得
        member_ids = await get_group_members(line_group_id)
        
        if not member_ids:
            print(f"No members found for group {line_group_id}")
            return
            
        print(f"Found {len(member_ids)} members in group {line_group_id}")
        
        # 非同期でユーザー作成処理を並列実行
        user_tasks = []
        for line_user_id in member_ids:
            task = get_or_create_user(line_user_id)
            user_tasks.append((line_user_id, task))
        
        # 全ユーザーの作成/取得を並列実行
        user_results = {}
        for line_user_id, task in user_tasks:
            try:
                user_id = await task
                user_results[line_user_id] = user_id
            except Exception as e:
                print(f"Error creating/getting user {line_user_id}: {e}")
                continue
        
        # group_membersテーブルへの追加処理
        for line_user_id, user_id in user_results.items():
            try:
                # 既存のメンバーシップをチェック
                existing = supabase.table("group_members").select("*").eq("group_id", group_id).eq("user_id", user_id).execute()
                
                if not existing.data:
                    # 新しいメンバーを追加
                    member_data = {
                        "group_id": group_id,
                        "user_id": user_id,
                        "joined_at": datetime.now(timezone.utc).isoformat(),
                        "last_active_at": datetime.now(timezone.utc).isoformat()
                    }
                    supabase.table("group_members").insert(member_data).execute()
                    print(f"Added new member {line_user_id} to group {line_group_id}")
                else:
                    # 既存メンバーのlast_active_atを更新
                    supabase.table("group_members").update({
                        "last_active_at": datetime.now(timezone.utc).isoformat()
                    }).eq("group_id", group_id).eq("user_id", user_id).execute()
                    print(f"Updated last_active_at for member {line_user_id}")
                    
            except Exception as e:
                print(f"Error adding member {line_user_id} to group: {e}")
                continue
        
        # 同期完了をキャッシュに記録
        _group_sync_cache[line_group_id] = current_time
        print(f"Group member sync completed for {line_group_id}")
                
    except Exception as e:
        print(f"Error syncing group members: {e}")
        raise

async def sync_group_members_background(line_group_id: str, group_id: str):
    """
    バックグラウンドでグループメンバーを同期
    """
    try:
        await sync_group_members(line_group_id, group_id)
    except Exception as e:
        print(f"Background sync failed for group {line_group_id}: {e}")

# =========================
# 【フロー2】メッセージイベントハンドラ
# =========================
@handler.add(MessageEvent, message=TextMessageContent)
def on_message(event: MessageEvent):
    """
    LINEメッセージイベントハンドラ（LINE SDKデコレータによるルーティング）
    同期処理で即座に応答し、非同期タスクを作成して処理を移行
    """
    try:
        # 非同期処理に移行 → 【フロー3】process_message_async() へ
        asyncio.create_task(process_message_async(event))
        
    except Exception as e:
        print(f"Error in on_message: {e}")
        # エラー時の返信
        try:
            with ApiClient(cfg) as api_client:
                MessagingApi(api_client).reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text="申し訳ございません。エラーが発生しました。")]
                    )
                )
        except Exception as reply_error:
            print(f"Failed to send error reply: {reply_error}")

# =========================
# 【フロー3】非同期メッセージ処理
# =========================
async def process_message_async(event: MessageEvent):
    """
    メッセージ処理の非同期実装
    ユーザー作成、グループ作成、LLM呼び出しを並列処理で実行
    """
    try:
        # TextMessageContentかどうかを確認
        if not isinstance(event.message, TextMessageContent):
            print("Non-text message received, skipping...")
            return
            
        user_text = event.message.text
        print(f"Received message: {user_text}")
        
        # reply_tokenが存在しない場合はエラー
        if not event.reply_token:
            print("No reply token found, cannot respond")
            return
        
        # 並列処理用のタスクを準備
        tasks = []
        
        # ユーザー情報を取得・作成（非同期）
        line_user_id = event.source.user_id
        user_task = get_or_create_user(line_user_id)
        tasks.append(("user", user_task))
        
        # グループメッセージかどうかチェック
        group_id = None
        line_group_id = getattr(event.source, 'group_id', None)
        if line_group_id:
            group_task = get_or_create_group(line_group_id)
            tasks.append(("group", group_task))
        
        # 【★重要】AI応答生成タスクを準備（履歴は後で取得）
        # この時点ではタスクを作成せず、後で履歴と一緒に処理
        
        # 並列実行
        results = {}
        for task_name, task in tasks:
            try:
                result = await task
                results[task_name] = result
            except Exception as e:
                print(f"Error in {task_name} task: {e}")
                if task_name == "user":
                    raise  # ユーザー作成は必須
        
        user_id = results.get("user")
        group_id = results.get("group")
        
        # ユーザーIDが取得できない場合はエラー
        if not user_id:
            raise Exception("User ID could not be obtained")
        
        # 【フロー4】履歴取得 + LLM応答生成
        history = ""
        if group_id:
            # グループの場合は過去メッセージ履歴を取得
            history = await message_service.get_recent_messages_for_llm(group_id, max_messages=1000)
        
        # AI応答生成（履歴付き）
        reply_text = await ai_service.generate_response_async(user_text, history)
        
        # グループメンバー同期（バックグラウンド実行）
        if line_group_id and group_id:
            asyncio.create_task(sync_group_members_background(line_group_id, group_id))
        
        # メッセージをSupabaseに保存（非同期）
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
        
        # メッセージ保存と返信を並列実行
        save_task = message_service.save_message(user_id, group_id, "text", user_text, raw_payload)
        reply_task = send_reply_async(event.reply_token, reply_text)
        
        await asyncio.gather(save_task, reply_task, return_exceptions=True)
        print("Message processing completed")
    
    except Exception as e:
        print(f"Error in process_message_async: {e}")
        # エラー時の返信
        try:
            await send_reply_async(event.reply_token, "申し訳ございません。エラーが発生しました。")
        except Exception as reply_error:
            print(f"Failed to send error reply: {reply_error}")

# 【フロー4】LLM応答生成は ai_service.generate_response_async() に移行済み

async def send_reply_async(reply_token: str, text: str):
    """
    LINE返信の非同期実装
    """
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, send_reply_sync, reply_token, text)
        print("Reply sent successfully")
    except Exception as e:
        print(f"Error sending reply: {e}")
        raise

def send_reply_sync(reply_token: str, text: str):
    """
    LINE返信の同期実装
    """
    with ApiClient(cfg) as api_client:
        MessagingApi(api_client).reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=text)]
            )
        )
