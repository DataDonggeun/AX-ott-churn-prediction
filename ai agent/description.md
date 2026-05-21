# Membership Features 파생변수 설명서

- **입력**: `260510_merged_v2/Membership_v2.csv` (23,343명)
- **관측창**: 가입일 기준 0~20일 고정 (CUTOFF=21일)
- **출력**: `260510_features/Membership_features.csv`
- **생성일**: 2026-05-10
- **참고**: park.ingyeom, kim.kwangil, legacy v3, 어드바이저 문서

---

## 원본 변수 (주요 유지)

| 변수 | 설명 |
|------|------|
| `USER_KEY` | 유저 식별자 |
| `price` | 결제 금액 |
| `billing_method` | 결제 방식 코드 |
| `is_churn_prevented` | 이탈 방지 처리 여부 |
| `is_repurchase` | 재구매 여부 **(타겟, 0=이탈 1=재구매)** |
| `payment_device` | 결제 기기 |
| `is_user_verified` | 본인인증 여부 |
| `gender` | 성별 |
| `age` | 연령 |

> ❌ 제외: `coinReceived`(누수), `max_screen`(is_standard/premium 대체), `reg_date`/`end_date`(duration_days 대체), `reg_hour`(reg_hour_group 대체), `is_promotion`(price로 커버)

---

## 파생변수 (약 60개)

### 📅 날짜/시간 (2개)

| 변수 | 설명 |
|------|------|
| `duration_days` | 구독 기간 (일) |
| `reg_hour_group` | 가입 시간대 (0=새벽, 1=오전, 2=오후, 3=저녁) |

### 💰 가격 (2개)

| 변수 | 설명 |
|------|------|
| `is_usd` | 달러 결제 여부 (price < 100) |
| `price_per_day` | 하루당 비용 |

### 📱 기기/요금제 (3개)

| 변수 | 설명 |
|------|------|
| `device_group` | mobile / pc / tv |
| `is_standard` | 2화면 요금제 |
| `is_premium` | 4화면 요금제 |

### 👤 인구통계 (5개)

| 변수 | 설명 |
|------|------|
| `age_group` | 연령대 (0=10대~4=50대+) |
| `gender_enc` | 성별 인코딩 (M=1, F=0, 미상=2) |
| `age_x_screen` | 나이 × max_screen (가족 공유 패턴) |
| `verified_x_age` | 본인인증 × 나이 |
| `is_senior_unverified` | 50대+ 미인증 여부 |

### 📺 시청 기본 (9개)

| 변수 | 설명 |
|------|------|
| `total_sessions` | 총 시청 횟수 |
| `unique_movies` | 고유 영화 수 |
| `active_days` | 시청 일수 |
| `total_watch_time` | 총 시청 시간 (분) |
| `avg_session_time` | 평균 시청 시간 |
| `std_session_time` | 시청 시간 표준편차 |
| `activity_rate` | 활동률 (active_days / CUTOFF) |
| `watch_per_day` | 하루 평균 시청 횟수 |
| `avg_rewatch_ratio` | 재시청 비율 |

### ⏱️ 온보딩/이탈 신호 (5개)

| 변수 | 설명 | 비고 |
|------|------|------|
| `has_watch_history` | 시청 이력 여부 | |
| `cold_start` | 7일 이내 첫 시청 | kim.kwangil |
| `signup_to_first_watch` | 첫 시청까지 일수 | |
| `recency` | ★ cutoff(20일) - 마지막 시청일 | end_date 아님 (누수 방지) |
| `sessions_per_active_day` | 시청 집중도 | park.ingyeom |

### 📊 시청 패턴 (7개) — park.ingyeom + 어드바이저

| 변수 | 설명 |
|------|------|
| `max_inactive_gap_days` | 최장 미시청 기간 |
| `max_daily_watch_time` | 하루 최대 시청량 |
| `max_day_share` | 하루 집중도 (max_daily / total) |
| `vh_short_watch_ratio` | 5분 이하 시청 비율 (탐색/오류 신호) |
| `vh_one_min_watch_ratio` | 1분 시청 비율 |
| `vh_last7d_watch_ratio` | 마지막 7일 시청 집중도 |
| `vh_title_div_per_day` | 하루당 타이틀 다양성 |

### 📅 주차별 시청 (12개)

| 변수 | 설명 |
|------|------|
| `dur_w1/w2/w3` | 주차별 시청 시간 (분) |
| `week1/2/3_sessions` | 주차별 시청 횟수 |
| `week1/2/3_active` | 주차별 활동 일수 |
| `retention_w2/w3` | 주차별 시청 여부 (binary) |
| `retention_w2/w3_ratio` | 주차별 시청 비율 |

