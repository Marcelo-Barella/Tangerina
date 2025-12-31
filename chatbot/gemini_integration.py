import logging
import asyncio
import json
from typing import Optional, Dict, Any, List, Tuple
from google import genai
from google.genai import types
from chatbot.model_helper import BaseChatbot
from chatbot.model_helper import _normalize_integer_ids

logger = logging.getLogger(__name__)


def convert_messages_to_gemini_format(messages: List[Dict]) -> List[types.Content]:
    gemini_contents = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content")
        
        role_map = {
            "system": "user",
            "assistant": "model",
            "user": "user",
            "tool": "function"
        }
        gemini_role = role_map.get(role, "user")
        
        parts = []
        if role == "tool":
            tool_name = msg.get("name", "")
            if content is not None:
                try:
                    tool_response = json.loads(content) if isinstance(content, str) else content
                    if isinstance(tool_response, dict):
                        parts.append(types.Part.from_function_response(
                            name=tool_name,
                            response=tool_response
                        ))
                except json.JSONDecodeError:
                    parts.append(types.Part.from_function_response(
                        name=tool_name,
                        response={"error": str(content)}
                    ))
        else:
            if content is not None:
                if isinstance(content, str) and content.strip():
                    parts.append(types.Part.from_text(text=content))
                elif isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            parts.append(types.Part.from_text(text=part.get("text", "")))
            
            if "tool_calls" in msg and msg["tool_calls"]:
                for tool_call in msg["tool_calls"]:
                    func_info = tool_call.get("function", {})
                    func_name = func_info.get("name", "")
                    func_args_str = func_info.get("arguments", "{}")
                    try:
                        func_args = json.loads(func_args_str) if isinstance(func_args_str, str) else func_args_str
                    except json.JSONDecodeError:
                        func_args = {}
                    parts.append(types.Part.from_function_call(name=func_name, args=func_args))
        
        if parts:
            gemini_contents.append(types.Content(role=gemini_role, parts=parts))
    
    return gemini_contents


def convert_tools_to_gemini_format(tools: List[Dict]) -> List[types.Tool]:
    if not tools:
        return []
    
    function_declarations = []
    for tool in tools:
        if tool.get("type") != "function":
            continue
            
        func_def = tool.get("function", {})
        func_name = func_def.get("name", "")
        func_desc = func_def.get("description", "")
        func_params = func_def.get("parameters", {})
        
        properties = {}
        required = []
        
        if isinstance(func_params, dict):
            props = func_params.get("properties", {})
            required = func_params.get("required", [])
            
            for param_name, param_spec in props.items():
                param_type = param_spec.get("type", "STRING").upper()
                param_desc = param_spec.get("description", "")
                
                type_map = {
                    "INTEGER": types.Type.INTEGER,
                    "NUMBER": types.Type.NUMBER,
                    "BOOLEAN": types.Type.BOOLEAN,
                    "ARRAY": types.Type.ARRAY,
                    "OBJECT": types.Type.OBJECT
                }
                schema_type = type_map.get(param_type, types.Type.STRING)
                
                schema_dict = {"type": schema_type.value}
                if param_desc:
                    schema_dict["description"] = param_desc
                properties[param_name] = types.Schema(**schema_dict)
        
        schema_dict = {"type": types.Type.OBJECT.value, "properties": properties}
        if required:
            schema_dict["required"] = required
        schema = types.Schema(**schema_dict)
        
        function_declaration = types.FunctionDeclaration(
            name=func_name,
            description=func_desc,
            parameters=schema
        )
        function_declarations.append(function_declaration)
    
    return [types.Tool(function_declarations=function_declarations)] if function_declarations else []


