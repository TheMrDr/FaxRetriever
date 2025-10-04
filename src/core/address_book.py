import json
import os
import sys
from typing import Optional


def _resolve_address_book_path(exe_dir: str, filename: str = "address_book.json") -> str:
    """
    Resolve a shared path for the address book so all clients launching from a
    network share use the same file. Priority:
      1) FR_ADDRESS_BOOK_FILE (file or dir) and FR_ADDRESS_BOOK_DIR
      2) FR_ORIGINAL_ROOT (set by SMB bootstrap) at <root>/address_book.json
      3) origin.path stored in LOCALAPPDATA\\...\\bin\\origin.path
      4) Process-dir relative (exe_dir)
      5) Project root (..\\.. from this file)
      6) Current working directory
    If none exist, prefer creating under FR_ORIGINAL_ROOT when available.
    """
    cands: list[str] = []

    # 1) Environment overrides
    env_file = os.environ.get('FR_ADDRESS_BOOK_FILE')
    if env_file:
        if os.path.isdir(env_file):
            cands.append(os.path.join(env_file, filename))
        else:
            cands.append(env_file)
    env_dir = os.environ.get('FR_ADDRESS_BOOK_DIR')
    if env_dir:
        cands.append(os.path.join(env_dir, filename))

    # 2) Original network launch root provided by bootstrap
    orig_root = os.environ.get('FR_ORIGINAL_ROOT')
    if orig_root:
        cands.append(os.path.join(orig_root, filename))

    # 3) Origin path file written by bootstrap in local cache bin
    try:
        local_appdata = os.environ.get('LOCALAPPDATA') or ''
        origin_file = os.path.join(local_appdata, 'Clinic Networking, LLC', 'FaxRetriever', '2.0', 'bin', 'origin.path')
        if os.path.exists(origin_file):
            with open(origin_file, 'r', encoding='utf-8') as f:
                origin_root = f.read().strip()
                if origin_root:
                    cands.append(os.path.join(origin_root, filename))
    except Exception:
        pass

    # 4) Process directory provided to manager (exe_dir)
    if exe_dir:
        cands.append(os.path.join(exe_dir, filename))

    # 5) Project root when running from source
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        proj_root = os.path.abspath(os.path.join(here, '..', '..'))
        cands.append(os.path.join(proj_root, filename))
    except Exception:
        pass

    # 6) Current working directory
    cands.append(os.path.join(os.getcwd(), filename))

    for p in cands:
        try:
            if p and os.path.exists(p):
                return p
        except Exception:
            continue

    # Prefer creating under original root if available
    if orig_root:
        return os.path.join(orig_root, filename)
    # Else, create in exe_dir if possible
    if exe_dir:
        return os.path.join(exe_dir, filename)
    # Fallback to CWD
    return os.path.join(os.getcwd(), filename)


