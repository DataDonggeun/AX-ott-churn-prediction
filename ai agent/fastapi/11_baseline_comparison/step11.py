"""
Step 11: 베이스라인 성장 비교 (Baseline Growth Comparison)

역할: FastAPI
목적: conservative(22개) vs expanded(75개) 피처셋으로
      StratifiedGroupKFold 5-fold CV를 돌려 OOF AUC를 비교한다.
      모델: DummyClassifier, LogisticRegression, XGBoost, RandomForest
출력: 피처셋×모델×scope별 OOF AUC 요약
캐시: step11_result.json, step11_oof.csv
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import APIRouter
import pandas as pd
import numpy as np

from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, average_precision_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from config import N_SPLITS, RANDOM_STATE
from cache import is_done, mark_done, save_json, load_json, load_df, save_df

router = APIRouter(prefix="/11", tags=["11. Baseline Comparison"])

MODELS = {
    "DummyPrior": DummyClassifier(strategy="prior"),
    "LogisticRegression": Pipeline([
        ("scaler", StandardScaler()),
        ("model", LogisticRegression(max_iter=1000, solver="lbfgs")),
    ]),
    "XGBoost": XGBClassifier(
        n_estimators=120, max_depth=4, learning_rate=0.06,
        subsample=0.9, colsample_bytree=0.9,
        eval_metric="logloss", tree_method="hist",
        n_jobs=-1, random_state=RANDOM_STATE, verbosity=0,
    ),
    "RandomForest": RandomForestClassifier(
        n_estimators=120, min_samples_leaf=20,
        max_features="sqrt", random_state=RANDOM_STATE, n_jobs=-1,
    ),
}

SCOPES = {
    "overall_without_promotion": lambda df: (df, False),
    "overall_with_promotion":    lambda df: (df, True),
    "promotion_only":            lambda df: (df[df["is_promotion"] == 1].copy(), False),
    "nonpromotion_only":         lambda df: (df[df["is_promotion"] == 0].copy(), False),
}


def _features_for(df: pd.DataFrame, include_promotion: bool) -> list:
    exclude = {"USER_KEY", "is_repurchase"}
    if not include_promotion:
        exclude.add("is_promotion")
    return [c for c in df.columns if c not in exclude]


def _cv_auc(df_scope: pd.DataFrame, features: list, model) -> dict:
    """5-fold CV OOF AUC 계산"""
    from sklearn.base import clone
    X      = df_scope[features].apply(pd.to_numeric, errors="coerce").fillna(0)
    y      = df_scope["is_repurchase"].astype(int).to_numpy()
    groups = df_scope["USER_KEY"].astype(str).to_numpy()

    sgkf   = StratifiedGroupKFold(n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_STATE)
    oof    = np.full(len(X), np.nan)
    tr_aucs, va_aucs = [], []

    for tr_idx, va_idx in sgkf.split(X, y, groups):
        est = clone(model)
        if isinstance(est, DummyClassifier):
            X_tr = np.zeros((len(tr_idx), 1))
            X_va = np.zeros((len(va_idx), 1))
        else:
            X_tr = X.iloc[tr_idx]
            X_va = X.iloc[va_idx]
        est.fit(X_tr, y[tr_idx])
        p_va = est.predict_proba(X_va)[:, 1]
        p_tr = est.predict_proba(X_tr)[:, 1]
        oof[va_idx] = p_va
        if len(np.unique(y[tr_idx])) == 2:
            tr_aucs.append(roc_auc_score(y[tr_idx], p_tr))
            va_aucs.append(roc_auc_score(y[va_idx], p_va))

    valid_mask = ~np.isnan(oof)
    oof_auc    = (
        round(float(roc_auc_score(y[valid_mask], oof[valid_mask])), 4)
        if len(np.unique(y[valid_mask])) == 2 else None
    )
    return {
        "oof_auc":          oof_auc,
        "mean_train_auc":   round(float(np.nanmean(tr_aucs)), 4),
        "mean_valid_auc":   round(float(np.nanmean(va_aucs)), 4),
        "train_valid_gap":  round(float(np.nanmean(tr_aucs) - np.nanmean(va_aucs)), 4),
        "fold_auc_std":     round(float(np.nanstd(va_aucs, ddof=1)), 4),
    }


def run_baseline_comparison(cons_df: pd.DataFrame, exp_df: pd.DataFrame) -> dict:
    rows = []

    datasets = {
        "conservative_safe_22": cons_df,
        "expanded_feature_set": exp_df,
    }

    for fs_name, df in datasets.items():
        # conservative_dataset에 is_promotion이 없을 경우 USER_KEY 기준 merge로 보완
        if "is_promotion" not in df.columns and "is_promotion" in exp_df.columns:
            df = df.merge(
                exp_df[["USER_KEY", "is_promotion"]].drop_duplicates("USER_KEY"),
                on="USER_KEY", how="left",
            )

        for scope_name, scope_fn in SCOPES.items():
            df_scope, inc_promo = scope_fn(df)
            if len(df_scope) == 0:
                continue
            features = _features_for(df_scope, inc_promo)
            if not features:
                continue

            for model_name, model in MODELS.items():
                metrics = _cv_auc(df_scope, features, model)
                rows.append({
                    "feature_set": fs_name,
                    "scope":       scope_name,
                    "model":       model_name,
                    "rows":        len(df_scope),
                    "features":    len(features),
                    **metrics,
                })

    summary_df = pd.DataFrame(rows)

    # conservative vs expanded AUC 비교
    comp = []
    for scope in SCOPES:
        for model in MODELS:
            c = summary_df[
                (summary_df["feature_set"] == "conservative_safe_22") &
                (summary_df["scope"] == scope) &
                (summary_df["model"] == model)
            ]
            e = summary_df[
                (summary_df["feature_set"] == "expanded_feature_set") &
                (summary_df["scope"] == scope) &
                (summary_df["model"] == model)
            ]
            if len(c) and len(e):
                delta = round((e.iloc[0]["oof_auc"] or 0) - (c.iloc[0]["oof_auc"] or 0), 4)
                comp.append({"scope": scope, "model": model, "delta_auc_expanded_minus_conservative": delta})

    return {
        "status":      "PASS",
        "summary":     rows,
        "comparison":  comp,
        "best_expanded_scope": (
            max(comp, key=lambda x: x["delta_auc_expanded_minus_conservative"])
            if comp else None
        ),
        "note": "baseline comparison only. 최종 모델 확정 아님.",
    }


@router.post("/baseline-comparison")
def baseline_comparison(force: bool = False):
    """
    Step 11: conservative vs expanded 베이스라인 AUC 비교.
    4개 scope × 4개 모델 × 2개 피처셋 = 32회 CV 실행.
    처음 실행 시 수 분 소요.
    """
    if not force and is_done("step11"):
        cached = load_json("step11_result")
        if cached:
            cached["from_cache"] = True
            return cached

    cons_df = load_df("conservative_dataset")
    exp_df  = load_df("expanded_dataset")
    if cons_df is None or exp_df is None:
        return {"status": "FAIL", "reason": "Step 06 먼저 실행 필요"}

    result = run_baseline_comparison(cons_df, exp_df)

    save_json("step11_result", result)
    mark_done("step11", {"model_runs": len(result["summary"])})

    result["from_cache"] = False
    return result
