"""
Step 05: 스태킹 앙상블 (Stacking Ensemble)

역할: FastAPI
목적: 5개 Base Learner OOF → Meta LR 스태킹으로 단일 모델 성능 개선

흐름:
  /05/stacking/tune      — Optuna 200 trial × 5 모델 병렬 튜닝 → step05_base_params.json
  /05/stacking/run-oof   — 캐시 파라미터로 OOF 병렬 생성 + 전체 학습 pkl 저장
  /05/stacking/train-meta — Meta LR 학습, 채택 여부 판정
  /05/stacking/score     — 최종 점수 → step05_scores.csv 덮어쓰기
  /05/stacking/score-fast — 저장 모델로 새 데이터 빠른 스코어링

캐시:
  step05_base_params.json    — Optuna 튜닝 결과 (tune 실행 시 자동 갱신)
  step05_oof.json            — OOF 메타데이터 (AUC, gap 등)
  step05_oof_arrays.json     — 실제 OOF 배열 (scope × model)
  step05_meta.json           — meta 학습 결과, 채택 여부
  step05_score.json          — 최종 스코어링 결과
  stacking_{model}_{scope}.pkl  — fast mode용 base learner 전체 학습 모델
  meta_model_{scope}.pkl        — scope별 Meta LR
  tuned_model_{scope}.pkl       — SHAP용 CatBoost 전체 학습 모델 (step06 공용)
  meta_col_names_{scope}.json   — fast mode 컬럼 순서 보존용

6개월 재학습 시:
  /05/stacking/tune (force=True) → /05/stacking/run-oof (force=True)
  → /05/stacking/train-meta (force=True) → /05/stacking/score (force=True)
"""
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import APIRouter
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold, StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from config import N_SPLITS, RANDOM_STATE
from cache import (
    is_done, mark_done,
    save_json, load_json,
    load_df, save_df,
    save_artifact, load_artifact,
)

router = APIRouter(prefix="/05", tags=["05. Stacking Ensemble"])

# ── 기본값 (캐시 없을 때 fallback — 최초 실행 또는 tune 전) ──────────────────
# tune 실행 시 step05_base_params.json에 저장되고 이후엔 캐시를 읽음
BASE_PARAMS_DEFAULT = {
    "LR": {
        "penalty": "l1",
        "C": 0.10056716687034523,
        "solver": "liblinear",
        "class_weight": "balanced",
    },
    "XGBoost": {
        "n_estimators": 976,
        "learning_rate": 0.020490715682736027,
        "max_depth": 10,
        "min_child_weight": 9.004257423916812,
        "subsample": 0.5797367503235903,
        "colsample_bytree": 0.5794482187488027,
        "gamma": 9.042315510069226,
        "reg_alpha": 5.4508104089795335,
        "reg_lambda": 4.821382527216652,
        "scale_pos_weight": 2.537860208461067,
    },
    "CatBoost": {
        "iterations": 1045,
        "learning_rate": 0.019122068283565937,
        "depth": 7,
        "l2_leaf_reg": 19.388796600683467,
        "random_strength": 0.2826617100946603,
        "bagging_temperature": 5.463930902267277,
        "border_count": 226,
    },
    "RF": {
        "n_estimators": 408,
        "max_depth": 17,
        "min_samples_split": 6,
        "min_samples_leaf": 10,
        "max_features": None,
        "bootstrap": True,
        "class_weight": "balanced",
    },
    "SVM": {
        "C": 5.0,
        "gamma": "scale",
        "kernel": "rbf",
    },
}

META_GAP_MAX = 0.05
MODEL_NAMES  = list(BASE_PARAMS_DEFAULT.keys())

SCOPES = {
    "overall":           lambda df: (df, True),
    "promotion_only":    lambda df: (df[df["is_promotion"] == 1].copy(), False),
    "nonpromotion_only": lambda df: (df[df["is_promotion"] == 0].copy(), False),
}


# ── 파라미터 로드 (캐시 우선, 없으면 기본값) ─────────────────────────────────

def _load_base_params() -> dict:
    """
    step05_base_params.json (tune 결과) 읽기.
    없으면 BASE_PARAMS_DEFAULT 반환.
    6개월 재학습 시 tune → 자동으로 새 파라미터 반영.
    """
    cached = load_json("step05_base_params")
    if cached:
        return {
            name: info["best_params"]
            for name, info in cached.items()
            if isinstance(info, dict) and "best_params" in info
        }
    return BASE_PARAMS_DEFAULT


# ── 모델 팩토리 ───────────────────────────────────────────────────────────────

