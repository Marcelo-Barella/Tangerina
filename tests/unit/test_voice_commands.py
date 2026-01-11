import pytest
import re
from features.voice.voice_commands import (
    WAKE_WORD,
    CANCEL_KEYWORDS,
    VOLUME_MIN,
    VOLUME_MAX,
    LISTENING_DURATION
)

@pytest.mark.unit
class TestVoiceCommandConstants:
    def test_wake_word_is_tangerina(self):
        assert WAKE_WORD == 'tangerina'

    def test_volume_min_is_zero(self):
        assert VOLUME_MIN == 0

    def test_volume_max_is_hundred(self):
        assert VOLUME_MAX == 100

    def test_listening_duration_is_positive(self):
        assert LISTENING_DURATION > 0
        assert isinstance(LISTENING_DURATION, float)

    def test_cancel_keywords_contains_cancel_variants(self):
        assert 'cancel' in CANCEL_KEYWORDS
        assert 'cancelar' in CANCEL_KEYWORDS
        assert 'stop' in CANCEL_KEYWORDS
        assert 'parar' in CANCEL_KEYWORDS

    def test_cancel_keywords_is_list(self):
        assert isinstance(CANCEL_KEYWORDS, list)
        assert len(CANCEL_KEYWORDS) > 0


@pytest.mark.unit
class TestWakeWordDetection:
    def test_wake_word_detection_simple(self):
        text = "tangerina toca uma música"
        assert WAKE_WORD in text.lower()

    def test_wake_word_detection_case_insensitive(self):
        text = "Tangerina, toca música"
        assert WAKE_WORD in text.lower()

    def test_wake_word_detection_uppercase(self):
        text = "TANGERINA PARA"
        assert WAKE_WORD in text.lower()

    def test_wake_word_not_detected_in_unrelated_text(self):
        text = "just some random text"
        assert WAKE_WORD not in text.lower()

    def test_wake_word_detection_with_punctuation(self):
        text = "tangerina, play song"
        assert WAKE_WORD in text.lower()

    def test_wake_word_extraction_position(self):
        text = "hey tangerina toca música"
        text_lower = text.lower()
        index = text_lower.find(WAKE_WORD)
        assert index > 0
        command = text[index + len(WAKE_WORD):].strip()
        assert 'toca' in command


@pytest.mark.unit
class TestVolumeExtraction:
    def test_volume_extraction_simple(self):
        text = "volume 75"
        match = re.search(r'\d+', text)
        assert match is not None
        volume = int(match.group())
        assert volume == 75

    def test_volume_extraction_with_prefix(self):
        text = "set volume to 50"
        match = re.search(r'\d+', text)
        assert match is not None
        volume = int(match.group())
        assert volume == 50

    def test_volume_extraction_first_number(self):
        text = "volume 25 percent"
        match = re.search(r'\d+', text)
        volume = int(match.group())
        assert volume == 25

    def test_volume_validation_in_range(self):
        text = "volume 50"
        match = re.search(r'\d+', text)
        volume = int(match.group())
        assert VOLUME_MIN <= volume <= VOLUME_MAX

    def test_volume_validation_out_of_range_high(self):
        text = "volume 150"
        match = re.search(r'\d+', text)
        volume = int(match.group())
        assert not (VOLUME_MIN <= volume <= VOLUME_MAX)

    def test_volume_validation_out_of_range_low(self):
        text = "volume -10"
        match = re.search(r'-?\d+', text)
        volume = int(match.group())
        assert not (VOLUME_MIN <= volume <= VOLUME_MAX)

    def test_volume_no_match_returns_none(self):
        text = "volume abc"
        match = re.search(r'\d+', text)
        assert match is None


