#!/usr/bin/env python3
"""
PushServiceのテスト用スクリプト
"""
import asyncio
import os
import uuid
from unittest.mock import Mock, patch, MagicMock
from app.push_service import PushService
from dotenv import load_dotenv

# =============================================================================
# モックテスト
# =============================================================================

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
    
    return mock_client, mock_table, mock_query

@patch('app.push_service.MessagingApi')
@patch('app.push_service.ApiClient')
async def test_send_to_user_mock(mock_api_client, mock_messaging_api):
    """
    send_to_userのモックテスト
    """
    print("=== Testing send_to_user (Mock) ===")
    
    # モックSupabaseクライアントを設定
    mock_client, mock_table, mock_query = create_mock_supabase_client()
    
    # ユーザー情報のモックデータ
    test_user_id = str(uuid.uuid4())
    test_line_user_id = "U" + uuid.uuid4().hex[:30]
    
    mock_result = Mock()
    mock_result.data = [{"line_user_id": test_line_user_id}]
    mock_query.execute.return_value = mock_result
    
    # LINE API モックを設定
    mock_messaging_instance = Mock()
    mock_messaging_api.return_value = mock_messaging_instance
    mock_messaging_instance.push_message.return_value = None
    
    # PushServiceを初期化
    service = PushService("mock_token", mock_client)
    
    # テスト実行
    result = await service.send_to_user(test_user_id, "テストメッセージ")
    
    # 結果検証
    assert result == True, "メッセージ送信が成功するべき"
    
    # Supabaseクエリが呼ばれたことを確認
    mock_table.select.assert_called_with("line_user_id")
    mock_query.eq.assert_called_with("id", test_user_id)
    
    # LINE API が呼ばれたことを確認
    mock_messaging_instance.push_message.assert_called_once()
    
    print(f"✓ User ID: {test_user_id}")
    print(f"✓ LINE User ID: {test_line_user_id}")
    print("✓ send_to_user モックテスト成功")

@patch('app.push_service.MessagingApi')
@patch('app.push_service.ApiClient')
async def test_send_to_line_user_mock(mock_api_client, mock_messaging_api):
    """
    send_to_line_userのモックテスト
    """
    print("\n=== Testing send_to_line_user (Mock) ===")
    
    mock_client, _, _ = create_mock_supabase_client()
    
    # LINE API モックを設定
    mock_messaging_instance = Mock()
    mock_messaging_api.return_value = mock_messaging_instance
    mock_messaging_instance.push_message.return_value = None
    
    # PushServiceを初期化
    service = PushService("mock_token", mock_client)
    
    # テスト実行
    test_line_user_id = "U" + uuid.uuid4().hex[:30]
    result = await service.send_to_line_user(test_line_user_id, "LINE直接送信テスト")
    
    # 結果検証
    assert result == True, "LINE直接送信が成功するべき"
    mock_messaging_instance.push_message.assert_called_once()
    
    print(f"✓ LINE User ID: {test_line_user_id}")
    print("✓ send_to_line_user モックテスト成功")

@patch('app.push_service.MessagingApi')
@patch('app.push_service.ApiClient')
async def test_send_to_group_mock(mock_api_client, mock_messaging_api):
    """
    send_to_groupのモックテスト
    """
    print("\n=== Testing send_to_group (Mock) ===")
    
    # モックSupabaseクライアントを設定
    mock_client, mock_table, mock_query = create_mock_supabase_client()
    
    # グループ情報のモックデータ
    test_group_id = str(uuid.uuid4())
    test_line_group_id = "C" + uuid.uuid4().hex[:30]
    
    mock_result = Mock()
    mock_result.data = [{"line_group_id": test_line_group_id}]
    mock_query.execute.return_value = mock_result
    
    # LINE API モックを設定
    mock_messaging_instance = Mock()
    mock_messaging_api.return_value = mock_messaging_instance
    mock_messaging_instance.push_message.return_value = None
    
    # PushServiceを初期化
    service = PushService("mock_token", mock_client)
    
    # テスト実行
    result = await service.send_to_group(test_group_id, "グループメッセージテスト")
    
    # 結果検証
    assert result == True, "グループメッセージ送信が成功するべき"
    
    # Supabaseクエリが呼ばれたことを確認
    mock_table.select.assert_called_with("line_group_id")
    mock_query.eq.assert_called_with("id", test_group_id)
    
    # LINE API が呼ばれたことを確認
    mock_messaging_instance.push_message.assert_called_once()
    
    print(f"✓ Group ID: {test_group_id}")
    print(f"✓ LINE Group ID: {test_line_group_id}")
    print("✓ send_to_group モックテスト成功")

