from __future__ import annotations

# 실행:
#   cd dashboard
#   python -m streamlit run app_crm_full_workbench.py

"""
100원딜 OTT 이탈 분석 | CRM Full Workbench 후보본

이 앱은 발표/멘토링/Streamlit 시연을 위한 확장 후보본입니다.

고정 원칙
- 공식 입력: 06x_expanded_dataset.csv
- 분석 단위: 고객(person)이 아니라 구독 이벤트(subscription event)
- CRM 시연 모집단: is_promotion == 1 인 100원딜 프로모션 이벤트
- 메인 세그먼트: watch_ratio_under_5m hard gate 제거 기준
  early_formed = (watch_time_min_w1 + watch_time_min_w2) >= 119
  late_state = active(w3 >= 141), weakened(1 <= w3 < 141), dormant(w3 == 0)
- watch_ratio_under_5m은 메시지 보조 플래그이지 세그먼트 탈락 조건이 아님
- w4는 관측 지표이며, CRM 효과 또는 인과를 증명하지 않음
- Gemini는 전략 결정자가 아니라, 승인된 전략과 실제 근거 안에서 문구만 생성
"""

import hashlib
import html
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

try:
    from google import genai
except ImportError:
    genai = None


# =============================================================================
# 0. 설정 및 상수
# =============================================================================
APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
REVIEW_DIR = APP_DIR / "review_outputs"
PATHS = {
    "expanded": DATA_DIR / "06x_expanded_dataset.csv",
    "membership": DATA_DIR / "Membership_v2.csv",
    "mapping": DATA_DIR / "User_Mapping_v2.csv",
    "views": DATA_DIR / "View_History_v2.csv",
    "movies": DATA_DIR / "Movie_Master_v2.csv",
}

EARLY_FORMED_MIN = 119
LATE_ACTIVE_MIN = 141
SHORT_SESSION_THRESHOLD = 0.25
DEFAULT_MODEL = "gemini-2.5-flash"

SEGMENTS = ["S1", "S2", "S3", "S4", "S5", "S6"]
SEGMENT_COLORS = {
    "S1": "#1D9E75",
    "S2": "#378ADD",
    "S3": "#E8743B",
    "S4": "#38A169",
    "S5": "#D4537E",
    "S6": "#C0392B",
}
SEGMENT_INFO: dict[str, dict[str, Any]] = {
    "S1": {
        "name": "초기 소비형성 · 후반활성",
        "label": "유지 보호군",
        "state": "처음부터 충분히 보았고, 3주차에도 시청 흐름이 살아 있는 이벤트입니다.",
        "goal": "과잉 개입을 피하고 현재의 만족스러운 이용 흐름을 보호합니다.",
        "primary": "정보성 후킹",
        "secondary": "리퍼럴 실험",
        "avoid": "복귀 쿠폰 남발, 재촉형 알림, 온보딩 메시지",
    },
    "S2": {
        "name": "초기 소비형성 · 후반약화",
        "label": "이용 약화 회복군",
        "state": "초기에 충분히 보았지만, 3주차에는 이용이 약해진 이벤트입니다.",
        "goal": "보던 흐름을 다시 잇는 다음 시청을 만들 수 있는지 실험합니다.",
        "primary": "이어보기 후킹",
        "secondary": "시청 체크포인트 실험",
        "avoid": "처음 이용 안내, 즉시 할인 압박, 작품 대량 나열",
    },
    "S3": {
        "name": "초기 소비형성 · 후반휴면",
        "label": "초기 관심 재활성화군",
        "state": "초기에 충분히 보았지만, 3주차에는 시청이 완전히 멈춘 이벤트입니다.",
        "goal": "실제 시청 이력을 근거로 복귀 이유를 만들고 재활성화를 실험합니다.",
        "primary": "재활성화 후킹",
        "secondary": "복귀보상 실험",
        "avoid": "첫 진입 안내, 무근거 인기작 추천, 반복 푸시",
    },
    "S4": {
        "name": "초기 소비미형성 · 후반활성",
        "label": "늦은 활성 유지군",
        "state": "초반에는 소비가 약했으나, 3주차에 시청 흐름이 살아난 이벤트입니다.",
        "goal": "최근 형성된 콘텐츠 흐름을 방해하지 않고 유지합니다.",
        "primary": "최근 시청 기반 정보성 후킹",
        "secondary": "리퍼럴 실험",
        "avoid": "초기 이용이 적었다는 이유의 온보딩, 성급한 보상",
    },
    "S5": {
        "name": "초기 소비미형성 · 후반약화",
        "label": "저관여 회복 실험군",
        "state": "처음부터 이용이 약했고, 3주차에도 약한 접촉만 남은 이벤트입니다.",
        "goal": "선택 부담을 줄여 두 번째 유효 시청을 만들 수 있는지 실험합니다.",
        "primary": "선택 축소 후킹",
        "secondary": "시청 체크포인트 실험",
        "avoid": "콘텐츠 나열, 만족 고객처럼 리퍼럴 유도, 고액 할인 일괄 제공",
    },
    "S6": {
        "name": "초기 소비미형성 · 후반휴면",
        "label": "진입 미형성 휴면군",
        "state": "초기 시청이 충분하지 않았고, 3주차에는 시청이 없는 이벤트입니다.",
        "goal": "시청 경험 유무에 따라 첫 진입 또는 재접촉 실험을 분리합니다.",
        "primary": "첫 진입/재접촉 후킹",
        "secondary": "복귀보상 또는 체크포인트 실험",
        "avoid": "모두에게 같은 쿠폰, 시청 근거 없는 이어보기, 반복 알림",
    },
}

LEVER_INFO = {
    "메시지 후킹": {
        "meaning": "콘텐츠를 이유로 다시 열어볼 동기를 제시합니다.",
        "best": "S2·S3·S5·S6의 시청 경험자",
        "measure": "메시지 클릭률, 시청 시작률, holdout 대비 재시청률",
        "caution": "메시지를 보냈기 때문에 유지되었다고 관측 데이터만으로 주장하지 않습니다.",
    },
    "복귀보상": {
        "meaning": "휴면 이후 의미 있는 재시청을 한 고객에게 작은 혜택을 연결하는 실험입니다.",
        "best": "S3, S6 탐색·저소비형",
        "measure": "복귀율, 보상 달성률, 재구매율, 보상 비용 대비 증분효과",
        "caution": "보상 없이도 복귀할 고객에게 불필요하게 혜택을 주지 않도록 대조군이 필요합니다.",
    },
    "시청 체크포인트": {
        "meaning": "단순 출석이 아니라 시청 행동 달성에 보상 후보를 연결합니다.",
        "best": "S2·S5·S6 시청 경험자",
        "measure": "체크포인트 달성률, 두 번째 시청 연결률, 증분 재구매율",
        "caution": "30분·100분은 관측 구간이지 효과가 검증된 최적 목표가 아닙니다.",
    },
    "리퍼럴": {
        "meaning": "현재 경험이 좋은 고객에게 친구 초대 메시지를 제안합니다.",
        "best": "S1·S4와 같이 이용 흐름이 살아 있는 집단",
        "measure": "초대 전송률, 신규 가입률, 추천 유입 재구매율",
        "caution": "연령·성별만으로 추천 가능성을 단정하지 않습니다.",
    },
}

