from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

from app.evaluation.spec import TextPattern

_CONTRACTIONS = {
    "can't": "cannot",
    "cannot": "cannot",
    "couldn't": "could not",
    "didn't": "did not",
    "doesn't": "does not",
    "don't": "do not",
    "isn't": "is not",
    "mustn't": "must not",
    "shouldn't": "should not",
    "wasn't": "was not",
    "weren't": "were not",
    "won't": "will not",
    "wouldn't": "would not",
}
_NEGATION_TOKENS = frozenset(
    {
        "beyond",
        "cannot",
        "ineligible",
        "neither",
        "never",
        "no",
        "not",
        "outside",
        "without",
    }
)
_NEGATION_WINDOW = 3


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).lower().replace("’", "'").replace("`", "'")
    for contraction, expanded in _CONTRACTIONS.items():
        normalized = re.sub(rf"\b{re.escape(contraction)}\b", expanded, normalized)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return " ".join(normalized.split())


def pattern_matches(text: str, pattern: TextPattern) -> bool:
    normalized = normalize_text(text)
    tokens = normalized.split()
    occurrences = (
        _phrase_occurrences(tokens, pattern.value)
        if pattern.kind == "phrase"
        else _regex_occurrences(normalized, pattern.value)
    )
    if pattern.polarity == "any":
        return bool(occurrences)
    if pattern.polarity == "positive":
        return any(not _is_negated(tokens, index) for index in occurrences)
    return any(_is_negated(tokens, index) for index in occurrences)


def any_pattern_matches(text: str, patterns: Iterable[TextPattern]) -> bool:
    return any(pattern_matches(text, pattern) for pattern in patterns)


def normalized_literal_is_present(text: str, literal: str) -> bool:
    normalized_literal = normalize_text(literal)
    if not normalized_literal:
        return False
    text_tokens = normalize_text(text).split()
    literal_tokens = normalized_literal.split()
    return bool(_token_sequence_occurrences(text_tokens, literal_tokens))


def _phrase_occurrences(tokens: list[str], phrase: str) -> list[int]:
    phrase_tokens = normalize_text(phrase).split()
    return _token_sequence_occurrences(tokens, phrase_tokens)


def _token_sequence_occurrences(tokens: list[str], phrase_tokens: list[str]) -> list[int]:
    if not phrase_tokens or len(phrase_tokens) > len(tokens):
        return []
    width = len(phrase_tokens)
    return [
        index
        for index in range(len(tokens) - width + 1)
        if tokens[index : index + width] == phrase_tokens
    ]


def _regex_occurrences(normalized_text: str, expression: str) -> list[int]:
    occurrences: list[int] = []
    for match in re.finditer(expression, normalized_text):
        occurrences.append(len(normalized_text[: match.start()].split()))
    return occurrences


def _is_negated(tokens: list[str], index: int) -> bool:
    prefix = tokens[max(0, index - _NEGATION_WINDOW) : index]
    return any(token in _NEGATION_TOKENS for token in prefix)
