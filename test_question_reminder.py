#!/usr/bin/env python3
"""
Test script for question reminder functionality
"""

import asyncio
import logging
from app.question_reminder_service import question_reminder_service

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_question_reminder_service():
    """Test the question reminder service"""
    logger.info("Testing question reminder service...")
    
    try:
        # Test 1: Check for inactive users
        logger.info("Test 1: Finding inactive users for questions...")
        inactive_users = await question_reminder_service.find_inactive_users_for_questions(hours_threshold=2)
        logger.info(f"Found {len(inactive_users)} inactive users")
        
        # Test 2: Test AI response generation
        logger.info("Test 2: Testing AI response generation...")
        if inactive_users:
            sample_question = inactive_users[0]
            response = await question_reminder_service.generate_response_suggestion(
                sample_question.get('question_text', 'テストの質問'),
                sample_question.get('group_name', 'テストグループ'),
                sample_question.get('questioner_name', 'テストユーザー')
            )
            logger.info(f"Generated response: {response[:100]}...")
        
        # Test 3: Get status without sending messages
        logger.info("Test 3: Getting question reminder status...")
        status = {
            "inactive_users_count": len(inactive_users),
            "sample_inactive_users": inactive_users[:3] if inactive_users else []
        }
        logger.info(f"Status: {status}")
        
        return True
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        return False

async def main():
    """Main test function"""
    logger.info("Starting question reminder service tests...")
    
    success = await test_question_reminder_service()
    
    if success:
        logger.info("All tests passed!")
    else:
        logger.error("Tests failed!")
    
    return success

if __name__ == "__main__":
    asyncio.run(main())