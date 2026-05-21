import sys, io, base64
sys.stdout.reconfigure(encoding='utf-8')

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
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

# ── 데이터 로드 ────────────────────────────────────────────────────────────
mem_raw = pd.read_csv(DATA + 'Membership.csv')
um      = pd.read_csv(DATA + 'User_Mapping.csv')
vh      = pd.read_csv(DATA + 'View_History.csv')

mem_raw['reg_date']      = pd.to_datetime(mem_raw['reg_date'])
mem_raw['end_date']      = pd.to_datetime(mem_raw['end_date'])
mem_raw['duration_days'] = (mem_raw['end_date'] - mem_raw['reg_date']).dt.days

mem = mem_raw.copy()
print(f'로드 완료: Membership {mem.shape}, User_Mapping {um.shape}, View_History {vh.shape}')

# ── 유틸 ──────────────────────────────────────────────────────────────────
CHARTS = {}

def fig_to_b64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=120, bbox_inches='tight', facecolor='white')
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()

def spines_off(ax):
    ax.spines[['top', 'right']].set_visible(False)

# ════════════════════════════════════════════════════════════════════════════
# 차트 1. 전처리 전 결측치 현황
# ════════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(11, 4))
miss = mem.isnull().sum().sort_values(ascending=False)
miss = miss[miss > 0]
colors_miss = [RED if v/len(mem) > 0.3 else ORANGE if v/len(mem) > 0.05 else GREEN
               for v in miss.values]
bars = ax.bar(miss.index, miss.values / len(mem) * 100, color=colors_miss)
ax.set_title('전처리 전 결측치 비율 (%)', fontsize=13, fontweight='bold', pad=10)
ax.set_ylabel('%')
ax.set_ylim(0, 95)
for bar, val in zip(bars, miss.values):
    ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+0.5,
            f'{val:,}\n({val/len(mem)*100:.1f}%)', ha='center', va='bottom', fontsize=8)
ax.tick_params(axis='x', rotation=20)
spines_off(ax)
plt.tight_layout()
CHARTS['missing_before'] = fig_to_b64(fig)
plt.close()
print('1. missing_before 완료')

# ════════════════════════════════════════════════════════════════════════════
# 전처리 수행 (HTML 수치 계산용)
# ════════════════════════════════════════════════════════════════════════════

# 필수 1: 중복 제거
n_before_dup = len(mem)
n_dup_rows   = mem.duplicated('user_no', keep=False).sum()
n_dup_users  = mem[mem.duplicated('user_no', keep=False)]['user_no'].nunique()
mem = (mem.sort_values('duration_days', ascending=False, na_position='last')
          .drop_duplicates(subset='user_no', keep='first')
          .reset_index(drop=True))
n_after_dup = len(mem)

# 필수 2: 타겟 인코딩
for col in ['repurchase', 'promotion_yn', 'is_churn_prevented']:
    mem[col] = mem[col].map({'O': 1}).fillna(0).astype(int)

# 필수 3: 통화 통일
USD_PRODUCTS = {'pk_1506', 'pk_1507', 'pk_1508'}
USD_TO_KRW   = 1144
usd_mask = mem['product_cd'].isin(USD_PRODUCTS) & (mem['amount'] != 100)
n_usd = usd_mask.sum()
amount_before_max = mem.loc[usd_mask, 'amount'].max()
mem.loc[usd_mask, 'amount'] = (mem.loc[usd_mask, 'amount'] * USD_TO_KRW).round().astype(int)

# 필수 4: is_user_verified
mem['is_user_verified'] = mem['is_user_verified'].fillna('N')
mem['is_verified']      = (mem['is_user_verified'] == 'Y').astype(int)

# 필수 5: concurrent_streams
n_cs3  = (mem['concurrent_streams'] == 3).sum()
n_csna = mem['concurrent_streams'].isna().sum()
n_before_cs = len(mem)
mem = mem[mem['concurrent_streams'] != 3].dropna(subset=['concurrent_streams'])
mem['concurrent_streams'] = mem['concurrent_streams'].astype(int)
mem = mem.reset_index(drop=True)
n_after_cs = len(mem)

# 권장 1: age
n_age_out = (mem['age'] > 100).sum()
n_age_na  = mem['age'].isna().sum()
age_before = mem['age'].copy()
mem.loc[mem['age'] > 100, 'age'] = np.nan
valid_ages = mem['age'].dropna().astype(int)
age_dist   = valid_ages.value_counts(normalize=True).sort_index()
null_idx   = mem[mem['age'].isna()].index
np.random.seed(42)
mem.loc[null_idx, 'age'] = np.random.choice(age_dist.index, size=len(null_idx), p=age_dist.values)
mem['age'] = mem['age'].astype(int)

# 권장 2: billing_group
def billing_group(val):
    if pd.isna(val): return '기타'
    s = str(int(val))
    if s.startswith('13'): return '국내카드'
    if s == '151':         return '간편결제'
    if s == '140':         return 'iOS'
    if s.startswith('18'): return '모바일'
    return '기타'

mem['billing_group'] = mem['billing_method'].apply(billing_group)

# 권장 3: gender
gender_before = mem['gender'].copy()
n_gN  = (mem['gender'] == 'N').sum()
n_gna = mem['gender'].isna().sum()
mem['gender'] = mem['gender'].replace('N', np.nan)
fm_dist    = mem['gender'].value_counts(normalize=True)
null_idx_g = mem[mem['gender'].isna()].index
np.random.seed(42)
mem.loc[null_idx_g, 'gender'] = np.random.choice(fm_dist.index, size=len(null_idx_g), p=fm_dist.values)

