"""
Step 07: 세그멘테이션 설계 (Segmentation Design)

역할: FastAPI
목적: Step 05/score의 OOF churn_risk 점수와
      day0~20 행동 규칙을 결합해 6개 대표 세그먼트를 배정한다.
      payment/auth/demographic proxy는 규칙으로 사용하지 않음.
출력: 세그먼트별 행 수·재구매율, 전체 배정 CSV
캐시: step07_segment_summary.json, step07_segment_assignment.csv
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import APIRouter
import pandas as pd
import numpy as np

from config import SEGMENT_ORDER
from cache import is_done, mark_done, save_json, load_json, load_df, save_df

router = APIRouter(prefix="/07", tags=["07. Segmentation"])


def run_segmentation(exp_df: pd.DataFrame, oof_df: pd.DataFrame) -> dict:
    """
    A1~B3 세그먼트 배정.

    기준:
      w1+w2 합계 >= 119분 → 상위군 (A1/A2/A3)
      w1+w2 합계 <  119분 → 하위군 (B1/B2/B3)
      w3 >= 141분          → A1 (상위) / B1 (하위)
      0 < w3 < 141분       → A2 (상위) / B2 (하위)
      w3 = 0               → A3 (상위) / B3 (하위)
    """
    oof_scope = oof_df[oof_df["scope"] == "overall"].copy()
    if oof_scope.empty:
        oof_scope = oof_df.drop_duplicates("USER_KEY").copy()

    base = exp_df.copy().reset_index(drop=True)

    score_lookup = oof_scope.drop_duplicates("USER_KEY").set_index("USER_KEY")["repurchase_score"]
    base["repurchase_score"] = base["USER_KEY"].map(score_lookup).fillna(0.5)
    base["churn_risk"] = 1 - base["repurchase_score"]

    def col(name, default=0):
        return base[name] if name in base.columns else pd.Series(default, index=base.index)

    w1 = col("watch_time(min)_w1")
    w2 = col("watch_time(min)_w2")
    w3 = col("watch_time(min)_w3")

    w1w2 = w1 + w2
    thresh_w1   = w1.median()         # Day 7 기준: w1 중앙값
    thresh_w1w2 = w1w2.median()       # Day 14 기준: w1+w2 중앙값 (약 118분)
    thresh_w3   = w3.quantile(0.75)   # Day 21 기준: w3 75th percentile (약 140분)

    # ── Day 7 개입 플래그 ──────────────────────────────────────────────────────
    base["day7_flag"] = np.where(w1 < thresh_w1, "개입필요", "정상")

    # ── Day 14 개입 플래그 ─────────────────────────────────────────────────────
    base["day14_flag"] = np.where(w1w2 < thresh_w1w2, "개입필요", "정상")

    # ── Day 21 S1~S6 확정 배정 ────────────────────────────────────────────────
    high = w1w2 >= thresh_w1w2
    low  = w1w2 <  thresh_w1w2
    w3_high = w3 >= thresh_w3
    w3_mid  = (w3 > 0) & (w3 < thresh_w3)
    w3_zero = w3 <= 0

    conditions = [
        high & w3_high,   # A1
        high & w3_mid,    # A2
        high & w3_zero,   # A3
        low  & w3_high,   # B1
        low  & w3_mid,    # B2
        low  & w3_zero,   # B3
    ]
    labels = ["A1", "A2", "A3", "B1", "B2", "B3"]
    base["segment"] = np.select(conditions, labels, default="B3")

    # ── 세그먼트 요약 ──────────────────────────────────────────────────────────
    def _seg_stats(sub):
        return {
            "row_count":      int(len(sub)),
            "row_share":      round(len(sub) / max(len(base), 1), 4),
            "repurchase_rate": round(float(sub["is_repurchase"].mean()), 4)
                               if "is_repurchase" in sub.columns and len(sub) and not pd.isna(sub["is_repurchase"].mean()) else None,
            "mean_churn_risk": round(float(sub["churn_risk"].mean()), 4)
                               if len(sub) and not pd.isna(sub["churn_risk"].mean()) else None,
        }

    has_promo = "is_promotion" in base.columns
    summary = []
    for seg in SEGMENT_ORDER:
        sub = base[base["segment"] == seg]
        row = {"segment": seg, **_seg_stats(sub)}
        if has_promo:
            sub_promo    = sub[sub["is_promotion"] == 1]
            sub_nonpromo = sub[sub["is_promotion"] == 0]
            row["promotion"]    = _seg_stats(sub_promo)
            row["nonpromotion"] = _seg_stats(sub_nonpromo)
        summary.append(row)

    # 배정 결과 저장
    out_cols = [
        "USER_KEY", "is_repurchase", "is_promotion",
        "repurchase_score", "churn_risk",
        "day7_flag", "day14_flag", "segment",
    ]
    save_df("step07_segment_assignment",
            base[[c for c in out_cols if c in base.columns]])

    # 주차별 개입 대상 요약
    early_intervention = {
        "day7": {
            "threshold_w1": round(float(thresh_w1), 1),
            "개입필요": int((base["day7_flag"] == "개입필요").sum()),
            "정상":     int((base["day7_flag"] == "정상").sum()),
        },
        "day14": {
            "threshold_w1w2": round(float(thresh_w1w2), 1),
            "개입필요": int((base["day14_flag"] == "개입필요").sum()),
            "정상":     int((base["day14_flag"] == "정상").sum()),
        },
        "day21": {
            "threshold_w3": round(float(thresh_w3), 1),
            "note": "A1~B3 확정 배정",
        },
    }

    return {
        "status":   "PASS",
        "total_rows": int(len(base)),
        "segments": summary,
        "early_intervention": early_intervention,
        "note": f"A1~B3: w1+w2 중앙값({thresh_w1w2:.0f}분) × w3 75th percentile({thresh_w3:.0f}분) 기준 6분할.",
        "summary": " | ".join(
            f"{r['segment'].replace('_',' ')}:{r['row_count']:,}" for r in summary
        ),
    }


@router.post("/segmentation")
def segmentation(force: bool = False):
    """Step 07: 세그먼트 배정. force=false면 캐시 사용."""
    if not force and is_done("step07"):
        cached = load_json("step07_segment_summary")
        if cached:
            cached["from_cache"] = True
            return cached

    exp_df = load_df("expanded_dataset")
    oof_df = load_df("step05_scores")
    if exp_df is None:
        return {"status": "FAIL", "reason": "Step 00 먼저 실행 필요"}
    if oof_df is None:
        return {"status": "FAIL", "reason": "Step 05/score 먼저 실행 필요"}

    result = run_segmentation(exp_df, oof_df)

    save_json("step07_segment_summary", result)
    mark_done("step07", {
        seg["segment"]: seg["row_count"]
        for seg in result["segments"]
    })

    result["from_cache"] = False
    return result


@router.get("/segment-summary")
def segment_summary():
    """캐시된 세그먼트 요약 조회 (재실행 없이)."""
    cached = load_json("step07_segment_summary")
    if cached:
        cached["from_cache"] = True
        return cached
    return {"status": "NOT_READY", "message": "Step 07 아직 실행 안 됨"}
