"""
Stacking 앙상블 다이어그램 PNG 생성 스크립트
실행: python make_stacking_diagram.py
출력: stacking_diagram.png
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import matplotlib.font_manager as fm

# Windows 한글 폰트 설정
_KO_FONTS = ["Malgun Gothic", "맑은 고딕", "NanumGothic", "AppleGothic", "Gulim"]
_ko_font = next(
    (f.name for f in fm.fontManager.ttflist if f.name in _KO_FONTS),
    None,
)
if _ko_font:
    plt.rcParams["font.family"] = _ko_font
plt.rcParams["axes.unicode_minus"] = False

fig, ax = plt.subplots(figsize=(20, 11))
ax.set_xlim(0, 20)
ax.set_ylim(0, 11)
ax.axis("off")
fig.patch.set_facecolor("white")

# ── 색상 팔레트 ─────────────────────────────────────────────────────────────────
C_PURPLE   = "#6C5CE7"
C_BLUE     = "#4A90D9"
C_LBLUE    = "#74B9FF"
C_HEADER   = "#2D3436"
C_FOLD_BG  = "#EEF2FF"
C_FOLD_BD  = "#A29BFE"
C_META_BG  = "#4A90D9"
C_FINAL_BG = "#2D3436"
C_TEXT_W   = "white"
C_TEXT_D   = "#2D3436"
C_ARROW    = "#636E72"

def rounded_box(ax, x, y, w, h, fc, ec, lw=1.5, radius=0.25, alpha=1.0):
    box = FancyBboxPatch(
        (x, y), w, h,
        boxstyle=f"round,pad=0,rounding_size={radius}",
        facecolor=fc, edgecolor=ec, linewidth=lw, alpha=alpha,
    )
    ax.add_patch(box)
    return box

def arrow(ax, x1, y1, x2, y2, color=C_ARROW, lw=1.5, style="->"):
    ax.annotate(
        "", xy=(x2, y2), xytext=(x1, y1),
        arrowprops=dict(arrowstyle=style, color=color, lw=lw),
    )

def text(ax, x, y, s, fs=10, color="white", ha="center", va="center", bold=False):
    ax.text(x, y, s, fontsize=fs, color=color, ha=ha, va=va,
            fontweight="bold" if bold else "normal")

# ══════════════════════════════════════════════════════════════════════
# 제목
# ══════════════════════════════════════════════════════════════════════
ax.text(10, 10.5, "교차검증 기반 Stacking 앙상블",
        fontsize=19, fontweight="bold", color=C_HEADER,
        ha="center", va="center")
ax.text(10, 10.0,
        "5개 Base Learner OOF Stacking으로 데이터 누수 방지, 모델 강화",
        fontsize=11, color="#636E72", ha="center", va="center")

# ══════════════════════════════════════════════════════════════════════
# 1. Training Set 박스
# ══════════════════════════════════════════════════════════════════════
rounded_box(ax, 0.3, 3.8, 1.6, 2.8, C_PURPLE, C_PURPLE, lw=0)
text(ax, 1.1, 5.2, "Training", fs=10, bold=True)
text(ax, 1.1, 4.9, "Set", fs=10)

# ══════════════════════════════════════════════════════════════════════
# 2. 5번 반복 레이블
# ══════════════════════════════════════════════════════════════════════
rounded_box(ax, 2.1, 8.4, 1.5, 0.5, C_PURPLE, C_PURPLE, lw=0, radius=0.2)
text(ax, 2.85, 8.65, "5번 반복", fs=9, bold=True)

# ══════════════════════════════════════════════════════════════════════
# 3. Fold 블록 (5-fold 분할)
# ══════════════════════════════════════════════════════════════════════
fold_x, fold_y0, fold_w, fold_h, fold_gap = 2.2, 2.3, 1.4, 1.0, 0.18

fold_labels = ["Fold 1", "Fold 2", "Fold 3", "Fold 4", "Fold 5 (Val)"]
fold_colors = [C_FOLD_BG] * 4 + ["#A29BFE"]
fold_tcolors = [C_TEXT_D] * 4 + [C_TEXT_W]

for i, (label, fc, tc) in enumerate(zip(fold_labels, fold_colors, fold_tcolors)):
    fy = fold_y0 + i * (fold_h + fold_gap)
    rounded_box(ax, fold_x, fy, fold_w, fold_h, fc, C_FOLD_BD, lw=1.5, radius=0.15)
    text(ax, fold_x + fold_w / 2, fy + fold_h / 2, label, fs=8.5, color=tc)

# "Training folds" / "Validation fold" 레이블
ax.text(2.9, 5.55, "Training\nfolds", fontsize=8, color=C_TEXT_D,
        ha="center", va="center", style="italic")
ax.text(2.9, 2.8, "Validation\nfold", fontsize=8, color=C_TEXT_W,
        ha="center", va="center", style="italic")

# Training Set → Fold 화살표
arrow(ax, 1.9, 5.2, 2.2, 5.2, lw=1.8)

# ══════════════════════════════════════════════════════════════════════
# 4. Base Learner 박스 (중앙)
# ══════════════════════════════════════════════════════════════════════
base_x    = 5.5
base_w    = 2.0
base_h    = 0.72
base_gap  = 0.38
base_y0   = 2.5

models = ["LGBM", "XGBoost", "CatBoost", "Random\nForest", "SVM"]

# "Base Learner 학습" 헤더
ax.text(base_x + base_w / 2, 9.1, "Base Learner 학습",
        fontsize=11, fontweight="bold", color=C_BLUE,
        ha="center", va="center")
ax.text(base_x + base_w / 2, 8.7,
        "각 fold마다 5개 Base를\n4개 folds로 학습",
        fontsize=8.5, color="#636E72", ha="center", va="center")

for i, name in enumerate(models):
    by = base_y0 + i * (base_h + base_gap)
    rounded_box(ax, base_x, by, base_w, base_h, C_LBLUE, C_BLUE, lw=1.5, radius=0.18)
    text(ax, base_x + base_w / 2, by + base_h / 2, name, fs=9.5, color=C_TEXT_W, bold=True)
    # Fold → Base Learner 화살표
    arrow(ax, fold_x + fold_w, fold_y0 + 2 * (fold_h + fold_gap) + fold_h / 2,
          base_x, by + base_h / 2, lw=1.2)

# ══════════════════════════════════════════════════════════════════════
# 5. Hold-out 예측값 박스
# ══════════════════════════════════════════════════════════════════════
hout_x   = 9.1
hout_w   = 1.8
hout_h   = base_h
hout_gap = base_gap

ax.text(hout_x + hout_w / 2, 9.1, "Hold-out fold",
        fontsize=10, fontweight="bold", color=C_BLUE,
        ha="center", va="center")
ax.text(hout_x + hout_w / 2, 8.7, "예측값 저장 (%)",
        fontsize=8.5, color="#636E72", ha="center", va="center")

hout_labels = ["LGBM\n예측값", "XGBoost\n예측값", "CatBoost\n예측값",
               "RF\n예측값", "SVM\n예측값"]

for i, label in enumerate(hout_labels):
    hy = base_y0 + i * (hout_h + hout_gap)
    rounded_box(ax, hout_x, hy, hout_w, hout_h, C_FOLD_BG, C_FOLD_BD, lw=1.5, radius=0.18)
    text(ax, hout_x + hout_w / 2, hy + hout_h / 2, label, fs=8.5, color=C_TEXT_D)
    # Base → Hold-out 화살표
    arrow(ax, base_x + base_w,
          base_y0 + i * (base_h + base_gap) + base_h / 2,
          hout_x,
          hy + hout_h / 2,
          lw=1.2)

# ══════════════════════════════════════════════════════════════════════
# 6. Meta Learner 헤더 + 박스
# ══════════════════════════════════════════════════════════════════════
meta_x, meta_y, meta_w, meta_h = 13.0, 4.3, 2.6, 1.8

ax.text(meta_x + meta_w / 2, 9.1, "Meta Learner 학습",
        fontsize=11, fontweight="bold", color=C_BLUE,
        ha="center", va="center")
ax.text(meta_x + meta_w / 2, 8.7,
        "각 모델의 OOF 예측을\n피처로 메타모델 학습",
        fontsize=8.5, color="#636E72", ha="center", va="center")

rounded_box(ax, meta_x, meta_y, meta_w, meta_h, C_META_BG, C_META_BG, lw=0, radius=0.3)
text(ax, meta_x + meta_w / 2, meta_y + meta_h / 2 + 0.2,
     "Logistic", fs=12, bold=True)
text(ax, meta_x + meta_w / 2, meta_y + meta_h / 2 - 0.25,
     "Regression", fs=12, bold=True)

# Hold-out → Meta (5개 선 모두)
for i in range(5):
    hy = base_y0 + i * (hout_h + hout_gap) + hout_h / 2
    arrow(ax, hout_x + hout_w, hy,
          meta_x, meta_y + meta_h / 2,
          lw=1.2)

# ══════════════════════════════════════════════════════════════════════
# 7. 최종 예측값 박스
# ══════════════════════════════════════════════════════════════════════
fin_x, fin_y, fin_w, fin_h = 16.5, 4.6, 2.2, 1.3

rounded_box(ax, fin_x, fin_y, fin_w, fin_h, C_FINAL_BG, C_FINAL_BG, lw=0, radius=0.25)
text(ax, fin_x + fin_w / 2, fin_y + fin_h / 2, "최종\n예측값", fs=12, bold=True)

arrow(ax, meta_x + meta_w, meta_y + meta_h / 2,
      fin_x, fin_y + fin_h / 2,
      lw=2.2, color=C_PURPLE, style="-|>")

# ══════════════════════════════════════════════════════════════════════
# 8. Test Set 화살표 (하단)
# ══════════════════════════════════════════════════════════════════════
rounded_box(ax, 0.3, 1.1, 1.6, 0.65, "#636E72", "#636E72", lw=0, radius=0.18)
text(ax, 1.1, 1.42, "Test set", fs=9.5, bold=True)

# Test set → (아래 점선) → 각 Base Learner 예측
ax.annotate(
    "", xy=(base_x + base_w / 2, 1.5),
    xytext=(1.9, 1.42),
    arrowprops=dict(arrowstyle="->", color="#636E72", lw=1.5,
                    linestyle="dashed"),
)

rounded_box(ax, base_x - 0.1, 1.0, base_w + 0.2, 0.65,
            "#DFE6E9", "#B2BEC3", lw=1.2, radius=0.15)
text(ax, base_x + base_w / 2, 1.32,
     "각 Base Learner로 예측", fs=8.5, color=C_TEXT_D)

# Base Learner 예측 → Meta
arrow(ax, base_x + base_w + 0.1, 1.32,
      meta_x + meta_w / 2, meta_y,
      lw=1.5, color="#636E72")

# ══════════════════════════════════════════════════════════════════════
# 9. 저장
# ══════════════════════════════════════════════════════════════════════
plt.tight_layout(pad=0.5)
out_path = "stacking_diagram.png"
plt.savefig(out_path, dpi=180, bbox_inches="tight",
            facecolor="white", edgecolor="none")
plt.close()
print(f"저장 완료: {out_path}")
