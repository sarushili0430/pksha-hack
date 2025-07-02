"""
AI/LLM関連のサービスモジュール

LangChain + OpenAI GPT-4を使用した応答生成機能を提供します。
履歴付きの会話生成に対応しています。
"""

import os
import asyncio
from typing import Dict, Optional
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.chains import LLMChain


class AIService:
    """
    AI応答生成サービス
    
    OpenAI GPT-4を使用して、履歴付きの会話応答を生成します。
    """
    
    def __init__(self, openai_api_key: str):
        """
        AIServiceを初期化
        
        Args:
            openai_api_key: OpenAI APIキー
        """
        self.openai_api_key = openai_api_key
        self._setup_llm()
        self._setup_prompt()
        self._setup_chain()
    
    def _setup_llm(self):
        """LLMモデルの設定"""
        self.llm = ChatOpenAI(
            model_name="gpt-4.1-2025-04-14",
            temperature=0.7,
            openai_api_key=self.openai_api_key
        )
    
    def _setup_prompt(self):
        """プロンプトテンプレートの設定（履歴対応）"""
        system_prompt = "あなたは親切なアシスタントです。以下の会話履歴を踏まえて、適切に返信してください。"
        
        # "history" と "input" の両方をテンプレートで受け取る
        self.prompt = ChatPromptTemplate.from_template(
            system_prompt + "\n\n" +
            "【会話履歴】\n" +
            "{history}\n\n" +
            "【新しい発言】\n" +
            "{input}\n\n" +
            "アシスタント:"
        )
    
    def _setup_chain(self):
        """LangChainチェーンの設定"""
        self.chat_chain = LLMChain(llm=self.llm, prompt=self.prompt)
    
    async def generate_response_async(self, user_text: str, history: str = "") -> str:
        """
        履歴付きで非同期にAI応答を生成
        
        Args:
            user_text: ユーザーの最新メッセージ
            history: 過去の会話履歴（空文字なら履歴なし）
            
        Returns:
            AI生成の応答テキスト
        """
        try:
            context_input = {
                "history": history,
                "input": user_text
            }
            
            # LangChainの同期処理を非同期で実行
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                self.chat_chain.invoke,
                context_input
            )
            
            reply_text = response["text"]
            print(f"Generated reply: {reply_text}")
            return reply_text
            
        except Exception as e:
            print(f"Error generating response: {e}")
            return "申し訳ございません。応答の生成に失敗しました。"
    
    def generate_response_sync(self, user_text: str, history: str = "") -> str:
        """
        履歴付きで同期的にAI応答を生成（デバッグ用）
        
        Args:
            user_text: ユーザーの最新メッセージ
            history: 過去の会話履歴
            
        Returns:
            AI生成の応答テキスト
        """
        try:
            context_input = {
                "history": history,
                "input": user_text
            }
            
            response = self.chat_chain.invoke(context_input)
            return response["text"]
            
        except Exception as e:
            print(f"Error generating response: {e}")
            return "申し訳ございません。応答の生成に失敗しました。"


# シングルトンインスタンス（main.pyで使用）
_ai_service: Optional[AIService] = None

def get_ai_service(openai_api_key: str) -> AIService:
    """
    AIServiceのシングルトンインスタンスを取得
    
    Args:
        openai_api_key: OpenAI APIキー
        
    Returns:
        AIServiceインスタンス
    """
    global _ai_service
    if _ai_service is None:
        _ai_service = AIService(openai_api_key)
    return _ai_service 