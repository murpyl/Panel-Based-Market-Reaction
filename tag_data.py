import argparse
import glob
import os
import sys

import pandas as pd

CANDIDATE_LABELS = [
    "business or market relevant commentary",
    "personal, political, or non-business content",
]
LABEL_MAP = {
    CANDIDATE_LABELS[0]: "business/market relevant",
    CANDIDATE_LABELS[1]: "personal/non-business",
}

DEFAULT_MODEL = "facebook/bart-large-mnli"
BATCH_SIZE = 16


def load_posts(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"id": str, "author_id": str})
    return df


def build_classifier(model_name: str):
    from transformers import pipeline
    return pipeline("zero-shot-classification", model=model_name)


def tag_dataframe(df: pd.DataFrame, classifier, model_name: str, batch_size: int = BATCH_SIZE) -> pd.DataFrame:
    df = df.copy()
    texts = df["text"].fillna("").astype(str).tolist()
    labels = []
    scores = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start:start + BATCH_SIZE]
        is_empty = [len(b) == 0 for b in batch]
        nonempty_batch = [t for t, b in zip(batch, is_empty) if not b]
        batch_results = classifier(nonempty_batch, CANDIDATE_LABELS)
        iterx = iter(batch_results)
        for empty in is_empty:
            if empty:
                labels.append("unclassified, empty")
                scores.append(float("nan"))
            else:
                r = next(iterx)
                l = r["labels"][0]
                s = r["scores"][0]
                labels.append(LABEL_MAP[l])
                scores.append(round(float(s), 4))
        print(f"Processed {start} to {start + BATCH_SIZE} tweets")
    df["market_relevant_label"] = labels
    df["market_relevant_score"] = scores
    df["market_relevant_model"] = model_name
    return df



def summarize(df: pd.DataFrame, account_name: str) -> dict:
    counts = df["market_relevant_label"].value_counts(dropna=False)
    total = len(df)
    return {
        "account_name": account_name,
        "total": total, 
        "relevant": counts.get("business/market relevant", 0),
        "personal": counts.get("personal/non-business", 0),
        "unclassified": counts.get("unclassified, empty", 0),
        "percent_relevant": round(counts["business/market relevant"] / total * 100, 2),
        "total_score": df["market_relevant_score"].sum(),
        "avg_score": df["market_relevant_score"].mean(),
        "std_score": df["market_relevant_score"].std(),
        "min_score": df["market_relevant_score"].min(),
        "max_score": df["market_relevant_score"].max(),
    }


def process_file(input_path: str, output_path: str, model_name: str, sample: int, classifier=None):
    print(f"Processing {input_path}")
    df = load_posts(input_path)
    if sample: 
        df = df.head(sample)
        print(f"Sampled {len(df)} rows")
    if classifier is None:
        classifier = build_classifier(model_name)
    tagged = tag_dataframe(df, classifier, model_name)
    tagged.to_csv(output_path, index=False)
    print(f"Wrote {len(tagged)} rows to {output_path}")
    account = os.path.splitext(os.path.basename(input_path))[0]
    return summarize(tagged, account)


def print_summary_table(summaries: list):
    if not summaries:
        print("No summaries found.")
        return
    summary_df = pd.DataFrame(summaries)
    summary_df = summary_df.sort_values("account_name").reset_index(drop=True)
    print(summary_df.to_string(index=False))
    return summary_df

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", help="Single input CSV path")
    parser.add_argument("--output", help="Single output CSV path (required with --input)")
    parser.add_argument("--input-dir", help="Directory of per-account input CSVs (*.csv)")
    parser.add_argument("--output-dir", help="Directory to write tagged CSVs to (required with --input-dir)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"HF zero-shot model name (default: {DEFAULT_MODEL})")
    parser.add_argument("--sample", type=int, default=0, help="Only tag the first N rows (0 = all rows)")
    parser.add_argument("--summary-only", action="store_true",
                         help="Skip tagging; just recompute the summary table from already-tagged CSVs in --output-dir")
    args = parser.parse_args()

    if args.summary_only:
        if not args.output_dir:
            parser.error("--summary-only requires --output-dir")
        summaries = []
        for path in sorted(glob.glob(os.path.join(args.output_dir, "*.csv"))):
            df = pd.read_csv(path)
            if "market_relevant_label" not in df.columns:
                continue
            account_name = os.path.splitext(os.path.basename(path))[0]
            summaries.append(summarize(df, account_name))
        print_summary_table(summaries)
        return

    if args.input:
        if not args.output:
            parser.error("--input requires --output")
        summary = process_file(args.input, args.output, args.model, args.sample)
        print_summary_table([summary])
        return

    if args.input_dir:
        if not args.output_dir:
            parser.error("--input-dir requires --output-dir")
        os.makedirs(args.output_dir, exist_ok=True)
        classifier = build_classifier(args.model)  # build once, reuse across files
        summaries = []
        for in_path in sorted(glob.glob(os.path.join(args.input_dir, "*.csv"))):
            out_path = os.path.join(args.output_dir, os.path.basename(in_path))
            summaries.append(process_file(in_path, out_path, args.model, args.sample, classifier=classifier))
        summary_df = print_summary_table(summaries)
        if summary_df is not None:
            summary_path = os.path.join(args.output_dir, "_relevance_summary.csv")
            summary_df.to_csv(summary_path, index=False)
            print(f"\nWrote summary table to {summary_path}", file=sys.stderr)
        return

    parser.error("Provide either --input/--output or --input-dir/--output-dir (or --summary-only)")


if __name__ == "__main__":
    main()