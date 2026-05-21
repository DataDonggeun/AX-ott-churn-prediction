import json

nb = {
 "nbformat": 4, "nbformat_minor": 5,
 "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
               "language_info": {"name": "python", "version": "3.10.0"}},
 "cells": []
}

def md(src, cid):
    return {"cell_type":"markdown","id":cid,"metadata":{},"source":[src]}
def code(src, cid):
    return {"cell_type":"code","id":cid,"metadata":{},"source":[src],"outputs":[],"execution_count":None}

cells = []
cells.append(md("# OTT 이탈 예측 — final_merged 기본 vs v2 파생변수 비교\n\nCatBoost Optuna 100 trials | 기본 final_merged vs 파생변수 추가본", "md-title"))

# 셀 1: import
cells.append(code(
'import pandas as pd\n'
'import numpy as np\n'
'import sqlite3\n'
'import warnings; warnings.filterwarnings("ignore")\n'
'\n'
'from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score\n'
'from sklearn.preprocessing import LabelEncoder\n'
'from sklearn.metrics import roc_auc_score, average_precision_score, accuracy_score, f1_score\n'
'from catboost import CatBoostClassifier\n'
'import optuna\n'
'optuna.logging.set_verbosity(optuna.logging.WARNING)\n'
'\n'
'print("라이브러리 로드 완료")',
"cell-import"))

# 셀 2: final_merged 구성
cells.append(code(
'# integrated_analysis.db에서 membership + user_mapping 조인\n'
'conn = sqlite3.connect("../db/integrated_analysis.db")\n'
'mem = pd.read_sql("SELECT * FROM membership", conn)\n'
'um  = pd.read_sql("SELECT * FROM user_mapping", conn)\n'
'conn.close()\n'
'\n'
'# repurchase 타겟 변환\n'
'mem["repurchase"] = (mem["repurchase"] == "O").astype(int)\n'
'mem["promotion_yn"]       = (mem["promotion_yn"] == "O").astype(int)\n'
'mem["is_churn_prevented"] = (mem["is_churn_prevented"] == "O").astype(int)\n'
'mem["is_user_verified"]   = (mem["is_user_verified"] == "Y").astype(int)\n'
'mem["gender"] = mem["gender"].map({"F":0,"M":1}).fillna(0).astype(int)\n'
'\n'
'# membership + user_mapping 조인 (uid = user_no)\n'
'df = mem.merge(um.rename(columns={"uid":"user_no"}), on="user_no", how="left")\n'
'\n'
'# 불필요 컬럼 제거\n'
'drop_cols = ["user_no","product_cd","reg_date","end_date","USER_ID","repurchase_label","registerday"]\n'
'df_base = df.drop(columns=[c for c in drop_cols if c in df.columns])\n'
'\n'
'print(f"final_merged shape: {df.shape}")\n'
'print(f"기본 피처 수 (타겟 제외): {df_base.shape[1]-1}")\n'
'print(f"재결제율: {df_base.repurchase.mean():.3f}")',
"cell-load"))

# 셀 3: v2 파생변수 추가
cells.append(code(
'df_v2 = df.copy()\n'
'\n'
'# duration_days\n'
'df_v2["reg_date_dt"] = pd.to_datetime(df["reg_date"])\n'
'df_v2["end_date_dt"] = pd.to_datetime(df["end_date"])\n'
'df_v2["duration_days"] = (df_v2["end_date_dt"] - df_v2["reg_date_dt"]).dt.days.clip(0)\n'
'\n'
'# plan_tier, currency_type\n'
'tier_map = {\n'
'    "pk_1487":"basic","pk_1488":"standard","pk_1489":"premium",\n'
'    "pk_2025":"basic","pk_2026":"standard","pk_2027":"premium",\n'
'    "pk_1508":"basic","pk_1506":"standard","pk_1507":"premium",\n'
'}\n'
'df_v2["plan_tier"]     = df_v2["product_cd"].map(tier_map).fillna("기타")\n'
'df_v2["currency_type"] = df_v2["product_cd"].isin(["pk_1508","pk_1506","pk_1507"]).map({True:"USD",False:"KRW"})\n'
'\n'
'# 금액 더미\n'
'amount_norm = df_v2["amount"].copy()\n'
'df_v2["is_promotional_price"] = (amount_norm == 100).astype(int)\n'
'df_v2["amt_100"]   = (amount_norm == 100).astype(int)\n'
'df_v2["amt_7900"]  = (amount_norm == 7900).astype(int)\n'
'df_v2["amt_10900"] = (amount_norm == 10900).astype(int)\n'
'df_v2["amt_13900"] = (amount_norm == 13900).astype(int)\n'
'\n'
'# 가입 시간 파생\n'
'df_v2["reg_weekday"]    = pd.to_datetime(df_v2["reg_date"]).dt.weekday\n'
'df_v2["is_night_signup"]= df_v2["reg_hour"].isin([22,23,0,1,2,3,4,5]).astype(int)\n'
'df_v2["is_same_day_cancel"] = (df_v2["duration_days"] == 0).astype(int)\n'
'df_v2["age_group"]      = (df_v2["age"] // 10) * 10\n'
'\n'
'# 시청 파생 (user_mapping 컬럼 활용)\n'
'df_v2["has_watch_history"]    = (df_v2["view_count"] > 0).astype(int)\n'
'df_v2["avg_duration"]         = (df_v2["total_duration"] / (df_v2["view_count"] + 1)).round(2)\n'
'df_v2["watch_density"]        = df_v2["view_count"] / (df_v2["duration_days"] + 1)\n'
'df_v2["binge_score"]          = df_v2["dur_w1"] / (df_v2["total_duration"] + 1)\n'
'df_v2["recency"]              = (df_v2["dur_w3"] == 0).astype(int) * df_v2["duration_days"]\n'
'df_v2["stream_watch_interaction"] = df_v2["concurrent_streams"] * df_v2["view_count"]\n'
'\n'
'drop_cols2 = ["user_no","product_cd","reg_date","end_date",\n'
'              "reg_date_dt","end_date_dt","USER_ID","repurchase_label","registerday"]\n'
'df_feat = df_v2.drop(columns=[c for c in drop_cols2 if c in df_v2.columns])\n'
'\n'
'print(f"v2 파생변수 추가본 피처 수 (타겟 제외): {df_feat.shape[1]-1}")\n'
'new_feats = ["duration_days","plan_tier","currency_type","is_promotional_price",\n'
'             "amt_100","amt_7900","amt_10900","amt_13900","reg_weekday",\n'
'             "is_night_signup","is_same_day_cancel","age_group","has_watch_history",\n'
'             "avg_duration","watch_density","binge_score","recency","stream_watch_interaction"]\n'
'print(f"추가된 파생변수: {len(new_feats)}개")',
"cell-feat"))

