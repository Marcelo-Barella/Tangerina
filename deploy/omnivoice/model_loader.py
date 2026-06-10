import logging
import os

import torch

from quantize import VRAM_ESTIMATES_GB, apply_precision

logger = logging.getLogger(__name__)


def detect_device() -> str:
    configured = os.getenv("OMNIVOICE_DEVICE", "auto").lower()
    if configured != "auto":
        if configured == "cuda" and not torch.cuda.is_available():
            logger.warning("OMNIVOICE_DEVICE=cuda requested but CUDA unavailable, using cpu")
            return "cpu"
        return configured
    if torch.cuda.is_available():
        return "cuda:0"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def resolve_precision(device: str) -> str:
    configured = os.getenv("OMNIVOICE_PRECISION", "int8").lower()
    if configured == "auto":
        if device.startswith("cuda"):
            props = torch.cuda.get_device_properties(0)
            total_gb = props.total_memory / (1024 ** 3)
            return "int8" if total_gb <= 8 else "fp16"
        return "int8"
    return configured


def load_dtype(device: str) -> torch.dtype:
    if device == "cpu":
        return torch.float32
    return torch.float16


def load_omnivoice_model():
    from omnivoice import OmniVoice

    device = detect_device()
    precision = resolve_precision(device)
    dtype = load_dtype(device)
    load_asr = os.getenv("OMNIVOICE_LOAD_ASR", "false").lower() == "true"
    model_id = os.getenv("OMNIVOICE_MODEL", "k2-fsa/OmniVoice")

    logger.info(
        "Loading OmniVoice model=%s device=%s precision=%s load_asr=%s",
        model_id,
        device,
        precision,
        load_asr,
    )

    model = OmniVoice.from_pretrained(
        model_id,
        device_map=device,
        dtype=dtype,
        load_asr=load_asr,
    )

    if precision in ("int8", "int4"):
        model, precision = apply_precision(model, precision)

    return {
        "model": model,
        "device": device,
        "precision": precision,
        "model_id": model_id,
        "vram_estimate_gb": VRAM_ESTIMATES_GB.get(precision, 6.0),
    }
