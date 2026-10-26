"""Turn text into vectors.

Two options, picked with EMBEDDING_PROVIDER:

- "hash" (default): runs locally, free, no API key. Each word and word pair is
  hashed into one of 384 slots. Two texts that share words end up with similar
  vectors. It does not understand synonyms, so "leave" and "vacation" do not match.
- "openai": text-embedding-3-small, 1536 numbers per text. Understands meaning,
  costs a little money, needs OPENAI_API_KEY.

Both return unit-length vectors, so cosine similarity is just the dot product.
"""

import hashlib
import math
import re

import httpx

from app.config import settings

HASH_DIM = 384

# Very common words carry no meaning for search, so we skip them.
STOPWORDS = set(
    "a an and are as at be by can do does for from has have how i if in is it its of on or "
    "our should so that the their there this to was we what when where which who why will "
    "with you your".split()
)


def embed_texts(texts: list[str]) -> list[list[float]]:
    if settings.embedding_provider == "openai":
        return _openai_embed(texts)
    return [_hash_embed(t) for t in texts]


def _singular(word: str) -> str:
    # Crude plural handling so "deploys" matches "deploy". Leaves "process", "is", "bus" alone.
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def _words(text: str) -> list[str]:
    return [_singular(w) for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOPWORDS]


def _hash_embed(text: str) -> list[float]:
    vector = [0.0] * HASH_DIM
    words = _words(text)
    features = words + [f"{a} {b}" for a, b in zip(words, words[1:])]
    for feature in features:
        digest = hashlib.md5(feature.encode()).digest()
        slot = int.from_bytes(digest[:4], "little") % HASH_DIM
        # A second hash bit picks +1 or -1, so unrelated words cancel out instead of piling up.
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[slot] += sign
    return _normalize(vector)


def _openai_embed(texts: list[str]) -> list[list[float]]:
    if not settings.openai_api_key:
        raise RuntimeError("EMBEDDING_PROVIDER=openai needs OPENAI_API_KEY")
    response = httpx.post(
        "https://api.openai.com/v1/embeddings",
        headers={"Authorization": f"Bearer {settings.openai_api_key}"},
        json={"model": "text-embedding-3-small", "input": texts},
        timeout=60,
    )
    response.raise_for_status()
    return [item["embedding"] for item in response.json()["data"]]


def _normalize(vector: list[float]) -> list[float]:
    length = math.sqrt(sum(x * x for x in vector))
    return vector if length == 0 else [x / length for x in vector]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))
