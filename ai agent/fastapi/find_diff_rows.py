import pandas as pd
from pathlib import Path

BASE = Path(__file__).parent.parent
feat_dir = BASE / "_data" / "02_interim" / "260513 feature"
raw_dir  = BASE / "_data" / "01_raw"
v2_dir   = BASE / "_data" / "02_interim" / "260510_merged_v2"

mem_raw = pd.read_csv(raw_dir / "Membership_train.csv", encoding="utf-8-sig")
v2      = pd.read_csv(v2_dir  / "Membership_v2.csv",   encoding="utf-8-sig")
v3      = pd.read_csv(feat_dir / "Membership_v3.csv",  encoding="utf-8-sig")

# raw에서 전처리 단계별 행 수
print("=== raw 전처리 단계별 행수 ===")
print(f"raw 원본: {len(mem_raw)}행")

# 컬럼 rename
rn = {"uno":"USER_KEY","pgamount":"price","concurrentwatchcount":"max_screen",
      "promo_100":"is_promotion","coinReceived":"is_churn_prevented","isauth":"is_user_verified",
      "agegroup":"age","registerday":"reg_date","endday":"end_date","Repurchase":"is_repurchase"}
df = mem_raw.rename(columns=rn)

df["age"] = pd.to_numeric(df["age"], errors="coerce")
df = df[df["age"] >= 10].copy()
print(f"age>=10 필터 후: {len(df)}행")

m, s = df["age"].mean(), df["age"].std()
df = df[(df["age"] >= m-3*s) & (df["age"] <= m+3*s)].copy()
print(f"age Z-score 필터 후: {len(df)}행")

df["max_screen"] = pd.to_numeric(df["max_screen"], errors="coerce")
df = df[df["max_screen"].isin([1, 2, 4])].copy()
print(f"max_screen [1,2,4] 필터 후: {len(df)}행")

df["reg_date"] = pd.to_datetime(df["reg_date"], errors="coerce")
df["end_date"]  = pd.to_datetime(df["end_date"],  errors="coerce")
bad = (df["reg_date"] == df["end_date"]) & \
      (df["is_repurchase"].astype(str).str.strip().str.upper().isin(["Y","O"]))
df = df[~bad].copy()
print(f"reg=end & repurchase 필터 후: {len(df)}행")

print(f"\nv2 행수: {len(v2)}행")
print(f"v3 행수: {len(v3)}행")

# v2 중복 USER_KEY 확인
print(f"\nv2 unique USER_KEY: {v2['USER_KEY'].nunique()}")
print(f"v2 중복 USER_KEY 유저수: {v2.duplicated('USER_KEY',keep=False).sum()}")

# 문제 유저가 v2에 있는지
prob_key = 'f7c1f437965dac67f48c685d858e0f73482eeda3e0c6001772a82621f02adfbee337ed612f6d879d2eb2e836d04b96aeab636cbed10f41903c75607a42db55a8'
print(f"\n문제 유저가 v2에 있나: {prob_key[:20]}... -> {prob_key in v2['USER_KEY'].values}")
print(f"문제 유저가 raw step-by-step df에 있나: {prob_key in df['USER_KEY'].values}")
print(f"  raw df에서 행수: {(df['USER_KEY']==prob_key).sum()}")
