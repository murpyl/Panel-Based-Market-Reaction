import argparse
import sys
import warnings

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score


UNREGULARIZED_C = 1e6  # effectively unregularized without the numerical risk of literal np.inf

MIN_TRAIN_ROWS = 30  # walk-forward: skip a test point if fewer than this many training rows are available


def load_confirmatory_rows(panel_path: str) -> pd.DataFrame:
    df = pd.read_csv(panel_path)
    required = ["post_id", "author_id", "created_at_utc", "deviation_score",
                "abnormal_volatility_flag", "final_confirmatory_eligible"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"{panel_path}: missing columns {missing}. Found: {list(df.columns)}")
    df["created_at_utc"] = pd.to_datetime(df["created_at_utc"], utc=True)
    conf = df[df["final_confirmatory_eligible"] == True].copy()  # noqa: E712
    conf = conf.dropna(subset=["deviation_score", "abnormal_volatility_flag"])
    conf["y"] = conf["abnormal_volatility_flag"].astype(int)
    return conf.sort_values("created_at_utc").reset_index(drop=True)


def cluster_robust_se(X: np.ndarray, y: np.ndarray, beta: np.ndarray, clusters: np.ndarray) -> np.ndarray:
    """
    Standard cluster-robust (CR0) sandwich SE for a fitted logistic regression.
    X includes an intercept column. beta is [intercept, coef1, ...].
    Returns SE for each coefficient in beta, same order.
    """
    linear_pred = X @ beta
    p = 1 / (1 + np.exp(-linear_pred))
    W = p * (1 - p)

    # "Bread": inverse Fisher information, (X' W X)^-1
    bread = np.linalg.inv((X * W[:, None]).T @ X)

    # "Meat": sum over clusters of outer product of summed per-cluster scores
    score = (y - p)[:, None] * X  # per-observation score contribution
    meat = np.zeros((X.shape[1], X.shape[1]))
    for c in np.unique(clusters):
        cluster_score = score[clusters == c].sum(axis=0)
        meat += np.outer(cluster_score, cluster_score)

    sandwich = bread @ meat @ bread
    return np.sqrt(np.diag(sandwich))


def run_primary_test(conf: pd.DataFrame):
    x = conf["deviation_score"].values
    x_z = (x - x.mean()) / x.std()  # standardized: coefficient = effect per 1 SD of deviation
    X = np.column_stack([np.ones(len(x_z)), x_z])
    y = conf["y"].values
    clusters = conf["author_id"].values

    model = LogisticRegression(C=UNREGULARIZED_C, fit_intercept=False)  # intercept already in X
    model.fit(X, y)
    beta = model.coef_[0]  # [intercept, deviation_score_z]

    se = cluster_robust_se(X, y, beta, clusters)
    z_stats = beta / se
    p_values = 2 * (1 - stats.norm.cdf(np.abs(z_stats)))

    print("\n=== PRIMARY CONFIRMATORY TEST ===")
    print(f"n = {len(conf)}, accounts = {conf['author_id'].nunique()}, "
          f"positive rate = {y.mean():.3f}")
    print(f"deviation_score coefficient (per 1 SD): {beta[1]:.4f}")
    print(f"cluster-robust SE (by author_id):        {se[1]:.4f}")
    print(f"z-statistic:                              {z_stats[1]:.4f}")
    print(f"two-sided p-value:                        {p_values[1]:.4f}")
    print(f"odds ratio per 1 SD deviation increase:   {np.exp(beta[1]):.4f}")
    print("\nRemember: this p-value is uncorrected. Apply Bonferroni across this test plus")
    print("any secondary horizon tests (5-min/60-min) before reporting significance.")

    return {"coef": beta[1], "se": se[1], "z": z_stats[1], "p_value": p_values[1]}


