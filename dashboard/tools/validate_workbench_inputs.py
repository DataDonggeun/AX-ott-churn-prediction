from pathlib import Path
import hashlib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
OUT = ROOT / 'validation_outputs'
OUT.mkdir(exist_ok=True)

EARLY = 119
ACTIVE = 141
THRESH = 0.25
ORDER = ['S1','S2','S3','S4','S5','S6']
LOOKUP={(True,'active'):'S1',(True,'weakened'):'S2',(True,'dormant'):'S3',(False,'active'):'S4',(False,'weakened'):'S5',(False,'dormant'):'S6'}

def h(path):
    x=hashlib.sha256()
    with path.open('rb') as f:
        for c in iter(lambda:f.read(1024*1024), b''): x.update(c)
    return x.hexdigest()

def load(name): return pd.read_csv(DATA/name, encoding='utf-8-sig')

expanded_raw=load('06x_expanded_dataset.csv')
expanded=expanded_raw.reset_index(drop=False).rename(columns={'index':'source_row_id'})
membership=load('Membership_v2.csv')
mapping=load('User_Mapping_v2.csv')
views=load('View_History_v2.csv')
movies=load('Movie_Master_v2.csv')

manifest=[]
for name, role, df in [
    ('06x_expanded_dataset.csv','공식 입력',expanded_raw),('Membership_v2.csv','가입일 연결',membership),
    ('User_Mapping_v2.csv','USER_NUM 연결',mapping),('View_History_v2.csv','시청 이력',views),('Movie_Master_v2.csv','작품명 연결',movies)
]:
    p=DATA/name
    manifest.append({'file_name':name,'role':role,'rows':len(df),'columns':len(df.columns),'size_bytes':p.stat().st_size,'sha256':h(p)})
pd.DataFrame(manifest).to_csv(OUT/'source_file_manifest.csv', index=False, encoding='utf-8-sig')

x=expanded[expanded['is_promotion'].eq(1)].copy()
x['is_churn']=(x['is_repurchase']==0).astype(int)
x['early_watch_min']=x['watch_time_min_w1']+x['watch_time_min_w2']
x['short_session_flag']=x['watch_ratio_under_5m']>THRESH
x['late']=np.select([x['watch_time_min_w3']>=ACTIVE,x['watch_time_min_w3']>0],['active','weakened'],default='dormant')
x['segment']=[LOOKUP[(a>=EARLY,l)] for a,l in zip(x['early_watch_min'],x['late'])]
x['segment_hardgate']=[LOOKUP[((a>=EARLY) and not s,l)] for a,s,l in zip(x['early_watch_min'],x['short_session_flag'],x['late'])]

summ=x.groupby('segment').agg(event_count=('source_row_id','size'),churn_count=('is_churn','sum'),watch_total_median=('total_watch_time_min','median'),short_flag_rate=('short_session_flag','mean')).reindex(ORDER).reset_index()
summ['churn_rate_pct']=summ['churn_count']/summ['event_count']*100
summ['share_pct']=summ['event_count']/len(x)*100
summ['short_flag_rate_pct']=summ['short_flag_rate']*100
summ.drop(columns=['short_flag_rate']).to_csv(OUT/'canonical_segment_summary_promotion.csv', index=False, encoding='utf-8-sig')

main=summ[['segment','event_count','churn_rate_pct']].rename(columns={'event_count':'canonical_n','churn_rate_pct':'canonical_churn_pct'})
hard=x.groupby('segment_hardgate').agg(hardgate_n=('source_row_id','size'),hardgate_churn_pct=('is_churn','mean')).reindex(ORDER).reset_index().rename(columns={'segment_hardgate':'segment'})
hard['hardgate_churn_pct']*=100
comp=main.merge(hard,on='segment')
comp['diff_n_canonical_minus_hardgate']=comp['canonical_n']-comp['hardgate_n']
comp.to_csv(OUT/'criteria_comparison_canonical_vs_hardgate.csv', index=False, encoding='utf-8-sig')

