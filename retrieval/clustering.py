"""Optional semantic clustering (sklearn) with simple keyword labels."""

from __future__ import annotations

import re
from collections import Counter

from retrieval.types import NormalizedResult


def _top_keywords_for_texts(texts: list[str], k: int = 3) -> str:
    toks: list[str] = []
    for t in texts:
        toks.extend(re.findall(r"[a-z][a-z0-9]{2,}", t.lower()))
    stop = frozenset(
        "the a an and or for to of in on at is are was were be been being it this that with from as by "
        "http https www com org net".split()
    )
    counts = Counter(w for w in toks if w not in stop and len(w) > 2)
    parts = [w for w, _ in counts.most_common(k)]
    return ", ".join(parts) if parts else "Results"


def cluster_results(
    results: list[NormalizedResult],
    *,
    max_clusters: int = 8,
) -> list[NormalizedResult]:
    """Attach ``cluster_id`` and ``cluster_label`` in ``extra`` when sklearn is available."""
    n = len(results)
    if n < 4:
        for i, r in enumerate(results):
            r.extra = {**r.extra, "cluster_id": 0, "cluster_label": "All"}
        return results

    try:
        from sklearn.cluster import AgglomerativeClustering
        import numpy as np
    except ImportError:
        for r in results:
            r.extra = {**r.extra, "cluster_id": 0, "cluster_label": "All"}
        return results

    from retrieval.embeddings import embed_text

    mat = np.array([list(embed_text(f"{r.title}\n{r.snippet}"[:800])) for r in results], dtype=np.float64)
    n_clust = min(max_clusters, max(2, n // 5))
    try:
        model = AgglomerativeClustering(n_clusters=n_clust, linkage="average", metric="cosine")
    except TypeError:
        model = AgglomerativeClustering(n_clusters=n_clust, linkage="average", affinity="cosine")
    labels = model.fit_predict(mat)

    clusters: dict[int, list[NormalizedResult]] = {}
    for r, lab in zip(results, labels):
        clusters.setdefault(int(lab), []).append(r)

    cluster_labels: dict[int, str] = {}
    for lab, members in clusters.items():
        texts = [f"{m.title} {m.snippet[:200]}" for m in members[:12]]
        cluster_labels[lab] = _top_keywords_for_texts(texts)

    for r, lab in zip(results, labels):
        lid = int(lab)
        r.extra = {
            **r.extra,
            "cluster_id": lid,
            "cluster_label": cluster_labels.get(lid, "Topic"),
        }
    return results
