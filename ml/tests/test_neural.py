import numpy as np
import pytest
import torch

from iris_ml import embeddings, neural


# --- heads -----------------------------------------------------------------------------------------------------------

def test_ordinal_head_outputs_valid_ordered_probabilities():
    torch.manual_seed(0)
    head = neural.OrdinalHead(8, 3)
    p = head(torch.randn(50, 8)).exp()
    assert torch.allclose(p.sum(dim=1), torch.ones(50), atol=1e-4) and (p >= 0).all()
    th = head.thresholds()
    assert th[1] > th[0]                                                    # thresholds are strictly increasing


def test_ordinal_head_shifts_mass_monotonically_with_the_score():
    head = neural.OrdinalHead(1, 3)
    with torch.no_grad():
        head.score.weight.fill_(1.0)
        head.score.bias.zero_()
    p = head(torch.tensor([[-5.0], [0.0], [5.0]])).exp()
    expected_level = (p * torch.arange(3.0)).sum(dim=1)
    assert expected_level[0] < expected_level[1] < expected_level[2]
    assert p[0].argmax() == 0 and p[2].argmax() == 2


def test_unknown_head_rejected():
    with pytest.raises(ValueError):
        neural.make_head("magic", 4)


def test_class_weights_favour_the_rare_class():
    w = neural.class_weights(np.array([0] * 90 + [1] * 8 + [2] * 2), 3)
    assert w[2] > w[1] > w[0]


@pytest.mark.parametrize("kind", ["ce", "ordinal"])
def test_embedding_head_learns_a_separable_problem(kind):
    rng = np.random.default_rng(0)
    y = rng.integers(0, 3, 400)
    X = rng.normal(size=(400, 6)).astype(np.float32)
    X[:, 0] += (y - 1) * 3.0                                                # urgency is encoded along one axis
    head = neural.fit_embedding_head(X, y, kind=kind, epochs=400, lr=1e-2, seed=1)   # the ordinal head moves its thresholds slowly
    pred = neural.predict_head(head, X).argmax(axis=1)
    assert (pred == y).mean() > 0.85


# --- attention multiple-instance model -------------------------------------------------------------------------------------

def toy_bags(n=120, d=8, seed=0):
    """A bag is High if ANY of its chunks carries the signal pattern; most chunks are noise."""
    rng = np.random.default_rng(seed)
    bags, y = [], []
    for _ in range(n):
        k = rng.integers(3, 12)
        b = rng.normal(size=(k, d)).astype(np.float32) * 0.5
        label = int(rng.random() < 0.5) * 2
        if label == 2:
            b[rng.integers(0, k), 0] += 4.0                                  # one telling chunk among many
        bags.append(b)
        y.append(label)
    return bags, np.array(y)


def test_pad_bags_masks_padding():
    x, m = neural.pad_bags([np.ones((2, 4), np.float32), np.ones((5, 4), np.float32)], "cpu")
    assert x.shape == (2, 5, 4) and m.sum(dim=1).tolist() == [2, 5] and x[0, 2:].abs().sum() == 0


def test_mil_finds_the_one_telling_chunk_and_ignores_padding():
    bags, y = toy_bags()
    model = neural.fit_mil(bags, y, kind="ce", epochs=60, lr=3e-3, seed=0)
    probs, att = neural.predict_mil(model, bags)
    assert (probs.argmax(axis=1) == y).mean() > 0.9
    high = [i for i in range(len(bags)) if y[i] == 2][:20]
    hit = np.mean([int(att[i].argmax() == bags[i][:, 0].argmax()) for i in high])
    assert hit > 0.7                                                         # attention lands on the informative chunk
    # padding must not matter: scoring one bag alone or batched with longer bags gives the same answer
    alone, _ = neural.predict_mil(model, [bags[0]])
    batched, _ = neural.predict_mil(model, bags[:10])
    assert np.allclose(alone[0], batched[0], atol=1e-4)


# --- embedding cache ---------------------------------------------------------------------------------------------------------

class FakeEncoder:
    def __init__(self):
        self.calls = 0

    def encode(self, texts, **kw):
        self.calls += 1
        rng = np.random.default_rng(abs(hash(tuple(texts))) % 2**32)
        v = rng.normal(size=(len(texts), 5))
        return v / np.linalg.norm(v, axis=1, keepdims=True)


def test_embeddings_are_cached_by_content_and_model_name(tmp_path):
    enc = FakeEncoder()
    a = embeddings.embed(["hello there", "how are you"], name="fake/m", cache_dir=tmp_path, encoder=enc)
    b = embeddings.embed(["hello there", "how are you"], name="fake/m", cache_dir=tmp_path, encoder=enc)
    assert enc.calls == 1 and np.array_equal(a, b) and a.dtype == np.float32
    embeddings.embed(["hello there", "different text"], name="fake/m", cache_dir=tmp_path, encoder=enc)
    embeddings.embed(["hello there", "how are you"], name="fake/other", cache_dir=tmp_path, encoder=enc)
    assert enc.calls == 3                                                    # changed text or model name: recomputed
    assert not any("hello there" in p.read_bytes().decode("latin-1") for p in tmp_path.glob("*.npy"))   # no raw text on disk


# --- fine-tuning (uses the cached DistilRoBERTa; skipped if it was never downloaded) ---------------------------------------------

def _model_cached() -> bool:
    try:
        from transformers import AutoTokenizer
        AutoTokenizer.from_pretrained("distilroberta-base", local_files_only=True)
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _model_cached(), reason="distilroberta-base is not in the local cache")
def test_finetune_learns_a_trivial_text_task_and_returns_probabilities():
    texts = ["I am so happy and calm today"] * 20 + ["I am furious and everything is terrible"] * 20
    y = np.array([0] * 20 + [2] * 20)
    ft = neural.FineTuneScorer(neural.FTConfig(epochs=3, batch_size=8, max_len=32, seed=0)).fit(texts, y)
    p = ft.predict_proba(["I am so happy and calm today", "I am furious and everything is terrible"])
    assert p.shape == (2, 3) and np.allclose(p.sum(axis=1), 1.0, atol=1e-3)
    assert p[0].argmax() == 0 and p[1].argmax() == 2
    ft.free()
