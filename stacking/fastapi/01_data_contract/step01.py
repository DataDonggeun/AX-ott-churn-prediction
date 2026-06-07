"""
Step 01: 데이터 계약 감사 (Data Contract)

역할: FastAPI
목적: 새 데이터가 들어왔을 때 행 수·열 수·결측치·타입·중복·duration 이상치를 검사해
      다음 단계로 진행 가능한지 판단한다.
출력: status(PASS/WARN/FAIL), 핵심 수치, 요약 문장
캐시: cache/step01_result.json
"""
import sys
from pathlib import Path

# fastapi/ 루트를 경로에 추가 (config, cache import용)
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import APIRouter
import pandas as pd

from config import MEM_PATH
from cache import is_done, mark_done, save_json, load_json

router = APIRouter(prefix="/01", tags=["01. Data Contract"])

# 01단계에서 반드시 존재해야 하는 컬럼 (01_data_contract 계약 기준)
REQUIRED_COLS = [
    "USER_KEY", "reg_date", "end_date",
    "is_repurchase", "is_promotion",
    "age", "gender",
    "watch_time(min)_w1", "watch_time(min)_w2", "watch_time(min)_w3",
    "watch_session_w1",   "watch_session_w2",   "watch_session_w3",
    "retention_w2_ratio", "retention_w3_ratio",
    "is_cold_start_3d",   "is_cold_start_7d",
    "recency",            "watch_per_day",
    "max_inactive_gap_days",
]


def run_data_contract(df: pd.DataFrame) -> dict:
    """
    DataFrame을 받아 계약 감사를 수행하고 결과 dict 반환.
    step01 엔드포인트와 pipeline.py 모두에서 재사용 가능.
    """
    row_count     = len(df)
    col_count     = len(df.columns)
    missing_total = int(df.isna().sum().sum())
    dup_full      = int(df.duplicated().sum())
    dup_user_key  = int(df["USER_KEY"].duplicated().sum()) if "USER_KEY" in df.columns else -1

    # 필수 컬럼 누락 체크
    missing_cols = [c for c in REQUIRED_COLS if c not in df.columns]

    # 결측률 10% 초과 컬럼
    high_missing = {
        c: round(float(df[c].isna().mean()) * 100, 1)
        for c in df.columns
        if df[c].isna().mean() > 0.10
    }

    # duration 이상치 (reg_date ~ end_date 기준)
    dur_lt21 = dur_eq0 = cohort_eligible = -1
    if "reg_date" in df.columns and "end_date" in df.columns:
        dur = (
            pd.to_datetime(df["end_date"],  errors="coerce") -
            pd.to_datetime(df["reg_date"], errors="coerce")
        ).dt.days
        dur_lt21        = int((dur < 21).sum())
        dur_eq0         = int((dur == 0).sum())
        cohort_eligible = int((dur >= 21).sum())

    # 타겟 분포
    target_dist = {}
    if "is_repurchase" in df.columns:
        vc = df["is_repurchase"].value_counts(dropna=False)
        target_dist = {str(k): int(v) for k, v in vc.items()}

    # 프로모션 분포
    promo_dist = {}
    if "is_promotion" in df.columns:
        vc2 = df["is_promotion"].value_counts(dropna=False)
        promo_dist = {str(k): int(v) for k, v in vc2.items()}

    # 상태 판단
    if missing_cols:
        status = "FAIL"
    elif high_missing or missing_total > 0:
        status = "WARN"
    else:
        status = "PASS"

    return {
        "status":          status,
        "row_count":       row_count,
        "col_count":       col_count,
        "missing_total":   missing_total,
        "dup_full_rows":   dup_full,
        "dup_user_key":    dup_user_key,
        "missing_cols":    missing_cols,
        "high_missing":    high_missing,
        "dur_lt21":        dur_lt21,
        "dur_eq0":         dur_eq0,
        "cohort_eligible": cohort_eligible,
        "target_dist":     target_dist,
        "promo_dist":      promo_dist,
        "summary": (
            f"총 {row_count:,}행 {col_count}열. "
            f"21일 코호트 예상 {cohort_eligible:,}행. "
            f"중복행 {dup_full}개. "
            f"누락 필수 컬럼 {len(missing_cols)}개. "
            f"상태: {status}."
        ),
    }


@router.post("/data-contract")
def data_contract():
    """Step 01: 데이터 계약 감사. 항상 재실행."""
    if not MEM_PATH.exists():
        return {"status": "FAIL", "reason": "데이터 파일 없음", "path": str(MEM_PATH)}

    df     = pd.read_csv(MEM_PATH)
    result = run_data_contract(df)

    save_json("step01_result", result)
    mark_done("step01", {
        "row_count":       result["row_count"],
        "cohort_eligible": result["cohort_eligible"],
        "status":          result["status"],
    })

    result["from_cache"] = False
    return result
