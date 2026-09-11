import re
import unicodedata

from unidecode import unidecode

_PUNCT = re.compile(r"[^a-z0-9 ]+")
_SPACES = re.compile(r"\s+")
_SUFFIXES = {"jr", "junior", "sr", "senior", "filho", "neto"}


def normalize_name(name: str | None) -> str:
    """Accent-insensitive, lower-case, punctuation-free form used for blocking and search.
    'Vinícius José Paixão de Oliveira Júnior' -> 'vinicius jose paixao de oliveira'."""
    if not name:
        return ""
    s = unidecode(unicodedata.normalize("NFKD", name)).lower()
    s = _PUNCT.sub(" ", s)
    tokens = [t for t in _SPACES.split(s) if t]
    while tokens and tokens[-1] in _SUFFIXES and len(tokens) > 1:
        tokens.pop()
    return " ".join(tokens)
