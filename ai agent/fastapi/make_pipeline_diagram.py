"""
슬라이드 스타일 파이프라인 다이어그램
실행: python make_pipeline_diagram.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import matplotlib.font_manager as fm
import matplotlib.patheffects as pe

_KO = ["Malgun Gothic", "맑은 고딕", "NanumGothic", "Gulim"]
_ko = next((f.name for f in fm.fontManager.ttflist if f.name in _KO), None)
if _ko:
    plt.rcParams["font.family"] = _ko
plt.rcParams["axes.unicode_minus"] = False

# ── 슬라이드 색상 (원본과 최대한 동일) ──────────────────────────────────────────
C_BG_OUTER  = "white"
C_BG_INNER  = "#F0F1F8"          # 연보라 컨테이너
C_FOLD_LT   = "#D8DAF0"          # 일반 fold
C_FOLD_DK   = "#6C5CE7"          # Validation fold
C_MODEL     = "#7986CB"          # 모델 박스
C_MODEL_WIN = "#5C6BC0"          # 우승 모델
C_OOF       = "#D8DAF0"          # OOF 결과 박스
C_BADGE     = "#8E44AD"          # "5번 반복" 배지
C_META      = "#5C6BC0"          # Meta/Step06 박스
C_FINAL     = "#5C6BC0"          # 최종 박스
C_ARROW     = "#9E9E9E"
C_HDR_BLUE  = "#1A5DAC"          # 섹션 헤더 텍스트
C_DARK      = "#212121"
C_GRAY      = "#757575"
C_WHITE     = "white"
C_WINNER_BD = "#E53935"          # 우승 강조 테두리

fig, ax = plt.subplots(figsize=(22, 10))
ax.set_xlim(0, 22)
ax.set_ylim(0, 10)
ax.axis("off")
fig.patch.set_facecolor(C_BG_OUTER)


# ── helpers ───────────────────────────────────────────────────────────────────
def rbox(x, y, w, h, fc, ec=None, lw=1.2, r=0.2, alpha=1.0, zorder=2):
    ec = ec or fc
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h,
        boxstyle=f"round,pad=0,rounding_size={r}",
        facecolor=fc, edgecolor=ec, linewidth=lw,
        alpha=alpha, zorder=zorder,
    ))

def t(x, y, s, fs=9, c=C_DARK, ha="center", va="center",
      bold=False, italic=False, z=5):
    ax.text(x, y, s, fontsize=fs, color=c, ha=ha, va=va, zorder=z,
            fontweight="bold" if bold else "normal",
            fontstyle="italic" if italic else "normal",
            linespacing=1.4)

def arr(x1, y1, x2, y2, color=C_ARROW, lw=1.4, style="->", ls="solid"):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
        arrowprops=dict(arrowstyle=style, color=color, lw=lw,
                        linestyle=ls, mutation_scale=14), zorder=4)


# ══════════════════════════════════════════════════════════════════════════════
# 배경 컨테이너
# ══════════════════════════════════════════════════════════════════════════════
rbox(2.4, 0.5, 17.2, 8.3, C_BG_INNER, C_BG_INNER, r=0.4, zorder=1)

# ══════════════════════════════════════════════════════════════════════════════
# 슬라이드 상단 레이블 (섹션 헤더 - 컨테이너 바깥 위)
# ══════════════════════════════════════════════════════════════════════════════
t(7.9,  9.55, "Step 04 · 계열 대표 비교",      fs=12, c=C_HDR_BLUE, bold=True)
t(7.9,  9.18, "각 fold마다 3개 모델을\n4개 fold로 학습",  fs=8.5, c=C_GRAY)

t(13.0, 9.55, "Hold-out fold 결과",           fs=12, c=C_HDR_BLUE, bold=True)
t(13.0, 9.18, "OOF AUC 비교 →\n우승 계열 선정", fs=8.5, c=C_GRAY)

t(17.5, 9.55, "Step 06 · 계열 내 비교",        fs=12, c=C_HDR_BLUE, bold=True)
t(17.5, 9.18, "Boosting 계열 5개 모델\n최적 모델 선정", fs=8.5, c=C_GRAY)

# ══════════════════════════════════════════════════════════════════════════════
# Training Set (왼쪽)
# ══════════════════════════════════════════════════════════════════════════════
rbox(0.2, 3.4, 1.8, 2.8, C_META, C_META, r=0.3, zorder=3)
t(1.1, 4.9, "Training\nSet", fs=11, c=C_WHITE, bold=True)

# >> 화살표
ax.annotate("", xy=(2.55, 4.8), xytext=(2.0, 4.8),
    arrowprops=dict(arrowstyle="-|>", color=C_ARROW, lw=2.0,
                    mutation_scale=18), zorder=4)

# ══════════════════════════════════════════════════════════════════════════════
# 5번 반복 배지
# ══════════════════════════════════════════════════════════════════════════════
rbox(2.8, 8.25, 1.5, 0.45, C_BADGE, C_BADGE, r=0.18, zorder=4)
t(3.55, 8.47, "5번 반복", fs=9, c=C_WHITE, bold=True)

# ══════════════════════════════════════════════════════════════════════════════
# Fold 블록 (5개)
# ══════════════════════════════════════════════════════════════════════════════
fold_x  = 2.6
fw, fh, fg = 1.55, 1.05, 0.18
fy0 = 1.5

fold_cfg = [
    ("Fold 1", C_FOLD_LT, C_DARK),
    ("Fold 2", C_FOLD_LT, C_DARK),
    ("Fold 3", C_FOLD_LT, C_DARK),
    ("Fold 4", C_FOLD_LT, C_DARK),
    ("Validation\nfold", C_FOLD_DK, C_WHITE),
]
for i, (lbl, fc, tc) in enumerate(fold_cfg):
    fy = fy0 + i * (fh + fg)
    rbox(fold_x, fy, fw, fh, fc, fc, r=0.15, zorder=3)
    t(fold_x + fw/2, fy + fh/2, lbl, fs=8.5, c=tc)

# 레이블
t(fold_x + fw/2, fy0 + 2*(fh+fg) + fh + 0.2, "Training\nfolds", fs=8, c=C_GRAY, italic=True)
t(fold_x + fw/2, fy0 - 0.35, "Validation\nfold", fs=8, c=C_FOLD_DK, italic=True)

# ══════════════════════════════════════════════════════════════════════════════
# Step 04 모델 박스 (3개: LR, XGB, RF)
# ══════════════════════════════════════════════════════════════════════════════
m4_x = 5.5
m4_bw, m4_bh, m4_gap = 2.2, 1.5, 0.55
m4_y0 = 1.8

m4_models = [
    ("Logistic\nRegression", C_MODEL,     C_MODEL,     False),
    ("XGBoost",              C_MODEL_WIN, C_WINNER_BD, True),
    ("Random\nForest",       C_MODEL,     C_MODEL,     False),
]

mid_fold_y = fy0 + 2*(fh+fg) + fh/2   # fold 중간 y

for i, (name, fc, ec, win) in enumerate(m4_models):
    my = m4_y0 + (2-i) * (m4_bh + m4_gap)
    lw = 2.5 if win else 1.2
    rbox(m4_x, my, m4_bw, m4_bh, fc, ec, lw=lw, r=0.2, zorder=3)
    t(m4_x + m4_bw/2, my + m4_bh/2, name, fs=10.5, c=C_WHITE, bold=win)
    # fold → model 화살표
    arr(fold_x + fw, mid_fold_y, m4_x, my + m4_bh/2, lw=1.1)

# ══════════════════════════════════════════════════════════════════════════════
# Hold-out fold OOF 결과 박스 (3개)
# ══════════════════════════════════════════════════════════════════════════════
oof_x = 8.9
oof_bw, oof_bh = 2.0, 1.5

oof_data = [
    ("LR\nAUC 0.712",     False),
    ("XGBoost\nAUC 0.763 ★", True),
    ("RF\nAUC 0.741",     False),
]

for i, (lbl, win) in enumerate(oof_data):
    oy = m4_y0 + (2-i) * (m4_bh + m4_gap)
    fc = "#B0BCD8" if not win else "#C5CAE9"
    ec = C_WINNER_BD if win else C_OOF
    lw = 2.5 if win else 1.2
    rbox(oof_x, oy, oof_bw, oof_bh, fc, ec, lw=lw, r=0.18, zorder=3)
    t(oof_x + oof_bw/2, oy + oof_bh/2, lbl, fs=10, c=C_DARK, bold=win)
    # model → oof 화살표
    arr(m4_x + m4_bw, m4_y0 + (2-i)*(m4_bh+m4_gap) + m4_bh/2,
        oof_x, oy + oof_bh/2, lw=1.1)

# ══════════════════════════════════════════════════════════════════════════════
# 우승 배지: Boosting 계열 선정
# ══════════════════════════════════════════════════════════════════════════════
rbox(9.2, 0.8, 1.5, 0.7, C_FOLD_DK, C_FOLD_DK, r=0.2, zorder=4)
t(9.95, 1.15, "Boosting\n계열 선정", fs=8.5, c=C_WHITE, bold=True)

# OOF XGBoost → 배지
arr(oof_x + oof_bw/2, m4_y0 + m4_bh/2, 9.95, 1.5, color=C_FOLD_DK, lw=1.5)

# ══════════════════════════════════════════════════════════════════════════════
# Step 06: Boosting 계열 세부 비교 (오른쪽, Meta 역할)
# ══════════════════════════════════════════════════════════════════════════════
s6_x = 12.3
s6_bw, s6_bh, s6_gap = 2.1, 0.95, 0.22
s6_y0 = 1.5

s6_models = [
    ("LightGBM",      True),
    ("XGBoost",       False),
    ("CatBoost",      False),
    ("HistGrad\nBoost", False),
    ("Gradient\nBoost", False),
]

for i, (name, win) in enumerate(s6_models):
    sy = s6_y0 + (4-i) * (s6_bh + s6_gap)
    fc = C_META if win else C_MODEL
    ec = C_WINNER_BD if win else C_MODEL
    lw = 2.5 if win else 1.2
    rbox(s6_x, sy, s6_bw, s6_bh, fc, ec, lw=lw, r=0.2, zorder=3)
    t(s6_x + s6_bw/2, sy + s6_bh/2, name, fs=10, c=C_WHITE, bold=win)
    # oof → s6 화살표 (OOF 우승 박스에서 연결)
    arr(oof_x + oof_bw, m4_y0 + m4_bh/2,
        s6_x, sy + s6_bh/2, color=C_ARROW, lw=0.9)

# ══════════════════════════════════════════════════════════════════════════════
# 최종 결과: Step 07 Optuna → 최종 모델
# ══════════════════════════════════════════════════════════════════════════════
fin_x, fin_y, fin_w, fin_h = 15.8, 3.4, 2.4, 1.8

rbox(fin_x, fin_y, fin_w, fin_h, C_FINAL, C_FINAL, r=0.3, lw=0, zorder=3)
t(fin_x + fin_w/2, fin_y + fin_h/2 + 0.25, "Step 07", fs=12, c=C_WHITE, bold=True)
t(fin_x + fin_w/2, fin_y + fin_h/2 - 0.15, "Optuna 튜닝", fs=10.5, c=C_WHITE)

# s6 LightGBM → Optuna
lgbm_y = s6_y0 + 4*(s6_bh + s6_gap) + s6_bh/2
arr(s6_x + s6_bw, lgbm_y, fin_x, fin_y + fin_h/2, lw=2.0, color=C_META, style="-|>")

# 최종 예측값 박스
rbox(19.2, 3.7, 2.1, 1.3, C_FINAL, C_FINAL, r=0.25, zorder=3)
t(20.25, 4.35, "최종\n예측값", fs=12, c=C_WHITE, bold=True)

arr(fin_x + fin_w, fin_y + fin_h/2, 19.2, 4.35, lw=2.5, color=C_META, style="-|>")

# ══════════════════════════════════════════════════════════════════════════════
# Test set (하단 점선)
# ══════════════════════════════════════════════════════════════════════════════
rbox(0.2, 0.5, 1.8, 0.72, "#555555", "#555555", r=0.2, zorder=3)
t(1.1, 0.86, "Test set", fs=10, c=C_WHITE, bold=True)

ax.annotate("", xy=(s6_x + s6_bw/2, 1.2), xytext=(2.0, 0.86),
    arrowprops=dict(arrowstyle="->", color="#888888", lw=1.5,
                    linestyle="dashed", mutation_scale=13), zorder=4)

rbox(s6_x - 0.2, 0.55, s6_bw + 0.4, 0.65, "#DCDDE1", "#BBBCC0", lw=1.2, r=0.2, zorder=3)
t(s6_x + s6_bw/2, 0.88, "각 모델로 예측 후 최적 모델 적용", fs=8.5, c=C_DARK)

# ══════════════════════════════════════════════════════════════════════════════
# 저장
# ══════════════════════════════════════════════════════════════════════════════
plt.tight_layout(pad=0.2)
plt.savefig("pipeline_diagram.png", dpi=180, bbox_inches="tight",
            facecolor=C_BG_OUTER, edgecolor="none")
plt.close()
print("저장 완료: pipeline_diagram.png")
