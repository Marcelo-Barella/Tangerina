import logging
import time
from typing import Any, Callable, Tuple

logger = logging.getLogger(__name__)
_patched = False
_crypto_patched = False


def _decode_with_fec(decoder: Any, packet_data: bytes) -> bytes:
    return decoder.decode(packet_data, fec=True)


def _decode_plc(decoder: Any) -> bytes | None:
    try:
        return decoder.decode(None, fec=False)
    except Exception:
        return None


def _recover_opus_decode(decoder: Any, packet_data: bytes, exc: Exception, ssrc: Any) -> bytes:
    try:
        return _decode_with_fec(decoder, packet_data)
    except Exception:
        pcm = _decode_plc(decoder)
        if pcm:
            return pcm
        logger.warning("Opus decode failed for ssrc %s after FEC recovery", ssrc)
        raise exc


def _wrap_decryptor_for_crypto_resync(reader: Any) -> None:
    if getattr(reader.decryptor, "_tangerina_crypto_wrap", False):
        return
    try:
        from nacl.exceptions import CryptoError
    except ImportError:
        return

    decryptor = reader.decryptor

    def wrap(method_name: str) -> None:
        original = getattr(decryptor, method_name)

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            try:
                return original(*args, **kwargs)
            except CryptoError:
                try:
                    decryptor.update_secret_key(bytes(reader.voice_client.secret_key))
                except Exception:
                    logger.warning(
                        "Failed to resync voice secret_key after CryptoError",
                        exc_info=True,
                    )
                try:
                    return original(*args, **kwargs)
                except CryptoError:
                    sink = getattr(reader, "sink", None)
                    if sink is not None and hasattr(sink, "note_crypto_error"):
                        sink.note_crypto_error()
                    raise

        wrapped._tangerina_crypto_wrap = True
        setattr(decryptor, method_name, wrapped)

    for name in ("decrypt_rtp", "decrypt_rtcp"):
        if hasattr(decryptor, name):
            wrap(name)
    decryptor._tangerina_crypto_wrap = True


def _patch_audio_reader_crypto_resync() -> None:
    global _crypto_patched
    if _crypto_patched:
        return
    try:
        from discord.ext.voice_recv.reader import AudioReader
    except ImportError:
        return
    if getattr(AudioReader, "_tangerina_reader_patched", False):
        _crypto_patched = True
        return

    original_init = AudioReader.__init__

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        _wrap_decryptor_for_crypto_resync(self)

    AudioReader.__init__ = __init__
    AudioReader._tangerina_reader_patched = True
    _crypto_patched = True
    logger.info("Applied voice_recv CryptoError secret_key resync patch")


def apply_voice_recv_patches() -> None:
    global _patched
    if _patched:
        _patch_audio_reader_crypto_resync()
        return
    try:
        from discord.ext.voice_recv import opus as vr_opus
        from discord.opus import OpusError
    except ImportError:
        _patch_audio_reader_crypto_resync()
        return
    if getattr(vr_opus.PacketDecoder._decode_packet, "_tangerina_patched", False):
        _patched = True
        _patch_audio_reader_crypto_resync()
        return
    original_decode: Callable[..., Tuple[Any, bytes]] = vr_opus.PacketDecoder._decode_packet

    def _decode_packet_resilient(self: Any, packet: Any) -> Tuple[Any, bytes]:
        assert self._decoder is not None
        if not packet:
            return original_decode(self, packet)
        try:
            pcm = self._decoder.decode(packet.decrypted_data, fec=False)
            return packet, pcm
        except OpusError as exc:
            pcm = _recover_opus_decode(self._decoder, packet.decrypted_data, exc, getattr(self, "ssrc", "?"))
            return packet, pcm

    _decode_packet_resilient._tangerina_patched = True
    vr_opus.PacketDecoder._decode_packet = _decode_packet_resilient
    _patched = True
    logger.info("Applied voice_recv FEC resilience patch")
    _patch_audio_reader_crypto_resync()
