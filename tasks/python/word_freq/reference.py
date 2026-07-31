from collections import Counter


def _words(text: str) -> list[str]:
    out, current = [], []
    for ch in text:
        if ch.isalnum():
            current.append(ch)
        elif current:
            out.append("".join(current))
            current = []
    if current:
        out.append("".join(current))
    return out


def top_k(text: str, k: int) -> list[tuple[str, int]]:
    counts = Counter(w.lower() for w in _words(text))
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return ranked[:k]