# 파생 피처
plan_map = {
    'pk_1487': 'basic',    'pk_2025': 'basic',    'pk_1508': 'basic',
    'pk_1488': 'standard', 'pk_2026': 'standard', 'pk_1506': 'standard',
    'pk_1489': 'premium',  'pk_2027': 'premium',  'pk_1507': 'premium',
}
mem['plan_tier']            = mem['product_cd'].map(plan_map).fillna('기타')
mem['currency_type']        = mem['product_cd'].apply(lambda x: 'USD' if x in USD_PRODUCTS else 'KRW')
mem['is_promotional_price'] = (mem['amount'] == 100).astype(int)
mem['is_night_signup']      = mem['reg_hour'].isin([22, 23, 0, 1, 2, 3]).astype(int)
mem['reg_weekday']          = mem['reg_date'].dt.dayofweek
mem['is_same_day_cancel']   = (mem['duration_days'] == 0).astype(int)
mem['age_group']            = (mem['age'] // 10 * 10).astype(int)

# View_History 집계
vh_agg = (
    vh.groupby('USER_ID')
      .agg(total_watch_count    = ('MOVIE_ID',  'count'),
           total_watch_duration = ('DURATION',  'sum'),
           unique_movies        = ('MOVIE_ID',  'nunique'),
           avg_duration         = ('DURATION',  'mean'),
           watch_days_count     = ('WATCH_DAY', 'nunique'))
      .reset_index()
)
vh_agg = vh_agg.merge(um[['USER_ID', 'uid']], on='USER_ID', how='left')
vh_cols = ['uid', 'total_watch_count', 'total_watch_duration',
           'unique_movies', 'avg_duration', 'watch_days_count']
mem = mem.merge(vh_agg[vh_cols], left_on='user_no', right_on='uid', how='left')
mem.drop(columns=['uid'], inplace=True)
mem['has_watch_history'] = mem['total_watch_count'].notna().astype(int)
for c in ['total_watch_count', 'total_watch_duration', 'unique_movies', 'avg_duration', 'watch_days_count']:
    mem[c] = mem[c].fillna(0)

print('전처리 완료')

# ════════════════════════════════════════════════════════════════════════════
# 차트 2. 타겟 분포 (전처리 후)
# ════════════════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(1, 2, figsize=(11, 5))
fig.suptitle('타겟 변수(repurchase) 분포 — 전처리 후', fontsize=13, fontweight='bold')
vc     = mem['repurchase'].value_counts()
vals   = [vc.get(1, 0), vc.get(0, 0)]
labels = ['재결제(1)', '이탈(0)']
axes[0].pie(vals, labels=labels, colors=[BLUE, RED], autopct='%1.1f%%',
            startangle=90, wedgeprops=dict(edgecolor='white', linewidth=2))
axes[0].set_title(f'전체 {len(mem):,}건')
bars = axes[1].bar(labels, vals, color=[BLUE, RED], edgecolor='white')
for bar, v in zip(bars, vals):
    axes[1].text(bar.get_x()+bar.get_width()/2, bar.get_height()+30,
                 f'{v:,}건', ha='center', va='bottom', fontsize=11)
axes[1].set_ylabel('건수')
spines_off(axes[1])
plt.tight_layout()
CHARTS['target_after'] = fig_to_b64(fig)
plt.close()
print('2. target_after 완료')

# ════════════════════════════════════════════════════════════════════════════
# 차트 3. amount 분포 (KRW 통일 후)
# ════════════════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(1, 2, figsize=(13, 5))
fig.suptitle('결제 금액 분포 — KRW 통일 후', fontsize=13, fontweight='bold')
axes[0].hist(mem['amount'], bins=50, color=BLUE, edgecolor='white', alpha=0.85)
axes[0].set_xlabel('amount (원)')
axes[0].set_ylabel('건수')
axes[0].set_title('전체 분포')
axes[0].xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f'{int(x):,}'))
axes[0].tick_params(axis='x', rotation=20)
spines_off(axes[0])
top_amt = mem['amount'].value_counts().head(10).sort_index()
bars = axes[1].bar(range(len(top_amt)), top_amt.values, color=ORANGE, edgecolor='white')
axes[1].set_xticks(range(len(top_amt)))
axes[1].set_xticklabels([f'{int(x):,}' for x in top_amt.index], rotation=35, ha='right')
for bar, v in zip(bars, top_amt.values):
    axes[1].text(bar.get_x()+bar.get_width()/2, bar.get_height()+10,
                 f'{v:,}', ha='center', va='bottom', fontsize=9)
axes[1].set_xlabel('amount (원)')
axes[1].set_ylabel('건수')
axes[1].set_title('주요 금액 Top 10')
spines_off(axes[1])
plt.tight_layout()
CHARTS['amount_after'] = fig_to_b64(fig)
plt.close()
print('3. amount_after 완료')

# ════════════════════════════════════════════════════════════════════════════
# 차트 4. age 분포 — 전처리 전후 비교
# ════════════════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(1, 2, figsize=(13, 5))
fig.suptitle('연령 분포 — 전처리 전후 비교 (5세 구간)', fontsize=13, fontweight='bold')
age_bins = np.arange(10, 106, 5) - 0.5
before_clean = mem_raw['age'].dropna()
before_clean = before_clean[before_clean <= 100]
axes[0].hist(before_clean, bins=age_bins, color=GRAY, edgecolor='white', alpha=0.85)
axes[0].set_xlabel('나이')
axes[0].set_ylabel('건수')
axes[0].set_title('처리 전 (≤100세, NaN 제외)')
axes[0].set_xticks(range(10, 105, 5))
axes[0].tick_params(axis='x', rotation=45)
spines_off(axes[0])
axes[1].hist(mem['age'], bins=age_bins, color=BLUE, edgecolor='white', alpha=0.85)
axes[1].set_xlabel('나이')
axes[1].set_ylabel('건수')
axes[1].set_title('처리 후 (이상값 → 비율 대체)')
axes[1].set_xticks(range(10, 105, 5))
axes[1].tick_params(axis='x', rotation=45)
spines_off(axes[1])
plt.tight_layout()
CHARTS['age_compare'] = fig_to_b64(fig)
plt.close()
print('4. age_compare 완료')

