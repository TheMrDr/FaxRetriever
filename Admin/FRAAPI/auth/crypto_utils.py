# auth/crypto_utils.py

import base64
import json
import os

from config import SYSTEM_ACTOR
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from core.logger import log_event_v2


class CryptoError(Exception):
    """Custom error for encryption/decryption failures."""

    pass


def derive_key(passphrase: str, salt: bytes, iterations: int = 100_000) -> bytes:
    """
    Derives a symmetric key from the given passphrase and salt.
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations
    )
    return kdf.derive(passphrase.encode("utf-8"))


def encrypt_blob(passphrase: str, payload: dict) -> dict:
    """
    Encrypts a dictionary into a sealed blob using AES-GCM.

    Args:
        passphrase (str): Base key string (e.g., reseller_id)
        payload (dict): Plaintext data to encrypt

    Returns:
        dict: Encrypted blob with base64-encoded fields
    """
    try:
        plaintext = json.dumps(payload).encode("utf-8")
        salt = os.urandom(16)
        nonce = os.urandom(12)
        key = derive_key(passphrase, salt)
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)

        log_event_v2(
            event_type="reseller_blob_encrypted",
            note="Reseller blob encrypted via AES-GCM",
            actor_component=SYSTEM_ACTOR,
            actor_function="encrypt_blob",
            object_type="reseller_blob",
            object_operation="encrypt",
            audit=True,
        )

        return {
            "ciphertext": base64.b64encode(ciphertext).decode("utf-8"),
            "nonce": base64.b64encode(nonce).decode("utf-8"),
            "salt": base64.b64encode(salt).decode("utf-8"),
        }
    except Exception as e:
        log_event_v2(
            event_type="crypto_error",
            note=f"Encryption/Decryption failure: {str(e)}",
            actor_component=SYSTEM_ACTOR,
            actor_function="<encrypt_blob or decrypt_blob>",
            object_type="reseller_blob",
            object_operation="failure",
            payload={"error": str(e)},
            audit=True,
        )
        raise CryptoError(f"Encryption failed: {str(e)}")


def decrypt_blob(passphrase: str, blob: dict) -> dict:
    """
    Decrypts a sealed blob using the passphrase.

    Args:
        passphrase (str): Base key string used for encryption
        blob (dict): Must contain base64-encoded 'ciphertext', 'nonce', 'salt'

    Returns:
        dict: Decrypted dictionary
    """
    try:
        required_fields = ("ciphertext", "nonce", "salt")
        if not all(k in blob for k in required_fields):
            raise CryptoError("Blob is missing required fields.")

        ciphertext = base64.b64decode(blob["ciphertext"])
        nonce = base64.b64decode(blob["nonce"])
        salt = base64.b64decode(blob["salt"])
        key = derive_key(passphrase, salt)
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        # log_event_v2(
        #     event_type="reseller_blob_decrypted",
        #     note="Reseller blob successfully decrypted",
        #     actor_component=SYSTEM_ACTOR,
        #     actor_function="decrypt_blob",
        #     object_type="reseller_blob",
        #     object_operation="decrypt",
        #     audit=True
        # )
        return json.loads(plaintext.decode("utf-8"))
    except Exception as e:
        log_event_v2(
            event_type="crypto_error",
            note=f"Encryption/Decryption failure: {str(e)}",
            actor_component=SYSTEM_ACTOR,
            actor_function="<encrypt_blob or decrypt_blob>",
            object_type="reseller_blob",
            object_operation="failure",
            payload={"error": str(e)},
            audit=True,
        )
        raise CryptoError(f"Decryption failed: {str(e)}")
