import os
import json
import random
from typing import Optional, Dict, List

_DEFAULT_MESSAGES = {
    "humorous": [
        "This page intentionally left blank. (It’s shy.)",
        "Nothing to see here… except high standards for tidy pages.",
        "Blank by design. Our toner thanks you.",
    ],
    "uplifting": [
        "This space is left open for good news.",
        "Empty for now — may your day be full of wins.",
        "Reserved for a moment of calm.",
    ],
    "seasonal": [
        "A season for blanks and a reason for covers.",
        "This blank page brought to you by the season of simplicity.",
        "Warm wishes — even this page gets a holiday.",
    ],
    "classic": [
        "The remainder of this page is intentionally left blank.",
        "Intentionally left blank.",
        "This page has been intentionally left blank.",
    ]
}


def load_message_pool(base_dir: str) -> Dict[str, List[str]]:
    """
    Load cover footer messages from shared/cover_messages.json if present.
    Fallback to in-module defaults.
    - Normalizes category keys to lowercase so JSON can use any casing (e.g., "Humor" or "humorous").
    """
    try:
        path = os.path.join(base_dir, "shared", "cover_messages.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    # Coerce lists and normalize keys to lowercase
                    out: Dict[str, List[str]] = {}
                    for k, v in data.items():
                        if isinstance(v, list) and all(isinstance(x, str) for x in v):
                            out[(k or "").strip().lower()] = v
                    if out:
                        return out
    except Exception:
        pass
    # Default pool already uses lowercase keys
    return dict(_DEFAULT_MESSAGES)


def random_footer(base_dir: str, category: str | None) -> str:
    pool = load_message_pool(base_dir)
    cat = (category or "classic").strip().lower()
    messages = pool.get(cat) or pool.get("classic") or [
        "The remainder of this page is intentionally left blank."
    ]
    try:
        return random.choice(messages)
    except Exception:
        return messages[0]
