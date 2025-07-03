#!/usr/bin/env python3
"""
LINE User Profile API の使用例
"""
import requests
import json

def test_api_usage():
    """
    API の使用例を示す
    """
    # APIのベースURL（実際のサーバーのURLに変更してください）
    base_url = "http://localhost:8000"
    
    print("=== LINE User Profile API 使用例 ===\n")
    
    # 例1: 無効なユーザーID
    print("1. 無効なユーザーIDでのテスト:")
    invalid_user_id = "invalid_id"
    response = requests.get(f"{base_url}/api/line-user-profile/{invalid_user_id}")
    print(f"   URL: GET {base_url}/api/line-user-profile/{invalid_user_id}")
    print(f"   Response: {response.json()}")
    print()
    
    # 例2: 有効だが存在しないユーザーID
    print("2. 有効だが存在しないユーザーIDでのテスト:")
    fake_user_id = "U" + "1234567890abcdef" * 2  # 33文字の有効なフォーマット
    response = requests.get(f"{base_url}/api/line-user-profile/{fake_user_id}")
    print(f"   URL: GET {base_url}/api/line-user-profile/{fake_user_id}")
    print(f"   Response: {response.json()}")
    print()
    
    # 例3: キャッシュを強制リフレッシュ
    print("3. キャッシュを強制リフレッシュしてテスト:")
    response = requests.get(f"{base_url}/api/line-user-profile/{fake_user_id}?force_refresh=true")
    print(f"   URL: GET {base_url}/api/line-user-profile/{fake_user_id}?force_refresh=true")
    print(f"   Response: {response.json()}")
    print()
    
    print("4. 実際のユーザーIDでテストする場合:")
    print("   実際のLINE User IDを取得してください（例: Ubbadb3c6123cbf22a886969b48517655）")
    print("   curl \"http://localhost:8000/api/line-user-profile/Ubbadb3c6123cbf22a886969b48517655\"")
    print()
    
    print("=== API レスポンスの形式 ===")
    print("成功時:")
    print(json.dumps({
        "success": True,
        "data": {
            "id": "uuid",
            "line_user_id": "U1234567890abcdef...",
            "display_name": "ユーザー表示名",
            "picture_url": "https://profile.line-scdn.net/...",
            "status_message": "ステータスメッセージ",
            "language": "ja",
            "created_at": "2025-07-03T03:00:00.000000+00:00",
            "last_profile_sync": "2025-07-03T03:00:00.000000+00:00"
        }
    }, indent=2, ensure_ascii=False))
    print()
    
    print("エラー時:")
    print(json.dumps({
        "success": False,
        "error": "エラーメッセージ"
    }, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    try:
        test_api_usage()
    except requests.exceptions.ConnectionError:
        print("❌ APIサーバーに接続できません。")
        print("サーバーを起動してください: uv run uvicorn app.main:app --reload --port 8000")
    except Exception as e:
        print(f"❌ エラーが発生しました: {e}")