class AddressBookManager:
    def __init__(self, exe_dir, filename="address_book.json"):
        # Resolve to a shared location when launched via SMB; fall back as needed
        self.filename = _resolve_address_book_path(exe_dir, filename)
        self.contacts = self.load_contacts()

    @staticmethod
    def _sanitize_phone(raw: str) -> str:
        """Sanitize a phone into a uniform 10-digit numeric string (US/CA style).
        - Remove all non-digits
        - If 11 digits and starts with '1', drop the leading 1
        - If 10 digits, keep as-is
        - Otherwise, return the digits (best effort)
        """
        digits = ''.join(c for c in (raw or '') if c.isdigit())
        if len(digits) == 11 and digits.startswith('1'):
            return digits[1:]
        return digits[:10] if len(digits) >= 10 else digits

    @staticmethod
    def _clean_str(v):
        return (v or "").strip()

    def _normalize_contact(self, contact: dict) -> dict:
        """Return a standardized contact dict with canonical schema and values.
        Ensures numbers are sanitized, strings trimmed, email lowercased, booleans cast,
        and placeholders are never persisted.
        """
        c = dict(contact or {})
        name = self._clean_str(c.get("name"))
        phone = self._sanitize_phone(c.get("phone", ""))
        phone1 = self._sanitize_phone(c.get("phone1", ""))
        company = self._clean_str(c.get("company"))
        email = self._clean_str(c.get("email")).lower()
        notes = self._clean_str(c.get("notes"))
        custom_cover_sheet = bool(c.get("custom_cover_sheet", False))
        custom_cover_sheet_attn = self._clean_str(c.get("custom_cover_sheet_attn"))
        custom_cover_sheet_note = self._clean_str(c.get("custom_cover_sheet_note"))
        favorite = bool(c.get("favorite", False))
        # Preserve placeholder flag from input; we will filter placeholders on save
        is_placeholder = bool(c.get("is_placeholder", False))
        return {
            "name": name,
            "phone": phone,
            "phone1": phone1,
            "company": company,
            "email": email,
            "notes": notes,
            "custom_cover_sheet": custom_cover_sheet,
            "custom_cover_sheet_attn": custom_cover_sheet_attn,
            "custom_cover_sheet_note": custom_cover_sheet_note,
            "favorite": favorite,
            "is_placeholder": is_placeholder,
        }

    def _dedupe_contacts(self, contacts: list[dict]) -> list[dict]:
        """Return a list with duplicates removed by (name_lower, phone, phone1)."""
        seen = set()
        result = []
        for c in contacts or []:
            key = ((c.get("name") or "").strip().lower(), c.get("phone", ""), c.get("phone1", ""))
            if key in seen:
                continue
            seen.add(key)
            result.append(c)
        return result

    def load_contacts(self):
        if not os.path.exists(self.filename):
            self._initialize_with_placeholder()

        try:
            with open(self.filename, "r", encoding="utf-8") as file:
                data = json.load(file)
                if not isinstance(data, list):
                    return []
                # Normalize everything on load to migrate any legacy data once
                normalized = [self._normalize_contact(c) for c in (data or [])]
                # Remove any placeholders and dedupe
                normalized = [c for c in normalized if not c.get("is_placeholder", False)]
                normalized = self._dedupe_contacts(normalized)
                return sorted(normalized, key=lambda x: (x.get('name', '') or '').lower())
        except json.JSONDecodeError:
            return []

    def _initialize_with_placeholder(self):
        """
        Initialize an empty address book on first run. UI will render non-persistent
        placeholder cards (at least 4) so we avoid storing sample data permanently.
        """
        os.makedirs(os.path.dirname(self.filename) or '.', exist_ok=True)
        tmp_path = self.filename + '.tmp'
        with open(tmp_path, "w", encoding="utf-8") as file:
            json.dump([], file, indent=4)
        os.replace(tmp_path, self.filename)

    def save_contacts(self):
        # Normalize, drop placeholders, dedupe, and persist in a canonical order
        normalized = [self._normalize_contact(c) for c in (self.contacts or [])]
        normalized = [c for c in normalized if not c.get("is_placeholder", False)]
        normalized = self._dedupe_contacts(normalized)
        normalized.sort(key=lambda x: (x.get('name', '') or '').lower())
        self.contacts = normalized
        os.makedirs(os.path.dirname(self.filename) or '.', exist_ok=True)
        tmp_path = self.filename + '.tmp'
        with open(tmp_path, "w", encoding="utf-8") as file:
            json.dump(self.contacts, file, indent=4)
        os.replace(tmp_path, self.filename)

    def refresh_contacts(self):
        self.contacts = self.load_contacts()

    def find_contact_by_phone(self, phone: str):
        """Return (index, contact) for the first contact whose phone or phone1
        matches the sanitized input. If not found, returns (None, None).
        """
        try:
            target = self._sanitize_phone(phone or "")
            if not target:
                return None, None
            for idx, c in enumerate(self.contacts or []):
                if c.get("is_placeholder", False):
                    continue
                p0 = self._sanitize_phone(c.get("phone", ""))
                p1 = self._sanitize_phone(c.get("phone1", ""))
                if target and (target == p0 or target == p1):
                    return idx, c
        except Exception:
            pass
        return None, None

    def add_contact(self, name, phone, phone1, company="", email="", notes="", custom_cover_sheet=False, custom_cover_sheet_attn="", custom_cover_sheet_note="", favorite=False):
        """Add a new contact using canonical normalization and dedupe rules."""
        new_c = {
            "name": (name or "").strip(),
            "phone": phone,
            "phone1": phone1,
            "company": (company or "").strip(),
            "email": (email or "").strip(),
            "notes": (notes or "").strip(),
            "custom_cover_sheet": bool(custom_cover_sheet),
            "custom_cover_sheet_attn": custom_cover_sheet_attn,
            "custom_cover_sheet_note": custom_cover_sheet_note,
            "favorite": bool(favorite),
            "is_placeholder": False,
        }
        new_c = self._normalize_contact(new_c)
        key = (new_c.get("name", "").lower(), new_c.get("phone", ""), new_c.get("phone1", ""))
        replaced = False
        for i, c in enumerate(self.contacts or []):
            c_key = ((c.get("name") or "").strip().lower(), c.get("phone", ""), c.get("phone1", ""))
            if c_key == key:
                # Merge favorite preference (preserve existing favorite)
                new_c["favorite"] = bool(c.get("favorite", False)) or bool(new_c.get("favorite", False))
                self.contacts[i] = new_c
                replaced = True
                break
        if not replaced:
            self.contacts.append(new_c)
        self.save_contacts()

    def update_contact(self, index: int, contact_data: dict) -> bool:
        """Update contact at index with provided data via normalization pipeline."""
        if index is None or index < 0 or index >= len(self.contacts):
            return False
        existing = self.contacts[index]
        # Preserve favorite unless explicitly changed
        if "favorite" not in contact_data:
            contact_data["favorite"] = bool(existing.get("favorite", False))
        merged = dict(existing)
        merged.update(contact_data or {})
        merged["is_placeholder"] = False
        normalized = self._normalize_contact(merged)
        # Preserve favorite if previously true
        if existing.get("favorite", False):
            normalized["favorite"] = True
        self.contacts[index] = normalized
        self.save_contacts()
        return True

    def delete_contact(self, index):
        if 0 <= index < len(self.contacts):
            if not self.contacts[index].get("is_placeholder", False):
                del self.contacts[index]
                self.save_contacts()

    def export_contacts(self, filepath):
        with open(filepath, "w", encoding="utf-8") as file:
            json.dump(self.contacts, file, indent=4)

    def import_contacts(self, filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as file:
                imported = json.load(file)
                if isinstance(imported, list):
                    normalized = [self._normalize_contact(c) for c in imported]
                    # Drop placeholders from import
                    normalized = [c for c in normalized if not c.get("is_placeholder", False)]
                    self.contacts.extend(normalized)
                    self.save_contacts()
        except json.JSONDecodeError:
            pass