BRANCH_STRATEGIES: dict[str, list[dict[str, str]]] = {
    "S1": [
        {"branch": "꾸준한 탐색형", "condition": "복수 작품 시청, 후반 활성 유지", "crm": "관련 신작·후속작이 실제로 있을 때만 정보성 알림 1회를 보냅니다."},
        {"branch": "한 작품 몰입형", "condition": "작품 수 적음, 후반 활성 유지", "crm": "완주 직후 다음 편이나 같은 시리즈 한 편만 조용히 제시합니다."},
        {"branch": "활성 저하 조짐형", "condition": "활성이지만 w3 < w2", "crm": "할인보다 마지막 콘텐츠 흐름을 잇는 단발 후킹을 우선합니다."},
    ],
    "S2": [
        {"branch": "이어보기 가능형", "condition": "시청 작품 수 적음", "crm": "보던 작품 또는 직접 연결 콘텐츠로 시청 흐름을 다시 붙입니다."},
        {"branch": "복수 탐색 약화형", "condition": "복수 작품 접촉", "crm": "작품을 늘어놓지 않고 가까운 후보 한 편만 제시합니다."},
        {"branch": "짧은 세션 동반형", "condition": "짧은 세션 비율 > 25%", "crm": "선택을 더 단순화하고 체크포인트는 실험군으로만 검토합니다."},
    ],
    "S3": [
        {"branch": "단일·시리즈 휴면형", "condition": "시청 작품 수 적음", "crm": "실제 보았던 작품과 직접 연결되는 다음 콘텐츠로 복귀를 유도합니다."},
        {"branch": "다작 소비 후 휴면형", "condition": "복수 작품 접촉", "crm": "일반 추천 반복 대신 관련 신작이 있을 때만 단발 발송합니다."},
        {"branch": "짧은 세션 동반 휴면형", "condition": "짧은 세션 비율 > 25%", "crm": "간결한 콘텐츠 후킹과 복귀보상을 별도 실험군으로 분리합니다."},
    ],
    "S4": [
        {"branch": "최근 단일 작품 활성형", "condition": "후반 활성, 작품 수 적음", "crm": "최근 활성화를 만든 작품의 다음 흐름만 보호합니다."},
        {"branch": "최근 탐색 활성형", "condition": "후반 활성, 복수 작품", "crm": "푸시보다 홈 큐레이션 중심으로 탐색을 방해하지 않습니다."},
        {"branch": "단타 동반 활성형", "condition": "짧은 세션 비율 > 25%", "crm": "세그먼트는 유지하고 문구 길이와 선택지를 줄입니다."},
    ],
    "S5": [
        {"branch": "단일 접촉형", "condition": "작품 수 적음", "crm": "접촉 작품과 가까운 한 편으로 두 번째 유효 시청을 실험합니다."},
        {"branch": "짧은 탐색 반복형", "condition": "짧은 세션 비율 > 25%", "crm": "작품 선택지를 두 편 이하로 제한합니다."},
        {"branch": "약한 잔존형", "condition": "복수 작품 접촉, w3 > 0", "crm": "저비용 후킹과 시청 체크포인트 실험을 병행 후보로 둡니다."},
    ],
    "S6": [
        {"branch": "무시청형", "condition": "초기 누적 시청 0분", "crm": "이어보기 근거가 없으므로 첫 재생 선택을 쉽게 만드는 메시지만 사용합니다."},
        {"branch": "탐색형", "condition": "초기 누적 시청 1~30분", "crm": "마지막 접촉 콘텐츠에 가까운 한 편을 제시하고 무반응이면 멈춥니다."},
        {"branch": "저소비형", "condition": "초기 누적 시청 31~118분", "crm": "실제 시청 이력과 체크포인트 실험을 연결합니다."},
    ],
}


# =============================================================================
# 1. 스타일
# =============================================================================
st.set_page_config(page_title="100원딜 CRM Full Workbench", page_icon="📺", layout="wide", initial_sidebar_state="expanded")
st.markdown(
    """
<style>
:root { --navy:#101c32; --ink:#122033; --muted:#65748b; --line:#e2e8f0; --bg:#f5f7fb; }
.block-container {padding-top:1.2rem; padding-bottom:2.5rem;}
[data-testid="stSidebar"] {background:#101c32;}
[data-testid="stSidebar"] * {color:#edf3fb;}
.hero {padding:24px 28px; background:linear-gradient(135deg,#13233d,#234b78); color:#fff; border-radius:18px; margin-bottom:16px;}
.hero h1 {font-size:29px; margin:0 0 6px 0; font-weight:800;}
.hero p {margin:0; color:#c4d3e8; line-height:1.65;}
.callout {padding:12px 14px; border-left:4px solid #378ADD; background:#edf5ff; border-radius:0 10px 10px 0; margin:10px 0 16px 0; font-size:13px; line-height:1.65;}
.callout.warn {border-color:#E8743B; background:#fff5eb;}
.callout.safe {border-color:#1D9E75; background:#edfbf5;}
.callout.danger {border-color:#C0392B; background:#fff1f1;}
.stat-card {background:white; border:1px solid #e2e8f0; border-radius:14px; padding:14px; min-height:106px;}
.stat-card .title {font-size:12px; color:#667085; margin-bottom:6px;}
.stat-card .value {font-size:25px; font-weight:800; color:#142238;}
.stat-card .desc {font-size:12px; color:#667085; line-height:1.45; margin-top:4px;}
.segment-card {background:#fff; border:1px solid #e2e8f0; border-radius:15px; padding:15px; min-height:128px;}
.segment-card h4 {margin:0 0 5px 0; font-size:15px;}
.segment-card p {font-size:12px; color:#65748b; line-height:1.5; margin:0;}
.segment-card .n {font-size:23px; font-weight:800; margin-top:10px;}
.section-title {font-size:22px; font-weight:800; margin:4px 0 13px 0; color:#122033;}
.subtle {font-size:12px; color:#667085;}
.tag {display:inline-block; border-radius:99px; padding:3px 9px; font-size:11px; font-weight:700; margin-right:5px;}
.message {background:#fff; border:1px solid #dfe6ef; border-radius:13px; padding:15px; line-height:1.65;}
.small-table {font-size:12px;}
hr {margin:15px 0 !important;}
</style>
""",
    unsafe_allow_html=True,
)


# =============================================================================
# 2. 데이터 로드·검증·가공
# =============================================================================
@dataclass
class DataBundle:
    expanded: pd.DataFrame
    membership: Optional[pd.DataFrame]
    mapping: Optional[pd.DataFrame]
    views: Optional[pd.DataFrame]
    movies: Optional[pd.DataFrame]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


@st.cache_data(show_spinner=False)
def load_csv(path: str) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig")


@st.cache_data(show_spinner=False)
def load_local_bundle() -> DataBundle:
    return DataBundle(
        expanded=load_csv(str(PATHS["expanded"])),
        membership=load_csv(str(PATHS["membership"])) if PATHS["membership"].exists() else None,
        mapping=load_csv(str(PATHS["mapping"])) if PATHS["mapping"].exists() else None,
        views=load_csv(str(PATHS["views"])) if PATHS["views"].exists() else None,
        movies=load_csv(str(PATHS["movies"])) if PATHS["movies"].exists() else None,
    )


def required_columns_missing(df: pd.DataFrame) -> list[str]:
    required = {
        "USER_KEY", "is_repurchase", "is_promotion", "is_user_verified",
        "watch_time_min_w1", "watch_time_min_w2", "watch_time_min_w3",
        "watch_ratio_under_5m", "unique_movie", "total_watch_time_min",
        "watch_days", "genre_diversity_count", "is_basic", "is_standard", "is_premium",
        "age_group", "is_female", "is_male", "is_cold_start_7d_fixed",
    }
    return sorted(required.difference(df.columns))


