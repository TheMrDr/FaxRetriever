import json
import os

class AddressBookManager:
    def __init__(self, exe_dir, filename="address_book.json"):
        self.filename = os.path.join(exe_dir, filename)
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
            with open(self.filename, "r") as file:
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
        with open(self.filename, "w") as file:
            json.dump([], file, indent=4)

    def save_contacts(self):
        # Normalize, drop placeholders, dedupe, and persist in a canonical order
        normalized = [self._normalize_contact(c) for c in (self.contacts or [])]
        normalized = [c for c in normalized if not c.get("is_placeholder", False)]
        normalized = self._dedupe_contacts(normalized)
        normalized.sort(key=lambda x: (x.get('name', '') or '').lower())
        self.contacts = normalized
        with open(self.filename, "w") as file:
            json.dump(self.contacts, file, indent=4)

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
        with open(filepath, "w") as file:
            json.dump(self.contacts, file, indent=4)

    def import_contacts(self, filepath):
        try:
            with open(filepath, "r") as file:
                imported = json.load(file)
                if isinstance(imported, list):
                    normalized = [self._normalize_contact(c) for c in imported]
                    # Drop placeholders from import
                    normalized = [c for c in normalized if not c.get("is_placeholder", False)]
                    self.contacts.extend(normalized)
                    self.save_contacts()
        except json.JSONDecodeError:
            pass