# ════════════════════════════════════════════════════════════════════════════
# 차트 5. 그룹별 재결제율 (plan_tier / billing_group / currency / gender)
# ════════════════════════════════════════════════════════════════════════════
groups = [
    ('plan_tier',    '플랜 Tier',  ['basic', 'standard', 'premium', '기타']),
    ('billing_group','결제 방법',  ['국내카드', '간편결제', 'iOS', '모바일', '기타']),
    ('currency_type','통화',       ['KRW', 'USD']),
    ('gender',       '성별',       ['F', 'M']),
]
fig, axes = plt.subplots(1, 4, figsize=(18, 5))
fig.suptitle('그룹별 재결제율', fontsize=13, fontweight='bold')
avg = mem['repurchase'].mean() * 100
for ax, (col, title, order) in zip(axes, groups):
    existing = [x for x in order if x in mem[col].unique()]
    rates    = mem.groupby(col)['repurchase'].mean().reindex(existing) * 100
    counts   = mem[col].value_counts().reindex(existing)
    bars = ax.bar(existing, rates.values, color=BLUE, edgecolor='white', alpha=0.85)
    ax.axhline(avg, color=RED, linestyle='--', linewidth=1.5, label=f'평균 {avg:.1f}%')
    for bar, v, cnt in zip(bars, rates.values, counts.values):
        ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+0.5,
                f'{v:.1f}%\n({cnt:,})', ha='center', va='bottom', fontsize=9)
    ax.set_ylim(0, 100)
    ax.set_title(title, fontweight='bold')
    ax.set_ylabel('재결제율 (%)')
    ax.legend(fontsize=8)
    spines_off(ax)
    ax.tick_params(axis='x', rotation=15)
plt.tight_layout()
CHARTS['group_repurchase'] = fig_to_b64(fig)
plt.close()
print('5. group_repurchase 완료')

# ════════════════════════════════════════════════════════════════════════════
# 차트 6. 이진 파생 피처별 재결제율
# ════════════════════════════════════════════════════════════════════════════
binary_feats = [
    ('is_verified',          '인증 여부'),
    ('promotion_yn',         '프로모션 참여'),
    ('is_churn_prevented',   '해지방어'),
    ('is_promotional_price', '프로모션 가격'),
    ('is_night_signup',      '야간 가입'),
    ('is_same_day_cancel',   '당일 해지'),
    ('has_watch_history',    '시청이력 보유'),
]
fig, axes = plt.subplots(2, 4, figsize=(18, 9))
fig.suptitle('이진 파생 피처별 재결제율', fontsize=13, fontweight='bold')
axes_flat = axes.flatten()
for i, (col, title) in enumerate(binary_feats):
    ax     = axes_flat[i]
    rates  = mem.groupby(col)['repurchase'].mean() * 100
    counts = mem[col].value_counts()
    yvals  = [rates.get(0, 0), rates.get(1, 0)]
    cnts   = [counts.get(0, 0), counts.get(1, 0)]
    bars = ax.bar(['없음(0)', '있음(1)'], yvals, color=[GRAY, BLUE], edgecolor='white')
    ax.axhline(avg, color=RED, linestyle='--', linewidth=1.2, alpha=0.7)
    for bar, v, cnt in zip(bars, yvals, cnts):
        ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+0.5,
                f'{v:.1f}%\n({cnt:,})', ha='center', va='bottom', fontsize=9)
    ax.set_ylim(0, 110)
    ax.set_title(title, fontweight='bold')
    ax.set_ylabel('재결제율 (%)')
    spines_off(ax)
axes_flat[-1].set_visible(False)
plt.tight_layout()
CHARTS['binary_repurchase'] = fig_to_b64(fig)
plt.close()
print('6. binary_repurchase 완료')

# ════════════════════════════════════════════════════════════════════════════
# 차트 7. 연령대별 재결제율 & duration_days
# ════════════════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(1, 2, figsize=(13, 5))
fig.suptitle('연령대 & duration_days × 재결제율', fontsize=13, fontweight='bold')
ag = mem.groupby('age_group')['repurchase'].agg(['mean', 'count'])
ag['mean'] *= 100
bars = axes[0].bar(ag.index, ag['mean'], color=ORANGE, edgecolor='white', alpha=0.85, width=7)
axes[0].axhline(avg, color=RED, linestyle='--', linewidth=1.5, label=f'평균 {avg:.1f}%')
for bar, (idx, row) in zip(bars, ag.iterrows()):
    axes[0].text(bar.get_x()+bar.get_width()/2, bar.get_height()+0.5,
                 f'{row["mean"]:.1f}%', ha='center', va='bottom', fontsize=9)
