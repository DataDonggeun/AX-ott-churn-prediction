"""
Step 15: 결제 디바이스 민감도 (Payment Device Sensitivity)

역할: FastAPI
목적: payment_is_mobile·pc·android·ios 4개 피처를 제거했을 때
      AUC 변화를 계산해 제거 여부 판단 근거를 만든다.
      결제기기는 시청기기가 아니라 proxy이므로 제거 권장.
출력: payment 포함/제거 AUC 차이, OOF 예측 (세그멘테이션용)
캐시: step15_result.json, step15_oof.csv
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import APIRouter
import pandas as pd
import numpy as np
from sklearn.base import clone
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.ensemble import HistGradientBoostingClassifier

from config import N_SPLITS, RANDOM_STATE, PAYMENT_FEATURES
from cache import is_done, mark_done, save_json, load_json, load_df, save_df, load_artifact

router = APIRouter(prefix="/15", tags=["15. Payment Device Sensitivity"])

SCOPES = {
    "overall_without_promotion": lambda df: (df, False),
    "overall_with_promotion":    lambda df: (df, True),
    "promotion_only":            lambda df: (df[df["is_promotion"] == 1].copy(), False),
    "nonpromotion_only":         lambda df: (df[df["is_promotion"] == 0].copy(), False),
}


def _get_model(scope_name: str):
    """Step 14 튜닝 모델 사용, 없으면 기본 HistGradientBoosting"""
    m = load_artifact(f"tuned_model_{scope_name}")
    if m is not None:
        return clone(m)
    return HistGradientBoostingClassifier(
        max_iter=200, learning_rate=0.05, max_leaf_nodes=31,
        random_state=RANDOM_STATE,
    )


def _cv_oof(df_scope, features, model):
    X      = df_scope[features].apply(pd.to_numeric, errors="coerce").fillna(0)
    y      = df_scope["is_repurchase"].astype(int).to_numpy()
    groups = df_scope["USER_KEY"].astype(str).to_numpy()
    sgkf   = StratifiedGroupKFold(n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_STATE)
    oof    = np.full(len(X), np.nan)
    va_aucs = []

    for tr, va in sgkf.split(X, y, groups):
        est = clone(model)
        est.fit(X.iloc[tr], y[tr])
        p   = est.predict_proba(X.iloc[va])[:, 1]
        oof[va] = p
        if len(np.unique(y[va])) == 2:
            va_aucs.append(roc_auc_score(y[va], p))

    valid   = ~np.isnan(oof)
    oof_auc = (
        round(float(roc_auc_score(y[valid], oof[valid])), 4)
        if len(np.unique(y[valid])) == 2 else None
    )
    return oof, oof_auc


def run_payment_sensitivity(exp_df: pd.DataFrame) -> dict:
    rows     = []
    oof_rows = []

    for scope_name, scope_fn in SCOPES.items():
        df_scope, inc_promo = scope_fn(exp_df)
        if len(df_scope) == 0:
            continue

        exclude = {"USER_KEY", "is_repurchase"} | (set() if inc_promo else {"is_promotion"})
        all_features     = [c for c in exp_df.columns if c not in exclude and c in df_scope.columns]
        no_pay_features  = [f for f in all_features if f not in PAYMENT_FEATURES]

        model = _get_model(scope_name)

        # payment 포함 AUC
        _, auc_with = _cv_oof(df_scope, all_features, model)

        # payment 제거 AUC + OOF 저장 (세그멘테이션용)
        oof_scores, auc_without = _cv_oof(df_scope, no_pay_features, model)

        delta = round((auc_without or 0) - (auc_with or 0), 4)

        rows.append({
            "scope":          scope_name,
            "auc_with_payment":    auc_with,
            "auc_without_payment": auc_without,
            "delta_auc":      delta,
            "payment_count":  len(PAYMENT_FEATURES),
            "features_with":  len(all_features),
            "features_without": len(no_pay_features),
            "recommendation": "제거 권장 (proxy 오염 위험)" if abs(delta) <= 0.005 else "추가 검토 필요",
        })

        # OOF 예측 저장 (17단계 세그멘테이션 입력)
        tmp = df_scope[["USER_KEY", "is_repurchase"]].copy().reset_index(drop=True)
        tmp["scope"]           = scope_name
        tmp["repurchase_score"] = oof_scores
        tmp["churn_risk"]      = 1 - oof_scores
        oof_rows.append(tmp)

    oof_df = pd.concat(oof_rows, ignore_index=True) if oof_rows else pd.DataFrame()
    if not oof_df.empty:
        save_df("step15_oof", oof_df)

    return {
        "status":  "PASS",
        "by_scope": rows,
        "oof_saved": not oof_df.empty,
        "summary": "; ".join(
            f"{r['scope']}: Δ{r['delta_auc']:+.4f}" for r in rows
        ),
    }


@router.post("/payment-sensitivity")
def payment_sensitivity(force: bool = False):
    """Step 15: payment_is_* 제거 민감도 분석 + OOF 예측 저장."""
    if not force and is_done("step15"):
        cached = load_json("step15_result")
        if cached:
            cached["from_cache"] = True
            return cached

    exp_df = load_df("expanded_dataset")
    if exp_df is None:
        return {"status": "FAIL", "reason": "Step 06 먼저 실행 필요"}

    result = run_payment_sensitivity(exp_df)

    save_json("step15_result", result)
    mark_done("step15", {"scopes": len(result["by_scope"])})

    result["from_cache"] = False
    return result
