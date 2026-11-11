"""Grounding scoring: combine CLIP similarity, label lexical match, and spatial fit."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class ScoreWeights:
    clip: float = 0.7
    label: float = 0.2
    spatial: float = 0.1
    attr_clip: float = 0.6
    attr_label: float = 0.3
    attr_spatial: float = 0.1


def lexical_label_match(target_noun: str, object_label: str) -> float:
    """Substring match with partial credit for shared prefixes.

    Character-overlap fallback is only applied to sufficiently long tokens,
    otherwise short words like 'car' vs 'chair' produce spurious matches.
    """
    if not target_noun or not object_label:
        return 0.0
    t = target_noun.strip().lower()
    lbl = object_label.strip().lower()
    if t == lbl:
        return 1.0
    if t in lbl or lbl in t:
        return 0.7
    # Character overlap fallback — guarded by min length to avoid short-word noise.
    if len(t) < 4 or len(lbl) < 4:
        return 0.0
    t_set = set(t)
    l_set = set(lbl)
    if not t_set or not l_set:
        return 0.0
    return 0.3 * (len(t_set & l_set) / len(t_set | l_set))


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    if a.shape != b.shape or a.size == 0:
        return 0.0
    an = float(np.linalg.norm(a))
    bn = float(np.linalg.norm(b))
    if an < 1e-9 or bn < 1e-9:
        return 0.0
    return float(np.dot(a, b) / (an * bn))


def combine(
    clip_score: float,
    label_score: float,
    spatial_score: float,
    weights: ScoreWeights | None = None,
    has_attribute: bool = False,
) -> float:
    """Combine the three sub-scores into a single ranking score.

    - Without an attribute query, use the configured weights verbatim.
    - With an attribute query (e.g. "black chair"), bias toward CLIP so that
      colour/material differences are not diluted by the label/spatial floors,
      but still honour the configured weights as the *base* mix.
    """
    w = weights or ScoreWeights()

    if not has_attribute:
        return float(
            w.clip * clip_score + w.label * label_score + w.spatial * spatial_score
        )

    # Attribute-aware blend: CLIP dominates, but label still gets a real vote.
    total_w = w.attr_clip + w.attr_label + w.attr_spatial
    if total_w <= 1e-9:
        a_clip, a_label, a_spatial = 0.6, 0.3, 0.1
    else:
        a_clip = w.attr_clip / total_w
        a_label = w.attr_label / total_w
        a_spatial = w.attr_spatial / total_w

    base = (
        a_clip * clip_score
        + a_label * label_score
        + a_spatial * spatial_score
    )
    if label_score < 0.1:
        base *= 0.3
    return float(base)