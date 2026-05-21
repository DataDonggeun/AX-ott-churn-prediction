"""데이터 로드 및 GradientBoosting 이탈 예측 모듈 — 23,079 코호트 기준"""
import os
import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import train_test_split
import joblib

BASE     = Path(__file__).parent.parent
DATA_DIR = BASE / "_data"
AGENT_DIR = Path(__file__).parent   # 에이전트/ 폴더

_model      = None
_df_mem     = None
_df_view    = None
_activity   = None   # user_activity.csv 캐시
_watch_genre = None  # watch_genre.csv 캐시


def load_watch_genre() -> pd.DataFrame:
    """watch_genre.csv 로드 — 고객별 날짜·장르·시청시간"""
    global _watch_genre
    if _watch_genre is not None:
        return _watch_genre
    path = AGENT_DIR / "watch_genre.csv"
    if path.exists():
        _watch_genre = pd.read_csv(path)
        _watch_genre["USER_KEY"]   = _watch_genre["USER_KEY"].astype(str)
        _watch_genre["watch_date"] = pd.to_datetime(_watch_genre["watch_date"])
    else:
        _watch_genre = pd.DataFrame()
    return _watch_genre


def get_top_genre_as_of(user_key: str, selected_date) -> str:
    """
    선택한 날짜까지 본 영화 기준 상위 장르 반환
    3월 1일 선택 → 3월 1일까지 본 것만 집계
    3월 5일 선택 → 3월 1~5일 누적 집계
    """
    wg  = load_watch_genre()
    sel = pd.Timestamp(selected_date)

    if wg.empty:
        return "drama"

    user_wg = wg[
        (wg["USER_KEY"] == str(user_key)) &
        (wg["watch_date"] <= sel)
    ]

    if user_wg.empty:
        return "drama"

    # 시청 시간 기준 장르 합산
    genre_sum = user_wg.groupby("genre")["watch_time(min)"].sum()

    # Movie_Master 장르명 → TMDB 장르명 매핑
    genre_map = {
        "Drama":            "drama",
        "Action/Adventure": "action",
        "Romance":          "romance",
        "Thriller/Crime":   "thriller",
        "Horror":           "horror",
        "Animation/Family": "family",
        "SF/Fantasy":       "sf",
        "Comedy":           "comedy",
        "Historical/War":   "drama",
        "Documentary":      "drama",
        "Other":            "drama",
    }

    top_raw = genre_sum.idxmax()
    return genre_map.get(top_raw, "drama")


def load_activity() -> pd.DataFrame:
    """사전 계산된 user_activity.csv 로드 (View_History 기반 미접속 일수)"""
    global _activity
    if _activity is not None:
        return _activity
    path = AGENT_DIR / "user_activity.csv"
    if path.exists():
        _activity = pd.read_csv(path)
        _activity["USER_KEY"] = _activity["USER_KEY"].astype(str)
    else:
        _activity = pd.DataFrame()
    return _activity


def load_data():
    global _df_mem, _df_view
    if _df_mem is not None:
        return _df_mem, _df_view

    mem_path  = DATA_DIR / "02_interim" / "260513 feature" / "Membership_v3.csv"
    view_path = DATA_DIR / "01_raw" / "Views_train.csv"

    df = pd.read_csv(mem_path)
    df["reg_date"] = pd.to_datetime(df["reg_date"])
    df["end_date"]  = pd.to_datetime(df["end_date"])
    df["duration_days"] = (df["end_date"] - df["reg_date"]).dt.days

    # 06단계 코호트: duration>=21 + 완전중복 제거 → 23,079행
    df = df[df["duration_days"] >= 21].drop_duplicates().reset_index(drop=True)

    view_df = pd.read_csv(view_path) if view_path.exists() else pd.DataFrame()

    _df_mem  = df
    _df_view = view_df
    return _df_mem, _df_view


MODEL_PATH = AGENT_DIR / "churn_model.pkl"


def train_churn_model():
    global _model
    if _model is not None:
        return _model

    # 저장된 모델 있으면 바로 로드 (0.3초)
    if MODEL_PATH.exists():
        try:
            _model = joblib.load(MODEL_PATH)
            return _model
        except Exception:
            pass  # 파일 깨진 경우 재학습

    # 모델 없으면 학습 (23초, 최초 1회만)
    df, _ = load_data()

    feature_cols = [
        "watch_time(min)_w1", "watch_time(min)_w2", "watch_time(min)_w3",
        "watch_session_w1",   "watch_session_w2",   "watch_session_w3",
        "retention_w2_ratio", "retention_w3_ratio",
        "is_cold_start_3d",   "is_cold_start_7d",
        "is_only_w1",         "is_w1_over_50pct",
        "diff_between_w3_w2", "diff_between_w3_w1", "diff_between_w2_w1",
        "recency",            "max_inactive_gap_days",
        "active_ratio",       "watch_per_day",
        "age",                "is_promotion",       "duration_days",
    ]
    available = [c for c in feature_cols if c in df.columns]
    target    = "is_repurchase"

    if target not in df.columns or len(available) < 5:
        _model = None
        return None

    X = df[available].fillna(0)
    y = df[target]

    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=42)
    model = GradientBoostingClassifier(
        n_estimators=300, max_depth=5, learning_rate=0.05,
        random_state=42,
    )
    model.fit(X_tr, y_tr)
    _model = (model, available)

    # 파일로 저장 → 다음 실행부터 0.3초
    joblib.dump(_model, MODEL_PATH)

    return _model


