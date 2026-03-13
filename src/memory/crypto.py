"""Per-driver encryption using AES-256-GCM with HKDF-derived keys.

Master key comes from BETTY_MEMORY_KEY env var.
Each driver gets a unique derived key: HKDF(master, driver_id).
Nothing is stored except the encrypted blob + nonce.
"""

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

_SALT = b"betty-driver-memory-v1"


def _get_master_key() -> bytes:
    """Get master key from environment. Raises if not set."""
    key = os.environ.get("BETTY_MEMORY_KEY", "")
    if not key:
        raise RuntimeError(
            "BETTY_MEMORY_KEY environment variable not set. "
            "Set it to any random string (32+ chars recommended)."
        )
    return key.encode("utf-8")


def _derive_key(driver_id: str) -> bytes:
    """Derive a 32-byte AES key for a specific driver using HKDF."""
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_SALT,
        info=driver_id.encode("utf-8"),
    )
    return hkdf.derive(_get_master_key())


def encrypt(driver_id: str, plaintext: bytes) -> bytes:
    """Encrypt data for a specific driver. Returns nonce + ciphertext."""
    key = _derive_key(driver_id)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)  # 96-bit nonce for AES-GCM
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return nonce + ciphertext


def decrypt(driver_id: str, blob: bytes) -> bytes:
    """Decrypt data for a specific driver. Input is nonce + ciphertext."""
    if len(blob) < 13:  # 12-byte nonce + at least 1 byte
        raise ValueError("Invalid encrypted blob")
    key = _derive_key(driver_id)
    aesgcm = AESGCM(key)
    nonce = blob[:12]
    ciphertext = blob[12:]
    return aesgcm.decrypt(nonce, ciphertext, None)