class NormalizedToolCall:
    def __init__(self, part=None, func_call=None):
        if part and hasattr(part, "function_call"):
            func_call = part.function_call
        
        if func_call:
            try:
                self.id = getattr(func_call, "name", None) or ""
                self.type = "function"
                self.function = NormalizedFunction(func_call)
            except (AttributeError, Exception):
                self.id = None
                self.type = "function"
                self.function = None
        else:
            self.id = None
            self.type = "function"
            self.function = None
    
    @classmethod
    def from_function_call(cls, func_call):
        return cls(func_call=func_call)


class NormalizedFunction:
    def __init__(self, func_call):
        try:
            if func_call is None:
                self.name = ""
                self.arguments = "{}"
                return
            
            self.name = getattr(func_call, "name", "") if func_call else ""
            
            if func_call and hasattr(func_call, "args"):
                args = func_call.args
                if args is None:
                    self.arguments = "{}"
                elif isinstance(args, dict):
                    try:
                        self.arguments = json.dumps(args)
                    except (TypeError, ValueError):
                        self.arguments = "{}"
                else:
                    self.arguments = "{}"
            else:
                self.arguments = "{}"
        except (AttributeError, Exception):
            self.name = ""
            self.arguments = "{}"


def normalize_gemini_response_to_openai_like(response: Any) -> Any:
    class NormalizedResponse:
        def __init__(self, gemini_response):
            self.choices = []
            try:
                if hasattr(gemini_response, "candidates") and gemini_response.candidates:
                    candidate = gemini_response.candidates[0]
                    choice = NormalizedChoice(candidate, gemini_response)
                    self.choices = [choice]
            except (AttributeError, IndexError, Exception):
                self.choices = []
    
    class NormalizedChoice:
        def __init__(self, candidate, gemini_response):
            self.candidate = candidate
            self.gemini_response = gemini_response
            try:
                self.finish_reason = str(candidate.finish_reason).lower() if getattr(candidate, "finish_reason", None) else None
            except (AttributeError, Exception):
                self.finish_reason = None
            self.message = NormalizedMessage(candidate, gemini_response)
    
    class NormalizedMessage:
        def __init__(self, candidate, gemini_response):
            self.candidate = candidate
            self.gemini_response = gemini_response
            self.content = None
            self.tool_calls = []
            
            tool_call_names_seen = set()
            
            try:
                if hasattr(candidate, "content") and candidate.content:
                    if hasattr(candidate.content, "parts") and candidate.content.parts:
                        text_parts = []
                        for part in candidate.content.parts:
                            try:
                                if hasattr(part, "text") and part.text:
                                    text_parts.append(part.text)
                                elif hasattr(part, "function_call") and part.function_call:
                                    tool_call = NormalizedToolCall(part)
                                    if tool_call.function:
                                        tool_name = tool_call.function.name
                                        tool_id = f"{tool_name}_{tool_call.function.arguments}"
                                        if tool_id not in tool_call_names_seen:
                                            self.tool_calls.append(tool_call)
                                            tool_call_names_seen.add(tool_id)
                            except (AttributeError, Exception):
                                continue
                        
                        if text_parts:
                            self.content = " ".join(text_parts)
            except (AttributeError, Exception):
                pass
            
            if not self.tool_calls:
                try:
                    if hasattr(gemini_response, "function_calls") and gemini_response.function_calls:
                        for func_call in gemini_response.function_calls:
                            try:
                                tool_call = NormalizedToolCall.from_function_call(func_call)
                                if tool_call.function:
                                    tool_name = tool_call.function.name
                                    tool_id = f"{tool_name}_{tool_call.function.arguments}"
                                    if tool_id not in tool_call_names_seen:
                                        self.tool_calls.append(tool_call)
                                        tool_call_names_seen.add(tool_id)
                            except (AttributeError, Exception):
                                continue
                except (AttributeError, Exception):
                    pass
    
    return NormalizedResponse(response)


