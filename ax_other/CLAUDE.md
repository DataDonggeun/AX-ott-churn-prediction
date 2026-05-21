# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

OTT(Over-The-Top) 서비스의 **고객 이탈(Churn) 예측** 기업연계 프로젝트.
멤버십 데이터를 기반으로 EDA → 피처 엔지니어링 → 머신러닝 모델 개발 순으로 진행.

**현재 단계**: EDA 완료 → 전처리 완료 → 모델링 단계

---

## 현재 파일 구조

```
새 폴더/
├── CLAUDE.md
├── kobis_search.py                 # KOBIS API 검색 스크립트 (wavve_notfound.txt → 유사도 0.8)
├── model_churn.ipynb               # 이탈 예측 모델링 노트북 (LR/RF/GB/LGB/XGB)
├── view_history_repurchase.ipynb   # View_History × 재결제율 분석
├── 영화 크로링.ipynb                 # KOBIS 전체 영화 크롤링 (완료, Anaconda 커널 오류 있음)
├── data/
│   ├── Membership.csv              # 원본 (18,183행)
│   ├── Membership_processing.csv   # 전처리 완료본 (17,810행, 29컬럼) ← 모델링에 사용
│   ├── User_Mapping.csv
│   ├── View_History.csv
│   ├── Movie_Master.csv
│   ├── Movie_Master_kobis.csv      # KOBIS 크롤링 결과 (14,018행)
│   ├── movie_repurchase_stats.csv  # 영화별 재결제 통계
│   ├── wavve_notfound_kobis.csv    # wavve 미발견 → KOBIS 매칭 결과
│   └── wavve_notfound_still.txt    # KOBIS에서도 못 찾은 제목 목록
└── EDA/
    ├── eda_membership.ipynb
    ├── preprocessing_membership.ipynb
    ├── eda_report.html             # 직접 수정됨 → gen_eda_html.py 실행 금지
    ├── preprocessing_report.html
    ├── 파이썬 파일/
    │   ├── gen_charts.py
    │   ├── gen_eda_html.py         # out of sync, 실행 금지
    │   └── gen_preprocessing_html.py
    └── charts_b64.json
```

> **주의**: `gen_eda_html.py`는 현재 `eda_report.html`과 out of sync 상태.
> 실행하면 직접 수정한 내용(섹션 12·13, 결측치 테이블 등)이 덮어씌워짐.
> → 차트 업데이트는 charts_b64.json에서 base64만 교체하는 방식 사용.

> **차트 재생성만 할 경우**: `EDA/파이썬 파일/` 폴더에서
> `python gen_charts.py` → charts_b64.json 생성 후 HTML에 base64 교체

---

## 데이터 파일 현황

| 파일 | 행수 | 설명 |
|---|---|---|
| Membership.csv | 18,183 | 원본 멤버십 데이터 |
| **Membership_processing.csv** | **17,810** | **전처리 완료본 — 모델링에 사용** |
| User_Mapping.csv | 19,877 | user_no(해시) ↔ USER_ID(숫자) 매핑. 컬럼명: `uid`, `USER_ID` |
| View_History.csv | 106,205 | 시청 이력 (USER_ID, MOVIE_ID, DURATION, WATCH_DAY, WATCH_SEQ) |
| Movie_Master.csv | 14,018 | 영화 목록 (TITLE, RELEASE_MONTH) |
| Movie_Master_kobis.csv | 14,018 | KOBIS 크롤링 결과 (genreNm, directors, actors 등 포함) |

> View_History → Membership 조인 경로: `USER_ID` → `uid`(User_Mapping) → `user_no`(Membership)

### Membership_processing.csv 컬럼 (29개)

| 컬럼 | 타입 | 설명 |
|---|---|---|
| user_no | str | 유저 해시 ID (모델링 시 제거) |
| product_cd | str | 상품 코드 (모델링 시 제거, plan_tier/currency_type으로 대체) |
| amount | float | 결제금액 — 100(프로모션) / 7900 / 10900 / 13900 원화 통일 완료 |
| billing_method | int | 결제수단 코드 (13x=카드, 151=간편결제, 140=iOS, 18x=모바일) |
| concurrent_streams | int | 동시시청수 (1/2/4) |
| promotion_yn | int | 프로모션 참여 (0/1) |
| is_churn_prevented | int | 해지방어 (0/1) |
| repurchase | int | **타겟** — 재결제(1) / 이탈(0) |
| payment_device | str | 결제 디바이스 (android/pc/ios/mobile/lgtv 등) |
| is_user_verified | int | 본인인증 여부 Y→1 / N→0 |
| gender | int | 성별 F→0 / M→1 (N은 비율 대체 완료) |
| age | int | 나이 (age=40 미인증 기본값 → 인증유저 비율로 재배분 완료) |
| reg_date | str | 가입일 (모델링 시 제거) |
| reg_hour | int | 가입 시간 (0~23) |
| end_date | str | 종료일 (모델링 시 제거) |
| duration_days | int | 멤버십 유지일수 |
| plan_tier | str | 플랜 (basic/standard/premium/기타) |
| currency_type | str | 통화 (KRW/USD) |
| is_promotional_price | int | amount==100 여부 (0/1) |
| is_night_signup | int | 야간 가입 — 22~05시 → 1 |
| reg_weekday | int | 가입 요일 (월=0, 일=6) |
| is_same_day_cancel | int | 당일 해지 duration_days==0 (0/1) |
| age_group | int | 연령대 10단위 (10/20/30/40/50/60/70/80/90) |
| total_watch_count | float | 시청 횟수 합계 |
| total_watch_duration | float | 총 시청 시간(분) |
| unique_movies | float | 시청 고유 영화 수 |
| avg_duration | float | 평균 시청 시간(분), 소수점 2자리 |
| watch_days_count | float | 시청 일수 |
| has_watch_history | int | 시청 이력 유무 (0/1) |

