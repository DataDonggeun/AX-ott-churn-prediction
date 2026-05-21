"""OTT 이탈 방지 파이프라인 FastAPI 서버"""
from fastapi import FastAPI
from pathlib import Path
import pandas as pd
import numpy as np

app = FastAPI(title="OTT 이탈 방지 파이프라인", version="1.0")

BASE     = Path(__file__).parent.parent
DATA_DIR = BASE / "_data"

# ──────────────────────────────────────────────
# 01. 데이터 계약 (Data Contract)
# 새 데이터가 들어왔을 때 써도 되는지 검사
# ──────────────────────────────────────────────
@app.get("/01/data-contract")
def data_contract():
    path = DATA_DIR / "02_interim" / "260513 feature" / "Membership_v3.csv"

    # 파일 존재 확인
    if not path.exists():
        return {"status": "FAIL", "reason": "파일 없음", "path": str(path)}

    df = pd.read_csv(path)

    # 필수 컬럼 목록
    required_cols = [
        "USER_KEY", "reg_date", "end_date", "is_repurchase",
        "is_promotion", "duration_days", "age", "gender",
        "watch_time(min)_w1", "watch_time(min)_w2", "watch_time(min)_w3",
        "watch_session_w1", "watch_session_w2", "watch_session_w3",
        "retention_w2_ratio", "retention_w3_ratio",
        "is_cold_start_3d", "is_cold_start_7d",
        "recency", "active_ratio", "watch_per_day",
        "max_inactive_gap_days",
    ]
    missing_cols  = [c for c in required_cols if c not in df.columns]
    total_cols    = len(df.columns)
    total_rows    = len(df)
    dup_rows      = int(df.duplicated().sum())
    dup_users     = int(df["USER_KEY"].duplicated().sum()) if "USER_KEY" in df.columns else -1
    missing_rates = {c: round(df[c].isna().mean() * 100, 1) for c in df.columns if df[c].isna().any()}
    high_missing  = {c: v for c, v in missing_rates.items() if v > 10}

    # 코호트 필터 적용 시 예상 행 수
    if "duration_days" in df.columns:
        cohort_rows = int((df["duration_days"] >= 21).sum())
    else:
        cohort_rows = -1

    status = "PASS" if not missing_cols and total_rows > 1000 and not high_missing else "WARN"

    return {
        "status":        status,
        "total_rows":    total_rows,
        "total_cols":    total_cols,
        "cohort_rows":   cohort_rows,
        "dup_rows":      dup_rows,
        "dup_users":     dup_users,
        "missing_cols":  missing_cols,
        "high_missing":  high_missing,
        "summary": (
            f"총 {total_rows:,}행 {total_cols}열. "
            f"21일 코호트 예상 {cohort_rows:,}행. "
            f"중복행 {dup_rows}개. "
            f"누락 필수 컬럼 {len(missing_cols)}개."
        )
    }
