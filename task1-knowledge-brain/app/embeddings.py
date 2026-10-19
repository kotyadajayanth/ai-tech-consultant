"""Embedders. 'hash' needs no download and no API, so tests and the first demo run anywhere.
It is a BASELINE: compare it with 'fastembed' (set EMBEDDER=fastembed) in EVALS.md."""
import hashlib
import re

import numpy as np

_TOKEN = re.compile(r"[a-z0-9]+")
STOP = set("a an the and or of to in on for is are was be do does how what can i my me you your it this that with at by from as if we".split())


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in STOP]


class HashEmbedder:
    name = "hash-512"
    dim = 512

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, text in enumerate(texts):
            toks = tokenize(text)
            for feat in toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:])]:
                h = int.from_bytes(hashlib.md5(feat.encode()).digest()[:8], "big")
                out[i, h % self.dim] += 1.0 if (h >> 63) & 1 else -1.0
            n = np.linalg.norm(out[i])
            if n:
                out[i] /= n
        return out


class FastEmbedder:
    """Optional local model: pip install fastembed"""
    name = "fastembed-bge-small"

    def __init__(self) -> None:
        from fastembed import TextEmbedding  # imported lazily so it stays optional
        self._m = TextEmbedding("BAAI/bge-small-en-v1.5")

    def embed(self, texts: list[str]) -> np.ndarray:
        v = np.array(list(self._m.embed(texts)), dtype=np.float32)
        return v / np.linalg.norm(v, axis=1, keepdims=True)


def get_embedder(name: str):
    return FastEmbedder() if name == "fastembed" else HashEmbedder()
