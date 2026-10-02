"""Conservative corrections for known Vietnamese PDF font extraction artifacts."""

import re
import unicodedata


# U+01A3 is emitted in place of Vietnamese ư by legacy PDF fonts.
# Do not guess missing accents or rewrite words. Preserve code/math spans.
_FONT_ARTIFACTS = str.maketrans({"ƣ": "ư", "Ƣ": "Ư"})
_PROTECTED_SPANS = re.compile(
    r"(```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]*`|\$\$[\s\S]*?\$\$|\$[^$\n]+\$)"
)
_WORD_ARTIFACT = re.compile(r"(?<=[^\W\d_])[ƣƢ]|[ƣƢ](?=[^\W\d_])")


def normalize_source_text(value: str) -> str:
    """Normalize prose representation, leaving isolated symbols and code intact."""
    parts = _PROTECTED_SPANS.split(unicodedata.normalize("NFC", value))
    for index in range(0, len(parts), 2):
        parts[index] = _WORD_ARTIFACT.sub(
            lambda match: match.group().translate(_FONT_ARTIFACTS), parts[index]
        )
    return "".join(parts)
