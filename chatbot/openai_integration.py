import logging
import asyncio
import os
from typing import Optional, Dict, Any, List
from openai import OpenAI
from chatbot.model_helper import BaseChatbot

logger = logging.getLogger(__name__)


class OpenAIChatbot(BaseChatbot):
    def __init__(self, api_key: str, bot_instance=None, music_bot_instance=None, memory_manager=None, web_search_service=None):
        super().__init__(api_key, bot_instance, music_bot_instance, memory_manager, web_search_service)
        logger.info("OpenAI chatbot initialized")

    def _initialize_client(self, api_key: str):
        self.client = OpenAI(api_key=api_key)

    def _get_models_to_try(self) -> List[str]:
        model = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
        return [model]

    def _make_sync_api_request(self, model_name: str, messages: List[Dict],
                               max_tokens: int, tools: Optional[List]) -> Any:
        return self.client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=0.7,
            max_tokens=max_tokens,
            tools=tools or None
        )

    async def _make_api_request(self, messages: List[Dict], max_tokens: int = 1000, tools: Optional[List] = None):
        for model_name in self._get_models_to_try():
            try:
                return await asyncio.to_thread(self._make_sync_api_request, model_name, messages, max_tokens, tools)
            except Exception as error:
                last_error = error
        raise last_error or Exception("All model names failed")

    def _extract_tool_calls(self, choice) -> List[Any]:
        return getattr(getattr(choice, "message", None), "tool_calls", None) or []

    def _extract_choice_content(self, choice) -> str:
        return str(getattr(getattr(choice, "message", None), "content", "") or "")
