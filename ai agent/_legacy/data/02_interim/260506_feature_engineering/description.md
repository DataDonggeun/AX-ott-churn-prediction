# Membership v3 파생변수 설명서

- **원본 파일**: `promotion_0_membership_v2.csv` (15개 컬럼)
- **생성 파일**: `promotion_0_membership_v3.csv` (62개 컬럼)
- **추가 파생변수**: 47개

---

## 원본 변수 (15개)

| 변수 | 설명 |
|------|------|
| `USER_KEY` | 유저 식별자 |
| `product_code` | 구독 상품 코드 |
| `price` | 결제 금액 |
| `billing_method` | 결제 방식 코드 |
| `max_screen` | 동시 접속 가능 화면 수 |
| `is_promotion` | 100원 프로모션 여부 |
| `is_churn_prevented` | 이탈 방지 처리 여부 |
| `is_repurchase` | 재구매 여부 (타겟 변수, 0=이탈 1=재구매) |
| `payment_device` | 결제 기기 |
| `is_user_verified` | 본인인증 여부 |
| `gender` | 성별 (M/F) |
| `age` | 나이 (5세 단위, 예: 35=31~35세) |
| `reg_date` | 가입일 |
| `reg_hour` | 가입 시각 |
| `end_date` | 구독 종료일 |

---

## 파생변수 (47개)

### 📅 날짜/시간 (2개)

| 변수 | 설명 | 계산 방법 |
|------|------|-----------|
| `duration_days` | 구독 기간 (일) | end_date - reg_date |
| `reg_hour_group` | 가입 시간대 | 0=새벽(0~5시), 1=오전(6~11시), 2=오후(12~17시), 3=저녁(18~23시) |

### 💰 가격 (2개)

| 변수 | 설명 | 계산 방법 |
|------|------|-----------|
| `is_usd` | 달러 결제 여부 | price < 100이면 1 (이탈률 37.5% vs 원화 26.5%) |
| `price_per_day` | 하루당 비용 | price / duration_days |

### 📦 상품/기기 (5개)

| 변수 | 설명 | 계산 방법 |
|------|------|-----------|
| `is_family_plan` | 공유 계정 여부 | max_screen > 1이면 1 |
| `device_group` | 기기 그룹 | mobile(ios/android/mobile) / pc / tv(smarttv/ott) |
| `is_basic` | 1화면 요금제 여부 | max_screen == 1 |
| `is_standard` | 2화면 요금제 여부 | max_screen == 2 |
| `is_premium` | 4화면 요금제 여부 | max_screen == 4 |

### 👤 인구통계 (6개)

| 변수 | 설명 | 계산 방법 |
|------|------|-----------|
| `age_group` | 연령대 | 0=10대, 1=20대, 2=30대, 3=40대, 4=50대+ (SHAP 2위 검증) |
| `gender_enc` | 성별 인코딩 | M=1, F=0, 미상=2 |
| `age_x_screen` | 나이 × 동시접속 수 | 가족 공유 패턴 |
| `verified_x_age` | 본인인증 × 나이 | 인증한 고연령 유저 = 충성 유저 가설 |
| `is_senior_unverified` | 50대+ 미인증 여부 | 이탈 위험군 가설 |
| `is_young_unverified` | 25세 이하 미인증 여부 | 체험 후 이탈 가설 |

### 🎬 장르/콘텐츠 (11개)

View History + Movie 데이터를 유저 단위로 집계한 피처

| 변수 | 설명 |
|------|------|
| `genre_diversity` | 시청한 장르 종류 수 (취향 다양성) |
| `korean_ratio` | 한국 영화 시청 비율 (0~1) |
| `avg_showtime` | 평균 영화 러닝타임 (분) |
| `genre_액션_ratio` | 액션 장르 시청 비율 (0~1) |
| `genre_드라마_ratio` | 드라마 장르 시청 비율 (0~1) |
| `genre_로맨스_ratio` | 로맨스 장르 시청 비율 (0~1) |
| `genre_스릴러_ratio` | 스릴러 장르 시청 비율 (0~1) |
| `genre_애니메이션_ratio` | 애니메이션 장르 시청 비율 (0~1) |
| `genre_공포_ratio` | 공포 장르 시청 비율 (0~1) |
| `genre_코미디_ratio` | 코미디 장르 시청 비율 (0~1) |
| `genre_SF_ratio` | SF 장르 시청 비율 (0~1) |

