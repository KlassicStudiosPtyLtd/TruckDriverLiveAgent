"""Unit tests for memory encryption — no API key needed."""

import os
import pytest

# Set test key before importing crypto module
os.environ["BETTY_MEMORY_KEY"] = "test-key-for-unit-tests-1234567890"

from src.memory.crypto import encrypt, decrypt, _derive_key


class TestEncryptDecrypt:
    """Test AES-256-GCM encrypt/decrypt round-trip."""

    def test_round_trip(self):
        plaintext = b"Hello, Dazza!"
        blob = encrypt("DRV-001", plaintext)
        result = decrypt("DRV-001", blob)
        assert result == plaintext

    def test_round_trip_unicode(self):
        plaintext = "G'day mate, how's the drive? ".encode("utf-8")
        blob = encrypt("DRV-001", plaintext)
        result = decrypt("DRV-001", blob)
        assert result == plaintext

    def test_round_trip_json(self):
        import json
        data = [{"summary": "Driver was tired", "mood": "grumpy"}]
        plaintext = json.dumps(data).encode("utf-8")
        blob = encrypt("DRV-001", plaintext)
        result = json.loads(decrypt("DRV-001", blob))
        assert result == data

    def test_different_drivers_different_ciphertext(self):
        plaintext = b"Same message"
        blob1 = encrypt("DRV-001", plaintext)
        blob2 = encrypt("DRV-002", plaintext)
        # Ciphertexts should differ (different derived keys + random nonces)
        assert blob1 != blob2

    def test_wrong_driver_cannot_decrypt(self):
        plaintext = b"Secret message"
        blob = encrypt("DRV-001", plaintext)
        with pytest.raises(Exception):  # InvalidTag from AES-GCM
            decrypt("DRV-002", blob)

    def test_tampered_blob_fails(self):
        plaintext = b"Sensitive data"
        blob = encrypt("DRV-001", plaintext)
        tampered = blob[:-1] + bytes([blob[-1] ^ 0xFF])
        with pytest.raises(Exception):
            decrypt("DRV-001", tampered)

    def test_too_short_blob_fails(self):
        with pytest.raises(ValueError, match="Invalid encrypted blob"):
            decrypt("DRV-001", b"short")

    def test_empty_blob_fails(self):
        with pytest.raises(ValueError):
            decrypt("DRV-001", b"")

    def test_nonce_is_unique(self):
        plaintext = b"Same plaintext"
        blob1 = encrypt("DRV-001", plaintext)
        blob2 = encrypt("DRV-001", plaintext)
        # First 12 bytes are the nonce — should differ
        assert blob1[:12] != blob2[:12]


class TestKeyDerivation:
    """Test HKDF key derivation."""

    def test_same_driver_same_key(self):
        key1 = _derive_key("DRV-001")
        key2 = _derive_key("DRV-001")
        assert key1 == key2

    def test_different_drivers_different_keys(self):
        key1 = _derive_key("DRV-001")
        key2 = _derive_key("DRV-002")
        assert key1 != key2

    def test_key_is_32_bytes(self):
        key = _derive_key("DRV-001")
        assert len(key) == 32


class TestMissingMasterKey:
    """Test behavior when BETTY_MEMORY_KEY is not set."""

    def test_missing_key_raises(self):
        original = os.environ.pop("BETTY_MEMORY_KEY", None)
        try:
            with pytest.raises(RuntimeError, match="BETTY_MEMORY_KEY"):
                encrypt("DRV-001", b"test")
        finally:
            if original:
                os.environ["BETTY_MEMORY_KEY"] = original
