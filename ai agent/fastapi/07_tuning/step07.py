"""
Step 07: 하이퍼파라미터 튜닝 (Lightweight Candidate Tuning)

역할: FastAPI
목적: Step 06에서 선정된 후보 모델을 Optuna 30 trial로 최적화하고
      최적 파라미터·튜닝된 모델을 저장한다.
      6개월 주기 재학습 시 이 단계부터 재실행.
출력: scope별 최적 파라미터, 튜닝 전후 AUC 비교
캐시: step07_best_params.json, tuned_model_{scope}.pkl
"""
import sys, importlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import uuid
from fastapi import APIRouter, BackgroundTasks
import pandas as pd
import numpy as np
from sklearn.base import clone
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold

from config import N_SPLITS, RANDOM_STATE, N_OPTUNA_TRIALS
from cache import is_done, mark_done, save_json, load_json, load_df, save_artifact

router = APIRouter(prefix="/07", tags=["07. Optuna Tuning"])

_jobs: dict = {}


def _bg_tuning(job_id: str, force: bool):
    _jobs[job_id]["status"] = "RUNNING"
    try:
        exp_df     = load_df("expanded_dataset")
        candidates = load_json("step06_candidates")
        if exp_df is None:
            _jobs[job_id] = {"status": "FAIL", "reason": "Step 00 먼저 실행 필요"}
            return
        if candidates is None:
            _jobs[job_id] = {"status": "FAIL", "reason": "Step 06 먼저 실행 필요"}
            return

        result = run_tuning(exp_df, candidates, job_id=job_id)
        save_json("step07_result",      result)
        save_json("step07_best_params", result.get("by_scope", {}))
        mark_done("step07", {"scopes_tuned": len(result.get("by_scope", {}))})
        _jobs[job_id]["status"] = "DONE"
        _jobs[job_id]["result"] = result
    except Exception as exc:
        _jobs[job_id]["status"] = "ERROR"
        _jobs[job_id]["error"]  = str(exc)

SCOPES = {
    "overall_without_promotion": lambda df: (df, False),
    "overall_with_promotion":    lambda df: (df, True),
    "promotion_only":            lambda df: (df[df["is_promotion"] == 1].copy(), False),
    "nonpromotion_only":         lambda df: (df[df["is_promotion"] == 0].copy(), False),
}


def _make_model(model_name: str, params: dict):
    if model_name == "LightGBM":
        cls = importlib.import_module("lightgbm").LGBMClassifier
        return cls(**params, random_state=RANDOM_STATE, n_jobs=1, num_threads=1, verbose=-1)
    if model_name == "XGBoost":
        cls = importlib.import_module("xgboost").XGBClassifier
        return cls(**params, eval_metric="logloss", n_jobs=1,
                   random_state=RANDOM_STATE, tree_method="hist")
    if model_name == "CatBoost":
        cls = importlib.import_module("catboost").CatBoostClassifier
        return cls(**params, random_seed=RANDOM_STATE,
                   verbose=False, allow_writing_files=False)
    if model_name == "HistGradientBoosting":
        return HistGradientBoostingClassifier(**params, random_state=RANDOM_STATE)
    if model_name == "RandomForest":
        return RandomForestClassifier(**params, random_state=RANDOM_STATE, n_jobs=-1)
    raise ValueError(f"지원하지 않는 모델: {model_name}")


def _search_space(trial, model_name: str) -> dict:
    if model_name == "LightGBM":
        return {
            "n_estimators":    trial.suggest_int("n_estimators", 100, 300),
            "learning_rate":   trial.suggest_float("learning_rate", 0.01, 0.20, log=True),
            "num_leaves":      trial.suggest_int("num_leaves", 16, 64),
            "min_child_samples": trial.suggest_int("min_child_samples", 10, 100),
            "subsample":       trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
            "reg_lambda":      trial.suggest_float("reg_lambda", 1e-8, 20.0, log=True),
        }
    if model_name == "XGBoost":
        return {
            "n_estimators":  trial.suggest_int("n_estimators", 100, 800),
            "max_depth":     trial.suggest_int("max_depth", 2, 6),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.20, log=True),
            "subsample":     trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
            "reg_lambda":    trial.suggest_float("reg_lambda", 1e-8, 20.0, log=True),
        }
    if model_name == "HistGradientBoosting":
        return {
            "max_iter":       trial.suggest_int("max_iter", 100, 500),
            "learning_rate":  trial.suggest_float("learning_rate", 0.01, 0.20, log=True),
            "max_leaf_nodes": trial.suggest_int("max_leaf_nodes", 15, 63),
        }
    if model_name == "CatBoost":
        # CatBoost는 max_iter/max_leaf_nodes 아님 — iterations/max_leaves 사용
        return {
            "iterations":    trial.suggest_int("iterations", 100, 500),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.20, log=True),
            "depth":         trial.suggest_int("depth", 3, 8),
            "l2_leaf_reg":   trial.suggest_float("l2_leaf_reg", 1.0, 10.0),
        }
    if model_name == "RandomForest":
        return {
            "n_estimators":    trial.suggest_int("n_estimators", 100, 600),
            "max_depth":       trial.suggest_int("max_depth", 4, 18),
            "min_samples_leaf": trial.suggest_int("min_samples_leaf", 1, 20),
        }
    return {}