> 시청 이력이 없는 유저의 장르 관련 피처는 모두 0으로 처리

### 📺 View History 기반 (23개)

| 변수 | 설명 | 계산 방법 |
|------|------|-----------|
| `total_sessions` | 총 시청 횟수 | COUNT |
| `unique_movies` | 고유 영화 수 | NUNIQUE(MOVIE_NUM) |
| `active_days` | 시청한 일수 | NUNIQUE(watch_date) |
| `avg_session_time` | 평균 시청 시간 (분) | MEAN(watch_time) |
| `activity_rate` | 활동률 | active_days / duration_days |
| `watch_per_day` | 하루 평균 시청 횟수 | total_sessions / active_days |
| `avg_rewatch_ratio` | 재시청 비율 | (total_sessions - unique_movies) / total_sessions |
| `signup_to_first_watch` | 첫 시청까지 걸린 일수 | MIN(days_since_reg) |
| `recency` | 마지막 시청 ~ 구독 종료까지 남은 일수 | (end_date - last_watch_date).days |
| `completion_rate` | 완주율 | MEAN(watch_time / showtime_min), 0~1 클리핑 |
| `weekend_watch_ratio` | 주말 시청 비율 | 주말 세션 / 전체 세션 |
| `max_gap_between_watch_days` | 최대 연속 미시청 기간 (일) | MAX(시청일 간격) |
| `dur_w1` | 1주차(0~6일) 시청 시간 | SUM(watch_time) in week 1 |
| `dur_w2` | 2주차(7~13일) 시청 시간 | SUM(watch_time) in week 2 |
| `dur_w3` | 3주차(14~20일) 시청 시간 | SUM(watch_time) in week 3 |
| `retention_w2` | 2주차 시청 여부 | dur_w2 > 0이면 1 |
| `retention_w3` | 3주차 시청 여부 | dur_w3 > 0이면 1 |
| `retention_w2_ratio` | 1주차 대비 2주차 시청 시간 비율 | dur_w2 / dur_w1 |
| `retention_w3_ratio` | 2주차 대비 3주차 시청 시간 비율 | dur_w3 / dur_w2 |
| `is_new_movie` | 신작 의존도 | 21년 3월 신작 시청 비율 |
| `binge_day_count` | 폭식 시청일 수 | 하루 3회 이상 시청한 날 수 |
| `has_watch_history` | 시청 이력 여부 | 1이면 시청 기록 있음, 0이면 없음 |

> 시청 이력이 없는 유저의 View History 피처는 모두 0으로 처리

### 🔗 교호작용 변수 (2개)

| 변수 | 설명 | 계산 방법 |
|------|------|-----------|
| `stream_watch_interaction` | 요금제 × 총 시청량 | max_screen × total_watch_time |
| `plan_promotion` | 요금제 × 프로모션 여부 | max_screen × is_promotion |

---

## ❌ 검토 후 제외된 파생변수

| 변수 | 제외 이유 |
|------|-----------|
| `reg_weekday` | 데이터가 2021년 3월 한 달에 집중되어 요일 효과 미미 |
| `is_weekend_reg` | 동일 이유 |
| `is_month_start_reg` | 급여일 효과 가설 약함 + 데이터 특성상 무의미 |
| `billing_group` | is_usd와 onestore 완전 중복, 나머지 채널도 불확실 |
| `price_tier` | price, is_usd, price_per_day로 이미 충분히 표현됨 |
| `price_per_screen` | price와 상관관계 0.745, unique 값 31개 뿐 (price ÷ {1,2,4}) |
| `weekday_watch_ratio` | = 1 - weekend_watch_ratio (완전 중복) |
| `is_new_product` | pk_2xxx 분류 기준 불확실, 모델 노이즈 가능성 |
| `is_apple_ecosystem` | iOS + billing_method=151 동시 충족 유저 수 적음 |
| `is_long_sub` | duration_days와 중복 |
| `hour_x_weekend` | reg_hour와 중복, 실제 효과 미미 |
| `is_promotion` | promotion_0 그룹은 전원 0 → 상수, 분산 없음 |
| `plan_promotion` | is_promotion=0으로 고정이라 항상 0 → 상수 |
| `max_screen` | is_standard/is_premium으로 대체 (완전 중복, VIF=inf) |
| `is_basic` | 더미 함정 기준 범주 — is_standard=0, is_premium=0이면 자동으로 basic (VIF=inf) |
| `is_family_plan` | = 1 - is_basic = is_standard + is_premium, 완전 중복 (VIF=inf) |
| `total_watch_time` | ≈ dur_w1 + dur_w2 + dur_w3 합산값, 거의 동일한 정보 (VIF=300) |

