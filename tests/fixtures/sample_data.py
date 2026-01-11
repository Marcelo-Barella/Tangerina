SAMPLE_DISCORD_MESSAGE = {
    'content': 'Tangerina, toca música',
    'author_id': 515664341194768385,
    'guild_id': 123456789,
    'channel_id': 987654321
}

SAMPLE_TOOL_CALL_RESPONSE = {
    'choices': [{
        'message': {
            'tool_calls': [{
                'function': {
                    'name': 'MusicPlay',
                    'arguments': '{"guild_id": 123456789, "channel_id": 987654321, "query": "test song"}'
                },
                'id': 'call_123'
            }]
        }
    }]
}

SAMPLE_SPOTIFY_TRACK = {
    'id': 'abc123',
    'name': 'Bohemian Rhapsody',
    'artists': [{'name': 'Queen'}],
    'duration_ms': 354000,
    'album': {'name': 'A Night at the Opera'}
}

SAMPLE_SPOTIFY_PLAYLIST_TRACKS = [
    {
        'track': {
            'name': 'Another One Bites the Dust',
            'artists': [{'name': 'Queen'}],
            'id': 'def456'
        }
    },
    {
        'track': {
            'name': 'We Will Rock You',
            'artists': [{'name': 'Queen'}],
            'id': 'ghi789'
        }
    }
]

SAMPLE_YOUTUBE_DATA = {
    'title': 'Queen - Bohemian Rhapsody',
    'url': 'https://youtube.com/watch?v=test123',
    'duration': '5:55',
    'thumbnail': 'https://i.ytimg.com/vi/test123/default.jpg'
}

SAMPLE_CONVERSATION_CONTEXT = [
    {'role': 'user', 'content': 'Oi Tangerina'},
    {'role': 'assistant', 'content': 'Oi! Como posso ajudar?'},
    {'role': 'user', 'content': 'Toca uma música'},
]

SAMPLE_XML_TOOL_CALL = '<function_call><tool_name>MusicPlay</tool_name><parameters><arg_key>guild_id</arg_key><arg_value>123456789</arg_value><arg_key>channel_id</arg_key><arg_value>987654321</arg_value><arg_key>query</arg_key><arg_value>test song</arg_value></parameters></function_call>'

SAMPLE_JSON_TOOL_CALL = '''
{
    "function": "MusicPlay",
    "parameters": {
        "guild_id": 123456789,
        "channel_id": 987654321,
        "query": "test song"
    }
}
'''

SAMPLE_VOICE_COMMANDS = [
    "tangerina toca bohemian rhapsody",
    "tangerina para a música",
    "tangerina pula essa",
    "tangerina volume 50",
    "cancelar",
    "tangerina entra no canal",
]

SAMPLE_MEMORY_ENTRIES = [
    {
        'content': 'User asked about weather',
        'metadata': {
            'guild_id': '123456789',
            'channel_id': '987654321',
            'user_id': '515664341194768385',
            'timestamp': '2024-01-01T12:00:00'
        }
    },
    {
        'content': 'Bot played music for user',
        'metadata': {
            'guild_id': '123456789',
            'channel_id': '987654321',
            'user_id': '515664341194768385',
            'timestamp': '2024-01-01T12:05:00'
        }
    }
]
