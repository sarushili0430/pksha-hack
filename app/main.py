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
from typing import Optional, Set
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
    TextMessageV2,  # ★ADD: Mention 用
    MentionSubstitutionObject,  # ★ADD: Mention 用
    UserMentionTarget,  # ★ADD: Mention 用
)
from linebot.v3.messaging.rest import ApiException

# ------ 分離されたサービス ------
from app.ai_service import get_ai_service
from app.message_service import get_message_service
from app.push_service import get_push_service
from app.line_user_profile_service import get_line_user_profile_service
from app.question_service import get_question_service
from app.group_sync_service import get_group_sync_service

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
# Question Service 初期化
# =========================
question_service = get_question_service(supabase, ai_service)

# =========================
# Group Sync Service 初期化
# =========================
group_sync_service = get_group_sync_service(TOKEN, supabase)

# =========================
# FastAPI アプリ
# =========================
app = FastAPI()

# ★ADD: 重複メッセージ処理防止用のセット
processed_message_ids: Set[str] = set()

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
            .is_("reminded_at", "null") \
            .order("remind_at") \
            .limit(1) \
            .execute().data
        
        print(f"★DEBUG: Found {len(due)} due reminders")
        
        # 1回のループで1つのリマインダーのみ処理
        if due:
            row = due[0]  # 最初の（最も古い）リマインダーを処理
            try:
                print(f"★DEBUG: Processing reminder ID: {row['id']}")
                
                # LINE Group IDを個別に取得
                group_result = supabase.table("groups").select("line_group_id").eq("id", row["group_id"]).execute()
                if not group_result.data:
                    print(f"Group not found: {row['group_id']}, marking as reminded to skip")
                    # 無効なリマインダーをスキップ（reminded_atを設定）
                    supabase.table("money_requests").update({
                        "reminded_at": datetime.now(timezone.utc).isoformat()
                    }).eq("id", row["id"]).execute()
                else:
                    line_group_id = group_result.data[0]["line_group_id"]
                    
                    # 請求者のLINE User IDを取得
                    requester_result = supabase.table("users").select("line_user_id").eq("id", row["requester_user_id"]).execute()
                    if not requester_result.data:
                        print(f"Requester user not found: {row['requester_user_id']}, marking as reminded to skip")
                        # 無効なリマインダーをスキップ（reminded_atを設定）
                        supabase.table("money_requests").update({
                            "reminded_at": datetime.now(timezone.utc).isoformat()
                        }).eq("id", row["id"]).execute()
                    else:
                        requester_line_user_id = requester_result.data[0]["line_user_id"]
                        
                        # 請求者のプロフィール情報を取得
                        requester_profile = await line_user_profile_service.get_user_profile_with_cache(requester_line_user_id)
                        requester_name = "誰か"  # デフォルト名
                        
                        if requester_profile and requester_profile.get("display_name"):
                            requester_name = requester_profile["display_name"]
                            print(f"★DEBUG: Found requester profile: {requester_name}")
                        else:
                            print(f"★DEBUG: Could not get requester profile for {requester_line_user_id}")
                        
                        # グループの他のメンバーを取得（請求者以外）
                        mention_targets = []
                        mention_text_parts = []
                        try:
                            # グループメンバーを取得
                            group_members_result = supabase.table("group_members") \
                                .select("user_id, users(line_user_id)") \
                                .eq("group_id", row["group_id"]) \
                                .neq("user_id", row["requester_user_id"]) \
                                .execute()
                            
                            if group_members_result.data:
                                for i, member in enumerate(group_members_result.data):
                                    if member.get("users") and i < 6:  # 最大6名まで
                                        member_line_user_id = member["users"]["line_user_id"]
                                        member_profile = await line_user_profile_service.get_user_profile_with_cache(member_line_user_id)
                                        
                                        if member_profile and member_profile.get("display_name"):
                                            # メンション対象を追加
                                            mention_key = f"member{i}"
                                            mention_targets.append(UserMentionTarget(
                                                user_id=member_line_user_id,
                                                type="user"
                                            ))
                                            mention_text_parts.append(f"{{{mention_key}}}")
                                            print(f"★DEBUG: Added mention target {member_line_user_id}")
                                        else:
                                            print(f"★DEBUG: Could not get member profile for {member_line_user_id}")
                                
                                # 残りのメンバー数を計算
                                total_members = len(group_members_result.data)
                                displayed_members = len(mention_targets)
                                remaining_count = total_members - displayed_members
                                
                                print(f"★DEBUG: Total members: {total_members}, Displayed: {displayed_members}, Remaining: {remaining_count}")
                            else:
                                print("★DEBUG: No other group members found")
                        except Exception as e:
                            print(f"★DEBUG: Error getting other group members: {e}")
                        
                        # メンション付きメッセージを作成
                        base_text = (
                            f"💰 お金の催促リマインド\n"
                            f"{requester_name}さんへの {row['amount']}円の支払いはお済みですか？\n"
                            f"まだの方は忘れずにお支払いください。"
                        )
                        
                        if mention_targets:
                            # メンション部分を追加
                            mention_text = " ".join(mention_text_parts)
                            remaining_count = len(group_members_result.data) - len(mention_targets)
                            if remaining_count > 0:
                                text = f"{base_text}\n\n{mention_text} 他{remaining_count}名の皆さん、確認お願いします！"
                            else:
                                text = f"{base_text}\n\n{mention_text} さん、確認お願いします！"
                        else:
                            text = base_text
                        
                        print(f"★DEBUG: Sending reminder message: {text}")
                        
                        # メンション付きメッセージ送信
                        if mention_targets:
                            success = await push_service.send_to_line_group_with_mentions(line_group_id, text, mention_targets)
                        else:
                            # メンションがない場合は通常のメッセージ送信
                            success = await push_service.send_to_line_group(line_group_id, text)
                        
                        if success:
                            # 送信成功時にreminded_atを更新（レコードは削除しない）
                            supabase.table("money_requests").update({
                                "reminded_at": datetime.now(timezone.utc).isoformat()
                            }).eq("id", row["id"]).execute()
                            print(f"★DEBUG: Sent reminder and marked as reminded for ID: {row['id']}")
                        else:
                            print(f"★DEBUG: Failed to send reminder for ID: {row['id']}")
                    
            except Exception as e:
                print(f"★DEBUG: Reminder processing failed for ID {row.get('id', 'unknown')}: {e}")
                # エラーが発生したリマインダーもスキップ（無限ループを防ぐ）
                try:
                    supabase.table("money_requests").update({
                        "reminded_at": datetime.now(timezone.utc).isoformat()
                    }).eq("id", row["id"]).execute()
                    print(f"★DEBUG: Marked problematic reminder as reminded, ID: {row['id']}")
                except:
                    pass
        else:
            print("★DEBUG: No reminders due at this time")
        await asyncio.sleep(15)  # ハッカソン用: 15秒間隔でチェック

