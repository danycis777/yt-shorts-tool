"""Text helpers: normalisation, tokenisation, n-grams, hashtags, title casing."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import Iterable, List, Sequence, Tuple

STOPWORDS = frozenset(
    """a an the and or but if then than so of to in on at by for from with without into onto over under
    is are was were be been being am do does did doing have has had having i me my mine we us our ours you
    your yours he him his she her hers it its they them their theirs this that these those there here what
    which who whom whose when where why how all any both each few more most other some such no nor not only
    own same too very can will just should now s t don didn doesn isn aren wasn weren won wouldn couldn
    shouldn ll re ve d m o y as up out about again further once off vs via""".split()
)

# Words that carry no topical signal on YouTube; ignored when mining phrases/insights (not when matching).
NOISE_WORDS = STOPWORDS | frozenset(
    """get got gets make makes made one new video videos shorts short youtube yt official full part ep episode
    pt vlog clip clips subscribe like comment channel""".split()
)

QUESTION_WORDS = (
    "how", "what", "why", "when", "where", "which", "who", "whom", "whose", "can", "could", "is", "are",
    "does", "do", "did", "should", "would", "will", "was", "were", "has", "have",
)

_WS = re.compile(r"\s+")
_TOKEN = re.compile(r"[^\W_]+(?:['’][^\W_]+)*", re.UNICODE)
_HASHTAG = re.compile(r"(?<![\w&])#([^\W_][\w]*)", re.UNICODE)
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F900-\U0001F9FF\U00002B00-\U00002BFF\U0000FE0F]",
    re.UNICODE,
)


def normalize(text: str) -> str:
    """Lowercase, NFKC-normalise and collapse whitespace (keeps punctuation)."""
    text = unicodedata.normalize("NFKC", text or "")
    return _WS.sub(" ", text.lower()).strip()


def normalize_keyword(text: str) -> str:
    """Normalise a search phrase: lowercase, strip surrounding punctuation, collapse spaces."""
    text = normalize(text)
    text = re.sub(r"[\"“”‘’`´]", "", text)
    text = re.sub(r"[?!.,;:]+$", "", text)
    return _WS.sub(" ", text).strip()


def tokens(text: str) -> List[str]:
    return [t.replace("’", "'") for t in _TOKEN.findall(normalize(text))]


def content_tokens(text: str) -> List[str]:
    return [t for t in tokens(text) if t not in NOISE_WORDS and len(t) > 1 and not t.isdigit()]


def singular(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def token_set(text: str) -> set:
    return {singular(t) for t in tokens(text)}


def contains_phrase(haystack: str, phrase: str) -> bool:
    """Whole-word phrase match on normalised text (tolerates punctuation between words)."""
    h = " " + " ".join(tokens(haystack)) + " "
    p = " " + " ".join(tokens(phrase)) + " "
    return bool(p.strip()) and p in h


def contains_all_tokens(haystack: str, phrase: str) -> bool:
    want = {singular(t) for t in tokens(phrase) if t not in STOPWORDS} or token_set(phrase)
    have = token_set(haystack)
    return bool(want) and want <= have


def ngrams(words: Sequence[str], n: int) -> List[Tuple[str, ...]]:
    return [tuple(words[i:i + n]) for i in range(len(words) - n + 1)]


def top_phrases(texts: Iterable[str], n_values: Sequence[int] = (2, 3), min_count: int = 2,
                limit: int = 15) -> List[Tuple[str, int]]:
    """Most frequent n-grams across texts; each text counts a phrase once; stopword-edged grams skipped."""
    counter: Counter = Counter()
    for text in texts:
        words = tokens(text)
        seen = set()
        for n in n_values:
            for gram in ngrams(words, n):
                if gram[0] in NOISE_WORDS or gram[-1] in NOISE_WORDS:
                    continue
                if all(w.isdigit() for w in gram):
                    continue
                seen.add(" ".join(gram))
        counter.update(seen)
    items = [(p, c) for p, c in counter.most_common() if c >= min_count]
    # drop phrases fully contained in a longer phrase with the same count
    result: List[Tuple[str, int]] = []
    for phrase, count in items:
        if any(count == c2 and phrase != p2 and f" {phrase} " in f" {p2} " for p2, c2 in items):
            continue
        result.append((phrase, count))
        if len(result) >= limit:
            break
    return result


def word_counts(texts: Iterable[str], min_len: int = 3) -> Counter:
    counter: Counter = Counter()
    for text in texts:
        counter.update({t for t in content_tokens(text) if len(t) >= min_len})
    return counter


def hashtags(text: str) -> List[str]:
    return ["#" + h for h in _HASHTAG.findall(text or "")]


def emoji_count(text: str) -> int:
    return len(_EMOJI.findall(text or ""))


def smart_title(phrase: str) -> str:
    """Title-case a phrase for use in titles, keeping small words lowercase and acronyms intact."""
    small = {"a", "an", "the", "and", "or", "but", "of", "to", "in", "on", "at", "by", "for", "vs", "with"}
    words = phrase.split()
    out = []
    for i, w in enumerate(words):
        if w.isupper() and len(w) > 1:
            out.append(w)
        elif i > 0 and w.lower() in small:
            out.append(w.lower())
        elif any(ch.isdigit() for ch in w):
            out.append(w)
        else:
            out.append(w[:1].upper() + w[1:])
    return " ".join(out)


def is_question(phrase: str) -> bool:
    words = normalize(phrase).split()
    return bool(words) and (words[0] in QUESTION_WORDS or phrase.strip().endswith("?"))


def youtube_tag_length(tags: Iterable[str]) -> int:
    """Characters counted by YouTube Studio's 500-char tag limit (spaces make a tag count 2 extra for quotes)."""
    total = 0
    tag_list = [t for t in tags if t]
    for t in tag_list:
        total += len(t) + (2 if " " in t else 0)
    total += max(0, len(tag_list) - 1)  # commas
    return total


def truncate(text: str, length: int) -> str:
    text = text or ""
    return text if len(text) <= length else text[: max(0, length - 1)].rstrip() + "…"
