import sys, io, base64, json
sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import seaborn as sns
import warnings
warnings.filterwarnings('ignore')

DATA = 'c:/Users/USER/OneDrive/바탕 화면/AX/data/'

font_candidates = [f.name for f in fm.fontManager.ttflist if 'Malgun' in f.name]
FONT = font_candidates[0] if font_candidates else 'DejaVu Sans'
plt.rcParams['font.family'] = FONT
plt.rcParams['axes.unicode_minus'] = False
print('Font:', FONT)

BLUE   = '#2962a2'
ORANGE = '#f59e0b'
GREEN  = '#43a047'
RED    = '#e53935'
GRAY   = '#90a4ae'

mem = pd.read_csv(DATA + 'Membership.csv')
mem['reg_date']      = pd.to_datetime(mem['reg_date'])
mem['end_date']      = pd.to_datetime(mem['end_date'])
mem['duration_days'] = (mem['end_date'] - mem['reg_date']).dt.days

CHARTS = {}

def fig_to_b64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=120, bbox_inches='tight', facecolor='white')
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()

# ── 1. 결측치 비율 ──────────────────────────────────────────
fig, ax = plt.subplots(figsize=(12, 4))
miss = mem.isnull().sum().sort_values(ascending=False)
miss = miss[miss > 0]
colors = ['#e53935' if v/len(mem)>0.3 else '#f59e0b' if v/len(mem)>0.05 else '#43a047' for v in miss.values]
bars = ax.bar(miss.index, miss.values / len(mem) * 100, color=colors)
ax.set_title('결측치 비율 (%)', fontsize=14, fontweight='bold', pad=12)
ax.set_ylabel('%')
ax.set_ylim(0, 95)
for bar, val in zip(bars, miss.values):
    ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+0.5,
            f'{val:,}\n({val/len(mem)*100:.1f}%)', ha='center', va='bottom', fontsize=9)
ax.tick_params(axis='x', rotation=20)
ax.spines[['top','right']].set_visible(False)
plt.tight_layout()
CHARTS['missing'] = fig_to_b64(fig)
plt.close()
print('1. 결측치 완료')

# ── 2. amount 분포 ────────────────────────────────────────────
fig, axes = plt.subplots(1, 3, figsize=(18, 5))
top_amt = mem['amount'].value_counts().head(12).sort_index()
axes[0].bar(top_amt.index.astype(str), top_amt.values, color=BLUE)
axes[0].set_title('금액별 건수 (상위 12)', fontweight='bold')
axes[0].tick_params(axis='x', rotation=45)
axes[0].spines[['top','right']].set_visible(False)

axes[1].hist(mem['amount'], bins=40, color=BLUE, edgecolor='white', linewidth=0.5)
axes[1].set_title('amount 히스토그램', fontweight='bold')
axes[1].set_yscale('log')
axes[1].set_xlabel('금액')
axes[1].spines[['top','right']].set_visible(False)

axes[2].boxplot(mem['amount'].dropna(), vert=False, patch_artist=True,
                boxprops=dict(facecolor=BLUE, alpha=0.6),
                medianprops=dict(color='white', linewidth=2))
axes[2].set_title('amount 박스플롯', fontweight='bold')
axes[2].set_xlabel('금액')
axes[2].spines[['top','right']].set_visible(False)
plt.suptitle('amount (결제 금액)  ※ 원화/달러 혼재', fontsize=13, fontweight='bold', y=1.02)
plt.tight_layout()
CHARTS['amount'] = fig_to_b64(fig)
plt.close()
print('2. amount 완료')

# ── 3. age 분포 (950 이상값 제거, 단일 히스토그램) ──────────
AGE_MAX = 100
fig, ax = plt.subplots(figsize=(10, 5))
verified_clean = mem[(mem['is_user_verified']=='Y') & (mem['age'] <= AGE_MAX)]['age'].dropna()
all_clean      = mem[mem['age'] <= AGE_MAX]['age'].dropna()
n_outlier      = (mem['age'] > AGE_MAX).sum()