# ★ADD: 質問リマインド送信ループ
async def question_reminder_loop():
    """質問への返答リマインドを送信するループ"""
    while True:
        now_iso = datetime.now(timezone.utc).isoformat()
        print(f"★DEBUG: Checking questions for reminders at {now_iso}")
        
        # 期限が来た未解決の質問を取得
        due_questions = supabase.table("questions") \
            .select("*") \
            .lte("remind_at", now_iso) \
            .is_("resolved_at", "null") \
            .order("remind_at") \
            .limit(1) \
            .execute().data
        
        print(f"★DEBUG: Found {len(due_questions)} due question reminders")
        
        if due_questions:
            question = due_questions[0]
            try:
                print(f"★DEBUG: Processing question reminder ID: {question['id']}")
                
                # 質問に対する返答をチェック
                response_found = await question_service.check_for_responses(question['id'])
                
                if response_found:
                    print(f"★DEBUG: Question {question['id']} has responses, skipping reminder")
                else:
                    # 未返答かつ未リマインドのターゲットを取得
                    targets_result = supabase.table("question_targets") \
                        .select("id, target_user_id, users(line_user_id)") \
                        .eq("question_id", question['id']) \
                        .is_("responded_at", "null") \
                        .is_("reminded_at", "null") \
                        .execute()
                    
                    if targets_result.data:
                        # 質問者の情報を取得
                        questioner_result = supabase.table("users") \
                            .select("line_user_id") \
                            .eq("id", question['questioner_user_id']) \
                            .execute()
                        
                        questioner_name = "誰か"
                        if questioner_result.data:
                            questioner_line_user_id = questioner_result.data[0]['line_user_id']
                            questioner_profile = await line_user_profile_service.get_user_profile_with_cache(questioner_line_user_id)
                            if questioner_profile and questioner_profile.get("display_name"):
                                questioner_name = questioner_profile["display_name"]
                        
                        # グループ名を取得
                        group_result = supabase.table("groups") \
                            .select("line_group_id") \
                            .eq("id", question['group_id']) \
                            .execute()
                        
                        group_name = "グループ"
                        if group_result.data:
                            # グループ名の取得は複雑なので、簡易的にIDを使用
                            group_name = f"グループ({group_result.data[0]['line_group_id'][:8]}...)"
                        
                        # 各ターゲットに個別にリマインドを送信
                        for target in targets_result.data:
                            if target.get("users"):
                                target_line_user_id = target["users"]["line_user_id"]
                                target_record_id = target["id"]
                                
                                # 返答提案を生成
                                response_suggestion = await _generate_response_suggestion(
                                    question['question_text'], 
                                    questioner_name
                                )
                                
                                # リマインドメッセージを作成
                                reminder_text = (
                                    f"💬 返答リマインド\n\n"
                                    f"{questioner_name}さんから{group_name}で質問が届いて30秒経過しています。\n\n"
                                    f"質問内容：\n{question['question_text']}\n\n"
                                    f"こんな感じで返信しましょうか？\n{response_suggestion}"
                                )
                                
                                print(f"★DEBUG: Sending reminder to {target_line_user_id}")
                                
                                # 個人チャットにリマインド送信
                                success = await push_service.send_to_line_user(target_line_user_id, reminder_text)
                                
                                if success:
                                    # 個人ごとにリマインド送信完了をマーク
                                    supabase.table("question_targets").update({
                                        "reminded_at": datetime.now(timezone.utc).isoformat()
                                    }).eq("id", target_record_id).execute()
                                    
                                    print(f"★DEBUG: Sent reminder to {target_line_user_id} and marked as reminded")
                                else:
                                    print(f"★DEBUG: Failed to send reminder to {target_line_user_id}")
                    
                    # 全ターゲットが返答済みか確認
                    remaining_targets = supabase.table("question_targets") \
                        .select("id") \
                        .eq("question_id", question['id']) \
                        .is_("responded_at", "null") \
                        .execute()
                    
                    if not remaining_targets.data:
                        # 質問を解決済みとしてマーク（全ターゲットが返答済みの場合）
                        supabase.table("questions").update({
                            "resolved_at": datetime.now(timezone.utc).isoformat()
                        }).eq("id", question['id']).execute()
                        
                        print(f"★DEBUG: Marked question {question['id']} as resolved after all targets responded")
                    else:
                        print(f"★DEBUG: Question {question['id']} still has unresolved targets")
                    
            except Exception as e:
                print(f"★DEBUG: Question reminder processing failed for ID {question.get('id', 'unknown')}: {e}")
                # エラーが発生した質問もリマインド済みとしてマーク（無限ループを防ぐ）
                try:
                    supabase.table("questions").update({
                        "reminded_at": datetime.now(timezone.utc).isoformat()
                    }).eq("id", question['id']).execute()
                    print(f"★DEBUG: Marked problematic question as reminded, ID: {question['id']}")
                except:
                    pass
        else:
            print("★DEBUG: No question reminders due at this time")
        
        await asyncio.sleep(15)  # ハッカソン用: 15秒間隔でチェック

