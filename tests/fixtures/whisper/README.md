# Golden Portuguese utterance containing the wake word "tangerina".
#
# Regenerate (prefer espeak-ng when installed):
#   espeak-ng -v pt -w /tmp/pt_tangerina_raw.wav "tangerina tocar musica"
#   ffmpeg -y -i /tmp/pt_tangerina_raw.wav -ac 1 -ar 16000 tests/fixtures/whisper/pt_tangerina.wav
#
# Fallback used to create the checked-in file (no espeak on host):
#   Google Translate TTS (pt) for the same phrase, then ffmpeg to 16k mono WAV.