age_bins = np.arange(10, 106, 5) - 0.5  # 10, 15, 20, ..., 100 각 5세 간격
ax.hist(all_clean,      bins=age_bins, color=ORANGE, edgecolor='white', linewidth=0.5,
        label=f'전체 (≤{AGE_MAX}세, n={len(all_clean):,})', alpha=0.85)
ax.hist(verified_clean, bins=age_bins, color=BLUE,   edgecolor='white', linewidth=0.5,
        label=f'인증 고객 (n={len(verified_clean):,})', alpha=0.7)
ax.set_xticks(range(10, 105, 5))
ax.set_title(f'age 히스토그램  ※ {AGE_MAX}세 초과 {n_outlier}건 제외 (이상값)',
             fontweight='bold', fontsize=13)
ax.set_xlabel('연령')
ax.set_ylabel('건수')
ax.legend(fontsize=10)
ax.spines[['top','right']].set_visible(False)
plt.tight_layout()
CHARTS['age'] = fig_to_b64(fig)
plt.close()
print('3. age 완료')

# ── 4. concurrent_streams / reg_hour ─────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
sc = mem['concurrent_streams'].value_counts().sort_index()
bar_colors = [RED if idx == 3 else BLUE for idx in sc.index]
axes[0].bar(sc.index.astype(str), sc.values, color=bar_colors)
for i, (idx, val) in enumerate(zip(sc.index, sc.values)):
    label = f'{val:,}\n(!!)' if idx == 3 else f'{val:,}'
    axes[0].text(i, val+50, label, ha='center', fontsize=9,
                 color=RED if idx == 3 else 'black', fontweight='bold' if idx == 3 else 'normal')
axes[0].set_title('concurrent_streams 분포  ※ 3=7건 이상값', fontweight='bold')
axes[0].spines[['top','right']].set_visible(False)

hour_cnt = mem['reg_hour'].value_counts().sort_index()
colors_h = [RED if h in [0,1,2,3,22,23] else BLUE for h in hour_cnt.index]
axes[1].bar(hour_cnt.index, hour_cnt.values, color=colors_h)
axes[1].set_title('가입 시간대 (reg_hour)', fontweight='bold')
axes[1].set_xlabel('시간 (0~23)')
axes[1].spines[['top','right']].set_visible(False)
plt.tight_layout()
CHARTS['streams_hour'] = fig_to_b64(fig)
plt.close()
print('4. streams/hour 완료')

# ── 5. duration_days ─────────────────────────────────────────
fig, ax = plt.subplots(figsize=(10, 5))
ax.hist(mem['duration_days'], bins=35, color=ORANGE, edgecolor='white')
ax.axvline(0, color=RED, linestyle='--', linewidth=2, label='0일(당일해지)')
ax.set_title('duration_days 히스토그램', fontweight='bold')
ax.set_xlabel('지속 일수')
ax.set_ylabel('건수')
ax.legend()
ax.spines[['top','right']].set_visible(False)
plt.tight_layout()
CHARTS['duration'] = fig_to_b64(fig)
plt.close()
print('5. duration 완료')

# ── 6. 범주형 분포 ───────────────────────────────────────────
fig, axes = plt.subplots(2, 2, figsize=(16, 10))
cats = {
    'product_cd':     ('상품 코드',   axes[0][0]),
    'payment_device': ('결제 기기',   axes[0][1]),
    'billing_method': ('결제 수단',   axes[1][0]),
    'gender':         ('성별',        axes[1][1]),
}
for col, (title, ax) in cats.items():
    vc = mem[col].value_counts().head(10)
    ax.barh(vc.index.astype(str)[::-1], vc.values[::-1], color=BLUE)
    ax.set_title(title, fontweight='bold')
    ax.spines[['top','right']].set_visible(False)
    for i, v in enumerate(vc.values[::-1]):
        ax.text(v+10, i, f'{v:,}', va='center', fontsize=9)
plt.suptitle('범주형 변수 분포', fontsize=14, fontweight='bold')
plt.tight_layout()
CHARTS['categorical'] = fig_to_b64(fig)
plt.close()
print('6. 범주형 완료')

