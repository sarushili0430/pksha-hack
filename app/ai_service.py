"""
AI/LLM関連のサービスモジュール

LangChain + OpenAI GPT-4を使用した応答生成機能を提供します。
履歴付きの会話生成に対応しています。
"""

# ---------- ai_service.py ----------

import os
import asyncio
from typing import Optional
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.chains import LLMChain

class AIService:
    def __init__(self, openai_api_key: str):
        self.openai_api_key = openai_api_key
        self._setup_llm()
        self._setup_prompt()
        self._setup_chain()

    def _setup_llm(self):
        self.llm = ChatOpenAI(
            model_name="gpt-4.1-2025-04-14",
            temperature=0.7,
            openai_api_key=self.openai_api_key
        )

    def _setup_prompt(self):
        system_prompt = "あなたは親切なアシスタントです。以下の会話履歴を踏まえて、適切に返信してください。"
        self.prompt = ChatPromptTemplate.from_template(
            system_prompt + "\n\n" +
            "【会話履歴】\n{history}\n\n" +
            "【新しい発言】\n{input}\n\n" +
            "アシスタント:"
        )

    def _setup_chain(self):
        self.chat_chain = LLMChain(llm=self.llm, prompt=self.prompt)

    async def generate_response_async(self, user_text: str, history: str = "") -> str:
        try:
            inputs = {"history": history, "input": user_text}
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, self.chat_chain.invoke, inputs)
            return response["text"]
        except Exception as e:
            print(f"Error generating response: {e}")
            return "申し訳ございません。応答の生成に失敗しました。"

    # ★ADD: ダイレクト呼び出し用
    async def quick_call(self, prompt: str) -> str:
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(None, self.llm.invoke, prompt)
        return resp.content

# シングルトン取得
_ai_service: Optional[AIService] = None

def get_ai_service(openai_api_key: str) -> AIService:
    global _ai_service
    if _ai_service is None:
        _ai_service = AIService(openai_api_key)
    return _ai_service