def _build_model(name: str, params: dict, n_jobs: int = -1):
    """
    모델명 + 튜닝 파라미터 → sklearn 모델.
    fixed params(random_state, n_jobs 등)는 여기서 추가.
    """
    p = dict(params)

    if name == "LR":
        return Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(
                **p,
                max_iter=3000,
                random_state=RANDOM_STATE,
            )),
        ])

    if name == "XGBoost":
        from xgboost import XGBClassifier
        return XGBClassifier(
            **p,
            objective="binary:logistic",
            eval_metric="logloss",
            random_state=RANDOM_STATE,
            n_jobs=n_jobs,
        )

    if name == "CatBoost":
        from catboost import CatBoostClassifier
        return CatBoostClassifier(
            **p,
            random_seed=RANDOM_STATE,
            verbose=False,
            allow_writing_files=False,
            thread_count=1 if n_jobs == 1 else -1,
        )

    if name == "RF":
        from sklearn.ensemble import RandomForestClassifier
        return RandomForestClassifier(
            **p,
            random_state=RANDOM_STATE,
            n_jobs=n_jobs,
        )

    if name == "SVM":
        from sklearn.svm import SVC
        return Pipeline([
            ("scaler", StandardScaler()),
            ("clf", SVC(**p, probability=True)),
        ])

    raise ValueError(f"지원하지 않는 모델: {name}")


# ── Optuna 탐색 공간 ──────────────────────────────────────────────────────────

def _search_space(trial, name: str) -> dict:
    if name == "LR":
        penalty = trial.suggest_categorical("penalty", ["l1", "l2"])
        solver  = "liblinear" if penalty == "l1" else "lbfgs"
        return {
            "penalty":      penalty,
            "solver":       solver,
            "C":            trial.suggest_float("C", 0.001, 10.0, log=True),
            "class_weight": trial.suggest_categorical("class_weight", ["balanced", None]),
        }

    if name == "XGBoost":
        return {
            "n_estimators":     trial.suggest_int("n_estimators", 200, 1500),
            "learning_rate":    trial.suggest_float("learning_rate", 0.005, 0.1, log=True),
            "max_depth":        trial.suggest_int("max_depth", 4, 12),
            "min_child_weight": trial.suggest_float("min_child_weight", 1.0, 20.0),
            "subsample":        trial.suggest_float("subsample", 0.4, 0.9),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.4, 0.9),
            "gamma":            trial.suggest_float("gamma", 0.0, 15.0),
            "reg_alpha":        trial.suggest_float("reg_alpha", 0.1, 20.0, log=True),
            "reg_lambda":       trial.suggest_float("reg_lambda", 0.1, 20.0, log=True),
            "scale_pos_weight": trial.suggest_float("scale_pos_weight", 1.0, 5.0),
        }

    if name == "CatBoost":
        return {
            "iterations":         trial.suggest_int("iterations", 300, 2000),
            "learning_rate":      trial.suggest_float("learning_rate", 0.005, 0.1, log=True),
            "depth":              trial.suggest_int("depth", 4, 10),
            "l2_leaf_reg":        trial.suggest_float("l2_leaf_reg", 1.0, 50.0),
            "random_strength":    trial.suggest_float("random_strength", 0.0, 2.0),
            "bagging_temperature":trial.suggest_float("bagging_temperature", 0.0, 10.0),
            "border_count":       trial.suggest_int("border_count", 32, 254),
        }

    if name == "RF":
        return {
            "n_estimators":    trial.suggest_int("n_estimators", 100, 800),
            "max_depth":       trial.suggest_int("max_depth", 5, 25),
            "min_samples_split": trial.suggest_int("min_samples_split", 2, 20),
            "min_samples_leaf":  trial.suggest_int("min_samples_leaf", 1, 20),
            "max_features":    trial.suggest_categorical("max_features", ["sqrt", "log2", None]),
            "class_weight":    trial.suggest_categorical("class_weight", ["balanced", None]),
        }

    if name == "SVM":
        kernel = trial.suggest_categorical("kernel", ["rbf", "linear"])
        params = {
            "kernel": kernel,
            "C":      trial.suggest_float("C", 0.1, 20.0, log=True),
        }
        if kernel == "rbf":
            params["gamma"] = trial.suggest_categorical("gamma", ["scale", "auto"])
        return params

    return {}


# ── 엔드포인트 0: Optuna 튜닝 ────────────────────────────────────────────────