### 📈 트렌드 (7개) — park.ingyeom

| 변수 | 설명 |
|------|------|
| `w2_minus_w1` | 1→2주차 시청량 변화 |
| `w3_minus_w2` | 2→3주차 시청량 변화 |
| `w3_minus_w1` | 전체 트렌드 방향 |
| `daily_watch_slope` | 시청 모멘텀 (w3-w1)/14 |
| `front_loaded_flag` | 1주차 50%+ 집중 |
| `late_binge_flag` | 3주차 50%+ 집중 |
| `steady_3week_flag` | 3주 모두 시청 |

### 🍿 몰아보기 (3개)

| 변수 | 설명 |
|------|------|
| `one_day_binge_flag` | 하루 80%+ 집중 시청 |
| `binge_day_count` | 하루 3회 이상 시청한 날 수 |
| `weekend_watch_ratio` | 주말 시청 비율 |

### 🎬 장르/콘텐츠 (11개)

| 변수 | 설명 | 근거 |
|------|------|------|
| `horror_ratio` | 공포 시청 비율 | EDA: 이탈률 29.4% 1위 |
| `family_ratio` | Animation/Family 비율 | EDA: 이탈률 12% 최저 |
| `drama_ratio` | Drama 비율 | |
| `action_ratio` | Action/Adventure 비율 | |
| `thriller_ratio` | Thriller/Crime 비율 | |
| `sf_ratio` | SF/Fantasy 비율 | |
| `comedy_ratio` | Comedy 비율 | |
| `romance_ratio` | Romance 비율 | |
| `genre_entropy_norm` | 장르 다양성 엔트로피 (0~1) | park.ingyeom |
| `is_new_movie_ratio` | 신작(202103) 시청 비율 | |
| `stream_watch_interaction` | max_screen × total_watch_time | |

---

## 관측창 정의

```
reg_date <= watch_date <= reg_date + 20일 (CUTOFF=21)
```
- 구독 전 로그 제거: watch_date < reg_date
- 관측창 이후 로그 제거: watch_date > cutoff_date
- recency = cutoff_date - last_watch_date (end_date 사용 금지 — 누수)

---

## ❌ 제외된 변수

| 변수 | 이유 |
|------|------|
| `coinReceived` | is_churn과 동일 정보 — 데이터 누수 |
| `max_screen` | is_standard/is_premium으로 대체 |
| `end_date` | 모델 입력 금지 (결과 정보) |
| `reg_date`, `reg_hour` | 파생변수로 대체 |
| `is_promotion` | price로 이미 커버 (중복) |

---

## 🔬 다중공선성 분석 후 추가 제거 (VIF 기반)

**파일**: `Membership_features_clean.csv` (Membership_features.csv에서 제거 후 저장)

### 제거 이유별 분류

| 제거 이유 | 변수 |
|-----------|------|
| **총합 = 부분합 (완전 중복)** | `total_watch_time` (=dur_w1+w2+w3), `week1/2/3_active`, `week1/2/3_sessions` |
| **파생 관계로 중복** | `no_week1_flag`, `no_week3_flag`, `w2_minus_w1`, `w3_minus_w2`, `active_span_days`, `signup_to_first_watch`, `steady_3week_flag` |
| **거의 상수** | `has_watch_history` (시청 유저는 전부 1) |

### 제거 후 컬럼 수
- 제거 전: 100개
- 제거 수: 14개
- **최종: 약 86개**

### VIF 판단 기준
- `inf/심각` → 수학적 완전 중복 → 제거
- `주의` → XGBoost에서 허용, SHAP 후 최종 판단
- `양호` → 유지

---

## 🤖 XAI 분석 결과 (2026-05-10)

**모델**: XGBoost (`n_estimators=500, max_depth=6, scale_pos_weight=spw, early_stopping`)
**분석**: SHAP TreeExplainer, Permutation Importance, Surrogate Tree, Counterfactual
**입력**: `Membership_features_clean.csv` (23,343명, 81개 변수)

---

### SHAP Top 20 변수 중요도