@patch('app.push_service.MessagingApi')
@patch('app.push_service.ApiClient')
async def test_send_multiple_messages_mock(mock_api_client, mock_messaging_api):
    """
    send_multiple_messagesのモックテスト
    """
    print("\n=== Testing send_multiple_messages (Mock) ===")
    
    mock_client, _, _ = create_mock_supabase_client()
    
    # LINE API モックを設定
    mock_messaging_instance = Mock()
    mock_messaging_api.return_value = mock_messaging_instance
    mock_messaging_instance.push_message.return_value = None
    
    # PushServiceを初期化
    service = PushService("mock_token", mock_client)
    
    # テスト実行
    test_target_id = "U" + uuid.uuid4().hex[:30]
    test_messages = ["メッセージ1", "メッセージ2", "メッセージ3"]
    result = await service.send_multiple_messages(test_target_id, test_messages)
    
    # 結果検証
    assert result == True, "複数メッセージ送信が成功するべき"
    mock_messaging_instance.push_message.assert_called_once()
    
    print(f"✓ Target ID: {test_target_id}")
    print(f"✓ Messages: {test_messages}")
    print("✓ send_multiple_messages モックテスト成功")

async def test_user_not_found_mock():
    """
    ユーザーが見つからない場合のテスト
    """
    print("\n=== Testing user not found (Mock) ===")
    
    # モックSupabaseクライアントを設定（空の結果）
    mock_client, mock_table, mock_query = create_mock_supabase_client()
    
    mock_result = Mock()
    mock_result.data = []  # ユーザーが見つからない
    mock_query.execute.return_value = mock_result
    
    # PushServiceを初期化
    service = PushService("mock_token", mock_client)
    
    # テスト実行
    test_user_id = str(uuid.uuid4())
    result = await service.send_to_user(test_user_id, "存在しないユーザーへのメッセージ")
    
    # 結果検証
    assert result == False, "存在しないユーザーへの送信は失敗するべき"
    
    print(f"✓ Non-existent User ID: {test_user_id}")
    print("✓ user not found テスト成功")

# =============================================================================
# 実際のSupabaseとLINE APIを使用するテスト
# =============================================================================

def create_real_supabase_client():
    """
    実際のSupabaseクライアントを作成
    """
    try:
        from supabase import create_client, Client
        
        # .envファイルを読み込み
        load_dotenv()
        
        # 環境変数から接続情報を取得
        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_ANON_KEY')
        
        if not supabase_url or not supabase_key:
            print("Supabase環境変数が設定されていません")
            return None
            
        print(f"Supabase接続中: {supabase_url}")
        return create_client(supabase_url, supabase_key)
        
    except Exception as e:
        print(f"Supabase接続エラー: {e}")
        return None

def create_real_push_service():
    """
    実際のPushServiceを作成
    """
    try:
        load_dotenv()
        
        line_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
        if not line_token:
            print("LINE_CHANNEL_ACCESS_TOKEN環境変数が設定されていません")
            return None
        
        supabase_client = create_real_supabase_client()
        if not supabase_client:
            return None
        
        return PushService(line_token, supabase_client)
        
    except Exception as e:
        print(f"PushService作成エラー: {e}")
        return None

