"""
Question Detection and Management Service

This service detects questions in messages using LLM and manages question tracking
with reminders for unanswered questions.
"""

import json
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timezone, timedelta
from supabase import Client
from app.ai_service import AIService


class QuestionService:
    """
    Question detection and management service
    
    Detects questions in messages using LLM and manages question tracking
    with automatic reminders for unanswered questions.
    """
    
    def __init__(self, supabase_client: Client, ai_service: AIService):
        """
        Initialize QuestionService
        
        Args:
            supabase_client: Supabase client instance
            ai_service: AI service for LLM calls
        """
        self.supabase = supabase_client
        self.ai_service = ai_service
        self.default_remind_seconds = 30  # ハッカソン用: 30秒でリマインド
    
    async def detect_question_and_targets(
        self, 
        message_text: str, 
        group_id: str
    ) -> Optional[Tuple[bool, List[str], str]]:
        """
        Detect if message contains a question and identify targets
        
        Args:
            message_text: The message text to analyze
            group_id: Group ID for context
            
        Returns:
            Tuple of (is_question, target_user_ids, question_content) or None if not a question
        """
        try:
            # Get group members for context
            group_members = await self._get_group_members(group_id)
            member_info = ", ".join([f"{m['line_user_id']}" for m in group_members])
            
            prompt = f"""
あなたは質問検出の専門家です。以下のメッセージを分析してください。

【グループメンバー情報】
{member_info}

【メッセージ】
{message_text}

このメッセージが以下の条件を満たす場合のみ、JSONで結果を返してください：
1. 質問や提案など、他の人からの返答を求めている
2. 特定の人またはグループ全体に向けられている

条件を満たす場合：
{{
  "is_question": true,
  "question_content": "質問内容の要約",
  "targets": ["全員" または "特定のユーザーID"],
  "target_type": "all" | "specific"
}}

条件を満たさない場合：
{{
  "is_question": false
}}

注意：
- 「みんな」「全員」「誰か」などは target_type: "all" とする
- 単純な感想や独り言は質問ではない
- 明確に返答を求めていない場合は質問ではない
"""
            
            response = await self.ai_service.quick_call(prompt)
            
            try:
                data = json.loads(response.strip())
                
                if not data.get("is_question"):
                    return None
                
                is_question = True
                question_content = data.get("question_content", message_text)
                target_type = data.get("target_type", "all")
                
                # Determine target user IDs
                target_user_ids = []
                if target_type == "all":
                    # Target all group members
                    target_user_ids = [member["id"] for member in group_members]
                else:
                    # Target specific users (this would need more sophisticated parsing)
                    # For now, default to all members if specific targets aren't clear
                    target_user_ids = [member["id"] for member in group_members]
                
                return (is_question, target_user_ids, question_content)
                
            except (json.JSONDecodeError, KeyError) as e:
                print(f"Failed to parse question detection response: {e}")
                print(f"Response was: {response}")
                return None
                
        except Exception as e:
            print(f"Error in question detection: {e}")
            return None
    
    async def create_question_record(
        self,
        group_id: str,
        questioner_user_id: str,
        question_text: str,
        target_user_ids: List[str],
        message_id: str,
        remind_seconds: Optional[int] = None
    ) -> Optional[str]:
        """
        Create question record in database
        
        Args:
            group_id: Group ID where question was asked
            questioner_user_id: User ID who asked the question
            question_text: The question text
            target_user_ids: List of user IDs who should respond
            message_id: LINE message ID for reference
            remind_seconds: Seconds to wait before reminder (default: 30)
            
        Returns:
            Question ID if created successfully, None otherwise
        """
        try:
            # Remove questioner from targets to avoid self-reminders
            filtered_targets = [uid for uid in target_user_ids if uid != questioner_user_id]
            
            if not filtered_targets:
                print("No valid targets for question (all targets were the questioner)")
                return None
            
            remind_at = datetime.now(timezone.utc) + timedelta(seconds=remind_seconds or self.default_remind_seconds)
            
            # Create question record
            question_data = {
                "group_id": group_id,
                "questioner_user_id": questioner_user_id,
                "question_text": question_text,
                "message_id": message_id,
                "remind_at": remind_at.isoformat(),
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            question_result = self.supabase.table("questions").insert(question_data).execute()
            
            if not question_result.data:
                print("Failed to create question record")
                return None
            
            question_id = question_result.data[0]["id"]
            
            # Create question target records
            target_records = []
            for target_user_id in filtered_targets:
                target_records.append({
                    "question_id": question_id,
                    "target_user_id": target_user_id,
                    "created_at": datetime.now(timezone.utc).isoformat()
                })
            
            if target_records:
                self.supabase.table("question_targets").insert(target_records).execute()
                print(f"Created question with {len(target_records)} targets")
            
            return question_id
            
        except Exception as e:
            print(f"Error creating question record: {e}")
            return None
    
    async def check_for_responses(self, question_id: str) -> bool:
        """
        Check if targets have responded to a question
        
        Args:
            question_id: Question ID to check
            
        Returns:
            True if responses were found and marked, False otherwise
        """
        try:
            # Get question details
            question_result = self.supabase.table("questions").select("*").eq("id", question_id).execute()
            
            if not question_result.data:
                return False
            
            question = question_result.data[0]
            
            # Get unresponded targets
            targets_result = self.supabase.table("question_targets").select("*").eq("question_id", question_id).is_("responded_at", "null").execute()
            
            if not targets_result.data:
                return True  # All targets have already responded
            
            # Get messages after the question was asked
            messages_result = self.supabase.table("messages").select("*").eq("group_id", question["group_id"]).gt("created_at", question["created_at"]).order("created_at").execute()
            
            if not messages_result.data:
                return False  # No messages after question
            
            # Check if any target has sent a message (indicating response)
            target_user_ids = [target["target_user_id"] for target in targets_result.data]
            responding_users = set()
            
            for message in messages_result.data:
                if message["user_id"] in target_user_ids:
                    responding_users.add(message["user_id"])
            
            # Mark responding users as responded
            if responding_users:
                now = datetime.now(timezone.utc).isoformat()
                for user_id in responding_users:
                    self.supabase.table("question_targets").update({
                        "responded_at": now
                    }).eq("question_id", question_id).eq("target_user_id", user_id).execute()
                
                print(f"Marked {len(responding_users)} users as responded to question {question_id}")
            
            # Check if all targets have now responded
            remaining_targets = self.supabase.table("question_targets").select("id").eq("question_id", question_id).is_("responded_at", "null").execute()
            
            if not remaining_targets.data:
                # All targets have responded, mark question as resolved
                self.supabase.table("questions").update({
                    "resolved_at": datetime.now(timezone.utc).isoformat()
                }).eq("id", question_id).execute()
                
                print(f"Question {question_id} resolved - all targets have responded")
                return True
            
            return len(responding_users) > 0
            
        except Exception as e:
            print(f"Error checking for responses: {e}")
            return False
    
    async def _get_group_members(self, group_id: str) -> List[Dict]:
        """
        Get all members of a group
        
        Args:
            group_id: Group ID
            
        Returns:
            List of group members with user info
        """
        try:
            result = self.supabase.table("group_members").select("user_id, users(id, line_user_id)").eq("group_id", group_id).execute()
            
            members = []
            for row in result.data:
                if row.get("users"):
                    members.append({
                        "id": row["users"]["id"],
                        "line_user_id": row["users"]["line_user_id"]
                    })
            
            return members
            
        except Exception as e:
            print(f"Error getting group members: {e}")
            return []


# Singleton instance
_question_service: Optional[QuestionService] = None

def get_question_service(supabase_client: Client, ai_service: AIService) -> QuestionService:
    """
    Get QuestionService singleton instance
    
    Args:
        supabase_client: Supabase client
        ai_service: AI service instance
        
    Returns:
        QuestionService instance
    """
    global _question_service
    if _question_service is None:
        _question_service = QuestionService(supabase_client, ai_service)
    return _question_service