from unittest.mock import MagicMock, AsyncMock

def create_mock_guild(guild_id=123456789, name="Test Guild"):
    guild = MagicMock()
    guild.id = guild_id
    guild.name = name
    guild.voice_channels = []
    guild.text_channels = []
    guild.me = MagicMock()
    guild.get_channel = MagicMock(return_value=None)
    return guild

def create_mock_voice_channel(channel_id=987654321, name="Test Voice", guild=None):
    channel = MagicMock()
    channel.id = channel_id
    channel.name = name
    channel.type = MagicMock()
    channel.type.name = "voice"
    channel.guild = guild or create_mock_guild()
    channel.members = []
    return channel

def create_mock_text_channel(channel_id=111222333, name="Test Text", guild=None):
    channel = MagicMock()
    channel.id = channel_id
    channel.name = name
    channel.type = MagicMock()
    channel.type.name = "text"
    channel.guild = guild or create_mock_guild()
    channel.send = AsyncMock()
    channel.permissions_for = MagicMock(return_value=MagicMock(send_messages=True))
    return channel

def create_mock_member(user_id=515664341194768385, name="TestUser", voice_channel=None):
    member = MagicMock()
    member.id = user_id
    member.display_name = name
    member.name = name
    if voice_channel:
        member.voice = MagicMock()
        member.voice.channel = voice_channel
    else:
        member.voice = None
    return member

def create_mock_voice_client(guild_id=123456789, channel=None):
    vc = MagicMock()
    vc.guild = MagicMock()
    vc.guild.id = guild_id
    vc.channel = channel or create_mock_voice_channel()
    vc.is_connected = MagicMock(return_value=True)
    vc.is_playing = MagicMock(return_value=False)
    vc.play = MagicMock()
    vc.stop = MagicMock()
    vc.pause = MagicMock()
    vc.resume = MagicMock()
    vc.disconnect = AsyncMock()
    vc.source = None
    return vc