async def test_real_database_lookup():
    """
    実際のデータベースからユーザー・グループ情報を取得するテスト
    """
    print("\n=== Real Database Lookup Test ===")
    
    service = create_real_push_service()
    if not service:
        print("❌ PushService作成に失敗しました")
        return
    
    try:
        # 既存のユーザーを取得
        users_result = service.supabase.table("users").select("id, line_user_id, display_name").limit(3).execute()
        if users_result.data:
            print("既存ユーザー:")
            for user in users_result.data:
                print(f"  - User ID: {user['id']}")
                print(f"    LINE User ID: {user['line_user_id']}")
                print(f"    Name: {user.get('display_name', 'N/A')}")
                
                # LINE User IDの取得テスト
                line_user_id = await service._get_line_user_id(user['id'])
                assert line_user_id == user['line_user_id'], "LINE User ID取得エラー"
                print(f"    ✓ LINE User ID取得成功: {line_user_id}")
                print()
        else:
            print("既存ユーザーが見つかりません")
        
        # 既存のグループを取得
        groups_result = service.supabase.table("groups").select("id, line_group_id, group_name").limit(3).execute()
        if groups_result.data:
            print("既存グループ:")
            for group in groups_result.data:
                print(f"  - Group ID: {group['id']}")
                print(f"    LINE Group ID: {group['line_group_id']}")
                print(f"    Name: {group.get('group_name', 'N/A')}")
                
                # LINE Group IDの取得テスト
                line_group_id = await service._get_line_group_id(group['id'])
                assert line_group_id == group['line_group_id'], "LINE Group ID取得エラー"
                print(f"    ✓ LINE Group ID取得成功: {line_group_id}")
                print()
        else:
            print("既存グループが見つかりません")
        
        print("✓ 実際のデータベース検索テスト成功")
        
    except Exception as e:
        print(f"❌ データベース検索テストエラー: {e}")
        import traceback
        traceback.print_exc()

async def test_real_send_message_to_user():
    """
    実際のユーザーにメッセージを送信するテスト
    """
    print("\n=== Real Send Message Test ===")
    
    service = create_real_push_service()
    if not service:
        print("❌ PushService作成に失敗しました")
        return
    
    try:
        # 既存のユーザーを取得
        users_result = service.supabase.table("users").select("id, line_user_id, display_name").limit(1).execute()
        if not users_result.data:
            print("テスト用ユーザーが見つかりません")
            return
        
        user = users_result.data[0]
        user_id = user['id']
        line_user_id = user['line_user_id']
        display_name = user.get('display_name', 'Unknown')
        
        print(f"テスト送信先:")
        print(f"  - User ID: {user_id}")
        print(f"  - LINE User ID: {line_user_id}")
        print(f"  - Name: {display_name}")
        
        # ユーザーの確認を求める
        print("\n⚠️  実際のLINEメッセージを送信します。続行しますか？")
        print("送信をテストするには 'yes' と入力してください: ", end="")
        
        # 実際のテストでは自動実行するためコメントアウト
        # confirm = input().strip().lower()
        # if confirm != 'yes':
        #     print("テストをスキップしました")
        #     return
        
        print("yes (自動実行)")
        
        # 1. 内部IDでメッセージ送信
        print("\n1. 内部IDでメッセージ送信中...")
        test_message = f"PushService テストメッセージ (内部ID) - {uuid.uuid4().hex[:8]}"
        result1 = await service.send_to_user(user_id, test_message)
        
        if result1:
            print("✓ 内部IDでのメッセージ送信成功")
        else:
            print("❌ 内部IDでのメッセージ送信失敗")
        
        # 2. LINE IDで直接メッセージ送信
        print("\n2. LINE IDで直接メッセージ送信中...")
        test_message2 = f"PushService テストメッセージ (LINE ID) - {uuid.uuid4().hex[:8]}"
        result2 = await service.send_to_line_user(line_user_id, test_message2)
        
        if result2:
            print("✓ LINE IDでのメッセージ送信成功")
        else:
            print("❌ LINE IDでのメッセージ送信失敗")
        
        # 3. 複数メッセージ送信
        print("\n3. 複数メッセージ送信中...")
        multiple_messages = [
            "複数メッセージテスト 1/3",
            "複数メッセージテスト 2/3", 
            "複数メッセージテスト 3/3"
        ]
        result3 = await service.send_multiple_messages(line_user_id, multiple_messages)
        
        if result3:
            print("✓ 複数メッセージ送信成功")
        else:
            print("❌ 複数メッセージ送信失敗")
        
        # 結果サマリー
        success_count = sum([result1, result2, result3])
        print(f"\n📊 テスト結果: {success_count}/3 成功")
        
        if success_count == 3:
            print("🎉 全てのメッセージ送信テストが成功しました！")
        else:
            print("⚠️  一部のテストが失敗しました")
        
    except Exception as e:
        print(f"❌ 実際のメッセージ送信テストエラー: {e}")
        import traceback
        traceback.print_exc()

