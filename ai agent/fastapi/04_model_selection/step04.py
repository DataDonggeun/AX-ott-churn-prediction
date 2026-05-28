"""
Step 04: 모델 계열 선정 (Model Selection)

역할: FastAPI
목적: Membership_v5(expanded_dataset) 기준으로 LogisticRegression, XGBoost, RandomForest
      3개 모델 AUC를 비교해 scope별 우승 모델 계열을 선정한다.
      선정 결과는 step06(모델 계열 비교)에 전달된다.
출력: 모델별 OOF AUC, scope별 우승 모델 계열
캐시: step04_result.json
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import APIRouter
import pandas as pd
import numpy as np

from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, average_precision_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from config import N_SPLITS, RANDOM_STATE
from cache import is_done, mark_done, save_json, load_json, load_df, save_df

router = APIRouter(prefix="/04", tags=["04. Model Selection"])

MODELS = {
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
        est  = clone(model)
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


def run_baseline_comparison(exp_df: pd.DataFrame) -> dict:
    """Membership_v5 기반 3개 모델 AUC 비교 → 우승 모델 계열 선정."""
    rows = []

    for scope_name, scope_fn in SCOPES.items():
        df_scope, inc_promo = scope_fn(exp_df)
        if len(df_scope) == 0:
            continue
        features = _features_for(df_scope, inc_promo)
        if not features:
            continue

        for model_name, model in MODELS.items():
            metrics = _cv_auc(df_scope, features, model)
            rows.append({
                "scope":    scope_name,
                "model":    model_name,
                "rows":     len(df_scope),
                "features": len(features),
                **metrics,
            })

    summary_df = pd.DataFrame(rows)

    # scope별 우승 모델 선정
    candidates = {}
    for scope in SCOPES:
        sub = summary_df[
            (summary_df["scope"] == scope) &
            summary_df["oof_auc"].notna()
        ].sort_values("oof_auc", ascending=False)
        if len(sub):
            best = sub.iloc[0]
            candidates[scope] = {"model": best["model"], "oof_auc": best["oof_auc"]}

    return {
        "status":     "PASS",
        "summary":    rows,
        "candidates": candidates,
        "note": "Membership_v5 기반 3개 모델 계열 선정. 우승 계열 → step06 전달.",
    }


@router.post("/baseline-comparison")
def baseline_comparison(force: bool = False):
    """Step 04: 3개 모델 AUC 비교로 우승 모델 계열 선정 (LogisticRegression / XGBoost / RandomForest)."""
    if not force and is_done("step04"):
        cached = load_json("step04_result")
        if cached:
            cached["from_cache"] = True
            return cached

    exp_df = load_df("expanded_dataset")
    if exp_df is None:
        return {"status": "FAIL", "reason": "Step 00 먼저 실행 필요"}

    result = run_baseline_comparison(exp_df)

    save_json("step04_result", result)
    mark_done("step04", {"candidates": result["candidates"]})

    result["from_cache"] = False
    return result