def _tune_single_model(
    name: str,
    X: pd.DataFrame,
    y: np.ndarray,
    groups: np.ndarray,
    n_trials: int,
) -> dict:
    """
    단일 모델 Optuna 튜닝. ThreadPoolExecutor에서 병렬 호출.
    SVM은 속도 문제로 최대 5,000행 서브샘플 사용.
    """
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    # SVM: O(n²~n³) → 서브샘플
    if name == "SVM" and len(X) > 5000:
        idx = np.random.RandomState(RANDOM_STATE).choice(len(X), 5000, replace=False)
        X_t, y_t, g_t = X.iloc[idx].reset_index(drop=True), y[idx], groups[idx]
    else:
        X_t, y_t, g_t = X, y, groups

    sgkf = StratifiedGroupKFold(n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_STATE)

    def objective(trial):
        params = _search_space(trial, name)
        try:
            model = _build_model(name, params, n_jobs=1)
            aucs  = []
            for tr, va in sgkf.split(X_t, y_t, g_t):
                est = clone(model)
                est.fit(X_t.iloc[tr], y_t[tr])
                p   = est.predict_proba(X_t.iloc[va])[:, 1]
                if len(np.unique(y_t[va])) == 2:
                    aucs.append(roc_auc_score(y_t[va], p))
            return float(np.nanmean(aucs)) if aucs else 0.0
        except Exception:
            return 0.0

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=RANDOM_STATE),
    )
    study.optimize(objective, n_trials=n_trials, timeout=1800)  # 모델당 최대 30분

    best_params = study.best_params if study.trials else {}
    best_auc    = round(study.best_value, 4) if study.trials else None

    return {
        "model":       name,
        "best_params": best_params,
        "best_auc":    best_auc,
        "n_trials":    len(study.trials),
    }


def run_tune(exp_df: pd.DataFrame, n_trials: int = 200) -> dict:
    """
    5개 Base Learner Optuna 튜닝 병렬 실행 (overall 데이터 기준).
    결과 → step05_base_params.json (run-oof가 이 파일을 읽음).
    """
    exclude  = {"USER_KEY", "is_repurchase"}
    features = [c for c in exp_df.columns if c not in exclude]

    X      = exp_df[features].apply(pd.to_numeric, errors="coerce").fillna(0)
    y      = (1 - exp_df["is_repurchase"].astype(int)).to_numpy()
    groups = exp_df["USER_KEY"].astype(str).to_numpy()

    results: dict = {}

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {
            pool.submit(_tune_single_model, name, X, y, groups, n_trials): name
            for name in MODEL_NAMES
        }
        for fut in as_completed(futures):
            name = futures[fut]
            try:
                res = fut.result()
                results[name] = res
            except Exception as exc:
                results[name] = {"model": name, "best_params": BASE_PARAMS_DEFAULT[name], "error": str(exc)}

    # 캐시 저장 → run-oof가 이 파일을 읽어서 모델 생성
    save_json("step05_base_params", results)

    return {
        "status":   "PASS",
        "by_model": results,
        "n_trials": n_trials,
        "note":     "step05_base_params.json 저장 완료. run-oof 실행하면 이 파라미터로 OOF 생성.",
    }


@router.post("/stacking/tune")
def stacking_tune(force: bool = False, n_trials: int = 200):
    """
    Step 05-0: 5개 Base Learner Optuna 튜닝 (병렬).
    결과를 step05_base_params.json에 저장.
    6개월 재학습 시 force=True로 재실행 → 새 파라미터 자동 반영.
    """
    if not force and is_done("step05_tune"):
        cached = load_json("step05_base_params")
        if cached:
            return {"status": "PASS", "from_cache": True, "by_model": cached}

    exp_df = load_df("expanded_dataset")
    if exp_df is None:
        return {"status": "FAIL", "reason": "Step 00 먼저 실행 필요"}

    result = run_tune(exp_df, n_trials=n_trials)
    mark_done("step05_tune", {"n_trials": n_trials, "models": MODEL_NAMES})

    result["from_cache"] = False
    return result


# ── 엔드포인트 1: OOF 생성 ───────────────────────────────────────────────────