def enrich_events(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy().reset_index(drop=False).rename(columns={"index": "source_row_id"})
    out["event_id"] = out["source_row_id"].map(lambda x: f"EVT-{x:05d}")
    out["is_churn"] = (out["is_repurchase"] == 0).astype(int)
    out["early_watch_min"] = out["watch_time_min_w1"] + out["watch_time_min_w2"]
    out["early_formed"] = out["early_watch_min"] >= EARLY_FORMED_MIN
    out["short_session_flag"] = out["watch_ratio_under_5m"] > SHORT_SESSION_THRESHOLD
    out["late_state"] = np.select(
        [out["watch_time_min_w3"] >= LATE_ACTIVE_MIN, out["watch_time_min_w3"] > 0],
        ["active", "weakened"], default="dormant",
    )
    mapping = {
        (True, "active"): "S1", (True, "weakened"): "S2", (True, "dormant"): "S3",
        (False, "active"): "S4", (False, "weakened"): "S5", (False, "dormant"): "S6",
    }
    out["segment"] = [mapping[(a, s)] for a, s in zip(out["early_formed"], out["late_state"])]
    hard_early = out["early_formed"] & (~out["short_session_flag"])
    out["segment_hardgate"] = [mapping[(a, s)] for a, s in zip(hard_early, out["late_state"])]
    out["gender"] = np.select([out["is_female"] == 1, out["is_male"] == 1], ["여성", "남성"], default="기타")
    out["plan"] = np.select([out["is_premium"] == 1, out["is_standard"] == 1], ["Premium", "Standard"], default="Basic")
    out["cold_start_unmet"] = out["is_cold_start_7d_fixed"] == 0
    out["w3_drop_from_w2"] = out["watch_time_min_w3"] < out["watch_time_min_w2"]
    return out


def assign_operating_branch(row: pd.Series) -> str:
    seg = row["segment"]
    if seg == "S6":
        if row["early_watch_min"] == 0:
            return "무시청형"
        if row["early_watch_min"] <= 30:
            return "탐색형"
        return "저소비형"
    if seg in {"S1", "S4"}:
        if row["w3_drop_from_w2"]:
            return "활성 저하 조짐형"
        return "한 작품 몰입형" if row["unique_movie"] <= 2 else "꾸준한 탐색형"
    if seg == "S2":
        if row["short_session_flag"]:
            return "짧은 세션 동반형"
        return "이어보기 가능형" if row["unique_movie"] <= 2 else "복수 탐색 약화형"
    if seg == "S3":
        if row["short_session_flag"]:
            return "짧은 세션 동반 휴면형"
        return "단일·시리즈 휴면형" if row["unique_movie"] <= 2 else "다작 소비 후 휴면형"
    if row["short_session_flag"]:
        return "짧은 탐색 반복형"
    return "단일 접촉형" if row["unique_movie"] <= 2 else "약한 잔존형"


def segment_summary(df: pd.DataFrame, segment_col: str = "segment") -> pd.DataFrame:
    result = (
        df.groupby(segment_col, observed=True)
        .agg(
            events=("source_row_id", "count"),
            churn_events=("is_churn", "sum"),
            watch_w1_median=("watch_time_min_w1", "median"),
            watch_w2_median=("watch_time_min_w2", "median"),
            watch_w3_median=("watch_time_min_w3", "median"),
            total_watch_median=("total_watch_time_min", "median"),
            short_flag_rate=("short_session_flag", "mean"),
            cold_start_unmet_rate=("cold_start_unmet", "mean"),
        )
        .reindex(SEGMENTS)
        .reset_index()
        .rename(columns={segment_col: "segment"})
    )
    result["share_pct"] = result["events"] / len(df) * 100
    result["churn_rate_pct"] = result["churn_events"] / result["events"] * 100
    result["label"] = result["segment"].map(lambda s: SEGMENT_INFO[s]["label"])
    result["short_flag_rate"] *= 100
    result["cold_start_unmet_rate"] *= 100
    return result


@st.cache_data(show_spinner=False)
def reconstruct_w4(promo: pd.DataFrame, membership: pd.DataFrame, mapping: pd.DataFrame, views: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Day 21~27 관측 시청을 구독 이벤트에 연결합니다.

    이벤트별로 프로모션/재구매/본인인증이 일치하는 membership reg_date를 선택하고,
    USER_KEY에 다중 USER_NUM이 있는 경우 후보 USER_NUM들의 w4 결과가 동일할 때만 채택합니다.
    이 값은 관측 분석용이며 CRM 효과 추정값이 아닙니다.
    """
    event_cols = ["source_row_id", "USER_KEY", "is_promotion", "is_repurchase", "is_user_verified"]
    mem_cols = ["USER_KEY", "is_promotion", "is_repurchase", "is_user_verified", "reg_date"]
    candidates = promo[event_cols].merge(membership[mem_cols], on=["USER_KEY", "is_promotion", "is_repurchase", "is_user_verified"], how="left")
    candidates["reg_date"] = pd.to_datetime(candidates["reg_date"], errors="coerce")
    candidates = candidates.merge(mapping[["USER_KEY", "USER_NUM"]].drop_duplicates(), on="USER_KEY", how="left")
    candidates = candidates[["source_row_id", "USER_NUM", "reg_date"]].drop_duplicates()

    v = views.copy()
    v["watch_date"] = pd.to_datetime(v["watch_day"].astype(str), format="%Y%m%d", errors="coerce")
    joined = candidates.merge(v[["USER_NUM", "watch_time(min)", "watch_date"]], on="USER_NUM", how="left")
    joined["day_offset"] = (joined["watch_date"] - joined["reg_date"]).dt.days
    w4_rows = joined[(joined["day_offset"] >= 21) & (joined["day_offset"] <= 27)]
    by_candidate = (
        w4_rows.groupby(["source_row_id", "USER_NUM", "reg_date"], dropna=False)["watch_time(min)"]
        .sum().reset_index(name="w4_minutes")
    )
    candidate_result = candidates.merge(by_candidate, on=["source_row_id", "USER_NUM", "reg_date"], how="left")
    candidate_result["w4_minutes"] = candidate_result["w4_minutes"].fillna(0)
    audit = candidate_result.groupby("source_row_id", as_index=False).agg(
        candidate_count=("USER_NUM", "size"),
        distinct_user_num=("USER_NUM", "nunique"),
        w4_min=("w4_minutes", "min"),
        w4_max=("w4_minutes", "max"),
        w4_distinct_values=("w4_minutes", "nunique"),
    )
    audit["w4_resolved"] = audit["w4_distinct_values"] <= 1
    audit["w4_minutes"] = np.where(audit["w4_resolved"], audit["w4_min"], np.nan)
    out = promo.merge(audit[["source_row_id", "candidate_count", "distinct_user_num", "w4_resolved", "w4_minutes"]], on="source_row_id", how="left")
    out["has_w4"] = out["w4_minutes"] > 0
    return out, audit


def w4_segment_summary(df: pd.DataFrame) -> pd.DataFrame:
    known = df[df["w4_resolved"]].copy()
    rows = []
    for seg in SEGMENTS:
        sub = known[known["segment"] == seg]
        yes = sub[sub["has_w4"]]
        no = sub[~sub["has_w4"]]
        rows.append({
            "segment": seg,
            "events": len(sub),
            "w4_view_events": int(sub["has_w4"].sum()),
            "w4_view_rate_pct": sub["has_w4"].mean() * 100 if len(sub) else np.nan,
            "churn_w4_yes_pct": yes["is_churn"].mean() * 100 if len(yes) else np.nan,
            "churn_w4_no_pct": no["is_churn"].mean() * 100 if len(no) else np.nan,
        })
    result = pd.DataFrame(rows)
    result["gap_pct"] = result["churn_w4_no_pct"] - result["churn_w4_yes_pct"]
    return result


def safe_titles_for_event(row: pd.Series, bundle: DataBundle) -> tuple[list[str], str]:
    if any(x is None for x in [bundle.membership, bundle.mapping, bundle.views, bundle.movies]):
        return [], "원천 시청 이력 파일이 없어 작품명 소재를 사용하지 않습니다."
    mem = bundle.membership
    mapped = bundle.mapping
    views = bundle.views
    movies = bundle.movies
    candidate_mem = mem[
        (mem["USER_KEY"] == row["USER_KEY"])
        & (mem["is_promotion"] == row["is_promotion"])
        & (mem["is_repurchase"] == row["is_repurchase"])
        & (mem["is_user_verified"] == row["is_user_verified"])
    ].copy()
    reg_dates = candidate_mem["reg_date"].drop_duplicates()
    user_nums = mapped.loc[mapped["USER_KEY"] == row["USER_KEY"], "USER_NUM"].drop_duplicates()
    if len(reg_dates) != 1 or len(user_nums) != 1:
        return [], "이벤트-시청 이력 연결이 하나로 확정되지 않아 개인화 작품명을 사용하지 않습니다."
    reg_date = pd.to_datetime(reg_dates.iloc[0])
    view = views[views["USER_NUM"] == user_nums.iloc[0]].copy()
    view["watch_date"] = pd.to_datetime(view["watch_day"].astype(str), format="%Y%m%d", errors="coerce")
    view["day_offset"] = (view["watch_date"] - reg_date).dt.days
    view = view[(view["day_offset"] >= 0) & (view["day_offset"] <= 20)]
    if view.empty:
        return [], "Day 0~20 범위에서 사용할 실제 시청작이 없습니다."
    movie_names = movies[["MOVIE_NUM", "movie_title"]].drop_duplicates("MOVIE_NUM")
    joined = view.merge(movie_names, on="MOVIE_NUM", how="left")
    ranked = joined.groupby("movie_title", dropna=True, as_index=False)["watch_time(min)"].sum().sort_values("watch_time(min)", ascending=False)
    titles = ranked["movie_title"].head(3).astype(str).tolist()
    return titles, "개입 전 Day 0~20 실제 시청작 중 시청시간 상위 작품만 문구 소재 후보로 사용합니다."


def get_api_key() -> Optional[str]:
    for key in ["GEMINI_API_KEY", "GOOGLE_API_KEY"]:
        try:
            value = st.secrets.get(key)
        except Exception:
            value = None
        if value:
            return str(value)
        if os.getenv(key):
            return os.getenv(key)
    return None


def build_prompt(row: pd.Series, branch: str, lever: str, titles: list[str], channel: str) -> str:
    allowed_title = ", ".join(titles) if titles else "없음: 작품명을 문구에 넣지 말 것"
    return f"""
당신은 Wavve 100원 프로모션 CRM 문구 작성 보조 도구입니다.
새로운 전략 판단을 하지 말고 아래 입력 범위 안에서만 메시지를 작성하세요.

[승인된 분석 입력]
- 분석 단위: 구독 이벤트
- 세그먼트: {row['segment']} / {SEGMENT_INFO[row['segment']]['name']}
- 실행 분기: {branch}
- CRM 수단: {lever}
- 채널: {channel}
- 개입 전 실제 시청작 소재: {allowed_title}

[작성 제한]
- {channel} 메시지 후보 3개만 작성하세요.
- 실제 시청작 소재가 없으면 특정 작품명이나 취향을 만들어내지 마세요.
- 혜택은 수단이 복귀보상·체크포인트·리퍼럴일 때만 '실험 후보'로 언급하세요.
- 성별, 연령, 이탈 확률, 감정 압박, 죄책감 유발 표현은 쓰지 마세요.
- 할인이 이탈을 막는다고 단정하지 마세요.
- 앱 푸시는 45자 이내로 작성하세요.
- 피해야 할 접근: {SEGMENT_INFO[row['segment']]['avoid']}
""".strip()


def preview_message(row: pd.Series, lever: str, titles: list[str]) -> str:
    title = titles[0] if titles else "오늘 보기 좋은 콘텐츠"
    if lever == "리퍼럴":
        return "함께 보고 싶은 분이 있나요? 친구 초대 혜택 실험을 확인해 보세요."
    if lever == "복귀보상":
        return f"{title}, 다시 이어볼까요? 복귀 혜택 실험 대상 여부를 확인해 보세요."
    if lever == "시청 체크포인트":
        return f"{title}부터 시작해 보세요. 시청 체크포인트 실험을 확인할 수 있습니다."
    if row["segment"] == "S6" and not titles:
        return "오늘 인기 콘텐츠 중 한 편을 골라 첫 시청을 시작해 보세요."
    return f"{title}, 이어서 살펴보실 수 있습니다."


def gemini_generate(prompt: str, api_key: str, model: str) -> str:
    if genai is None:
        raise RuntimeError("google-genai 패키지가 설치되어 있지 않습니다.")
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(model=model, contents=prompt)
    return response.text or "응답 텍스트가 없습니다."


# =============================================================================
# 3. 앱 데이터 준비
# =============================================================================
missing_paths = [str(path) for path in PATHS.values() if not path.exists()]
if not PATHS["expanded"].exists():
    st.error("`data/06x_expanded_dataset.csv`가 필요합니다.")
    st.stop()

bundle = load_local_bundle()
missing_cols = required_columns_missing(bundle.expanded)
if missing_cols:
    st.error(f"공식 입력에 필요한 컬럼이 없습니다: {', '.join(missing_cols)}")
    st.stop()

all_events = enrich_events(bundle.expanded)
promo = all_events[all_events["is_promotion"] == 1].copy().reset_index(drop=True)
promo["branch"] = promo.apply(assign_operating_branch, axis=1)
promo["demo_event_id"] = [f"PROMO-EVT-{i:05d}" for i in range(1, len(promo) + 1)]
nonpromo = all_events[all_events["is_promotion"] == 0].copy().reset_index(drop=True)
summary = segment_summary(promo)
hardgate_summary = segment_summary(promo, "segment_hardgate")
moved = promo[promo["segment"] != promo["segment_hardgate"]].copy()

w4_available = all(x is not None for x in [bundle.membership, bundle.mapping, bundle.views])
if w4_available:
    promo_w4, w4_audit = reconstruct_w4(promo, bundle.membership, bundle.mapping, bundle.views)
    w4_summary = w4_segment_summary(promo_w4)
else:
    promo_w4 = promo.copy()
    w4_audit = pd.DataFrame()
    w4_summary = pd.DataFrame()


# =============================================================================
# 4. 사이드바 / 공통 헤더
# =============================================================================
with st.sidebar:
    st.markdown("## 📺 CRM Full Workbench")
    st.caption("100원딜 프로모션 · 분석에서 실행 시연까지")
    st.markdown("---")
    page = st.radio(
        "메뉴",
        [
            "🏠 Executive Summary",
            "🗂️ 데이터셋 소개",
            "📊 기초 EDA",
            "🧩 세그먼트 설계",
            "🔬 심화 EDA",
            "🗓️ W4 관측 분석",
            "🎯 CRM 플레이북",
            "🤖 Gemini 메시지 시연",
            "🧪 실험 설계",
            "🔍 검증·한계",
        ],
        label_visibility="collapsed",
    )
    st.markdown("---")
    st.caption("공식 시연 모집단")
    st.markdown(f"**프로모션 구독 이벤트 {len(promo):,}건**")
    st.caption("고객 수가 아닌 구독 이벤트 기준")

st.markdown(
    """
<div class="hero">
  <h1>100원딜 CRM Full Workbench</h1>
  <p>공식 행동 데이터로 세그먼트를 설명하고, CRM 전략을 설계하며, Gemini는 승인된 근거 안에서 개인화 메시지 문구만 생성합니다.</p>
</div>
""",
    unsafe_allow_html=True,
)


# =============================================================================
# 5. Executive Summary
# =============================================================================
if page == "🏠 Executive Summary":
    st.markdown("<div class='section-title'>분석 요약</div>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("공식 전체 이벤트", f"{len(all_events):,}건")
    c2.metric("100원딜 이벤트", f"{len(promo):,}건", f"전체의 {len(promo)/len(all_events)*100:.1f}%")
    c3.metric("100원딜 관측 이탈률", f"{promo['is_churn'].mean()*100:.1f}%")
    c4.metric("비프로모션 관측 이탈률", f"{nonpromo['is_churn'].mean()*100:.1f}%")
    st.markdown(
        "<div class='callout warn'><strong>해석 주의:</strong> 프로모션 집단의 이탈률이 다르더라도 가격이 원인이라고 단정할 수 없습니다. 이 대시보드는 행동 상태별 CRM 실험 후보를 설계하는 도구입니다.</div>",
        unsafe_allow_html=True,
    )

    left, right = st.columns([1.15, 1])
    with left:
        fig = px.bar(summary, x="segment", y="churn_rate_pct", color="segment", text=summary["churn_rate_pct"].round(1),
                     color_discrete_map=SEGMENT_COLORS, hover_data=["label", "events"])
        fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        fig.update_layout(title="메인 S1~S6 관측 이탈률", showlegend=False, yaxis_title="이탈률 (%)", xaxis_title="", height=380)
        st.plotly_chart(fig, use_container_width=True)
    with right:
        share = summary.copy()
        fig = px.pie(share, names="segment", values="events", color="segment", color_discrete_map=SEGMENT_COLORS, hole=0.53)
        fig.update_layout(title="100원딜 이벤트 세그먼트 구성", height=380)
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("이 앱에서 보여주는 실행 흐름")
    steps = [
        ("1. 데이터", "공식 06x 데이터에서 100원딜 이벤트를 분리합니다."),
        ("2. 상태", "초기 소비형성 여부와 후반 상태로 S1~S6를 판정합니다."),
        ("3. 전략", "세그먼트와 내부 실행 분기에 맞는 CRM 수단을 선택합니다."),
        ("4. 문구", "Gemini가 허용된 실제 소재 안에서 메시지 문구를 생성합니다."),
    ]
    cols = st.columns(4)
    for col, (title, body) in zip(cols, steps):
        with col:
            st.markdown(f"<div class='stat-card'><div class='title'>{title}</div><div class='desc'>{body}</div></div>", unsafe_allow_html=True)


# =============================================================================
# 6. 데이터셋 소개
# =============================================================================
elif page == "🗂️ 데이터셋 소개":
    st.markdown("<div class='section-title'>데이터셋 소개와 분석 단위</div>", unsafe_allow_html=True)
    st.markdown(
        """
<div class="callout safe">
<strong>핵심:</strong> 공식 분석 단위는 사람이 아니라 <strong>구독 이벤트</strong>입니다. 같은 USER_KEY가 여러 구독 이벤트를 가질 수 있으므로, 화면에서도 ‘명’ 대신 ‘건’을 사용합니다.
</div>
""", unsafe_allow_html=True)
    manifest_rows = []
    for key, path in PATHS.items():
        if path.exists():
            frame = getattr(bundle, key)
            manifest_rows.append({"파일": path.name, "역할": key, "행": len(frame), "열": len(frame.columns), "SHA256 앞16자": sha256(path)[:16]})
    st.dataframe(pd.DataFrame(manifest_rows), use_container_width=True, hide_index=True)

    st.subheader("공식 데이터가 담고 있는 정보")
    groups = pd.DataFrame([
        {"영역": "대상·결과", "예시 컬럼": "is_promotion, is_repurchase, is_user_verified", "사용": "대상 집단과 관측 이탈 정의"},
        {"영역": "주차별 이용", "예시 컬럼": "watch_time_min_w1~w3, retention_w2_ratio", "사용": "메인 세그먼트 상태 판정"},
        {"영역": "시청 습관", "예시 컬럼": "watch_ratio_under_5m, watch_days, recency", "사용": "메시지 보정 플래그·EDA"},
        {"영역": "콘텐츠 폭", "예시 컬럼": "unique_movie, genre_diversity_count, genre ratios", "사용": "탐색 상태 설명"},
        {"영역": "맥락", "예시 컬럼": "is_basic, age_group, is_female/is_male", "사용": "기술 통계만 제공, 개인 추천 근거 금지"},
    ])
    st.dataframe(groups, use_container_width=True, hide_index=True)

    with st.expander("현재 앱에서 의도적으로 사용하지 않는 주장"):
        st.markdown("- 검증된 모델 성능, SHAP, LTV, 기대매출은 원천 산출물이 없으므로 표시하지 않습니다.\n- 작품별 높은 재구매율을 ‘추천하면 효과가 난다’는 근거로 사용하지 않습니다.\n- 연령·성별만으로 메시지 콘텐츠를 결정하지 않습니다.")


# =============================================================================
# 7. 기초 EDA
# =============================================================================
elif page == "📊 기초 EDA":
    st.markdown("<div class='section-title'>기초 EDA: 프로모션과 이용 행동</div>", unsafe_allow_html=True)
    st.markdown("<div class='callout'>아래 수치는 상태 차이를 보여주는 기술 통계입니다. 가격 정책 또는 CRM 효과의 인과 설명은 아닙니다.</div>", unsafe_allow_html=True)

    comp = pd.DataFrame([
        {"집단": "100원딜", "이벤트 수": len(promo), "관측 이탈률": promo["is_churn"].mean()*100, "총시청 중앙값": promo["total_watch_time_min"].median(), "작품수 중앙값": promo["unique_movie"].median()},
        {"집단": "비프로모션", "이벤트 수": len(nonpromo), "관측 이탈률": nonpromo["is_churn"].mean()*100, "총시청 중앙값": nonpromo["total_watch_time_min"].median(), "작품수 중앙값": nonpromo["unique_movie"].median()},
    ])
    st.dataframe(comp.style.format({"관측 이탈률": "{:.1f}%", "총시청 중앙값": "{:.0f}분", "작품수 중앙값": "{:.0f}편"}), use_container_width=True, hide_index=True)

    l, r = st.columns(2)
    with l:
        long = pd.concat([
            promo.assign(집단="100원딜"), nonpromo.assign(집단="비프로모션")
        ]).melt(id_vars=["집단"], value_vars=["watch_time_min_w1", "watch_time_min_w2", "watch_time_min_w3"], var_name="주차", value_name="시청시간")
        long["주차"] = long["주차"].map({"watch_time_min_w1": "1주차", "watch_time_min_w2": "2주차", "watch_time_min_w3": "3주차"})
        med = long.groupby(["집단", "주차"], as_index=False)["시청시간"].median()
        fig = px.line(med, x="주차", y="시청시간", color="집단", markers=True, text="시청시간", title="집단별 주차 시청시간 중앙값")
        fig.update_traces(texttemplate="%{text:.0f}분", textposition="top center")
        fig.update_layout(yaxis_title="중앙값 (분)", height=350)
        st.plotly_chart(fig, use_container_width=True)
    with r:
        plan = promo.groupby("plan", as_index=False).agg(events=("source_row_id", "count"), churn_rate=("is_churn", "mean"))
        plan["churn_rate"] *= 100
        fig = px.bar(plan, x="plan", y="churn_rate", text=plan["churn_rate"].round(1), title="100원딜 요금제별 관측 이탈률")
        fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        fig.update_layout(yaxis_title="이탈률 (%)", xaxis_title="", height=350, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    l, r = st.columns(2)
    with l:
        age = promo.groupby("age_group", as_index=False).agg(events=("source_row_id", "count"), churn_rate=("is_churn", "mean"))
        age["churn_rate"] *= 100
        age["age_group"] = age["age_group"].astype(int).astype(str) + "대"
        fig = px.bar(age, x="age_group", y="churn_rate", text=age["churn_rate"].round(1), title="100원딜 연령대별 관측 이탈률")
        fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        fig.update_layout(yaxis_title="이탈률 (%)", xaxis_title="", height=340)
        st.plotly_chart(fig, use_container_width=True)
    with r:
        gender = promo[promo["gender"].isin(["여성", "남성"])].groupby("gender", as_index=False).agg(events=("source_row_id", "count"), churn_rate=("is_churn", "mean"))
        gender["churn_rate"] *= 100
        fig = px.bar(gender, x="gender", y="churn_rate", text=gender["churn_rate"].round(1), title="100원딜 성별 관측 이탈률")
        fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        fig.update_layout(yaxis_title="이탈률 (%)", xaxis_title="", height=340)
        st.plotly_chart(fig, use_container_width=True)
    st.caption("연령·성별·요금제 차이는 집단 기술 통계입니다. 개인화 메시지의 콘텐츠 소재는 실제 시청 이력을 우선합니다.")


# =============================================================================
# 8. 세그먼트 설계
# =============================================================================
elif page == "🧩 세그먼트 설계":
    st.markdown("<div class='section-title'>세그먼트 설계와 기준 비교</div>", unsafe_allow_html=True)
    st.markdown(
        f"""
<div class="callout safe"><strong>메인 기준:</strong> 초기 누적 시청 <strong>{EARLY_FORMED_MIN}분</strong>과 3주차 상태만으로 S1~S6를 정의합니다. 짧은 세션 비율은 메인 세그먼트 탈락 조건에서 제외하고 실행 보조 플래그로 둡니다.</div>
""", unsafe_allow_html=True)
    rules = pd.DataFrame([
        {"초기 상태": "소비형성", "3주차 상태": "활성 (141분 이상)", "세그먼트": "S1", "CRM 핵심": "흐름 보호"},
        {"초기 상태": "소비형성", "3주차 상태": "약화 (1~140분)", "세그먼트": "S2", "CRM 핵심": "이어보기"},
        {"초기 상태": "소비형성", "3주차 상태": "휴면 (0분)", "세그먼트": "S3", "CRM 핵심": "재활성화"},
        {"초기 상태": "소비미형성", "3주차 상태": "활성 (141분 이상)", "세그먼트": "S4", "CRM 핵심": "늦은 활성 유지"},
        {"초기 상태": "소비미형성", "3주차 상태": "약화 (1~140분)", "세그먼트": "S5", "CRM 핵심": "선택 부담 축소"},
        {"초기 상태": "소비미형성", "3주차 상태": "휴면 (0분)", "세그먼트": "S6", "CRM 핵심": "첫 진입/저소비 회복"},
    ])
    st.dataframe(rules, use_container_width=True, hide_index=True)

    st.subheader("100원딜 이벤트의 메인 세그먼트")
    chart = px.bar(summary, x="segment", y="events", color="segment", color_discrete_map=SEGMENT_COLORS,
                   text="events", hover_data=["label", "churn_rate_pct"])
    chart.update_traces(texttemplate="%{text:,}건", textposition="outside")
    chart.update_layout(showlegend=False, xaxis_title="", yaxis_title="이벤트 수", height=340)
    st.plotly_chart(chart, use_container_width=True)
    show = summary[["segment", "label", "events", "share_pct", "churn_rate_pct", "total_watch_median", "short_flag_rate"]].copy()
    show.columns = ["세그먼트", "역할명", "이벤트 수", "비중(%)", "관측 이탈률(%)", "총 시청 중앙값(분)", "짧은 세션 플래그 비율(%)"]
    st.dataframe(show.style.format({"비중(%)": "{:.1f}", "관측 이탈률(%)": "{:.1f}", "총 시청 중앙값(분)": "{:.0f}", "짧은 세션 플래그 비율(%)": "{:.1f}"}), use_container_width=True, hide_index=True)

    st.subheader("기존 hard gate 기준과의 차이")
    compare = summary[["segment", "events", "churn_rate_pct"]].merge(
        hardgate_summary[["segment", "events", "churn_rate_pct"]], on="segment", suffixes=("_main", "_hardgate")
    )
    compare["이동에 따른 규모 차이"] = compare["events_main"] - compare["events_hardgate"]
    compare = compare.rename(columns={"segment": "세그먼트", "events_main": "메인 기준 건수", "churn_rate_pct_main": "메인 기준 이탈률", "events_hardgate": "hard gate 건수", "churn_rate_pct_hardgate": "hard gate 이탈률"})
    st.dataframe(compare.style.format({"메인 기준 이탈률": "{:.1f}%", "hard gate 이탈률": "{:.1f}%"}), use_container_width=True, hide_index=True)
    st.markdown(f"<div class='callout danger'><strong>기준 영향:</strong> 짧은 세션 비율을 hard gate로 쓰면 프로모션 이벤트 중 <strong>{len(moved):,}건 ({len(moved)/len(promo)*100:.2f}%)</strong>이 다른 세그먼트로 이동합니다. 따라서 이 앱에서는 hard gate 제거 기준을 메인으로 사용합니다.</div>", unsafe_allow_html=True)


# =============================================================================
# 9. 심화 EDA
# =============================================================================
elif page == "🔬 심화 EDA":
    st.markdown("<div class='section-title'>심화 EDA: 세그먼트 안의 행동 차이</div>", unsafe_allow_html=True)
    selected = st.selectbox("세그먼트 선택", SEGMENTS, format_func=lambda s: f"{s} · {SEGMENT_INFO[s]['label']} — {SEGMENT_INFO[s]['name']}")
    sub = promo[promo["segment"] == selected].copy()
    info = SEGMENT_INFO[selected]
    st.markdown(f"<div class='callout'><strong>{selected} · {info['label']}</strong><br>{info['state']}<br><strong>CRM 목표:</strong> {info['goal']}</div>", unsafe_allow_html=True)
    a, b, c, d = st.columns(4)
    a.metric("이벤트 수", f"{len(sub):,}건")
    b.metric("관측 이탈률", f"{sub['is_churn'].mean()*100:.1f}%")
    c.metric("초기 시청 중앙값", f"{sub['early_watch_min'].median():.0f}분")
    d.metric("짧은 세션 플래그", f"{sub['short_session_flag'].mean()*100:.1f}%")

    l, r = st.columns(2)
    with l:
        weekly = sub[["watch_time_min_w1", "watch_time_min_w2", "watch_time_min_w3", "is_churn"]].melt(id_vars="is_churn", var_name="week", value_name="minutes")
        weekly["구분"] = weekly["is_churn"].map({0: "재구매", 1: "이탈"})
        weekly["week"] = weekly["week"].map({"watch_time_min_w1": "1주차", "watch_time_min_w2": "2주차", "watch_time_min_w3": "3주차"})
        med = weekly.groupby(["구분", "week"], as_index=False)["minutes"].median()
        fig = px.line(med, x="week", y="minutes", color="구분", markers=True, text="minutes", title=f"{selected} 이탈/재구매 주차 시청 중앙값")
        fig.update_traces(texttemplate="%{text:.0f}분", textposition="top center")
        fig.update_layout(yaxis_title="중앙값 (분)", xaxis_title="", height=360)
        st.plotly_chart(fig, use_container_width=True)
    with r:
        indicators = pd.DataFrame([
            {"지표": "짧은 세션 플래그", "재구매": sub[sub.is_churn.eq(0)]["short_session_flag"].mean()*100, "이탈": sub[sub.is_churn.eq(1)]["short_session_flag"].mean()*100},
            {"지표": "7일 cold-start 미충족", "재구매": sub[sub.is_churn.eq(0)]["cold_start_unmet"].mean()*100, "이탈": sub[sub.is_churn.eq(1)]["cold_start_unmet"].mean()*100},
            {"지표": "w3가 w2보다 감소", "재구매": sub[sub.is_churn.eq(0)]["w3_drop_from_w2"].mean()*100, "이탈": sub[sub.is_churn.eq(1)]["w3_drop_from_w2"].mean()*100},
        ]).melt(id_vars="지표", var_name="구분", value_name="비율")
        fig = px.bar(indicators, x="지표", y="비율", color="구분", barmode="group", text=indicators["비율"].round(1), title=f"{selected} 보조 플래그 관측 차이")
        fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        fig.update_layout(yaxis_title="비율 (%)", xaxis_title="", height=360)
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("실행 분기별 관측 프로파일")
    sub["branch"] = sub.apply(assign_operating_branch, axis=1)
    branch_summary = sub.groupby("branch", as_index=False).agg(
        events=("source_row_id", "count"), churn_rate=("is_churn", "mean"), early_watch_median=("early_watch_min", "median"), movies_median=("unique_movie", "median")
    )
    branch_summary["churn_rate"] *= 100
    st.dataframe(branch_summary.rename(columns={"branch": "실행 분기", "events": "이벤트 수", "churn_rate": "관측 이탈률(%)", "early_watch_median": "초기 시청 중앙값(분)", "movies_median": "작품 수 중앙값"}).style.format({"관측 이탈률(%)": "{:.1f}", "초기 시청 중앙값(분)": "{:.0f}", "작품 수 중앙값": "{:.0f}"}), use_container_width=True, hide_index=True)
    st.caption("실행 분기는 메시지 방식을 달리하기 위한 운영용 분기입니다. 별도의 공식 세그먼트로 확정한 것이 아닙니다.")


# =============================================================================
# 10. W4 관측 분석
# =============================================================================
elif page == "🗓️ W4 관측 분석":
    st.markdown("<div class='section-title'>W4 관측 분석: 복귀 패턴과 CRM 실험 후보</div>", unsafe_allow_html=True)
    if not w4_available or w4_summary.empty:
        st.warning("w4 원천 시청 파일을 사용할 수 없어 이 화면을 계산할 수 없습니다.")
    else:
        st.markdown("<div class='callout warn'><strong>인과 금지:</strong> 4주차에 시청한 이벤트의 이탈률이 낮다고 해서, 메시지나 보상으로 시청을 만들면 같은 효과가 발생한다고 단정할 수 없습니다. 이 화면은 실험 후보를 설계하기 위한 관측 자료입니다.</div>", unsafe_allow_html=True)
        st.markdown("<div class='callout'><strong>연결 기준 주의:</strong> 이 화면은 프로모션·재구매·본인인증이 일치하는 구독 이벤트의 가입일을 우선 연결한 <strong>앱 내부 재구성값</strong>입니다. Claude review 산출물의 W4 연결 규칙과 2건 차이가 확인되어, 팀 승인 전까지 공식 확정 수치로 부르지 않습니다.</div>", unsafe_allow_html=True)
        resolved = int(promo_w4["w4_resolved"].sum())
        ambiguous = int((~promo_w4["w4_resolved"]).sum())
        a, b, c = st.columns(3)
        a.metric("W4 연결 해석 가능 이벤트", f"{resolved:,}건")
        b.metric("W4 미해결 이벤트", f"{ambiguous:,}건")
        c.metric("W4 시청 관측 이벤트", f"{int(promo_w4['has_w4'].sum()):,}건")
        l, r = st.columns([1.25, 1])
        with l:
            plot = w4_summary.melt(id_vars=["segment"], value_vars=["churn_w4_yes_pct", "churn_w4_no_pct"], var_name="상태", value_name="이탈률")
            plot["상태"] = plot["상태"].map({"churn_w4_yes_pct": "W4 시청 있음", "churn_w4_no_pct": "W4 시청 없음"})
            fig = px.bar(plot, x="segment", y="이탈률", color="상태", barmode="group", text=plot["이탈률"].round(1), title="세그먼트별 W4 시청 유무와 관측 이탈률")
            fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
            fig.update_layout(yaxis_title="관측 이탈률 (%)", xaxis_title="", height=405)
            st.plotly_chart(fig, use_container_width=True)
        with r:
            fig = px.bar(w4_summary, x="segment", y="gap_pct", color="segment", color_discrete_map=SEGMENT_COLORS, text=w4_summary["gap_pct"].round(1), title="W4 미시청 - 시청 이탈률 격차")
            fig.update_traces(texttemplate="%{text:.1f}%p", textposition="outside")
            fig.update_layout(yaxis_title="격차 (%p)", xaxis_title="", showlegend=False, height=405)
            st.plotly_chart(fig, use_container_width=True)
        display = w4_summary.rename(columns={"segment": "세그먼트", "events": "이벤트 수", "w4_view_events": "W4 시청 건수", "w4_view_rate_pct": "W4 시청률(%)", "churn_w4_yes_pct": "W4 시청 이탈률(%)", "churn_w4_no_pct": "W4 미시청 이탈률(%)", "gap_pct": "격차(%p)"})
        st.dataframe(display.style.format({"W4 시청률(%)": "{:.1f}", "W4 시청 이탈률(%)": "{:.1f}", "W4 미시청 이탈률(%)": "{:.1f}", "격차(%p)": "{:.1f}"}), use_container_width=True, hide_index=True)
        with st.expander("W4 연결 감사 정보"):
            st.markdown("- W4 정의: 가입일 기준 Day 21~27 관측 시청시간입니다.\n- 연결 조건: 프로모션·재구매·본인인증 값이 일치하는 멤버십 reg_date와 USER_KEY→USER_NUM 매핑을 사용합니다.\n- 다중 USER_NUM 후보가 있어도 후보별 W4 합계가 다르면 해석에서 제외하도록 설계했습니다.")
            audit_show = pd.DataFrame({
                "항목": ["다중 후보 이벤트", "후보별 W4 값 충돌 이벤트"],
                "값": [int((w4_audit["candidate_count"] > 1).sum()), int((~w4_audit["w4_resolved"]).sum())]
            })
            st.dataframe(audit_show, use_container_width=True, hide_index=True)


# =============================================================================
# 11. CRM 플레이북
# =============================================================================
elif page == "🎯 CRM 플레이북":
    st.markdown("<div class='section-title'>CRM 플레이북: 네 가지 실행 수단</div>", unsafe_allow_html=True)
    cols = st.columns(4)
    for col, (lever, info) in zip(cols, LEVER_INFO.items()):
        with col:
            st.markdown(f"<div class='segment-card'><h4>{lever}</h4><p>{info['meaning']}</p><p style='margin-top:7px;'><strong>주 대상:</strong> {info['best']}</p></div>", unsafe_allow_html=True)
    chosen = st.selectbox("세그먼트별 운영안 보기", SEGMENTS, format_func=lambda s: f"{s} · {SEGMENT_INFO[s]['label']} — {SEGMENT_INFO[s]['name']}")
    meta = SEGMENT_INFO[chosen]
    st.markdown(f"<div class='callout safe'><strong>{chosen} · {meta['label']}</strong><br>{meta['state']}<br><strong>우선 수단:</strong> {meta['primary']} &nbsp; | &nbsp; <strong>보조 실험:</strong> {meta['secondary']}<br><strong>금지선:</strong> {meta['avoid']}</div>", unsafe_allow_html=True)
    cards = st.columns(len(BRANCH_STRATEGIES[chosen]))
    for col, item in zip(cards, BRANCH_STRATEGIES[chosen]):
        with col:
            st.markdown(f"<div class='segment-card'><h4>{item['branch']}</h4><p><strong>조건 예:</strong> {item['condition']}<br><br>{item['crm']}</p></div>", unsafe_allow_html=True)
    st.caption("내부 부류는 CRM 실행을 나누기 위한 operational branch이며, 데이터 분석의 공식 S1~S6를 늘리는 것은 아닙니다.")

    st.subheader("수단별 실험 측정 방법")
    measure = pd.DataFrame([
        {"수단": lever, "적합 대상": info["best"], "측정 지표": info["measure"], "주의": info["caution"]}
        for lever, info in LEVER_INFO.items()
    ])
    st.dataframe(measure, use_container_width=True, hide_index=True)


# =============================================================================
# 12. Gemini 메시지 시연
# =============================================================================
elif page == "🤖 Gemini 메시지 시연":
    st.markdown("<div class='section-title'>Gemini API 기반 개인화 메시지 스튜디오</div>", unsafe_allow_html=True)
    st.markdown("<div class='callout safe'><strong>통제 원칙:</strong> 세그먼트·대상·CRM 수단은 규칙이 결정합니다. Gemini는 개인 식별정보 없이, 실제로 확인된 시청 소재 범위 안에서 문구만 생성합니다.</div>", unsafe_allow_html=True)
    left, right = st.columns([1, 1.15])
    with left:
        selected_seg = st.selectbox("대상 세그먼트", SEGMENTS, format_func=lambda s: f"{s} · {SEGMENT_INFO[s]['label']}")
        examples = promo[promo["segment"] == selected_seg].copy().reset_index(drop=True)
        examples["label"] = examples.apply(lambda r: f"{r['demo_event_id']} · 초기 {int(r['early_watch_min'])}분 / 3주차 {int(r['watch_time_min_w3'])}분 / {assign_operating_branch(r)}", axis=1)
        selected_index = st.selectbox("익명 구독 이벤트 선택", examples.index.tolist(), format_func=lambda i: examples.loc[i, "label"])
        row = examples.loc[selected_index]
        branch = assign_operating_branch(row)
        titles, titles_note = safe_titles_for_event(row, bundle)
        st.markdown(f"**세그먼트:** {selected_seg} · {SEGMENT_INFO[selected_seg]['name']}")
        st.markdown(f"**실행 분기:** {branch}")
        st.markdown(f"**행동 관측:** 초기 `{int(row['early_watch_min'])}분`, 3주차 `{int(row['watch_time_min_w3'])}분`, 작품 `{int(row['unique_movie'])}편`")
        flags = []
        if row["short_session_flag"]: flags.append("짧은 세션 다발")
        if row["cold_start_unmet"]: flags.append("7일 내 첫 시청 미충족")
        st.markdown(f"**보조 플래그:** {', '.join(flags) if flags else '없음'}")
        st.markdown(f"**메시지 소재 후보:** {', '.join(titles) if titles else '작품명 사용 불가'}")
        st.caption(titles_note)
    with right:
        lever_options = [SEGMENT_INFO[selected_seg]["primary"], SEGMENT_INFO[selected_seg]["secondary"]]
        # UI에서 표현은 단순 수단명으로 정리
        normalized = []
        for text in lever_options:
            if "리퍼럴" in text: normalized.append("리퍼럴")
            elif "복귀보상" in text: normalized.append("복귀보상")
            elif "체크포인트" in text: normalized.append("시청 체크포인트")
            else: normalized.append("메시지 후킹")
        normalized = list(dict.fromkeys(normalized))
        lever = st.selectbox("CRM 수단", normalized)
        channel = st.radio("채널", ["앱 푸시", "앱 내 배너", "이메일 제목"], horizontal=True)
        st.markdown(f"<div class='callout'><strong>선택 수단:</strong> {lever}<br>{LEVER_INFO[lever]['meaning'] if lever in LEVER_INFO else ''}</div>", unsafe_allow_html=True)
        preview = preview_message(row, lever, titles)
        st.markdown("**규칙 기반 미리보기**")
        st.markdown(f"<div class='message'>{html.escape(preview)}</div>", unsafe_allow_html=True)
        st.caption("위 문구는 API 결과가 아니라 작동 확인용 preview입니다.")
        prompt = build_prompt(row, branch, lever, titles, channel)
        with st.expander("Gemini에 전달할 통제 프롬프트"):
            st.code(prompt, language="text")
        model = st.text_input("Gemini 모델명", DEFAULT_MODEL)
        api_key = get_api_key()
        if api_key:
            st.success("Gemini API 키가 감지되었습니다. 키 값은 표시하지 않습니다.")
        else:
            st.info("`.streamlit/secrets.toml`에 `GEMINI_API_KEY`를 입력하면 실제 생성 버튼이 활성화됩니다.")
        if st.button("✨ Gemini 문구 생성", disabled=not bool(api_key), use_container_width=True):
            try:
                with st.spinner("메시지 생성 중"):
                    st.session_state["generated_message"] = gemini_generate(prompt, api_key or "", model)
            except Exception as exc:
                st.error(f"Gemini 호출 실패: {exc}")
        if st.session_state.get("generated_message"):
            st.markdown("**Gemini 생성 결과**")
            safe_text = html.escape(st.session_state["generated_message"]).replace("\n", "<br>")
            st.markdown(f"<div class='message'>{safe_text}</div>", unsafe_allow_html=True)
            st.caption("실제 발송 결과가 아니라 메시지 생성 시연입니다. 효과 확인에는 실험이 필요합니다.")


# =============================================================================
# 13. 실험 설계
# =============================================================================
elif page == "🧪 실험 설계":
    st.markdown("<div class='section-title'>실험 설계: CRM 아이디어를 효과 검증으로 연결</div>", unsafe_allow_html=True)
    st.markdown("<div class='callout warn'><strong>현재의 위치:</strong> 메시지·보상·체크포인트·리퍼럴은 모두 실험 후보입니다. 성공 전략이라고 말하려면 무발송 대조군 또는 기존 정책 대조군이 필요합니다.</div>", unsafe_allow_html=True)
    experiment = pd.DataFrame([
        {"실험": "콘텐츠 후킹", "우선 대상": "S2·S3", "실험군": "실제 시청작 기반 단발 문구", "대조군": "무발송 또는 일반 알림", "핵심 지표": "클릭률, 재시청률, 증분 재구매율"},
        {"실험": "복귀보상", "우선 대상": "S3·S6 시청경험형", "실험군": "재시청 달성 후 혜택 안내", "대조군": "동일 후킹, 보상 없음", "핵심 지표": "재시청·재구매 증분, 비용"},
        {"실험": "시청 체크포인트", "우선 대상": "S5·S6 탐색/저소비형", "실험군": "행동 달성 보상 후보", "대조군": "추천만 제공", "핵심 지표": "달성률, 두 번째 시청 연결률"},
        {"실험": "리퍼럴", "우선 대상": "S1·S4", "실험군": "양방향 초대 문구", "대조군": "리퍼럴 노출 없음", "핵심 지표": "초대·가입·유입 품질"},
    ])
    st.dataframe(experiment, use_container_width=True, hide_index=True)
    st.subheader("대시보드에서 구현할 수 있는 시연")
    demo = pd.DataFrame([
        {"단계": "사례 선택", "보여줄 것": "익명 구독 이벤트와 세그먼트/실행 분기"},
        {"단계": "전략 선택", "보여줄 것": "허용된 CRM 수단과 금지선"},
        {"단계": "문구 생성", "보여줄 것": "Gemini 앱 푸시/배너/이메일 제목 후보"},
        {"단계": "검증 설계", "보여줄 것": "실험군·대조군·측정 지표"},
    ])
    st.dataframe(demo, use_container_width=True, hide_index=True)
    st.markdown("<div class='callout safe'><strong>외부 사례 위치:</strong> 시청 행동 기반 보상은 Sling TV Rewards 같은 참고 사례가 존재합니다. 다만 이 사례는 Wavve 효과 입증이 아니라 실험 아이디어의 벤치마킹으로만 사용합니다.</div>", unsafe_allow_html=True)


# =============================================================================
# 14. 검증·한계
# =============================================================================
elif page == "🔍 검증·한계":
    st.markdown("<div class='section-title'>검증 상태와 사용 금지선</div>", unsafe_allow_html=True)
    checks = pd.DataFrame([
        {"항목": "공식 06x 입력 사용", "상태": "적용", "설명": f"{len(all_events):,}개 구독 이벤트"},
        {"항목": "CRM 시연 대상", "상태": "적용", "설명": f"프로모션 이벤트 {len(promo):,}건"},
        {"항목": "메인 세그먼트", "상태": "적용", "설명": "hard gate 제거 S1~S6"},
        {"항목": "짧은 세션 비율", "상태": "적용", "설명": "메시지 보조 플래그로만 사용"},
        {"항목": "W4 관측", "상태": "조건부 적용", "설명": "인과 주장 금지, 연결 감사 포함"},
        {"항목": "작품 재구매율 기반 추천", "상태": "사용 안 함", "설명": "기존 세션 가중 오류·사후 오염 문제"},
        {"항목": "모델 성능/SHAP/LTV", "상태": "사용 안 함", "설명": "이 앱의 근거 파일로 검증되지 않음"},
        {"항목": "Gemini", "상태": "문구 생성만", "설명": "전략·대상 판단 금지"},
    ])
    st.dataframe(checks, use_container_width=True, hide_index=True)
    st.subheader("입력 파일 fingerprint")
    file_rows = []
    for key, path in PATHS.items():
        if path.exists():
            file_rows.append({"파일": path.name, "역할": key, "SHA256": sha256(path), "size_bytes": path.stat().st_size})
    st.dataframe(pd.DataFrame(file_rows), use_container_width=True, hide_index=True)
    with st.expander("Claude HTML에서 재사용하지 않은 내용"):
        st.markdown("- 광일 hard gate를 공식 기준으로 승격하지 않았습니다.\n- S6 724건 누락 구조를 가져오지 않았습니다.\n- 작품·장르별 재구매율 기반 트리거를 사용하지 않았습니다.\n- W4를 CRM 효과처럼 표현하지 않았습니다.\n- 출처 미확인 외부 효과 수치를 사용하지 않았습니다.")
    with st.expander("향후 실제 운영화에 필요한 데이터"):
        st.markdown("- 메시지 발송 여부·발송 시각·채널·템플릿 ID\n- 노출/클릭/앱 오픈/시청 시작 로그\n- 보상 노출·수령·사용 비용 로그\n- 리퍼럴 초대·가입·결제 연결 로그\n- holdout 또는 A/B test assignment")
