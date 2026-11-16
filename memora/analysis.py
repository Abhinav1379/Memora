"""Deterministic Unicode text statistics; no network or models."""
import re
import unicodedata
from heapq import nsmallest
from collections import Counter

WORD_PATTERN = re.compile(r"[^\W_]+(?:['’][^\W_]+)*", re.UNICODE)
STOP_WORDS = frozenset("""
a an and are as at be been being but by can could did do does for from had has
have he her hers him his how i if in into is it its may me might more most my
no nor not of on one or our ours out over own she should so some than that the
their theirs them then there these they this those through to too under up us
very was we were what when where which while who why will with would you your yours
""".split())


def words(text: str) -> list[str]:
    return WORD_PATTERN.findall(unicodedata.normalize("NFKC", text).casefold().replace("’", "'"))


def analyze_text(text: str, ignore_stop_words: bool = True, top_n: int = 15) -> dict:
    if top_n < 1:
        raise ValueError("Frequency list length must be positive.")
    tokens = words(text)
    counts = Counter(tokens)
    frequency = nsmallest(top_n, ((word, count) for word, count in counts.items()
                                 if not ignore_stop_words or word not in STOP_WORDS),
                          key=lambda item: (-item[1], item[0]))
    return {
        "character_count": len(text),
        "characters_without_spaces": sum(not char.isspace() for char in text),
        "word_count": len(tokens),
        "unique_word_count": len(counts),
        "line_count": len(text.splitlines()),
        "paragraph_count": len([part for part in re.split(r"\n\s*\n", text.strip()) if part.strip()]),
        "average_word_length": round(sum(len(word) for word in tokens) / len(tokens), 2) if tokens else 0.0,
        "reading_time_minutes": round(len(tokens) / 200, 2),
        "reading_speed_wpm": 200,
        "ignore_stop_words": ignore_stop_words,
        "frequent_words": [{"word": word, "count": count} for word, count in frequency],
    }
