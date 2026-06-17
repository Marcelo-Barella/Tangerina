import logging
from typing import Any, Callable, Tuple
logger = logging.getLogger(__name__)
_patched = False
def _recover_opus_decode(decoder: Any, packet_data: bytes, exc: Exception, ssrc: Any) -> bytes:
    try:
        return decoder.decode(packet_data, fec=True)
    except Exception:
        try:
            pcm = decoder.decode(None, fec=False)
        except Exception:
            pcm = None
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
            pcm = _recover_opus_decode(self._decoder, packet.decrypted_data, exc, getattr(self, 'ssrc', '?'))
            return packet, pcm
    _decode_packet_resilient._tangerina_patched = True
    vr_opus.PacketDecoder._decode_packet = _decode_packet_resilient
    _patched = True
    logger.info("Applied voice_recv FEC resilience patch")
