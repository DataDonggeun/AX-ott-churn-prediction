"""
Step 03: 관측창 정책 (Observation Window Policy)

역할: FastAPI
목적: duration >= 21 필터 + 완전중복 제거를 적용해
      모델링 코호트 크기와 duration 분포를 반환한다.
출력: 코호트 행 수, duration 분포, 이상치 통계
캐시: step03_result.json
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import APIRouter
import pandas as pd
import numpy as np

from config import MEM_PATH, COHORT_MIN_DAYS
from cache import is_done, mark_done, save_json, load_json, save_df

router = APIRouter(prefix="/03", tags=["03. Observation Window"])


def run_observation_window(df: pd.DataFrame) -> dict:
    """
    관측창 정책 적용:
    1) reg_date ~ end_date 로 duration_days 계산
    2) duration >= 21 필터 (1~3주 관측창 완료 기준)
    3) 완전중복 행 제거
    → 최종 코호트 크기와 각종 통계 반환
    """
    raw_rows = len(df)

    # duration 계산
    df = df.copy()
    df["_reg"] = pd.to_datetime(df["reg_date"], errors="coerce")
    df["_end"] = pd.to_datetime(df["end_date"],  errors="coerce")
    df["_dur"] = (df["_end"] - df["_reg"]).dt.days

    # 1단계: duration < 21 제거
    dur_lt21     = int((df["_dur"] < 21).sum())
    dur_eq0      = int((df["_dur"] == 0).sum())
    after_filter = df[df["_dur"] >= COHORT_MIN_DAYS].copy()

    # 2단계: 완전중복 제거
    before_dedup = len(after_filter)
    after_filter = after_filter.drop_duplicates(
        subset=[c for c in after_filter.columns if not c.startswith("_")]
    ).reset_index(drop=True)
    dup_removed  = before_dedup - len(after_filter)
    cohort_rows  = len(after_filter)

    # duration 분포 (최종 코호트 기준)
    dur_series   = after_filter["_dur"]
    dur_dist     = dur_series.value_counts().sort_index().head(10).to_dict()
    dur_dist     = {str(k): int(v) for k, v in dur_dist.items()}

    # 타겟·프로모션 분포 (최종 코호트)
    target_dist = {}
    promo_dist  = {}
    if "is_repurchase" in after_filter.columns:
        target_dist = {
            str(k): int(v)
            for k, v in after_filter["is_repurchase"].value_counts().items()
        }
    if "is_promotion" in after_filter.columns:
        promo_dist = {
            str(k): int(v)
            for k, v in after_filter["is_promotion"].value_counts().items()
        }

    # 정제된 데이터 CSV 저장 (임시 컬럼 제거)
    save_cols = [c for c in after_filter.columns if not c.startswith("_")]
    after_filter[save_cols].to_csv(MEM_PATH, index=False, encoding="utf-8-sig")

    return {
        "status":           "PASS",
        "raw_rows":         raw_rows,
        "dur_lt21_removed": dur_lt21,
        "dur_eq0_count":    dur_eq0,
        "after_dur_filter": before_dedup,
        "dup_removed":      dup_removed,
        "cohort_rows":      cohort_rows,
        "duration_dist_top10": dur_dist,
        "target_dist":      target_dist,
        "promo_dist":       promo_dist,
        "summary": (
            f"원본 {raw_rows:,}행 → "
            f"duration<21 {dur_lt21}행 제거 → "
            f"중복 {dup_removed}행 제거 → "
            f"최종 코호트 {cohort_rows:,}행. "
            f"Membership_v5.csv 저장 완료."
        ),
    }


@router.post("/observation-window")
def observation_window():
    """Step 03: 관측창 정책 적용 결과 반환. 항상 재실행."""
    if not MEM_PATH.exists():
        return {"status": "FAIL", "reason": "데이터 파일 없음"}

    df     = pd.read_csv(MEM_PATH)
    result = run_observation_window(df)

    save_json("step03_result", result)
    mark_done("step03", {
        "cohort_rows": result["cohort_rows"],
        "dup_removed": result["dup_removed"],
    })

    result["from_cache"] = False
    return result
