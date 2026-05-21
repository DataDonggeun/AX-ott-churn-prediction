"""
KOBIS 영화 크롤링 스크립트
- 중단해도 kobis_progress.json에 저장되어 이어서 실행 가능
- 620개 미매칭 영화 재시도
"""
import json, time, re, requests, pandas as pd
from pathlib import Path
from difflib import SequenceMatcher

# ── API 설정 ──────────────────────────────────────────────────────
API_KEYS = [
    "7eccea85dd0b53c5a9646f1e012297c6",
    "6c473256f22b9b3d9e50983e6d322725",
    "470e9ac05da21ed137381f0b878e4ea7",
    "d584d161685528e42a5d34cc6eb82c47",
    "da7a44d27226f75c18e8588170e7be10",
    "ced897d260349ad1fd4bfdfac8c644bf",
    "524283f348b55f75461e7b726425187b",
    "f3761b1a552eba9ab32b62dfb2fadfd4",
    "880da37637c3f986d6eb4e3243aa658b",
    "bacdd7462fa288520c44b7668d6335be",
    "7921cebeda88d15034069a7bf396cb96",
    "41cfdaf9f543e7d5625fa56b2cdc064c",
]
DAILY_LIMIT    = 3500          # 키당 일일 한도
REQUEST_DELAY  = 0.25          # 요청 간 딜레이(초)
SIMILARITY_THR = 0.6           # 제목 유사도 기준

SEARCH_URL  = "http://www.kobis.or.kr/kobisopenapi/webservice/rest/movie/searchMovieList.json"
DETAIL_URL  = "http://www.kobis.or.kr/kobisopenapi/webservice/rest/movie/searchMovieInfo.json"

DATA_DIR      = Path("../data")
MOVIE_MASTER  = DATA_DIR / "Movie_Master.csv"
PROGRESS_FILE = DATA_DIR / "kobis_progress.json"
OUTPUT_FILE   = DATA_DIR / "Movie_Master_kobis.csv"


# ── KeyManager ────────────────────────────────────────────────────
class KeyManager:
    def __init__(self, keys, daily_limit):
        self.keys  = keys
        self.limit = daily_limit
        self.usage = {k: 0 for k in keys}

    def get(self):
        for k in self.keys:
            if self.usage[k] < self.limit:
                return k
        return None

    def use(self, key):
        self.usage[key] += 1

    def remaining(self):
        return sum(self.limit - v for v in self.usage.values())


# ── 제목 전처리 ───────────────────────────────────────────────────
def make_queries(title):
    queries, raw = [], title.strip()
    queries.append(raw)
    no_bracket = re.sub(r'\[.*?\]', '', raw).strip()
    if no_bracket and no_bracket != raw:
        queries.append(no_bracket)
    no_year = re.sub(r'\(\d{4}\)', '', no_bracket or raw).strip()
    if no_year and no_year not in queries:
        queries.append(no_year)
    no_paren = re.sub(r'[\(\[（【][^)\]）】]*[\)\]）】]', '', raw).strip()
    if no_paren and no_paren not in queries:
        queries.append(no_paren)
    base = no_paren or no_year or raw
    if ':' in base:
        queries.append(base.split(':')[0].strip())
    if len(base) > 6:
        queries.append(base[:6])
    if len(base) > 4:
        queries.append(base[:4])
    seen = []
    for q in queries:
        if q and q not in seen:
            seen.append(q)
    return seen


# ── API 호출 ──────────────────────────────────────────────────────
def search_api(query, km):
    key = km.get()
    if not key:
        raise RuntimeError("모든 API 키 한도 초과")
    km.use(key)
    try:
        resp = requests.get(SEARCH_URL,
                            params={"key": key, "movieNm": query, "itemPerPage": 10},
                            timeout=10)
        resp.raise_for_status()
        res = resp.json().get("movieListResult", {})
        return res.get("movieList", []), int(res.get("totCnt", 0))
    except Exception as e:
        print(f"  [검색 오류] {query}: {e}")
        return [], 0


def fetch_detail(movie_cd, km):
    key = km.get()
    if not key:
        raise RuntimeError("모든 API 키 한도 초과")
    km.use(key)
    try:
        resp = requests.get(DETAIL_URL,
                            params={"key": key, "movieCd": movie_cd},
                            timeout=10)
        resp.raise_for_status()
        return resp.json().get("movieInfoResult", {}).get("movieInfo", {})
    except Exception as e:
        print(f"  [상세 오류] {movie_cd}: {e}")
        return {}


# ── 매칭 로직 ─────────────────────────────────────────────────────
def title_sim(a, b):
    a2 = re.sub(r'\s', '', a)
    b2 = re.sub(r'\s', '', b)
    return SequenceMatcher(None, a2, b2).ratio()


def is_good_match(orig, result_title, threshold=SIMILARITY_THR):
    clean = re.sub(r'[\(\[（【][^)\]）】]*[\)\]）】]', '', orig).strip()
    if ':' in clean:
        clean = clean.split(':')[0].strip()
    if len(re.sub(r'\s', '', clean)) <= 3:
        return re.sub(r'\s', '', clean) == re.sub(r'\s', '', result_title)
    return title_sim(clean, result_title) >= threshold


