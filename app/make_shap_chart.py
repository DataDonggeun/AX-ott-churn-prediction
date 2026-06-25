"""
SHAP Beeswarm plot PNG 생성 (프로모션 / 비프로모션)
실행: python make_shap_chart.py
출력: cache/shap_beeswarm_promotion.png, cache/shap_beeswarm_nonpromotion.png
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.colors import Normalize
from matplotlib.cm import ScalarMappable

from cache import load_df, load_artifact
from config import RANDOM_STATE, PAYMENT_FEATURES

# ── 한국어 폰트 ─────────────────────────────────────────────────────────────────
for font in ["Malgun Gothic", "NanumGothic", "AppleGothic", "DejaVu Sans"]:
    try:
        fm.findfont(fm.FontProperties(family=font), fallback_to_default=False)
        plt.rcParams["font.family"] = font
        break
    except Exception:
        continue
plt.rcParams["axes.unicode_minus"] = False

# ── 피처 한국어 매핑 ────────────────────────────────────────────────────────────
KO = {
    "retention_w2_ratio":       "2주차 시청 유지율",
    "retention_w3_ratio":       "3주차 시청 유지율",
    "is_cold_start_3d":         "가입 후 3일 내 미시청",
    "drama_ratio":              "드라마 시청 비율",
    "romance_ratio":            "로맨스 시청 비율",
    "thriller_crime_ratio":     "스릴러/범죄 시청 비율",
    "family_animation_ratio":   "가족/애니메이션 시청 비율",
    "watch_time(min)_w3":       "3주차 총 시청 시간",
    "action_adventure_ratio":   "액션/어드벤처 시청 비율",
    "max_watch_time(min)":      "최대 1회 시청 시간",
    "diff_between_w3_w2":       "3→2주차 시청 변화량",
    "diff_between_w2_w1":       "2→1주차 시청 변화량",
    "diff_between_w3_w1":       "3→1주차 시청 변화량",
    "median_watch_time(min)":   "중간 시청 시간",
    "genre_diversity_count":    "장르 다양성 수",
    "is_churn_prevented":       "이탈 방지 이력",
    "is_basic":                 "베이직 요금제",
    "avg_watch_time(min)":      "평균 시청 시간",
    "horror_ratio":             "공포 시청 비율",
    "is_w1_over_50pct":         "1주차 시청 50% 이상",
    "is_only_w1":               "1주차에만 시청",
    "age_group":                "연령대",
    "max_day_share":            "특정 요일 집중도",
    "watch_time(min)_w1":       "1주차 총 시청 시간",
    "sf_fantasy_ratio":         "SF/판타지 시청 비율",
}

cache_dir = Path(__file__).parent / "cache"


def compute_shap(df_scope: pd.DataFrame, features: list, model, n_sample: int = 2000):
    import shap
    from sklearn.base import clone

    X = df_scope[features].apply(pd.to_numeric, errors="coerce").fillna(0)
    y = (1 - df_scope["is_repurchase"].astype(int)).to_numpy()

    rng = np.random.RandomState(RANDOM_STATE)
    idx = rng.choice(len(X), min(n_sample, len(X)), replace=False)
    X_sample = X.iloc[idx]

    fitted = clone(model)
    fitted.fit(X, y)

    explainer = shap.TreeExplainer(fitted)
    vals = explainer.shap_values(X_sample)
    if isinstance(vals, list):
        vals = vals[1] if len(vals) > 1 else vals[0]
    vals = np.asarray(vals)
    if vals.ndim == 3:
        vals = vals[:, :, 1] if vals.shape[2] > 1 else vals[:, :, 0]

    return vals, X_sample.reset_index(drop=True)


def make_beeswarm(scope_key: str, title: str, out_path: Path, top_n: int = 10):
    exp_df = load_df("expanded_dataset")
    model  = load_artifact(f"tuned_model_{scope_key}")

    inc_promo = (scope_key == "overall")
    if scope_key == "promotion_only":
        df_scope = exp_df[exp_df["is_promotion"] == 1].copy()
    elif scope_key == "nonpromotion_only":
        df_scope = exp_df[exp_df["is_promotion"] == 0].copy()
    else:
        df_scope = exp_df.copy()

    exclude  = {"USER_KEY", "is_repurchase"} | (set() if inc_promo else {"is_promotion"})
    features = [c for c in exp_df.columns if c not in exclude and c in df_scope.columns]

    print(f"[{scope_key}] SHAP 계산 중...")
    shap_vals, X_sample = compute_shap(df_scope, features, model)

    # top_n 피처 선택 (mean |shap| 기준)
    mean_abs = np.abs(shap_vals).mean(axis=0)
    top_idx  = np.argsort(mean_abs)[::-1][:top_n]
    top_idx  = top_idx[::-1]  # 위쪽이 1등 되도록 뒤집기

    top_features  = [features[i] for i in top_idx]
    top_shap      = shap_vals[:, top_idx]
    top_X         = X_sample.iloc[:, top_idx]

    # ── 그리기 ──────────────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(11, 7))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    cmap = plt.get_cmap("RdBu_r")   # 파랑(낮은 값) → 빨강(높은 값)

    for row_i, feat_i in enumerate(range(top_n)):
        sv   = top_shap[:, feat_i]
        fv   = top_X.iloc[:, feat_i].values.astype(float)

        # 피처 값 0~1 정규화 → 색상
        fv_min, fv_max = fv.min(), fv.max()
        fv_norm = (fv - fv_min) / (fv_max - fv_min + 1e-9)
        colors  = cmap(fv_norm)

        # y축 jitter (겹침 방지)
        jitter = np.random.RandomState(RANDOM_STATE + row_i).uniform(-0.3, 0.3, len(sv))
        y_pos  = np.full(len(sv), row_i) + jitter

        ax.scatter(sv, y_pos, c=colors, s=8, alpha=0.6, linewidths=0)

    # y축 레이블
    labels_ko = [KO.get(f, f) for f in top_features]
    ax.set_yticks(range(top_n))
    ax.set_yticklabels(labels_ko, fontsize=11)
    ax.set_ylim(-0.6, top_n - 0.4)

    ax.axvline(0, color="#555", linewidth=0.8, linestyle="--")
    ax.set_xlabel("SHAP 값  (+ : 이탈 위험 증가 / − : 이탈 위험 감소)", fontsize=11)
    ax.set_title(title, fontsize=14, fontweight="bold", pad=14)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.xaxis.grid(True, linestyle="--", alpha=0.3)
    ax.set_axisbelow(True)

    # 컬러바 (피처 값 Low→High)
    sm = ScalarMappable(cmap=cmap, norm=Normalize(0, 1))
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, orientation="vertical", fraction=0.02, pad=0.02)
    cbar.set_ticks([0, 1])
    cbar.set_ticklabels(["낮음", "높음"], fontsize=9)
    cbar.set_label("피처 값", fontsize=9)

    ax.text(0.01, -0.07, "※ SHAP은 모델 설명이며 인과 주장이 아님",
            transform=ax.transAxes, fontsize=8, color="#999")

    plt.tight_layout()
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"저장 완료: {out_path}")


make_beeswarm(
    "promotion_only",
    "SHAP Beeswarm — 프로모션 가입자 (Top 10)",
    cache_dir / "shap_beeswarm_promotion.png",
)
make_beeswarm(
    "nonpromotion_only",
    "SHAP Beeswarm — 비프로모션 가입자 (Top 10)",
    cache_dir / "shap_beeswarm_nonpromotion.png",
)
