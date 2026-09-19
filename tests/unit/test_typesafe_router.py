from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chatbot.typesafe_candidates import music_play_query_candidates, volume_candidates
from chatbot.typesafe_router import TypeSafeToolRouter, VoiceTranscriptDecision


class TestTypeSafeCandidates:
    def test_music_play_candidates_strip_command_words(self):
        criteria = music_play_query_candidates("Tangerina, toca Bohemian Rhapsody")
        values = list(criteria.values())
        assert any("Bohemian" in v for v in values)

    def test_volume_candidates_extract_digits(self):
        criteria = volume_candidates("volume cinquenta 40 por favor")
        assert "40" in criteria.values()


@pytest.fixture
def router_with_key(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    monkeypatch.setenv("TYPESAFE_ENABLED", "true")
    return TypeSafeToolRouter(api_key="test-key")


def _mock_system_one_result(choices=None, nouls=None, scores=None):
    result = MagicMock()
    result.choices = choices or {}
    result.nouls = nouls or {}
    result.scores = scores or {}
    return result


def _choice(name, choice, confidence=0.9):
    answer = MagicMock()
    answer.choice = choice
    answer.confidence = confidence
    return {name: answer}


def _noul(name, noul, confidence=0.9):
    answer = MagicMock()
    answer.noul = noul
    answer.confidence = confidence
    return {name: answer}


def _score(name, score, confidence=0.9):
    answer = MagicMock()
    answer.score = score
    answer.confidence = confidence
    return {name: answer}


@pytest.mark.asyncio
async def test_try_route_user_turn_none_when_disabled(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    router = TypeSafeToolRouter(api_key=None)
    chatbot = MagicMock()
    out = await router.try_route_user_turn(chatbot, "para a musica", 1, 2, 3, {})
    assert out is None


@pytest.mark.asyncio
async def test_try_route_music_stop(router_with_key):
    router = router_with_key
    chatbot = MagicMock()
    chatbot._call_tool = AsyncMock(
        return_value={"success": True, "message": "Música parada"}
    )

    mock_result = _mock_system_one_result(
        choices=_choice("tool_route", "MusicStop"),
    )

    with patch.object(router, "_system_one", AsyncMock(return_value=mock_result)):
        text, tool_calls = await router.try_route_user_turn(
            chatbot, "para a musica", guild_id=10, channel_id=20, user_id=30, app_functions={}
        )

    assert text == "Ação executada."
    assert tool_calls[0]["tool"] == "MusicStop"
    chatbot._call_tool.assert_awaited_once()


@pytest.mark.asyncio
async def test_try_route_low_confidence_falls_back(router_with_key):
    router = router_with_key
    chatbot = MagicMock()
    mock_result = _mock_system_one_result(
        choices=_choice("tool_route", "MusicStop", confidence=0.2),
    )
    with patch.object(router, "_system_one", AsyncMock(return_value=mock_result)):
        out = await router.try_route_user_turn(
            chatbot, "para", guild_id=1, channel_id=2, user_id=3, app_functions={}
        )
    assert out is None


@pytest.mark.asyncio
async def test_voice_transcript_legacy_when_typesafe_disabled(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    router = TypeSafeToolRouter(api_key=None)
    decision = await router.evaluate_voice_transcript(
        "tangerina oi",
        listening_mode=False,
        wake_word_present=True,
    )
    assert decision.use_legacy_routing is True
    assert decision.usable is True


@pytest.mark.asyncio
async def test_voice_transcript_ignore_on_low_usability(router_with_key):
    router = router_with_key
    mock_result = _mock_system_one_result(
        nouls=_noul("usable_speech", 0.1, confidence=0.9),
        choices=_choice("voice_path", "ignore"),
        scores=_score("transcript_quality", 2, confidence=0.9),
    )
    with patch.object(router, "_system_one", AsyncMock(return_value=mock_result)):
        decision = await router.evaluate_voice_transcript(
            "mmm",
            listening_mode=False,
            wake_word_present=False,
        )
    assert decision.usable is False
    assert decision.path == "ignore"


@pytest.mark.asyncio
async def test_tts_should_not_speak(router_with_key):
    router = router_with_key
    mock_result = _mock_system_one_result(
        nouls=_noul("should_speak", 0.1, confidence=0.95),
        choices=_choice("tts_provider", "piper"),
        scores=_score("music_duck", 1),
    )
    with patch.object(router, "_system_one", AsyncMock(return_value=mock_result)):
        decision = await router.evaluate_tts_playback(
            "ok",
            ["piper"],
            music_playing=True,
            default_provider="piper",
        )
    assert decision.should_speak is False
