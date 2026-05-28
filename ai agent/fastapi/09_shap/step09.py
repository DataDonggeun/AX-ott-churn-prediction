"""
Step 09: SHAP + Permutation Importance 해석

역할: FastAPI
목적: Step 07 튜닝 모델에 대해 SHAP과 Permutation Importance를 계산해
      피처별 중요도를 두 가지 관점에서 비교한다.
      SHAP은 모델 설명이며 인과가 아님.
출력: SHAP 상위 20개, Permutation Importance 상위 20개, 패밀리별 합계
캐시: step09_shap_global.json
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import APIRouter
import pandas as pd
import numpy as np
from sklearn.base import clone
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import roc_auc_score

from config import RANDOM_STATE, PAYMENT_FEATURES
from cache import is_done, mark_done, save_json, load_json, load_df, load_artifact

router = APIRouter(prefix="/09", tags=["09. SHAP + Permutation Importance"])

FEATURE_FAMILY = {
    "usage_retention_behavior": [
        "watch_time", "watch_session", "retention", "diff_between",
        "only_w", "cold_start", "recency", "gap", "inactive",
        "active_ratio", "watch_per_day", "rewatch", "weekend",
    ],
    "content_preference": [
        "drama", "comedy", "romance", "thriller", "sf", "horror",
        "action", "family", "documentary", "historical", "other",
        "movie", "release", "genre",
    ],
    "membership_context": [
        "is_standard", "is_premium", "is_basic",
        "is_churn_prevented", "is_user_verified",
        "reg_is_weekend", "reg_hour",
        "age_group", "is_female", "is_male",
    ],
    "acquisition_split": ["is_promotion"],
    "payment_proxy":     PAYMENT_FEATURES,
}


def _family_of(feature: str) -> str:
    fn = feature.lower()
    for fam, keywords in FEATURE_FAMILY.items():
        if any(kw in fn for kw in keywords):
            return fam
    return "other"


def run_shap(df_scope: pd.DataFrame, features: list, model) -> dict:
    """SHAP TreeExplainer로 mean absolute SHAP 계산"""
    try:
        import shap
    except ImportError:
        return {"status": "FAIL", "reason": "shap 미설치. pip install shap"}

    X = df_scope[features].apply(pd.to_numeric, errors="coerce").fillna(0)
    y = df_scope["is_repurchase"].astype(int).to_numpy()

    # 최대 5000샘플로 제한 (속도)
    if len(X) > 5000:
        idx = np.random.RandomState(RANDOM_STATE).choice(len(X), 5000, replace=False)
        X_sample = X.iloc[idx]
    else:
        X_sample = X

    fitted = clone(model)
    fitted.fit(X, y)

    explainer = shap.TreeExplainer(fitted)
    vals = explainer.shap_values(X_sample)
    if isinstance(vals, list):
        vals = vals[1] if len(vals) > 1 else vals[0]
    vals = np.asarray(vals)
    if vals.ndim == 3:
        vals = vals[:, :, 1] if vals.shape[2] > 1 else vals[:, :, 0]

    mean_abs = np.abs(vals).mean(axis=0)
    importance = pd.DataFrame({
        "feature":        features,
        "mean_abs_shap":  mean_abs,
        "family":         [_family_of(f) for f in features],
    }).sort_values("mean_abs_shap", ascending=False).reset_index(drop=True)

    top20 = importance.head(20).round(6).to_dict("records")

    # 패밀리별 합계
    family_sum = (
        importance.groupby("family")["mean_abs_shap"]
        .sum().sort_values(ascending=False).round(6).to_dict()
    )

    return {
        "status":       "PASS",
        "top20":        top20,
        "family_sum":   family_sum,
        "sample_size":  int(len(X_sample)),
        "note": "SHAP은 모델 설명이며 인과 주장이 아님.",
    }


def run_permutation_importance(df_scope: pd.DataFrame, features: list, model) -> dict:
    """Permutation Importance 계산 — AUC 기반."""
    X = df_scope[features].apply(pd.to_numeric, errors="coerce").fillna(0)
    y = df_scope["is_repurchase"].astype(int).to_numpy()

    fitted = clone(model)
    fitted.fit(X, y)

    result = permutation_importance(
        fitted, X, y,
        scoring="roc_auc",
        n_repeats=5,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )

    importance = pd.DataFrame({
        "feature":         features,
        "perm_importance": result.importances_mean,
        "perm_std":        result.importances_std,
        "family":          [_family_of(f) for f in features],
    }).sort_values("perm_importance", ascending=False).reset_index(drop=True)

    top20 = importance.head(20).round(6).to_dict("records")
    family_sum = (
        importance.groupby("family")["perm_importance"]
        .sum().sort_values(ascending=False).round(6).to_dict()
    )

    return {
        "status":     "PASS",
        "top20":      top20,
        "family_sum": family_sum,
        "note": "Permutation Importance: 피처 섞었을 때 AUC 감소량. 클수록 중요.",
    }


def run_shap_all_scopes(exp_df: pd.DataFrame) -> dict:
    scopes = {
        "overall_with_promotion":    (exp_df, True),
        "overall_without_promotion": (exp_df, False),
        "promotion_only":   (exp_df[exp_df["is_promotion"] == 1].copy(), False),
        "nonpromotion_only": (exp_df[exp_df["is_promotion"] == 0].copy(), False),
    }

    results = {}
    for scope_name, (df_scope, inc_promo) in scopes.items():
        model = load_artifact(f"tuned_model_{scope_name}")
        if model is None:
            model = HistGradientBoostingClassifier(
                max_iter=200, learning_rate=0.05, random_state=RANDOM_STATE
            )

        exclude  = {"USER_KEY", "is_repurchase"} | (set() if inc_promo else {"is_promotion"})
        features = [c for c in exp_df.columns if c not in exclude and c in df_scope.columns]

        results[scope_name] = {
            "shap":        run_shap(df_scope, features, model),
            "permutation": run_permutation_importance(df_scope, features, model),
        }

    return {"status": "PASS", "by_scope": results}


@router.post("/shap")
def shap_interpretation():
    """Step 09: SHAP + Permutation Importance 피처 중요도 계산. 항상 재실행."""

    exp_df = load_df("expanded_dataset")
    if exp_df is None:
        return {"status": "FAIL", "reason": "Step 00 먼저 실행 필요"}

    result = run_shap_all_scopes(exp_df)

    save_json("step09_shap_global", result)
    mark_done("step09", {"scopes": list(result["by_scope"].keys())})

    result["from_cache"] = False
    return result
