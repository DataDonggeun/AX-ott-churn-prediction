"""
Step 02: 프로모션 EDA (Promotion vs Non-Promotion)

역할: FastAPI
목적: 프로모션·비프로모션 그룹별 재구매율 차이와 주요 피처 평균 차이를 계산한다.
      인과 주장 없이 관찰된 차이만 반환한다.
출력: 그룹별 재구매율, 주요 피처 SMD(표준화 평균 차이) Top 10
캐시: step02_result.json
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import APIRouter
import pandas as pd
import numpy as np

from cache import is_done, mark_done, save_json, load_json, load_df

router = APIRouter(prefix="/02", tags=["02. Promotion EDA"])


def _smd(a: pd.Series, b: pd.Series) -> float:
    """표준화 평균 차이 (Standardized Mean Difference)"""
    a = pd.to_numeric(a, errors="coerce").dropna()
    b = pd.to_numeric(b, errors="coerce").dropna()
    if len(a) == 0 or len(b) == 0:
        return float("nan")
    pooled = np.sqrt((a.var(ddof=1) + b.var(ddof=1)) / 2)
    if pooled == 0:
        return 0.0
    return float((a.mean() - b.mean()) / pooled)


def run_promotion_eda(df: pd.DataFrame) -> dict:
    """
    프로모션·비프로모션 그룹 비교:
    1) 그룹별 행 수 + 재구매율
    2) 주요 피처 SMD 상위 10개
    주의: 인과 주장 없이 관찰된 차이만 기록
    """
    if "is_promotion" not in df.columns:
        return {"status": "FAIL", "reason": "is_promotion 컬럼 없음"}

    promo    = df[df["is_promotion"] == 1]
    nonpromo = df[df["is_promotion"] == 0]

    promo_rt    = float(promo["is_repurchase"].mean()) if "is_repurchase" in df.columns else None
    nonpromo_rt = float(nonpromo["is_repurchase"].mean()) if "is_repurchase" in df.columns else None
    diff_rt     = round(promo_rt - nonpromo_rt, 4) if promo_rt and nonpromo_rt else None

    # 숫자형 피처별 SMD
    exclude = {"USER_KEY", "is_repurchase", "is_promotion"}
    num_cols = [
        c for c in df.select_dtypes(include=[np.number]).columns
        if c not in exclude
    ]

    smd_rows = []
    for col in num_cols:
        s = _smd(promo[col], nonpromo[col])
        smd_rows.append({"feature": col, "smd": round(s, 4)})

    smd_df  = pd.DataFrame(smd_rows).dropna()
    top10   = smd_df.reindex(
        smd_df["smd"].abs().nlargest(10).index
    ).to_dict("records")

    return {
        "status": "PASS",
        "promo_rows":         int(len(promo)),
        "nonpromo_rows":      int(len(nonpromo)),
        "promo_repurchase_rate":    round(promo_rt, 4) if promo_rt else None,
        "nonpromo_repurchase_rate": round(nonpromo_rt, 4) if nonpromo_rt else None,
        "repurchase_rate_diff":     diff_rt,
        "top10_smd_features":       top10,
        "interpretation": "관찰된 차이만 기록. 프로모션이 재구매율 차이를 유발했다는 주장이 아님.",
        "summary": (
            f"프로모션 {len(promo):,}행 재구매율 {promo_rt:.1%} | "
            f"비프로모션 {len(nonpromo):,}행 재구매율 {nonpromo_rt:.1%} | "
            f"격차 {diff_rt:+.4f}."
        ),
    }


@router.post("/promotion-eda")
def promotion_eda():
    """Step 07: 프로모션 vs 비프로모션 EDA. 항상 재실행."""

    df = load_df("expanded_dataset")
    if df is None:
        return {"status": "FAIL", "reason": "Step 00 먼저 실행 필요"}

    result = run_promotion_eda(df)

    save_json("step02_result", result)
    mark_done("step02", {
        "promo_rows":   result.get("promo_rows"),
        "nonpromo_rows": result.get("nonpromo_rows"),
        "rate_diff":    result.get("repurchase_rate_diff"),
    })

    result["from_cache"] = False
    return result