# ── 7. 타겟(repurchase) 분포 ─────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(12, 5))
labels_p = ['재결제(O)\n11,931 (65.6%)', '이탈(NaN)\n6,252 (34.4%)']
sizes_p  = [11931, 6252]
axes[0].pie(sizes_p, labels=labels_p, colors=[GREEN, RED], autopct='%1.1f%%',
            startangle=90, textprops={'fontsize':11},
            wedgeprops={'edgecolor':'white','linewidth':2})
axes[0].set_title('repurchase (타겟) 분포', fontweight='bold')

segs = {
    '전체':          mem,
    '프로모션 참여':  mem[mem['promotion_yn']=='O'],
    '프로모션 미참여':mem[mem['promotion_yn'].isna()],
    '해지방어':       mem[mem['is_churn_prevented']=='O'],
    '인증 고객':      mem[mem['is_user_verified']=='Y'],
}
seg_rates = {k: (v['repurchase']=='O').mean()*100 for k,v in segs.items()}
seg_colors = [BLUE, ORANGE, GRAY, RED, GREEN]
axes[1].barh(list(seg_rates.keys()), list(seg_rates.values()), color=seg_colors)
axes[1].set_xlim(0, 100)
axes[1].set_xlabel('재결제율 (%)')
axes[1].set_title('세그먼트별 재결제율', fontweight='bold')
for i, v in enumerate(seg_rates.values()):
    axes[1].text(v+0.5, i, f'{v:.1f}%', va='center', fontsize=10)
axes[1].spines[['top','right']].set_visible(False)
plt.tight_layout()
CHARTS['target'] = fig_to_b64(fig)
plt.close()
print('7. 타겟 완료')

# ── 8. 프로모션 세그먼트 ─────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
promo_y = mem[mem['promotion_yn']=='O']
promo_n = mem[mem['promotion_yn'].isna()]
for ax, col, title in [
    (axes[0], 'payment_device', '결제 기기별'),
    (axes[1], 'product_cd',     '상품별'),
]:
    top_items = mem[col].value_counts().head(6).index
    data_y = promo_y[col].value_counts().reindex(top_items, fill_value=0)
    data_n = promo_n[col].value_counts().reindex(top_items, fill_value=0)
    x = np.arange(len(top_items))
    w = 0.35
    ax.bar(x-w/2, data_y.values, w, label='프로모션 참여', color=ORANGE)
    ax.bar(x+w/2, data_n.values, w, label='미참여', color=BLUE)
    ax.set_xticks(x)
    ax.set_xticklabels(top_items, rotation=20, ha='right', fontsize=9)
    ax.set_title(f'프로모션 × {title}', fontweight='bold')
    ax.legend(fontsize=9)
    ax.spines[['top','right']].set_visible(False)
plt.tight_layout()
CHARTS['promo_seg'] = fig_to_b64(fig)
plt.close()
print('8. 프로모션 완료')

# ── 9. 해지방어 교차 ─────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
mem['churn_label'] = mem['is_churn_prevented'].fillna('미해당')
mem['promo_label'] = mem['promotion_yn'].fillna('미참여')
ct = pd.crosstab(mem['churn_label'], mem['promo_label'])
sns.heatmap(ct, annot=True, fmt='d', cmap='Blues', ax=axes[0],
            linewidths=0.5, cbar_kws={'shrink':0.8})
axes[0].set_title('해지방어 × 프로모션 교차', fontweight='bold')

churn_seg = {
    '해지방어(O)': (mem[mem['is_churn_prevented']=='O']['repurchase']=='O').mean()*100,
    '비해당(NaN)': (mem[mem['is_churn_prevented'].isna()]['repurchase']=='O').mean()*100,
}
axes[1].bar(list(churn_seg.keys()), list(churn_seg.values()), color=[RED, BLUE], width=0.4)
axes[1].set_ylim(0, 100)
axes[1].set_ylabel('재결제율 (%)')
axes[1].set_title('해지방어 여부별 재결제율', fontweight='bold')
for i, v in enumerate(churn_seg.values()):
    axes[1].text(i, v+1, f'{v:.1f}%', ha='center', fontsize=12, fontweight='bold')
axes[1].spines[['top','right']].set_visible(False)
plt.tight_layout()
CHARTS['churn_cross'] = fig_to_b64(fig)
plt.close()
print('9. 해지방어 완료')

