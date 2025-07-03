#!/usr/bin/env python3
"""
MessageServiceのテスト用スクリプト
"""
import asyncio
import uuid
import os
from unittest.mock import Mock, MagicMock
from app.message_service import MessageService

def create_mock_supabase_client():
    """
    モックSupabaseクライアントを作成
    """
    mock_client = Mock()
    mock_table = Mock()
    mock_client.table.return_value = mock_table
    
    # Mock query builder
    mock_query = Mock()
    mock_table.select.return_value = mock_query
    mock_query.eq.return_value = mock_query
    mock_query.order.return_value = mock_query
    mock_query.limit.return_value = mock_query
    
    return mock_client, mock_table, mock_query

async def test_get_group_message_history():
    """
    get_group_message_historyをテスト
    """
    print("=== Testing get_group_message_history ===")
    
    # モックデータを準備
    mock_client, mock_table, mock_query = create_mock_supabase_client()
    
    # サンプルメッセージデータ
    sample_messages = [
        {
            "text_content": "こんにちは",
            "message_type": "text",
            "created_at": "2024-01-01T10:00:00Z"
        },
        {
            "text_content": "元気ですか？",
            "message_type": "text", 
            "created_at": "2024-01-01T10:01:00Z"
        },
        {
            "text_content": "",
            "message_type": "sticker",
            "created_at": "2024-01-01T10:02:00Z"
        }
    ]
    
    # Mock executeの結果を設定
    mock_result = Mock()
    mock_result.data = sample_messages
    mock_query.execute.return_value = mock_result
    
    # MessageServiceを初期化
    service = MessageService(mock_client)
    
    # テスト実行
    test_group_id = str(uuid.uuid4())
    result = await service.get_group_message_history(test_group_id, limit=10)
    
    # 結果検証
    print(f"Group ID: {test_group_id}")
    print(f"取得したメッセージ数: {len(result)}")
    print(f"メッセージ内容: {result}")
    
    # テキストメッセージのみがフィルタされることを確認
    assert len(result) == 2, f"Expected 2 text messages, got {len(result)}"
    assert result[0]["text_content"] == "こんにちは"
    assert result[1]["text_content"] == "元気ですか？"
    
    print("✓ get_group_message_history テスト成功")

async def test_format_history_for_llm():
    """
    format_history_for_llmをテスト
    """
    print("\n=== Testing format_history_for_llm ===")
    
    mock_client, _, _ = create_mock_supabase_client()
    service = MessageService(mock_client)
    
    # サンプルメッセージデータ
    messages = [
        {"text_content": "今日は良い天気ですね"},
        {"text_content": "そうですね、散歩日和です"},
        {"text_content": "公園に行きませんか？"}
    ]
    
    # テスト実行
    result = service.format_history_for_llm(messages)
    
    print(f"フォーマット結果:\n{result}")
    
    # 結果検証
    expected_lines = [
        "- 今日は良い天気ですね",
        "- そうですね、散歩日和です", 
        "- 公園に行きませんか？"
    ]
    expected_result = "\n".join(expected_lines)
    
    assert result == expected_result, f"Expected:\n{expected_result}\nGot:\n{result}"
    
    print("✓ format_history_for_llm テスト成功")

async def test_get_recent_messages_for_llm():
    """
    get_recent_messages_for_llmをテスト
    """
    print("\n=== Testing get_recent_messages_for_llm ===")
    
    mock_client, mock_table, mock_query = create_mock_supabase_client()
    
    # サンプルメッセージデータ（新しい順）
    recent_messages = [
        {
            "text_content": "最新メッセージ",
            "message_type": "text",
            "created_at": "2024-01-01T12:00:00Z"
        },
        {
            "text_content": "2番目のメッセージ",
            "message_type": "text",
            "created_at": "2024-01-01T11:00:00Z"
        },
        {
            "text_content": "3番目のメッセージ",
            "message_type": "text",
            "created_at": "2024-01-01T10:00:00Z"
        }
    ]
    
    # Mock executeの結果を設定
    mock_result = Mock()
    mock_result.data = recent_messages
    mock_query.execute.return_value = mock_result
    
    # MessageServiceを初期化
    service = MessageService(mock_client)
    
    # テスト実行
    test_group_id = str(uuid.uuid4())
    result = await service.get_recent_messages_for_llm(test_group_id, max_messages=5)
    
    print(f"Group ID: {test_group_id}")
    print(f"フォーマット結果:\n{result}")
    
    # 結果検証（古い順になっているか）
    expected_result = "- 3番目のメッセージ\n- 2番目のメッセージ\n- 最新メッセージ"
    assert result == expected_result, f"Expected:\n{expected_result}\nGot:\n{result}"
    
    print("✓ get_recent_messages_for_llm テスト成功")

