1. uv sync でライブラリインストール
2. uv run uvicorn app.main:app --reload --port 8000


LINE                         FastAPI               Domain Services                 外部API
┌─────────┐   1.POST        ┌──────────────┐                                       ┌─────────┐
│  User   │ ─────────────▶ │ /api/webhook │ ─ 2. handler.handle ───────────────▶ │  None   │
└─────────┘                └──────────────┘            │                          └─────────┘
                                                         ▼
                                             3. on_message()   (同期)─┐
                                                                     │ asyncio.create_task
                                                                     ▼
                                             4. process_message_async()  (非同期)
     ┌──────────────────────────────────────────────────────────────────────────────────────────┐
     │ 4-1  get_or_create_user()          ──────────┐                                           │
     │ 4-2  get_or_create_group() (任意)  ─────┐    │   （並列 Future）                         │
     │                                         ▼    ▼                                           │
     │ 4-3  message_service.get_recent_messages_for_llm()   ────┐ (履歴取得 & 整形)            │
     │                                                          │                                │
     │ 4-4  ai_service.generate_response_async()  (OpenAI) ◀────┘                                │
     │                                                                                        │
     │ 4-5  sync_group_members_background()  ──▶ Supabase & LINE API  (※BGタスク)              │
     │ 4-6  message_service.save_message()    ──▶ Supabase (ログ保存)                          │
     │ 4-7  send_reply_async()                ──▶ LINE Reply API                               │
     └──────────────────────────────────────────────────────────────────────────────────────────┘
