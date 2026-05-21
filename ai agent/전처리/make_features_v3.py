# -*- coding: utf-8 -*-
import warnings; warnings.filterwarnings('ignore')
import numpy as np
import pandas as pd
from pathlib import Path

BASE   = Path(__file__).parent.parent / '_data/02_interim/260510_merged_v2'
OUT    = Path(__file__).parent.parent / '_data/02_interim/260510_features'
OUT.mkdir(exist_ok=True)
CUTOFF = 21

# 데이터 로드
mem   = pd.read_csv(BASE/'Membership_v2.csv',   encoding='utf-8-sig')
vh    = pd.read_csv(BASE/'View_History_v2.csv',  encoding='utf-8-sig')
movie = pd.read_csv(BASE/'Movie_Master_v2.csv',  encoding='utf-8-sig')
umap  = pd.read_csv(BASE/'User_Mapping_v2.csv',  encoding='utf-8-sig')
print(f'Membership: {mem.shape}')

# reg_date / end_date → datetime (이미 실제 날짜)
mem['reg_date_dt'] = pd.to_datetime(mem['reg_date'])
mem['end_date_dt'] = pd.to_datetime(mem['end_date'])
print(f'reg_date sample: {mem["reg_date"].iloc[0]}')

# ViewHistory 전처리
vh['watch_date'] = pd.to_datetime(vh['watch_day'].astype(str))
vh = vh.merge(umap, on='USER_NUM', how='left')
vh = vh.merge(mem[['USER_KEY','reg_date_dt']], on='USER_KEY', how='left')
vh['obs_day'] = (vh['watch_date'] - vh['reg_date_dt']).dt.days
vh = vh[(vh['obs_day'] >= 0) & (vh['obs_day'] < CUTOFF)].copy()
vh['is_weekend'] = vh['watch_date'].dt.weekday >= 5
vh = vh.merge(movie[['MOVIE_NUM','genre','ott_release_month']], on='MOVIE_NUM', how='left')
print(f'ViewHistory filtered: {vh.shape}')

df  = mem.copy()
grp = vh.groupby('USER_KEY')

# 0. duration_days, price_per_day
df['duration_days'] = (mem['end_date_dt'] - mem['reg_date_dt']).dt.days
df['price_per_day'] = np.where(df['duration_days'] > 0, df['price'] / df['duration_days'], 0)

# 1. 기본 멤버십
df['is_standard'] = (df['max_screen'] == 2).astype(int)
df['is_premium']  = (df['max_screen'] == 4).astype(int)

