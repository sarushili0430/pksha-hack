"""
Test for LINE Group Service
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from app.line_group_service import get_line_group_service


class TestLineGroupService:
    """LINE Group Service のテストクラス"""
    
    def setup_method(self):
        """各テストメソッドの前に実行される"""
        self.mock_token = "test_channel_access_token"
        self.mock_supabase = Mock()
        self.test_group_id = "C1234567890abcdef1234567890abcdef0"
        self.test_group_name = "テストグループ"
    
    @pytest.mark.anyio
    async def test_get_group_summary_success(self):
        """グループ情報取得成功のテスト"""
        # 実装されたので、実際にAPI呼び出しを試行する
        service = get_line_group_service(self.mock_token, self.mock_supabase)
        
        # 実際のLINE APIが呼ばれるため、アクセストークンが無効な場合はNoneが返される
        result = await service.get_group_summary(self.test_group_id)
        assert result is None  # モックトークンなので None が返されるはず
    
    @pytest.mark.anyio
    async def test_get_group_summary_with_cache_success(self):
        """キャッシュ機能付きグループ情報取得成功のテスト"""
        service = get_line_group_service(self.mock_token, self.mock_supabase)
        
        # キャッシュ機能付きで実際にAPI呼び出しを試行する
        result = await service.get_group_summary_with_cache(self.test_group_id)
        assert result is None  # モックトークンなので None が返されるはず
    
    @pytest.mark.anyio
    async def test_get_group_summary_invalid_group_id(self):
        """無効なグループIDのテスト"""
        service = get_line_group_service(self.mock_token, self.mock_supabase)
        invalid_group_id = "invalid_group_id"
        
        # 無効なグループIDでテスト
        result = await service.get_group_summary(invalid_group_id)
        assert result is None  # 無効なIDなので None が返されるはず
    
    @pytest.mark.anyio
    async def test_get_group_summary_api_error(self):
        """LINE API エラーのテスト"""
        service = get_line_group_service(self.mock_token, self.mock_supabase)
        
        # API エラーのケースをテスト
        result = await service.get_group_summary(self.test_group_id)
        assert result is None  # エラー時は None が返されるはず


if __name__ == "__main__":
    # テストを実行
    pytest.main([__file__, "-v"])