import logging
import json
import re
from typing import Optional, Dict, Any, Tuple, List
from zhipuai import ZhipuAI

logger = logging.getLogger(__name__)


class ZhipuChatbot:
    def __init__(self, api_key: str, bot_instance=None, music_bot_instance=None, model: str = "glm-4-plus"):
        self.client = ZhipuAI(api_key=api_key)
        self.model = model
        self._fallback_models = ["glm-4-plus", "glm-4-flash", "glm-3-turbo", "glm-4"]
        self.persona_context = self._load_tangerina_persona()
        self.bot = bot_instance
        self.music_bot = music_bot_instance
        self._tools_schema = self._build_tools_schema()
        self._tool_mapping = self._build_tool_mapping()
        logger.info(f"ZhipuAI GLM initialized with model {model}")

    def _load_tangerina_persona(self) -> str:
        try:
            with open("tangerina_persona.txt", "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return "\n".join([
                "IDENTIDADE",
                "- Nome: Tangerina",
                "- Personalidade: Direto, bem-humorado, objetivo",
                "- Idioma: Sempre português brasileiro",
                "- Emojis: Máximo 1 por resposta quando contextual",
                "- Tom: Positivo, descontraído, profissional quando necessário",
                "- Criador: Bergamota, ID usuário: 515664341194768385",
            ])

    def _system_text(self) -> str:
        return "\n".join([
            self.persona_context.strip(),
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
        ]).strip()

    def _normalize_context(self, context: Optional[List[Dict]]) -> List[Dict]:
        if not context:
            return []
        normalized = []
        for item in context[-10:]:
            if isinstance(item, dict):
                content = item.get("content")
                if isinstance(content, str) and content.strip():
                    normalized.append({"role": "user", "content": content.strip()})
        return normalized

    def _build_tools_schema(self) -> List[Dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "GET_Canais",
                    "description": "Lista todos os canais do servidor Discord",
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
                    "description": "Entra em um canal de voz do Discord",
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
                    "description": "Retorna a fila de músicas atual",
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
            }
        ]

    def _build_tool_mapping(self) -> Dict[str, Dict[str, Any]]:
        mapping = {}
        for tool_def in self._tools_schema:
            func_info = tool_def["function"]
            name = func_info["name"]
            params = func_info["parameters"]
            mapping[name] = {
                "required": params.get("required", []),
                "properties": params.get("properties", {})
            }
        return mapping

    def _get_tools_schema(self) -> List[Dict[str, Any]]:
        return self._tools_schema

    def _get_required_params(self, tool_name: str) -> List[str]:
        return self._tool_mapping.get(tool_name, {}).get("required", [])

    def _validate_parameters(self, tool_name: str, parameters: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        if tool_name not in self._tool_mapping:
            return False, f"Unknown tool: {tool_name}"
        
        required = self._get_required_params(tool_name)
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

    async def _call_app_function(self, func_name: str, app_functions: Dict[str, Any], *args) -> Dict[str, Any]:
        func = app_functions.get(func_name)
        if func:
            return await func(*args)
        return {"success": False, "error": "Function not available"}

    async def _call_tool(self, tool_name: str, parameters: Dict[str, Any], app_functions: Dict[str, Any],
                        guild_id: Optional[int] = None, channel_id: Optional[int] = None,
                        user_id: Optional[int] = None) -> Dict[str, Any]:
        required = self._get_required_params(tool_name)
        
        if "guild_id" in required and "guild_id" not in parameters and guild_id is not None:
            parameters["guild_id"] = guild_id
            logger.info(f"Auto-filled guild_id={guild_id} for {tool_name}")
        
        if "channel_id" in required and "channel_id" not in parameters and channel_id is not None:
            parameters["channel_id"] = channel_id
            logger.info(f"Auto-filled channel_id={channel_id} for {tool_name}")
        
        if "user_id" in required and "user_id" not in parameters and user_id is not None:
            parameters["user_id"] = user_id
            logger.info(f"Auto-filled user_id={user_id} for {tool_name}")
        
        is_valid, error_msg = self._validate_parameters(tool_name, parameters)
        if not is_valid:
            logger.warning(f"Invalid parameters for {tool_name}: {error_msg}")
            return {"success": False, "error": error_msg}
        
        logger.info(f"Calling tool: {tool_name} with parameters: {parameters}")
        
        try:
            if tool_name == "GET_Canais":
                guild_id = int(parameters["guild_id"])
                guild = self.bot.get_guild(guild_id) if self.bot else None
                if not guild:
                    return {"success": False, "error": f"Guild {guild_id} not found"}
                channels = [{"id": ch.id, "name": ch.name, "type": str(ch.type)} for ch in guild.channels]
                return {"success": True, "channels": channels}
            
            elif tool_name == "GET_UserVoiceChannel":
                return await self._call_app_function("get_user_voice_channel", app_functions,
                                                    int(parameters["guild_id"]), int(parameters["user_id"]))
            
            elif tool_name == "SEND_Mensagem":
                if not self.bot:
                    return {"success": False, "error": "Bot instance not available"}
                channel = self.bot.get_channel(int(parameters["channel_id"]))
                if not channel:
                    return {"success": False, "error": f"Channel {parameters['channel_id']} not found"}
                await channel.send(str(parameters["text"]))
                return {"success": True, "message": "Message sent"}
            
            elif tool_name == "EnterChannel":
                if not self.music_bot:
                    return {"success": False, "error": "Music bot not available"}
                vc = await self.music_bot.join_voice_channel(int(parameters["guild_id"]), int(parameters["channel_id"]))
                if vc:
                    return {"success": True, "channel_id": parameters["channel_id"],
                           "channel_name": vc.channel.name if vc.channel else None}
                return {"success": False, "error": "Failed to join voice channel"}
            
            elif tool_name == "LeaveChannel":
                return await self._call_app_function("leave_music", app_functions, int(parameters["guild_id"]))
            
            elif tool_name == "MusicPlay":
                return await self._call_app_function("play_music", app_functions,
                                                    int(parameters["guild_id"]), int(parameters["channel_id"]),
                                                    str(parameters["query"]))
            
            elif tool_name == "MusicStop":
                return await self._call_app_function("stop_music", app_functions, int(parameters["guild_id"]))
            
            elif tool_name == "MusicSkip":
                return await self._call_app_function("skip_music", app_functions, int(parameters["guild_id"]))
            
            elif tool_name == "MusicPause":
                return await self._call_app_function("pause_music", app_functions, int(parameters["guild_id"]))
            
            elif tool_name == "MusicResume":
                return await self._call_app_function("resume_music", app_functions, int(parameters["guild_id"]))
            
            elif tool_name == "MusicVolume":
                return await self._call_app_function("set_volume", app_functions,
                                                    int(parameters["guild_id"]), int(parameters["volume"]))
            
            elif tool_name == "GET_MusicQueue":
                return await self._call_app_function("get_queue", app_functions, int(parameters["guild_id"]))
            
            elif tool_name == "MusicSpotifyPlay":
                return await self._call_app_function("play_spotify_music", app_functions,
                                                    int(parameters["guild_id"]), int(parameters["channel_id"]),
                                                    str(parameters["spotify_uri"]))
            
            elif tool_name == "MusicLeave":
                return await self._call_app_function("leave_music", app_functions, int(parameters["guild_id"]))
            
            elif tool_name == "TTSSpeak":
                return await self._call_app_function("speak_tts", app_functions,
                                                    int(parameters["guild_id"]), int(parameters["channel_id"]),
                                                    str(parameters["text"]))
            
            return {"success": False, "error": f"Unknown tool: {tool_name}"}
        
        except KeyError as e:
            logger.error(f"Missing parameter for {tool_name}: {e}")
            return {"success": False, "error": f"Missing required parameter: {str(e)}"}
        except ValueError as e:
            logger.error(f"Invalid parameter value for {tool_name}: {e}")
            return {"success": False, "error": f"Invalid parameter: {str(e)}"}
        except Exception as e:
            logger.error(f"Error calling tool {tool_name}: {e}", exc_info=True)
            return {"success": False, "error": f"Tool execution failed: {str(e)}"}

    def _build_messages(self, message: str, context: Optional[List[Dict]] = None,
                       guild_id: Optional[int] = None, channel_id: Optional[int] = None,
                       user_id: Optional[int] = None) -> List[Dict]:
        system_content = self._system_text()
        
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
        
        messages = [{"role": "system", "content": system_content}]
        messages.extend(self._normalize_context(context))
        messages.append({"role": "user", "content": message.strip()})
        return messages

    def _extract_content(self, response) -> str:
        if hasattr(response, "choices") and response.choices:
            choice = response.choices[0]
            if hasattr(choice, "message") and hasattr(choice.message, "content"):
                content = choice.message.content
                if isinstance(content, str) and content.strip():
                    return content.strip()
        elif isinstance(response, dict):
            data = response.get("data", {})
            choices = data.get("choices", [])
            if choices:
                content = choices[0].get("content", "")
                if isinstance(content, str) and content.strip():
                    return content.strip()
        return ""

    def _parse_tool_call_from_text(self, text: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        text = text.strip()
        
        tool_names = [tool["function"]["name"] for tool in self._tools_schema]
        
        for tool_name in tool_names:
            patterns = [
                rf"^{re.escape(tool_name)}\s*\n\s*(\{{.*?\}})",
                rf"^{re.escape(tool_name)}\s+(\{{.*?\}})",
                rf"^{re.escape(tool_name)}\s*:\s*(\{{.*?\}})",
                rf"^{re.escape(tool_name)}\s*(\{{.*?\}})",
            ]
            
            for pattern in patterns:
                match = re.search(pattern, text, re.DOTALL | re.MULTILINE)
                if match:
                    try:
                        params_json = match.group(1).strip()
                        params = json.loads(params_json)
                        if isinstance(params, dict):
                            logger.info(f"Parsed tool call from text: {tool_name} with params: {params}")
                            return tool_name, params
                    except (json.JSONDecodeError, Exception) as e:
                        logger.debug(f"Failed to parse tool call parameters for {tool_name} with pattern {pattern}: {e}")
                        continue
        
        return None

    async def generate_response_with_tools(self, message: str, context: Optional[List[Dict]] = None,
                                          guild_id: Optional[int] = None, channel_id: Optional[int] = None,
                                          user_id: Optional[int] = None,
                                          app_functions: Optional[Dict[str, Any]] = None) -> Tuple[str, List[Dict[str, Any]]]:
        if not isinstance(message, str) or not message.strip():
            return "Manda a pergunta de novo pra mim, por favor.", []

        messages = self._build_messages(message, context, guild_id, channel_id, user_id)
        tool_calls_executed = []
        max_iterations = 5

        for iteration in range(max_iterations):
            try:
                models_to_try = [self.model] + [m for m in self._fallback_models if m != self.model]
                response = None
                last_error = None
                for model_name in models_to_try:
                    try:
                        response = self.client.chat.completions.create(
                            model=model_name,
                            messages=messages,
                            temperature=0.7,
                            top_p=0.9,
                            max_tokens=1000,
                            tools=self._tools_schema if iteration == 0 else None
                        )
                        if model_name != self.model:
                            logger.info(f"Using fallback model {model_name} instead of {self.model}")
                        break
                    except Exception as api_error:
                        last_error = api_error
                        continue
                
                if response is None:
                    raise last_error if last_error else Exception("All model names failed")

                choices = response.choices if hasattr(response, "choices") else []
                if not choices:
                    break
                
                choice = choices[0]
                finish_reason = choice.finish_reason if hasattr(choice, "finish_reason") else getattr(choice, "finish_reason", None)
                content = choice.message.content if hasattr(choice, "message") and hasattr(choice.message, "content") else (choice.get("content", "") if isinstance(choice, dict) else "")
                tool_calls = choice.message.tool_calls if hasattr(choice, "message") and hasattr(choice.message, "tool_calls") else (choice.get("tool_calls", []) if isinstance(choice, dict) else [])

                if tool_calls:
                    for tool_call in tool_calls:
                        if hasattr(tool_call, "function"):
                            function_info = tool_call.function
                            tool_name = function_info.name if hasattr(function_info, "name") else None
                            tool_params_str = function_info.arguments if hasattr(function_info, "arguments") else "{}"
                        elif isinstance(tool_call, dict):
                            function_info = tool_call.get("function", {})
                            tool_name = function_info.get("name") if isinstance(function_info, dict) else None
                            tool_params_str = function_info.get("arguments", "{}") if isinstance(function_info, dict) else "{}"
                        else:
                            logger.warning(f"Invalid tool_call format: {tool_call}")
                            continue
                        
                        if not tool_name:
                            logger.warning(f"Tool call missing name: {tool_call}")
                            continue
                        
                        try:
                            tool_params = json.loads(tool_params_str) if isinstance(tool_params_str, str) else tool_params_str
                            if not isinstance(tool_params, dict):
                                tool_params = {}
                        except (json.JSONDecodeError, Exception) as e:
                            logger.warning(f"Failed to parse tool parameters for {tool_name}: {e}")
                            tool_params = {}
                        
                        tool_result = await self._call_tool(tool_name, tool_params, app_functions or {},
                                                           guild_id, channel_id, user_id)
                        tool_calls_executed.append({
                            "tool": tool_name,
                            "parameters": tool_params,
                            "result": tool_result
                        })
                        
                        tool_call_dict = {
                            "id": tool_call.id if hasattr(tool_call, "id") else None,
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": tool_params_str
                            }
                        }
                        messages.append({
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [tool_call_dict]
                        })
                        messages.append({
                            "role": "tool",
                            "content": json.dumps(tool_result) if isinstance(tool_result, dict) else str(tool_result),
                            "name": tool_name
                        })
                    
                    continue
                
                if finish_reason == "stop" or (not tool_calls and content):
                    if isinstance(content, str) and content.strip():
                        parsed_tool = self._parse_tool_call_from_text(content)
                        if parsed_tool:
                            tool_name, tool_params = parsed_tool
                            logger.info(f"Detected tool call in text response: {tool_name} with params: {tool_params}")
                            tool_result = await self._call_tool(tool_name, tool_params, app_functions or {},
                                                               guild_id, channel_id, user_id)
                            tool_calls_executed.append({
                                "tool": tool_name,
                                "parameters": tool_params,
                                "result": tool_result
                            })
                            
                            if tool_result.get("success"):
                                if tool_name == "EnterChannel":
                                    channel_name = tool_result.get("channel_name", "canal")
                                    return f"Entrei no canal {channel_name}!", tool_calls_executed
                                elif tool_name == "SEND_Mensagem":
                                    return "Mensagem enviada!", tool_calls_executed
                                else:
                                    return "Ação executada com sucesso!", tool_calls_executed
                            else:
                                error_msg = tool_result.get("error", "Erro desconhecido")
                                return f"Erro ao executar ação: {error_msg}", tool_calls_executed
                        
                        return content.strip(), tool_calls_executed
                    break
                
                if content:
                    parsed_tool = self._parse_tool_call_from_text(str(content))
                    if parsed_tool:
                        tool_name, tool_params = parsed_tool
                        logger.info(f"Detected tool call in text response: {tool_name} with params: {tool_params}")
                        tool_result = await self._call_tool(tool_name, tool_params, app_functions or {},
                                                           guild_id, channel_id, user_id)
                        tool_calls_executed.append({
                            "tool": tool_name,
                            "parameters": tool_params,
                            "result": tool_result
                        })
                        
                        if tool_result.get("success"):
                            if tool_name == "EnterChannel":
                                channel_name = tool_result.get("channel_name", "canal")
                                return f"Entrei no canal {channel_name}!", tool_calls_executed
                            elif tool_name == "SEND_Mensagem":
                                return "Mensagem enviada!", tool_calls_executed
                            else:
                                return "Ação executada com sucesso!", tool_calls_executed
                        else:
                            error_msg = tool_result.get("error", "Erro desconhecido")
                            return f"Erro ao executar ação: {error_msg}", tool_calls_executed
                    
                    return str(content).strip(), tool_calls_executed
                
                break
                
            except Exception as e:
                logger.error(f"ZhipuAI request failed: {e}")
                return "Deu ruim aqui do meu lado. Tenta de novo em instantes.", tool_calls_executed
        
        return "Tive um problema pra responder agora. Tenta de novo?", tool_calls_executed

    async def generate_response(self, message: str, context: Optional[List[Dict]] = None) -> str:
        if not isinstance(message, str) or not message.strip():
            return "Manda a pergunta de novo pra mim, por favor."

        messages = self._build_messages(message, context)

        models_to_try = [self.model] + [m for m in self._fallback_models if m != self.model]
        response = None
        last_error = None
        for model_name in models_to_try:
            try:
                response = self.client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    temperature=0.7,
                    top_p=0.9,
                    max_tokens=600,
                )
                if model_name != self.model:
                    logger.info(f"Using fallback model {model_name} instead of {self.model}")
                break
            except Exception as api_error:
                last_error = api_error
                continue
        
        if response is None:
            raise last_error if last_error else Exception("All model names failed")
        
        try:
            content = self._extract_content(response)
            if content:
                return content
            return "Tive um problema pra responder agora. Tenta de novo?"
        except Exception as e:
            logger.error(f"ZhipuAI request failed: {e}")
            return "Deu ruim aqui do meu lado. Tenta de novo em instantes."
