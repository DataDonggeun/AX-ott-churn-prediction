"""
Step 08: 스코어링 (Scoring)

역할: FastAPI
목적:
  [full 모드] Step 07 튜닝 모델로 OOF 예측 점수 생성 → Step 10 세그멘테이션 입력
  [fast 모드] 저장된 튜닝 모델을 새 데이터에 바로 적용. 재학습 없음.
출력: OOF 예측 (step08_oof.csv)
캐시: step08_result.json, step08_oof.csv
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

from config import N_SPLITS, RANDOM_STATE
from cache import mark_done, save_json, load_df, save_df, load_artifact

router = APIRouter(prefix="/08", tags=["08. Scoring"])

SCOPES = {
    "overall_without_promotion": lambda df: (df, False),
    "overall_with_promotion":    lambda df: (df, True),
    "promotion_only":            lambda df: (df[df["is_promotion"] == 1].copy(), False),
    "nonpromotion_only":         lambda df: (df[df["is_promotion"] == 0].copy(), False),
}


def _get_model(scope_name: str):
    """Step 07 튜닝 모델 로드. 없으면 기본 HistGradientBoosting."""
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


# ── [full 모드] OOF 예측 생성 ──────────────────────────────────────────────────

def run_scoring(exp_df: pd.DataFrame) -> dict:
    """run-full 전용. Step 07 튜닝 모델 구조로 OOF 예측 점수 생성."""
    rows     = []
    oof_rows = []

    for scope_name, scope_fn in SCOPES.items():
        df_scope, inc_promo = scope_fn(exp_df)
        if len(df_scope) == 0:
            continue

        exclude  = {"USER_KEY", "is_repurchase"} | (set() if inc_promo else {"is_promotion"})
        features = [c for c in exp_df.columns if c not in exclude and c in df_scope.columns]
        model    = _get_model(scope_name)

        oof_scores, oof_auc = _cv_oof(df_scope, features, model)

        rows.append({"scope": scope_name, "oof_auc": oof_auc, "rows": len(df_scope)})

        tmp = df_scope[["USER_KEY", "is_repurchase"]].copy().reset_index(drop=True)
        tmp["scope"]            = scope_name
        tmp["repurchase_score"] = oof_scores
        tmp["churn_risk"]       = 1 - oof_scores
        oof_rows.append(tmp)

    oof_df = pd.concat(oof_rows, ignore_index=True) if oof_rows else pd.DataFrame()
    if not oof_df.empty:
        save_df("step08_oof", oof_df)

    return {
        "status":    "PASS",
        "mode":      "full",
        "by_scope":  rows,
        "oof_saved": not oof_df.empty,
        "summary": " | ".join(
            f"{r['scope']}: AUC {r['oof_auc']}" for r in rows if r["oof_auc"]
        ),
    }


# ── [fast 모드] 저장 모델로 점수만 계산 ────────────────────────────────────────

def run_scoring_fast(exp_df: pd.DataFrame) -> dict:
    """run-fast 전용. 저장된 모델로 점수만 계산. 재학습 없음."""
    oof_rows = []

    for scope_name, scope_fn in SCOPES.items():
        df_scope, inc_promo = scope_fn(exp_df)
        if len(df_scope) == 0:
            continue

        exclude  = {"USER_KEY", "is_repurchase"} | (set() if inc_promo else {"is_promotion"})
        features = [c for c in exp_df.columns if c not in exclude and c in df_scope.columns]
        if not features:
            continue

        X           = df_scope[features].apply(pd.to_numeric, errors="coerce").fillna(0)
        y           = df_scope["is_repurchase"].astype(int).to_numpy()
        saved_model = load_artifact(f"tuned_model_{scope_name}")

        if saved_model is not None:
            scores       = saved_model.predict_proba(X)[:, 1]
            model_source = "cached_tuned_model"
        else:
            fallback = HistGradientBoostingClassifier(
                max_iter=200, learning_rate=0.05, max_leaf_nodes=31,
                random_state=RANDOM_STATE,
            )
            fallback.fit(X, y)
            scores       = fallback.predict_proba(X)[:, 1]
            model_source = "fallback_default_model"

        tmp = df_scope[["USER_KEY", "is_repurchase"]].copy().reset_index(drop=True)
        tmp["scope"]            = scope_name
        tmp["repurchase_score"] = scores
        tmp["churn_risk"]       = 1 - scores
        tmp["model_source"]     = model_source
        oof_rows.append(tmp)

    oof_df = pd.concat(oof_rows, ignore_index=True) if oof_rows else pd.DataFrame()
    if not oof_df.empty:
        save_df("step08_oof", oof_df)

    return {
        "status":       "PASS",
        "mode":         "fast",
        "oof_saved":    not oof_df.empty,
        "total_scored": int(len(oof_df)),
        "summary":      f"저장된 모델로 {len(oof_df):,}행 점수 계산 완료. 재학습 없음.",
    }


# ── 엔드포인트 ─────────────────────────────────────────────────────────────────

@router.post("/scoring")
def scoring():
    """Step 08 full: OOF 예측 점수 생성. 항상 재실행."""
    exp_df = load_df("expanded_dataset")
    if exp_df is None:
        return {"status": "FAIL", "reason": "Step 00 먼저 실행 필요"}

    result = run_scoring(exp_df)
    save_json("step08_result", result)
    mark_done("step08", {"scopes": len(result["by_scope"])})
    result["from_cache"] = False
    return result


@router.post("/scoring-fast")
def scoring_fast():
    """Step 08 fast: 저장된 모델로 새 데이터 점수만 계산. 재학습 없음."""
    exp_df = load_df("expanded_dataset")
    if exp_df is None:
        return {"status": "FAIL", "reason": "Step 00 먼저 실행 필요"}

    result = run_scoring_fast(exp_df)
    save_json("step08_scoring_result", result)
    result["from_cache"] = False
    return result
