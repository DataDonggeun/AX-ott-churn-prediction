"""TMDB 영화 추천 모듈 — 고객 장르 유사도 기반, 성인 제외, 유명작 위주"""
import hashlib
import os

import requests
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TMDB_TOKEN", "")

BASE_URL = "https://api.themoviedb.org/3"
HEADERS  = {"Authorization": f"Bearer {TOKEN}", "accept": "application/json"}

GENRE_MAP = {
    "drama":    18,
    "action":   28,
    "romance":  10749,
    "thriller": 53,
    "horror":   27,
    "family":   10751,
    "sf":       878,
    "comedy":   35,
}

# 고객별 정렬 방법 변형 (같은 장르라도 다른 결과)
SORT_METHODS = ["popularity.desc", "vote_average.desc", "revenue.desc"]

# 성인 콘텐츠 의심 키워드 (제목에 포함 시 제거)
ADULT_KEYWORDS = ["에로", "성인", "야동", "19금", "xxx", "adult", "erotic", "porn"]


def _is_adult(movie: dict) -> bool:
    """성인 콘텐츠 여부 확인"""
    if movie.get("adult", False):
        return True
    title = (movie.get("title", "") + movie.get("original_title", "")).lower()
    if any(kw in title for kw in ADULT_KEYWORDS):
        return True
    # 투표 수가 너무 적은 영화 제거 (성인/마이너 콘텐츠 경향)
    if movie.get("vote_count", 0) < 200:
        return True
    return False


def get_movies_by_genres(genre_ratios: dict, customer_key: str = "",
                          year_gte: int = 2018, n: int = 5) -> list:
    """
    고객 장르 시청 비율 기반 맞춤 추천
    - 상위 2개 장르 조합
    - 고객 KEY 해시로 정렬/페이지 변형 → 고객마다 다른 결과
    - 한국어 한정 제거 → 귀멸의 칼날, 어벤져스 등 유명작 포함
    - 성인 콘텐츠 다중 필터링
    """
    # 장르 비율 상위 2개
    sorted_genres = sorted(genre_ratios.items(), key=lambda x: x[1], reverse=True)
    top_genres = [g for g, r in sorted_genres if r > 0.05][:2]

    if not top_genres:
        # 시청 이력 없으면 해시로 장르 다양화
        genre_list = list(GENRE_MAP.keys())
        h = int(hashlib.md5(customer_key.encode()).hexdigest(), 16)
        top_genres = [genre_list[h % len(genre_list)]]

    genre_ids = ",".join(str(GENRE_MAP[g]) for g in top_genres if g in GENRE_MAP)

    # 고객별 정렬 + 페이지 변형
    h_val    = int(hashlib.md5(customer_key.encode()).hexdigest(), 16)
    sort_by  = SORT_METHODS[h_val % len(SORT_METHODS)]
    page_num = (h_val % 3) + 1

    params = {
        "with_genres":              genre_ids,
        "sort_by":                  sort_by,
        "vote_count.gte":           500,       # 유명한 영화만
        "vote_average.gte":         6.5,       # 최소 평점
        "primary_release_date.gte": f"{year_gte}-01-01",
        "page":                     page_num,
        "include_adult":            False,
        "language":                 "ko-KR",   # 한국어 제목·줄거리
        # 원본 언어 제한 없음 → 한국/일본/미국 등 모든 유명작
    }

    try:
        r = requests.get(f"{BASE_URL}/discover/movie",
                         headers=HEADERS, params=params, timeout=6)
        results = r.json().get("results", [])
        # 성인 콘텐츠 추가 필터링
        results = [m for m in results if not _is_adult(m)]
        return results[:n]
    except Exception:
        return []


def get_movies(genre: str = "drama", page: int = 1, year_gte: int = 2018) -> list:
    """단일 장르 기반 추천 (챗봇용)"""
    genre_id = GENRE_MAP.get(genre.lower(), 18)
    params = {
        "with_genres":              genre_id,
        "sort_by":                  "popularity.desc",
        "vote_count.gte":           500,
        "vote_average.gte":         6.5,
        "primary_release_date.gte": f"{year_gte}-01-01",
        "page":                     page,
        "include_adult":            False,
        "language":                 "ko-KR",
    }
    try:
        r = requests.get(f"{BASE_URL}/discover/movie",
                         headers=HEADERS, params=params, timeout=6)
        results = r.json().get("results", [])
        results = [m for m in results if not _is_adult(m)]
        return results[:10]
    except Exception:
        return []


def add_reasons(movies: list, genre: str, customer_age: int,
                customer_gender: str) -> list:
    """영화별 추천 이유 추가"""
    age_desc    = "젊은" if customer_age < 35 else ("중장년" if customer_age < 55 else "시니어")
    gender_desc = "여성" if str(customer_gender).upper() == "F" else "남성"

    reasons = {
        "drama":    f"{age_desc} {gender_desc} 시청자에게 인기 있는 감동 드라마예요.",
        "action":   f"스릴 넘치는 액션으로 {age_desc} {gender_desc} 시청자 사이 화제작이에요.",
        "romance":  f"달콤한 로맨스로 {gender_desc} 시청자들이 특히 좋아해요.",
        "thriller": f"긴장감 있는 스릴러로 몰입도가 높은 작품이에요.",
        "horror":   f"공포 장르 마니아라면 놓치지 말아야 할 작품이에요.",
        "family":   f"온 가족이 함께 볼 수 있는 따뜻한 영화예요.",
        "sf":       f"SF 팬이라면 반드시 봐야 할 화제작이에요.",
        "comedy":   f"유쾌한 코미디로 스트레스 해소에 딱이에요.",
    }
    reason = reasons.get(genre.lower(), "취향에 맞는 인기작이에요.")

    for m in movies:
        m["reason"] = reason
        m["poster"] = (f"https://image.tmdb.org/t/p/w300{m['poster_path']}"
                       if m.get("poster_path") else "")
    return movies
