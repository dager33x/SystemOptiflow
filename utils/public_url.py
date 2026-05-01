import os
import logging
import re

logger = logging.getLogger(__name__)

_PUBLIC_URL_RE = re.compile(r"^https?://", re.IGNORECASE)

def normalize_public_base_url(value: str | None) -> str:
    normalized = (value or "").strip()
    if not normalized:
        return ""
    if "://" in normalized and not _PUBLIC_URL_RE.match(normalized):
        logger.warning("Ignoring PUBLIC_BASE_URL with unsupported scheme.")
        return ""
    if not _PUBLIC_URL_RE.match(normalized):
        normalized = f"https://{normalized}"
    return normalized.rstrip("/")


def get_public_base_url() -> str:
    return normalize_public_base_url(os.getenv("PUBLIC_BASE_URL"))
