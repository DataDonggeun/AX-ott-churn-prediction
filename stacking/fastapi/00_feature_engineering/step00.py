"""
Step 00: 피처 엔지니어링 (Feature Engineering)

역할: FastAPI 파이프라인의 첫 번째 실제 작업 단계.
목적: 원본 4개 파일을 받아 정제 + 피처 계산 후
      Membership_v5.csv (FastAPI step01~17 입력) 를 생성한다.

처리 흐름:
  1. 원본 데이터 로드 (Membership, View_History, Movie_Master, User_Mapping)
  2. 멤버십 원본 정제 (260509_membership_v1 노트북 로직)
     - age: 10 미만 제거, Z-score 이상치 제거
     - max_screen: 1/2/4 외 제거
     - is_user_verified + gender 보정
     - reg_date == end_date AND is_repurchase=='Y' 행 제거
     - price==100 인데 미인증인 경우 → 인증으로 보정
     - payment_device 정규화
     - O/Y → 1/0 인코딩
     - 컬럼명 통일
  3. View_History 기반 피처 계산 (make_features_v3.py 로직)
     - 주차별 시청량/세션
     - 장르/콘텐츠 비율
     - 리텐션, 갭, 리콜런시 등
  4. config.py 컬럼명과 일치하도록 rename
  5. Membership_v5.csv 저장

입력 파일 (DATA_DIR/01_raw/):
  - Membership_train.csv
  - Views_train.csv
  - Movies.csv
  - mapping.csv

출력:
  - DATA_DIR/02_interim/260513 feature/Membership_v5.csv
캐시: step00_result.json
"""
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import APIRouter, Query
import numpy as np
import pandas as pd

from config import DATA_DIR, MEM_PATH, EXPANDED_FEATURES, RANDOM_STATE
from cache import is_done, mark_done, save_json, load_json, save_df

router = APIRouter(prefix="/00", tags=["00. Feature Engineering"])

CUTOFF = 21  # 관측창 day0~20

# ── 입력 파일 경로 ──────────────────────────────────────────────────────────────
RAW_DIR        = DATA_DIR / "01_raw"
MEM_RAW        = RAW_DIR / "Membership_train.csv"
VH_RAW         = RAW_DIR / "Views_train.csv"
TEST_MEM_RAW   = RAW_DIR / "Membership_test.csv"
TEST_VH_RAW    = RAW_DIR / "Views_test.csv"
MOVIE_RAW      = RAW_DIR / "Movies.csv"
UMAP_RAW       = RAW_DIR / "mapping.csv"

# ── 출력 경로 ───────────────────────────────────────────────────────────────────
# 검증용: Membership_v5.csv 로 저장 (v3와 비교 후 문제없으면 v3로 교체)
OUTPUT_PATH      = MEM_PATH.parent / "Membership_final.csv"
TEST_OUTPUT_PATH = MEM_PATH.parent / "Membership_final_2.csv"
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)


# ══════════════════════════════════════════════════════════════════════════════
# 1단계: 멤버십 원본 정제 (260509_membership_v1 노트북 로직)
# ══════════════════════════════════════════════════════════════════════════════

