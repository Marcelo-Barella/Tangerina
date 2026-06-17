import logging
from typing import Any, Tuple

logger = logging.getLogger(__name__)

_patched = False


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

    original_decode = vr_opus.PacketDecoder._decode_packet

    def _decode_packet_resilient(self: Any, packet: Any) -> Tuple[Any, bytes]:
        assert self._decoder is not None
        if not packet:
            return original_decode(self, packet)
        try:
            pcm = self._decoder.decode(packet.decrypted_data, fec=False)
            return packet, pcm
        except OpusError as exc:
            try:
                pcm = self._decoder.decode(packet.decrypted_data, fec=True)
                return packet, pcm
            except OpusError:
                try:
                    pcm = self._decoder.decode(None, fec=False)
                    if pcm:
                        return packet, pcm
                except OpusError:
                    pass
                logger.warning(
                    "Opus decode failed for ssrc %s after FEC recovery",
                    getattr(self, 'ssrc', '?'),
                )
                raise exc

    _decode_packet_resilient._tangerina_patched = True  # type: ignore[attr-defined]
    vr_opus.PacketDecoder._decode_packet = _decode_packet_resilient
    _patched = True
    logger.info("Applied voice_recv FEC resilience patch")