axes[0].set_xticks(ag.index)
axes[0].set_xticklabels([f'{x}대' for x in ag.index])
axes[0].set_ylim(0, 100)
axes[0].set_ylabel('재결제율 (%)')
axes[0].set_title('연령대별 재결제율')
axes[0].legend(fontsize=9)
spines_off(axes[0])
for v, color, label in [(1, BLUE, '재결제'), (0, RED, '이탈')]:
    sub = mem[mem['repurchase'] == v]['duration_days']
    axes[1].hist(sub, bins=35, color=color, alpha=0.6,
                 label=f'{label} ({len(sub):,}건)', edgecolor='white')
axes[1].set_xlabel('지속 일수')
axes[1].set_ylabel('건수')
axes[1].set_title('재결제 여부별 duration_days')
axes[1].legend()
spines_off(axes[1])
plt.tight_layout()
CHARTS['age_duration'] = fig_to_b64(fig)
plt.close()
print('7. age_duration 완료')

# ════════════════════════════════════════════════════════════════════════════
# 차트 8. 상관관계 히트맵
# ════════════════════════════════════════════════════════════════════════════
num_cols = ['repurchase', 'duration_days', 'amount', 'age', 'concurrent_streams',
            'reg_hour', 'reg_weekday', 'is_verified', 'promotion_yn', 'is_churn_prevented',
            'is_promotional_price', 'is_night_signup', 'is_same_day_cancel',
            'total_watch_count', 'total_watch_duration', 'unique_movies',
            'avg_duration', 'watch_days_count', 'has_watch_history']
num_cols = [c for c in num_cols if c in mem.columns]
corr = mem[num_cols].corr()
fig, ax = plt.subplots(figsize=(14, 11))
mask = np.triu(np.ones_like(corr, dtype=bool))
sns.heatmap(corr, mask=mask, annot=True, fmt='.2f', cmap='RdBu_r',
            center=0, vmin=-1, vmax=1, linewidths=0.4, ax=ax, annot_kws={'size': 8})
ax.set_title('수치형 피처 상관관계 (전처리 후)', fontsize=13, fontweight='bold')
plt.tight_layout()
CHARTS['corr_heatmap'] = fig_to_b64(fig)
plt.close()
print('8. corr_heatmap 완료')

# ════════════════════════════════════════════════════════════════════════════
# 차트 9. View_History 집계 피처 × 재결제율
# ════════════════════════════════════════════════════════════════════════════
vh_users = mem[mem['has_watch_history'] == 1]
vh_feats = [
    ('total_watch_count',    '총 시청 횟수'),
    ('total_watch_duration', '총 시청 시간(분)'),
    ('unique_movies',        '시청 영화 수'),
    ('avg_duration',         '평균 시청 시간(분)'),
    ('watch_days_count',     '시청 일수'),
]
fig, axes = plt.subplots(2, 3, figsize=(16, 9))
fig.suptitle('View_History 집계 피처 분포 (시청이력 보유 유저)', fontsize=13, fontweight='bold')
ax_flat = axes.flatten()
for i, (col, title) in enumerate(vh_feats):
    ax  = ax_flat[i]
    p99 = vh_users[col].quantile(0.99)
    for v, color, label in [(1, BLUE, '재결제'), (0, RED, '이탈')]:
        sub = vh_users[vh_users['repurchase'] == v][col]
        ax.hist(sub[sub <= p99], bins=30, color=color, alpha=0.6,
                label=f'{label} ({len(sub):,})', edgecolor='white')
    ax.set_title(title)
    ax.set_xlabel(title)
    ax.set_ylabel('건수')
    ax.legend(fontsize=8)
    spines_off(ax)
ax = ax_flat[5]
rates  = mem.groupby('has_watch_history')['repurchase'].mean() * 100
counts = mem['has_watch_history'].value_counts()
bars   = ax.bar(['없음(0)', '있음(1)'],
                [rates.get(0, 0), rates.get(1, 0)],
                color=[GRAY, GREEN], edgecolor='white')
ax.axhline(avg, color=RED, linestyle='--', linewidth=1.5, label=f'평균 {avg:.1f}%')
for bar, k in zip(bars, [0, 1]):
    ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+0.5,
            f'{rates.get(k,0):.1f}%\n({counts.get(k,0):,})',
            ha='center', va='bottom', fontsize=10)
ax.set_ylim(0, 100)
ax.set_title('시청이력 유무 × 재결제율')
ax.set_ylabel('재결제율 (%)')
ax.legend(fontsize=9)
spines_off(ax)
plt.tight_layout()
CHARTS['vh_features'] = fig_to_b64(fig)
plt.close()
print('9. vh_features 완료')

print(f'\n차트 생성 완료: {len(CHARTS)}개')

# ════════════════════════════════════════════════════════════════════════════
# 최종 수치 계산
# ════════════════════════════════════════════════════════════════════════════
n_final   = len(mem)
n_removed = len(mem_raw) - n_final
repurchase_rate = mem['repurchase'].mean() * 100

target_corr = (
    corr['repurchase'].drop('repurchase').abs()
       .sort_values(ascending=False).round(3)
)
top_corr = target_corr.head(5)

vh_pct = mem['has_watch_history'].mean() * 100
plan_rates = mem.groupby('plan_tier')['repurchase'].mean() * 100
billing_rates = mem.groupby('billing_group')['repurchase'].mean() * 100

# ════════════════════════════════════════════════════════════════════════════
# HTML 생성
# ════════════════════════════════════════════════════════════════════════════
def img(key, caption='', width='100%'):
    return f'''
<figure style="margin:16px 0;">
  <img src="data:image/png;base64,{CHARTS[key]}" style="width:{width};border-radius:8px;box-shadow:0 2px 10px rgba(0,0,0,0.10);" alt="{caption}">
  {f'<figcaption style="text-align:center;font-size:12px;color:#888;margin-top:6px;">{caption}</figcaption>' if caption else ''}
</figure>'''

