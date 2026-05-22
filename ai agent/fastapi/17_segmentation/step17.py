"""
Step 17: 세그멘테이션 설계 (Segmentation Design)

역할: FastAPI
목적: Step 15의 payment-removed OOF churn_risk 점수와
      day0~20 행동 규칙을 결합해 7개 대표 세그먼트를 배정한다.
      payment/auth/demographic proxy는 규칙으로 사용하지 않음.
출력: 세그먼트별 행 수·재구매율, 전체 배정 CSV
캐시: step17_segment_summary.json, step17_segment_assignment.csv
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import APIRouter
import pandas as pd
import numpy as np

from config import SEGMENT_ORDER
from cache import is_done, mark_done, save_json, load_json, load_df, save_df

router = APIRouter(prefix="/17", tags=["17. Segmentation"])


def run_segmentation(exp_df: pd.DataFrame, oof_df: pd.DataFrame) -> dict:
    """
    17x 7-세그먼트 배정.

    입력:
      exp_df  — expanded_dataset (행동 피처 포함)
      oof_df  — step15_oof (overall_with_promotion scope, churn_risk)

    우선순위 규칙:
    1. top20% risk & (week3 inactive | drop | retention decay)
    2. top20% risk & (only_w1 | cold_start_weak)
    3. top20% risk & low_activity
    4. 20~50% risk & retention decay
    5. content proxy
    6. stable (하위 20% risk & stable retention)
    7. general_observation (나머지)
    """
    # OOF 점수 (overall_with_promotion, LightGBM 또는 사용 가능한 것)
    oof_scope = oof_df[oof_df["scope"] == "overall_with_promotion"].copy()
    if oof_scope.empty:
        oof_scope = oof_df.drop_duplicates("USER_KEY").copy()

    oof_scope = oof_scope.sort_values("USER_KEY").reset_index(drop=True)
    base = exp_df.copy().reset_index(drop=True)

    # 점수 병합 — dict map으로 직접 매핑 (lambda보다 빠름)
    score_lookup = oof_scope.set_index("USER_KEY")["repurchase_score"]
    base["repurchase_score"] = base["USER_KEY"].map(score_lookup).fillna(0.5)
    base["churn_risk"] = 1 - base["repurchase_score"]

    # 위험도 백분위
    base["_rank"] = base["churn_risk"].rank(method="first", ascending=False)
    base["_pct"]  = base["_rank"] / len(base) * 100

    def col(name, default=0):
        return base[name] if name in base.columns else pd.Series(default, index=base.index)

    # ── 행동 플래그 ────────────────────────────────────────────────────────────
    w3t = col("watch_time(min)_w3"); w3s = col("watch_session_w3")
    w2t = col("watch_time(min)_w2"); d32 = col("diff_between_w3_w2")
    rw2 = col("retention_w2_ratio"); rw3 = col("retention_w3_ratio")
    cs3 = "is_cold_start_3d_fixed" if "is_cold_start_3d_fixed" in base.columns else "is_cold_start_3d"
    cs7 = "is_cold_start_7d_fixed" if "is_cold_start_7d_fixed" in base.columns else "is_cold_start_7d"

    top20  = base["_pct"] <= 20
    f_w3i  = (w3t <= 0) | (w3s <= 0)
    f_w3d  = (d32 < 0) & (w3t < w2t)
    f_rdec = (rw3 < rw2) | (rw3 < 0.5)
    f_ow1  = col("is_only_w1") == 1
    f_cs   = (col(cs3) == 1) | (col(cs7) == 1)
    f_low  = (
        (col("total_watch_time(min)") <= col("total_watch_time(min)").quantile(0.25)) |
        (col("total_watch_count")     <= col("total_watch_count").quantile(0.25))
    )
    f_stab = (base["_pct"] >= 80) & (rw3 >= rw2.fillna(0))

    # 콘텐츠 proxy 플래그
    genre_cols = [
        c for c in base.columns
        if c.endswith("_ratio") and c not in
        {"active_ratio","retention_w2_ratio","retention_w3_ratio",
         "watch_ratio_under_1m","watch_ratio_under_5m"}
    ]
    if genre_cols:
        max_g   = base[genre_cols].max(axis=1)
        f_cont  = max_g >= max_g.quantile(0.75)
    else:
        f_cont = pd.Series(False, index=base.index)
    for nm in ["new_movie_in_365d_ratio","old_movie_ratio(5y)"]:
        if nm in base.columns:
            f_cont = f_cont | (base[nm] >= base[nm].quantile(0.75))

    # ── 우선순위 배정 ──────────────────────────────────────────────────────────
    conditions = [
        top20 & (f_w3i | f_w3d | f_rdec),
        top20 & (f_ow1 | f_cs),
        top20 & f_low,
        ~top20 & (base["_pct"] > 20) & (base["_pct"] <= 50) & f_rdec,
        ~top20 & ~f_low & f_cont,
        f_stab,
    ]
    labels = [
        "high_risk_week3_inactive_or_drop",
        "high_risk_only_w1_or_cold_start_weak",
        "high_risk_low_activity",
        "medium_risk_retention_decay",
        "content_preference_target_candidate",
        "stable_retained_user",
    ]
    base["segment"] = np.select(conditions, labels, default="general_observation")
    base = base.drop(columns=["_rank", "_pct"], errors="ignore")

    # ── 세그먼트 요약 ──────────────────────────────────────────────────────────
    summary = []
    for seg in SEGMENT_ORDER:
        sub = base[base["segment"] == seg]
        summary.append({
            "segment":        seg,
            "row_count":      int(len(sub)),
            "row_share":      round(len(sub) / max(len(base), 1), 4),
            "repurchase_rate": round(float(sub["is_repurchase"].mean()), 4)
                               if "is_repurchase" in sub.columns and len(sub) else None,
            "mean_churn_risk": round(float(sub["churn_risk"].mean()), 4)
                               if len(sub) else None,
        })

    # 배정 결과 저장
    out_cols = [
        "USER_KEY", "is_repurchase", "is_promotion",
        "repurchase_score", "churn_risk", "segment",
    ]
    save_df("step17_segment_assignment",
            base[[c for c in out_cols if c in base.columns]])

    return {
        "status":   "PASS",
        "total_rows": int(len(base)),
        "segments": summary,
        "note": "payment/auth/demographic proxy는 규칙에 미사용. 행동 변수 기반.",
        "summary": " | ".join(
            f"{r['segment'].replace('_',' ')}:{r['row_count']:,}" for r in summary
        ),
    }


@router.post("/segmentation")
def segmentation(force: bool = False):
    """Step 17: 7-세그먼트 배정 (payment-removed OOF + 행동 규칙)."""
    if not force and is_done("step17"):
        cached = load_json("step17_segment_summary")
        if cached:
            cached["from_cache"] = True
            return cached

    exp_df = load_df("expanded_dataset")
    oof_df = load_df("step15_oof")
    if exp_df is None:
        return {"status": "FAIL", "reason": "Step 06 먼저 실행 필요"}
    if oof_df is None:
        return {"status": "FAIL", "reason": "Step 15 먼저 실행 필요"}

    result = run_segmentation(exp_df, oof_df)

    save_json("step17_segment_summary", result)
    mark_done("step17", {
        seg["segment"]: seg["row_count"]
        for seg in result["segments"]
    })

    result["from_cache"] = False
    return result


@router.get("/segment-summary")
def segment_summary():
    """캐시된 세그먼트 요약 조회 (재실행 없이)."""
    cached = load_json("step17_segment_summary")
    if cached:
        cached["from_cache"] = True
        return cached
    return {"status": "NOT_READY", "message": "Step 17 아직 실행 안 됨"}