def _run_oof_single(
    name: str,
    params: dict,
    X: pd.DataFrame,
    y: np.ndarray,
    groups: np.ndarray,
) -> dict:
    """단일 모델 5-fold OOF 예측. ThreadPoolExecutor에서 병렬 호출."""
    sgkf    = StratifiedGroupKFold(n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_STATE)
    oof     = np.full(len(X), np.nan)
    tr_aucs, va_aucs = [], []

    for tr, va in sgkf.split(X, y, groups):
        est = _build_model(name, params, n_jobs=1)
        est.fit(X.iloc[tr], y[tr])
        p_va = est.predict_proba(X.iloc[va])[:, 1]
        oof[va] = p_va
        if len(np.unique(y[va])) == 2:
            va_aucs.append(roc_auc_score(y[va], p_va))
        if len(np.unique(y[tr])) == 2:
            p_tr = est.predict_proba(X.iloc[tr])[:, 1]
            tr_aucs.append(roc_auc_score(y[tr], p_tr))

    valid   = ~np.isnan(oof)
    oof_auc = (
        round(float(roc_auc_score(y[valid], oof[valid])), 4)
        if len(np.unique(y[valid])) == 2 else None
    )
    gap = (
        round(float(np.nanmean(tr_aucs) - np.nanmean(va_aucs)), 4)
        if tr_aucs and va_aucs else None
    )

    return {
        "oof":            oof,
        "oof_auc":        oof_auc,
        "gap":            gap,
        "mean_train_auc": round(float(np.nanmean(tr_aucs)), 4) if tr_aucs else None,
        "mean_valid_auc": round(float(np.nanmean(va_aucs)), 4) if va_aucs else None,
    }


def run_oof(exp_df: pd.DataFrame) -> dict:
    """
    5개 Base Learner × 3 scope OOF 병렬 생성.
    파라미터: step05_base_params.json 우선, 없으면 BASE_PARAMS_DEFAULT.
    완료 후 전체 학습 pkl 저장 (fast mode + SHAP용).
    """
    base_params = _load_base_params()  # 캐시 읽기 (tune 결과 or 기본값)

    oof_store: dict = {}
    summary:   dict = {}

    for scope_name, scope_fn in SCOPES.items():
        df_scope, inc_promo = scope_fn(exp_df)
        if len(df_scope) == 0:
            continue

        exclude  = {"USER_KEY", "is_repurchase"} | (set() if inc_promo else {"is_promotion"})
        features = [c for c in exp_df.columns if c not in exclude and c in df_scope.columns]

        X      = df_scope[features].apply(pd.to_numeric, errors="coerce").fillna(0)
        y      = (1 - df_scope["is_repurchase"].astype(int)).to_numpy()
        groups = df_scope["USER_KEY"].astype(str).to_numpy()

        oof_store[scope_name] = {}
        summary[scope_name]   = {}

        # ── 5개 모델 병렬 OOF ─────────────────────────────────────────────────
        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = {
                pool.submit(
                    _run_oof_single,
                    name,
                    base_params.get(name, BASE_PARAMS_DEFAULT[name]),
                    X, y, groups,
                ): name
                for name in MODEL_NAMES
            }
            for fut in as_completed(futures):
                name = futures[fut]
                try:
                    res = fut.result()
                    oof_store[scope_name][name] = res["oof"].tolist()
                    summary[scope_name][name] = {
                        "oof_auc":        res["oof_auc"],
                        "gap":            res["gap"],
                        "mean_train_auc": res["mean_train_auc"],
                        "mean_valid_auc": res["mean_valid_auc"],
                        "overfit":        (res["gap"] or 0) > META_GAP_MAX,
                    }
                except Exception as exc:
                    oof_store[scope_name][name] = None
                    summary[scope_name][name]   = {"error": str(exc)}

        # ── 전체 데이터 학습 + pkl 저장 ───────────────────────────────────────
        # CatBoost: SHAP(step06)이 tuned_model_{scope}.pkl 로드
        try:
            cb_params = base_params.get("CatBoost", BASE_PARAMS_DEFAULT["CatBoost"])
            cb = _build_model("CatBoost", cb_params, n_jobs=-1)
            cb.fit(X, y)
            save_artifact(f"tuned_model_{scope_name}", cb)
            save_artifact(f"stacking_CatBoost_{scope_name}", cb)
        except Exception as exc:
            summary[scope_name].setdefault("CatBoost", {})["full_fit_error"] = str(exc)

        # 나머지 4개 모델 (fast mode 재현용)
        for name in MODEL_NAMES:
            if name == "CatBoost":
                continue
            try:
                p = base_params.get(name, BASE_PARAMS_DEFAULT[name])
                m = _build_model(name, p, n_jobs=-1)
                m.fit(X, y)
                save_artifact(f"stacking_{name}_{scope_name}", m)
            except Exception as exc:
                summary[scope_name].setdefault(name, {})["full_fit_error"] = str(exc)

    save_json("step05_oof_arrays", oof_store)

    return {
        "status":      "PASS",
        "by_scope":    summary,
        "models":      MODEL_NAMES,
        "params_from": "step05_base_params.json" if load_json("step05_base_params") else "BASE_PARAMS_DEFAULT",
        "note":        "tuned_model_{scope}.pkl(SHAP용 CatBoost) 저장 완료.",
    }