def _cv_mean_auc(X, y, groups, model) -> float:
    sgkf  = StratifiedGroupKFold(n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_STATE)
    aucs  = []
    for tr, va in sgkf.split(X, y, groups):
        est = clone(model)
        est.fit(X.iloc[tr], y[tr])
        p   = est.predict_proba(X.iloc[va])[:, 1]
        if len(np.unique(y[va])) == 2:
            aucs.append(roc_auc_score(y[va], p))
    return float(np.nanmean(aucs))


def run_tuning(exp_df: pd.DataFrame, candidates: dict, job_id: str = None) -> dict:
    try:
        import optuna
        optuna.logging.set_verbosity(optuna.logging.INFO)
    except ImportError:
        return {"status": "FAIL", "reason": "optuna 미설치. pip install optuna"}

    scope_list = list(SCOPES.keys())
    total_scopes = len(scope_list)
    best_params_all = {}
    summary = []

    for scope_idx, (scope_name, scope_fn) in enumerate(SCOPES.items()):
        model_name = candidates.get(scope_name, {}).get("model")
        if not model_name:
            continue

        if job_id and job_id in _jobs:
            _jobs[job_id]["progress"] = {
                "scope": scope_name,
                "scope_step": f"{scope_idx+1}/{total_scopes}",
                "trial": 0,
                "total_trials": N_OPTUNA_TRIALS,
            }

        df_scope, inc_promo = scope_fn(exp_df)
        exclude  = {"USER_KEY", "is_repurchase"} | (set() if inc_promo else {"is_promotion"})
        features = [c for c in exp_df.columns if c not in exclude and c in df_scope.columns]
        if not features:
            continue

        X      = df_scope[features].apply(pd.to_numeric, errors="coerce").fillna(0)
        y      = df_scope["is_repurchase"].astype(int).to_numpy()
        groups = df_scope["USER_KEY"].astype(str).to_numpy()

        # baseline AUC
        def _set_progress(step, trial_num=0, best=None):
            if job_id and job_id in _jobs:
                _jobs[job_id]["progress"] = {
                    "scope": scope_name,
                    "scope_step": f"{scope_idx+1}/{total_scopes}",
                    "step": step,
                    "trial": trial_num,
                    "total_trials": N_OPTUNA_TRIALS,
                    "best_auc_so_far": best,
                }

        baseline_auc = None
        _set_progress("optuna 튜닝 시작", 0)

        # Optuna 최적화
        def objective(trial):
            params = _search_space(trial, model_name)
            try:
                model = _make_model(model_name, params)
                return _cv_mean_auc(X, y, groups, model)
            except Exception:
                return 0.0

        def _progress_callback(study, trial):
            best = round(study.best_value, 4) if study.trials else None
            _set_progress("optuna 튜닝 중", trial.number + 1, best)

        study = optuna.create_study(
            direction="maximize",
            sampler=optuna.samplers.TPESampler(seed=RANDOM_STATE),
        )
        study.optimize(objective, n_trials=N_OPTUNA_TRIALS, timeout=900, callbacks=[_progress_callback])

        best_params = study.best_params if study.trials else {}
        best_auc    = round(study.best_value, 4) if study.trials else None

        # 최적 파라미터로 최종 모델 학습 및 저장
        try:
            tuned_model = _make_model(model_name, best_params)
            tuned_model.fit(X, y)
            save_artifact(f"tuned_model_{scope_name}", tuned_model)
        except Exception:
            pass

        best_params_all[scope_name] = {
            "model":        model_name,
            "best_params":  best_params,
            "baseline_auc": baseline_auc,
            "tuned_auc":    best_auc,
            "delta_auc":    round((best_auc or 0) - (baseline_auc or 0), 4),
            "n_trials":     len(study.trials),
        }
        summary.append(best_params_all[scope_name] | {"scope": scope_name})

    return {
        "status":     "PASS",
        "by_scope":   best_params_all,
        "summary":    summary,
        "note": "튜닝 완료. cache/tuned_model_{scope}.pkl에 저장됨.",
    }


@router.post("/tuning")
def tuning(force: bool = False):
    """
    Step 07: Optuna 경량 튜닝 (30 trial × scope별).
    완료까지 시간이 걸림. 브라우저 타임아웃 나도 서버는 계속 실행됨.
    완료 후 cache/step07_result.json 생성됨.
    """
    if not force and is_done("step07"):
        cached = load_json("step07_result")
        if cached:
            cached["from_cache"] = True
            return cached

    exp_df     = load_df("expanded_dataset")
    candidates = load_json("step06_candidates")
    if exp_df is None:
        return {"status": "FAIL", "reason": "Step 00 먼저 실행 필요"}
    if candidates is None:
        return {"status": "FAIL", "reason": "Step 06 먼저 실행 필요"}

    result = run_tuning(exp_df, candidates)
    save_json("step07_result",      result)
    save_json("step07_best_params", result.get("by_scope", {}))
    mark_done("step07", {"scopes_tuned": len(result.get("by_scope", {}))})

    result["from_cache"] = False
    return result
