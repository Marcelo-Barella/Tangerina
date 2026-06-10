import logging

logger = logging.getLogger(__name__)

VRAM_ESTIMATES_GB = {
    "fp16": 6.0,
    "int8": 3.5,
    "int4": 2.2,
}


def apply_precision(model, precision: str):
    precision = (precision or "int8").lower()
    if precision == "fp16":
        return model, precision

    if precision == "int8":
        try:
            from torchao.quantization import int8_weight_only, quantize_

            quantize_(model, int8_weight_only())
            logger.info("Applied INT8 weight-only quantization")
            return model, "int8"
        except Exception as exc:
            logger.warning("INT8 quantization failed, using fp16: %s", exc)
            return model, "fp16"

    if precision == "int4":
        try:
            from torchao.quantization import int4_weight_only, quantize_

            quantize_(model, int4_weight_only())
            logger.info("Applied INT4 weight-only quantization")
            return model, "int4"
        except Exception as exc:
            logger.warning("INT4 quantization failed, using fp16: %s", exc)
            return model, "fp16"

    logger.warning("Unknown precision %s, using fp16", precision)
    return model, "fp16"