# 셀 4: make_Xy + split
cells.append(code(
'def make_Xy(df):\n'
'    feat = [c for c in df.columns if c != "repurchase"]\n'
'    X = df[feat].copy()\n'
'    for c in X.select_dtypes(include="object").columns:\n'
'        X[c] = LabelEncoder().fit_transform(X[c].astype(str))\n'
'    X = X.fillna(0)\n'
'    return X, df["repurchase"], feat\n'
'\n'
'X_base, y_base, feat_base = make_Xy(df_base)\n'
'X_feat, y_feat, feat_feat = make_Xy(df_feat)\n'
'\n'
'Xb_tr, Xb_te, yb_tr, yb_te = train_test_split(X_base, y_base, test_size=0.2, random_state=42, stratify=y_base)\n'
'Xf_tr, Xf_te, yf_tr, yf_te = train_test_split(X_feat, y_feat, test_size=0.2, random_state=42, stratify=y_feat)\n'
'\n'
'print(f"기본:    피처 {len(feat_base)}개 | Train {len(Xb_tr)} / Test {len(Xb_te)}")\n'
'print(f"파생추가: 피처 {len(feat_feat)}개 | Train {len(Xf_tr)} / Test {len(Xf_te)}")',
"cell-split"))

# 셀 5: Optuna CatBoost 함수
cells.append(code(
'N_TRIALS = 100\n'
'\n'
'def obj_cat(trial, X_tr, y_tr):\n'
'    p = dict(\n'
'        iterations    = trial.suggest_int("iterations", 200, 800),\n'
'        learning_rate = trial.suggest_float("learning_rate", 0.01, 0.2, log=True),\n'
'        depth         = trial.suggest_int("depth", 3, 9),\n'
'        l2_leaf_reg   = trial.suggest_float("l2_leaf_reg", 1e-3, 10.0, log=True),\n'
'        random_seed=42, verbose=0,\n'
'    )\n'
'    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)\n'
'    return cross_val_score(CatBoostClassifier(**p), X_tr, y_tr,\n'
'                           cv=cv, scoring="roc_auc", n_jobs=-1).mean()\n'
'\n'
'def run_cat(X_tr, y_tr, X_te, y_te, label):\n'
'    print(f"[{label}] CatBoost Optuna {N_TRIALS} trials...")\n'
'    study = optuna.create_study(direction="maximize")\n'
'    study.optimize(lambda t: obj_cat(t, X_tr, y_tr), n_trials=N_TRIALS, show_progress_bar=True)\n'
'\n'
'    model = CatBoostClassifier(**study.best_params, random_seed=42, verbose=0)\n'
'    model.fit(X_tr, y_tr)\n'
'\n'
'    prob  = model.predict_proba(X_te)[:,1]\n'
'    pred  = model.predict(X_te)\n'
'    tr_auc = roc_auc_score(y_tr, model.predict_proba(X_tr)[:,1])\n'
'    te_auc = roc_auc_score(y_te, prob)\n'
'    gap    = tr_auc - te_auc\n'
'\n'
'    result = {\n'
'        "label":   label,\n'
'        "CV":      round(study.best_value, 4),\n'
'        "AUC":     round(te_auc, 4),\n'
'        "PR_AUC":  round(average_precision_score(y_te, prob), 4),\n'
'        "Acc":     round(accuracy_score(y_te, pred), 4),\n'
'        "F1":      round(f1_score(y_te, pred), 4),\n'
'        "gap":     round(gap, 4),\n'
'        "model":   model,\n'
'    }\n'
'    auc_te = result["AUC"]\n'
'    print(f"  CV={study.best_value:.4f}  Test AUC={auc_te:.4f}  Gap={gap:+.4f}")\n'
'    return result\n'
'\n'
'print("Optuna 함수 정의 완료")',
"cell-optuna"))

