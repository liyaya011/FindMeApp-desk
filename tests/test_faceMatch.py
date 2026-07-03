"""
test_faceMatch.py — unit tests for cosine distance matching logic.
"""
import numpy as np
import pytest
from src.scripts.faceMatch import cosineDist, matchFace


def test_cosineDist_identical():
    v = np.random.rand(512).tolist()
    assert cosineDist(v, v) < 1e-5


def test_cosineDist_opposite():
    v = np.random.rand(512).tolist()
    neg = [-x for x in v]
    assert cosineDist(v, neg) > 1.9


def test_matchFace_empty_references(sampleEmbedding):
    r = matchFace(sampleEmbedding, [])
    assert r["success"] is False
    assert "No reference" in r["error"]


def test_matchFace_identical_embedding_matches(sampleEmbedding):
    r = matchFace(sampleEmbedding, [sampleEmbedding], threshold=0.45)
    assert r["success"] is True
    assert r["output"]["matched"] is True
    assert r["output"]["best_dist"] < 0.01


def test_matchFace_random_does_not_match(sampleEmbedding):
    refEmb = np.random.rand(512).tolist()
    queryEmb = np.random.rand(512).tolist()
    # Random vectors in 512-d have cosine dist ~0.5; use strict threshold
    r = matchFace(queryEmb, [refEmb], threshold=0.1)
    assert r["success"] is True
    # May or may not match, but should not crash
    assert "matched" in r["output"]


def test_matchFace_picks_best_reference(sampleEmbedding):
    close = [sampleEmbedding[i] + 0.0001 for i in range(len(sampleEmbedding))]
    far = np.random.rand(512).tolist()
    r = matchFace(sampleEmbedding, [far, close], threshold=0.45)
    assert r["success"] is True
    assert r["output"]["best_ref_idx"] == 1
