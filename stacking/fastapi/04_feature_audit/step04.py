"""
Step 04: 피처 감사 (Feature Redundancy Pre-Audit)

역할: FastAPI
목적: VIF(다중공선성)·피처 간 고상관 쌍·zero-inflation을 계산해
      모델링 전 주의 피처를 파악한다.
      피처를 제거하지 않고, 경고 리스트만 반환한다.
출력: VIF 상위 10개, 상관계수 0.85 이상 쌍, zero-inflation 50% 이상 피처
캐시: step04_result.json
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import APIRouter
import pandas as pd
import numpy as np

from cache import is_done, mark_done, save_json, load_json, load_df

router = APIRouter(prefix="/04", tags=["04. Feature Audit"])


def _vif_for(X: pd.DataFrame) -> pd.DataFrame:
    """
    최대 30개 수치형 피처에 대해 VIF 계산.
    OLS로 직접 계산 (statsmodels 불필요).
    """
    cols = list(X.columns)
    vif_vals = {}
    values = X.to_numpy(dtype=float)

    for j, col in enumerate(cols):
        y      = values[:, j]
        others = np.delete(values, j, axis=1)
        design = np.column_stack([np.ones(len(y)), others])
        try:
            beta, _, _, _ = np.linalg.lstsq(design, y, rcond=None)
            pred  = design @ beta
            ss_res = float(np.sum((y - pred) ** 2))
            ss_tot = float(np.sum((y - y.mean()) ** 2))
            r2    = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan
            vif_vals[col] = (
                float("inf") if (pd.notna(r2) and r2 >= 0.9999)
                else (1 / (1 - r2) if pd.notna(r2) else np.nan)
            )
        except Exception:
            vif_vals[col] = np.nan

    def _safe_vif(v):
        """inf/nan → JSON 직렬화 가능한 값으로 변환."""
        if pd.isna(v) or (isinstance(v, float) and np.isnan(v)):
            return None
        if np.isinf(v):
            return "inf"   # float inf는 JSON 불가 → 문자열로
        return round(float(v), 2)

    df = pd.DataFrame([
        {"feature": k, "vif": _safe_vif(v)}
        for k, v in vif_vals.items()
    ])
    return df.sort_values("vif", ascending=False, key=lambda s: s.apply(
        lambda x: float("inf") if x == "inf" else (x or 0)
    ))


def run_feature_audit(df: pd.DataFrame) -> dict:
    """
    1) VIF: 수치형 피처 최대 30개
    2) 고상관 쌍: |pearson| >= 0.85
    3) zero-inflation: zero 비율 >= 50%
    """
    exclude = {"USER_KEY", "is_repurchase", "is_promotion"}
    num_cols = [
        c for c in df.select_dtypes(include=[np.number]).columns
        if c not in exclude
    ]

    # ── VIF (최대 30개) ────────────────────────────────────────────────────────
    vif_cols = num_cols[:30]
    X = df[vif_cols].apply(pd.to_numeric, errors="coerce").fillna(0)
    # 분산이 0인 컬럼 제거
    X = X.loc[:, X.std() > 0]

    vif_df  = _vif_for(X)
    top_vif = vif_df.head(10).to_dict("records")

    # ── 고상관 쌍 ─────────────────────────────────────────────────────────────
    corr_mat  = X.corr(method="pearson")
    high_pairs = []
    cols_list  = list(corr_mat.columns)
    for i, a in enumerate(cols_list):
        for b in cols_list[i + 1:]:
            v = corr_mat.loc[a, b]
            if pd.notna(v) and abs(v) >= 0.85:
                high_pairs.append({
                    "feature_a": a,
                    "feature_b": b,
                    "pearson":   round(float(v), 4),
                })
    high_pairs.sort(key=lambda x: abs(x["pearson"]), reverse=True)

    # ── zero-inflation ────────────────────────────────────────────────────────
    zero_inf = []
    for col in num_cols:
        s = pd.to_numeric(df[col], errors="coerce")
        zero_rate = float((s == 0).mean())
        if zero_rate >= 0.5:
            zero_inf.append({"feature": col, "zero_rate": round(zero_rate, 4)})
    zero_inf.sort(key=lambda x: x["zero_rate"], reverse=True)

    inf_count = sum(1 for r in top_vif if r["vif"] == "inf" or (isinstance(r["vif"], (int, float)) and (r["vif"] or 0) >= 20))
    return {
        "status":               "PASS",
        "vif_top10":            top_vif,
        "high_corr_pairs":      high_pairs[:20],
        "high_corr_pair_count": len(high_pairs),
        "zero_inflation_features": zero_inf,
        "note": "피처 제거 없음. 경고 리스트만 기록. vif='inf'는 완전 다중공선성.",
        "summary": (
            f"VIF 극단값 피처 {inf_count}개 | "
            f"고상관 쌍 {len(high_pairs)}개 | "
            f"zero-inflation >= 50% 피처 {len(zero_inf)}개."
        ),
    }


@router.post("/feature-audit")
def feature_audit():
    """Step 04: VIF · 고상관 쌍 · zero-inflation 감사. 항상 재실행."""

    df = load_df("expanded_dataset")
    if df is None:
        return {"status": "FAIL", "reason": "Step 00 먼저 실행 필요"}

    result = run_feature_audit(df)

    save_json("step04_result", result)
    mark_done("step04", {
        "high_corr_pairs": result.get("high_corr_pair_count"),
        "zero_inf_count":  len(result.get("zero_inflation_features", [])),
    })

    result["from_cache"] = False
    return result