# 2. 인구통계
df['age_group'] = (df['age'] // 10 * 10).fillna(0).astype(int)
df['is_female'] = (df['gender'] == 'F').astype(int)
df['is_male']   = (df['gender'] == 'M').astype(int)

# 3. 가입 시간대
df['reg_is_weekend']     = (mem['reg_date_dt'].dt.weekday >= 5).astype(int)
h = df['reg_hour'].fillna(-1)
df['reg_hour_morning']   = ((h >= 6)  & (h < 12)).astype(int)
df['reg_hour_afternoon'] = ((h >= 12) & (h < 18)).astype(int)
df['reg_hour_evening']   = ((h >= 18) & (h < 24)).astype(int)
df['reg_hour_night']     = ((h >= 0)  & (h < 6)).astype(int)

# 4. 결제 디바이스
dev = df['payment_device'].str.lower().fillna('')
df['payment_is_mobile']  = (dev == 'mobile').astype(int)
df['payment_is_pc']      = (dev == 'pc').astype(int)
df['payment_is_android'] = (dev == 'android').astype(int)
df['payment_is_ios']     = (dev == 'ios').astype(int)

# 5. 시청 기본
basic = grp.agg(
    total_watch_count=('watch_time(min)', 'count'),
    unique_movie=('MOVIE_NUM', 'nunique'),
    watch_days=('watch_day', 'nunique'),
    total_watch_time=('watch_time(min)', 'sum'),
).reset_index()
basic['active_ratio']  = basic['watch_days'] / CUTOFF
basic['watch_per_day'] = basic['total_watch_count'] / basic['watch_days'].clip(lower=1)
df = df.merge(basic, on='USER_KEY', how='left')

# 6. 시청 시간 분포
tdist = grp['watch_time(min)'].agg(
    avg_watch_time='mean',
    median_watch_time='median',
    std_watch_time=lambda x: x.std(ddof=0),
    max_watch_time='max',
).reset_index()
df = df.merge(tdist, on='USER_KEY', how='left')

daily = vh.groupby(['USER_KEY','watch_day'])['watch_time(min)'].agg(
    daily_sum='sum', daily_count='count').reset_index()
dagg = daily.groupby('USER_KEY').agg(
    avg_daily_watch_time=('daily_sum','mean'),
    max_daily_watch_time=('daily_sum','max'),
    max_daily_sessions=('daily_count','max'),
).reset_index()
df = df.merge(dagg, on='USER_KEY', how='left')

# 7. 시청 패턴
rec = grp['obs_day'].max().reset_index()
rec.columns = ['USER_KEY','last_obs_day']
rec['recency'] = 20 - rec['last_obs_day']
df = df.merge(rec[['USER_KEY','recency']], on='USER_KEY', how='left')

def avg_gap(x):
    d = sorted(x.unique())
    return np.mean(np.diff(d)) if len(d) >= 2 else np.nan

def max_gap(x):
    d = sorted(x.unique())
    return max(np.diff(d)) if len(d) >= 2 else float(CUTOFF)

tmp = grp['obs_day'].apply(avg_gap).reset_index()
tmp.columns = ['USER_KEY','avg_gap_between_watch_days']
df = df.merge(tmp, on='USER_KEY', how='left')

tmp = grp['obs_day'].apply(max_gap).reset_index()
tmp.columns = ['USER_KEY','max_inactive_gap_days']
df = df.merge(tmp, on='USER_KEY', how='left')

for w, (lo, hi) in enumerate([(0,7),(7,14),(14,21)], 1):
    wvh = vh[(vh['obs_day'] >= lo) & (vh['obs_day'] < hi)]
    tmp = wvh.groupby('USER_KEY')['obs_day'].apply(avg_gap).reset_index()
    tmp.columns = ['USER_KEY', f'avg_gap_w{w}_watch_days']
    df = df.merge(tmp, on='USER_KEY', how='left')

tc = grp.size().reset_index(name='tc')
rw = vh.groupby(['USER_KEY','MOVIE_NUM']).size().reset_index(name='cnt')
rw = rw[rw['cnt']>=2].groupby('USER_KEY').size().reset_index(name='rw')
rw_r = tc.merge(rw, on='USER_KEY', how='left').fillna(0)
rw_r['avg_rewatch_ratio'] = rw_r['rw'] / rw_r['tc'].clip(lower=1)
df = df.merge(rw_r[['USER_KEY','avg_rewatch_ratio']], on='USER_KEY', how='left')

tmp = grp['is_weekend'].mean().reset_index(name='weekend_watch_ratio')
df = df.merge(tmp, on='USER_KEY', how='left')

for mins, col in [(1,'watch_ratio_under_1m'),(5,'watch_ratio_under_5m')]:
    tmp = vh.groupby('USER_KEY')['watch_time(min)'].apply(
        lambda x: (x < mins).mean()).reset_index(name=col)
    df = df.merge(tmp, on='USER_KEY', how='left')

# 8. 온보딩
tmp = grp['obs_day'].min().reset_index(name='first_watch_day')
df = df.merge(tmp, on='USER_KEY', how='left')
df['is_cold_start_3d'] = (df['first_watch_day'] <= 2).astype(int)
df['is_cold_start_7d'] = (df['first_watch_day'] <= 6).astype(int)

# 9. 시청 강도
df['movie_per_active_day'] = np.where(df['watch_days']>0, df['unique_movie']/df['watch_days'], 0)
df['max_day_share']        = np.where(df['total_watch_time']>0, df['max_daily_watch_time']/df['total_watch_time'], 0)
tmp = daily[daily['daily_count']>=3].groupby('USER_KEY').size().reset_index(name='day_count_over_3times')
df = df.merge(tmp, on='USER_KEY', how='left')

# 10. 주차별 시청
for w, (lo, hi) in enumerate([(0,7),(7,14),(14,21)], 1):
    wvh = vh[(vh['obs_day'] >= lo) & (vh['obs_day'] < hi)]
    wt  = wvh.groupby('USER_KEY')['watch_time(min)'].sum().reset_index(name=f'watch_time_w{w}')
    ws  = wvh.groupby('USER_KEY').size().reset_index(name=f'watch_session_w{w}')
    df  = df.merge(wt, on='USER_KEY', how='left').merge(ws, on='USER_KEY', how='left')

for c in ['watch_time_w1','watch_time_w2','watch_time_w3',
          'watch_session_w1','watch_session_w2','watch_session_w3']:
    df[c] = df[c].fillna(0)

df['retention_w2_ratio']    = np.log1p(df['watch_time_w2']) - np.log1p(df['watch_time_w1'])
df['retention_w3_ratio']    = np.where(df['total_watch_time']>0, df['watch_time_w3']/df['total_watch_time'], 0)
df['w3_to_w1_ratio_capped'] = np.where(df['watch_time_w1']>0,
    (df['watch_time_w3']/df['watch_time_w1']).clip(upper=5),
    np.where(df['watch_time_w3']>0, 5, 0))
df['diff_between_w2_w1'] = df['watch_time_w2'] - df['watch_time_w1']
df['diff_between_w3_w1'] = df['watch_time_w3'] - df['watch_time_w1']
df['diff_between_w3_w2'] = df['watch_time_w3'] - df['watch_time_w2']

# 11. 시청 유형 플래그
tot = df['total_watch_time'].replace(0, np.nan)
df['is_w1_over_50'] = (df['watch_time_w1']/tot >= 0.5).fillna(0).astype(int)
df['is_w2_over_50'] = (df['watch_time_w2']/tot >= 0.5).fillna(0).astype(int)
df['is_w3_over_50'] = (df['watch_time_w3']/tot >= 0.5).fillna(0).astype(int)
df['is_only_w1'] = ((df['watch_time_w1']>0)&(df['watch_time_w2']==0)&(df['watch_time_w3']==0)).astype(int)
df['is_only_w2'] = ((df['watch_time_w1']==0)&(df['watch_time_w2']>0)&(df['watch_time_w3']==0)).astype(int)
df['is_only_w3'] = ((df['watch_time_w1']==0)&(df['watch_time_w2']==0)&(df['watch_time_w3']>0)).astype(int)

# 12. 신규 영화 시청
vh['rel_month'] = pd.to_numeric(vh['ott_release_month'], errors='coerce').fillna(0).astype(int)
tc2 = grp.size().reset_index(name='tc2')

for cutym, col in [
    (202101,'new_movie_in_90d_ratio'),
    (202009,'new_movie_in_180d_ratio'),
    (202003,'new_movie_in_365d_ratio'),
]:
    sub = vh[vh['rel_month'] >= cutym].groupby('USER_KEY').size().reset_index(name='nc')
    tmp = tc2.merge(sub, on='USER_KEY', how='left').fillna(0)
    tmp[col] = tmp['nc'] / tmp['tc2'].clip(lower=1)
    df = df.merge(tmp[['USER_KEY',col]], on='USER_KEY', how='left')

old = vh[(vh['rel_month']>0)&(vh['rel_month']<=201603)].groupby('USER_KEY').size().reset_index(name='oc')
tmp = tc2.merge(old, on='USER_KEY', how='left').fillna(0)
tmp['old_movie_ratio'] = tmp['oc'] / tmp['tc2'].clip(lower=1)
df = df.merge(tmp[['USER_KEY','old_movie_ratio']], on='USER_KEY', how='left')

vhr = vh[vh['rel_month']>0].copy()
vhr['rel_year'] = vhr['rel_month'] // 100
tmp = vhr.groupby('USER_KEY')['rel_year'].mean().reset_index(name='avg_release_year')
df = df.merge(tmp, on='USER_KEY', how='left')

# 13. 장르
tmp = grp['genre'].nunique().reset_index(name='genre_diversity_count')
df  = df.merge(tmp, on='USER_KEY', how='left')

tc3 = grp.size().reset_index(name='tc3')
for col, genres in [
    ('action_adventure_ratio', ['Action/Adventure']),
    ('family_animation_ratio', ['Animation/Family']),
    ('drama_ratio',            ['Drama']),
    ('thriller_crime_ratio',   ['Thriller/Crime']),
    ('sf_fantasy_ratio',       ['SF/Fantasy']),
    ('comedy_ratio',           ['Comedy']),
    ('romance_ratio',          ['Romance']),
    ('horror_ratio',           ['Horror']),
    ('documentary_ratio',      ['Documentary']),
    ('historical_war_ratio',   ['Historical/War']),
    ('other_ratio',            ['Other']),
]:
    sub = vh[vh['genre'].isin(genres)].groupby('USER_KEY').size().reset_index(name='gc')
    tmp = tc3.merge(sub, on='USER_KEY', how='left').fillna(0)
    tmp[col] = tmp['gc'] / tmp['tc3'].clip(lower=1)
    df = df.merge(tmp[['USER_KEY',col]], on='USER_KEY', how='left')

# 결측 처리 및 내부 컬럼 제거
num_cols = df.select_dtypes(include='number').columns
df[num_cols] = df[num_cols].fillna(0)
df = df.drop(columns=['reg_date_dt','end_date_dt'], errors='ignore')

out = OUT / 'Membership_features_v3.csv'
df.to_csv(out, index=False, encoding='utf-8-sig')
print(f'done! shape: {df.shape}')
print(f'saved: {out}')
