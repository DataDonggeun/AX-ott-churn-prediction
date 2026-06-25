import json
import pickle
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import shap

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

# ── 데이터 로드 ──────────────────────────────────────────────────────────
with open("cache/step06_shap_global.json", encoding="utf-8") as f:
    shap_data = json.load(f)

with open("cache/tuned_model_nonpromotion_only.pkl", "rb") as f:
    model_nonpromo = pickle.load(f)
with open("cache/tuned_model_promotion_only.pkl", "rb") as f:
    model_promo = pickle.load(f)

exp_df = pd.read_csv("cache/expanded_dataset.csv")

FAMILY_COLORS = {
    "usage_retention_behavior": "#4C72B0",
    "content_preference":       "#DD8452",
    "acquisition_split":        "#55A868",
    "membership_context":       "#C44E52",
    "other":                    "#8172B3",
    "payment_proxy":            "#AAAAAA",
}
SCOPE_LABELS = {
    "overall":           "전체",
    "promotion_only":    "프로모션 가입",
    "nonpromotion_only": "일반 가입",
}
TOP_N = 15


# ── 그래프 1: scope별 Top15 절댓값 막대 ─────────────────────────────────
fig1, axes = plt.subplots(1, 3, figsize=(20, 8))
fig1.suptitle("SHAP Feature Importance Top 15 (scope별)", fontsize=15, fontweight="bold", y=1.01)

for ax, scope in zip(axes, ["overall", "promotion_only", "nonpromotion_only"]):
    top = shap_data["by_scope"][scope]["shap"]["top20"][:TOP_N]
    features = [d["feature"] for d in reversed(top)]
    values   = [d["mean_abs_shap"] for d in reversed(top)]
    colors   = [FAMILY_COLORS.get(d["family"], "#AAAAAA") for d in reversed(top)]

    bars = ax.barh(features, values, color=colors, edgecolor="white", height=0.7)
    ax.set_title(SCOPE_LABELS[scope], fontsize=13, fontweight="bold", pad=10)
    ax.set_xlabel("Mean |SHAP value|", fontsize=10)
    ax.tick_params(axis="y", labelsize=9)
    ax.spines[["top", "right"]].set_visible(False)
    for bar, val in zip(bars, values):
        ax.text(val + 0.003, bar.get_y() + bar.get_height() / 2,
                f"{val:.3f}", va="center", fontsize=8)

legend_patches = [mpatches.Patch(color=c, label=k.replace("_", " ").title())
                  for k, c in FAMILY_COLORS.items()]
fig1.legend(handles=legend_patches, loc="lower center", ncol=3,
            fontsize=10, frameon=False, bbox_to_anchor=(0.5, -0.04))
plt.tight_layout()
fig1.savefig("cache/shap_top15.png", dpi=150, bbox_inches="tight")
print("저장: cache/shap_top15.png")


# ── 그래프 2: 양수/음수 방향 SHAP (Diverging Bar) ───────────────────────
def compute_directional_shap(df, model, exclude_cols, top_n=15, sample=3000):
    features = [c for c in df.columns if c not in exclude_cols]
    X = df[features].apply(pd.to_numeric, errors="coerce").fillna(0)
    if len(X) > sample:
        idx = np.random.RandomState(42).choice(len(X), sample, replace=False)
        X = X.iloc[idx]
    explainer = shap.TreeExplainer(model)
    vals = explainer.shap_values(X)
    if isinstance(vals, list):
        vals = vals[1] if len(vals) > 1 else vals[0]
    vals = np.asarray(vals)
    if vals.ndim == 3:
        vals = vals[:, :, 1] if vals.shape[2] > 1 else vals[:, :, 0]

    mean_pos = np.where(vals > 0, vals, 0).mean(axis=0)
    mean_neg = np.where(vals < 0, vals, 0).mean(axis=0)
    mean_abs = np.abs(vals).mean(axis=0)

    df_imp = pd.DataFrame({
        "feature":  features,
        "mean_abs": mean_abs,
        "mean_pos": mean_pos,
        "mean_neg": mean_neg,
    }).sort_values("mean_abs", ascending=False).head(top_n)
    return df_imp


fig2, axes2 = plt.subplots(1, 2, figsize=(18, 8))
fig2.suptitle("SHAP 방향성 분석 — 이탈 위험 증가(+) vs 감소(-)", fontsize=15, fontweight="bold")

exclude_base = {"USER_KEY", "is_repurchase"}

configs = [
    (exp_df[exp_df["is_promotion"] == 1].copy(), model_promo,
     exclude_base | {"is_promotion"}, "프로모션 가입", axes2[0]),
    (exp_df[exp_df["is_promotion"] == 0].copy(), model_nonpromo,
     exclude_base | {"is_promotion"}, "일반 가입", axes2[1]),
]

for df_s, model_s, excl, title, ax in configs:
    df_imp = compute_directional_shap(df_s, model_s, excl, top_n=15)
    features = df_imp["feature"].tolist()[::-1]
    pos_vals = df_imp["mean_pos"].tolist()[::-1]
    neg_vals = df_imp["mean_neg"].tolist()[::-1]
    y = np.arange(len(features))

    ax.barh(y, pos_vals, color="#E05C5C", label="이탈 위험 증가 (+)", height=0.6)
    ax.barh(y, neg_vals, color="#4C72B0", label="이탈 위험 감소 (-)", height=0.6)
    ax.axvline(0, color="black", linewidth=0.8, linestyle="--")
    ax.set_yticks(y)
    ax.set_yticklabels(features, fontsize=9)
    ax.set_xlabel("Mean SHAP value", fontsize=10)
    ax.set_title(title, fontsize=13, fontweight="bold")
    ax.legend(fontsize=9, frameon=False)
    ax.spines[["top", "right"]].set_visible(False)

plt.tight_layout()
fig2.savefig("cache/shap_directional.png", dpi=150, bbox_inches="tight")
print("저장: cache/shap_directional.png")

plt.show()
print("완료.")