# 최종 컬럼 테이블 행 생성
final_cols_info = [
    ('user_no',              '원본',   '고유 사용자 ID'),
    ('repurchase',           '타겟',   '재결제 여부 (0/1)'),
    ('promotion_yn',         '인코딩', '프로모션 참여 (0/1)'),
    ('is_churn_prevented',   '인코딩', '해지방어 (0/1)'),
    ('amount',               '정제',   '결제 금액 (KRW 통일)'),
    ('duration_days',        '계산',   '멤버십 지속 일수'),
    ('age',                  '정제',   '연령 (이상값→비율대체)'),
    ('concurrent_streams',   '정제',   '동시 시청 수 (1/2/4)'),
    ('reg_hour',             '원본',   '가입 시간대'),
    ('gender',               '정제',   '성별 (F/M, N→비율대체)'),
    ('is_user_verified',     '원본',   '인증 여부 문자'),
    ('is_verified',          '파생',   '인증 여부 (0/1)'),
    ('billing_group',        '파생',   '결제 방법 4그룹'),
    ('plan_tier',            '파생',   '플랜 등급 (basic/standard/premium)'),
    ('currency_type',        '파생',   '결제 통화 (KRW/USD)'),
    ('is_promotional_price', '파생',   'amount==100 프로모션 (0/1)'),
    ('is_night_signup',      '파생',   '야간 가입 (0/1)'),
    ('reg_weekday',          '파생',   '가입 요일 (0=월~6=일)'),
    ('is_same_day_cancel',   '파생',   '당일 해지 (0/1)'),
    ('age_group',            '파생',   '연령대 (10대 단위)'),
    ('total_watch_count',    'VH집계', '총 시청 횟수'),
    ('total_watch_duration', 'VH집계', '총 시청 시간(분)'),
    ('unique_movies',        'VH집계', '시청 영화 수'),
    ('avg_duration',         'VH집계', '평균 시청 시간(분)'),
    ('watch_days_count',     'VH집계', '시청 일수'),
    ('has_watch_history',    'VH집계', '시청이력 보유 (0/1)'),
]

tag_map = {
    '원본': 'tag-blue', '타겟': 'tag-red', '인코딩': 'tag-orange',
    '정제': 'tag-green', '파생': 'tag-orange', '계산': 'tag-green',
    'VH집계': 'tag-blue'
}

col_rows = ''
for col, ctype, desc in final_cols_info:
    exists = '✓' if col in mem.columns else '—'
    tag_cls = tag_map.get(ctype, 'tag-blue')
    col_rows += f'''
      <tr>
        <td><code>{col}</code></td>
        <td><span class="tag {tag_cls}">{ctype}</span></td>
        <td>{desc}</td>
        <td style="text-align:center;">{exists}</td>
      </tr>'''

# 상관계수 상위 행 생성
corr_rows = ''
for feat, val in top_corr.items():
    bar_w = int(val * 200)
    corr_rows += f'''
      <tr>
        <td><code>{feat}</code></td>
        <td>
          <div style="display:flex;align-items:center;gap:8px;">
            <div style="width:{bar_w}px;height:12px;background:{BLUE};border-radius:3px;"></div>
            <span>{val:.3f}</span>
          </div>
        </td>
      </tr>'''