---

## 타겟 변수

- **`repurchase`**: O = 재결제(1), NaN = 이탈(0)
- 재결제 11,931건 (65.6%) / 이탈 6,252건 (34.4%)
- `promotion_yn`, `is_churn_prevented` 도 동일하게 O=해당, NaN=미해당 구조

### is_churn_prevented (해지방어) 경우의 수

| 해지 시도 | 해지방어 | repurchase | 설명 |
|---|---|---|---|
| O | O | O | 해지 시도 → 인센티브 수락 → 재결제 |
| O | O | NaN | 해지방어 성공했으나 다음 달 재결제 안 함 (드물지만 존재) |
| X | NaN | O | 그냥 정상 재결제 |
| X | NaN | NaN | 해지 시도 없이 자동 만료 이탈 (iOS 등 자동결제 미갱신 포함) |

---

## product_cd 코드 체계

**플랜(동시 시청 수) × 결제 수단** 조합.

| 플랜 | 동시 시청 | 정가(원화) | 원화 구(13x) | 원화 신(151) | 달러 iOS(140) |
|---|---|---|---|---|---|
| 베이직 | 1 | 7,900원 | pk_1487 | pk_2025 | pk_1508 · $9.99 |
| 스탠다드 | 2 | 10,900원 | pk_1488 | pk_2026 | pk_1506 · $13.49 |
| 프리미엄 | 4 | 13,900원 | pk_1489 | pk_2027 | pk_1507 · $16.49 |

- 위 9개 코드가 전체 53개 중 96% 차지
- 중간 금액(3,950 / 5,450 / 6,950원) = 월 중간 가입 일할 계산 (정상값)
- **amount=100이면 무조건 promotion_yn=O** (1:1 대응 확인)
- billing_method: 13x=국내카드, 151=간편결제, 140=iOS앱스토어, 18x=모바일결제
- **duration_days max=32**: 해외(iOS) 결제 시 국가별 월 길이(28~31일) 및 시차 차이로 청구 주기가 하루 길어지는 경우 발생

---

## EDA에서 발견된 주요 이슈

### 결측치 및 처리 방향
| 컬럼 | 결측률 | 처리 방향 |
|---|---|---|
| is_churn_prevented | 82.1% | NaN → 0 (미해당), O → 1 |
| promotion_yn | 49.4% | NaN → 0 (미참여), O → 1 |
| repurchase | 34.4% | NaN → 0 (이탈), O → 1 **(타겟)** |
| is_user_verified | 3.3% | 결측 → N으로 대체, Y→1 / N→0 인코딩 |
| gender | 0.9% | 결측 → 기존 F/M/N 비율(52.6%/31.6%/15.8%)대로 랜덤 대체 |
| age | 0.9% | 결측 → 기존 연령대 비율대로 랜덤 대체 (age>100 이상값 제거 후 비율 계산) |
| concurrent_streams | 0.4% | 결측 행 제거 |

### 이상값 & 오류
- `amount`: 원화(₩) + 달러($) 혼재 — 달러 케이스 약 3,062건(16.8%). product_cd로 식별 가능
- `age`: max=950 (미인증 입력 오류). 100세 초과는 이상값 처리. **age=40에 5,100건+ spike → 40대 미인증 기본값으로 추정**
- `concurrent_streams=3`: 7건만 존재 — 상품 tier가 1/2/4만 있으므로 입력 오류 → 제거
- `user_no` 중복: 338건 (동일인 다중 가입) → duration_days 최대값 행 유지
- `duration_days=0`: 399건 (당일 해지)
- `reg_hour=0`: 1,500건으로 최다 spike — 실제 자정 vs 기본값 불명확
- `gender=N`: 미확인 성별 (중립 아님), 미인증 고객의 67.3%