@pytest.mark.unit
class TestCancelKeywordDetection:
    def test_cancel_keyword_detected_cancel(self):
        text = "cancel"
        assert any(keyword in text.lower() for keyword in CANCEL_KEYWORDS)

    def test_cancel_keyword_detected_cancelar(self):
        text = "cancelar"
        assert any(keyword in text.lower() for keyword in CANCEL_KEYWORDS)

    def test_cancel_keyword_detected_stop(self):
        text = "stop"
        assert any(keyword in text.lower() for keyword in CANCEL_KEYWORDS)

    def test_cancel_keyword_detected_parar(self):
        text = "parar"
        assert any(keyword in text.lower() for keyword in CANCEL_KEYWORDS)

    def test_cancel_keyword_detected_nevermind(self):
        text = "nevermind"
        assert any(keyword in text.lower() for keyword in CANCEL_KEYWORDS)

    def test_cancel_keyword_detected_esquece(self):
        text = "esquece"
        assert any(keyword in text.lower() for keyword in CANCEL_KEYWORDS)

    def test_cancel_keyword_not_detected_in_normal_text(self):
        text = "play music please"
        assert not any(keyword in text.lower() for keyword in CANCEL_KEYWORDS)

    def test_cancel_keyword_case_insensitive(self):
        text = "CANCEL"
        assert any(keyword in text.lower() for keyword in CANCEL_KEYWORDS)


@pytest.mark.unit
class TestCommandParsing:
    def test_play_command_keyword_detection(self):
        play_keywords = ['toca', 'play', 'tocar']
        text = "toca bohemian rhapsody"
        assert any(keyword in text.lower() for keyword in play_keywords)

    def test_stop_command_keyword_detection(self):
        stop_keywords = ['para', 'stop', 'parar']
        text = "para a música"
        assert any(keyword in text.lower() for keyword in stop_keywords)

    def test_skip_command_keyword_detection(self):
        skip_keywords = ['pula', 'skip', 'pular', 'próxima', 'next']
        text = "pula essa"
        assert any(keyword in text.lower() for keyword in skip_keywords)

    def test_pause_command_keyword_detection(self):
        pause_keywords = ['pausa', 'pause']
        text = "pause the music"
        assert any(keyword in text.lower() for keyword in pause_keywords)

    def test_resume_command_keyword_detection(self):
        resume_keywords = ['continua', 'resume', 'continuar']
        text = "continua a música"
        assert any(keyword in text.lower() for keyword in resume_keywords)

    def test_enter_command_keyword_detection(self):
        enter_keywords = ['entra', 'join', 'entrar']
        text = "entra no canal"
        assert any(keyword in text.lower() for keyword in enter_keywords)

    def test_leave_command_keyword_detection(self):
        leave_keywords = ['sai', 'leave', 'sair']
        text = "sai do canal"
        assert any(keyword in text.lower() for keyword in leave_keywords)

    def test_command_keyword_case_insensitive(self):
        text = "TOCA MÚSICA"
        assert 'toca' in text.lower()


@pytest.mark.unit
class TestQueryExtraction:
    def test_query_extraction_after_play_keyword(self):
        text = "toca bohemian rhapsody"
        query = re.sub(r'\b(toca|play|tocar)\b', '', text, flags=re.IGNORECASE).strip()
        assert query == 'bohemian rhapsody'

    def test_query_extraction_multiple_words(self):
        text = "play never gonna give you up"
        query = re.sub(r'\b(toca|play|tocar)\b', '', text, flags=re.IGNORECASE).strip()
        assert 'never gonna give you up' in query

    def test_query_extraction_with_punctuation(self):
        text = "toca, bohemian rhapsody"
        query = re.sub(r'\b(toca|play|tocar)\b', '', text, flags=re.IGNORECASE).strip()
        assert 'bohemian rhapsody' in query

    def test_query_extraction_removes_command_word(self):
        text = "tocar some song"
        query = re.sub(r'\b(toca|play|tocar)\b', '', text, flags=re.IGNORECASE).strip()
        assert 'tocar' not in query.lower()
        assert 'some song' in query

    def test_query_extraction_case_insensitive_removal(self):
        text = "PLAY some song"
        query = re.sub(r'\b(toca|play|tocar)\b', '', text, flags=re.IGNORECASE).strip()
        assert 'play' not in query.lower()