# ── 10. 상품별 재결제율 ───────────────────────────────────────
fig, ax = plt.subplots(figsize=(12, 5))
top10 = mem['product_cd'].value_counts().head(10).index
prod_r = mem[mem['product_cd'].isin(top10)].groupby('product_cd').apply(
    lambda x: (x['repurchase']=='O').mean()*100).sort_values(ascending=False)
colors_p = [RED if v<50 else GREEN if v>70 else ORANGE for v in prod_r.values]
bars = ax.bar(prod_r.index, prod_r.values, color=colors_p)
ax.set_ylim(0, 100)
ax.axhline(65.6, color=GRAY, linestyle='--', linewidth=1.5, label='전체 평균 65.6%')
ax.set_ylabel('재결제율 (%)')
ax.set_title('상품별 재결제율 (상위 10개)', fontweight='bold')
for bar, val in zip(bars, prod_r.values):
    ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+0.5,
            f'{val:.1f}%', ha='center', fontsize=9)
ax.legend()
ax.spines[['top','right']].set_visible(False)
plt.tight_layout()
CHARTS['prod_repurchase'] = fig_to_b64(fig)
plt.close()
print('10. 상품별 재결제율 완료')

# ── 11. 상관관계 히트맵 ──────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(16, 6))
num_cols = ['amount', 'concurrent_streams', 'age', 'reg_hour', 'duration_days']
corr_all = mem[num_cols].corr()
corr_ver = mem[mem['is_user_verified']=='Y'][num_cols].corr()
for ax, corr, title in [
    (axes[0], corr_all, '전체 고객'),
    (axes[1], corr_ver, '인증 고객'),
]:
    mask = np.tril(np.ones_like(corr, dtype=bool))
    sns.heatmap(corr, annot=True, fmt='.2f', cmap='coolwarm', center=0,
                ax=ax, mask=~mask, square=True, linewidths=0.5,
                cbar_kws={'shrink':0.8}, vmin=-1, vmax=1)
    ax.set_title(f'상관관계 ({title})', fontweight='bold')
plt.suptitle('수치형 변수 상관관계  ※ billing_method 범주형 제외', fontsize=12)
plt.tight_layout()
CHARTS['corr'] = fig_to_b64(fig)
plt.close()
print('11. 상관관계 완료')

# ── 12. 일별/요일별 가입 패턴 ────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
daily = mem.groupby('reg_date').size()
axes[0].plot(daily.index, daily.values, color=BLUE, linewidth=1.5, marker='o', markersize=3)
axes[0].fill_between(daily.index, daily.values, alpha=0.15, color=BLUE)
axes[0].set_title('일별 가입 추이', fontweight='bold')
axes[0].tick_params(axis='x', rotation=20)
axes[0].spines[['top','right']].set_visible(False)

mem['reg_weekday'] = mem['reg_date'].dt.dayofweek
day_labels = ['월','화','수','목','금','토','일']
weekday_cnt = mem['reg_weekday'].value_counts().sort_index()
colors_w = [RED if i>=5 else BLUE for i in weekday_cnt.index]
axes[1].bar(day_labels, weekday_cnt.values, color=colors_w)
axes[1].axhline(weekday_cnt.mean(), color=GRAY, linestyle='--', linewidth=1.5,
                label=f'평균 {weekday_cnt.mean():.0f}건')
axes[1].set_title('요일별 가입 건수', fontweight='bold')
axes[1].legend(fontsize=9)
axes[1].spines[['top','right']].set_visible(False)
plt.tight_layout()
CHARTS['timeseries'] = fig_to_b64(fig)
plt.close()
print('12. 시계열 완료')

# ── 13. 금액 구간 × 재결제율 ─────────────────────────────────
fig, ax = plt.subplots(figsize=(10, 5))
bins2   = [0, 100, 1000, 7900, 10900, 16400]
labels2 = ['~100원', '101~1,000원', '1,001~7,900원', '7,901~10,900원', '10,901~16,400원']
mem['amt_group'] = pd.cut(mem['amount'], bins=bins2, labels=labels2, include_lowest=True)
grp = mem.groupby('amt_group', observed=True).apply(
    lambda x: (x['repurchase']=='O').mean()*100)
