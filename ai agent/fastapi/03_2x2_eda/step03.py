"""
Step 03: 2×2 EDA (Promotion × Repurchase)

역할: FastAPI
목적: 프로모션(0/1) × 재구매(0/1) 4개 코호트의 행 수와
      주요 피처 평균을 계산해 코호트 간 차이를 파악한다.
출력: 4개 코호트 크기·재구매율, 주요 피처 코호트 프로파일
캐시: step03_result.json
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import APIRouter
import pandas as pd
import numpy as np

from cache import is_done, mark_done, save_json, load_json, load_df

router = APIRouter(prefix="/03", tags=["03. 2×2 EDA"])

COHORT_LABELS = {
    (1, 1): "promotion_repurchase",
    (1, 0): "promotion_nonrepurchase",
    (0, 1): "nonpromotion_repurchase",
    (0, 0): "nonpromotion_nonrepurchase",
}

# 2×2 EDA에서 프로파일할 핵심 피처
PROFILE_FEATURES = [
    "watch_time(min)_w1", "watch_time(min)_w2", "watch_time(min)_w3",
    "watch_session_w1",   "watch_session_w2",   "watch_session_w3",
    "retention_w2_ratio", "retention_w3_ratio",
    "recency",
    "is_cold_start_3d", "is_cold_start_7d",
    "is_only_w1",         "diff_between_w3_w2",
]


def run_2x2_eda(df: pd.DataFrame) -> dict:
    """
    4개 코호트 생성 및 프로파일 계산.
    """
    if "is_promotion" not in df.columns or "is_repurchase" not in df.columns:
        return {"status": "FAIL", "reason": "is_promotion 또는 is_repurchase 컬럼 없음"}

    cohorts = {}
    profile_features = [f for f in PROFILE_FEATURES if f in df.columns]

    for (promo, repurchase), label in COHORT_LABELS.items():
        sub = df[(df["is_promotion"] == promo) & (df["is_repurchase"] == repurchase)]
        profile = {}
        for feat in profile_features:
            s = pd.to_numeric(sub[feat], errors="coerce")
            profile[feat] = {
                "mean":   round(float(s.mean()), 4) if s.notna().any() else None,
                "median": round(float(s.median()), 4) if s.notna().any() else None,
            }
        cohorts[label] = {
            "is_promotion":  promo,
            "is_repurchase": repurchase,
            "row_count":     int(len(sub)),
            "row_share":     round(len(sub) / max(len(df), 1), 4),
            "profile":       profile,
        }

    # 프로모션 그룹 내 재구매율
    promo_grp    = df[df["is_promotion"] == 1]["is_repurchase"]
    nonpromo_grp = df[df["is_promotion"] == 0]["is_repurchase"]
    promo_rt     = round(float(promo_grp.mean()), 4)
    nonpromo_rt  = round(float(nonpromo_grp.mean()), 4)

    return {
        "status":               "PASS",
        "total_rows":           int(len(df)),
        "cohorts":              cohorts,
        "promo_repurchase_rate":    promo_rt,
        "nonpromo_repurchase_rate": nonpromo_rt,
        "profile_features_used":   profile_features,
        "interpretation": "관찰된 코호트 차이만 기록. 인과 주장 없음.",
        "summary": (
            f"4개 코호트 생성. "
            f"프로모션 재구매율 {promo_rt:.1%} | "
            f"비프로모션 재구매율 {nonpromo_rt:.1%}."
        ),
    }


@router.post("/2x2-eda")
def eda_2x2():
    """Step 08: 프로모션×재구매 2×2 EDA. 항상 재실행."""

    df = load_df("expanded_dataset")
    if df is None:
        return {"status": "FAIL", "reason": "Step 00 먼저 실행 필요"}

    result = run_2x2_eda(df)

    save_json("step03_result", result)
    mark_done("step03", {"total_rows": result.get("total_rows")})

    result["from_cache"] = False
    return result