migration=x.groupby(['segment_hardgate','segment']).agg(event_count=('source_row_id','size'),churn_rate=('is_churn','mean')).reset_index()
migration['churn_rate_pct']=migration['churn_rate']*100
migration.drop(columns='churn_rate').to_csv(OUT/'criteria_migration_canonical_vs_hardgate.csv', index=False, encoding='utf-8-sig')

# Safer event-level W4 reconstruction: match same outcome/promotion/verification membership date;
# if a USER_KEY has multiple USER_NUM candidates, accept only when candidate w4 totals agree.
cols=['source_row_id','USER_KEY','is_promotion','is_repurchase','is_user_verified']
cand=x[cols].merge(membership[['USER_KEY','is_promotion','is_repurchase','is_user_verified','reg_date']],on=['USER_KEY','is_promotion','is_repurchase','is_user_verified'],how='left')
cand['reg_date']=pd.to_datetime(cand['reg_date'],errors='coerce')
cand=cand.merge(mapping[['USER_KEY','USER_NUM']].drop_duplicates(),on='USER_KEY',how='left')[['source_row_id','USER_NUM','reg_date']].drop_duplicates()
v=views.copy()
v['watch_date']=pd.to_datetime(v['watch_day'].astype(str),format='%Y%m%d',errors='coerce')
j=cand.merge(v[['USER_NUM','watch_time(min)','watch_date']],on='USER_NUM',how='left')
j['day_offset']=(j['watch_date']-j['reg_date']).dt.days
w4=j[(j['day_offset']>=21)&(j['day_offset']<=27)].groupby(['source_row_id','USER_NUM','reg_date'],dropna=False)['watch_time(min)'].sum().reset_index(name='w4_minutes')
r=cand.merge(w4,on=['source_row_id','USER_NUM','reg_date'],how='left')
r['w4_minutes']=r['w4_minutes'].fillna(0)
a=r.groupby('source_row_id').agg(candidate_count=('USER_NUM','size'),distinct_user_num=('USER_NUM','nunique'),w4_min=('w4_minutes','min'),w4_max=('w4_minutes','max'),w4_values=('w4_minutes','nunique')).reset_index()
a['w4_resolved']=a['w4_values']<=1
a['w4_minutes']=np.where(a['w4_resolved'],a['w4_min'],np.nan)
y=x.merge(a[['source_row_id','candidate_count','distinct_user_num','w4_resolved','w4_minutes']],on='source_row_id',how='left')
y['has_w4']=y['w4_minutes']>0
rows=[]
for seg in ORDER:
    z=y[(y['segment']==seg)&y['w4_resolved']]
    yes=z[z['has_w4']]; no=z[~z['has_w4']]
    rows.append({'segment':seg,'event_count':len(z),'w4_view_events':int(z['has_w4'].sum()),'w4_view_rate_pct':z['has_w4'].mean()*100,'churn_rate_w4_yes_pct':yes['is_churn'].mean()*100,'churn_rate_w4_no_pct':no['is_churn'].mean()*100,'gap_observed_pct_point':no['is_churn'].mean()*100-yes['is_churn'].mean()*100})
pd.DataFrame(rows).to_csv(OUT/'canonical_w4_observation_summary.csv',index=False,encoding='utf-8-sig')
pd.DataFrame([{'item':'promo_event_count','value':len(x)},{'item':'events_with_multiple_user_num_candidates','value':int((a['candidate_count']>1).sum())},{'item':'events_with_conflicting_w4_candidate_values','value':int((~a['w4_resolved']).sum())},{'item':'resolved_w4_events','value':int(a['w4_resolved'].sum())},{'item':'w4_positive_events','value':int(y['has_w4'].sum())},{'item':'w4_definition','value':'Day 21~27 after matched reg_date; observational only'}]).to_csv(OUT/'canonical_w4_connection_audit.csv',index=False,encoding='utf-8-sig')

print('PASS: validation outputs created')
print('promo events', len(x), 'moved_by_hardgate', int((x.segment != x.segment_hardgate).sum()))
print('w4 resolved', int(a.w4_resolved.sum()), 'w4 positive', int(y.has_w4.sum()))