colors_g = [RED if v<50 else GREEN if v>70 else ORANGE for v in grp.values]
bars = ax.bar(grp.index, grp.values, color=colors_g)
ax.axhline(65.6, color=GRAY, linestyle='--', linewidth=1.5, label='전체 평균 65.6%')
ax.set_ylim(0, 100)
ax.set_ylabel('재결제율 (%)')
ax.set_title('금액 구간별 재결제율', fontweight='bold')
ax.tick_params(axis='x', rotation=10)
for bar, val in zip(bars, grp.values):
    ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+0.5,
            f'{val:.1f}%', ha='center', fontsize=10)
ax.legend()
ax.spines[['top','right']].set_visible(False)
plt.tight_layout()
CHARTS['amt_repurchase'] = fig_to_b64(fig)
plt.close()
print('13. 금액구간 완료')

# ══════════════════════════════════════════════════════════════
# 세그먼트 비교 함수 (전체/A/B 3패널 × 4변수)
# ══════════════════════════════════════════════════════════════
def seg_compare_chart(segs, num_vars, title, bins_map=None):
    """
    segs  : [('전체', df_all), ('라벨A', df_a), ('라벨B', df_b)]
    num_vars : [('컬럼명', 'x축 레이블'), ...]
    bins_map : {'컬럼명': bins} 히스토그램 bin 수 또는 리스트
    """
    nrow = len(num_vars)
    ncol = 3
    seg_colors = [BLUE, GREEN, RED]
    fig, axes = plt.subplots(nrow, ncol, figsize=(16, 4.2 * nrow))
    if nrow == 1:
        axes = [axes]

    for r, (col, xlabel) in enumerate(num_vars):
        for c, (label, df) in enumerate(segs):
            ax = axes[r][c]
            data = df[col].dropna()
            n    = len(data)
            bins = (bins_map or {}).get(col, 25)

            # discrete 여부 판단
            unique_vals = sorted(data.unique())
            if len(unique_vals) <= 10:
                vc = data.value_counts().sort_index()
                ax.bar(vc.index.astype(str), vc.values, color=seg_colors[c], alpha=0.85)
                for xi, vi in zip(range(len(vc)), vc.values):
                    ax.text(xi, vi + max(vc.values)*0.01, f'{vi:,}', ha='center', fontsize=8)
            else:
                ax.hist(data, bins=bins, color=seg_colors[c], edgecolor='white',
                        linewidth=0.4, alpha=0.85)

            if pd.api.types.is_numeric_dtype(data):
                mean_v = data.mean()
                ax.axvline(mean_v, color='black', linestyle='--', linewidth=1.2,
                           label=f'평균 {mean_v:.1f}')
                ax.legend(fontsize=8, handlelength=1)
            ax.set_title(f'{label}  (n={n:,})', fontweight='bold', fontsize=11)
            if c == 0:
                ax.set_ylabel(col, fontsize=10)
            ax.set_xlabel(xlabel, fontsize=9)
            ax.spines[['top','right']].set_visible(False)

    plt.suptitle(title, fontsize=14, fontweight='bold', y=1.01)
    plt.tight_layout()
    return fig

# amount 제외, age는 100세 이하만 사용하는 세그먼트 비교용 데이터
mem_seg = mem.copy()
mem_seg.loc[mem_seg['age'] > 100, 'age'] = np.nan  # 950 등 이상값 NaN 처리

NUM_VARS = [
    ('age',                '연령'),
    ('concurrent_streams', '동시 시청 수'),
    ('gender',             '성별'),
]
AGE_BINS_SEG = np.arange(10, 106, 5) - 0.5  # 10~100 5세 간격
BINS = {'age': AGE_BINS_SEG, 'concurrent_streams': 4}

# ── 14. 인증 여부 세그먼트 ───────────────────────────────────
seg_v = [
    ('전체',      mem_seg),
    ('인증(Y)',   mem_seg[mem_seg['is_user_verified'] == 'Y']),
    ('미인증(N)', mem_seg[mem_seg['is_user_verified'] == 'N']),
]
fig = seg_compare_chart(seg_v, NUM_VARS, '인증 여부 세그먼트 비교 (전체 / 인증Y / 미인증N)', BINS)
CHARTS['seg_verified'] = fig_to_b64(fig)
plt.close()
print('14. 인증 세그먼트 완료')

