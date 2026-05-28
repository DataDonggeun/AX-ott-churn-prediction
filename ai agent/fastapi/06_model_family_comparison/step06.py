"""
Step 06: 모델 패밀리 비교 (Model Family Comparison)

역할: FastAPI
목적: Step 04에서 선정된 우승 계열(boosting/tree/linear) 내에서
      LightGBM·XGBoost·CatBoost·HistGradientBoosting 등을 비교해
      Step 07 Optuna 튜닝 대상 후보를 선정한다.
출력: 모델별 OOF AUC, 후보 선정 결과
캐시: step06_result.json, step06_candidates.json
"""
import sys, importlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import APIRouter
import pandas as pd
import numpy as np
from sklearn.base import clone
from sklearn.ensemble import (
    HistGradientBoostingClassifier, RandomForestClassifier,
    GradientBoostingClassifier, ExtraTreesClassifier,
)
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from config import N_SPLITS, RANDOM_STATE
from cache import is_done, mark_done, save_json, load_json, load_df

router = APIRouter(prefix="/06", tags=["06. Model Family Comparison"])

# step04 우승 모델 → step06에서 돌릴 계열
FAMILY_MAP = {
    "boosting": ["XGBoost", "LightGBM", "CatBoost", "HistGradientBoosting", "GradientBoosting"],
    "tree":     ["RandomForest", "ExtraTrees"],
    "linear":   ["LogisticRegression"],
}

def _model_family(model_name: str) -> str:
    for family, members in FAMILY_MAP.items():
        if model_name in members:
            return family
    return "boosting"  # 기본값

def _winner_families_from_step04() -> dict:
    """step04 결과에서 scope별 우승 모델 계열 반환."""
    cached = load_json("step04_result")
    if not cached or "candidates" not in cached:
        return {}
    families = {}
    for scope, info in cached["candidates"].items():
        winner = info.get("model", "")
        families[scope] = _model_family(winner)
    return families

SCOPES = {
    "overall_without_promotion": lambda df: (df, False),
    "overall_with_promotion":    lambda df: (df, True),
    "promotion_only":            lambda df: (df[df["is_promotion"] == 1].copy(), False),
    "nonpromotion_only":         lambda df: (df[df["is_promotion"] == 0].copy(), False),
}


def _build_models() -> dict:
    """설치 여부에 따라 사용 가능한 모델만 포함"""
    models = {
        "LogisticRegression": Pipeline([
            ("scaler", StandardScaler()),
            ("model", LogisticRegression(max_iter=2000, solver="lbfgs")),
        ]),
        "HistGradientBoosting": HistGradientBoostingClassifier(
            max_iter=100, learning_rate=0.06, max_leaf_nodes=31,
            random_state=RANDOM_STATE,
        ),
        "RandomForest": RandomForestClassifier(
            n_estimators=120, min_samples_leaf=20,
            max_features="sqrt", random_state=RANDOM_STATE, n_jobs=-1,
        ),
        "GradientBoosting": GradientBoostingClassifier(
            n_estimators=100, learning_rate=0.06, max_depth=3,
            random_state=RANDOM_STATE,
        ),
        "ExtraTrees": ExtraTreesClassifier(
            n_estimators=120, min_samples_leaf=10,
            max_features="sqrt", random_state=RANDOM_STATE, n_jobs=-1,
        ),
    }
    # 선택 패키지 (설치된 경우에만 추가)
    optional = [
        ("LightGBM", "lightgbm", "LGBMClassifier",
         {"n_estimators": 120, "learning_rate": 0.05, "num_leaves": 31,
          "subsample": 0.9, "colsample_bytree": 0.9, "random_state": RANDOM_STATE,
          "n_jobs": -1, "verbose": -1}),
        ("XGBoost", "xgboost", "XGBClassifier",
         {"n_estimators": 120, "max_depth": 3, "learning_rate": 0.05,
          "subsample": 0.9, "colsample_bytree": 0.9,
          "eval_metric": "logloss", "n_jobs": -1, "random_state": RANDOM_STATE,
          "tree_method": "hist"}),
        ("CatBoost", "catboost", "CatBoostClassifier",
         {"iterations": 120, "depth": 4, "learning_rate": 0.05,
          "loss_function": "Logloss", "random_seed": RANDOM_STATE,
          "verbose": False, "allow_writing_files": False}),
    ]
    for name, module_name, cls_name, kwargs in optional:
        try:
            mod = importlib.import_module(module_name)
            cls = getattr(mod, cls_name)
            models[name] = cls(**kwargs)
        except Exception:
            pass
    return models