def pick_best(candidates, title, release_month):
    valid = [c for c in candidates if is_good_match(title, c.get("movieNm", ""))]
    if not valid:
        return None
    clean = re.sub(r'[\(\[（【][^)\]）】]*[\)\]）】]', '', title).strip()
    exact = [c for c in valid if c.get("movieNm", "") == clean]
    pool  = exact if exact else valid
    if release_month and str(release_month).isdigit():
        yr = int(str(release_month)[:4])
        def dist(c):
            od = c.get("openDt", "") or ""
            return abs(int(od[:4]) - yr) if len(od) >= 4 and od[:4].isdigit() else 9999
        pool.sort(key=dist)
    return pool[0]


def parse_detail(info):
    if not info:
        return {}
    def join(lst, key):
        return "|".join(x.get(key, "") for x in lst if x.get(key))
    return {
        "MovieCd"      : info.get("movieCd", ""),
        "movieNm(api)" : info.get("movieNm", ""),
        "movieNmEn"    : info.get("movieNmEn", ""),
        "showTm"       : info.get("showTm", ""),
        "prdtYear"     : info.get("prdtYear", ""),
        "openDt"       : info.get("openDt", ""),
        "typeNm"       : info.get("typeNm", ""),
        "nationNm"     : join(info.get("nations",   []), "nationNm"),
        "genreNm"      : join(info.get("genres",    []), "genreNm"),
        "directors"    : join(info.get("directors", []), "peopleNm"),
        "actors"       : join(info.get("actors",    [])[:5], "peopleNm"),
        "watchGrade"   : info.get("audits", [{}])[0].get("watchGradeNm", "")
                         if info.get("audits") else "",
    }


# ── 저장 / 출력 빌드 ──────────────────────────────────────────────
def save_progress(progress):
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def build_output(mv, progress):
    rows = []
    for _, row in mv.iterrows():
        mid  = str(row["MOVIE_ID"])
        info = progress["results"].get(mid, {})
        merged = row.to_dict()
        merged.update(info)
        rows.append(merged)
    pd.DataFrame(rows).to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")
    print(f"CSV 저장: {OUTPUT_FILE}")


# ── 키 유효성 확인 ────────────────────────────────────────────────
def check_keys():
    print("=== API 키 확인 ===")
    ok = 0
    for i, key in enumerate(API_KEYS):
        try:
            resp = requests.get(SEARCH_URL,
                                params={"key": key, "movieNm": "기생충", "itemPerPage": 1},
                                timeout=10)
            res = resp.json().get("movieListResult", {})
            if "totCnt" in res:
                print(f"  키{i+1:2d}: ✓ 정상")
                ok += 1
            else:
                print(f"  키{i+1:2d}: ✗ 한도 초과")
        except Exception as e:
            print(f"  키{i+1:2d}: ✗ 오류 - {e}")
    print(f"\n사용 가능: {ok}/{len(API_KEYS)}개  추정 가용 요청: {ok * DAILY_LIMIT:,}건\n")
    return ok


# ── 메인 실행 ─────────────────────────────────────────────────────
if __name__ == "__main__":
    check_keys()

    mv = pd.read_csv(MOVIE_MASTER)
    print(f"Movie_Master 로드: {len(mv)}개 영화")

    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, encoding="utf-8") as f:
            progress = json.load(f)
        print(f"이전 진행 상황 로드: {len(progress['results'])}개 완료")
    else:
        progress = {"results": {}, "not_found": []}

    done_ids = set(progress["results"].keys())
    km       = KeyManager(API_KEYS, DAILY_LIMIT)
    todo     = mv[~mv["MOVIE_ID"].astype(str).isin(done_ids)]
    total    = len(mv)

    print(f"남은 작업: {len(todo)}개 / 전체 {total}개")
    print(f"가용 API 요청 수: {km.remaining():,}건\n")

    for idx, row in todo.iterrows():
        movie_id      = str(row["MOVIE_ID"])
        title         = str(row["TITLE"])
        release_month = row.get("RELEASE_MONTH", None)

        m = re.search(r'\((\d{4})\)', title)
        year_for_search = int(m.group(1)) if m else release_month

        done_cnt = len(progress["results"])
        if done_cnt % 100 == 0:
            print(f"[{done_cnt}/{total}] 남은 요청: {km.remaining():,}건")

        if km.remaining() <= 0:
            print("모든 키 한도 소진. 내일 재실행하세요.")
            break

        queries = make_queries(title)
        found, matched_query, tot_cnt = None, None, 0

        for q in queries:
            time.sleep(REQUEST_DELAY)
            candidates, tot = search_api(q, km)
            if tot > 0:
                tot_cnt = tot
            best = pick_best(candidates, title, year_for_search)
            if best:
                found, matched_query = best, q
                break

        if not found:
            print(f"  [미발견] {title}")
            progress["results"][movie_id] = {"totCnt": tot_cnt}
        else:
            time.sleep(REQUEST_DELAY)
            detail = fetch_detail(found["movieCd"], km)
            parsed = parse_detail(detail)
            parsed["totCnt"] = tot_cnt
            if matched_query != title:
                print(f"  [fallback] {title} → {matched_query} → {found.get('movieNm', '')}")
            progress["results"][movie_id] = parsed

        if done_cnt % 100 == 0:
            save_progress(progress)

    save_progress(progress)
    build_output(mv, progress)

    found_cnt = sum(1 for v in progress["results"].values() if v.get("MovieCd"))
    print(f"\n완료! 발견: {found_cnt}개 / 미발견: {total - found_cnt}개")