import re
import unicodedata
from difflib import SequenceMatcher
from typing import Iterable, Optional, Tuple


LEGAL_SUFFIXES = {
    "co",
    "company",
    "corp",
    "corporation",
    "gmbh",
    "group",
    "holdings",
    "inc",
    "incorporated",
    "limited",
    "llc",
    "ltd",
    "plc",
    "sarl",
}

NON_SPACED_SUFFIXES = ("股份有限公司", "有限责任公司", "有限公司")


def normalize_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    for suffix in NON_SPACED_SUFFIXES:
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
            break
    normalized = "".join(
        character
        for character in unicodedata.normalize("NFKD", normalized)
        if not unicodedata.combining(character)
    )
    normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE)
    words = normalized.split()
    suffix_start = len(words)
    while suffix_start > 0 and len(words[suffix_start - 1]) == 1:
        suffix_start -= 1
    if suffix_start < len(words) and "".join(words[suffix_start:]) in LEGAL_SUFFIXES:
        words = words[:suffix_start]
    while words and words[-1] in LEGAL_SUFFIXES:
        words.pop()
    return " ".join(words)


def similarity_score(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left == right:
        return 100.0
    return round(SequenceMatcher(None, left, right).ratio() * 100, 2)


def best_name_match(screened_name: str, listed_names: Iterable[str]) -> Tuple[Optional[str], float, str]:
    normalized_screened = normalize_name(screened_name)
    best_name: Optional[str] = None
    best_score = 0.0
    best_type = "fuzzy"
    for listed_name in listed_names:
        normalized_listed = normalize_name(listed_name)
        score = similarity_score(normalized_screened, normalized_listed)
        match_type = "exact" if score == 100.0 else "fuzzy"
        if score > best_score:
            best_name = listed_name
            best_score = score
            best_type = match_type
    return best_name, best_score, best_type