# 셀 6: 실행
cells.append(code(
'result_base = run_cat(Xb_tr, yb_tr, Xb_te, yb_te, "기본 final_merged")\n'
'result_feat = run_cat(Xf_tr, yf_tr, Xf_te, yf_te, "파생변수 추가")',
"cell-run"))

# 셀 7: 결과 비교
cells.append(code(
'print()\n'
'print("=" * 62)\n'
'print(" CatBoost Optuna 100 — 기본 vs 파생변수 추가 비교")\n'
'print("=" * 62)\n'
'fmt_h = "  {:<18}  {:>7}  {:>7}  {:>7}  {:>8}  {:>6}  {:>8}"\n'
'fmt_r = "  {:<18}  {:>7.4f}  {:>7.4f}  {:>7.4f}  {:>8.4f}  {:>6.4f}  {:>8}"\n'
'print(fmt_h.format("버전", "CV-AUC", "AUC", "PR-AUC", "Accuracy", "F1", "Gap"))\n'
'print("  " + "-" * 60)\n'
'\n'
'for r in [result_base, result_feat]:\n'
'    flag = " << 과적합" if r["gap"] > 0.05 else ""\n'
'    print(fmt_r.format(r["label"], r["CV"], r["AUC"], r["PR_AUC"],\n'
'                       r["Acc"], r["F1"], f"{r[\'gap\']:+.4f}{flag}"))\n'
'\n'
'print("=" * 62)\n'
'diff = result_feat["AUC"] - result_base["AUC"]\n'
'print(f"\\n파생변수 추가 효과: {diff:+.4f}")\n'
'if diff > 0.003:\n'
'    print("-> 파생변수가 유의미하게 기여함")\n'
'elif diff > 0:\n'
'    print("-> 파생변수가 소폭 기여함")\n'
'else:\n'
'    print("-> 파생변수 효과 없음 (기본 모델과 동일 수준)")',
"cell-result"))

# 셀 8: Feature Importance 비교
cells.append(code(
'import matplotlib.pyplot as plt\n'
'import matplotlib\n'
'matplotlib.rcParams["font.family"] = "Malgun Gothic"\n'
'matplotlib.rcParams["axes.unicode_minus"] = False\n'
'from matplotlib.patches import Patch\n'
'\n'
'derived = {"duration_days","plan_tier","currency_type","is_promotional_price",\n'
'           "amt_100","amt_7900","amt_10900","amt_13900","reg_weekday",\n'
'           "is_night_signup","is_same_day_cancel","age_group","has_watch_history",\n'
'           "avg_duration","watch_density","binge_score","recency","stream_watch_interaction"}\n'
'\n'
'fig, axes = plt.subplots(1, 2, figsize=(18, 8))\n'
'\n'
'for ax, res, feats, title in [\n'
'    (axes[0], result_base, feat_base, "기본 final_merged"),\n'
'    (axes[1], result_feat, feat_feat, "파생변수 추가"),\n'
']:\n'
'    fi = pd.Series(res["model"].feature_importances_, index=feats).sort_values(ascending=False)\n'
'    top20 = fi.head(20).sort_values()\n'
'    colors = ["#C00000" if f in derived else "#4472C4" for f in top20.index]\n'
'    top20.plot(kind="barh", ax=ax, color=colors[::-1])\n'
'    ax.set_title(f"Top 20 Feature Importance\\n{title}\\n빨강=파생변수 / 파랑=기본")\n'
'    ax.set_xlabel("Importance")\n'
'\n'
'axes[1].legend(handles=[Patch(color="#C00000", label="파생변수"),\n'
'                         Patch(color="#4472C4", label="기본 피처")])\n'
'plt.tight_layout()\n'
'plt.show()\n'
'\n'
'print("\\n=== 파생변수 추가본 Top 15 ===")\n'
'fi_feat = pd.Series(result_feat["model"].feature_importances_, index=feat_feat).sort_values(ascending=False)\n'
'for i, (f, v) in enumerate(fi_feat.head(15).items(), 1):\n'
'    tag = " <- 파생" if f in derived else ""\n'
'    print(f"  {i:>2}. {f:<30} {v:.1f}{tag}")',
"cell-fi"))

nb["cells"] = cells
path = "c:/Users/USER/OneDrive/바탕 화면/새 폴더/모델링/model_final_merged.ipynb"
with open(path, "w", encoding="utf-8") as f:
    json.dump(nb, f, ensure_ascii=False, indent=1)
print("저장 완료:", path)