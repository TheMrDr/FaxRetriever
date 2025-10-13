"""
Windows DPAPI secure store helpers (Sprint 4)

- secure_encrypt_for_machine: encrypts a plaintext string using Windows DPAPI
  with the LocalMachine scope and returns a base64-encoded blob suitable for
  storing in JSON config files.
- secure_decrypt_for_machine: reverses the process and returns the plaintext
  string, or None if decryption fails.

Notes
- On Windows, prefer pywin32's win32crypt if available; otherwise fall back to
  ctypes bindings for CryptProtectData / CryptUnprotectData.
- On non-Windows platforms, these helpers are not supported and will raise
  NotImplementedError. Unit tests skip on non-Windows.
- Empty inputs are handled gracefully ("" encrypts to "" and decrypts to "").

Security
- Do NOT log secrets. This module emits no logs.
- The returned base64 blob contains DPAPI-protected bytes that are only
  decryptable on the same machine (LocalMachine scope) and under appropriate
  Windows protection contexts.
"""
from __future__ import annotations

import base64
import sys
from typing import Optional


def _is_windows() -> bool:
    return sys.platform.startswith("win32") or sys.platform.startswith("cygwin")


# --- win32crypt (pywin32) implementation ---
try:  # pragma: no cover - availability depends on environment
    import win32crypt  # type: ignore
except Exception:  # noqa: E722 - broad by design; we fall back to ctypes
    win32crypt = None  # type: ignore


def _encrypt_win32crypt(plaintext: str) -> str:
    # CRYPTPROTECT_LOCAL_MACHINE = 0x4 ensures machine scope
    flags = 0x4
    data = (plaintext or "").encode("utf-8")
    if not data:
        return ""
    blob = win32crypt.CryptProtectData(data, None, None, None, None, flags)  # type: ignore[attr-defined]
    return base64.b64encode(blob).decode("ascii")


def _decrypt_win32crypt(b64blob: str) -> Optional[str]:
    if not b64blob:
        return ""
    try:
        raw = base64.b64decode(b64blob)
        data = win32crypt.CryptUnprotectData(raw, None, None, None, 0)[1]  # type: ignore[attr-defined]
        return data.decode("utf-8")
    except Exception:
        return None


# --- ctypes implementation for DPAPI ---

def _encrypt_ctypes(plaintext: str) -> str:  # pragma: no cover - environment-specific
    import ctypes
    from ctypes import wintypes

    CRYPTPROTECT_LOCAL_MACHINE = 0x4

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

    CryptProtectData = ctypes.windll.crypt32.CryptProtectData
    CryptProtectData.argtypes = [ctypes.POINTER(DATA_BLOB), wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB)]
    CryptProtectData.restype = wintypes.BOOL

    LocalFree = ctypes.windll.kernel32.LocalFree
    LocalFree.argtypes = [ctypes.c_void_p]
    LocalFree.restype = ctypes.c_void_p

    data_bytes = (plaintext or "").encode("utf-8")
    if not data_bytes:
        return ""

    # Prepare input blob; keep a reference to the buffer to avoid GC
    in_buffer = ctypes.create_string_buffer(data_bytes)
    in_blob = DATA_BLOB(len(data_bytes), ctypes.cast(in_buffer, ctypes.POINTER(ctypes.c_byte)))
    out_blob = DATA_BLOB()

    if not CryptProtectData(ctypes.byref(in_blob), None, None, None, None, CRYPTPROTECT_LOCAL_MACHINE, ctypes.byref(out_blob)):
        raise OSError("CryptProtectData failed")

    try:
        # Copy encrypted bytes
        encrypted = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        return base64.b64encode(encrypted).decode("ascii")
    finally:
        if out_blob.pbData:
            LocalFree(out_blob.pbData)


def _decrypt_ctypes(b64blob: str) -> Optional[str]:  # pragma: no cover - environment-specific
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

    CryptUnprotectData = ctypes.windll.crypt32.CryptUnprotectData
    CryptUnprotectData.argtypes = [ctypes.POINTER(DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB)]
    CryptUnprotectData.restype = wintypes.BOOL

    LocalFree = ctypes.windll.kernel32.LocalFree
    LocalFree.argtypes = [ctypes.c_void_p]
    LocalFree.restype = ctypes.c_void_p

    if not b64blob:
        return ""

    try:
        raw = base64.b64decode(b64blob)
    except Exception:
        return None

    in_buffer = ctypes.create_string_buffer(raw)
    in_blob = DATA_BLOB(len(raw), ctypes.cast(in_buffer, ctypes.POINTER(ctypes.c_byte)))
    out_blob = DATA_BLOB()

    if not CryptUnprotectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)):
        return None

    try:
        decrypted = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        return decrypted.decode("utf-8")
    except Exception:
        return None
    finally:
        if out_blob.pbData:
            LocalFree(out_blob.pbData)


# --- Public API ---

def secure_encrypt_for_machine(plaintext: str) -> str:
    """Encrypt plaintext for storage using Windows DPAPI (LocalMachine scope).

    Returns a base64-encoded string. On non-Windows platforms, raises
    NotImplementedError.
    """
    if not _is_windows():
        raise NotImplementedError("secure_encrypt_for_machine is only supported on Windows")
    if win32crypt is not None:  # type: ignore
        return _encrypt_win32crypt(plaintext)
    return _encrypt_ctypes(plaintext)


def secure_decrypt_for_machine(b64blob: str) -> Optional[str]:
    """Decrypt a base64-encoded DPAPI blob back to plaintext.

    Returns the plaintext string, an empty string for empty input, or None on
    decryption failure. On non-Windows platforms, raises NotImplementedError.
    """
    if not _is_windows():
        raise NotImplementedError("secure_decrypt_for_machine is only supported on Windows")
    if win32crypt is not None:  # type: ignore
        return _decrypt_win32crypt(b64blob)
    return _decrypt_ctypes(b64blob)