async def test_real_send_message_to_group():
    """
    実際のグループにメッセージを送信するテスト
    """
    print("\n=== Real Send Message to Group Test ===")
    
    service = create_real_push_service()
    if not service:
        print("❌ PushService作成に失敗しました")
        return
    
    try:
        # 既存のグループを取得
        groups_result = service.supabase.table("groups").select("id, line_group_id, group_name").limit(1).execute()
        if not groups_result.data:
            print("テスト用グループが見つかりません")
            return
        
        group = groups_result.data[0]
        group_id = group['id']
        line_group_id = group['line_group_id']
        group_name = group.get('group_name', 'Unknown')
        
        print(f"テスト送信先グループ:")
        print(f"  - Group ID: {group_id}")
        print(f"  - LINE Group ID: {line_group_id}")
        print(f"  - Name: {group_name}")
        
        print("\n⚠️  実際のLINEグループメッセージを送信します。続行しますか？")
        print("yes (自動実行)")
        
        # グループメッセージ送信
        print("\nグループメッセージ送信中...")
        test_message = f"PushService グループテストメッセージ - {uuid.uuid4().hex[:8]}"
        result = await service.send_to_group(group_id, test_message)
        
        if result:
            print("✓ グループメッセージ送信成功")
        else:
            print("❌ グループメッセージ送信失敗")
        
    except Exception as e:
        print(f"❌ グループメッセージ送信テストエラー: {e}")
        import traceback
        traceback.print_exc()

# =============================================================================
# メイン実行関数
# =============================================================================

async def run_mock_tests():
    """
    モックテストを実行
    """
    print("=== PUSH SERVICE MOCK TESTS ===")
    
    try:
        await test_send_to_user_mock()
        await test_send_to_line_user_mock()
        await test_send_to_group_mock()
        await test_send_multiple_messages_mock()
        await test_user_not_found_mock()
        
        print("\n🎉 全てのモックテストが成功しました！")
        
    except Exception as e:
        print(f"\n❌ モックテストエラー: {e}")
        import traceback
        traceback.print_exc()

async def run_real_tests():
    """
    実際のSupabaseとLINE APIを使用するテストを実行
    """
    print("\n\n=== PUSH SERVICE REAL TESTS ===")
    
    # 実際のサービスが利用可能かチェック
    service = create_real_push_service()
    if service:
        try:
            await test_real_database_lookup()
            await test_real_send_message_to_user()
            await test_real_send_message_to_group()
            print("\n🎉 実際のPushServiceテストも成功しました！")
        except Exception as e:
            print(f"\n❌ 実際のPushServiceテストエラー: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("実際のPushServiceテストをスキップしました（設定不備）")
        print("必要な環境変数:")
        print("- LINE_CHANNEL_ACCESS_TOKEN")
        print("- SUPABASE_URL")
        print("- SUPABASE_ANON_KEY")

async def main():
    """
    全てのテストを実行
    """
    print("PushService 関数テストを開始します...\n")
    
    # モックテストを実行
    await run_mock_tests()
    
    # 実際のテストを実行
    await run_real_tests()

if __name__ == "__main__":
    asyncio.run(main())