def get_churn_risk(top_n: int = 20, min_prob: float = 0.5) -> pd.DataFrame:
    """이탈 위험 고객 반환 — churn_risk = 1 - repurchase_score"""
    result = train_churn_model()
    df, _  = load_data()

    if result is None:
        # 모델 없으면 더미 데이터
        return df.head(top_n)[["USER_KEY", "age", "gender", "is_promotion"]].assign(
            churn_risk=0.5, repurchase_score=0.5
        )

    model, cols = result
    X = df[cols].fillna(0)
    proba = model.predict_proba(X)[:, 1]          # repurchase_score
    df = df.copy()
    df["repurchase_score"] = proba
    df["churn_risk"]       = 1 - proba

    high = df[df["churn_risk"] >= min_prob].sort_values("churn_risk", ascending=False)
    return high.head(top_n)


def days_inactive_as_of(row: pd.Series, selected_date) -> int:
    """
    선택한 날짜 기준으로 해당 고객의 미접속 일수 계산
    - 시청 날짜 목록에서 selected_date 이전 마지막 시청일 찾기
    - 마지막 시청일 이후 초기화됨
    """
    import pandas as pd
    sel = pd.Timestamp(selected_date)
    reg = pd.Timestamp(row["reg_date"])
    dates_str = str(row.get("watch_dates", ""))

    if dates_str.strip():
        dates = [pd.Timestamp(d) for d in dates_str.split(",") if d.strip()]
        past  = [d for d in dates if d <= sel]
        if past:
            return (sel - max(past)).days
    # 한번도 안 봤으면 가입일부터 계산
    return (sel - reg).days


def get_inactive_users(selected_date, min_days: int = 14) -> pd.DataFrame:
    """
    선택한 날짜 기준으로 N일 이상 미접속 고객 반환
    날짜가 바뀌면 결과도 바뀜 (동적 계산)
    """
    import pandas as pd
    act = load_activity()
    if act.empty:
        return pd.DataFrame()
    act = act.copy()
    act["days_inactive"] = act.apply(
        lambda r: days_inactive_as_of(r, selected_date), axis=1
    )
    return act[act["days_inactive"] >= min_days]


def get_retention_info(user_key: str) -> dict:
    """특정 고객의 리텐션 정보 반환 (View_History 기반 미접속 일수 사용)"""
    import hashlib
    df, _ = load_data()
    row = df[df["USER_KEY"].astype(str) == str(user_key)]
    if row.empty:
        return {}

    r = row.iloc[0]

    # View_History 기반 실제 미접속 일수 (선택 날짜 기준 동적 계산)
    act = load_activity()
    days_inactive = 7   # 기본값
    if not act.empty:
        act_row = act[act["USER_KEY"] == str(user_key)]
        if not act_row.empty:
            ref = r["end_date"] if pd.notna(r.get("end_date")) else pd.Timestamp("2021-03-20")
            raw = days_inactive_as_of(act_row.iloc[0], ref)
            days_inactive = min(30, max(1, raw))

    # 장르: ratio 값이 실제로 있는 컬럼 우선, 없으면 hash로 다양성 부여
    genre_map = {
        "drama": "drama_ratio", "action": "action_ratio",
        "romance": "romance_ratio", "thriller": "thriller_ratio",
        "horror": "horror_ratio", "family": "family_ratio",
        "sf": "sf_ratio", "comedy": "comedy_ratio",
    }
    genre_values = {g: float(r.get(c, 0)) for g, c in genre_map.items() if c in df.columns}
    max_val = max(genre_values.values(), default=0)

    if max_val > 0.01:
        top_genre = max(genre_values, key=genre_values.get)
    else:
        # 시청 이력 없으면 USER_KEY 해시로 장르 다양화
        genres = list(genre_map.keys())
        idx = int(hashlib.md5(str(user_key).encode()).hexdigest(), 16) % len(genres)
        top_genre = genres[idx]

    return {
        "user_key":      str(user_key),
        "age":           int(r.get("age", 30)),
        "gender":        str(r.get("gender", "M")),
        "days_inactive": days_inactive,
        "top_genre":     top_genre,
        "is_promotion":  int(r.get("is_promotion", 0)),
    }


def get_weekly_segments() -> dict:
    """주간 세그먼트 분류"""
    result = train_churn_model()
    df, _  = load_data()

    if result is not None:
        model, cols = result
        X = df[cols].fillna(0)
        proba = model.predict_proba(X)[:, 1]
        df = df.copy()
        df["churn_risk"] = 1 - proba
    else:
        df = df.copy()
        df["churn_risk"] = 0.5

    high   = df[df["churn_risk"] >= 0.7]
    medium = df[(df["churn_risk"] >= 0.4) & (df["churn_risk"] < 0.7)]
    low    = df[df["churn_risk"] < 0.4]

    prom_high   = high[high["is_promotion"] == 1] if "is_promotion" in high.columns else high
    prom_medium = medium[medium["is_promotion"] == 1] if "is_promotion" in medium.columns else medium

    return {
        "total":           len(df),
        "high_risk":       len(high),
        "medium_risk":     len(medium),
        "low_risk":        len(low),
        "promo_high":      len(prom_high),
        "promo_medium":    len(prom_medium),
        "repurchase_rate": round(df["is_repurchase"].mean() * 100, 1) if "is_repurchase" in df.columns else 0,
    }


def get_summary_stats() -> dict:
    """경영진 요약용 핵심 지표"""
    segs = get_weekly_segments()
    df, _ = load_data()

    promo_rate = df["is_repurchase"][df["is_promotion"] == 1].mean() if "is_promotion" in df.columns else 0
    non_promo_rate = df["is_repurchase"][df["is_promotion"] == 0].mean() if "is_promotion" in df.columns else 0

    return {
        **segs,
        "promo_repurchase_rate":     round(promo_rate * 100, 1),
        "non_promo_repurchase_rate": round(non_promo_rate * 100, 1),
        "cohort_size":               len(df),
    }
