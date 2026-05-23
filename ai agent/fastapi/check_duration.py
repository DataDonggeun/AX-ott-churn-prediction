import pandas as pd
from pathlib import Path

BASE = Path(__file__).parent.parent
feat = BASE / "_data/02_interim/260513 feature"

for name in ["Membership_v3.csv", "Membership_v5.csv"]:
    df = pd.read_csv(feat / name, encoding="utf-8-sig")
    df["reg_date"] = pd.to_datetime(df["reg_date"], errors="coerce")
    df["end_date"]  = pd.to_datetime(df["end_date"],  errors="coerce")
    df["_dur"] = (df["end_date"] - df["reg_date"]).dt.days

    total    = len(df)
    lt21     = int((df["_dur"] < 21).sum())
    gte21    = int((df["_dur"] >= 21).sum())

    print(f"=== {name} ===")
    print(f"  전체:           {total:,}행")
    print(f"  duration < 21:  {lt21}행  ({lt21/total*100:.1f}%)")
    print(f"  duration >= 21: {gte21:,}행  → 모델링 코호트")
    print(f"  duration 0일:   {int((df['_dur']==0).sum())}행")
    print()
