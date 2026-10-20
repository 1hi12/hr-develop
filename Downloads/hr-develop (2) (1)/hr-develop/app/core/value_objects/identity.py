"""
Candidate identity — groups multiple CV uploads that belong to the same person.

Two CVs are considered the same identity only when full_name, email, and phone
all match exactly after normalization. Missing any of the three fields means
we can't confidently group, so a fresh random identity is used instead.
"""

from __future__ import annotations

import re
import uuid

_IDENTITY_NAMESPACE = uuid.UUID("6f6a6f0e-6b5a-4b8e-9a2a-8f1a6b2c9d10")


def normalize_name(name: str | None) -> str:
    if not name:
        return ""
    return re.sub(r"\s+", " ", name.strip().lower())


def normalize_email(email: str | None) -> str:
    if not email:
        return ""
    return email.strip().lower()


def normalize_phone(phone: str | None) -> str:
    if not phone:
        return ""
    keep_plus = phone.strip().startswith("+")
    digits = re.sub(r"\D", "", phone)
    return f"+{digits}" if keep_plus else digits


def compute_identity_id(
    full_name: str | None,
    email: str | None,
    phone: str | None,
) -> str:
    """
    Deterministic identity key shared by CVs of the same person.
    Falls back to a random (unique) id when name, email, or phone is missing —
    grouping requires all three fields to match, per product decision.
    """
    norm_name  = normalize_name(full_name)
    norm_email = normalize_email(email)
    norm_phone = normalize_phone(phone)

    if not (norm_name and norm_email and norm_phone):
        return str(uuid.uuid4())

    key = f"{norm_name}|{norm_email}|{norm_phone}"
    return str(uuid.uuid5(_IDENTITY_NAMESPACE, key))
