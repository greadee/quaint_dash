"""Local secret cipher utilities for broker provider user secrets."""

from __future__ import annotations

import base64
import hashlib
import hmac


class LocalSecretCipher:
    """Small reversible cipher for local encrypted-at-rest provider secrets.

    This avoids storing provider user secrets as plaintext. Production deployments
    should prefer OS keyring or a managed KMS-backed cipher with the same interface.
    """

    name = "local-hmac-xor-v1"

    def __init__(self, key: str) -> None:
        if not key:
            raise ValueError("broker secret key is required")
        self._key = key.encode("utf-8")

    def encrypt(self, plaintext: str) -> str:
        data = plaintext.encode("utf-8")
        nonce = hmac.new(self._key, data, hashlib.sha256).digest()[:16]
        stream = self._keystream(nonce, len(data))
        encrypted = bytes(byte ^ stream[i] for i, byte in enumerate(data))
        return base64.urlsafe_b64encode(nonce + encrypted).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        payload = base64.urlsafe_b64decode(ciphertext.encode("ascii"))
        nonce = payload[:16]
        encrypted = payload[16:]
        stream = self._keystream(nonce, len(encrypted))
        data = bytes(byte ^ stream[i] for i, byte in enumerate(encrypted))
        return data.decode("utf-8")

    def _keystream(self, nonce: bytes, length: int) -> bytes:
        chunks = []
        counter = 0
        while sum(len(chunk) for chunk in chunks) < length:
            counter_bytes = counter.to_bytes(8, "big")
            chunks.append(hmac.new(self._key, nonce + counter_bytes, hashlib.sha256).digest())
            counter += 1
        return b"".join(chunks)[:length]