### View_History
- 시청 기간: 2021-03-01 ~ 2021-04-05 (약 5주, 짧은 기간 주의)
- DURATION max=200분 (캡핑값, 644건)
- WATCH_SEQ = 동일 영화 분할 시청 구분 → 합산 처리
- View_History에만 있고 Membership에 없는 유저 → 전처리 시 제거 대상

---

## 전처리 완료 사항 (Membership_processing.csv 기준)

- user_no 중복 제거, concurrent_streams=3 제거, age==0 제거 (5행)
- repurchase / promotion_yn / is_churn_prevented: O→1, NaN→0
- is_user_verified: Y→1, N→0
- gender: F→0, M→1 (N은 F/M 비율 기반 랜덤 대체 완료)
- age=40 미인증 기본값 3,590건 → 인증유저 나이 분포로 재배분
- age_group: (age // 10) * 10 으로 재계산
- amount: concurrent_streams 기준 원화 통일 (100 제외) — 100/7900/10900/13900 4가지만 존재
- is_night_signup: reg_hour ∈ {22,23,0,1,2,3,4,5} → 1
- is_verified / billing_group 컬럼 제거 (중복/불필요)
- View_History 집계 피처 포함 (total_watch_count 등 6개)

---

## eda_report.html 섹션 구성 (현재)

| 섹션 | 내용 | 차트 |
|---|---|---|
| 1 | 결측치 현황 | 결측치 히트맵 |
| 2 | 타겟 분포 (repurchase) | 파이차트 |
| 3 | 결제 금액 (amount) | 히스토그램 |
| 4 | 연령 분포 (age) | 히스토그램 (5세 단위 bin) |
| 5 | concurrent_streams / reg_hour | 바차트 |
| 6 | 가입 지속일 (duration_days) | 히스토그램 (단일 패널) |
| 7 | 범주형 변수 | 바차트 |
| 8 | 시계열 (가입일·시간) | 라인+바 |
| 9 | product_cd × repurchase | 누적 바차트 |
| 10 | 세그먼트: 인증 여부 | 비교 히스토그램 (5세 bin) |
| 11 | 세그먼트: 재결제 여부 | 비교 히스토그램 (5세 bin) |
| 12 | 시간대·요일 히트맵 | 히트맵 |
| 13 | 성별·연령 히트맵 | 히트맵 |
| 14 | View_History EDA | 4패널 (분포·추세·유저수·WATCH_SEQ) |
| 14-1 | View_History 세그먼트: 인증 여부 | 비교 히스토그램 |
| 14-2 | View_History 세그먼트: 재결제 여부 | 비교 히스토그램 |
| 15 | 전처리 필요 사항 요약 | (차트 없음) |

> **gen_eda_html.py 실행 금지**: eda_report.html을 직접 수정했으므로 실행 시 섹션 12·14·15 등 덮어씌워짐

---

## gen_charts.py 주요 기술 메모

- **Age bin**: `np.arange(10, 106, 5) - 0.5` → 5세 간격 [10,15), [15,20), ...[100,105)
- **Integer bin**: `np.arange(0, int(p99) + 2) - 0.5` → 정수값 하나씩 bin
- **세그먼트 차트**: 비수치형(gender 등)은 mean line 스킵
  ```python
  if pd.api.types.is_numeric_dtype(data):
      ax.axvline(data.mean(), ...)
  ```
- **View_History 조인**: `user_stats.merge(um[['USER_ID','uid']], on='USER_ID').merge(mem, left_on='uid', right_on='user_no')`
- **차트 키 목록** (charts_b64.json): missing, target, amount, age, streams_hour, duration, categorical, timeseries, prod_repurchase, seg_verified, seg_repurchase, hour_weekday_heatmap, gender_age_heatmap, view_history, vh_seg_verified, vh_seg_repurchase (+ 5개 추가 키)

---

## 데이터 (Google Drive)

| 파일 | 용도 | 다운로드 URL |
|---|---|---|
| Description.xlsx | 컬럼 설명서 | `https://docs.google.com/spreadsheets/d/1QN5dJA8U8JXLa-r1A7ngRgTJI2O2bf4D/export?format=xlsx` |
| Membership.csv | 멤버십 원본 데이터 | `https://drive.google.com/uc?id=1KsQjWpPbiM4HpTUaISKKxaqAN35Blig4` |

> **주의**: `edit?usp=...` URL로 gdown 사용 시 HTML이 받아짐 → 반드시 위 export/uc URL 사용

---

## 참고 GitHub

- [Fitness-Center-Retention-Analysis](https://github.com/bhutto17/Fitness-Center-Retention-Analysis) — EDA + Gradient Boosting (AUC 97.25%) + K-means
- [Churn-Prediction-Credit-Card](https://github.com/allmeidaapedro/Churn-Prediction-Credit-Card) — LightGBM 최고 성능
- [customer_churn_segmentation](https://github.com/biancaportela/customer_churn_segmentation) — LR·DT·RF + 클러스터링