| 순위 | 변수 | 평균 |SHAP| | 방향 | 해석 |
|------|------|---------|------|------|
| 1 | `dur_w3` | 0.55 | ↑ 재구매 | **3주차(15~21일) 시청 시간** — 가장 강력한 단일 예측 변수 |
| 2 | `retention_w3_ratio` | 0.37 | ↑ 재구매 | 3주차 시청 비율 — dur_w3와 방향 일치, 상호 보완 |
| 3 | `drama_ratio` | 0.31 | ↑ 재구매 | 드라마 시청 비율 높을수록 재구매 |
| 4 | `family_ratio` | 0.29 | ↑ 재구매 | 패밀리/애니 비율 — EDA 이탈률 12% 최저 검증 |
| 5 | `romance_ratio` | 0.28 | ↑ 재구매 | 로맨스 시청 비율 |
| 6 | `retention_w2_ratio` | 0.27 | ↑ 재구매 | 2주차 시청 비율 |
| 7 | `price_per_day` | 0.25 | ↓ 낮을수록 재구매 | 하루 구독 단가 — 고가 요금제 이탈 위험 |
| 8 | `thriller_ratio` | 0.23 | **↓ 이탈** | 스릴러 비율 높을수록 이탈 (공포 계열과 동일 패턴) |
| 9 | `week1_ratio` | 0.22 | 복합 | 1주차 시청 집중도 |
| 10 | `action_sf_thriller_affinity` | 0.21 | 복합 | 액션/SF/스릴러 친화도 복합 지표 |
| 11 | `action_ratio` | 0.18 | 복합 | |
| 12 | `median_session_time` | 0.15 | ↑ 재구매 | 중앙 시청 시간 |
| 13 | `dur_w2` | 0.14 | ↑ 재구매 | 2주차 시청 시간 |
| 14 | `max_day_share` | 0.14 | **↓ 이탈** | 하루 집중도 높으면 이탈 — 몰아보기 후 이탈 패턴 |
| 15 | `stream_watch_interaction` | 0.13 | ↑ 재구매 | 화면 수 × 총 시청 시간 |
| 16 | `is_churn_prevented` | 0.13 | ↑ 재구매 | 이탈 방지 처리 효과 존재 |
| 17 | `max_session_time` | 0.12 | ↑ 재구매 | |
| 18 | `duration_days` | 0.12 | 극단적 낮은 값 → 이탈 | 단기 구독자 이탈 신호 |
| 19 | `week2_ratio` | 0.12 | ↑ 재구매 | |
| 20 | `w3_minus_w1` | 0.11 | ↑ 재구매 | 전체 시청 트렌드 상승 = 재구매 |

---

### Surrogate Tree 핵심 규칙 (max_depth=4)

```
[이탈 규칙]
IF dur_w3 <= 3.5                    # 3주차 시청 거의 없음
   AND dur_w2 <= 62.5               # 2주차도 적음
   AND week1_ratio <= 0.355         # 1주차 집중도도 낮음
   AND price_per_day <= 13.89       # 저가 요금제
→ 이탈 확률 높음

[재구매 규칙]
IF dur_w3 > 3.5                     # 3주차에 계속 시청
   AND action_sf_thriller_affinity <= 0.5   # 액션/SF/스릴러 편향 낮음
   AND horror_ratio <= 0.233        # 공포 집중 아님
→ 재구매 확률 높음
```

**핵심**: 이탈/재구매의 분기점은 사실상 **"3주차(15~21일)에도 계속 보는가"**

---

### XAI 기반 제거 검토 변수

> XGBoost는 노이즈 변수를 자동으로 낮게 평가하므로 **성능상 필수 제거는 아님**.
> 해석 단순화 목적일 때만 제거 고려.

| 변수 | SHAP 순위 | 제거 이유 | 권고 |
|------|-----------|-----------|------|
| `retention_w2`, `retention_w3` (binary) | Top 20 밖 | ratio 버전(`retention_w2/w3_ratio`)이 Top 6에 이미 존재 | 제거 가능 |
| `reg_hour_group` | Top 20 밖 | 가입 시간대 — 예측력 낮음 | 제거 가능 |
| `is_usd` | Top 20 밖 | `price_per_day`가 이미 가격 정보 포함 | 제거 가능 |
| `vh_one_min_watch_ratio` | Top 20 밖 | `vh_short_watch_ratio`(5분)와 중복 | 제거 가능 |
| `avg_rewatch_ratio` | Top 20 밖 | 예측력 미미 | 제거 가능 |
| `front_loaded_flag`, `late_binge_flag` | Top 20 밖 | `week1_ratio`, `dur_w3`가 이미 포함 | 제거 가능 |
| `weekend_watch_ratio` | Top 20 밖 | 예측력 미미 | 제거 가능 |
| `is_new_movie_ratio` | Top 20 밖 | 예측력 미미 | 제거 가능 |
| `age_x_screen`, `verified_x_age`, `is_senior_unverified` | Top 20 밖 | 인구통계 상호작용 — 예측력 낮음 | 선택적 제거 |

**유지 권고** (Top 20 밖이지만 의미 있음):
- `recency` — Permutation Top 20 내, 경계 고객 판별에 중요
- `horror_ratio` — Surrogate Tree 분기점으로 등장
- `cold_start` — 온보딩 신호, 초반 이탈 설명에 필요
- `active_days` — Counterfactual에서 개입 가능한 변수
