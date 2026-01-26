import logging
import json
import re
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_PERSONA_FALLBACK = "\n".join([
    "IDENTIDADE",
    "- Nome: Tangerina",
    "- Personalidade: Direto, bem-humorado, objetivo",
    "- Idioma: Sempre português brasileiro",
    "- Emojis: Máximo 1 por resposta quando contextual",
    "- Tom: Positivo, descontraído, profissional quando necessário",
    "- Criador: Bergamota, ID usuário: 515664341194768385",
])

SYSTEM_PROMPT_TEMPLATE = "\n".join([
    "{persona_context}",
    "",
    "REGRAS DE RESPOSTA",
    "- Responda somente em português brasileiro",
    "- Fale sempre na primeira pessoa como Tangerina",
    "- Máximo 1 emoji quando fizer sentido",
    "- Resposta curta e direta",
    "",
    "REGRAS DE FERRAMENTAS",
    "- Use SEMPRE as ferramentas disponíveis quando precisar executar ações",
    "- NÃO escreva o nome da ferramenta e parâmetros como texto",
    "- Use o sistema de chamadas de ferramentas da API para executar ações",
    "- Quando uma ferramenta for executada com sucesso, informe o usuário de forma natural",
])


def build_tools_schema() -> List[Dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "GET_Canais",
                "description": "Lista todos os canais de voz do servidor Discord",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "guild_id": {"type": "integer", "description": "ID do servidor Discord"}
                    },
                    "required": ["guild_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "GET_UserVoiceChannel",
                "description": "Encontra o canal de voz onde o usuário está atualmente",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "guild_id": {"type": "integer", "description": "ID do servidor Discord"},
                        "user_id": {"type": "integer", "description": "ID do usuário Discord"}
                    },
                    "required": ["guild_id", "user_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "SEND_Mensagem",
                "description": "Envia uma mensagem de texto no canal Discord. Esta é a ÚNICA ferramenta permitida para enviar respostas ao usuário.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "channel_id": {"type": "integer", "description": "ID do canal Discord onde enviar a mensagem"},
                        "text": {"type": "string", "description": "Texto da mensagem a ser enviada"}
                    },
                    "required": ["channel_id", "text"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "EnterChannel",
                "description": (
                    "Entra em um canal de voz do Discord especificado por channel_id. "
                    "Caso não tenha o channel_id, use a ferramenta GET_UserVoiceChannel para obter o canal de voz atual do usuário. "
                    "Caso o usuário não esteja em nenhum canal de voz, use a ferramenta GET_Canais para obter a lista de canais disponíveis."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "guild_id": {"type": "integer", "description": "ID do servidor Discord"},
                        "channel_id": {"type": "integer", "description": "ID do canal de voz"}
                    },
                    "required": ["guild_id", "channel_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "LeaveChannel",
                "description": "Sai do canal de voz do Discord",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "guild_id": {"type": "integer", "description": "ID do servidor Discord"}
                    },
                    "required": ["guild_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "MusicPlay",
                "description": "Toca música do YouTube ou Spotify",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "guild_id": {"type": "integer", "description": "ID do servidor Discord"},
                        "channel_id": {"type": "integer", "description": "ID do canal de voz"},
                        "query": {"type": "string", "description": "Nome da música, URL do YouTube ou URI do Spotify"}
                    },
                    "required": ["guild_id", "channel_id", "query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "MusicStop",
                "description": "Para a música e limpa a fila",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "guild_id": {"type": "integer", "description": "ID do servidor Discord"}
                    },
                    "required": ["guild_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "MusicSkip",
                "description": "Pula a música atual",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "guild_id": {"type": "integer", "description": "ID do servidor Discord"}
                    },
                    "required": ["guild_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "MusicPause",
                "description": "Pausa a reprodução de música",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "guild_id": {"type": "integer", "description": "ID do servidor Discord"}
                    },
                    "required": ["guild_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "MusicResume",
                "description": "Retoma a reprodução de música pausada",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "guild_id": {"type": "integer", "description": "ID do servidor Discord"}
                    },
                    "required": ["guild_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "MusicVolume",
                "description": "Ajusta o volume da música (0-100)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "guild_id": {"type": "integer", "description": "ID do servidor Discord"},
                        "volume": {"type": "integer", "description": "Volume entre 0 e 100", "minimum": 0, "maximum": 100}
                    },
                    "required": ["guild_id", "volume"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "GET_MusicQueue",
                "description": "Retorna a fila de músicas atual com opções de filtragem e formatação",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "guild_id": {"type": "integer", "description": "ID do servidor Discord"},
                        "limit": {"type": "integer", "description": "Número máximo de itens da fila a retornar (padrão: todos)"},
                        "info_level": {"type": "string", "enum": ["all", "name", "link", "minimal"], "description": "Nível de informação: 'all' (título, url, duração, artistas), 'name' (apenas título), 'link' (título e url), 'minimal' (título e posição)"},
                        "offset": {"type": "integer", "description": "Posição inicial na fila para paginação (padrão: 0)"},
                        "include_current": {"type": "boolean", "description": "Incluir música atual em reprodução (padrão: true)"}
                    },
                    "required": ["guild_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "MusicSpotifyPlay",
                "description": "Toca uma música, playlist ou álbum específico do Spotify usando URI",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "guild_id": {"type": "integer", "description": "ID do servidor Discord"},
                        "channel_id": {"type": "integer", "description": "ID do canal de voz"},
                        "spotify_uri": {"type": "string", "description": "URI do Spotify (track, playlist ou album)"}
                    },
                    "required": ["guild_id", "channel_id", "spotify_uri"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "MusicLeave",
                "description": "Sai do canal de voz e limpa todos os recursos de música",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "guild_id": {"type": "integer", "description": "ID do servidor Discord"}
                    },
                    "required": ["guild_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "TTSSpeak",
                "description": "Fala um texto usando síntese de voz (TTS) via ElevenLabs",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "guild_id": {"type": "integer", "description": "ID do servidor Discord"},
                        "channel_id": {"type": "integer", "description": "ID do canal de voz"},
                        "text": {"type": "string", "description": "Texto a ser convertido em fala"}
                    },
                    "required": ["guild_id", "channel_id", "text"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "WebSearch",
                "description": "Searches the web for current information, news, facts, or any topic. Use this when you need up-to-date information that may not be in your training data.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query to look up on the web"
                        }
                    },
                    "required": ["query"]
                }
            }
        }
    ]


