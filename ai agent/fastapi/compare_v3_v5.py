import pandas as pd
import numpy as np
import os, datetime
from pathlib import Path

BASE = Path(__file__).parent.parent
feat_dir = BASE / "_data" / "02_interim" / "260513 feature"

v3 = pd.read_csv(feat_dir / "Membership_v3.csv", encoding="utf-8-sig")
v5 = pd.read_csv(feat_dir / "Membership_v5.csv", encoding="utf-8-sig")

mt = os.path.getmtime(feat_dir / "Membership_v5.csv")
print(f"v5: {datetime.datetime.fromtimestamp(mt)}")
print(f"v3: {v3.shape},  v5: {v5.shape}")
print(f"v3 unique USER_KEY: {v3['USER_KEY'].nunique()},  v5: {v5['USER_KEY'].nunique()}")

# 중복 USER_KEY 제거 후 비교
v3u = v3.drop_duplicates("USER_KEY")
v5u = v5.drop_duplicates("USER_KEY")
print(f"중복제거 후  v3: {v3u.shape},  v5: {v5u.shape}")

common_keys = set(v3u["USER_KEY"]) & set(v5u["USER_KEY"])
v3s = v3u[v3u["USER_KEY"].isin(common_keys)].set_index("USER_KEY").sort_index()
v5s = v5u[v5u["USER_KEY"].isin(common_keys)].set_index("USER_KEY").sort_index()
print(f"공통 USER_KEY: {len(common_keys)}")

common_num = [c for c in v3s.columns if c in v5s.columns and pd.api.types.is_numeric_dtype(v3s[c])]

real_diffs = []
for col in common_num:
    a = v3s[col].fillna(0)
    b = v5s[col].fillna(0)
    diff_mask = ~np.isclose(a, b, rtol=1e-5, atol=1e-8)
    pct = diff_mask.sum() / len(a) * 100
    if pct > 1.0:
        real_diffs.append((col, round(pct,1), a.mean(), b.mean()))

real_diffs.sort(key=lambda x: -x[1])
print(f"\n근사비교 차이 컬럼 ({len(real_diffs)}개) [rtol=1e-5, >1%]:")
for col, pct, vm3, vm5 in real_diffs:
    print(f"  {pct:5.1f}%  {col:<35}  v3={vm3:.4f}  v5={vm5:.4f}")

# recency 상세 분석
print("\n-- recency 상세 --")
print(f"v3 recency: {v3s['recency'].describe()}")
print(f"v5 recency: {v5s['recency'].describe()}")
diff_rec = v3s["recency"].fillna(0) - v5s["recency"].fillna(0)
print(f"v3-v5 recency 차이 분포:\n{diff_rec[diff_rec!=0].value_counts().head(10)}")