@router.post("/stacking/run-oof")
def stacking_run_oof(force: bool = False):
    """
    Step 05-1: 5개 Base Learner OOF 병렬 생성 + 전체 학습 pkl 저장.
    파라미터는 step05_base_params.json 우선 (tune 결과), 없으면 기본값.
    """
    if not force and is_done("step05_oof"):
        cached = load_json("step05_oof")
        if cached:
            cached["from_cache"] = True
            return cached

    exp_df = load_df("expanded_dataset")
    if exp_df is None:
        return {"status": "FAIL", "reason": "Step 00 먼저 실행 필요"}

    result = run_oof(exp_df)
    save_json("step05_oof", result)
    mark_done("step05_oof", {"scopes": list(result["by_scope"].keys())})

    result["from_cache"] = False
    return result


# ── 엔드포인트 2: Meta LR 학습 ──────────────────────────────────────────────

def run_train_meta(exp_df: pd.DataFrame) -> dict:
    """
    scope별 Meta LogisticRegression 학습 + 채택 여부 판정.
    채택 조건: meta_auc > best_base_auc AND meta_gap <= 0.05
    불채택 시 CatBoost 단일 모델로 fallback.
    """
    oof_arrays  = load_json("step05_oof_arrays")
    oof_summary = load_json("step05_oof")
    if not oof_arrays:
        return {"status": "FAIL", "reason": "step05 run-oof 먼저 실행 필요"}

    meta_results: dict = {}

    for scope_name, scope_fn in SCOPES.items():
        df_scope, _ = scope_fn(exp_df)
        if len(df_scope) == 0 or scope_name not in oof_arrays:
            continue

        y = (1 - df_scope["is_repurchase"].astype(int)).to_numpy()

        col_names, oof_cols = [], []
        for name in MODEL_NAMES:
            arr = oof_arrays[scope_name].get(name)
            if arr is not None:
                col_names.append(name)
                oof_cols.append(np.array(arr))

        if not oof_cols:
            meta_results[scope_name] = {"status": "FAIL", "reason": "유효한 OOF 없음"}
            continue

        X_meta = np.column_stack(oof_cols)

        base_aucs = [
            oof_summary["by_scope"][scope_name][n]["oof_auc"]
            for n in col_names
            if oof_summary
            and oof_summary.get("by_scope", {}).get(scope_name, {}).get(n, {}).get("oof_auc") is not None
        ]
        best_base_auc = max(base_aucs) if base_aucs else 0.0

        skf          = StratifiedKFold(n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_STATE)
        meta_oof     = np.full(len(X_meta), np.nan)
        meta_tr_aucs, meta_va_aucs = [], []

        for tr, va in skf.split(X_meta, y):
            clf = LogisticRegression(C=1.0, max_iter=1000, random_state=RANDOM_STATE)
            clf.fit(X_meta[tr], y[tr])
            p_va = clf.predict_proba(X_meta[va])[:, 1]
            meta_oof[va] = p_va
            if len(np.unique(y[va])) == 2:
                meta_va_aucs.append(roc_auc_score(y[va], p_va))
            if len(np.unique(y[tr])) == 2:
                p_tr = clf.predict_proba(X_meta[tr])[:, 1]
                meta_tr_aucs.append(roc_auc_score(y[tr], p_tr))

        valid    = ~np.isnan(meta_oof)
        meta_auc = (
            round(float(roc_auc_score(y[valid], meta_oof[valid])), 4)
            if len(np.unique(y[valid])) == 2 else None
        )
        meta_gap = (
            round(float(np.nanmean(meta_tr_aucs) - np.nanmean(meta_va_aucs)), 4)
            if meta_tr_aucs and meta_va_aucs else None
        )

        adopted = bool(
            meta_auc is not None
            and meta_auc >= best_base_auc
            and (meta_gap if meta_gap is not None else 1.0) <= META_GAP_MAX
        )

        meta_full = LogisticRegression(C=1.0, max_iter=1000, random_state=RANDOM_STATE)
        meta_full.fit(X_meta, y)
        save_artifact(f"meta_model_{scope_name}", meta_full)
        save_json(f"meta_col_names_{scope_name}", col_names)

        meta_results[scope_name] = {
            "meta_auc":      meta_auc,
            "meta_gap":      meta_gap,
            "best_base_auc": round(best_base_auc, 4),
            "col_names":     col_names,
            "adopted":       adopted,
            "fallback":      "CatBoost" if not adopted else None,
            "note": (
                "Meta LR 채택"
                if adopted else
                f"meta_auc({meta_auc}) <= best_base({round(best_base_auc,4)}) 또는 gap({meta_gap}) > {META_GAP_MAX} → CatBoost fallback"
            ),
        }

    return {
        "status":   "PASS",
        "by_scope": meta_results,
        "note":     f"채택 조건: meta_auc > best_base_auc AND meta_gap <= {META_GAP_MAX}",
    }


