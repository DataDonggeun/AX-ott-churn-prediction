"""파이프라인 공통 설정 — 경로, 상수, 피처 계약"""
import os
from pathlib import Path

# ── 경로 ──────────────────────────────────────────────────────────────────────
BASE      = Path(__file__).parent.parent          # ai agent/
DATA_DIR  = BASE / "_data"
CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# 원본 데이터
MEM_PATH  = DATA_DIR / "02_interim" / "260513 feature" / "Membership_final.csv"
VIEW_PATH = DATA_DIR / "01_raw" / "Views_train.csv"

# ── 인증 ───────────────────────────────────────────────────────────────────────
# 빈 문자열(기본값)이면 인증 비활성화 — 로컬/개발 환경 전용
# 운영 시: export PIPELINE_API_KEY=your-secret-key
API_KEY = os.getenv("PIPELINE_API_KEY", "")

# ── 파이프라인 상수 ────────────────────────────────────────────────────────────
COHORT_MIN_DAYS  = 21    # 관측창 완료 기준 (day0~20)
N_SPLITS         = 5     # StratifiedGroupKFold
RANDOM_STATE     = 42
N_OPTUNA_TRIALS  = 30    # Step 07 Optuna trial 수
RETRAIN_MONTHS   = 6     # 모델 재학습 주기 (개월)

# ── 피처 계약 ──────────────────────────────────────────────────────────────────
# is_promotion — split key. overall 모델에서만 feature로 사용.
PROMOTION_FEATURE = "is_promotion"

# payment 기기 피처 — SHAP 계열 분류용
PAYMENT_FEATURES = [
    "payment_is_mobile", "payment_is_pc",
    "payment_is_android", "payment_is_ios",
]

# expanded — step00 출력 기준 최종 피처 목록 (payment 포함)
# VIF=inf 제거 완료: diff_between_w3_w1, active_ratio, reg_hour_night, other_ratio, max_screen
EXPANDED_FEATURES = [
    # 주차별 행동
    "watch_time(min)_w1", "watch_time(min)_w2", "watch_time(min)_w3",
    "watch_session_w1",   "watch_session_w2",   "watch_session_w3",
    "retention_w2_ratio", "retention_w3_ratio",
    "is_cold_start_3d", "is_cold_start_7d",
    "is_only_w1",  "is_only_w2",  "is_only_w3",
    "is_w2_over_50pct", "is_w3_over_50pct", "is_w1_over_50pct",
    "diff_between_w3_w2", "diff_between_w2_w1", "diff_between_w3_w1",
    "recency",     "max_inactive_gap_days",
    "watch_per_day",
    # 사용량 요약
    "total_watch_count",    "unique_movie",        "watch_days",    "active_ratio",
    "avg_watch_time(min)",  "median_watch_time(min)", "std_watch_time(min)",
    "avg_daily_watch_time(min)", "max_watch_time(min)", "max_daily_watch_time(min)",
    "max_daily_sessions",   "avg_gap_between_watch_days",
    "avg_gap_w1_watch_days", "avg_gap_w2_watch_days", "avg_gap_w3_watch_days",
    "avg_rewatch_ratio",    "weekend_watch_ratio",
    "watch_ratio_under_1m", "watch_ratio_under_5m",
    "movie_per_active_day", "max_day_share", "day_count_over_3times",
    "total_watch_time(min)",
    # 콘텍스트
    "age_group", "is_female", "is_male",
    "is_basic", "is_standard", "is_premium",
    "reg_is_weekend",
    "reg_hour_morning", "reg_hour_afternoon", "reg_hour_evening", "reg_hour_night",
    "is_user_verified", "is_churn_prevented",
    # 콘텐츠
    "genre_diversity_count",
    "action_adventure_ratio", "family_animation_ratio", "drama_ratio",
    "thriller_crime_ratio",   "sf_fantasy_ratio",       "comedy_ratio",
    "romance_ratio",          "horror_ratio",            "documentary_ratio",
    "historical_war_ratio",   "other_ratio",
    "new_movie_in_90d_ratio", "new_movie_in_180d_ratio", "new_movie_in_365d_ratio",
    "old_movie_ratio(5y)",    "avg_ott_release_year",
    # payment 기기 피처
    "payment_is_mobile", "payment_is_pc",
    "payment_is_android", "payment_is_ios",
    # scope 조건부: overall에서만 모델 feature로 사용.
    # 데이터셋에는 포함해 scope 필터링(df[df["is_promotion"]==1])에 활용하고,
    # 각 step의 exclude 집합에서 제거 여부를 결정함.
    "is_promotion",
]

# 제외 컬럼 (타겟·식별자·원본 컬럼 — 모델 피처 아님)
EXCLUDED_COLS = [
    "USER_KEY", "is_repurchase", "reg_date", "end_date",
    "product_code", "billing_method", "payment_device",
    "gender", "age", "reg_hour",
    "price", "max_screen",
]

# ── 17x 세그먼트 순서 ──────────────────────────────────────────────────────────
SEGMENT_ORDER = ["A1", "A2", "A3", "B1", "B2", "B3"]