def _cv_auc(df_scope, features, model) -> dict:
    X      = df_scope[features].apply(pd.to_numeric, errors="coerce").fillna(0)
    y      = df_scope["is_repurchase"].astype(int).to_numpy()
    groups = df_scope["USER_KEY"].astype(str).to_numpy()
    sgkf   = StratifiedGroupKFold(n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_STATE)
    oof    = np.full(len(X), np.nan)
    va_aucs = []

    for tr_idx, va_idx in sgkf.split(X, y, groups):
        est  = clone(model)
        X_tr = X.iloc[tr_idx]; X_va = X.iloc[va_idx]
        est.fit(X_tr, y[tr_idx])
        p_va = est.predict_proba(X_va)[:, 1]
        oof[va_idx] = p_va
        if len(np.unique(y[va_idx])) == 2:
            va_aucs.append(roc_auc_score(y[va_idx], p_va))

    valid = ~np.isnan(oof)
    oof_auc = (
        round(float(roc_auc_score(y[valid], oof[valid])), 4)
        if len(np.unique(y[valid])) == 2 else None
    )
    return {
        "oof_auc":        oof_auc,
        "mean_valid_auc": round(float(np.nanmean(va_aucs)), 4),
        "fold_auc_std":   round(float(np.nanstd(va_aucs, ddof=1)), 4),
    }


def run_model_family_comparison(exp_df: pd.DataFrame) -> dict:
    all_models     = _build_models()
    winner_families = _winner_families_from_step04()
    rows = []

    for scope_name, scope_fn in SCOPES.items():
        df_scope, inc_promo = scope_fn(exp_df)
        if len(df_scope) == 0:
            continue
        exclude  = {"USER_KEY", "is_repurchase"}
        if not inc_promo:
            exclude.add("is_promotion")
        features = [c for c in exp_df.columns if c not in exclude and c in df_scope.columns]

        # step04 우승 계열만 실행, 없으면 전체
        family   = winner_families.get(scope_name)
        allowed  = set(FAMILY_MAP.get(family, [])) if family else None
        models   = {k: v for k, v in all_models.items() if allowed is None or k in allowed}

        for model_name, model in models.items():
            try:
                metrics = _cv_auc(df_scope, features, model)
            except Exception as e:
                metrics = {"oof_auc": None, "error": str(e)}
            rows.append({
                "scope": scope_name, "model": model_name,
                "family": family or "all",
                "rows": len(df_scope), "features": len(features),
                **metrics,
            })

    summary_df = pd.DataFrame(rows)

    # scope별 최고 AUC 후보 선정
    candidates = {}
    for scope in SCOPES:
        sub = summary_df[
            (summary_df["scope"] == scope) &
            summary_df["oof_auc"].notna()
        ].sort_values("oof_auc", ascending=False)
        if len(sub):
            best = sub.iloc[0]
            candidates[scope] = {
                "model":   best["model"],
                "oof_auc": best["oof_auc"],
            }

    return {
        "status":           "PASS",
        "winner_families":  winner_families,
        "summary":          rows,
        "candidates":       candidates,
        "note": "step04 우승 계열만 비교. 후보 선정만. 최종 모델 확정 아님.",
    }


@router.post("/model-family-comparison")
def model_family_comparison(force: bool = False):
    """
    Step 06: expanded 데이터셋으로 모델 패밀리 비교.
    LightGBM·XGBoost·CatBoost는 설치된 경우에만 실행.
    """
    if not force and is_done("step06"):
        cached = load_json("step06_result")
        if cached:
            cached["from_cache"] = True
            return cached

    exp_df = load_df("expanded_dataset")
    if exp_df is None:
        return {"status": "FAIL", "reason": "Step 00 먼저 실행 필요"}

    result = run_model_family_comparison(exp_df)

    save_json("step06_result",     result)
    save_json("step06_candidates", result["candidates"])
    mark_done("step06", {"candidates": result["candidates"]})

    result["from_cache"] = False
    return result