@router.post("/stacking/train-meta")
def stacking_train_meta(force: bool = False):
    """Step 05-2: Meta LogisticRegression 학습 + 채택 여부 판정."""
    if not force and is_done("step05_meta"):
        cached = load_json("step05_meta")
        if cached:
            cached["from_cache"] = True
            return cached

    exp_df = load_df("expanded_dataset")
    if exp_df is None:
        return {"status": "FAIL", "reason": "Step 00 먼저 실행 필요"}

    if load_json("step05_oof_arrays") is None or load_json("step05_oof") is None:
        return {"status": "FAIL", "reason": "Step 05 run-oof 먼저 실행 필요"}

    result = run_train_meta(exp_df)
    save_json("step05_meta", result)
    mark_done("step05_meta", {"scopes": list(result["by_scope"].keys())})

    result["from_cache"] = False
    return result


# ── 엔드포인트 3: 최종 스코어링 ─────────────────────────────────────────────

def run_score(exp_df: pd.DataFrame) -> dict:
    """OOF 점수로 최종 churn_risk → step05_scores.csv 덮어쓰기."""
    oof_arrays  = load_json("step05_oof_arrays")
    meta_result = load_json("step05_meta")

    if not oof_arrays:
        return {"status": "FAIL", "reason": "step05 run-oof 먼저 실행 필요"}
    if not meta_result:
        return {"status": "FAIL", "reason": "step05 train-meta 먼저 실행 필요"}

    oof_rows, rows = [], []

    for scope_name, scope_fn in SCOPES.items():
        df_scope, _ = scope_fn(exp_df)
        if len(df_scope) == 0 or scope_name not in oof_arrays:
            continue

        y          = (1 - df_scope["is_repurchase"].astype(int)).to_numpy()
        scope_meta = meta_result.get("by_scope", {}).get(scope_name, {})
        adopted    = scope_meta.get("adopted", False)
        col_names  = scope_meta.get("col_names", MODEL_NAMES)

        if adopted:
            oof_cols = [
                np.array(oof_arrays[scope_name][n])
                for n in col_names
                if oof_arrays[scope_name].get(n) is not None
            ]
            meta_clf = load_artifact(f"meta_model_{scope_name}")
            if oof_cols and meta_clf is not None:
                final_oof  = meta_clf.predict_proba(np.column_stack(oof_cols))[:, 1]
                model_used = "meta_stacking"
            else:
                cb_oof     = oof_arrays[scope_name].get("CatBoost")
                final_oof  = np.array(cb_oof) if cb_oof is not None else np.zeros(len(df_scope))
                model_used = "catboost_fallback"
        else:
            cb_oof     = oof_arrays[scope_name].get("CatBoost")
            final_oof  = np.array(cb_oof) if cb_oof is not None else np.zeros(len(df_scope))
            model_used = "catboost_fallback"

        valid   = ~np.isnan(final_oof)
        oof_auc = (
            round(float(roc_auc_score(y[valid], final_oof[valid])), 4)
            if len(np.unique(y[valid])) == 2 else None
        )

        tmp = df_scope[["USER_KEY", "is_repurchase"]].copy().reset_index(drop=True)
        tmp["scope"]            = scope_name
        tmp["churn_risk"]       = final_oof
        tmp["repurchase_score"] = 1 - final_oof
        tmp["model_used"]       = model_used
        oof_rows.append(tmp)
        rows.append({"scope": scope_name, "oof_auc": oof_auc, "adopted": adopted, "model_used": model_used, "rows": len(df_scope)})

    oof_df = pd.concat(oof_rows, ignore_index=True) if oof_rows else pd.DataFrame()
    if not oof_df.empty:
        save_df("step05_scores", oof_df)

    return {
        "status":    "PASS",
        "by_scope":  rows,
        "oof_saved": not oof_df.empty,
        "summary":   " | ".join(f"{r['scope']}: AUC {r['oof_auc']} ({r['model_used']})" for r in rows),
    }