---

## 분석 진행 기록

### 전처리 파이프라인
| 파일 | 컬럼 수 | 설명 |
|------|---------|------|
| `promotion_0_membership_v2.csv` | 15개 | 원본 |
| `promotion_0_membership_v3.csv` | 59개 | 파생변수 추가 후 |
| `promotion_0_membership_v4.csv` | 49개 | SHAP 하위 20% 제거 후 최종 |

### 제거 단계별 요약
1. **기획 단계 제거** (13개) — 중복/상수/무의미 변수
2. **VIF 검토 제거** (3개) — is_basic, is_family_plan, total_watch_time
3. **SHAP 하위 20% 제거** (10개) — binge_day_count, is_user_verified, is_young_unverified, is_premium, retention_w2, retention_w3, has_watch_history, is_senior_unverified, is_usd, korean_ratio

### 최종 모델 성능 (v4, 39개 피처)
| 지표 | 값 |
|------|-----|
| AUC-ROC | 0.6638 |
| F1 (재구매 기준) | 0.7708 |
| F1 (이탈 기준) | 0.4270 |
| 최적 임계값 | 0.6 |

### SHAP 상위 5개 이탈 요인 (v4)
1. `duration_days` — 구독 기간 (압도적 1위, 0.31)
2. `price` — 결제 금액 (0.20)
3. `billing_method` — 결제 방식
4. `recency` — 마지막 시청 ~ 종료일
5. `avg_showtime` — 평균 영화 러닝타임

### 세그먼트 분석 결과
| 세그먼트 | 이탈률 | 정의 |
|---------|--------|------|
| 단기+달러 | **100.0%** | 구독 31일 미만 + 달러 결제 |
| 단기구독 | **99.5%** | 구독 31일 미만 |
| 장기+활성 | 40.9% | 구독 31일 이상 + 최근 5일 내 시청 |
| 일반 | 27.0% | 그 외 |

### LIME 분석 결과
| 구분 | 이탈/재구매 확률 | 주요 기여 변수 |
|------|----------------|----------------|
| 이탈 예측 고객 | 이탈 99.7% | duration_days(↑이탈), recency(↑이탈), price 고가(↓이탈) |
| 재구매 예측 고객 | 재구매 95.0% | price 중가(↑재구매), recency 높음(↑재구매), completion_rate(↑재구매) |

**핵심 인사이트**
- `duration_days <= 31` — 단기 구독이 이탈의 가장 강력한 신호
- `recency` — 마지막 시청 시점이 종료일에 가까울수록 이탈 위험
- `completion_rate > 0.55` — 영화를 끝까지 보는 유저는 재구매 경향
- 고가 요금제(7900~10900원) 유저는 상대적으로 충성도 높음

### 신규 데이터 EDA 결과 (Movies.csv Category 기반)
| 장르 | 이탈률 | 비고 |
|------|--------|------|
| Horror | 29.4% | 가장 높음 — 충동적 시청 후 이탈 패턴 |
| Action/Adventure | 27.2% | 높음 |
| Thriller/Crime | 26.8% | 높음 |
| Animation/Family | 12.0% | 가장 낮음 — 가족 단위 장기 구독 |
| Drama | 13.0% | 낮음 — 시리즈 연속 시청 유도 |

### 📝 추후 추가 예정 파생변수 (신규 데이터 기반)
- `max_consecutive_days` — 최대 연속 시청 일수
- `avg_sessions_per_day` — 하루 평균 시청 횟수
- `max_daily_sessions` — 하루 최대 시청 횟수
- `horror_ratio` — 공포 장르 시청 비율 (이탈 신호)
- `family_ratio` — Animation/Family 비율 (재구매 신호)
- `genre_consistency` — 장르 일관성 (매번 같은 장르만 보는지)