# ── 15. 프로모션 세그먼트 ───────────────────────────────────
seg_p = [
    ('전체',             mem_seg),
    ('프로모션 참여(O)',  mem_seg[mem_seg['promotion_yn'] == 'O']),
    ('미참여(NaN)',       mem_seg[mem_seg['promotion_yn'].isna()]),
]
fig = seg_compare_chart(seg_p, NUM_VARS, '프로모션 여부 세그먼트 비교 (전체 / 참여 / 미참여)', BINS)
CHARTS['seg_promo'] = fig_to_b64(fig)
plt.close()
print('15. 프로모션 세그먼트 완료')

# ── 16. 재결제 세그먼트 ─────────────────────────────────────
seg_r = [
    ('전체',              mem_seg),
    ('재결제(O)',          mem_seg[mem_seg['repurchase'] == 'O']),
    ('미재결제(NaN=이탈)', mem_seg[mem_seg['repurchase'].isna()]),
]
fig = seg_compare_chart(seg_r, NUM_VARS, '재결제 여부 세그먼트 비교 (전체 / 재결제 / 이탈)', BINS)
CHARTS['seg_repurchase'] = fig_to_b64(fig)
plt.close()
print('16. 재결제 세그먼트 완료')

# ── 17. 요일×시간대 히트맵 ──────────────────────────────────
fig, ax = plt.subplots(figsize=(14, 5))
mem['reg_weekday'] = mem['reg_date'].dt.dayofweek
hmap = mem.groupby(['reg_weekday', 'reg_hour']).size().unstack(fill_value=0)
hmap.index = ['월','화','수','목','금','토','일']
sns.heatmap(hmap, cmap='Blues', ax=ax, linewidths=0.3,
            cbar_kws={'label':'건수', 'shrink':0.8})
ax.set_title('가입 시간대 × 요일 히트맵', fontweight='bold', fontsize=13)
ax.set_xlabel('가입 시간 (0~23시)')
ax.set_ylabel('요일')
plt.tight_layout()
CHARTS['hour_weekday_heatmap'] = fig_to_b64(fig)
plt.close()
print('17. 시간×요일 히트맵 완료')

# ── 18. 성별×연령대 히트맵 — 전체/재결제/이탈 3패널 ──────────
vf_base = mem[(mem['is_user_verified']=='Y') &
              mem['gender'].isin(['F','M']) &
              (mem['age'] <= 100)].copy()