async def _generate_response_suggestion(question_text: str, questioner_name: str) -> str:
    """質問に対する返答提案を生成"""
    try:
        prompt = f"""
以下の質問に対して、自然で適切な返答例を1つ提案してください。
返答は簡潔で、実際に使いやすいものにしてください。

質問者: {questioner_name}さん
質問: {question_text}

返答例:"""
        
        response = await ai_service.quick_call(prompt)
        return response.strip()
    except Exception as e:
        print(f"Failed to generate response suggestion: {e}")
        return "了解しました！"

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(reminder_loop())
    asyncio.create_task(question_reminder_loop())


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

    # ★ADD: 重複メッセージチェック
    message_id = event.message.id
    if message_id in processed_message_ids:
        print(f"★DEBUG: Duplicate message detected, skipping: {message_id}")
        return
    
    # メッセージIDを記録
    processed_message_ids.add(message_id)
    
    # セットサイズを制限（メモリリーク防止）
    if len(processed_message_ids) > 1000:
        # 古いIDを半分削除
        old_ids = list(processed_message_ids)[:500]
        for old_id in old_ids:
            processed_message_ids.discard(old_id)
        print(f"★DEBUG: Cleaned up processed_message_ids, current size: {len(processed_message_ids)}")

    user_text = event.message.text
    line_user_id  = event.source.user_id
    line_group_id = getattr(event.source, "group_id", None)
    reply_token   = event.reply_token
    
    print(f"★DEBUG: Processing message ID {message_id} from user {line_user_id} in group {line_group_id}")
    print(f"★DEBUG: Message: {user_text}")
    print(f"★DEBUG: Reply token: {reply_token}")

    # ユーザー＆グループ取得
    user_id  = await get_or_create_user(line_user_id)
    group_id = None
    if line_group_id:
        group_id = await get_or_create_group(line_group_id)
        # ★ADD: グループメンバーの自動追加と同期フラグ管理
        print(f"★DEBUG: About to call GroupSync for user {user_id} in group {group_id}")
        try:
            result = await group_sync_service.add_user_and_mark_sync_if_needed(user_id, group_id)
            print(f"★DEBUG: GroupSync result: {result}")
        except Exception as e:
            print(f"★ERROR: GroupSync failed: {e}")
            import traceback
            print(f"★ERROR: GroupSync traceback: {traceback.format_exc()}")

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

    # ★ADD: 質問判定タスク
    async def detect_question():
        # グループメッセージでない場合はスキップ
        if not group_id:
            print(f"★DEBUG: Skipping question detection - not a group message")
            return
            
        print(f"★DEBUG: Starting question detection for message: '{user_text}' in group: {group_id}")
        
        try:
            # 質問検出
            result = await question_service.detect_question_and_targets(user_text, group_id)
            print(f"★DEBUG: Question detection result: {result}")
            
            if result:
                is_question, target_user_ids, question_content = result
                print(f"★DEBUG: Is question: {is_question}, Targets: {len(target_user_ids) if target_user_ids else 0}, Content: {question_content}")
                
                if is_question and target_user_ids:
                    # 質問レコードを作成
                    question_id = await question_service.create_question_record(
                        group_id=group_id,
                        questioner_user_id=user_id,
                        question_text=question_content,
                        target_user_ids=target_user_ids,
                        message_id=message_id,
                        remind_seconds=30  # ハッカソン用: 30秒でリマインド
                    )
                    
                    if question_id:
                        print(f"★ADD: Question created with ID: {question_id}")
                    else:
                        print("★ADD: Failed to create question record")
                elif is_question and not target_user_ids:
                    print("★DEBUG: Question detected but no valid targets found")
                else:
                    print("★DEBUG: Not detected as a question")
            else:
                print("★DEBUG: Question detection returned None")
                        
        except Exception as e:
            print(f"★ERROR: Question detection failed: {e}")
            import traceback
            print(f"★ERROR: Traceback: {traceback.format_exc()}")

    # 並列実行
    await asyncio.gather(save_task, do_reply(), detect_money_request(), detect_question(), return_exceptions=True)
