"""
Step 06: 데이터셋 생성 (Dataset Generation)

역할: FastAPI
목적: 코호트에 cold_start_fixed·is_basic 등 파생 피처를 추가하고
      conservative / expanded 두 종류의 모델 입력 CSV를 cache에 저장한다.
출력: 두 데이터셋 행/열 수, 피처 목록, cold_start 변경 행 수
캐시: conservative_dataset.csv, expanded_dataset.csv
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import APIRouter
import pandas as pd
import numpy as np

from config import (
    MEM_PATH, VIEW_PATH, COHORT_MIN_DAYS,
    CONSERVATIVE_FEATURES, EXPANDED_FEATURES_NO_PAYMENT, PAYMENT_FEATURES,
)
from cache import is_done, mark_done, save_df, load_df, save_json, load_json

router = APIRouter(prefix="/06", tags=["06. Dataset Generation"])


# ── cold_start_fixed 계산 (06x 핫픽스) ────────────────────────────────────────

def _compute_cold_start_fixed(df: pd.DataFrame) -> pd.DataFrame:
    """
    is_cold_start_3d_fixed = 1 if first_watch_rel_day <= 2
    is_cold_start_7d_fixed = 1 if first_watch_rel_day <= 6
    View_History가 없으면 원본값 fallback.
    """
    df = df.copy()

    if not VIEW_PATH.exists():
        df["is_cold_start_3d_fixed"] = df.get("is_cold_start_3d", 0)
        df["is_cold_start_7d_fixed"] = df.get("is_cold_start_7d", 0)
        return df

    try:
        vh = pd.read_csv(VIEW_PATH)

        if "USER_KEY" not in vh.columns:
            raise ValueError("USER_KEY 없음")

        date_col = next(
            (c for c in ["watch_day", "watch_date", "VIEW_DATE"] if c in vh.columns),
            None,
        )
        if date_col is None:
            raise ValueError("날짜 컬럼 없음")

        # 날짜 파싱 (YYYYMMDD int or string)
        dates = pd.to_datetime(
            vh[date_col].astype(str).str.zfill(8), format="%Y%m%d", errors="coerce"
        )
        if dates.isna().mean() > 0.5:
            dates = pd.to_datetime(vh[date_col], errors="coerce")

        vh_clean = pd.DataFrame({
            "USER_KEY": vh["USER_KEY"].astype(str),
            "watch_date": dates,
        }).dropna(subset=["watch_date"])

        # 각 row에 고유 ID 부여
        df["_rid"] = df.index
        base = df[["_rid", "USER_KEY", "reg_date"]].copy()
        base["_reg"] = pd.to_datetime(base["reg_date"], errors="coerce")

        joined = base.merge(vh_clean, on="USER_KEY", how="left")
        joined["_rel"] = (joined["watch_date"] - joined["_reg"]).dt.days

        in_window = joined[
            joined["_rel"].notna() &
            (joined["_rel"] >= 0) &
            (joined["_rel"] <= 20)
        ]
        first_rel = (
            in_window.groupby("_rid")["_rel"].min().rename("_first")
        )

        df = df.merge(first_rel, on="_rid", how="left")
        df["is_cold_start_3d_fixed"] = (
            df["_first"].notna() & (df["_first"] <= 2)
        ).astype(int)
        df["is_cold_start_7d_fixed"] = (
            df["_first"].notna() & (df["_first"] <= 6)
        ).astype(int)
        df = df.drop(columns=["_rid", "_first"], errors="ignore")

    except Exception:
        df["is_cold_start_3d_fixed"] = df.get("is_cold_start_3d", 0)
        df["is_cold_start_7d_fixed"] = df.get("is_cold_start_7d", 0)

    return df


# ── 데이터셋 생성 핵심 로직 ────────────────────────────────────────────────────

def run_dataset_generation(df_raw: pd.DataFrame) -> dict:
    """
    1) 코호트 필터 (duration >= 21, 중복 제거)
    2) cold_start_fixed 계산
    3) is_basic 생성
    4) conservative / expanded 데이터셋 구성
    """
    # ── 코호트 필터 ────────────────────────────────────────────────────────────
    df = df_raw.copy()
    df["_reg"] = pd.to_datetime(df["reg_date"], errors="coerce")
    df["_end"] = pd.to_datetime(df["end_date"],  errors="coerce")
    df["_dur"] = (df["_end"] - df["_reg"]).dt.days
    df = df[df["_dur"] >= COHORT_MIN_DAYS].drop_duplicates(
        subset=[c for c in df.columns if not c.startswith("_")]
    ).reset_index(drop=True)
    cohort_rows = len(df)

    # ── cold_start_fixed 계산 ──────────────────────────────────────────────────
    df = _compute_cold_start_fixed(df)

    changed_3d = int(
        (df["is_cold_start_3d_fixed"] != df.get("is_cold_start_3d", 0)).sum()
    )
    changed_7d = int(
        (df["is_cold_start_7d_fixed"] != df.get("is_cold_start_7d", 0)).sum()
    )

    # ── is_basic 생성 ──────────────────────────────────────────────────────────
    if "is_standard" in df.columns and "is_premium" in df.columns:
        df["is_basic"] = (
            (df["is_standard"] == 0) & (df["is_premium"] == 0)
        ).astype(int)
    else:
        df["is_basic"] = 0

    # ── conservative 데이터셋 ──────────────────────────────────────────────────
    cons_features = [f for f in CONSERVATIVE_FEATURES if f in df.columns]
    cons_df = df[["USER_KEY", "is_repurchase"] + cons_features].copy()

    # ── expanded 데이터셋 (payment_is_* 제거 15x 결과 반영) ────────────────────
    exp_features = [
        f for f in EXPANDED_FEATURES_NO_PAYMENT
        if f in df.columns and f not in PAYMENT_FEATURES
    ]
    exp_df = df[["USER_KEY", "is_repurchase"] + exp_features].copy()

    # ── 캐시 저장 ──────────────────────────────────────────────────────────────
    save_df("conservative_dataset", cons_df)
    save_df("expanded_dataset",     exp_df)

    return {
        "status":               "PASS",
        "cohort_rows":          cohort_rows,
        "cold_start_3d_changed": changed_3d,
        "cold_start_7d_changed": changed_7d,
        "conservative": {
            "rows":         len(cons_df),
            "feature_count": len(cons_features),
            "features":      cons_features,
        },
        "expanded": {
            "rows":         len(exp_df),
            "feature_count": len(exp_features),
            "features":      exp_features,
        },
        "summary": (
            f"코호트 {cohort_rows:,}행. "
            f"cold_start 3d {changed_3d}행 / 7d {changed_7d}행 수정. "
            f"conservative {len(cons_features)}개 / expanded {len(exp_features)}개 피처."
        ),
    }


@router.post("/dataset-generation")
def dataset_generation(force: bool = False):
    """
    Step 06: 모델 입력 데이터셋 생성.
    가장 무거운 단계 — 처음 실행 시 수 분 소요.
    - force=false: 캐시 데이터셋 있으면 즉시 반환
    - force=true:  재생성
    """
    if not force and is_done("step06"):
        cached = load_json("step06_result")
        if cached:
            cached["from_cache"] = True
            return cached

    if not MEM_PATH.exists():
        return {"status": "FAIL", "reason": "데이터 파일 없음"}

    df_raw = pd.read_csv(MEM_PATH)
    result = run_dataset_generation(df_raw)

    save_json("step06_result", result)
    mark_done("step06", {
        "cohort_rows":    result["cohort_rows"],
        "cons_features":  result["conservative"]["feature_count"],
        "exp_features":   result["expanded"]["feature_count"],
    })

    result["from_cache"] = False
    return result