@router.post("/stacking/score")
def stacking_score(force: bool = False):
    """Step 05-3: 최종 점수 생성 → step05_scores.csv 덮어쓰기."""
    if not force and is_done("step05_score"):
        cached = load_json("step05_score")
        if cached:
            cached["from_cache"] = True
            return cached

    exp_df = load_df("expanded_dataset")
    if exp_df is None:
        return {"status": "FAIL", "reason": "Step 00 먼저 실행 필요"}
    if not is_done("step05_meta"):
        return {"status": "FAIL", "reason": "Step 05 train-meta 먼저 실행 필요"}

    result = run_score(exp_df)
    save_json("step05_score", result)
    mark_done("step05_score", {"scopes": len(result["by_scope"])})

    result["from_cache"] = False
    return result


# ── 엔드포인트 4: Fast mode (새 데이터 유입 시) ──────────────────────────────

def run_score_fast(exp_df: pd.DataFrame) -> dict:
    """
    run-fast 전용. 저장된 모델로 새 데이터 직접 predict. OOF·재학습 없음.
    채택 scope: base 모델 predict → meta 모델 통과
    불채택 scope: tuned_model_{scope}.pkl (CatBoost) 직접 사용
    """
    meta_result = load_json("step05_meta")
    oof_rows    = []

    for scope_name, scope_fn in SCOPES.items():
        df_scope, inc_promo = scope_fn(exp_df)
        if len(df_scope) == 0:
            continue

        exclude  = {"USER_KEY", "is_repurchase"} | (set() if inc_promo else {"is_promotion"})
        features = [c for c in exp_df.columns if c not in exclude and c in df_scope.columns]
        X = df_scope[features].apply(pd.to_numeric, errors="coerce").fillna(0)

        scope_meta = (meta_result or {}).get("by_scope", {}).get(scope_name, {})
        adopted    = scope_meta.get("adopted", False)
        col_names  = scope_meta.get("col_names", MODEL_NAMES)

        if adopted:
            base_preds = []
            for name in col_names:
                m = load_artifact(f"stacking_{name}_{scope_name}")
                if m is not None:
                    base_preds.append(m.predict_proba(X)[:, 1])

            meta_clf = load_artifact(f"meta_model_{scope_name}")
            if base_preds and meta_clf is not None:
                scores    = meta_clf.predict_proba(np.column_stack(base_preds))[:, 1]
                model_src = "meta_stacking"
            else:
                cb        = load_artifact(f"tuned_model_{scope_name}")
                scores    = cb.predict_proba(X)[:, 1] if cb is not None else np.zeros(len(X))
                model_src = "catboost_fallback"
        else:
            cb = load_artifact(f"tuned_model_{scope_name}")
            if cb is not None:
                scores    = cb.predict_proba(X)[:, 1]
                model_src = "catboost_cached"
            else:
                scores    = np.zeros(len(X))
                model_src = "no_model_found"

        tmp = df_scope[["USER_KEY", "is_repurchase"]].copy().reset_index(drop=True)
        tmp["scope"]            = scope_name
        tmp["churn_risk"]       = scores
        tmp["repurchase_score"] = 1 - scores
        tmp["model_source"]     = model_src
        oof_rows.append(tmp)

    oof_df = pd.concat(oof_rows, ignore_index=True) if oof_rows else pd.DataFrame()
    if not oof_df.empty:
        save_df("step05_scores", oof_df)

    return {
        "status":       "PASS",
        "mode":         "fast",
        "oof_saved":    not oof_df.empty,
        "total_scored": int(len(oof_df)),
        "summary":      f"저장된 모델로 {len(oof_df):,}행 점수 계산 완료. 재학습 없음.",
    }


@router.post("/stacking/score-fast")
def stacking_score_fast():
    """Step 05 fast: 저장된 모델로 새 데이터 점수만 계산. 재학습 없음."""
    exp_df = load_df("expanded_dataset")
    if exp_df is None:
        return {"status": "FAIL", "reason": "Step 00 먼저 실행 필요"}

    result = run_score_fast(exp_df)
    save_json("step05_scoring_fast_result", result)
    return result


# ── 엔드포인트 5: Test 평가 ──────────────────────────────────────────────────

