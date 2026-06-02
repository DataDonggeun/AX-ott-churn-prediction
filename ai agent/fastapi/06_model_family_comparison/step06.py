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
    ExtraTreesClassifier,
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
    "boosting": ["XGBoost", "LightGBM", "CatBoost", "HistGradientBoosting"],
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
    "overall":           lambda df: (df, True),
    "promotion_only":    lambda df: (df[df["is_promotion"] == 1].copy(), False),
    "nonpromotion_only": lambda df: (df[df["is_promotion"] == 0].copy(), False),
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
    y      = (1 - df_scope["is_repurchase"].astype(int)).to_numpy()
    groups = df_scope["USER_KEY"].astype(str).to_numpy()
    sgkf   = StratifiedGroupKFold(n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_STATE)
    oof     = np.full(len(X), np.nan)
    tr_aucs, va_aucs = [], []

    for tr_idx, va_idx in sgkf.split(X, y, groups):
        est  = clone(model)
        X_tr = X.iloc[tr_idx]; X_va = X.iloc[va_idx]
        est.fit(X_tr, y[tr_idx])
        p_va = est.predict_proba(X_va)[:, 1]
        p_tr = est.predict_proba(X_tr)[:, 1]
        oof[va_idx] = p_va
        if len(np.unique(y[va_idx])) == 2:
            va_aucs.append(roc_auc_score(y[va_idx], p_va))
        if len(np.unique(y[tr_idx])) == 2:
            tr_aucs.append(roc_auc_score(y[tr_idx], p_tr))

    valid = ~np.isnan(oof)
    oof_auc = (
        round(float(roc_auc_score(y[valid], oof[valid])), 4)
        if len(np.unique(y[valid])) == 2 else None
    )
    return {
        "oof_auc":         oof_auc,
        "mean_train_auc":  round(float(np.nanmean(tr_aucs)), 4),
        "mean_valid_auc":  round(float(np.nanmean(va_aucs)), 4),
        "train_valid_gap": round(float(np.nanmean(tr_aucs) - np.nanmean(va_aucs)), 4),
        "fold_auc_std":    round(float(np.nanstd(va_aucs, ddof=1)), 4),
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

    # ── 1단계: scope별 gap 필터 후 AUC 1등 선발 ─────────────────────────────
    scope_winners = {}   # scope → {model, oof_auc, gap, threshold, all_overfit}
    for scope in SCOPES:
        sub = summary_df[
            (summary_df["scope"] == scope) &
            summary_df["oof_auc"].notna()
        ].copy()
        if sub.empty:
            continue

        selected = None
        gap_used = None
        all_overfit = False

        for threshold in [0.03, 0.04, 0.05]:
            filtered = sub[sub["train_valid_gap"] <= threshold].sort_values("oof_auc", ascending=False)
            if not filtered.empty:
                selected = filtered.iloc[0]
                gap_used = threshold
                break
        else:
            all_overfit = True
            selected = sub.sort_values("oof_auc", ascending=False).iloc[0]

        scope_winners[scope] = {
            "model":       selected["model"],
            "oof_auc":     selected["oof_auc"],
            "gap":         selected["train_valid_gap"],
            "threshold":   gap_used,
            "all_overfit": all_overfit,
        }

    # ── 2단계: 가장 많이 1등한 모델 → 통합 모델 결정 ────────────────────────
    from collections import Counter

    def _model_passes_all_scopes(model_name: str) -> bool:
        """모델이 모든 scope에서 gap 기준을 통과하는지 확인"""
        for scope, winner in scope_winners.items():
            threshold = winner["threshold"] or 0.05
            row = summary_df[
                (summary_df["scope"] == scope) &
                (summary_df["model"] == model_name)
            ]
            if row.empty or row.iloc[0]["train_valid_gap"] > threshold:
                return False
        return True

    win_counts = Counter(v["model"] for v in scope_winners.values())
    max_wins   = max(win_counts.values())
    top_models = [m for m, c in win_counts.items() if c == max_wins]

    tie_info = None
    if len(top_models) == 1:
        unified_model = top_models[0]
    else:
        # 타이: 과적합 없는 모델 우선, 그 중 avg_gap↑ avg_auc↓ 기준
        no_overfit = [m for m in top_models if _model_passes_all_scopes(m)]
        candidates_pool = no_overfit if no_overfit else top_models

        model_stats = (
            summary_df[summary_df["model"].isin(candidates_pool)]
            .groupby("model")
            .agg(avg_auc=("oof_auc", "mean"), avg_gap=("train_valid_gap", "mean"))
            .reset_index()
            .sort_values(["avg_gap", "avg_auc"], ascending=[True, False])
        )
        unified_model = model_stats.iloc[0]["model"]
        tie_info = {
            "tied_models":       top_models,
            "no_overfit_models": no_overfit,
            "ranking":           model_stats.to_dict("records"),
        }

    # ── 3단계: 통합 모델 기준으로 candidates 확정 ────────────────────────────
    # 통합 모델이 해당 scope에서 과적합이면 scope 1등 모델로 따로 돌림
    candidates = {}
    for scope, winner in scope_winners.items():
        threshold = winner["threshold"] or 0.05
        sub = summary_df[
            (summary_df["scope"] == scope) &
            (summary_df["model"] == unified_model)
        ]

        if sub.empty:
            candidates[scope] = {
                **winner,
                "note": f"통합모델({unified_model}) 데이터 없음 → scope 1등 사용",
            }
            continue

        unified_row = sub.iloc[0]
        gap_ok = unified_row["train_valid_gap"] <= threshold

        if gap_ok:
            # 통합 모델 과적합 없음 → 통합 모델 사용
            candidates[scope] = {
                "model":            unified_model,
                "oof_auc":          unified_row["oof_auc"],
                "train_valid_gap":  unified_row["train_valid_gap"],
                "gap_threshold":    threshold,
                "overfit_warning":  False,
                "scope_winner":     winner["model"],
                "scope_winner_auc": winner["oof_auc"],
                "note":             "통합모델 사용",
            }
        else:
            # 통합 모델 과적합 → scope 1등 모델 따로 사용
            candidates[scope] = {
                "model":            winner["model"],
                "oof_auc":          winner["oof_auc"],
                "train_valid_gap":  winner["gap"],
                "gap_threshold":    threshold,
                "overfit_warning":  winner["all_overfit"],
                "unified_model":    unified_model,
                "note":             f"통합모델({unified_model}) gap={unified_row['train_valid_gap']:.4f} 과적합 → scope 1등 사용",
            }

    return {
        "status":          "PASS",
        "winner_families": winner_families,
        "unified_model":   unified_model,
        "win_counts":      dict(win_counts),
        "tie_info":        tie_info,
        "summary":         rows,
        "candidates":      candidates,
        "note": "scope별 gap 필터 후 최다 우승 모델을 통합 모델로 결정. 타이 시 avg_gap↑ avg_auc↓ 기준.",
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