async def test_save_message():
    """
    save_messageをテスト
    """
    print("\n=== Testing save_message ===")
    
    mock_client, mock_table, _ = create_mock_supabase_client()
    
    # Mock insert の結果を設定
    mock_insert = Mock()
    mock_table.insert.return_value = mock_insert
    mock_insert.execute.return_value = Mock()
    
    # MessageServiceを初期化
    service = MessageService(mock_client)
    
    # テスト用データ
    test_user_id = str(uuid.uuid4())
    test_group_id = str(uuid.uuid4())
    test_message_type = "text"
    test_text_content = "テストメッセージ"
    test_raw_payload = {"source": {"type": "group", "groupId": test_group_id}}
    
    # テスト実行
    await service.save_message(
        user_id=test_user_id,
        group_id=test_group_id,
        message_type=test_message_type,
        text_content=test_text_content,
        raw_payload=test_raw_payload
    )
    
    # 呼び出し確認
    mock_table.insert.assert_called_once()
    call_args = mock_table.insert.call_args[0][0]
    
    print(f"保存されたデータ: {call_args}")
    
    # データ検証
    assert call_args["user_id"] == test_user_id
    assert call_args["group_id"] == test_group_id
    assert call_args["message_type"] == test_message_type
    assert call_args["text_content"] == test_text_content
    assert call_args["raw_payload"] == test_raw_payload
    assert "created_at" in call_args
    
    print("✓ save_message テスト成功")

# =============================================================================
# 実際のSupabaseに接続するテスト
# =============================================================================

def create_real_supabase_client():
    """
    実際のSupabaseクライアントを作成
    """
    try:
        from supabase import create_client, Client
        from dotenv import load_dotenv
        
        # .envファイルを読み込み
        load_dotenv()
        
        # 環境変数から接続情報を取得
        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_ANON_KEY')
        
        if not supabase_url or not supabase_key:
            print("Supabase環境変数が設定されていません")
            print("SUPABASE_URL:", supabase_url)
            print("SUPABASE_ANON_KEY:", "設定済み" if supabase_key else "未設定")
            return None
            
        print(f"Supabase接続中: {supabase_url}")
        return create_client(supabase_url, supabase_key)
        
    except Exception as e:
        print(f"Supabase接続エラー: {e}")
        return None

