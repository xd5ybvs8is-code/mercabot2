"""DPoP (Demonstrating Proof-of-Possession) JWT-подпись для Mercari API.

Mercari требует на каждый запрос к api.mercari.jp заголовок `dpop` —
подписанный ES256 JWT (RFC 9449). Экспериментально подтверждено:
- ключ генерируется клиентом (один на сессию);
- сервер не привязывает ключ к конкретному device-uuid — лишь бы подпись
  была валидна, а uuid совпадал с тем, что в теле запроса (laplaceDeviceUuid);
- поле `jti` НЕ валидируется на replay, но мы всё равно делаем его уникальным.
"""

from __future__ import annotations

import base64
import json
import logging
import time
import uuid as uuidlib

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

logger = logging.getLogger(__name__)

# Смещение signing-input → компактный JWT. header.payload всегда валидный JSON
# без паддинга — это часть спецификации JWT.


def _b64url_bytes(raw: bytes) -> str:
    """base64url без паддинга (RFC 7515)."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64url_json(obj: dict) -> str:
    return _b64url_bytes(json.dumps(obj, separators=(",", ":")).encode())


def _int_to_b64url(n: int) -> str:
    """EC-координate (x или y) → 32 байта big-endian → base64url."""
    return _b64url_bytes(n.to_bytes(32, "big"))


class DpopSigner:
    """Подписывает DPoP-JWT одним EC P-256 ключом.

    Ключ генерируется один раз в конструкторе и переиспользуется на все
    запросы (экспериментально: Mercari принимает один и тот же ключ минутами).
    """

    def __init__(self, device_uuid: str) -> None:
        if not device_uuid:
            raise ValueError("device_uuid must be a non-empty string")
        self._device_uuid = device_uuid
        self._priv = ec.generate_private_key(ec.SECP256R1())
        nums = self._priv.public_key().public_numbers()
        # Public JWK встраивается в header — сервер по нему проверяет подпись.
        self._jwk = {
            "crv": "P-256",
            "kty": "EC",
            "x": _int_to_b64url(nums.x),
            "y": _int_to_b64url(nums.y),
        }
        self._header = {"typ": "dpop+jwt", "alg": "ES256", "jwk": self._jwk}

    @property
    def device_uuid(self) -> str:
        return self._device_uuid

    def sign(self, method: str, url: str) -> str:
        """Возвращает компактный DPoP-JWT для HTTP-запроса (method, url).

        На каждый вызов — свежие iat/jti. htu/htm должны совпадать с реальным
        запросом: Mercari валидирует их (экспериментально подтверждено).
        """
        header_b64 = _b64url_json(self._header)
        now = int(time.time())
        jti = str(uuidlib.uuid4())
        payload = {
            "iat": now,
            "jti": jti,
            "htu": url,
            "htm": method.upper(),
            "uuid": self._device_uuid,
        }
        payload_b64 = _b64url_json(payload)

        signing_input = f"{header_b64}.{payload_b64}".encode()
        der_sig = self._priv.sign(signing_input, ec.ECDSA(hashes.SHA256()))
        # ES256 требует raw-формат (R || S, по 32 байта), а cryptography
        # отдаёт DER — конвертируем.
        r, s = decode_dss_signature(der_sig)
        signature_b64 = _b64url_bytes(r.to_bytes(32, "big") + s.to_bytes(32, "big"))

        token = f"{header_b64}.{payload_b64}.{signature_b64}"
        logger.debug(
            "🔑 DPoP signed: %s %s | jti=%s | iat=%s | token_len=%s",
            method, url, jti, now, len(token),
        )
        return token