class GeminiChatbot(BaseChatbot):
    def __init__(self, api_key: str, bot_instance=None, music_bot_instance=None):
        super().__init__(api_key, bot_instance, music_bot_instance)
    
    def _initialize_client(self, api_key: str):
        self.client = genai.Client(api_key=api_key)
    
    def _get_models_to_try(self) -> List[str]:
        return ['gemini-2.5-flash-lite', 'gemini-2.0-flash-exp']
    
    def _make_sync_api_request(self, model_name: str, messages: List[Dict],
                               max_tokens: int, tools: Optional[List]) -> Any:
        gemini_contents = convert_messages_to_gemini_format(messages)
        gemini_tools = convert_tools_to_gemini_format(tools) if tools else None
        
        config = types.GenerateContentConfig(
            max_output_tokens=max_tokens,
            temperature=0.7,
            tools=gemini_tools if gemini_tools else None
        )
        
        response = self.client.models.generate_content(
            model=model_name,
            contents=gemini_contents,
            config=config
        )
        
        return normalize_gemini_response_to_openai_like(response)
    
    async def _make_api_request(self, messages: List[Dict], max_tokens: int = 1000, tools: Optional[List] = None):
        models_to_try = self._get_models_to_try()
        last_error = None
        errors_by_model = []
        
        for model_name in models_to_try:
            try:
                response = await asyncio.to_thread(
                    self._make_sync_api_request,
                    model_name,
                    messages,
                    max_tokens,
                    tools
                )
                if model_name != models_to_try[0]:
                    logger.info(f"Using fallback model {model_name} instead of {models_to_try[0]}")
                return response
            except Exception as api_error:
                errors_by_model.append(f"{model_name}: {api_error}")
                last_error = api_error
                continue
        
        all_errors = "; ".join(errors_by_model)
        final_error_msg = f"All models failed. Errors: {all_errors}"
        logger.error(final_error_msg)
        raise Exception(final_error_msg) if not last_error else last_error
    
    def _extract_tool_calls(self, choice) -> List[Any]:
        if hasattr(choice, "message") and hasattr(choice.message, "tool_calls"):
            tool_calls = choice.message.tool_calls
            if tool_calls:
                return tool_calls
        
        if hasattr(choice, "candidate") and hasattr(choice.candidate, "content"):
            candidate = choice.candidate
            if hasattr(candidate.content, "parts") and candidate.content.parts:
                tool_calls = []
                for part in candidate.content.parts:
                    if hasattr(part, "function_call") and part.function_call:
                        class DirectFunctionCall:
                            def __init__(self, func_call):
                                self.function_call = func_call
                        tool_calls.append(DirectFunctionCall(part.function_call))
                if tool_calls:
                    return tool_calls
        
        return []
    
    def _parse_tool_call(self, tool_call) -> Optional[Tuple[str, Dict[str, Any]]]:
        func_call = None
        
        if hasattr(tool_call, "function_call"):
            func_call = tool_call.function_call
        elif hasattr(tool_call, "function"):
            func_info = tool_call.function
            if hasattr(func_info, "name") and hasattr(func_info, "args"):
                func_call = func_info
        
        if func_call:
            tool_name = getattr(func_call, "name", None)
            if hasattr(func_call, "args"):
                args = func_call.args
                if tool_name and isinstance(args, dict):
                    normalized_params = _normalize_integer_ids(tool_name, args, self._tool_mapping)
                    return tool_name, normalized_params
                elif tool_name:
                    return tool_name, {}
        
        return super()._parse_tool_call(tool_call)
    
    def _extract_choice_content(self, choice) -> str:
        if hasattr(choice, "message") and hasattr(choice.message, "content"):
            content = choice.message.content
            if content:
                return str(content)
        
        if hasattr(choice, "candidate") and hasattr(choice.candidate, "content"):
            candidate = choice.candidate
            if hasattr(candidate.content, "parts") and candidate.content.parts:
                text_parts = []
                for part in candidate.content.parts:
                    if hasattr(part, "text") and part.text:
                        text_parts.append(str(part.text))
                if text_parts:
                    return " ".join(text_parts)
        
        return ""
