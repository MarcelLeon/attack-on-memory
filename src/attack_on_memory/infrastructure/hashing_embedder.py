"""Deterministic zero-dependency hashing embeddings for local baselines."""

from __future__ import annotations

import hashlib
import math
import re


TOKEN_RE = re.compile(r"[a-zA-Z0-9_\-\u4e00-\u9fff]+")


class HashingTextEmbedder:
    """Project normalized token counts into a stable signed hashing space.

    This is a reproducible lexical baseline, not a substitute for a production
    semantic embedding model. It implements the same embedder contract so a
    hosted or local model can be injected without changing storage semantics.
    """

    def __init__(self, dimensions: int = 256) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be > 0")
        self.dimensions = dimensions

    def embed(self, text: str) -> tuple[float, ...]:
        vector = [0.0] * self.dimensions
        for token in TOKEN_RE.findall(text.lower()):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            raw = int.from_bytes(digest, "big")
            index = raw % self.dimensions
            sign = 1.0 if raw & (1 << 63) else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            return tuple(vector)
        return tuple(value / norm for value in vector)
