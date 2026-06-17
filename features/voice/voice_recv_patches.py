import logging
from typing import Any, Callable, Tuple

logger = logging.getLogger(__name__)

_patched = False


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


def apply_voice_recv_patches() -> None:
    global _patched
    if _patched:
        return
    try:
        from discord.ext.voice_recv import opus as vr_opus
        from discord.opus import OpusError
    except ImportError:
        return

    if getattr(vr_opus.PacketDecoder._decode_packet, '_tangerina_patched', False):
        _patched = True
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
            pcm = _recover_opus_decode(
                self._decoder,
                packet.decrypted_data,
                exc,
                getattr(self, 'ssrc', '?'),
            )
            return packet, pcm

    _decode_packet_resilient._tangerina_patched = True  # type: ignore[attr-defined]
    vr_opus.PacketDecoder._decode_packet = _decode_packet_resilient
    _patched = True
    logger.info("Applied voice_recv FEC resilience patch")