html = f'''<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <title>Membership 전처리 보고서</title>
  <style>
    body {{
      font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif;
      background: #f4f6fb;
      color: #222;
      margin: 0;
      padding: 30px 0;
    }}
    .container {{
      max-width: 1100px;
      margin: 0 auto;
      background: #fff;
      border-radius: 12px;
      box-shadow: 0 4px 24px rgba(0,0,0,0.10);
      padding: 40px 50px 60px 50px;
    }}
    h1 {{
      font-size: 26px;
      color: #1a3a6b;
      border-bottom: 3px solid #2962a2;
      padding-bottom: 10px;
      margin-bottom: 6px;
    }}
    .subtitle {{
      color: #888;
      font-size: 13px;
      margin-bottom: 30px;
    }}
    h2 {{
      font-size: 17px;
      color: #fff;
      background: #2962a2;
      padding: 8px 16px;
      border-radius: 6px;
      margin-top: 40px;
      margin-bottom: 12px;
    }}
    h3 {{
      font-size: 14px;
      color: #1a3a6b;
      background: #dce8f7;
      padding: 5px 12px;
      border-radius: 4px;
      margin-top: 22px;
      margin-bottom: 10px;
    }}
    ul {{
      margin: 6px 0 6px 20px;
      padding: 0;
    }}
    li {{
      font-size: 13px;
      margin-bottom: 4px;
      line-height: 1.7;
    }}
    .warn {{
      background: #fff8e1;
      border-left: 4px solid #f59e0b;
      padding: 8px 14px;
      border-radius: 4px;
      font-size: 13px;
      margin: 10px 0;
    }}
    .info {{
      background: #e8f4fd;
      border-left: 4px solid #2962a2;
      padding: 8px 14px;
      border-radius: 4px;
      font-size: 13px;
      margin: 10px 0;
    }}
    .done {{
      background: #e8f5e9;
      border-left: 4px solid #43a047;
      padding: 8px 14px;
      border-radius: 4px;
      font-size: 13px;
      margin: 10px 0;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 12.5px;
      margin: 10px 0 14px 0;
    }}
    thead tr {{
      background: #2962a2;
      color: #fff;
    }}
    thead th {{
      padding: 7px 10px;
      text-align: left;
      font-weight: bold;
    }}
    tbody tr:nth-child(even) {{ background: #f0f5ff; }}
    tbody tr:nth-child(odd)  {{ background: #fff; }}
    tbody td {{
      padding: 6px 10px;
      border-bottom: 1px solid #e0e8f5;
      vertical-align: middle;
    }}
    code {{
      background: #f0f4ff;
      padding: 1px 5px;
      border-radius: 3px;
      font-size: 12px;
      color: #1a3a6b;
    }}
    .tag {{
      display: inline-block;
      padding: 2px 8px;
      border-radius: 10px;
      font-size: 11px;
      font-weight: bold;
    }}
    .tag-red    {{ background:#fde8e8; color:#c0392b; }}
    .tag-orange {{ background:#fff3e0; color:#e65100; }}
    .tag-green  {{ background:#e8f5e9; color:#2e7d32; }}
    .tag-blue   {{ background:#e3f2fd; color:#1565c0; }}
    .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 14px;
      margin: 16px 0;
    }}
    .kpi {{
      background: #f0f5ff;
      border-radius: 8px;
      padding: 14px 16px;
      text-align: center;
      border: 1px solid #c5d8f5;
    }}
    .kpi .val {{
      font-size: 22px;
      font-weight: bold;
      color: #1a3a6b;
    }}
    .kpi .lbl {{
      font-size: 11px;
      color: #666;
      margin-top: 4px;
    }}
    .step-grid {{
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 12px;
      margin: 14px 0;
    }}
    .step-card {{
      border: 1px solid #c5d8f5;
      border-radius: 8px;
      padding: 12px 16px;
      background: #f8faff;
    }}
    .step-card .step-title {{
      font-size: 13px;
      font-weight: bold;
      color: #1a3a6b;
      margin-bottom: 6px;
    }}
    .step-card .step-detail {{
      font-size: 12px;
      color: #555;
      line-height: 1.6;
    }}
    .step-card .badge {{
      display: inline-block;
      background: #2962a2;
      color: #fff;
      font-size: 10px;
      padding: 1px 7px;
      border-radius: 8px;
      margin-right: 4px;
    }}
    .badge-warn {{ background: #f59e0b; }}
    .badge-done {{ background: #43a047; }}
    hr {{ border: none; border-top: 1px solid #e0e8f5; margin: 32px 0; }}
    .footer {{
      margin-top: 40px;
      font-size: 12px;
      color: #aaa;
      text-align: right;
    }}
    .insight {{
      background: #fffde7;
      border: 1px solid #ffe082;
      border-radius: 6px;
      padding: 10px 14px;
      font-size: 13px;
      margin: 10px 0;
    }}
    .insight strong {{ color: #e65100; }}
    .two-col {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 20px;
    }}
  </style>
</head>
<body>
<div class="container">

  <h1>Membership 전처리 보고서</h1>
  <div class="subtitle">OTT 고객 이탈 예측 프로젝트 · 데이터 전처리 결과 · CLAUDE.md 방향성 기반</div>

  <!-- KPI 카드 -->
  <div class="kpi-grid">
    <div class="kpi">
      <div class="val">{len(mem_raw):,}</div>
      <div class="lbl">원본 행수</div>
    </div>
    <div class="kpi">
      <div class="val" style="color:#43a047;">{n_final:,}</div>
      <div class="lbl">전처리 후 행수</div>
    </div>
    <div class="kpi">
      <div class="val" style="color:#e53935;">{n_removed:,}</div>
      <div class="lbl">제거 행수</div>
    </div>
    <div class="kpi">
      <div class="val">{len(mem.columns)}</div>
      <div class="lbl">최종 피처 수</div>
    </div>
  </div>

  <hr>

  <!-- ══════════════════════════════════════════ -->
  <h2>1. 전처리 전 현황</h2>

  {img('missing_before', '전처리 전 컬럼별 결측치 비율 (%)')}

  <table>
    <thead><tr><th>컬럼</th><th>결측 수</th><th>결측률</th><th>해석</th><th>처리 방향</th></tr></thead>
    <tbody>
      <tr><td><code>is_churn_prevented</code></td><td>14,926</td><td><span class="tag tag-red">82.1%</span></td><td>NaN = 미해당</td><td>NaN→0, O→1</td></tr>
      <tr><td><code>promotion_yn</code></td><td>8,980</td><td><span class="tag tag-red">49.4%</span></td><td>NaN = 미참여</td><td>NaN→0, O→1</td></tr>
      <tr><td><code>repurchase</code></td><td>6,252</td><td><span class="tag tag-orange">34.4%</span></td><td>NaN = 이탈 <strong>(타겟)</strong></td><td>NaN→0, O→1</td></tr>
      <tr><td><code>is_user_verified</code></td><td>600</td><td><span class="tag tag-blue">3.3%</span></td><td>Y/N</td><td>결측→N, Y→1/N→0 인코딩</td></tr>
      <tr><td><code>gender</code></td><td>164</td><td><span class="tag tag-green">0.9%</span></td><td>미인증 연동</td><td>N→NaN 후 F/M 비율 대체</td></tr>
      <tr><td><code>age</code></td><td>164</td><td><span class="tag tag-green">0.9%</span></td><td>미인증 연동</td><td>이상값(>100)→NaN, 비율 대체</td></tr>
      <tr><td><code>concurrent_streams</code></td><td>70</td><td><span class="tag tag-green">0.4%</span></td><td>소량</td><td>결측 행 제거</td></tr>
    </tbody>
  </table>

  <hr>

  <!-- ══════════════════════════════════════════ -->
  <h2>2. 필수 전처리</h2>

  <div class="step-grid">
    <div class="step-card">
      <div class="step-title"><span class="badge">필수 1</span> user_no 중복 제거</div>
      <div class="step-detail">
        중복 보유 행: <strong>{n_dup_rows:,}건</strong> ({n_dup_users:,}명)<br>
        전략: duration_days 최대값 행 유지<br>
        결과: <strong>{n_before_dup:,} → {n_after_dup:,}</strong> ({n_before_dup - n_after_dup:,}건 제거)
      </div>
    </div>
    <div class="step-card">
      <div class="step-title"><span class="badge">필수 2</span> 타겟 인코딩</div>
      <div class="step-detail">
        repurchase / promotion_yn / is_churn_prevented<br>
        O → 1, NaN → 0<br>
        재결제: <strong>{mem['repurchase'].sum():,}건</strong> ({mem['repurchase'].mean()*100:.1f}%)
      </div>
    </div>
    <div class="step-card">
      <div class="step-title"><span class="badge">필수 3</span> 통화 통일</div>
      <div class="step-detail">
        iOS 달러 상품 (pk_1506/1507/1508): <strong>{n_usd:,}건</strong><br>
        환율: 2021년 평균 <strong>1,144원/USD</strong><br>
        amount=100(프로모션)은 제외
      </div>
    </div>
    <div class="step-card">
      <div class="step-title"><span class="badge">필수 4</span> is_user_verified 인코딩</div>
      <div class="step-detail">
        결측값 → N 대체 후 Y→1 / N→0<br>
        인증(1): <strong>{mem['is_verified'].sum():,}건</strong> ({mem['is_verified'].mean()*100:.1f}%)<br>
        미인증(0): <strong>{(mem['is_verified']==0).sum():,}건</strong>
      </div>
    </div>
    <div class="step-card">
      <div class="step-title"><span class="badge">필수 5</span> concurrent_streams 정리</div>
      <div class="step-detail">
        =3 이상값 제거: <strong>{n_cs3}건</strong> (입력 오류, 상품 tier 없음)<br>
        결측 행 제거: <strong>{n_csna}건</strong><br>
        결과: {n_before_cs:,} → {n_after_cs:,}
      </div>
    </div>
    <div class="step-card">
      <div class="step-title"><span class="badge">필수 6</span> View_History only 유저 확인</div>
      <div class="step-detail">
        조인 경로: USER_ID → uid(User_Mapping) → user_no<br>
        Membership 기준(left join)이므로 행 제거 없음<br>
        VH only 유저는 집계 피처 생성 시 자동 제외
      </div>
    </div>
  </div>

  {img('target_after', '타겟 변수(repurchase) 분포 — 필수 전처리 후')}

  <hr>

  <!-- ══════════════════════════════════════════ -->
  <h2>3. 권장 전처리</h2>

  <h3>3-1. age 이상값 처리</h3>
  <div class="warn">
    원본 max = <strong>950</strong> (미인증 입력 오류).
    age &gt; 100 이상값 <strong>{n_age_out}건</strong> 및 결측 <strong>{n_age_na}건</strong> → NaN 처리 후
    기존 연령대 비율 기반 랜덤 대체 (seed=42).
  </div>
  {img('age_compare', '연령 분포 — 처리 전(회색) vs 처리 후(파랑)')}

  <h3>3-2. billing_method 4그룹 그루핑</h3>
  <div class="info">
    <strong>국내카드</strong>(13x) / <strong>간편결제</strong>(151) / <strong>iOS</strong>(140) / <strong>모바일</strong>(18x)
  </div>
  <table>
    <thead><tr><th>그룹</th><th>billing_method</th><th>건수</th><th>재결제율</th></tr></thead>
    <tbody>
      {''.join(f"<tr><td><strong>{g}</strong></td><td>{'13x' if g=='국내카드' else '151' if g=='간편결제' else '140' if g=='iOS' else '18x' if g=='모바일' else '-'}</td><td>{mem[mem['billing_group']==g]['billing_group'].count():,}건</td><td>{mem[mem['billing_group']==g]['repurchase'].mean()*100:.1f}%</td></tr>" for g in ['국내카드','간편결제','iOS','모바일','기타'] if g in mem['billing_group'].values)}
    </tbody>
  </table>

  <h3>3-3. gender=N → 결측 처리 + F/M 비율 대체</h3>
  <div class="warn">
    gender=N은 미인증 기본값 (<strong>{n_gN:,}건</strong>). 실제 성별 정보 없음 → NaN 처리 후
    F/M 비율(<strong>F {fm_dist.get('F', 0)*100:.1f}% / M {fm_dist.get('M', 0)*100:.1f}%</strong>)로 랜덤 대체.
    기존 NaN <strong>{n_gna}건</strong> 포함 총 <strong>{n_gN + n_gna:,}건</strong> 대체.
  </div>

  <hr>

  <!-- ══════════════════════════════════════════ -->
  <h2>4. 파생 피처 생성</h2>

  <table>
    <thead><tr><th>피처명</th><th>생성 방법</th><th>설명</th><th>건수(해당=1)</th></tr></thead>
    <tbody>
      <tr><td><code>plan_tier</code></td><td>product_cd 매핑</td><td>basic/standard/premium</td>
          <td>basic {mem[mem['plan_tier']=='basic']['plan_tier'].count():,} / std {mem[mem['plan_tier']=='standard']['plan_tier'].count():,} / prem {mem[mem['plan_tier']=='premium']['plan_tier'].count():,}</td></tr>
      <tr><td><code>currency_type</code></td><td>product_cd 분류</td><td>KRW / USD</td>
          <td>KRW {mem[mem['currency_type']=='KRW']['currency_type'].count():,} / USD {mem[mem['currency_type']=='USD']['currency_type'].count():,}</td></tr>
      <tr><td><code>is_promotional_price</code></td><td>amount==100</td><td>프로모션 가격(100원)</td>
          <td>{mem['is_promotional_price'].sum():,}건 ({mem['is_promotional_price'].mean()*100:.1f}%)</td></tr>
      <tr><td><code>is_night_signup</code></td><td>reg_hour ∈ {{22,23,0,1,2,3}}</td><td>야간 가입</td>
          <td>{mem['is_night_signup'].sum():,}건 ({mem['is_night_signup'].mean()*100:.1f}%)</td></tr>
      <tr><td><code>reg_weekday</code></td><td>reg_date.dayofweek</td><td>가입 요일 (0=월~6=일)</td><td>—</td></tr>
      <tr><td><code>is_same_day_cancel</code></td><td>duration_days==0</td><td>당일 해지</td>
          <td>{mem['is_same_day_cancel'].sum():,}건 ({mem['is_same_day_cancel'].mean()*100:.1f}%)</td></tr>
      <tr><td><code>age_group</code></td><td>age // 10 × 10</td><td>10세 단위 연령대</td><td>—</td></tr>
    </tbody>
  </table>

  {img('group_repurchase', '그룹별 재결제율 — plan_tier / billing_group / currency_type / gender')}
  {img('binary_repurchase', '이진 파생 피처별 재결제율 비교')}
  {img('age_duration', '연령대별 재결제율 & 재결제 여부별 duration_days 분포')}

  <hr>

  <!-- ══════════════════════════════════════════ -->
  <h2>5. View_History 집계 피처 (선택)</h2>

  <div class="warn">
    시청 기간: <strong>2021-03-01 ~ 2021-04-05 (약 5주)</strong> → feature importance 낮을 수 있음.
    시청이력 보유 유저: <strong>{mem['has_watch_history'].sum():,}명 ({vh_pct:.1f}%)</strong>
  </div>

  <table>
    <thead><tr><th>피처명</th><th>설명</th><th>평균(전체)</th><th>시청이력 보유 유저</th></tr></thead>
    <tbody>
      <tr><td><code>total_watch_count</code></td><td>총 시청 횟수</td>
          <td>{mem['total_watch_count'].mean():.1f}</td>
          <td>{mem[mem['has_watch_history']==1]['total_watch_count'].mean():.1f}</td></tr>
      <tr><td><code>total_watch_duration</code></td><td>총 시청 시간(분)</td>
          <td>{mem['total_watch_duration'].mean():.1f}</td>
          <td>{mem[mem['has_watch_history']==1]['total_watch_duration'].mean():.1f}</td></tr>
      <tr><td><code>unique_movies</code></td><td>시청 영화 수</td>
          <td>{mem['unique_movies'].mean():.1f}</td>
          <td>{mem[mem['has_watch_history']==1]['unique_movies'].mean():.1f}</td></tr>
      <tr><td><code>avg_duration</code></td><td>평균 시청 시간(분/회)</td>
          <td>{mem['avg_duration'].mean():.1f}</td>
          <td>{mem[mem['has_watch_history']==1]['avg_duration'].mean():.1f}</td></tr>
      <tr><td><code>watch_days_count</code></td><td>시청 일수</td>
          <td>{mem['watch_days_count'].mean():.1f}</td>
          <td>{mem[mem['has_watch_history']==1]['watch_days_count'].mean():.1f}</td></tr>
      <tr><td><code>has_watch_history</code></td><td>시청이력 보유 여부</td>
          <td colspan="2">{mem['has_watch_history'].sum():,}명 ({vh_pct:.1f}%)</td></tr>
    </tbody>
  </table>

  {img('vh_features', 'View_History 집계 피처 분포 & 시청이력 유무 × 재결제율')}

  <hr>

  <!-- ══════════════════════════════════════════ -->
  <h2>6. 전처리 후 EDA — 상관관계</h2>

  {img('corr_heatmap', '수치형 피처 상관관계 히트맵 (전처리 후)')}

  <h3>repurchase와 상관계수 Top 5</h3>
  <table>
    <thead><tr><th>피처</th><th>|상관계수|</th></tr></thead>
    <tbody>{corr_rows}</tbody>
  </table>

  <div class="insight">
    <strong>해석 가이드:</strong> 상관계수가 높을수록 해당 피처가 재결제 예측에 직접 유용.
    단, 선형 상관관계만 측정하므로 트리 기반 모델에서는 비선형 관계도 활용됨.
  </div>

  <hr>

  <!-- ══════════════════════════════════════════ -->
  <h2>7. 최종 데이터셋 요약</h2>

  <div class="done">
    최종 데이터셋: <strong>{n_final:,}행 × {len(mem.columns)}열</strong>
    | 타겟 재결제율: <strong>{repurchase_rate:.1f}%</strong>
    | 잔여 결측치: <strong>없음</strong>
    | 저장: <code>Membership_clean.csv</code>
  </div>

  <table>
    <thead><tr><th>컬럼명</th><th>구분</th><th>설명</th><th>포함</th></tr></thead>
    <tbody>{col_rows}</tbody>
  </table>

  <div class="footer">OTT 고객 이탈 예측 프로젝트 · 전처리 보고서</div>
</div>
</body>
</html>'''

OUT = 'c:/Users/USER/OneDrive/바탕 화면/AX/EDA/preprocessing_report.html'
with open(OUT, 'w', encoding='utf-8') as f:
    f.write(html)
print(f'\nDone: {OUT}')
