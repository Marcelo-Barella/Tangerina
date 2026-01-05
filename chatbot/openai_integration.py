import logging
import asyncio
from typing import Optional, Dict, Any, List
from openai import OpenAI
from chatbot.model_helper import BaseChatbot

logger = logging.getLogger(__name__)


class OpenAIChatbot(BaseChatbot):
    def __init__(self, api_key: str, bot_instance=None, music_bot_instance=None, memory_manager=None):
        super().__init__(api_key, bot_instance, music_bot_instance, memory_manager)
        logger.info("OpenAI chatbot initialized")

    def _initialize_client(self, api_key: str):
        self.client = OpenAI(api_key=api_key)

    def _get_models_to_try(self) -> List[str]:
        return ['gpt-4o-mini']

    def _make_sync_api_request(self, model_name: str, messages: List[Dict],
                               max_tokens: int, tools: Optional[List]) -> Any:
        return self.client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=0.7,
            max_tokens=max_tokens,
            tools=tools
        )

    async def _make_api_request(self, messages: List[Dict], max_tokens: int = 1000, tools: Optional[List] = None):
        models_to_try = self._get_models_to_try()
        last_error = None
        
        for model_name in models_to_try:
            try:
                response = await asyncio.to_thread(
                    self._make_sync_api_request,
                    model_name,
                    messages,
                    max_tokens,
                    tools
                )
                return response
            except Exception as api_error:
                last_error = api_error
                continue
        
        raise last_error if last_error else Exception("All model names failed")

    def _extract_tool_calls(self, choice) -> List[Any]:
        if hasattr(choice, "message") and hasattr(choice.message, "tool_calls"):
            return choice.message.tool_calls or []
        return []

    def _extract_choice_content(self, choice) -> str:
        if hasattr(choice, "message") and hasattr(choice.message, "content"):
            content = choice.message.content
            return str(content) if content else ""
        return ""
