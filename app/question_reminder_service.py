"""
Question Reminder Service

質問に回答していないユーザーに個別メッセージを送信するサービス
"""

import logging
import json
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from app.database_service import database_service
from app.message_service import message_service
from app.ai_service import get_ai_service
import os

logger = logging.getLogger(__name__)

class QuestionReminderService:
    def __init__(self):
        self.ai_service = None
        self._initialize_ai_service()
    
    def _initialize_ai_service(self):
        """AI サービスを初期化"""
        try:
            openai_api_key = os.getenv("OPENAI_API_KEY")
            if openai_api_key:
                self.ai_service = get_ai_service(openai_api_key)
            else:
                logger.warning("OPENAI_API_KEY not found, response suggestion will be disabled")
        except Exception as e:
            logger.error(f"Error initializing AI service: {e}")
    
    async def find_inactive_users_for_questions(self, hours_threshold: int = 2, reminder_interval_hours: int = 24) -> List[Dict]:
        """
        質問投稿後に非アクティブなユーザーを検出
        
        Args:
            hours_threshold: 非アクティブと判定する時間（時間）
            reminder_interval_hours: リマインダーの再送間隔（時間）
            
        Returns:
            List[Dict]: 非アクティブユーザーの情報
        """
        try:
            # 指定時間前の時刻を計算
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_threshold)
            
            # 未回答の質問を取得
            questions_result = database_service.supabase.table("questions").select(
                "id, question_text, created_at, group_id, questioner_user_id, " +
                "groups(line_group_id, group_name), " +
                "users(line_user_id, display_name)"
            ).is_("resolved_at", "null").lt("created_at", cutoff_time.isoformat()).execute()
            
            if not questions_result.data:
                logger.info("No unanswered questions found")
                return []
            
            inactive_users = []
            
            for question in questions_result.data:
                # 質問後にアクティブでないグループメンバーを探す
                inactive_members = await self._find_inactive_group_members(
                    question['group_id'], 
                    question['created_at'],
                    question['users']['line_user_id'],
                    reminder_interval_hours
                )
                
                for member in inactive_members:
                    inactive_users.append({
                        'question_id': question['id'],
                        'question_text': question['question_text'],
                        'group_name': question['groups']['group_name'],
                        'line_group_id': question['groups']['line_group_id'],
                        'questioner_name': question['users']['display_name'],
                        'inactive_user_id': member['line_user_id'],
                        'inactive_user_name': member['display_name'],
                        'question_created_at': question['created_at']
                    })
            
            logger.info(f"Found {len(inactive_users)} inactive users for questions")
            return inactive_users
            
        except Exception as e:
            logger.error(f"Error finding inactive users for questions: {e}")
            return []
    
    async def _find_inactive_group_members(self, group_id: str, question_created_at: str, questioner_line_user_id: str, reminder_interval_hours: int = 24) -> List[Dict]:
        """
        質問投稿後に非アクティブなグループメンバーを検出
        
        Args:
            group_id: グループの内部ID
            question_created_at: 質問投稿時刻
            questioner_line_user_id: 質問者のLINE User ID（除外対象）
            reminder_interval_hours: リマインダーの再送間隔（時間）
            
        Returns:
            List[Dict]: 非アクティブメンバーの情報
        """
        try:
            # グループメンバーを取得（質問者は除外）
            members_result = database_service.supabase.table("group_members").select(
                "user_id, users(line_user_id, display_name), last_active_at"
            ).eq("group_id", group_id).execute()
            
            if not members_result.data:
                return []
            
            inactive_members = []
            reminder_cutoff_time = datetime.now(timezone.utc) - timedelta(hours=reminder_interval_hours)
            
            for member in members_result.data:
                user_data = member['users']
                last_active = member['last_active_at']
                
                # 質問者は除外
                if user_data['line_user_id'] == questioner_line_user_id:
                    continue
                
                # 最後のアクティビティが質問投稿前の場合は非アクティブ
                is_inactive = False
                
                if not last_active or last_active < question_created_at:
                    is_inactive = True
                else:
                    # 質問投稿後にメッセージを送信していないかチェック
                    messages_result = database_service.supabase.table("messages").select("id").eq(
                        "group_id", group_id
                    ).eq("user_id", member['user_id']).gt("created_at", question_created_at).limit(1).execute()
                    
                    if not messages_result.data:
                        is_inactive = True
                
                if is_inactive:
                    # 既にリマインダーを送信済みか確認
                    should_send_reminder = await self._should_send_reminder(
                        member['user_id'], 
                        reminder_cutoff_time
                    )
                    
                    if should_send_reminder:
                        inactive_members.append({
                            'line_user_id': user_data['line_user_id'],
                            'display_name': user_data['display_name'],
                            'last_active_at': last_active
                        })
            
            return inactive_members
            
        except Exception as e:
            logger.error(f"Error finding inactive group members: {e}")
            return []
    
    async def _should_send_reminder(self, user_id: str, reminder_cutoff_time: datetime) -> bool:
        """
        リマインダーを送信すべきかどうかを判定
        
        Args:
            user_id: ユーザーの内部ID
            reminder_cutoff_time: リマインダー送信のカットオフ時刻
            
        Returns:
            bool: リマインダーを送信すべきかどうか
        """
        try:
            # 最後のリマインダー送信時刻を取得
            last_reminder_result = database_service.supabase.table("question_targets").select(
                "reminded_at"
            ).eq("target_user_id", user_id).order("reminded_at", desc=True).limit(1).execute()
            
            if not last_reminder_result.data:
                # 一度もリマインダーを送信していない場合は送信
                return True
            
            last_reminded_at = last_reminder_result.data[0]['reminded_at']
            
            if not last_reminded_at:
                # reminded_atがnullの場合は送信
                return True
            
            # 最後のリマインダー送信時刻がカットオフ時刻より前の場合は送信
            # タイムゾーン情報を適切に処理
            if last_reminded_at.endswith('Z'):
                last_reminded_at = last_reminded_at.replace('Z', '+00:00')
            elif '+' not in last_reminded_at and 'T' in last_reminded_at:
                last_reminded_at = last_reminded_at + '+00:00'
            
            last_reminded_datetime = datetime.fromisoformat(last_reminded_at)
            return last_reminded_datetime < reminder_cutoff_time
            
        except Exception as e:
            logger.error(f"Error checking should send reminder: {e}")
            # エラーの場合はリマインダーを送信
            return True
    
    async def generate_response_suggestion(self, question_text: str, group_name: str, questioner_name: str) -> str:
        """
        AIを使用して回答候補を生成
        
        Args:
            question_text: 質問文
            group_name: グループ名
            questioner_name: 質問者名
            
        Returns:
            str: 回答候補
        """
        if not self.ai_service:
            return "申し訳ございません。回答候補の生成機能が利用できません。"
        
        try:
            prompt = f"""
以下の質問に対して、適切な回答候補を提案してください。

グループ名: {group_name}
質問者: {questioner_name}さん
質問内容: "{question_text}"

回答候補を以下の形式で3つ提案してください：
1. 具体的で実用的な回答
2. 質問者に詳細を確認する回答
3. 他のメンバーに意見を求める回答

各回答候補は簡潔で、グループチャットで使いやすい形式にしてください。
"""
            
            response = await self.ai_service.quick_call(prompt)
            return response
            
        except Exception as e:
            logger.error(f"Error generating response suggestion: {e}")
            return "申し訳ございません。回答候補の生成中にエラーが発生しました。"
    
    async def send_individual_reminder(self, inactive_user_info: Dict) -> bool:
        """
        個別ユーザーに質問リマインダーを送信
        
        Args:
            inactive_user_info: 非アクティブユーザーの情報
            
        Returns:
            bool: 送信成功の可否
        """
        try:
            # 回答候補を生成
            response_suggestion = await self.generate_response_suggestion(
                inactive_user_info['question_text'],
                inactive_user_info['group_name'],
                inactive_user_info['questioner_name']
            )
            
            # リマインダーメッセージを作成
            reminder_message = f"""🔔 未回答の質問があります

グループ: {inactive_user_info['group_name']}
質問者: {inactive_user_info['questioner_name']}さん

質問: {inactive_user_info['question_text']}

💡 回答候補:
{response_suggestion}

お時間のある時にグループで回答していただけますと幸いです。"""
            
            # 個別メッセージを送信
            success = await message_service.send_message_to_user(
                inactive_user_info['inactive_user_id'],
                reminder_message
            )
            
            if success:
                logger.info(f"Reminder sent to {inactive_user_info['inactive_user_name']} for question {inactive_user_info['question_id']}")
                # 送信記録を保存
                await self._record_reminder_sent(inactive_user_info)
            else:
                logger.error(f"Failed to send reminder to {inactive_user_info['inactive_user_name']}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error sending individual reminder: {e}")
            return False
    
    async def _record_reminder_sent(self, inactive_user_info: Dict):
        """
        リマインダー送信記録を保存
        
        Args:
            inactive_user_info: 非アクティブユーザーの情報
        """
        try:
            # question_targetsテーブルにリマインダー送信記録を保存
            user_uuid = await database_service._ensure_user_exists(inactive_user_info['inactive_user_id'])
            
            # 既存のtargetレコードを探す
            existing_target = database_service.supabase.table("question_targets").select("*").eq(
                "question_id", inactive_user_info['question_id']
            ).eq("target_user_id", user_uuid).execute()
            
            if existing_target.data:
                # 既存レコードのreminded_atを更新
                database_service.supabase.table("question_targets").update({
                    "reminded_at": datetime.now(timezone.utc).isoformat()
                }).eq("id", existing_target.data[0]['id']).execute()
            else:
                # 新規レコードを作成
                database_service.supabase.table("question_targets").insert({
                    "question_id": inactive_user_info['question_id'],
                    "target_user_id": user_uuid,
                    "reminded_at": datetime.now(timezone.utc).isoformat()
                }).execute()
                
        except Exception as e:
            logger.error(f"Error recording reminder sent: {e}")
    
    async def process_all_inactive_users(self, hours_threshold: int = 2, reminder_interval_hours: int = 24) -> Dict:
        """
        すべての非アクティブユーザーに質問リマインダーを送信
        
        Args:
            hours_threshold: 非アクティブと判定する時間（時間）
            reminder_interval_hours: リマインダーの再送間隔（時間）
            
        Returns:
            Dict: 処理結果の統計
        """
        try:
            # 非アクティブユーザーを検出
            inactive_users = await self.find_inactive_users_for_questions(hours_threshold, reminder_interval_hours)
            
            if not inactive_users:
                logger.info("No inactive users found for question reminders")
                return {
                    "total_inactive_users": 0,
                    "reminders_sent": 0,
                    "reminders_failed": 0
                }
            
            # 各ユーザーにリマインダーを送信
            sent_count = 0
            failed_count = 0
            
            for user_info in inactive_users:
                success = await self.send_individual_reminder(user_info)
                if success:
                    sent_count += 1
                else:
                    failed_count += 1
            
            result = {
                "total_inactive_users": len(inactive_users),
                "reminders_sent": sent_count,
                "reminders_failed": failed_count
            }
            
            logger.info(f"Question reminder processing completed: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Error processing all inactive users: {e}")
            return {
                "total_inactive_users": 0,
                "reminders_sent": 0,
                "reminders_failed": 0,
                "error": str(e)
            }

# シングルトンインスタンス
question_reminder_service = QuestionReminderService()