def _clean_membership(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # ── 컬럼명 통일 (260512_name_change.ipynb 기준) ───────────────────────────
    rename_map = {
        "uno":                "USER_KEY",
        "productcode":        "product_code",
        "pgamount":           "price",
        "chargetypeid":       "billing_method",
        "concurrentwatchcount": "max_screen",
        "promo_100":          "is_promotion",
        "coinReceived":       "is_churn_prevented",
        "devicetypeid":       "payment_device",
        "isauth":             "is_user_verified",
        "agegroup":           "age",
        "registerday":        "reg_date",
        "registerhour":       "reg_hour",
        "endday":             "end_date",
        "Repurchase":         "is_repurchase",
        # 혹시 이미 변환된 이름으로 들어올 경우도 대비
        "user_no":            "USER_KEY",
        "product_cd":         "product_code",
        "amount":             "price",
        "concurrent_streams": "max_screen",
        "promotion_yn":       "is_promotion",
        "repurchase":         "is_repurchase",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    # ── age 정제 ──────────────────────────────────────────────────────────────
    # age 컬럼이 있으면 이상치 제거, 없으면 age_group이 이미 있는 것으로 간주
    if "age" in df.columns:
        df["age"] = pd.to_numeric(df["age"], errors="coerce")
        df = df[df["age"] >= 10].copy()
        m, s = df["age"].mean(), df["age"].std()
        df = df[(df["age"] >= m - 3 * s) & (df["age"] <= m + 3 * s)].copy()
    elif "age_group" not in df.columns:
        df["age_group"] = 0  # 둘 다 없으면 기본값

    # ── max_screen 정제 ───────────────────────────────────────────────────────
    df["max_screen"] = pd.to_numeric(df["max_screen"], errors="coerce")
    df = df[df["max_screen"].isin([1, 2, 4])].copy()

    # ── is_user_verified + gender 보정 ────────────────────────────────────────
    # 본인인증='Y' 인데 gender='N' → 최빈값 'F'로 대체
    mask = (df["is_user_verified"].astype(str).str.strip().str.upper() == "Y") & \
           (df["gender"].astype(str).str.strip().str.upper() == "N")
    df.loc[mask, "gender"] = "F"

    # ── reg_date == end_date AND is_repurchase=='Y' 제거 ──────────────────────
    df["reg_date"] = pd.to_datetime(df["reg_date"], errors="coerce")
    df["end_date"]  = pd.to_datetime(df["end_date"],  errors="coerce")
    bad = (df["reg_date"] == df["end_date"]) & \
          (df["is_repurchase"].astype(str).str.strip().str.upper().isin(["Y", "O"]))
    df = df[~bad].copy()

    # ── price==100 + 미인증 → 인증으로 보정 ───────────────────────────────────
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df["is_user_verified"] = df["is_user_verified"].fillna("").astype(str).str.strip()
    fix_mask = (df["price"] == 100) & (df["is_user_verified"].isin(["N", ""]))
    df.loc[fix_mask, "is_user_verified"] = "Y"

    # ── payment_device 정규화 ─────────────────────────────────────────────────
    device_map = {
        "lgchplus": "smarttv", "lgtv": "smarttv",
        "smarttv":  "smarttv", "sstv": "smarttv",
        "ott":      "ott",     "ott_cjhello": "ott",
    }
    df["payment_device"] = (
        df["payment_device"].astype(str).str.strip().str.lower()
        .replace(device_map)
    )

    # ── O/Y → 1/0 인코딩 ──────────────────────────────────────────────────────
    for col in ["is_promotion", "is_churn_prevented"]:
        if col in df.columns:
            df[col] = (
                df[col].fillna("").astype(str).str.strip().str.upper().eq("O")
            ).astype(int)

    for col in ["is_user_verified", "is_repurchase"]:
        if col in df.columns:
            df[col] = (
                df[col].fillna("").astype(str).str.strip().str.upper().eq("Y")
            ).astype(int)

    return df.reset_index(drop=True)


# ══════════════════════════════════════════════════════════════════════════════
# 2단계: 피처 엔지니어링 (변수만드는 방법.csv 기준 완전 재구현)
# ══════════════════════════════════════════════════════════════════════════════

def _engineer_features(mem: pd.DataFrame,
                        vh_raw: pd.DataFrame,
                        movie: pd.DataFrame,
                        umap: pd.DataFrame) -> pd.DataFrame:
    """변수만드는 방법.csv 기준으로 완전 구현."""
    df = mem.copy()

    # ── 멤버십 기본 파생 ──────────────────────────────────────────────────────
    df["is_basic"]    = (df["max_screen"] == 1).astype(int)
    df["is_standard"] = (df["max_screen"] == 2).astype(int)
    df["is_premium"]  = (df["max_screen"] == 4).astype(int)

    # ── 인구통계 ──────────────────────────────────────────────────────────────
    if "age" in df.columns:
        df["age_group"] = (pd.to_numeric(df["age"], errors="coerce") // 10 * 10).fillna(0).astype(int)
    elif "age_group" not in df.columns:
        df["age_group"] = 0
    df["is_female"] = (df["gender"].astype(str).str.upper() == "F").astype(int)
    df["is_male"]   = (df["gender"].astype(str).str.upper() == "M").astype(int)

    # ── 결제 디바이스 플래그 ──────────────────────────────────────────────────
    dev = df.get("payment_device", pd.Series("", index=df.index)).astype(str).str.lower()
    df["payment_is_mobile"]  = (dev == "mobile").astype(int)
    df["payment_is_pc"]      = (dev == "pc").astype(int)
    df["payment_is_android"] = (dev == "android").astype(int)
    df["payment_is_ios"]     = (dev == "ios").astype(int)

    # ── 가입 시간대 ────────────────────────────────────────────────────────────
    df["reg_is_weekend"] = (df["reg_date"].dt.weekday >= 5).astype(int)
    h = pd.to_numeric(df.get("reg_hour", pd.Series(-1, index=df.index)), errors="coerce").fillna(-1)
    df["reg_hour_morning"]   = ((h >= 6)  & (h <= 11)).astype(int)
    df["reg_hour_afternoon"] = ((h >= 12) & (h <= 17)).astype(int)
    df["reg_hour_evening"]   = ((h >= 18) & (h <= 23)).astype(int)
    df["reg_hour_night"]     = ((h >= 0)  & (h <= 5)).astype(int)

    # ── View_History 전처리 ────────────────────────────────────────────────────
    vh = vh_raw.copy()
    umap = umap.rename(columns={"uid": "USER_KEY", "USER_ID": "USER_NUM"})
    vh = vh.rename(columns={
        "USER_ID":   "USER_NUM",
        "MOVIE_ID":  "MOVIE_NUM",
        "DURATION":  "watch_time(min)",
        "WATCH_DAY": "watch_day",
        "WATCH_SEQ": "watch_seq",
    })

    if "watch_day" not in vh.columns:
        return df

    # 완전 중복 행 제거 (동일 USER+MOVIE+DAY+SEQ+DURATION)
    vh = vh.drop_duplicates()

    vh["watch_date"] = pd.to_datetime(
        vh["watch_day"].astype(str).str.zfill(8), format="%Y%m%d", errors="coerce"
    )
    if vh["watch_date"].isna().mean() > 0.5:
        return df

    # USER_NUM → USER_KEY
    if "USER_NUM" in vh.columns and "USER_KEY" not in vh.columns:
        vh = vh.merge(umap[["USER_NUM", "USER_KEY"]], on="USER_NUM", how="left")

    # reg_date 조인 — USER_KEY 중복 방지 (중복 시 vh 행이 불어남)
    vh = vh.merge(df[["USER_KEY", "reg_date"]].drop_duplicates("USER_KEY"), on="USER_KEY", how="left")
    vh["obs_day"]      = (vh["watch_date"] - vh["reg_date"]).dt.days
    vh["watch_rel_day"] = vh["obs_day"] + 1

    # 관측창 필터: obs_day 0~20 (watch_rel_day 1~21)
    vh = vh[(vh["obs_day"] >= 0) & (vh["obs_day"] <= 20)].copy()
    vh["is_weekend"]   = vh["watch_date"].dt.weekday >= 5
    vh["watch_date_d"] = vh["watch_date"].dt.date

    # 영화 정보 조인
    movie = movie.rename(columns={
        "MOVIE_ID":      "MOVIE_NUM",
        "RELEASE_MONTH": "ott_release_month",
        "Category":      "genre",
        "category":      "genre",
    })
    if "MOVIE_NUM" in vh.columns and "MOVIE_NUM" in movie.columns:
        movie_cols = ["MOVIE_NUM"] + [c for c in ["genre","ott_release_month"] if c in movie.columns]
        vh = vh.merge(movie[movie_cols].drop_duplicates("MOVIE_NUM"), on="MOVIE_NUM", how="left")

    wc = "watch_time(min)"
    if wc not in vh.columns:
        return df

    grp = vh.groupby("USER_KEY")

    # ── 시청 기본 ────────────────────────────────────────────────────────────
    basic = grp.agg(
        total_watch_count=(wc, "count"),
        unique_movie=("MOVIE_NUM", "nunique"),
        watch_days=("watch_date_d", "nunique"),
        **{"total_watch_time(min)": (wc, "sum")},
    ).reset_index()
    basic["active_ratio"]  = basic["watch_days"] / 21
    basic["watch_per_day"] = basic["total_watch_count"] / basic["watch_days"].clip(lower=1)
    df = df.merge(basic, on="USER_KEY", how="left")

    # ── 시청 시간 통계 ────────────────────────────────────────────────────────
    tdist = grp[wc].agg(
        **{"avg_watch_time(min)":    "mean",
           "median_watch_time(min)": "median",
           "std_watch_time(min)":    lambda x: x.std(ddof=1),
           "max_watch_time(min)":    "max"},
    ).reset_index()
    df = df.merge(tdist, on="USER_KEY", how="left")

    # ── 일별 집계 ─────────────────────────────────────────────────────────────
    daily = vh.groupby(["USER_KEY", "watch_date_d"])[wc].agg(
        daily_sum="sum", daily_count="count"
    ).reset_index()
    dagg = daily.groupby("USER_KEY").agg(
        **{"avg_daily_watch_time(min)": ("daily_sum", "mean"),
           "max_daily_watch_time(min)": ("daily_sum", "max"),
           "max_daily_sessions":        ("daily_count", "max")},
    ).reset_index()
    df = df.merge(dagg, on="USER_KEY", how="left")

    # ── 리콜런시: 20 - last_obs_day (원본 make_features_v3.py 기준) ──────────
    rec = grp["obs_day"].max().reset_index()
    rec["recency"] = 20 - rec["obs_day"]
    df = df.merge(rec[["USER_KEY", "recency"]], on="USER_KEY", how="left")
    df["recency"] = df["recency"].fillna(21)  # 미시청자: 관측창 전체 미시청 = 21

    # ── 갭 계산 ───────────────────────────────────────────────────────────────
    # obs_day 정수 기반 갭 계산 (원본 make_features_v3.py 동일)
    def _avg_gap(x):
        d = sorted(x.unique())
        return float(np.mean(np.diff(d))) if len(d) >= 2 else np.nan

    def _max_gap(x):
        d = sorted(x.unique())
        return float(max(np.diff(d))) if len(d) >= 2 else np.nan

    tmp = grp["obs_day"].apply(_avg_gap).reset_index()
    tmp.columns = ["USER_KEY", "avg_gap_between_watch_days"]
    df = df.merge(tmp, on="USER_KEY", how="left")

    tmp = grp["obs_day"].apply(_max_gap).reset_index()
    tmp.columns = ["USER_KEY", "max_inactive_gap_days"]
    df = df.merge(tmp, on="USER_KEY", how="left")

    for w, (lo, hi) in enumerate([(0,6),(7,13),(14,20)], 1):
        wvh = vh[(vh["obs_day"] >= lo) & (vh["obs_day"] <= hi)]
        tmp = wvh.groupby("USER_KEY")["obs_day"].apply(_avg_gap).reset_index()
        tmp.columns = ["USER_KEY", f"avg_gap_w{w}_watch_days"]
        df = df.merge(tmp, on="USER_KEY", how="left")

    # ── 재시청 / 주말 / under 1m·5m ──────────────────────────────────────────
    tc = grp.size().reset_index(name="tc")
    if "MOVIE_NUM" in vh.columns:
        rw  = vh.groupby(["USER_KEY","MOVIE_NUM"]).size().reset_index(name="cnt")
        rw  = rw[rw["cnt"] >= 2].groupby("USER_KEY").size().reset_index(name="rw")
        rwr = tc.merge(rw, on="USER_KEY", how="left").fillna(0)
        rwr["avg_rewatch_ratio"] = rwr["rw"] / rwr["tc"].clip(lower=1)
        df  = df.merge(rwr[["USER_KEY","avg_rewatch_ratio"]], on="USER_KEY", how="left")

    df = df.merge(grp["is_weekend"].mean().reset_index(name="weekend_watch_ratio"), on="USER_KEY", how="left")

    for mins, col in [(1,"watch_ratio_under_1m"),(5,"watch_ratio_under_5m")]:
        tmp = vh.groupby("USER_KEY")[wc].apply(lambda x: (x <= mins).mean()).reset_index(name=col)
        df = df.merge(tmp, on="USER_KEY", how="left")

    # ── 온보딩 cold_start (watch_rel_day 1-based 기준) ────────────────────────
    first = grp["watch_rel_day"].min().reset_index(name="first_watch_rel_day")
    df = df.merge(first, on="USER_KEY", how="left")
    # CSV 기준: days = first_watch_rel_day - 1, is_cold_start_3d: days<=3, 7d: days<=7
    df["is_cold_start_3d"] = ((df["first_watch_rel_day"] - 1) <= 3).astype(int)
    df["is_cold_start_7d"] = ((df["first_watch_rel_day"] - 1) <= 7).astype(int)
    df = df.drop(columns=["first_watch_rel_day"], errors="ignore")

    # ── 시청 강도 ─────────────────────────────────────────────────────────────
    df["movie_per_active_day"] = np.where(
        df["watch_days"] > 0, df["unique_movie"] / df["watch_days"].clip(lower=1), 0
    )
    df["max_day_share"] = np.where(
        df["total_watch_time(min)"] > 0,
        df["max_daily_watch_time(min)"] / df["total_watch_time(min)"],
        0
    )
    tmp = daily[daily["daily_count"] >= 3].groupby("USER_KEY").size().reset_index(name="day_count_over_3times")
    df = df.merge(tmp, on="USER_KEY", how="left")

    # ── 주차별 시청 (watch_rel_day 1-based: w1=1~7, w2=8~14, w3=15~21) ───────
    for w, (lo, hi) in enumerate([(1,7),(8,14),(15,21)], 1):
        wvh = vh[(vh["watch_rel_day"] >= lo) & (vh["watch_rel_day"] <= hi)]
        wt  = wvh.groupby("USER_KEY")[wc].sum().reset_index(name=f"watch_time(min)_w{w}")
        ws  = wvh.groupby("USER_KEY").size().reset_index(name=f"watch_session_w{w}")
        df  = df.merge(wt, on="USER_KEY", how="left").merge(ws, on="USER_KEY", how="left")

    for c in [f"watch_time(min)_w{i}" for i in range(1,4)] + [f"watch_session_w{i}" for i in range(1,4)]:
        df[c] = df[c].fillna(0)

    # ── 리텐션 비율 (CSV 공식: (w2+1)/(w1+1), (w3+1)/(w2+1)) ─────────────────
    df["retention_w2_ratio"] = (df["watch_time(min)_w2"] + 1) / (df["watch_time(min)_w1"] + 1)
    df["retention_w3_ratio"] = (df["watch_time(min)_w3"] + 1) / (df["watch_time(min)_w2"] + 1)

    # ── diff ──────────────────────────────────────────────────────────────────
    df["diff_between_w2_w1"] = df["watch_time(min)_w2"] - df["watch_time(min)_w1"]
    df["diff_between_w3_w2"] = df["watch_time(min)_w3"] - df["watch_time(min)_w2"]
    df["diff_between_w3_w1"] = df["watch_time(min)_w3"] - df["watch_time(min)_w1"]

    # ── is_w*_over_50pct (분모: w1+w2+w3 합) ─────────────────────────────────
    total_3w = df["watch_time(min)_w1"] + df["watch_time(min)_w2"] + df["watch_time(min)_w3"]
    for w in range(1, 4):
        df[f"is_w{w}_over_50pct"] = np.where(
            total_3w > 0, (df[f"watch_time(min)_w{w}"] / total_3w >= 0.5).astype(int), 0
        )

    df["is_only_w1"] = ((df["watch_time(min)_w1"]>0)&(df["watch_time(min)_w2"]==0)&(df["watch_time(min)_w3"]==0)).astype(int)
    df["is_only_w2"] = ((df["watch_time(min)_w1"]==0)&(df["watch_time(min)_w2"]>0)&(df["watch_time(min)_w3"]==0)).astype(int)
    df["is_only_w3"] = ((df["watch_time(min)_w1"]==0)&(df["watch_time(min)_w2"]==0)&(df["watch_time(min)_w3"]>0)).astype(int)

    # ── 신규/구작 영화 비율 ────────────────────────────────────────────────────
    if "ott_release_month" in vh.columns:
        vh["rel_month"] = pd.to_numeric(vh["ott_release_month"], errors="coerce").fillna(0).astype(int)
        tc2 = grp.size().reset_index(name="tc2")

        for cutym, col in [
            (202101, "new_movie_in_90d_ratio"),
            (202009, "new_movie_in_180d_ratio"),
            (202003, "new_movie_in_365d_ratio"),
        ]:
            sub = vh[vh["rel_month"] >= cutym].groupby("USER_KEY").size().reset_index(name="nc")
            tmp = tc2.merge(sub, on="USER_KEY", how="left").fillna(0)
            tmp[col] = tmp["nc"] / tmp["tc2"].clip(lower=1)
            df = df.merge(tmp[["USER_KEY", col]], on="USER_KEY", how="left")

        # old_movie_ratio(5y): (watch_date - release_date).days >= 1825
        vh_old = vh[vh["rel_month"] > 0].copy()
        vh_old["release_date"] = pd.to_datetime(
            vh_old["rel_month"].astype(str).str.zfill(6) + "01", format="%Y%m%d", errors="coerce"
        )
        vh_old["is_old_5y"] = ((vh_old["watch_date"] - vh_old["release_date"]).dt.days >= 1825).astype(int)
        tmp = vh_old.groupby("USER_KEY")["is_old_5y"].mean().reset_index(name="old_movie_ratio(5y)")
        df = df.merge(tmp, on="USER_KEY", how="left")

        # avg_ott_release_year: 시청시간 가중 평균
        vhr = vh[vh["rel_month"] > 0].copy()
        vhr["rel_year"] = vhr["rel_month"] // 100
        def _wavg_year(g):
            w = g[wc].sum()
            return (g["rel_year"] * g[wc]).sum() / w if w > 0 else g["rel_year"].mean()
        tmp = vhr.groupby("USER_KEY").apply(_wavg_year).reset_index(name="avg_ott_release_year")
        df = df.merge(tmp, on="USER_KEY", how="left")

    # ── 장르 비율 (시청시간 가중, CSV 기준) ──────────────────────────────────
    if "genre" in vh.columns:
        df = df.merge(grp["genre"].nunique().reset_index(name="genre_diversity_count"), on="USER_KEY", how="left")

        total_wt = grp[wc].sum().reset_index(name="total_wt")
        for col, genre_val in [
            ("action_adventure_ratio", "Action/Adventure"),
            ("family_animation_ratio", "Animation/Family"),
            ("drama_ratio",            "Drama"),
            ("thriller_crime_ratio",   "Thriller/Crime"),
            ("sf_fantasy_ratio",       "SF/Fantasy"),
            ("comedy_ratio",           "Comedy"),
            ("romance_ratio",          "Romance"),
            ("horror_ratio",           "Horror"),
            ("documentary_ratio",      "Documentary"),
            ("historical_war_ratio",   "Historical/War"),
        ]:
            sub = vh[vh["genre"] == genre_val].groupby("USER_KEY")[wc].sum().reset_index(name="gwt")
            tmp = total_wt.merge(sub, on="USER_KEY", how="left").fillna(0)
            tmp[col] = tmp["gwt"] / tmp["total_wt"].clip(lower=0.001)
            df = df.merge(tmp[["USER_KEY", col]], on="USER_KEY", how="left")

        known_genres = [
            "Action/Adventure", "Animation/Family", "Drama", "Thriller/Crime",
            "SF/Fantasy", "Comedy", "Romance", "Horror", "Documentary", "Historical/War",
        ]
        sub = vh[~vh["genre"].isin(known_genres)].groupby("USER_KEY")[wc].sum().reset_index(name="gwt")
        tmp = total_wt.merge(sub, on="USER_KEY", how="left").fillna(0)
        tmp["other_ratio"] = tmp["gwt"] / tmp["total_wt"].clip(lower=0.001)
        df = df.merge(tmp[["USER_KEY", "other_ratio"]], on="USER_KEY", how="left")

    return df


# ══════════════════════════════════════════════════════════════════════════════
# 3단계: config.py 컬럼명 정합성 맞추기
# ══════════════════════════════════════════════════════════════════════════════

def _align_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """
    변수만드는 방법.csv 기준으로 컬럼명을 직접 생성하므로
    추가 rename 불필요. 혹시 남아있는 구형 컬럼명만 정리.
    """
    rename = {
        "total_watch_time_min":     "total_watch_time(min)",
        "avg_watch_time_min":       "avg_watch_time(min)",
        "median_watch_time_min":    "median_watch_time(min)",
        "std_watch_time_min":       "std_watch_time(min)",
        "max_watch_time_min":       "max_watch_time(min)",
        "avg_daily_watch_time_min": "avg_daily_watch_time(min)",
        "max_daily_watch_time_min": "max_daily_watch_time(min)",
    }
    return df.rename(columns={k: v for k, v in rename.items() if k in df.columns})


# ══════════════════════════════════════════════════════════════════════════════
# 전체 실행
# ══════════════════════════════════════════════════════════════════════════════

def _process_files(mem_path, vh_path, movie_path, umap_path) -> tuple:
    """
    단일 데이터셋(train 또는 test) 처리.
    반환: (완성된 df, 통계 dict)
    """
    mem_raw = pd.read_csv(mem_path,   encoding="utf-8-sig")
    vh_raw  = pd.read_csv(vh_path,    encoding="utf-8-sig")
    movie   = pd.read_csv(movie_path, encoding="utf-8-sig")
    umap    = pd.read_csv(umap_path,  encoding="utf-8-sig")

    raw_rows  = len(mem_raw)
    mem_clean = _clean_membership(mem_raw)
    cleaned_rows = len(mem_clean)

    df = _engineer_features(mem_clean, vh_raw, movie, umap)
    df = _align_column_names(df)

    num_cols = df.select_dtypes(include="number").columns
    df[num_cols] = df[num_cols].fillna(0)
    df = df.drop(columns=["max_screen"], errors="ignore")

    before_dur = len(df)
    df["_dur"] = (
        pd.to_datetime(df["end_date"], errors="coerce") -
        pd.to_datetime(df["reg_date"], errors="coerce")
    ).dt.days
    df = df[df["_dur"] >= 21].drop(columns=["_dur"]).copy()
    dur_removed = before_dur - len(df)

    before_dup = len(df)
    df = df.drop_duplicates().reset_index(drop=True)
    dup_removed = before_dup - len(df)

    stats = {
        "raw_rows":      raw_rows,
        "cleaned_rows":  cleaned_rows,
        "dur_removed":   dur_removed,
        "dup_removed":   dup_removed,
        "final_rows":    len(df),
        "final_cols":    len(df.columns),
    }
    return df, stats


def _to_exp_df(df: pd.DataFrame) -> pd.DataFrame:
    """완성된 df → 모델 입력용 컬럼만 선택."""
    exp_features = [f for f in EXPANDED_FEATURES if f in df.columns]
    cols = (
        ["USER_KEY", "is_repurchase"]
        + (["is_promotion"] if "is_promotion" in df.columns else [])
        + [f for f in exp_features if f not in {"USER_KEY", "is_repurchase", "is_promotion"}]
    )
    return df[cols].copy().reset_index(drop=True)


def run_feature_engineering(
    mem_file: str = None,
    vh_file: str = None,
    movie_file: str = None,
    mapping_file: str = None,
    test_mem_file: str = None,
    test_vh_file: str = None,
) -> dict:
    mem_path      = RAW_DIR / mem_file      if mem_file      else MEM_RAW
    vh_path       = RAW_DIR / vh_file       if vh_file       else VH_RAW
    movie_path    = RAW_DIR / movie_file    if movie_file    else MOVIE_RAW
    umap_path     = RAW_DIR / mapping_file  if mapping_file  else UMAP_RAW
    test_mem_path = RAW_DIR / test_mem_file if test_mem_file else TEST_MEM_RAW
    test_vh_path  = RAW_DIR / test_vh_file  if test_vh_file  else TEST_VH_RAW

    # ── 파일 존재 확인 ─────────────────────────────────────────────────────────
    missing = [str(p) for p in [mem_path, vh_path, movie_path, umap_path] if not p.exists()]
    if missing:
        return {
            "status": "FAIL",
            "reason": f"입력 파일 없음: {missing}",
            "expected_paths": {
                "membership":   str(mem_path),
                "view_history": str(vh_path),
                "movie_master": str(movie_path),
                "user_mapping": str(umap_path),
            },
        }

    # ── TRAIN 처리 ────────────────────────────────────────────────────────────
    train_df, train_stats = _process_files(mem_path, vh_path, movie_path, umap_path)
    train_df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

    exp_df = _to_exp_df(train_df)
    save_df("expanded_dataset", exp_df)   # 전체 23,081행 — split 없음

    # ── TEST 처리 ─────────────────────────────────────────────────────────────
    test_expanded_rows = None
    if test_mem_path.exists() and test_vh_path.exists():
        test_df, test_stats = _process_files(test_mem_path, test_vh_path, movie_path, umap_path)
        test_df.to_csv(TEST_OUTPUT_PATH, index=False, encoding="utf-8-sig")
        test_exp_df = _to_exp_df(test_df)
        save_df("test_expanded", test_exp_df)
        test_expanded_rows = test_stats["final_rows"]

    return {
        "status":              "PASS",
        **train_stats,
        "expanded_rows":       len(exp_df),
        "test_expanded_rows":  test_expanded_rows,
        "output_path":         str(OUTPUT_PATH),
        "summary": (
            f"[TRAIN] 원본 {train_stats['raw_rows']:,}행 → 정제 {train_stats['cleaned_rows']:,}행 → "
            f"duration<21 {train_stats['dur_removed']}행 제거 → 중복 {train_stats['dup_removed']}행 제거 → "
            f"최종 {train_stats['final_rows']:,}행 × {train_stats['final_cols']}컬럼. "
            f"expanded_dataset {len(exp_df):,}행 저장. "
            + (f"[TEST] Membership_final_2.csv + test_expanded {test_expanded_rows:,}행 저장." if test_expanded_rows else "[TEST] 파일 없음 — 건너뜀.")
        ),
    }


# ── 엔드포인트 ─────────────────────────────────────────────────────────────────

@router.post("/feature-engineering")
def feature_engineering(
    mem_file: str = Query(default="Membership_train.csv", description="멤버십 파일명 (_data/01_raw/ 기준)"),
    vh_file: str = Query(default="Views_train.csv", description="시청이력 파일명"),
    movie_file: str = Query(default="Movies.csv", description="영화 마스터 파일명"),
    mapping_file: str = Query(default="mapping.csv", description="유저 매핑 파일명"),
    test_mem_file: str = Query(default="Membership_test.csv", description="테스트 멤버십 파일명"),
    test_vh_file: str = Query(default="Views_test.csv", description="테스트 시청이력 파일명"),
):
    """
    Step 00: 피처 엔지니어링. 항상 재실행.

    - Train: Membership_train.csv + Views_train.csv → expanded_dataset.csv (전체, split 없음)
    - Test:  Membership_test.csv  + Views_test.csv  → test_expanded.csv

    파일명을 지정하지 않으면 기본값 사용. 경로는 _data/01_raw/ 고정.
    """
    result = run_feature_engineering(mem_file, vh_file, movie_file, mapping_file, test_mem_file, test_vh_file)

    if result["status"] == "PASS":
        save_json("step00_result", result)
        mark_done("step00", {
            "final_rows": result["final_rows"],
            "final_cols": result["final_cols"],
        })

    result["from_cache"] = False
    return result
