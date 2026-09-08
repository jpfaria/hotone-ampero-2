"""Which catalog model is *based on* a real-world unit: token match on model name + `based_on`.

Deterministic and policy-free: it ranks candidates, `strict()` says whether one is a clear
winner (unique highest hit count, at least half of the query matched). A tie between
variants (channels, "+" versions, A/B cabs) is reported as unresolved so the caller
tightens the name ("... normal channel"), never guesses.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .catalog import Catalog, Model

# real-world token -> extra tokens the catalog uses for it (name and based_on are both searched)
ALIASES: dict[str, tuple[str, ...]] = {
    "marshall": ("marshell", "uk"), "fender": ("tweed", "black", "silver", "brown", "baseman"),
    "vox": ("voxy",), "mesa": ("messe", "rector"), "boogie": ("messe", "rector"), "rectifier": ("rector",),
    "bogner": ("boger",), "orange": ("tang",), "diezel": ("dizzle",), "friedman": ("fryman",),
    "engl": ("engle",), "evh": ("eddie",), "peavey": ("eddie", "5150"), "5150": ("51", "eddie"),
    "dumble": ("dumbell",), "soldano": ("soloist",), "ampeg": ("ampage",), "hiwatt": ("hiway",),
    "matchless": ("match",), "supro": ("superb",), "badcat": ("kitty",), "carr": ("dr",),
    "klon": ("faun",), "centaur": ("faun",), "rat": ("rat2", "black tail"), "muff": ("pie",),
    "ts808": ("ts-808", "808"), "ts9": ("ts-9",), "tubescreamer": ("tube", "screamer"),
    "jcm800": ("800",), "jcm900": ("900",), "jtm45": ("jtm", "45"), "jmp": ("50",),
    "plexi": ("slp", "1959", "super lead"), "superlead": ("slp", "1959"),
    "deluxe": ("dlx",), "bassman": ("baseman",), "ac30": ("30hw", "ac30hw"), "ac15": ("15",),
    "greenback": ("green", "grn"), "v30": ("vintage 30",), "topboost": ("tb", "top boost"),
    "ep": ("ep",), "booster": ("boost",), "overdrive": ("od", "ods"), "special": ("ods",),
}
STOPWORDS = {
    "based", "the", "a", "an", "of", "and", "with", "by", "in", "for", "to", "is", "this", "that",
    "legendary", "famous", "classic", "widely", "used", "model", "models", "inspired", "recreates", "sound",
    "amp", "amps", "head", "pedal", "pedals", "combo", "cabinet", "cab", "version", "channel", "ch",
    "speaker", "speakers", "circuit", "series", "unit", "effect", "effects", "guitar", "type",
}
_STRIP = re.compile(r"[®™*©\"“”]")
_TOKEN = re.compile(r"[a-z0-9+']+")


def _tokens(text: str) -> set[str]:
    text = _STRIP.sub(" ", text.lower())
    text = re.sub(r"(?<=\w)-(?=\w)", "", text)          # ts-808 -> ts808, sch-1 -> sch1
    text = re.sub(r"^\s*(based on|inspired by)\s+", "", text)
    return {t for t in _TOKEN.findall(text) if t not in STOPWORDS and t != "+"}


def _groups(query: str) -> list[set[str]]:
    """One group per query token: the token plus its aliases (any hit counts the group as matched)."""
    return [{t} | {a for alias in ALIASES.get(t, ()) for a in _tokens(alias)} for t in sorted(_tokens(query))]


def _hit(token: str, hay: set[str]) -> bool:
    return token in hay or (len(token) >= 3 and any(h.startswith(token) for h in hay))


@dataclass(frozen=True)
class Match:
    name: str
    index: int
    code: int
    score: float
    hits: int
    based_on: str


def _rank(model: Model, groups: list[set[str]]) -> tuple[int, float]:
    hay = _tokens(model.name) | _tokens(model.based_on or "")
    hits = sum(any(_hit(t, hay) for t in g) for g in groups)
    if hits == 0:
        return 0, 0.0
    return hits, round(0.7 * hits / len(groups) + 0.3 * hits / max(len(hay), 1), 3)


def resolve(catalog: Catalog, category: str, query: str, limit: int = 3) -> list[Match]:
    groups = _groups(query)
    if not groups:
        return []
    ranked = []
    for m in catalog.category(category).models:
        hits, score = _rank(m, groups)
        if hits:
            ranked.append((hits, m.index, Match(m.name, m.index, m.code, score, hits, (m.based_on or "").strip())))
    ranked.sort(key=lambda t: (-t[0], t[1]))
    return [r[2] for r in ranked[:limit]]


def strict(matches: list[Match], query_tokens: int | None = None) -> Match | None:
    """The one clear winner, or None: unique highest hit count and at least half the query matched."""
    if not matches:
        return None
    top = matches[0]
    if len(matches) > 1 and matches[1].hits == top.hits:
        return None
    if query_tokens and top.hits * 2 < query_tokens:
        return None
    return top


def resolve_strict(catalog: Catalog, category: str, query: str) -> Match | None:
    return strict(resolve(catalog, category, query), len(_groups(query)))