async def test_real_save_and_retrieve():
    """
    実際のSupabaseにデータを保存し、取得をテスト
    """
    print("\n=== Real Supabase Test: Save and Retrieve ===")
    
    client = create_real_supabase_client()
    if not client:
        print("❌ Supabase接続に失敗しました")
        return
    
    service = MessageService(client)
    
    # テスト用データ
    test_user_id = str(uuid.uuid4())
    test_group_id = str(uuid.uuid4())
    test_messages = [
        {
            "text": "テストメッセージ1",
            "type": "text",
            "payload": {"source": {"type": "group", "groupId": test_group_id}}
        },
        {
            "text": "テストメッセージ2", 
            "type": "text",
            "payload": {"source": {"type": "group", "groupId": test_group_id}}
        },
        {
            "text": "テストメッセージ3",
            "type": "text", 
            "payload": {"source": {"type": "group", "groupId": test_group_id}}
        }
    ]
    
    try:
        # 1. テストユーザーを作成
        print(f"テストユーザー作成: {test_user_id}")
        user_data = {
            "id": test_user_id,
            "line_user_id": f"test_line_user_{uuid.uuid4().hex[:8]}",
            "display_name": "テストユーザー"
        }
        client.table("users").insert(user_data).execute()
        
        # 2. テストグループを作成
        print(f"テストグループ作成: {test_group_id}")
        group_data = {
            "id": test_group_id,
            "line_group_id": f"test_line_group_{uuid.uuid4().hex[:8]}",
            "group_name": "テストグループ"
        }
        client.table("groups").insert(group_data).execute()
        
        # 3. メッセージを保存
        print("メッセージ保存中...")
        for i, msg in enumerate(test_messages):
            await service.save_message(
                user_id=test_user_id,
                group_id=test_group_id,
                message_type=msg["type"],
                text_content=msg["text"],
                raw_payload=msg["payload"]
            )
            # 時間差を作るため少し待機
            await asyncio.sleep(0.1)
        
        # 4. メッセージ履歴を取得
        print("メッセージ履歴取得中...")
        history = await service.get_group_message_history(test_group_id)
        print(f"取得されたメッセージ数: {len(history)}")
        
        for i, msg in enumerate(history):
            print(f"  {i+1}. {msg.get('text_content', 'No text')}")
        
        # 5. LLM用フォーマットをテスト
        print("\nLLM用フォーマットテスト...")
        formatted = await service.get_recent_messages_for_llm(test_group_id, max_messages=5)
        print(f"フォーマット結果:\n{formatted}")
        
        # 6. 結果検証
        assert len(history) == 3, f"Expected 3 messages, got {len(history)}"
        assert history[0]["text_content"] == "テストメッセージ1"
        assert history[1]["text_content"] == "テストメッセージ2"
        assert history[2]["text_content"] == "テストメッセージ3"
        
        print("✓ 実際のSupabaseテスト成功")
        
    except Exception as e:
        print(f"❌ 実際のSupabaseテストエラー: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # クリーンアップ
        try:
            print("\nテストデータクリーンアップ中...")
            client.table("messages").delete().eq("group_id", test_group_id).execute()
            client.table("group_members").delete().eq("group_id", test_group_id).execute()
            client.table("groups").delete().eq("id", test_group_id).execute()
            client.table("users").delete().eq("id", test_user_id).execute()
            print("✓ クリーンアップ完了")
        except Exception as e:
            print(f"クリーンアップエラー: {e}")

async def test_real_with_existing_data():
    """
    既存のデータを使用したテスト
    """
    print("\n=== Real Supabase Test: Existing Data ===")
    
    client = create_real_supabase_client()
    if not client:
        print("❌ Supabase接続に失敗しました")
        return
    
    service = MessageService(client)
    
    try:
        # 既存のユーザーを取得
        users_result = client.table("users").select("id, line_user_id").limit(1).execute()
        if not users_result.data:
            print("既存のユーザーが見つかりません")
            return
        
        user_data = users_result.data[0]
        print(f"既存ユーザー使用: {user_data['id']}")
        
        # 既存のグループを取得
        groups_result = client.table("groups").select("id, line_group_id").limit(1).execute()
        if groups_result.data:
            group_data = groups_result.data[0]
            print(f"既存グループ使用: {group_data['id']}")
            
            # メッセージ履歴を取得
            history = await service.get_group_message_history(group_data['id'])
            print(f"既存メッセージ数: {len(history)}")
            
            if history:
                print("最新5件のメッセージ:")
                for i, msg in enumerate(history[-5:]):
                    print(f"  {i+1}. {msg.get('text_content', 'No text')[:50]}...")
            
            # LLM用フォーマット
            formatted = await service.get_recent_messages_for_llm(group_data['id'], max_messages=3)
            print(f"\nLLM用フォーマット（最新3件）:\n{formatted}")
            
        else:
            print("既存グループが見つかりません")
        
        print("✓ 既存データテスト完了")
        
    except Exception as e:
        print(f"❌ 既存データテストエラー: {e}")
        import traceback
        traceback.print_exc()

async def main():
    """
    すべてのテストを実行
    """
    print("MessageService 関数テストを開始します...\n")
    
    # モックテストを実行
    try:
        print("=== MOCK TESTS ===")
        await test_get_group_message_history()
        await test_format_history_for_llm()
        await test_get_recent_messages_for_llm()
        await test_save_message()
        
        print("\n🎉 モックテストが成功しました！")
        
    except Exception as e:
        print(f"\n❌ モックテストエラー: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 実際のSupabaseテスト
    print("\n\n=== REAL SUPABASE TESTS ===")
    
    # 実際のSupabaseが利用可能かチェック
    if create_real_supabase_client():
        try:
            await test_real_save_and_retrieve()
            await test_real_with_existing_data()
            print("\n🎉 実際のSupabaseテストも成功しました！")
        except Exception as e:
            print(f"\n❌ 実際のSupabaseテストエラー: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("実際のSupabaseテストをスキップしました（接続不可）")
        print("Supabaseを起動するには: supabase start")

if __name__ == "__main__":
    asyncio.run(main())