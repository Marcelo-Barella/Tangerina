# Tangerina Discord Bot

[![Tests](https://github.com/Marcelo-Barella/Tangerina/actions/workflows/test.yml/badge.svg)](https://github.com/Marcelo-Barella/Tangerina/actions/workflows/test.yml)

Sistema de bot do Discord inteligente com suporte a múltiplos provedores de IA (ZhipuAI GLM, OpenAI GPT, Google Gemini), com capacidades de chamada de funções para controle de música, voz e interações Discord.

## Requisitos

- Python 3.8+
- pip
- Conta Discord com permissões para criar bots
- Token de bot do Discord

## Instalação

1. Crie um ambiente virtual:
```bash
python -m venv .venv
```

2. Ative o ambiente virtual:

- Windows: `.venv\Scripts\activate`
- Linux/Mac: `source .venv/bin/activate`

3. Instale as dependências:
```bash
pip install -r requirements.txt
```


## Configuração do Bot Discord

1. Acesse https://discord.com/developers/applications
2. Crie uma nova aplicação ou selecione uma existente
3. Vá para a seção "Bot" e crie um bot
4. Copie o token do bot (você precisará dele)
5. Em "Privileged Gateway Intents", habilite:

   - MESSAGE CONTENT INTENT (necessário para ler conteúdo das mensagens)

6. Convide o bot para seu servidor Discord:

   - Vá para a seção "OAuth2" > "URL Generator"
   - Selecione escopo: `bot`
   - Selecione permissões: `View Channels`, `Read Message History`
   - Use a URL gerada para convidar o bot

## Configuração

1. Crie um arquivo `.env` na raiz do projeto e configure as seguintes variáveis:

**Variáveis Obrigatórias:**
- `DISCORD_BOT_TOKEN`: Token do bot do Discord (obrigatório)

**Variáveis de Configuração do Chatbot:**
- `MODEL_PROVIDER`: Provedor de IA a ser usado - 'zhipu' (padrão), 'openai' ou 'gemini'
- `ZHIPU_API_KEY`: Chave da API ZhipuAI GLM (obrigatório se MODEL_PROVIDER=zhipu)
- `OPENAI_API_KEY`: Chave da API OpenAI (obrigatório se MODEL_PROVIDER=openai, também usado para Whisper se WHISPER_PROVIDER=openai)
- `GEMINI_API_KEY`: Chave da API Google Gemini (obrigatório se MODEL_PROVIDER=gemini)

**Variáveis Opcionais:**
- `N8N_WEBHOOK_URL`: URL do webhook do n8n (opcional - para integração com n8n se desejado)
- `LOG_LEVEL`: Nível de log (opcional, padrão: INFO)

**Variáveis de Memória (ChromaDB):**
- `MEMORY_ENABLED`: Habilita memória de longo prazo (opcional, padrão: false)
- `CHROMADB_PATH`: Caminho para armazenar dados do ChromaDB (opcional, padrão: ./data/chromadb)
- `CHROMADB_COLLECTION_NAME`: Nome da coleção ChromaDB (opcional, padrão: tangerina_memory)
- `EMBEDDING_PROVIDER`: Provedor de embeddings - 'sentence_transformers' (padrão) ou 'openai'
- `OPENAI_EMBEDDING_MODEL`: Modelo de embedding OpenAI (opcional, padrão: text-embedding-3-small)
- `SENTENCE_TRANSFORMER_MODEL`: Modelo SentenceTransformer (opcional, padrão: all-MiniLM-L6-v2)
- `MAX_RETRIEVAL_RESULTS`: Número máximo de memórias a recuperar (opcional, padrão: 10)
- `MEMORY_SIMILARITY_THRESHOLD`: Limiar de similaridade para recuperação (opcional, padrão: 0.7)
- `MEMORY_RETENTION_DAYS`: Dias de retenção de memórias (opcional, padrão: 30)

## Configuração do Spotify (Opcional)

Para habilitar a integração com Spotify:

1. Acesse https://developer.spotify.com/dashboard
2. Faça login com sua conta Spotify
3. Clique em "Create app"
4. Preencha:
   - App name: Tangerina Music Bot (ou qualquer nome)
   - App description: Bot de música para Discord
   - Redirect URI: Deixe vazio ou use `http://localhost` (não será usado)
5. Aceite os termos e clique em "Create"
6. Copie o "Client ID" e "Client Secret"
7. Adicione ao arquivo `.env`:
   ```
   SPOTIFY_CLIENT_ID=seu_client_id_aqui
   SPOTIFY_CLIENT_SECRET=seu_client_secret_aqui
   ```

**Nota**: A integração do Spotify usa Client Credentials Flow, que não requer redirect URI ou autenticação do usuário. Funciona perfeitamente para bots!

## Configuração do Chatbot (Opcional)

O bot suporta múltiplos provedores de IA para o processamento inteligente. Configure o provedor desejado através da variável `MODEL_PROVIDER` no arquivo `.env`.

### Provedor ZhipuAI GLM (Padrão)

Para usar o ZhipuAI GLM como provedor:

1. Acesse https://open.bigmodel.cn/ e crie uma conta
2. Obtenha sua API Key
3. Configure no arquivo `.env`:
   ```
   MODEL_PROVIDER=zhipu
   ZHIPU_API_KEY=sua_api_key_aqui
   ```

**Modelos utilizados:** GLM-4 Plus (padrão), com fallback para GLM-4 Flash, GLM-3 Turbo e GLM-4

### Provedor OpenAI GPT

Para usar o OpenAI GPT como provedor:

1. Acesse https://platform.openai.com/ e crie uma conta
2. Obtenha sua API Key
3. Configure no arquivo `.env`:
   ```
   MODEL_PROVIDER=openai
   OPENAI_API_KEY=sua_api_key_aqui
   OPENAI_MODEL=gpt-4o-mini
   ```

**Modelos utilizados:** GPT-4o Mini (padrão)

Você pode configurar um modelo diferente usando a variável `OPENAI_MODEL` (ex: `gpt-4o`, etc.).

### Provedor Google Gemini

Para usar o Google Gemini como provedor:

1. Acesse https://aistudio.google.com/ e crie uma conta
2. Obtenha sua API Key
3. Configure no arquivo `.env`:
   ```
   MODEL_PROVIDER=gemini
   GEMINI_API_KEY=sua_api_key_aqui
   ```

**Modelos utilizados:** Gemini 2.5 Flash Lite (padrão), com fallback para Gemini 2.0 Flash Exp

**Nota:** O suporte ao Gemini está funcional, mas pode ter limitações. Para produção, considere usar ZhipuAI ou OpenAI.

### Funcionalidades do Chatbot

Independente do provedor escolhido, o chatbot oferece:
- Respostas inteligentes em português brasileiro
- Integração com comandos de música e voz via chamada de funções
- Persona personalizada da Tangerina (carregada de `tangerina_persona.txt`)
- Contexto de conversa mantido
- Processamento inteligente com acesso a 15 ferramentas
- Decisão automática de ações baseada no contexto

**Importante:** As respostas do chatbot não são enviadas automaticamente via Discord. Elas são disponibilizadas através de chamadas de ferramentas (tool calls) ou podem ser acessadas via webhook n8n se configurado.

## Configuração do Piper TTS (Opcional)

Como alternativa ao ElevenLabs, você pode usar Piper TTS (local e gratuito):

1. Instale Piper TTS:
   ```bash
   # Linux
   wget https://github.com/rhasspy/piper/releases/download/v1.2.0/piper_amd64.tar.gz
   tar -xzf piper_amd64.tar.gz
   sudo mv piper /usr/local/bin/

   # Ou instale via pip (recomendado)
   pip install piper-tts
   ```

2. Baixe um modelo de voz em português:
   ```bash
   mkdir -p ~/.piper/models
   cd ~/.piper/models
   wget https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx
   wget https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx.json
   ```

3. Configure no `.env`:
   ```
   TTS_PROVIDER=piper
   ```

**Nota**: Piper TTS roda localmente, não requer API keys e funciona offline!

## Uso

1. Inicie o bot:
```bash
python app.py
```

2. O bot se conectará ao Discord e começará a escutar mensagens em todos os canais.

3. O bot processa mensagens usando o provedor de IA configurado (via `MODEL_PROVIDER`) com chamada de funções, permitindo ações inteligentes como:
   - Controle de música (YouTube, Spotify)
   - Síntese de voz (TTS)
   - Gerenciamento de canais de voz
   - Respostas contextuais inteligentes

## Funcionalidades de IA com Chamada de Funções

O bot utiliza o provedor de IA configurado (ZhipuAI GLM, OpenAI GPT ou Google Gemini) como motor de processamento principal, com acesso a 15 ferramentas:

### Ferramentas Disponíveis

1. **GET_Canais** - Lista canais do servidor
2. **GET_UserVoiceChannel** - Encontra canal de voz do usuário
3. **SEND_Mensagem** - Envia mensagem no Discord (única ferramenta para respostas)
4. **EnterChannel** - Entra em canal de voz
5. **LeaveChannel** - Sai do canal de voz
6. **MusicPlay** - Toca música do YouTube/Spotify
7. **MusicStop** - Para música e limpa fila
8. **MusicSkip** - Pula música atual
9. **MusicPause** - Pausa música
10. **MusicResume** - Retoma música
11. **MusicVolume** - Ajusta volume (0-100)
12. **GET_MusicQueue** - Mostra fila de músicas
13. **MusicSpotifyPlay** - Toca Spotify específico
14. **MusicLeave** - Sai do canal e limpa recursos
15. **TTSSpeak** - Síntese de voz via ElevenLabs ou Piper
16. **WebSearch** - Pesquisa na web para obter informações atualizadas

O modelo de IA decide automaticamente quais ferramentas usar baseado no contexto da mensagem do usuário.

## Integração com n8n (Opcional)

Se `N8N_WEBHOOK_URL` estiver configurado, o bot também enviará dados de mensagens processadas para o webhook do n8n:

```json
{
  "content": "Texto da mensagem",
  "author": {
    "id": "123456789",
    "name": "nome_usuario",
    "discriminator": "1234",
    "bot": false
  },
  "channel": {
    "id": "987654321",
    "name": "nome_canal"
  },
  "guild": {
    "id": "111222333",
    "name": "Nome do Servidor"
  },
  "message_id": "444555666",
  "timestamp": "2025-01-15T10:30:00Z",
  "chatbot_response": "Resposta do modelo de IA",
  "tool_calls": [
    {
      "tool": "MusicPlay",
      "parameters": {...},
      "result": {...}
    }
  ]
}
```

**Nota sobre Respostas do Chatbot:**
As respostas do chatbot não são enviadas automaticamente via Discord através da ferramenta `SEND_Mensagem`. Elas estão disponíveis no campo `chatbot_response` do payload enviado para o n8n e podem ser processadas através de tool calls. Para enviar respostas ao Discord via n8n, configure seu workflow para usar o campo `chatbot_response` ou processar as tool calls retornadas.

## Variáveis de Ambiente

**Variáveis Obrigatórias:**
- `DISCORD_BOT_TOKEN` - Token do bot do Discord

**Variáveis de Configuração do Chatbot:**
- `MODEL_PROVIDER` (opcional, padrão: 'zhipu') - Provedor de IA: 'zhipu', 'openai' ou 'gemini'
- `ZHIPU_API_KEY` - Chave da API ZhipuAI GLM (obrigatório se MODEL_PROVIDER=zhipu)
- `OPENAI_API_KEY` - Chave da API OpenAI (obrigatório se MODEL_PROVIDER=openai, também usado para Whisper se WHISPER_PROVIDER=openai)
- `OPENAI_MODEL` (opcional, padrão: 'gpt-4o-mini') - Modelo OpenAI a ser usado.
- `GEMINI_API_KEY` - Chave da API Google Gemini (obrigatório se MODEL_PROVIDER=gemini)

**Variáveis Opcionais:**
- `N8N_WEBHOOK_URL` - URL do webhook do n8n para integração adicional
- `LOG_LEVEL` - Nível de log (padrão: INFO)
- `SPOTIFY_CLIENT_ID` - Client ID do Spotify Developer App
- `SPOTIFY_CLIENT_SECRET` - Client Secret do Spotify Developer App
- `TTS_PROVIDER` - Provedor TTS: 'elevenlabs' ou 'piper' (padrão: elevenlabs)
- `ELEVEN_API_KEY` - Chave da API ElevenLabs para TTS
- `WHISPER_PROVIDER` - Provedor de transcrição de voz: 'zhipu' (GLM-ASR-2512) ou 'openai' (Whisper local) (padrão: zhipu)

**Variáveis de Memória (ChromaDB):**
- `MEMORY_ENABLED` - Habilita memória de longo prazo (padrão: false)
- `CHROMADB_PATH` - Caminho para armazenar dados do ChromaDB (padrão: ./data/chromadb)
- `CHROMADB_COLLECTION_NAME` - Nome da coleção ChromaDB (padrão: tangerina_memory)
- `EMBEDDING_PROVIDER` - Provedor de embeddings: 'sentence_transformers' (padrão) ou 'openai'
- `OPENAI_EMBEDDING_MODEL` - Modelo de embedding OpenAI (padrão: text-embedding-3-small)
- `SENTENCE_TRANSFORMER_MODEL` - Modelo SentenceTransformer (padrão: all-MiniLM-L6-v2)
- `MAX_RETRIEVAL_RESULTS` - Número máximo de memórias a recuperar (padrão: 10)
- `MEMORY_SIMILARITY_THRESHOLD` - Limiar de similaridade para recuperação (padrão: 0.7)
- `MEMORY_RETENTION_DAYS` - Dias de retenção de memórias (padrão: 30)

## Solução de Problemas

### Bot não se conecta

- Verifique se o token do bot está correto
- Verifique se o bot foi convidado para o servidor
- Verifique se as intents necessárias estão habilitadas

### Mensagens não são processadas

- Verifique se a variável `MODEL_PROVIDER` está configurada corretamente
- Verifique se a API key correspondente ao provedor está configurada (`ZHIPU_API_KEY`, `OPENAI_API_KEY` ou `GEMINI_API_KEY`)
- Verifique os logs para erros
- Verifique se o bot tem permissões para ler mensagens no canal
- Se usando n8n, verifique se a URL do webhook está correta

### Bot não lê conteúdo das mensagens

- Certifique-se de que MESSAGE CONTENT INTENT está habilitado nas configurações do bot

### Erro: "PyNaCl library needed in order to use voice"

Este erro ocorre quando o bot tenta entrar em um canal de voz, mas a biblioteca PyNaCl não está instalada.

**Solução:**

1. Instale o PyNaCl:
```bash
pip install PyNaCl
```

2. Se estiver no Windows e encontrar problemas ao instalar PyNaCl:

   - Certifique-se de ter o Microsoft Visual C++ Build Tools instalado
   - Tente instalar apenas binários pré-compilados:
   ```bash
   pip install --only-binary=all PyNaCl
   ```

3. Reinicie o bot após a instalação

**Nota:** O PyNaCl é necessário para funcionalidades de voz no Discord. Certifique-se de que está listado no `requirements.txt` e foi instalado corretamente.

## API REST Endpoints

O bot expõe uma API REST na porta 5000 para controle via HTTP.

### Base URL
```
http://localhost:5000
```

### Health Check

#### GET /health
**Sem corpo de requisição**

**Resposta:**
```json
{
  "status": "ok",
  "bot_ready": true
}
```

### Gerenciamento de Canais de Voz

#### POST /enter-channel
**Corpo da Requisição:**
```json
{
  "guild_id": 123456789012345678,
  "channel_id": 987654321098765432
}
```

**Resposta (Sucesso):**
```json
{
  "success": true,
  "guild_id": 123456789012345678,
  "channel_id": 987654321098765432,
  "channel_name": "General"
}
```

#### POST /leave-channel
**Corpo da Requisição:**
```json
{
  "guild_id": 123456789012345678
}
```

**Resposta (Sucesso):**
```json
{
  "success": true,
  "guild_id": 123456789012345678
}
```

#### GET /user/voice-channel
**Parâmetros de Query:**
- `guild_id` (obrigatório): Inteiro - ID do servidor Discord
- `user_id` (obrigatório): Inteiro - ID do usuário Discord

**Exemplo de Requisição:**
```
GET /user/voice-channel?guild_id=123456789012345678&user_id=987654321098765432
```

**Resposta (Sucesso):**
```json
{
  "success": true,
  "user_id": 987654321098765432,
  "channel_id": 111222333444555666,
  "channel_name": "General"
}
```

**Resposta (Usuário não encontrado):**
```json
{
  "success": false,
  "error": "User not found in any voice channel"
}
```

### Endpoints de Música

#### POST /music/play
**Corpo da Requisição:**
```json
{
  "guild_id": 123456789012345678,
  "channel_id": 987654321098765432,
  "query": "Never Gonna Give You Up"
}
```

**Resposta (Sucesso - Tocando Agora):**
```json
{
  "success": true,
  "song": {
    "title": "Rick Astley - Never Gonna Give You Up",
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "id": "dQw4w9WgXcQ",
    "duration": 213
  },
  "queued": false,
  "message": "Now playing: Rick Astley - Never Gonna Give You Up"
}
```

**Resposta (Sucesso - Na Fila):**
```json
{
  "success": true,
  "song": {
    "title": "Rick Astley - Never Gonna Give You Up",
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "id": "dQw4w9WgXcQ",
    "duration": 213
  },
  "queued": true,
  "message": "Added 'Rick Astley - Never Gonna Give You Up' to queue"
}
```

#### POST /music/stop
**Corpo da Requisição:**
```json
{
  "guild_id": 123456789012345678
}
```

**Resposta (Sucesso):**
```json
{
  "success": true,
  "message": "Music stopped and queue cleared"
}
```

#### POST /music/skip
**Corpo da Requisição:**
```json
{
  "guild_id": 123456789012345678
}
```

**Resposta (Sucesso):**
```json
{
  "success": true,
  "message": "Skipped current song"
}
```

#### POST /music/pause
**Corpo da Requisição:**
```json
{
  "guild_id": 123456789012345678
}
```

**Resposta (Sucesso):**
```json
{
  "success": true,
  "message": "Music paused"
}
```

#### POST /music/resume
**Corpo da Requisição:**
```json
{
  "guild_id": 123456789012345678
}
```

**Resposta (Sucesso):**
```json
{
  "success": true,
  "message": "Music resumed"
}
```

#### POST /music/volume
**Corpo da Requisição:**
```json
{
  "guild_id": 123456789012345678,
  "volume": 75
}
```

**Nota:** `volume` deve ser um inteiro entre 0 e 100.

**Resposta (Sucesso):**
```json
{
  "success": true,
  "volume": 75,
  "message": "Volume set to 75%"
}
```

#### GET /music/queue
**Parâmetros de Query:**
- `guild_id` (obrigatório): Inteiro - ID do servidor Discord

**Exemplo de Requisição:**
```
GET /music/queue?guild_id=123456789012345678
```

**Resposta (Sucesso):**
```json
{
  "queue": [
    {
      "title": "Música 1",
      "url": "https://www.youtube.com/watch?v=...",
      "id": "...",
      "duration": 180
    },
    {
      "title": "Música 2",
      "url": "https://www.youtube.com/watch?v=...",
      "id": "...",
      "duration": 240
    }
  ],
  "current": {
    "title": "Música Tocando Agora",
    "url": "https://www.youtube.com/watch?v=...",
    "id": "...",
    "duration": 200
  }
}
```

#### POST /music/leave
**Corpo da Requisição:**
```json
{
  "guild_id": 123456789012345678
}
```

**Resposta (Sucesso):**
```json
{
  "success": true,
  "message": "Left voice channel"
}
```

#### POST /music/spotify/play
**Corpo da Requisição:**
```json
{
  "guild_id": 123456789012345678,
  "channel_id": 987654321098765432,
  "spotify_uri": "spotify:track:4uLU6hMCjMI75M1A2tKUQC"
}
```

**Formatos Suportados:**

- Track: `spotify:track:4uLU6hMCjMI75M1A2tKUQC` ou `https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC`
- Playlist: `spotify:playlist:37i9dQZF1DXcBWIGoYBM5M` ou `https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M`
- Album: `spotify:album:1ATL5GLyefJaxhQzSPVrLX` ou `https://open.spotify.com/album/1ATL5GLyefJaxhQzSPVrLX`

**Resposta (Sucesso):**

```json
{
  "success": true,
  "tracks_queued": 1,
  "message": "Now playing: Song Title"
}
```

**Resposta (Playlist/Album):**

```json
{
  "success": true,
  "tracks_queued": 15,
  "message": "Added 15 track(s) to queue"
}
```

### Text-to-Speech

#### POST /tts/speak
**Corpo da Requisição:**
```json
{
  "guild_id": 123456789012345678,
  "channel_id": 987654321098765432,
  "text": "Olá! Este é um teste de síntese de voz."
}
```

**Resposta (Sucesso):**
```json
{
  "success": true,
  "message": "Speaking..."
}
```

**Resposta (Erro - Dependência Ausente):**
```json
{
  "success": false,
  "error": "TTS unavailable: missing dependency or ELEVEN_API_KEY"
}
```

#### POST /tts/piper/speak
**Corpo da Requisição:**
```json
{
  "guild_id": 123456789012345678,
  "channel_id": 987654321098765432,
  "text": "Olá! Este é um teste de síntese de voz com Piper."
}
```

**Resposta (Sucesso):**
```json
{
  "success": true,
  "message": "Speaking with Piper..."
}
```

### Chatbot ZhipuAI GLM

#### POST /chatbot/message
**Corpo da Requisição:**
```json
{
  "message": "Olá Tangerina, como você está?",
  "context": [
    {"content": "Mensagem anterior", "author": "user123"}
  ]
}
```

**Resposta (Sucesso):**
```json
{
  "success": true,
  "response": "Olá! Estou bem, obrigado por perguntar! Como posso ajudar você hoje?"
}
```

### Respostas de Erro Comuns

#### 400 Bad Request
```json
{
  "error": "Request body is required"
}
```

#### 503 Service Unavailable
```json
{
  "error": "Bot is not ready yet"
}
```

#### 500 Internal Server Error
```json
{
  "error": "Error message here"
}
```

### Notas sobre a API

- Todos os valores `guild_id` e `channel_id` devem ser inteiros (IDs Discord snowflake)
- Todos os endpoints POST requerem um corpo JSON com `Content-Type: application/json`
- O endpoint `/music/queue` usa parâmetros de query em vez de corpo de requisição
- Valores de timeout:
  - `/music/play` e `/tts/speak`: 30 segundos
  - Todos os outros endpoints: 10 segundos
- O endpoint TTS requer a variável de ambiente `ELEVEN_API_KEY` configurada
- Todos os endpoints de música requerem que o bot esteja em um canal de voz (use `/enter-channel` primeiro)

### Comandos de Voz

O bot Tangerina agora pode escutar comandos de voz em canais de voz do Discord!

#### Como Usar

1. Entre em um canal de voz do Discord
2. Convide o bot para o canal de voz (use `!play` ou comando similar)
3. Fale seu comando naturalmente em português
4. O bot transcreverá sua fala e executará o comando

#### Modo de Escuta (Listening Mode)

O bot possui um modo de escuta especial ativado pela palavra-chave "tangerina":

**Como Funciona:**
1. Quando você diz "tangerina" em um canal de voz, o bot:
   - Reduz o volume da música para 20% automaticamente
   - Entra em modo de escuta por 5 segundos
   - Aguarda comandos conversacionais ou interações com o chatbot

2. Durante o modo de escuta, você pode:
   - Fazer perguntas ao chatbot
   - Dar comandos conversacionais
   - Cancelar o modo de escuta usando palavras-chave: 'cancel', 'cancelar', 'stop', 'parar', 'nevermind', 'esquece'

3. Após 5 segundos sem interação ou após processar o comando:
   - O volume da música é restaurado automaticamente
   - O modo de escuta é desativado

**Nota:** O modo de escuta requer que haja música tocando e que o volume possa ser ajustado.

#### Comandos de Voz Suportados

Todos os comandos de música funcionam por voz:
- "toca [música]" ou "play [música]" → tocar música
- "toca spotify:track:..." ou "play spotify:playlist:..." → tocar do Spotify
- "para" ou "stop" → parar música
- "pula" ou "skip" → pular música
- "pausa" ou "pause" → pausar
- "continua" ou "resume" → retomar
- "volume [0-100]" → ajustar volume
- "fila" ou "queue" → mostrar fila
- "sai" ou "leave" → sair do canal de voz

**Comandos de Chatbot:**
- "tangerina [pergunta]" → ativa modo de escuta e processa pergunta (em canal de voz)
- Conversas normais em canais de texto quando o bot é mencionado

#### Requisitos

- Bot deve estar no mesmo canal de voz
- Provedor de transcrição configurado (GLM-ASR-2512 via ZHIPU_API_KEY ou Whisper local)
- Microfone funcionando e sem ruído excessivo

#### Variáveis de Ambiente

- `WHISPER_PROVIDER` (opcional) - Provedor de transcrição: 'zhipu' (GLM-ASR-2512) ou 'openai' (Whisper local) (padrão: zhipu)
- `ZHIPU_API_KEY` (opcional) - Chave da API ZhipuAI GLM para chatbot e transcrição (necessário se WHISPER_PROVIDER=zhipu)
- `TTS_PROVIDER` (opcional) - Provedor TTS: 'elevenlabs' ou 'piper' (padrão: elevenlabs)
- `ELEVEN_API_KEY` (opcional) - Chave da API ElevenLabs para TTS

#### Docker Build com Whisper

Para usar Whisper local no Docker, construa a imagem com o build arg:

```bash
docker build --build-arg WHISPER_PROVIDER=openai -t tangerina .
```

Se não especificar o build arg, o comportamento padrão (GLM-ASR-2512) será mantido.

#### Notas

- O bot processa comandos quando você para de falar
- Comandos são transcritos e processados automaticamente
- Respostas podem ser por texto ou por voz (TTS)
- Múltiplos usuários podem usar comandos de voz simultaneamente

## Arquivo de Persona

O bot utiliza um arquivo de persona personalizado para definir o comportamento e personalidade da Tangerina:

**Localização:**
- Em execução local: `chatbot/tangerina_persona.txt`
- Em Docker: montado como volume em `/app/tangerina_persona.txt`

**Formato:**
O arquivo deve conter texto em português brasileiro descrevendo a personalidade, estilo de comunicação e características da Tangerina.

**Fallback:**
Se o arquivo não for encontrado, o bot utilizará uma persona padrão embutida no código.

**Importante:** Para usar o arquivo de persona no Docker, certifique-se de montar o volume corretamente no `docker-compose.yaml`.

## Estrutura do Projeto

O projeto está organizado em módulos para facilitar manutenção e extensão:

```
Tangerina/
├── chatbot/              # Integrações com provedores de IA
│   ├── zhipu_integration.py
│   ├── openai_integration.py
│   ├── gemini_integration.py
│   └── model_helper.py
├── features/             # Funcionalidades do bot
│   ├── music/           # Controle de música (YouTube, Spotify)
│   ├── tts/             # Síntese de voz (ElevenLabs, Piper)
│   └── voice/           # Comandos de voz e transcrição
├── deploy/              # Arquivos de deployment
│   ├── docker-compose.yaml
│   ├── Dockerfile
│   ├── piper/          # Serviço Piper TTS
│   └── whisper/        # Serviço Whisper (opcional)
├── app.py              # Arquivo principal do bot
├── flask_routes.py     # API REST
└── requirements.txt    # Dependências Python
```

## Deploy com Docker

O projeto inclui uma configuração completa do Docker Compose para facilitar o deployment:

### Estrutura de Serviços

O `docker-compose.yaml` define os seguintes serviços:

1. **tangerina-bot** - Serviço principal do bot Discord
   - Porta: 5000 (API REST)
   - Volume: `tangerina_persona.txt` (persona do bot)
   - Volume: `logs/` (logs da aplicação)
   - Health check: `/health`

2. **piper-tts** - Serviço de síntese de voz local (opcional)
   - Porta: 5001
   - Volume: modelos Piper TTS
   - Health check: `/health`

3. **n8n** - Serviço de automação (opcional, requer profile)
   - Porta: 5678
   - Acessível apenas quando o profile `n8n` for ativado

### Pré-requisitos

1. Docker e Docker Compose instalados
2. Arquivo `.env` configurado na raiz do projeto
3. Arquivo `tangerina_persona.txt` na raiz do projeto (será montado como volume)

### Deploy

1. Configure o arquivo `.env` com todas as variáveis necessárias
2. Certifique-se de que o arquivo `tangerina_persona.txt` existe na raiz do projeto
3. Execute o docker-compose:
   ```bash
   cd deploy
   docker-compose up -d
   ```

### Iniciar com n8n (opcional)

Para iniciar os serviços incluindo o n8n:
```bash
cd deploy
docker-compose --profile n8n up -d
```

### Verificar Status

Verifique o status dos serviços:
```bash
docker-compose ps
```

Verifique os logs:
```bash
docker-compose logs -f tangerina-bot
```

### Health Checks

Os serviços incluem health checks automáticos:
- Bot principal: `http://localhost:5000/health`
- Piper TTS: `http://localhost:5001/health`

### Variáveis de Ambiente no Docker

Todas as variáveis de ambiente definidas no arquivo `.env` na raiz do projeto são automaticamente carregadas pelo Docker Compose. Certifique-se de configurar:
- `MODEL_PROVIDER` e a respectiva API key
- `DISCORD_BOT_TOKEN`
- Outras variáveis conforme necessário

### Volumes

**Volumes Montados:**
- `tangerina_persona.txt` - Arquivo de persona (read-only)
- `logs/` - Diretório de logs (read-write)
- `piper_models/` - Modelos Piper TTS (gerenciado pelo Docker)
- `n8n_data/` - Dados do n8n (gerenciado pelo Docker)

### Rede

Todos os serviços estão conectados à rede `tangerina-network`, permitindo comunicação entre eles.

## Test Suite

O projeto inclui uma suíte de testes automatizada executada via Docker usando o mesmo container da aplicação principal. Os testes são organizados em testes unitários e de integração, com cobertura de código exigida de pelo menos 70%.

### Executando Testes

Use o script `test.sh` na raiz do projeto para executar os testes:

```bash
./test.sh [comando]
```

**Comandos disponíveis:**

- `all` (padrão) - Executa todos os testes com cobertura
- `unit` - Executa apenas testes unitários (rápido)
- `integration` - Executa apenas testes de integração
- `watch` - Executa testes em modo fail-fast (não é file-watching, apenas pytest com `-f`)
- `coverage` - Executa testes e abre o relatório HTML de cobertura
- `clean` - Remove artefatos de teste e limpa containers Docker

Os testes são executados usando o mesmo Dockerfile e imagem da aplicação principal, eliminando a necessidade de um container separado e reduzindo o uso de recursos e tempo de deployment.

### Cobertura de Código

- **Requisito mínimo:** 70% de cobertura de linha para `chatbot`, `features` e `flask_routes`
- **CI:** GitHub Actions verifica automaticamente o threshold de 70%
- **Local:** `./test.sh all` e `./test.sh coverage` também falham se a cobertura estiver abaixo de 70%
- **Relatório HTML:** Gerado em `htmlcov/index.html` após executar `./test.sh coverage`

### Estrutura de Testes

- **Testes unitários:** `tests/unit/` - Testes de lógica pura com mocks
- **Testes de integração:** `tests/integration/` - Testes com dependências reais (ex: ChromaDB)

### Marcadores pytest

Os testes usam marcadores para categorização:

- `@pytest.mark.unit` - Testes unitários
- `@pytest.mark.integration` - Testes de integração
- `@pytest.mark.chromadb` - Testes que usam ChromaDB
- `@pytest.mark.slow` - Testes lentos
