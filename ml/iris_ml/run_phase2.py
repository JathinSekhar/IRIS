"""Phase 2 runner.

    python -m iris_ml.run_phase2 experiments [--variants conservative lenient] [--only NAME ...] [--skip-finetune]
    python -m iris_ml.run_phase2 report

`experiments` runs every model in SPECS with the shared protocol (see experiments.py) and caches the out-of-fold results.
`report` turns the cached results, the final system, the ESConv workload audit and the challenge set into the report.
Only development users are ever loaded. The held-out test users and the gold set are not touched.
"""
from __future__ import annotations

import argparse
import time

from . import embeddings
from .experiments import Spec, prepare, run_spec

MINI, MPNET = embeddings.MINILM, embeddings.MPNET

# Registry fixed BEFORE seeing results. Cheap families use 3 repeats of 5-fold CV; fine-tuning uses 1 (GPU time).
SPECS: list[Spec] = [
    Spec("m1_doc_tfidf", "doc_tfidf"),
    Spec("e1_chunk_tfidf", "chunk_tfidf"),
    Spec("e1s_chunk_tfidf_syn", "chunk_tfidf", syn=True),
    Spec("e2_minilm_lr", "emb_lr", MINI),
    Spec("e2s_minilm_lr_syn", "emb_lr", MINI, syn=True),
    Spec("e2_mpnet_lr", "emb_lr", MPNET),
    Spec("e2s_mpnet_lr_syn", "emb_lr", MPNET, syn=True),
    Spec("e2h_mpnet_head_ce", "emb_head", MPNET, head="ce"),
    Spec("e2o_mpnet_head_ordinal", "emb_head", MPNET, head="ordinal"),
    Spec("e5_minilm_mil", "mil", MINI),
    Spec("e5_mpnet_mil", "mil", MPNET),
    Spec("e5s_mpnet_mil_syn", "mil", MPNET, syn=True),
    Spec("e5o_mpnet_mil_ordinal", "mil", MPNET, head="ordinal"),
    Spec("e3_distilroberta_ft", "finetune", repeats=1),
    Spec("e3s_distilroberta_ft_syn", "finetune", syn=True, repeats=1),
    Spec("e3o_distilroberta_ft_ordinal", "finetune", head="ordinal", repeats=1),
    # Added after the first results (trained on the psychiatrists' five labels, mapped to urgency afterwards)
    Spec("n5_m1_doc_tfidf", "doc_tfidf", target="native5"),
    Spec("n5_e1_chunk_tfidf", "chunk_tfidf", target="native5"),
    Spec("n5_e2_minilm_lr", "emb_lr", MINI, target="native5"),
    Spec("n5_e2_mpnet_lr", "emb_lr", MPNET, target="native5"),
    Spec("n5_e2o_mpnet_head_ordinal", "emb_head", MPNET, head="ordinal", target="native5"),
]
# The lenient mapping is run for the Phase 1 baseline and the strongest families only (sensitivity analysis).
LENIENT_SPECS = {"m1_doc_tfidf", "e2_mpnet_lr", "e2s_mpnet_lr_syn", "e5_mpnet_mil", "e5s_mpnet_mil_syn", "e3_distilroberta_ft",
                 "n5_m1_doc_tfidf", "n5_e2_mpnet_lr"}


def _finetune_allowed() -> bool:
    """Fine-tuning through this CLI needs a GPU AND an explicit opt-in (IRIS_ALLOW_FINETUNE=1). The development laptop never trains:
    the supported route is ml/colab/colab_finetune.py, which does not use this CLI."""
    import os
    import torch
    return os.environ.get("IRIS_ALLOW_FINETUNE") == "1" and torch.cuda.is_available()


def run_experiments(variants: list[str], only: list[str] | None, skip_finetune: bool) -> None:
    for variant in variants:
        prep = prepare(variant)
        print(f"== variant {variant}: {len(prep.y)} users, {len(prep.chunks)} chunks, {len(prep.synth)} synthetic messages", flush=True)
        for spec in SPECS:
            if only and spec.name not in only:
                continue
            if skip_finetune and spec.family == "finetune":
                continue
            if spec.family == "finetune" and not _finetune_allowed():
                print(f"-- {variant}/{spec.name}: skipped (fine-tuning runs on Colab only): see ml/colab/README.md", flush=True)
                continue
            if variant == "lenient" and spec.name not in LENIENT_SPECS:
                continue
            t = time.time()
            res = run_spec(spec, prep)
            print(f"-- {variant}/{spec.name}: done in {time.time() - t:.0f}s (stored {res.seconds:.0f}s)", flush=True)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["experiments", "report"])
    ap.add_argument("--variants", nargs="+", default=["conservative", "lenient"])
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--skip-finetune", action="store_true")
    args = ap.parse_args(argv)
    if args.command == "experiments":
        run_experiments(args.variants, args.only, args.skip_finetune)
    else:
        from .report2 import build_report
        build_report()


if __name__ == "__main__":
    main()
