"""
compute_deviation_feature.py

Computes the primary feature: embedding distance between each post and the
author's own rolling historical centroid ("deviation from usual rhetoric"),
per decision #9 -- point-in-time correct, using a TRAILING 180-CALENDAR-DAY
window with a minimum-post floor.

Design decisions baked in here (see conversation for reasoning):
  - Embedding model: sentence-transformers/all-mpnet-base-v2 (free, local,
    768-dim). Chosen over a smaller model since this is the primary feature
    the whole thesis depends on, not descriptive metadata -- and over an
    API-based embedding since a vendored local model gives a stronger
    "frozen, reproducible" guarantee (decision #8) without depending on a
    provider's model-versioning discipline.
  - Centroid window: trailing 180 calendar days, STRICTLY before the post
    being scored (no same-post or future leakage -- point-in-time correct
    per decision #9). This is deliberately a calendar-time window, not a
    fixed post-count window, so "recent" means the same thing for a
    high-frequency account (Tenev) and a low-frequency one (Amon).
  - Minimum-post floor: 20 posts required within the trailing window, else
    the post is marked insufficient_history=True and excluded from the
    confirmatory test. In practice this only excludes each account's first
    ~3-4 weeks of data (see reasoning in conversation) -- it is NOT expected
    to meaningfully reduce usable sample size for any confirmatory account.
  - Deviation metric: cosine distance (1 - cosine similarity) between the
    post's embedding and the mean of its window's prior embeddings. Cosine
    distance chosen over Euclidean since it's the standard choice for
    sentence-embedding similarity (magnitude is not meaningful for these
    embeddings; direction is).

This script does NOT touch market data, labels, or confound exclusion --
it only produces the deviation feature, per author, per post. Join against
the label-construction output separately.

Expected input CSV columns (one file per account, or one combined file with
an author_id column):
    id, author_id, created_at_utc, text, ... (extra columns ignored)

Usage:
    pip install sentence-transformers pandas --break-system-packages

    # single account
    python compute_deviation_feature.py --input nadella_posts.csv --output nadella_deviation.csv

    # multiple accounts at once (author_id must distinguish them)
    python compute_deviation_feature.py --input all_posts_combined.csv --output all_deviation.csv
"""

import argparse
import sys

import numpy as np
import pandas as pd

EMBEDDING_MODEL = "sentence-transformers/all-mpnet-base-v2"
WINDOW_DAYS = 180
MIN_POSTS_FLOOR = 20  
BATCH_SIZE = 32


def load_posts(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"id": str, "author_id": str})
    required = ["id", "author_id", "created_at_utc", "text"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"{path}: missing expected columns {missing}. Found: {list(df.columns)}")
    df["created_at_utc"] = pd.to_datetime(df["created_at_utc"], utc=True)
    df["text"] = df["text"].fillna("").astype(str)
    return df.sort_values(["author_id", "created_at_utc"]).reset_index(drop=True)


def embed_posts(texts: list, model_name: str = EMBEDDING_MODEL) -> np.ndarray:
    from sentence_transformers import SentenceTransformer
    print(f"Loading {model_name} ...", file=sys.stderr)
    model = SentenceTransformer(model_name)
    print(f"Encoding {len(texts)} posts ...", file=sys.stderr)
    embeddings = model.encode(
        texts, batch_size=BATCH_SIZE, show_progress_bar=True, normalize_embeddings=True
    )
    return np.asarray(embeddings)


def cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    return float(1.0 - np.dot(a, b))


def compute_deviation_for_author(author_df: pd.DataFrame, embeddings: np.ndarray) -> pd.DataFrame:
    out_rows = []
    window = pd.Timedelta(days=WINDOW_DAYS)

    for i in range(len(author_df)):
        t0 = author_df["created_at_utc"].iloc[i]
        window_start = t0 - window
        
        prior_mask = (author_df["created_at_utc"] < t0) & (author_df["created_at_utc"] >= window_start)
        prior_idx = author_df.index[prior_mask]
        n_prior = len(prior_idx)

        row = {
            "post_id": author_df["id"].iloc[i],
            "author_id": author_df["author_id"].iloc[i],
            "created_at_utc": t0,
            "n_prior_posts_180d": n_prior,
            "insufficient_history": n_prior < MIN_POSTS_FLOOR,
            "deviation_score": None,
            "embedding_model": EMBEDDING_MODEL,
        }

        if n_prior >= MIN_POSTS_FLOOR:
            local_positions = [author_df.index.get_loc(idx) for idx in prior_idx]
            centroid = embeddings[local_positions].mean(axis=0)
            centroid = centroid / np.linalg.norm(centroid)  # re-normalize after averaging
            row["deviation_score"] = cosine_distance(embeddings[i], centroid)

        out_rows.append(row)

    return pd.DataFrame(out_rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model", default=EMBEDDING_MODEL)
    parser.add_argument("--cache-embeddings", help="Optional .npy path to save/reuse computed embeddings")
    args = parser.parse_args()

    posts = load_posts(args.input)
    print(f"Loaded {len(posts)} posts across {posts['author_id'].nunique()} author(s).", file=sys.stderr)

    if args.cache_embeddings:
        import os
        if os.path.exists(args.cache_embeddings):
            print(f"Loading cached embeddings from {args.cache_embeddings}", file=sys.stderr)
            embeddings = np.load(args.cache_embeddings)
            if len(embeddings) != len(posts):
                raise ValueError(
                    f"Cached embeddings ({len(embeddings)}) don't match post count ({len(posts)}) "
                    f"-- input file likely changed. Delete the cache and re-run."
                )
        else:
            embeddings = embed_posts(posts["text"].tolist(), args.model)
            np.save(args.cache_embeddings, embeddings)
            print(f"Saved embeddings to {args.cache_embeddings}", file=sys.stderr)
    else:
        embeddings = embed_posts(posts["text"].tolist(), args.model)

    results = []
    for author_id, group in posts.groupby("author_id", sort=False):
        group_positions = [posts.index.get_loc(idx) for idx in group.index]
        author_embeddings_full = embeddings[group_positions]
        local_df = group.reset_index(drop=True)
        result = compute_deviation_for_author(local_df, author_embeddings_full)
        results.append(result)
        n_insufficient = result["insufficient_history"].sum()
        print(
            f"  {author_id}: {len(result)} posts, {n_insufficient} marked insufficient_history "
            f"({100 * n_insufficient / len(result):.1f}%)",
            file=sys.stderr,
        )

    out = pd.concat(results, ignore_index=True)
    out.to_csv(args.output, index=False)
    print(f"\nWrote {args.output}", file=sys.stderr)

    valid = out["deviation_score"].dropna()
    if len(valid):
        print(f"\ndeviation_score (n={len(valid)}): min={valid.min():.4f}, median={valid.median():.4f}, max={valid.max():.4f}")
        print("Sanity check: scores should mostly be small (similar posts), with a right tail")
        print("for genuinely off-brand posts. A distribution clustered near 0 everywhere would")
        print("suggest posts are too similar to distinguish; a distribution with no low end would")
        print("suggest something's off with the centroid computation (e.g. index-misalignment bug).")


if __name__ == "__main__":
    main()