def walk_forward_predict(conf: pd.DataFrame, model_factory):
    """
    model_factory: callable() -> a fresh unfit sklearn classifier.
    Returns a DataFrame of out-of-fold predictions (one row per confirmatory
    post, across all 4 LOAO folds).
    """
    accounts = conf["author_id"].unique()
    all_preds = []
    n_skipped = 0

    for held_out in accounts:
        test_rows = conf[conf["author_id"] == held_out].sort_values("created_at_utc")
        train_pool = conf[conf["author_id"] != held_out]

        for row in test_rows.itertuples():
            train_data = train_pool[train_pool["created_at_utc"] < row.created_at_utc]
            if len(train_data) < MIN_TRAIN_ROWS or train_data["y"].nunique() < 2:
                n_skipped += 1
                continue

            x_train = train_data["deviation_score"].values
            mean_, std_ = x_train.mean(), x_train.std()
            if std_ == 0:
                n_skipped += 1
                continue
            x_train_z = ((x_train - mean_) / std_).reshape(-1, 1)
            y_train = train_data["y"].values

            model = model_factory()
            model.fit(x_train_z, y_train)

            x_test_z = np.array([[(row.deviation_score - mean_) / std_]])
            pred_prob = model.predict_proba(x_test_z)[0, 1]

            all_preds.append({
                "post_id": row.post_id,
                "author_id": held_out,
                "created_at_utc": row.created_at_utc,
                "y_true": row.y,
                "pred_prob": pred_prob,
                "train_n": len(train_data),
            })

    print(f"  skipped {n_skipped} test points (insufficient/degenerate training history at that point in time)",
          file=sys.stderr)
    return pd.DataFrame(all_preds)


def summarize_cv(preds: pd.DataFrame, label: str):
    if len(preds) == 0:
        print(f"{label}: no predictions produced.")
        return
    overall_auc = roc_auc_score(preds["y_true"], preds["pred_prob"]) if preds["y_true"].nunique() == 2 else float("nan")
    print(f"\n=== {label}: LOAO walk-forward CV ===")
    print(f"Total out-of-fold predictions: {len(preds)}")
    print(f"Overall AUC: {overall_auc:.4f}" if not np.isnan(overall_auc) else "Overall AUC: undefined (single class)")
    print("Per-account AUC:")
    for account, grp in preds.groupby("author_id"):
        if grp["y_true"].nunique() == 2:
            auc = roc_auc_score(grp["y_true"], grp["pred_prob"])
            print(f"  {account}: n={len(grp)}, AUC={auc:.4f}")
        else:
            print(f"  {account}: n={len(grp)}, AUC=undefined (only one class present in this fold)")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--panel", required=True, help="Output of assemble_final_panel.py")
    parser.add_argument("--output-predictions", required=True)
    args = parser.parse_args()

    conf = load_confirmatory_rows(args.panel)
    print(f"Loaded {len(conf)} confirmatory-eligible rows across {conf['author_id'].nunique()} accounts.",
          file=sys.stderr)

    primary_result = run_primary_test(conf)

    print("\nRunning LOAO walk-forward CV (logistic regression)...", file=sys.stderr)
    logit_preds = walk_forward_predict(conf, lambda: LogisticRegression(C=UNREGULARIZED_C))
    logit_preds["model"] = "logistic_regression"
    summarize_cv(logit_preds, "Logistic regression")

    print("\nRunning LOAO walk-forward CV (shallow gradient-boosted tree)...", file=sys.stderr)
    gbt_preds = walk_forward_predict(
        conf,
        lambda: GradientBoostingClassifier(max_depth=2, n_estimators=50, learning_rate=0.1, subsample=0.8),
    )
    gbt_preds["model"] = "shallow_gbt"
    summarize_cv(gbt_preds, "Shallow GBT")

    all_preds = pd.concat([logit_preds, gbt_preds], ignore_index=True)
    all_preds.to_csv(args.output_predictions, index=False)
    print(f"\nWrote {args.output_predictions}", file=sys.stderr)


if __name__ == "__main__":
    main()