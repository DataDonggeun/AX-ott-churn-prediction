"""
Step 15: 결제 디바이스 민감도 + 스코어링 (Payment Device Sensitivity & Scoring)

역할: FastAPI
목적:
  [full 모드] payment_is_* 4개 피처 제거 AUC 비교 + OOF 예측 저장
  [score_only 모드] 저장된 튜닝 모델을 새 데이터에 바로 적용 → 점수만 생성
                   run-fast에서 사용. 모델 재학습 없음.
출력: OOF 예측 (세그멘테이션용 step15_oof.csv)
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

PRIMARY_SCOPE = "overall_with_promotion"


def _get_model(scope_name: str):
    """Step 14 튜닝 모델 로드. 없으면 기본 HistGradientBoosting."""
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
        p = est.predict_proba(X.iloc[va])[:, 1]
        oof[va] = p
        if len(np.unique(y[va])) == 2:
            va_aucs.append(roc_auc_score(y[va], p))

    valid   = ~np.isnan(oof)
    oof_auc = (
        round(float(roc_auc_score(y[valid], oof[valid])), 4)
        if len(np.unique(y[valid])) == 2 else None
    )
    return oof, oof_auc


# ── [full 모드] sensitivity 분석 + OOF 저장 ───────────────────────────────────

def run_payment_sensitivity(exp_df: pd.DataFrame) -> dict:
    """최초 run-full에서 사용. payment 제거 AUC 비교 + OOF 생성."""
    rows     = []
    oof_rows = []

    for scope_name, scope_fn in SCOPES.items():
        df_scope, inc_promo = scope_fn(exp_df)
        if len(df_scope) == 0:
            continue

        exclude         = {"USER_KEY", "is_repurchase"} | (set() if inc_promo else {"is_promotion"})
        all_features    = [c for c in exp_df.columns if c not in exclude and c in df_scope.columns]
        no_pay_features = [f for f in all_features if f not in PAYMENT_FEATURES]
        model           = _get_model(scope_name)

        _, auc_with    = _cv_oof(df_scope, all_features, model)
        oof_scores, auc_without = _cv_oof(df_scope, no_pay_features, model)

        delta = round((auc_without or 0) - (auc_with or 0), 4)
        rows.append({
            "scope":               scope_name,
            "auc_with_payment":    auc_with,
            "auc_without_payment": auc_without,
            "delta_auc":           delta,
            "recommendation": "제거 권장 (proxy 오염)" if abs(delta) <= 0.005 else "추가 검토 필요",
        })

        tmp = df_scope[["USER_KEY", "is_repurchase"]].copy().reset_index(drop=True)
        tmp["scope"]            = scope_name
        tmp["repurchase_score"] = oof_scores
        tmp["churn_risk"]       = 1 - oof_scores
        oof_rows.append(tmp)

    oof_df = pd.concat(oof_rows, ignore_index=True) if oof_rows else pd.DataFrame()
    if not oof_df.empty:
        save_df("step15_oof", oof_df)

    return {
        "status":    "PASS",
        "mode":      "full_sensitivity",
        "by_scope":  rows,
        "oof_saved": not oof_df.empty,
        "summary": "; ".join(f"{r['scope']}: Δ{r['delta_auc']:+.4f}" for r in rows),
    }


# ── [score_only 모드] 저장된 모델로 새 데이터 점수만 생성 ─────────────────────

def run_scoring_only(exp_df: pd.DataFrame) -> dict:
    """
    run-fast 전용. 모델 재학습 없이 저장된 튜닝 모델로 점수만 계산.
    step14 모델이 없으면 HistGradientBoosting 기본 모델로 fallback.
    """
    oof_rows = []

    for scope_name, scope_fn in SCOPES.items():
        df_scope, inc_promo = scope_fn(exp_df)
        if len(df_scope) == 0:
            continue

        exclude         = {"USER_KEY", "is_repurchase"} | (set() if inc_promo else {"is_promotion"})
        no_pay_features = [
            c for c in exp_df.columns
            if c not in exclude and c in df_scope.columns and c not in PAYMENT_FEATURES
        ]
        if not no_pay_features:
            continue

        X = df_scope[no_pay_features].apply(pd.to_numeric, errors="coerce").fillna(0)
        y = df_scope["is_repurchase"].astype(int).to_numpy()

        saved_model = load_artifact(f"tuned_model_{scope_name}")

        if saved_model is not None:
            # 저장된 모델 그대로 적용 (재학습 없음)
            scores = saved_model.predict_proba(X)[:, 1]
            model_source = "cached_tuned_model"
        else:
            # fallback: 기본 모델로 학습 후 적용
            fallback = HistGradientBoostingClassifier(
                max_iter=200, learning_rate=0.05, max_leaf_nodes=31,
                random_state=RANDOM_STATE,
            )
            fallback.fit(X, y)
            scores = fallback.predict_proba(X)[:, 1]
            model_source = "fallback_default_model"

        tmp = df_scope[["USER_KEY", "is_repurchase"]].copy().reset_index(drop=True)
        tmp["scope"]            = scope_name
        tmp["repurchase_score"] = scores
        tmp["churn_risk"]       = 1 - scores
        tmp["model_source"]     = model_source
        oof_rows.append(tmp)

    oof_df = pd.concat(oof_rows, ignore_index=True) if oof_rows else pd.DataFrame()
    if not oof_df.empty:
        save_df("step15_oof", oof_df)

    return {
        "status":    "PASS",
        "mode":      "score_only",
        "oof_saved": not oof_df.empty,
        "total_scored": int(len(oof_df)),
        "summary": f"저장된 모델로 {len(oof_df):,}행 점수 계산 완료. 재학습 없음.",
    }


# ── 엔드포인트 ─────────────────────────────────────────────────────────────────

@router.post("/payment-sensitivity")
def payment_sensitivity(force: bool = False):
    """Step 15 full: payment_is_* 제거 민감도 분석 + OOF 예측 저장."""
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


@router.post("/scoring")
def scoring(force: bool = False):
    """
    Step 15 score_only: 저장된 모델로 새 데이터 점수만 계산.
    run-fast에서 사용. 모델 재학습 없음.
    """
    exp_df = load_df("expanded_dataset")
    if exp_df is None:
        return {"status": "FAIL", "reason": "Step 06 먼저 실행 필요"}

    result = run_scoring_only(exp_df)
    save_json("step15_scoring_result", result)
    result["from_cache"] = False
    return result