def build_tool_mapping(tools_schema: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {tool_def["function"]["name"]: {"required": tool_def["function"]["parameters"].get("required", []), "properties": tool_def["function"]["parameters"].get("properties", {})} for tool_def in tools_schema}


def _normalize_integer_ids(tool_name: str, parameters: Dict[str, Any], tool_mapping: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    if tool_name not in tool_mapping:
        return parameters
    
    properties = tool_mapping[tool_name].get("properties", {})
    normalized = parameters.copy()
    
    for param_name, param_value in normalized.items():
        if param_name not in properties or properties[param_name].get("type") != "integer":
            continue
        if isinstance(param_value, float) and param_value.is_integer():
            normalized[param_name] = int(param_value)
        elif isinstance(param_value, str):
            try:
                normalized[param_name] = int(param_value)
            except (ValueError, OverflowError):
                try:
                    float_value = float(param_value)
                    if float_value.is_integer():
                        normalized[param_name] = int(float_value)
                except (ValueError, OverflowError):
                    pass
    
    return normalized


def normalize_context(context: Optional[List[Dict]]) -> List[Dict]:
    if not context:
        return []
    return [
        {"role": "user", "content": item.get("content", "").strip()}
        for item in context[-10:]
        if isinstance(item, dict) and isinstance(item.get("content"), str) and item.get("content", "").strip()
    ]


def load_tangerina_persona() -> str:
    try:
        persona_path = Path(__file__).parent / "tangerina_persona.txt"
        with open(persona_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return DEFAULT_PERSONA_FALLBACK


def build_system_text(persona_context: str) -> str:
    return SYSTEM_PROMPT_TEMPLATE.format(persona_context=persona_context.strip()).strip()


class BaseChatbot(ABC):
    def __init__(self, api_key: str, bot_instance=None, music_bot_instance=None, memory_manager=None, web_search_service=None):
        self._initialize_client(api_key)
        self.persona_context = load_tangerina_persona()
        self.bot = bot_instance
        self.music_bot = music_bot_instance
        self.memory_manager = memory_manager
        self.web_search_service = web_search_service
        self._tools_schema = build_tools_schema()
        self._tool_mapping = build_tool_mapping(self._tools_schema)

    @abstractmethod
    def _initialize_client(self, api_key: str):
        pass

    @abstractmethod
    async def _make_api_request(self, messages: List[Dict], max_tokens: int = 1000, tools: Optional[List] = None):
        pass

    @abstractmethod
    def _extract_tool_calls(self, choice) -> List[Any]:
        pass

    @abstractmethod
    def _extract_choice_content(self, choice) -> str:
        pass

    @abstractmethod
    def _get_models_to_try(self) -> List[str]:
        pass

    def _validate_parameters(self, tool_name: str, parameters: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        if tool_name not in self._tool_mapping:
            return False, f"Unknown tool: {tool_name}"
        
        required = self._tool_mapping[tool_name]["required"]
        missing = [p for p in required if p not in parameters]
        if missing:
            return False, f"Missing required parameters: {', '.join(missing)}"
        
        if tool_name == "MusicVolume":
            try:
                vol = int(parameters.get("volume", 0))
                if not 0 <= vol <= 100:
                    return False, "Volume must be between 0 and 100"
            except (ValueError, TypeError):
                return False, "Volume must be an integer"
        
        return True, None

    def _build_tool_message(self, tool_name: str, tool_result: Dict[str, Any], 
                            tool_call_id: Optional[str] = None) -> Dict[str, Any]:
        message = {
            "role": "tool",
            "content": json.dumps(tool_result) if isinstance(tool_result, dict) else str(tool_result),
            "name": tool_name
        }
        
        if tool_call_id is not None:
            message["tool_call_id"] = tool_call_id
        
        return message

    async def _call_tool(self, tool_name: str, parameters: Dict[str, Any], app_functions: Dict[str, Any],
                        guild_id: Optional[int] = None, channel_id: Optional[int] = None,
                        user_id: Optional[int] = None) -> Dict[str, Any]:
        required = self._tool_mapping.get(tool_name, {}).get("required", [])
        
        for param_name, param_value in [("guild_id", guild_id), ("channel_id", channel_id), ("user_id", user_id)]:
            if param_name in required and param_name not in parameters and param_value is not None:
                parameters[param_name] = param_value
        
        logger.info(f"Tool call: {tool_name} with parameters: {json.dumps(parameters, ensure_ascii=False)}")
        
        is_valid, error_msg = self._validate_parameters(tool_name, parameters)
        if not is_valid:
            return {"success": False, "error": error_msg}
        
        tool_handlers = {
            "GET_Canais": self._handle_get_canais,
            "GET_UserVoiceChannel": lambda p, f: self._call_app_function("get_user_voice_channel", f, int(p["guild_id"]), int(p["user_id"])),
            "SEND_Mensagem": self._handle_send_mensagem,
            "EnterChannel": self._handle_enter_channel,
            "LeaveChannel": lambda p, f: self._call_app_function("leave_music", f, int(p["guild_id"])),
            "MusicPlay": lambda p, f: self._call_app_function("play_music", f, int(p["guild_id"]), int(p["channel_id"]), str(p["query"])),
            "MusicStop": lambda p, f: self._call_app_function("stop_music", f, int(p["guild_id"])),
            "MusicSkip": lambda p, f: self._call_app_function("skip_music", f, int(p["guild_id"])),
            "MusicPause": lambda p, f: self._call_app_function("pause_music", f, int(p["guild_id"])),
            "MusicResume": lambda p, f: self._call_app_function("resume_music", f, int(p["guild_id"])),
            "MusicVolume": lambda p, f: self._call_app_function("set_volume", f, int(p["guild_id"]), int(p["volume"])),
            "GET_MusicQueue": self._handle_get_music_queue,
            "MusicSpotifyPlay": lambda p, f: self._call_app_function("play_spotify_music", f, int(p["guild_id"]), int(p["channel_id"]), str(p["spotify_uri"])),
            "MusicLeave": lambda p, f: self._call_app_function("leave_music", f, int(p["guild_id"])),
            "TTSSpeak": lambda p, f: self._call_app_function("speak_tts", f, int(p["guild_id"]), int(p["channel_id"]), str(p["text"])),
            "WebSearch": self._handle_web_search
        }
        
        handler = tool_handlers.get(tool_name)
        if not handler:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}
        
        try:
            return await handler(parameters, app_functions)
        except KeyError as e:
            return {"success": False, "error": f"Missing required parameter: {str(e)}"}
        except (ValueError, TypeError) as e:
            return {"success": False, "error": f"Invalid parameter: {str(e)}"}
        except Exception as e:
            logger.error(f"Error calling tool {tool_name}: {e}", exc_info=True)
            return {"success": False, "error": f"Tool execution failed: {str(e)}"}

    async def _call_app_function(self, func_name: str, app_functions: Dict[str, Any], *args) -> Dict[str, Any]:
        func = app_functions.get(func_name)
        return await func(*args) if func else {"success": False, "error": "Function not available"}

    async def _handle_get_canais(self, parameters: Dict[str, Any], app_functions: Dict[str, Any]) -> Dict[str, Any]:
        guild_id = int(parameters["guild_id"])
        guild = self.bot.get_guild(guild_id) if self.bot else None
        if not guild:
            return {"success": False, "error": f"Guild {guild_id} not found"}
        return {"success": True, "channels": [{"id": ch.id, "name": ch.name, "type": str(ch.type)} for ch in guild.voice_channels]}

    async def _handle_get_music_queue(self, parameters: Dict[str, Any], app_functions: Dict[str, Any]) -> Dict[str, Any]:
        guild_id = int(parameters["guild_id"])
        limit = parameters.get("limit")
        info_level = parameters.get("info_level", "all")
        offset = int(parameters.get("offset", 0))
        include_current = parameters.get("include_current", True)
        
        return await self._call_app_function("get_queue", app_functions, guild_id, limit, info_level, offset, include_current)

    async def _handle_send_mensagem(self, parameters: Dict[str, Any], app_functions: Dict[str, Any]) -> Dict[str, Any]:
        if not self.bot:
            return {"success": False, "error": "Bot instance not available"}
        channel = self.bot.get_channel(int(parameters["channel_id"]))
        if not channel:
            return {"success": False, "error": f"Channel {parameters['channel_id']} not found"}
        await channel.send(str(parameters["text"]))
        return {"success": True, "message": "Message sent"}

    async def _handle_enter_channel(self, parameters: Dict[str, Any], app_functions: Dict[str, Any]) -> Dict[str, Any]:
        if not self.music_bot:
            return {"success": False, "error": "Music bot not available"}
        vc = await self.music_bot.join_voice_channel(int(parameters["guild_id"]), int(parameters["channel_id"]))
        if vc:
            return {"success": True, "channel_id": parameters["channel_id"], "channel_name": vc.channel.name if vc.channel else None}
        return {"success": False, "error": "Failed to join voice channel"}

    async def _handle_web_search(self, parameters: Dict[str, Any], app_functions: Dict[str, Any]) -> Dict[str, Any]:
        if not self.web_search_service:
            return {"success": False, "error": "Web search service not available"}
        
        query = str(parameters.get("query", "")).strip()
        if not query:
            return {"success": False, "error": "Query cannot be empty"}
        
        try:
            result = self.web_search_service.search(query)
            return result if result.get("success") else {"success": False, "error": result.get("error", "Search failed"), "results": []}
        except Exception as e:
            logger.error(f"Web search error: {e}")
            return {"success": False, "error": str(e), "results": []}

    def _build_messages(self, message: str, context: Optional[List[Dict]] = None,
                       guild_id: Optional[int] = None, channel_id: Optional[int] = None,
                       user_id: Optional[int] = None,
                       retrieved_memories: Optional[List[Dict]] = None) -> List[Dict]:
        system_content = build_system_text(self.persona_context)
        
        context_info = []
        if guild_id is not None:
            context_info.append(f"ID do servidor atual (guild_id): {guild_id}")
        if channel_id is not None:
            context_info.append(f"ID do canal atual (channel_id): {channel_id}")
        if user_id is not None:
            context_info.append(f"ID do usuário atual (user_id): {user_id}")
        
        if context_info:
            system_content += "\n\nCONTEXTO ATUAL:\n" + "\n".join(context_info)
            system_content += "\n\nIMPORTANTE: Ao chamar ferramentas que requerem guild_id, channel_id ou user_id, use SEMPRE os valores do contexto atual acima. NUNCA use valores mockados ou de exemplo."
        
        if retrieved_memories:
            if isinstance(retrieved_memories, dict):
                recent_memories = retrieved_memories.get("recent", [])
                semantic_memories = retrieved_memories.get("semantic", [])
                
                if recent_memories:
                    recent_texts = [
                        f"[{mem.get('timestamp', '')[:19]}] {mem.get('content', '')}"
                        for mem in recent_memories
                    ]
                    if recent_texts:
                        memories_section = "\n\nMEMORIAS RECENTES (últimas 3 interações):\n"
                        memories_section += "\n".join([f"{i+1}. {text}" for i, text in enumerate(recent_texts)])
                        system_content += memories_section
                
                if semantic_memories:
                    semantic_texts = [mem.get("content", "") for mem in semantic_memories if mem.get("content")]
                    if semantic_texts:
                        memories_section = "\n\nMEMORIAS RELEVANTES DO PASSADO (baseadas em similaridade semântica):\n"
                        memories_section += "\n".join([f"- {text}" for text in semantic_texts])
                        system_content += memories_section
            else:
                memory_texts = [mem.get("content", "") for mem in retrieved_memories if mem.get("content")]
                if memory_texts:
                    memories_section = "\n\nMEMORIAS RELEVANTES (use estas informacoes para contextualizar sua resposta):\n" + "\n".join([f"- {mem}" for mem in memory_texts])
                    system_content += memories_section
        
        messages = [{"role": "system", "content": system_content}]
        messages.extend(normalize_context(context))
        messages.append({"role": "user", "content": message.strip()})
        return messages

    def _parse_xml_args(self, args_content: str) -> Dict[str, Any]:
        keys = re.findall(r"<arg_key>(.*?)</arg_key>", args_content, re.DOTALL)
        values = re.findall(r"<arg_value>(.*?)</arg_value>", args_content, re.DOTALL)
        
        if len(keys) != len(values):
            return {}
        
        params = {}
        for key, value in zip(keys, values):
            key = key.strip()
            value = value.strip()
            if value.isdigit():
                params[key] = int(value)
            elif value.replace('.', '', 1).replace('-', '', 1).isdigit():
                try:
                    params[key] = float(value)
                except ValueError:
                    params[key] = value
            else:
                params[key] = value
        return params

    def _parse_tool_call_from_text(self, text: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        text = text.strip()
        tool_names = [tool["function"]["name"] for tool in self._tools_schema]

        xml_patterns = [
            (r"<tool_call>(\w+)(.*?)</tool_call>", True),
            (r"^(\w+)\s*\n\s*(.*?)</tool_call>", True),
        ]

        for pattern, use_xml_args in xml_patterns:
            match = re.search(pattern, text, re.DOTALL | re.MULTILINE)
            if match:
                tool_name = match.group(1).strip()
                if tool_name in tool_names:
                    params = self._parse_xml_args(match.group(2)) if use_xml_args else {}
                    if params or not use_xml_args:
                        return tool_name, params

        for tool_name in tool_names:
            json_patterns = [
                rf"^{re.escape(tool_name)}\s*\n\s*(\{{.*?\}})",
                rf"^{re.escape(tool_name)}\s+(\{{.*?\}})",
                rf"^{re.escape(tool_name)}\s*:\s*(\{{.*?\}})",
                rf"^{re.escape(tool_name)}\s*(\{{.*?\}})",
            ]
            for pattern in json_patterns:
                match = re.search(pattern, text, re.DOTALL | re.MULTILINE)
                if match:
                    try:
                        params = json.loads(match.group(1).strip())
                        if isinstance(params, dict):
                            return tool_name, params
                    except (json.JSONDecodeError, Exception):
                        continue

        return None

    def _extract_text_from_malformed_tool_call(self, content: str) -> Optional[str]:
        patterns = [
            r'SEND_Mensagem\s*\([^)]*text\s*=\s*"([^"]+)"',
            r'SEND_Mensagem\s*\([^)]*text\s*=\s*\'([^\']+)\'',
            r'text\s*=\s*"([^"]+)"',
            r'text\s*=\s*\'([^\']+)\'',
        ]
        for pattern in patterns:
            match = re.search(pattern, content, re.DOTALL)
            if match:
                return match.group(1).strip()
        return None

    def _parse_tool_call(self, tool_call) -> Optional[Tuple[str, Dict[str, Any]]]:
        if hasattr(tool_call, "function"):
            func_info = tool_call.function
            tool_name = getattr(func_info, "name", None)
            tool_params_str = getattr(func_info, "arguments", "{}")
        elif isinstance(tool_call, dict):
            func_info = tool_call.get("function", {})
            tool_name = func_info.get("name") if isinstance(func_info, dict) else None
            tool_params_str = func_info.get("arguments", "{}") if isinstance(func_info, dict) else "{}"
        else:
            return None
        
        if not tool_name:
            return None
        
        try:
            tool_params = json.loads(tool_params_str) if isinstance(tool_params_str, str) else tool_params_str
            if isinstance(tool_params, dict):
                tool_params = _normalize_integer_ids(tool_name, tool_params, self._tool_mapping)
            return tool_name, tool_params if isinstance(tool_params, dict) else {}
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Failed to parse tool parameters for {tool_name}: {e}", exc_info=True)
            return None

    async def _handle_tool_call_from_text(self, content: str, app_functions: Dict[str, Any],
                                         guild_id: Optional[int], channel_id: Optional[int],
                                         user_id: Optional[int], tool_calls_executed: List[Dict],
                                         sent_message_texts: List[str]) -> Optional[Tuple[str, bool]]:
        parsed_tool = self._parse_tool_call_from_text(content)
        if not parsed_tool:
            return None
        
        tool_name, tool_params = parsed_tool
        tool_result = await self._call_tool(tool_name, tool_params, app_functions or {}, guild_id, channel_id, user_id)
        tool_calls_executed.append({"tool": tool_name, "parameters": tool_params, "result": tool_result})
        
        send_mensagem_executed = tool_name == "SEND_Mensagem" and tool_result.get("success")
        if send_mensagem_executed:
            sent_text = str(tool_params.get("text", ""))
            if sent_text:
                sent_message_texts.append(sent_text.strip())
        
        if not tool_result.get("success"):
            return f"Erro ao executar ação: {tool_result.get('error', 'Erro desconhecido')}", send_mensagem_executed
        
        if tool_name == "EnterChannel":
            return f"Entrei no canal {tool_result.get('channel_name', 'canal')}!", send_mensagem_executed
        if tool_name == "SEND_Mensagem":
            return " ".join(sent_message_texts) if sent_message_texts else "", send_mensagem_executed
        return "Ação executada com sucesso!", send_mensagem_executed

    async def generate_response_with_tools(self, message: str, context: Optional[List[Dict]] = None,
                                          guild_id: Optional[int] = None, channel_id: Optional[int] = None,
                                          user_id: Optional[int] = None,
                                          app_functions: Optional[Dict[str, Any]] = None,
                                          retrieved_memories: Optional[List[Dict]] = None) -> Tuple[str, List[Dict[str, Any]]]:
        if not isinstance(message, str) or not message.strip():
            return "Manda a pergunta de novo pra mim, por favor.", []

        messages = self._build_messages(message, context, guild_id, channel_id, user_id, retrieved_memories)
        tool_calls_executed = []
        send_mensagem_executed = False
        sent_message_texts = []

        max_iterations = 10
        iteration = 0
        while iteration < max_iterations:
            iteration += 1
            try:
                response = await self._make_api_request(
                    messages,
                    max_tokens=1000,
                    tools=self._tools_schema
                )

                choices = response.choices if hasattr(response, "choices") else []
                if not choices:
                    break
                
                choice = choices[0]
                finish_reason = getattr(choice, "finish_reason", None)
                content = self._extract_choice_content(choice)
                tool_calls = self._extract_tool_calls(choice)

                if tool_calls:
                    parsed_tool_calls = []
                    tool_results = []
                    
                    for tool_call in tool_calls:
                        parsed = self._parse_tool_call(tool_call)
                        if not parsed:
                            continue
                        
                        tool_name, tool_params = parsed
                        tool_result = await self._call_tool(tool_name, tool_params, app_functions or {}, guild_id, channel_id, user_id)
                        tool_calls_executed.append({"tool": tool_name, "parameters": tool_params, "result": tool_result})
                        
                        if tool_name == "SEND_Mensagem" and tool_result.get("success"):
                            send_mensagem_executed = True
                            sent_text = str(tool_params.get("text", ""))
                            if sent_text:
                                sent_message_texts.append(sent_text.strip())
                        
                        tool_call_id = tool_call.id if hasattr(tool_call, "id") else None
                        parsed_tool_calls.append({
                            "id": tool_call_id,
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": json.dumps(tool_params) if isinstance(tool_params, dict) else str(tool_params)
                            }
                        })
                        tool_results.append((tool_name, tool_result, tool_call_id))
                    
                    if parsed_tool_calls:
                        assistant_message = {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": parsed_tool_calls
                        }
                        messages.append(assistant_message)
                        
                        for tool_name, tool_result, tool_call_id in tool_results:
                            messages.append(self._build_tool_message(tool_name, tool_result, tool_call_id))
                    
                    continue
                
                if not isinstance(content, str) or not content.strip():
                    if finish_reason == "stop":
                        if send_mensagem_executed and sent_message_texts:
                            return " ".join(sent_message_texts), tool_calls_executed
                        if send_mensagem_executed:
                            return "", tool_calls_executed
                        if tool_calls_executed:
                            return "Ação executada.", tool_calls_executed
                    break
                
                content_stripped = content.strip()
                
                tool_call_result = await self._handle_tool_call_from_text(
                    content_stripped, app_functions or {}, guild_id, channel_id, user_id,
                    tool_calls_executed, sent_message_texts
                )
                if tool_call_result:
                    response_text, msg_executed = tool_call_result
                    if msg_executed:
                        send_mensagem_executed = True
                    return response_text, tool_calls_executed
                
                if any(marker in content_stripped.lower() for marker in ["</tool_call>", "<arg_key>", "<arg_value>", "<tool_call>"]):
                    return ("", tool_calls_executed) if send_mensagem_executed else ("Ação executada.", tool_calls_executed)
                
                if send_mensagem_executed and content_stripped in sent_message_texts:
                    return " ".join(sent_message_texts), tool_calls_executed
                
                if finish_reason == "stop":
                    if content_stripped:
                        extracted = self._extract_text_from_malformed_tool_call(content_stripped)
                        return extracted if extracted else content_stripped, tool_calls_executed
                    if send_mensagem_executed and sent_message_texts:
                        return " ".join(sent_message_texts), tool_calls_executed
                    if send_mensagem_executed or tool_calls_executed:
                        return "" if send_mensagem_executed else "Ação executada.", tool_calls_executed
                    return "Ação executada.", tool_calls_executed
                
                if finish_reason == "length":
                    if content_stripped:
                        logger.warning("Response truncated due to length limit")
                        extracted = self._extract_text_from_malformed_tool_call(content_stripped)
                        return extracted if extracted else content_stripped, tool_calls_executed
                    break
                
                if finish_reason == "tool_calls":
                    logger.warning("finish_reason is 'tool_calls' but no tool_calls found")
                    break
                
                if content_stripped:
                    extracted = self._extract_text_from_malformed_tool_call(content_stripped)
                    return extracted if extracted else content_stripped, tool_calls_executed
                break
                
            except Exception as e:
                logger.error(f"API request failed: {e}")
                return "Deu ruim aqui do meu lado. Tenta de novo em instantes.", tool_calls_executed
        
        logger.warning(f"Exceeded maximum iterations ({max_iterations}) without completion")
        if tool_calls_executed:
            return "Ação executada.", tool_calls_executed
        return "Tive um problema pra responder agora. Tenta de novo?", tool_calls_executed

    async def generate_response(self, message: str, context: Optional[List[Dict]] = None) -> str:
        if not isinstance(message, str) or not message.strip():
            return "Manda a pergunta de novo pra mim, por favor."

        messages = self._build_messages(message, context)

        try:
            response = await self._make_api_request(messages, max_tokens=600)
            content = self._extract_content(response)
            return content if content else "Tive um problema pra responder agora. Tenta de novo?"
        except Exception as e:
            logger.error(f"API request failed: {e}")
            return "Deu ruim aqui do meu lado. Tenta de novo em instantes."

    def _extract_content(self, response) -> str:
        if hasattr(response, "choices") and response.choices:
            choice = response.choices[0]
            if hasattr(choice, "message") and hasattr(choice.message, "content"):
                content = choice.message.content
                if isinstance(content, str) and content.strip():
                    return content.strip()
        elif isinstance(response, dict):
            response_data = response.get("data", {})
            choices = response_data.get("choices", [])
            if choices:
                content = choices[0].get("content", "")
                if isinstance(content, str) and content.strip():
                    return content.strip()
        return ""
