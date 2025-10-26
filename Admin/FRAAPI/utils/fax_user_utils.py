# Admin/licensing_server/utils/fax_user_utils.py

from typing import Optional


def parse_reseller_id(fax_user: str) -> str:
    """
    Extract reseller_id from a fax_user identifier.
    Supports formats like:
    - ext@domain.reseller.service
    - domain.reseller.service
    - Fallbacks: if only two labels, use the last label as reseller id.

    Raises ValueError if parsing is not possible.
    """
    if not fax_user or not isinstance(fax_user, str):
        raise ValueError("fax_user is empty or not a string")

    s = fax_user.strip().lower()
    if not s:
        raise ValueError("fax_user is empty after stripping")

    # If an '@' exists, take the part after it; otherwise treat the whole string as the domain-like part
    domain_part = s.split("@", 1)[1] if "@" in s else s

    # Split into labels (ignore empty labels)
    labels = [p for p in domain_part.split(".") if p]

    if len(labels) >= 3:
        # Typical: <clientdomain>.<reseller_id>.service  -> take penultimate
        return labels[-2]
    if len(labels) == 2:
        # Less typical: <something>.<reseller_id>
        return labels[-1]

    raise ValueError("Unable to derive reseller_id from fax_user: insufficient labels")
