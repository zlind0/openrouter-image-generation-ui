"""OpenRouter Key 信封加密：AES-256-GCM，主密钥只来自环境变量。"""
import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_master: bytes | None = None


def _master_key() -> bytes:
    global _master
    if _master is None:
        from .config import ensure_master_key

        _master = ensure_master_key()
    return _master


def encrypt_api_key(plaintext: str) -> tuple[str, str]:
    """返回 (ciphertext_b64, nonce_b64)。每次 nonce 随机。"""
    aes = AESGCM(_master_key())
    nonce = os.urandom(12)
    ct = aes.encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(ct).decode(), base64.b64encode(nonce).decode()


def decrypt_api_key(ciphertext_b64: str, nonce_b64: str) -> str:
    aes = AESGCM(_master_key())
    ct = base64.b64decode(ciphertext_b64)
    nonce = base64.b64decode(nonce_b64)
    return aes.decrypt(nonce, ct, None).decode()


def fingerprint(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode()).hexdigest()[:12]


def masked(plaintext: str) -> str:
    if len(plaintext) <= 10:
        return "****"
    return plaintext[:6] + "****" + plaintext[-4:]
