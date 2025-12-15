# Tangerina Discord Bot

Sistema de bot do Discord inteligente que utiliza GLM-4 (ZhipuAI) como motor de processamento principal, com capacidades de chamada de funções para controle de música, voz e interações Discord.

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

1. Copie o arquivo `.env.example` para `.env`:
```bash
cp .env.example .env
```

2. Edite o arquivo `.env` e configure:

- `DISCORD_BOT_TOKEN`: Token do bot do Discord (obrigatório)
- `ZHIPU_API_KEY`: Chave da API ZhipuAI GLM (obrigatório para funcionalidades inteligentes)
- `N8N_WEBHOOK_URL`: URL do webhook do n8n (opcional - para integração com n8n se desejado)
- `LOG_LEVEL`: Nível de log (opcional, padrão: INFO)

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

## Configuração do Chatbot ZhipuAI GLM (Opcional)

Para habilitar o chatbot inteligente com persona Tangerina:

1. Acesse https://open.bigmodel.cn/ e crie uma conta
2. Obtenha sua API Key
3. Adicione ao arquivo `.env`:
   ```
   ZHIPU_API_KEY=sua_api_key_aqui
   ```

**Funcionalidades do Chatbot:**
- Respostas inteligentes em português brasileiro
- Integração com comandos de música e voz via chamada de funções
- Persona personalizada da Tangerina
- Contexto de conversa mantido
- Processamento inteligente com GLM-4 e acesso a 15 ferramentas
- Decisão automática de ações baseada no contexto

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

3. O bot processa mensagens usando GLM-4 com chamada de funções, permitindo ações inteligentes como:
   - Controle de música (YouTube, Spotify)
   - Síntese de voz (TTS)
   - Gerenciamento de canais de voz
   - Respostas contextuais inteligentes

## Funcionalidades GLM com Chamada de Funções

O bot utiliza GLM-4 como motor de processamento principal, com acesso a 15 ferramentas:

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
15. **TTSSpeak** - Síntese de voz via ElevenLabs

O GLM decide automaticamente quais ferramentas usar baseado no contexto da mensagem do usuário.

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
  "chatbot_response": "Resposta do GLM",
  "tool_calls": [
    {
      "tool": "MusicPlay",
      "parameters": {...},
      "result": {...}
    }
  ]
}
```

## Variáveis de Ambiente

- `DISCORD_BOT_TOKEN` (obrigatório) - Token do bot do Discord
- `ZHIPU_API_KEY` (obrigatório) - Chave da API ZhipuAI GLM para processamento inteligente
- `N8N_WEBHOOK_URL` (opcional) - URL do webhook do n8n para integração adicional
- `LOG_LEVEL` (opcional) - Nível de log (padrão: INFO)
- `SPOTIFY_CLIENT_ID` (opcional) - Client ID do Spotify Developer App
- `SPOTIFY_CLIENT_SECRET` (opcional) - Client Secret do Spotify Developer App
- `TTS_PROVIDER` (opcional) - Provedor TTS: 'elevenlabs' ou 'piper' (padrão: elevenlabs)
- `ELEVEN_API_KEY` (opcional) - Chave da API ElevenLabs para TTS
- `OPENAI_API_KEY` (opcional) - Chave da API OpenAI para transcrição de voz

## Solução de Problemas

### Bot não se conecta

- Verifique se o token do bot está correto
- Verifique se o bot foi convidado para o servidor
- Verifique se as intents necessárias estão habilitadas

### Mensagens não são processadas

- Verifique se `ZHIPU_API_KEY` está configurado corretamente
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
- "tangerina [pergunta]" ou "fala [pergunta]" → conversar com o chatbot
- "conversa [tópico]" ou "chat [tópico]" → iniciar conversa

#### Requisitos

- Bot deve estar no mesmo canal de voz
- OpenAI API Key configurada (para transcrição de voz)
- Microfone funcionando e sem ruído excessivo

#### Variáveis de Ambiente

- `OPENAI_API_KEY` (opcional) - Chave da API OpenAI para Whisper (transcrição de voz)
- `ZHIPU_API_KEY` (opcional) - Chave da API ZhipuAI GLM para chatbot
- `TTS_PROVIDER` (opcional) - Provedor TTS: 'elevenlabs' ou 'piper' (padrão: elevenlabs)
- `ELEVEN_API_KEY` (opcional) - Chave da API ElevenLabs para TTS

#### Notas

- O bot processa comandos quando você para de falar
- Comandos são transcritos e processados automaticamente
- Respostas podem ser por texto ou por voz (TTS)
- Múltiplos usuários podem usar comandos de voz simultaneamente