def run_evaluate_test(exp_df: pd.DataFrame, test_df: pd.DataFrame) -> dict:
    """
    저장된 스태킹 모델로 test 데이터 성능 평가.
    scope별 Base 5개 + 최종 모델(스태킹 or fallback) AUC 계산.
    OOF AUC와 비교해 일반화 성능 확인.
    """
    meta_result = load_json("step05_meta")
    if not meta_result:
        return {"status": "FAIL", "reason": "step05 train-meta 먼저 실행 필요"}

    oof_summary = load_json("step05_oof")
    by_scope = []

    for scope_name, scope_fn in SCOPES.items():
        df_test_scope,  inc_promo = scope_fn(test_df)
        if len(df_test_scope) == 0:
            continue

        exclude  = {"USER_KEY", "is_repurchase"} | (set() if inc_promo else {"is_promotion"})
        features = [c for c in exp_df.columns if c not in exclude and c in df_test_scope.columns]

        X_test = df_test_scope[features].apply(pd.to_numeric, errors="coerce").fillna(0)
        y_test = (1 - df_test_scope["is_repurchase"].astype(int)).to_numpy()

        scope_meta = meta_result.get("by_scope", {}).get(scope_name, {})
        adopted    = scope_meta.get("adopted", False)
        col_names  = scope_meta.get("col_names", MODEL_NAMES)

        # ── Base 5개 모델 test 예측 ────────────────────────────────────────────
        base_preds  = {}
        base_results = []
        for name in MODEL_NAMES:
            m = load_artifact(f"stacking_{name}_{scope_name}")
            if m is None:
                continue
            try:
                pred = m.predict_proba(X_test)[:, 1]
                base_preds[name] = pred
                auc = (
                    round(float(roc_auc_score(y_test, pred)), 4)
                    if len(np.unique(y_test)) == 2 else None
                )
                oof_auc = (oof_summary or {}).get("by_scope", {}).get(scope_name, {}).get(name, {}).get("oof_auc")
                delta = round(auc - oof_auc, 4) if (auc is not None and oof_auc is not None) else None
                base_results.append({"model": name, "test_auc": auc, "oof_auc": oof_auc, "delta": delta})
            except Exception as exc:
                base_results.append({"model": name, "error": str(exc)})

        # ── 최종 모델 (스태킹 or fallback) ────────────────────────────────────
        if adopted and all(n in base_preds for n in col_names):
            meta_clf = load_artifact(f"meta_model_{scope_name}")
            if meta_clf is not None:
                stacking_pred = meta_clf.predict_proba(
                    np.column_stack([base_preds[n] for n in col_names])
                )[:, 1]
                model_used = "meta_stacking"
            else:
                stacking_pred = base_preds.get("CatBoost")
                model_used    = "catboost_fallback"
        else:
            stacking_pred = base_preds.get("CatBoost")
            model_used    = "catboost_fallback"

        final_test_auc = None
        if stacking_pred is not None:
            valid = ~np.isnan(stacking_pred)
            if len(np.unique(y_test[valid])) == 2:
                final_test_auc = round(float(roc_auc_score(y_test[valid], stacking_pred[valid])), 4)

        oof_auc_final = scope_meta.get("meta_auc") if adopted else scope_meta.get("best_base_auc")
        delta_final   = round(final_test_auc - oof_auc_final, 4) if (final_test_auc is not None and oof_auc_final is not None) else None

        by_scope.append({
            "scope":          scope_name,
            "final_model":    model_used,
            "test_auc":       final_test_auc,
            "oof_auc":        oof_auc_final,
            "delta":          delta_final,
            "test_rows":      int(len(df_test_scope)),
            "base_models":    base_results,
        })

    return {
        "status":   "PASS",
        "by_scope": by_scope,
        "summary":  " | ".join(
            f"{r['scope']}: test={r['test_auc']} (Δ{r['delta']:+.4f})"
            for r in by_scope if r.get("test_auc") is not None and r.get("delta") is not None
        ),
        "note": "test set 평가 완료. force=True 없이는 재실행 안 됨.",
    }


@router.post("/stacking/evaluate-test")
def stacking_evaluate_test(force: bool = False):
    """
    Step 05 test: 저장된 스태킹 모델로 test 데이터 최종 성능 평가.
    OOF AUC 대비 test AUC 비교 → 일반화 성능 확인.
    캐시 있으면 재실행 안 함 (data leakage 방지).
    """
    if not force and is_done("step05_test"):
        cached = load_json("test_score")
        if cached:
            cached["from_cache"] = True
            return cached

    exp_df  = load_df("expanded_dataset")
    test_df = load_df("test_expanded")

    if exp_df is None:
        return {"status": "FAIL", "reason": "Step 00 먼저 실행 필요"}
    if test_df is None:
        return {"status": "FAIL", "reason": "test_expanded.csv 없음 — step00 test 파라미터로 먼저 실행 필요"}
    if not is_done("step05_score"):
        return {"status": "FAIL", "reason": "Step 05/score 먼저 실행 필요"}

    result = run_evaluate_test(exp_df, test_df)
    save_json("test_score", result)
    mark_done("step05_test", {
        "scopes": len(result["by_scope"]),
        "summary": result.get("summary"),
    })

    result["from_cache"] = False
    return result