vf_base['age_bin'] = (vf_base['age'] // 5 * 5).astype(int)

seg_ga = [
    ('전체 (인증 고객)',    vf_base),
    ('재결제(O)',           vf_base[vf_base['repurchase'] == 'O']),
    ('미재결제=이탈(NaN)',  vf_base[vf_base['repurchase'].isna()]),
]

fig, axes = plt.subplots(1, 3, figsize=(20, 4))
for ax, (label, df) in zip(axes, seg_ga):
    ga = df.groupby(['gender','age_bin']).size().unstack(fill_value=0)
    sns.heatmap(ga, annot=True, fmt='d', cmap='Blues', ax=ax,
                linewidths=0.5, cbar_kws={'shrink':0.7})
    ax.set_title(f'{label}\n(n={len(df):,})', fontweight='bold', fontsize=11)
    ax.set_xlabel('연령대')
    ax.set_ylabel('성별')
plt.suptitle('성별 × 연령대 교차표 — 세그먼트 비교 (인증 고객, ≤100세)',
             fontsize=13, fontweight='bold', y=1.02)
plt.tight_layout()
CHARTS['gender_age_heatmap'] = fig_to_b64(fig)
plt.close()
print('18. 성별×연령대 히트맵 완료')

# ── 19. View_History EDA ─────────────────────────────────────
try:
    vh = pd.read_csv(DATA + 'View_History.csv')
    vh['WATCH_DAY'] = pd.to_datetime(vh['WATCH_DAY'])

    fig, axes = plt.subplots(2, 2, figsize=(16, 10))

    # (1) DURATION 분포 (히스토그램)
    ax = axes[0][0]
    cap_val = 200
    under_cap = vh[vh['DURATION'] < cap_val]['DURATION']
    capped    = vh[vh['DURATION'] >= cap_val]
    ax.hist(under_cap, bins=40, color=BLUE, edgecolor='white', linewidth=0.4, alpha=0.85,
            label=f'<{cap_val}분 (n={len(under_cap):,})')
    ax.axvline(cap_val, color=RED, linestyle='--', linewidth=1.5,
               label=f'캡핑값 {cap_val}분 (n={len(capped):,}건)')
    ax.set_title('시청 시간(DURATION) 분포', fontweight='bold')
    ax.set_xlabel('시청 시간 (분)')
    ax.set_ylabel('건수')
    ax.legend(fontsize=9)
    ax.spines[['top','right']].set_visible(False)

    # (2) 일별 시청 건수 추이
    ax = axes[0][1]
    daily_vh = vh.groupby('WATCH_DAY').size()
    ax.plot(daily_vh.index, daily_vh.values, color=ORANGE, linewidth=1.5, marker='o', markersize=3)
    ax.fill_between(daily_vh.index, daily_vh.values, alpha=0.15, color=ORANGE)
    ax.set_title('일별 시청 건수 추이', fontweight='bold')
    ax.tick_params(axis='x', rotation=20)
    ax.spines[['top','right']].set_visible(False)

    # (3) 유저별 시청 건수 분포 (상위 99퍼센타일까지)
    ax = axes[1][0]
    user_cnt = vh.groupby('USER_ID').size()
    p99 = user_cnt.quantile(0.99)
    int_bins = np.arange(0, int(p99) + 2) - 0.5  # 정수 단위 bin
    ax.hist(user_cnt[user_cnt <= p99], bins=int_bins, color=GREEN, edgecolor='white', linewidth=0.4, alpha=0.85)
    ax.axvline(user_cnt.mean(), color=RED, linestyle='--', linewidth=1.5,
               label=f'평균 {user_cnt.mean():.1f}건')
    ax.set_title(f'유저별 시청 건수 분포 (≤ p99={p99:.0f}건)', fontweight='bold')
    ax.set_xlabel('시청 건수')
    ax.set_ylabel('유저 수')
    ax.legend(fontsize=9)
    ax.spines[['top','right']].set_visible(False)

    # (4) WATCH_SEQ 분포 (분할 시청)
    ax = axes[1][1]
    seq_cnt = vh['WATCH_SEQ'].value_counts().sort_index().head(10)
    ax.bar(seq_cnt.index.astype(str), seq_cnt.values, color=BLUE, edgecolor='white')
    ax.set_title('WATCH_SEQ 분포 (분할 시청 횟수, 상위 10)', fontweight='bold')
    ax.set_xlabel('WATCH_SEQ')
    ax.set_ylabel('건수')
    ax.spines[['top','right']].set_visible(False)
    for i, v in enumerate(seq_cnt.values):
        ax.text(i, v + max(seq_cnt.values)*0.01, f'{v:,}', ha='center', fontsize=8)

    plt.suptitle('View_History EDA  (시청 이력 분석)', fontsize=14, fontweight='bold', y=1.01)
    plt.tight_layout()
    CHARTS['view_history'] = fig_to_b64(fig)
    plt.close()
    print('19. View_History EDA 완료')
except Exception as e:
    print(f'19. View_History EDA 건너뜀: {e}')

# ── 20. View_History 세그먼트 비교 ───────────────────────────
try:
    vh = pd.read_csv(DATA + 'View_History.csv')
    um = pd.read_csv(DATA + 'User_Mapping.csv')

    # 유저별 집계
    user_stats = vh.groupby('USER_ID').agg(
        total_count  = ('MOVIE_ID', 'count'),
        total_dur    = ('DURATION', 'sum'),
        unique_movies= ('MOVIE_ID', 'nunique'),
        watch_days   = ('WATCH_DAY', 'nunique'),
    ).reset_index()

    # Membership 조인 (USER_ID → uid → user_no → Membership)
    mem_tmp = mem[['user_no', 'is_user_verified', 'repurchase']].drop_duplicates('user_no')
    merged = user_stats.merge(
        um[['USER_ID', 'uid']], on='USER_ID', how='left'
    ).merge(mem_tmp, left_on='uid', right_on='user_no', how='left')

    # 세그먼트 정의
    seg_verified = [
        ('\uc804\uccb4',      merged),
        ('\uc778\uc99d(Y)',   merged[merged['is_user_verified'] == 'Y']),
        ('\ubbf8\uc778\uc99d(N)', merged[merged['is_user_verified'] == 'N']),
    ]
    seg_repurchase = [
        ('\uc804\uccb4',                 merged),
        ('\uc7ac\uacb0\uc81c(O)',         merged[merged['repurchase'] == 'O']),
        ('\uc774\ud0c8(NaN)',             merged[merged['repurchase'].isna()]),
    ]

    WATCH_VARS = [
        ('total_count',   '\uc2dc\uccad \uac74\uc218'),
        ('total_dur',     '\uc2dc\uccad \uc2dc\uac04(\ubd84)'),
        ('unique_movies', '\uc2dc\uccad \uc601\ud654 \uc218'),
        ('watch_days',    '\uc2dc\uccad \uc77c\uc218'),
    ]

    INT_FEATS = {'total_count', 'unique_movies', 'watch_days'}

    def get_watch_bins(vals_all, col):
        lo = vals_all.min()
        hi = vals_all.quantile(0.99)
        if col in INT_FEATS:
            return np.arange(int(lo), int(hi) + 2) - 0.5
        return np.linspace(lo, hi, 31)

    seg_colors = [BLUE, GREEN, RED]

    for seg_label, segs in [('\uc778\uc99d \uc5ec\ubd80', seg_verified),
                             ('\uc7ac\uacb0\uc81c \uc5ec\ubd80', seg_repurchase)]:
        nrow = len(WATCH_VARS)
        fig, axes = plt.subplots(nrow, 3, figsize=(16, 4.2 * nrow))

        for r, (col, xlabel) in enumerate(WATCH_VARS):
            vals_all = merged[col].dropna()
            bins = get_watch_bins(vals_all, col)

            for c, (label, df) in enumerate(segs):
                ax = axes[r][c]
                data = df[col].dropna()
                clip_hi = vals_all.quantile(0.99)
                data_clip = data[data <= clip_hi]

                ax.hist(data_clip, bins=bins, color=seg_colors[c],
                        edgecolor='white', linewidth=0.4, alpha=0.85)
                mean_v = data.mean()
                ax.axvline(mean_v, color='black', linestyle='--', linewidth=1.2,
                           label=f'\ud3c9\uade0 {mean_v:.1f}')
                ax.legend(fontsize=8, handlelength=1)
                ax.set_title(f'{label}  (n={len(data):,})', fontweight='bold', fontsize=11)
                if c == 0:
                    ax.set_ylabel(col, fontsize=10)
                ax.set_xlabel(xlabel, fontsize=9)
                ax.spines[['top', 'right']].set_visible(False)

        plt.suptitle(f'View_History \uc138\uadf8\uba3c\ud2b8 \ube44\uad50 \u2014 {seg_label}',
                     fontsize=14, fontweight='bold', y=1.01)
        plt.tight_layout()

        key = 'vh_seg_verified' if seg_label == '\uc778\uc99d \uc5ec\ubd80' else 'vh_seg_repurchase'
        CHARTS[key] = fig_to_b64(fig)
        plt.close()
        print(f'20. View_History {seg_label} \uc138\uadf8\uba3c\ud2b8 \uc644\ub8cc')

except Exception as e:
    import traceback; traceback.print_exc()
    print(f'20. View_History \uc138\uadf8\uba3c\ud2b8 \uac74\ub108\ub681: {e}')

# ── 저장 ─────────────────────────────────────────────────────
OUT = 'c:/Users/USER/OneDrive/바탕 화면/AX/EDA/charts_b64.json'
with open(OUT, 'w') as f:
    json.dump(CHARTS, f)
print(f'\n차트 {len(CHARTS)}개 생성 완료 -> {OUT}')
