from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core.config import OAUTH_TOKEN_ENCRYPTION_KEY, OAUTH_TOKEN_ENCRYPTION_KEYS

_ENC_PREFIX = "enc:v1:"


def _configured_keys() -> list[str]:
    raw: list[str] = []
    if OAUTH_TOKEN_ENCRYPTION_KEYS:
        raw.extend([k.strip() for k in str(OAUTH_TOKEN_ENCRYPTION_KEYS).split(",") if str(k).strip()])
    if OAUTH_TOKEN_ENCRYPTION_KEY:
        key = str(OAUTH_TOKEN_ENCRYPTION_KEY).strip()
        if key and key not in raw:
            raw.append(key)
    return raw


@lru_cache(maxsize=1)
def _fernet() -> MultiFernet | None:
    keys = _configured_keys()
    if not keys:
        return None
    return MultiFernet([Fernet(k.encode("utf-8")) for k in keys])


def token_encryption_enabled() -> bool:
    return _fernet() is not None


def ensure_token_encryption_ready() -> None:
    """
    Fail fast when encryption keys are misconfigured.
    """
    if not _configured_keys():
        raise RuntimeError(
            "OAUTH_TOKEN_ENCRYPTION_KEY (or OAUTH_TOKEN_ENCRYPTION_KEYS) must be set"
        )
    # Force key validation now.
    _fernet()


def is_encrypted_secret(value: str | None) -> bool:
    return str(value or "").startswith(_ENC_PREFIX)


def encrypt_secret(value: str | None) -> str:
    plain = str(value or "")
    if plain == "":
        return ""
    f = _fernet()
    if f is None:
        raise RuntimeError("token_encryption_not_configured")
    token = f.encrypt(plain.encode("utf-8")).decode("utf-8")
    return f"{_ENC_PREFIX}{token}"


def decrypt_secret(value: str | None, *, allow_plaintext: bool = False) -> str:
    raw = str(value or "")
    if raw == "":
        return ""
    if not is_encrypted_secret(raw):
        if allow_plaintext:
            return raw
        raise RuntimeError("token_not_encrypted")

    f = _fernet()
    if f is None:
        raise RuntimeError("token_encryption_not_configured")
    token = raw[len(_ENC_PREFIX):]
    try:
        return f.decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        raise RuntimeError("token_decrypt_failed")
