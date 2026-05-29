from __future__ import annotations

import re
from dataclasses import dataclass


EMAIL_PATTERN = re.compile(r"(?<![\w.%+-])[\w.%+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
PHONE_PATTERN = re.compile(
    r"(?<!\w)(?:\+?\d[\d\s().-]{6,}\d)(?!\w)"
)


@dataclass(frozen=True)
class RedactedText:
    value: str | None
    redacted: bool
    fields: tuple[str, ...]


def redact_display_text(value: str | None) -> RedactedText:
    if value is None:
        return RedactedText(value=None, redacted=False, fields=())

    redacted = value
    fields: list[str] = []
    if EMAIL_PATTERN.search(redacted):
        redacted = EMAIL_PATTERN.sub("[redacted email]", redacted)
        fields.append("email")
    if PHONE_PATTERN.search(redacted):
        redacted = PHONE_PATTERN.sub("[redacted phone]", redacted)
        fields.append("phone")
    return RedactedText(value=redacted, redacted=bool(fields), fields=tuple(fields))


def redacted_fields_for_values(values: dict[str, str | None]) -> list[str]:
    fields: list[str] = []
    for field_name, value in values.items():
        if redact_display_text(value).redacted:
            fields.append(field_name)
    return fields
