# XAI 기반 OTT 신규 고객 이탈 요인 분석 및 리텐션 전략

> SK플래닛 ASAC 10기 기업 연계 프로젝트 · 신통방통팀 4인 · 2026.04 ~ 2026.06
> 기준 보고서: [docs/XAI 기반 OTT 신규 고객 이탈 요인 분석 및 리텐션 전략.pdf](docs/XAI%20기반%20OTT%20신규%20고객%20이탈%20요인%20분석%20및%20리텐션%20전략.pdf)

국내 OTT 플랫폼의 신규 구독자 데이터로, 가입 후 21일(day0~day20)의 시청 행동만 보고 다음 달 재결제를 하지 않을 고객을 미리 찾는 프로젝트입니다.
예측에서 멈추지 않고 SHAP·PFI로 이탈 요인을 설명한 뒤, 행동 세그먼트별 리텐션 전략까지 연결했습니다.

---

## 한눈에 보기

| 항목 | 내용 |
|---|---|
| 출발점 | 프로모션으로 가입한 고객이 다른 고객보다 평균 28분 더 보고도 이탈률이 8.71%p 높았습니다(32.48% 대 23.77%). 시청량만으로는 이탈을 설명할 수 없었습니다 |
| 이탈 정의 | 가입 다음 달 재결제하지 않음 (`y = 1 - is_repurchase`), 재구독 72% · 이탈 28% |
| 데이터 | 23,081명 · 가입 후 21일 시청 기록 · 파생변수 91개 (VIF 정제) |
| 이탈 신호 | 가입 3일 내 미시청, 2~3주차 시청 유지율 감소, 장르 편중. SHAP과 PFI가 공통으로 지목한 변수만 채택 |
| 세그먼트 | 초기 안정성(1~2주차 시청 118분 기준) × 3주차 상태로 6개 세그먼트. 최위험군 B3의 이탈률 50.35% |
| 전략 | 게임형 퀘스트: 가입 3일 내 첫 시청 미션, 1주차 장르 추천 미션, 고위험군 복귀 미션 |
| 모델 | LR·RF·SVM·XGBoost·CatBoost 5개 모델의 5-fold OOF 스태킹 + Meta LR. ROC-AUC 0.886, 학습-검증 격차 0.004 |
| 한계 | 신규 가입 1개월 데이터라 고객 생애주기 추적과 A/B 검증은 하지 못했습니다 |

ROC-AUC 변화: 베이스라인 0.586 → 기초 파생변수 0.699 → 최종 변수 0.879 → Optuna 튜닝 0.885 → OOF 스태킹 0.886.
단일 모델 최고점인 CatBoost(0.885)는 학습-검증 격차가 0.066이라, 점수는 0.001 낮아도 격차가 0.004인 스태킹을 최종 모델로 골랐습니다.

## 역할 분담

| 구분 | 영역 |
|---|---|
| 권동근 단독 | 머신러닝 모델링, 5-fold OOF 스태킹 앙상블, Optuna 튜닝, FastAPI 파이프라인 서버(`app/`), Dify 연동 역할별 보고서 |
| 팀 공동 | 데이터 정제·EDA·파생변수 설계, XAI 해석, 행동 세그먼트, 리텐션 전략, Streamlit 대시보드 |

---

## 분석 과정 (notebooks/)

원본 → 전처리 → 피처 → EDA → 모델링 → 튜닝 → XAI·세그먼트 순으로 진행한 기록입니다.

### `01_preprocessing/` 전처리, 데이터 정의
| # | 노트북 | 내용 |
|---|---|---|
| 01 | data_processing | 원본(Membership·Views·Movies·mapping) 병합·정제 |
| 02 | data_contract | 행/열·중복·필수 컬럼 데이터 계약 |
| 03 | target_score_orientation | 타겟 방향 정의 (이탈=1, `y = 1 - is_repurchase`) |
| 04 | observation_window_policy | 관측창 정책 (가입 후 21일 코호트) |
| 05 | promotion_split | 프로모션 / 비프로모션 분리 기준 |

### `02_feature_engineering/` 피처 설계
| # | 노트북 | 내용 |
|---|---|---|
| 01~02 | feature_contract_rebuild (+patch) | 피처 계약 재구축 |
| 03~04 | feature_approval_and_dictionary (+patch2) | 피처 승인·딕셔너리 정리 |
| 05 | dataset_generation | 최종 학습 데이터셋 생성 (23,081행 × 91피처) |
| 06 | feature_mapping_AARRR | AARRR 프레임 매핑 |

### `03_eda/` 탐색적 분석
| # | 노트북 | 내용 |
|---|---|---|
| 01 | promotion_nonpromotion_EDA | 프로모션/비프로모션 분포 비교 |
| 02 | promotion_repurchase_2x2_EDA | 프로모션 × 재구매 2×2 교차 분석 |
| 03 | feature_distribution_redundancy_audit | 분포·다중공선성(VIF) 감사 |

### `04_modeling/` 모델링
| # | 노트북 | 내용 |
|---|---|---|
| 01 | baseline_growth_comparison | 베이스라인 비교 |
| 02 | model_family_comparison | 모델 패밀리 비교 (LR·RF·XGBoost·CatBoost·SVM) |

### `05_tuning/` 튜닝, 민감도
| # | 노트북 | 내용 |
|---|---|---|
| 01 | lightweight_candidate_tuning | 후보 모델 Optuna 하이퍼파라미터 튜닝 |
| 02 | payment_device_sensitivity | 결제 기기 피처 민감도 분석 |

### `06_xai_segmentation/` XAI, 세그먼트, 제언
| # | 노트북 | 내용 |
|---|---|---|
| 01 | SHAP_interpretation | SHAP 기반 이탈 요인 해석 |
| 02 | segmentation_design | 위험도 기반 세그먼트 설계 |
| 03 | business_recommendation_storyline | 세그먼트별 리텐션 전략 스토리라인 |

> 노트북은 결과 셀을 저장한 기록물입니다. 당시 중간 데이터를 기준으로 작성해 그대로 재실행하는 데는 제한이 있습니다. 재현은 아래 `app/` 파이프라인으로 합니다.

---

## 최종 산출물

### 1) 운영 파이프라인 `app/` (FastAPI)
노트북에서 확정한 결론을 원본 데이터부터 다시 돌릴 수 있는 파이프라인으로 정리했습니다.

| Step | 모듈 | 대응 과정 |
|---|---|---|
| 00 | `00_feature_engineering` | 원본 병합·파생변수 생성 |
| 01 | `01_data_contract` | 데이터 계약 검증 |
| 02·03 | `02_promotion_eda` · `03_2x2_eda` | EDA |
| 04 | `04_feature_audit` | 피처 감사 |
| 05 | `05_stacking` | Optuna 튜닝 → 5-fold OOF → Meta LR 스태킹 |
| 06 | `06_XAI` | SHAP 해석 |
| 07 | `07_segmentation` | 세그먼트 배정 |

### 2) Dify 챗봇, LLM 보고서
- `app/report.py` → `/pipeline/report/*` 가 역할별 HTML 보고서 생성 (CEO·CRM·Dev·SHAP)
- Dify 워크플로우 + Gemini 연동으로 보고서와 챗봇 서빙

### 3) Streamlit 대시보드 `dashboard/`
- `dashboard/app_crm_full_workbench.py`: 세그먼트별 이탈 분석과 전략을 보여 주는 CRM 워크벤치, Gemini 문구 생성 시연 포함
- 실행 방법은 아래 참고

---

## 데이터

기업이 제공한 비공개 실무 데이터라 저장소에 포함하지 않았습니다(`data/`는 gitignore). 학습된 모델(`.pkl`)과 캐시도 코드로 다시 만들기 때문에 제외했습니다.

파이프라인을 돌리려면 `data/01_raw/`에 원본 CSV 네 개가 필요합니다.

```
data/01_raw/
├── Membership_train.csv
├── Views_train.csv
├── Movies.csv
└── mapping.csv
```

`Membership_test.csv`, `Views_test.csv`를 함께 두면 테스트 평가 단계도 실행됩니다.

---

## 실행 방법

### 운영 파이프라인

```bash
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cd app
uvicorn main:app --port 8000
```

| 동작 | 엔드포인트 |
|---|---|
| API 문서 | `GET /docs` |
| 전체 실행 (최초 / 재학습) | `POST /pipeline/run-full` (00 → 05 스태킹 → 06 → 07) |
| 빠른 실행 (저장된 모델로 새 데이터 예측) | `POST /pipeline/run-fast` |
| 진행 상황 | `GET /pipeline/job/{job_id}` |
| 상태 확인 | `GET /pipeline/status` |

> **실행 확인 (2026-09-11)**: Python 3.13 새 가상환경에 `requirements.txt`만 설치하고 `data/01_raw/`에 원본 CSV를 둔 상태에서 `run-full`을 돌려 12단계가 모두 통과했습니다. 8코어 노트북에서 약 1시간 30분 걸렸습니다. Optuna 튜닝이 모델당 최대 30분, OOF가 3개 범위 × 5개 모델이라 대부분의 시간이 스태킹 단계에 들어갑니다.
> 재현 결과는 보고서와 같습니다. 세그먼트별 인원과 이탈률(B3 50.35% 등)이 일치하고, 스태킹 테스트 ROC-AUC는 0.887로 보고서의 0.886과 거의 같습니다. 튜닝이 시간 제한에 걸리는 환경에서는 소수점 셋째 자리가 조금 달라질 수 있습니다.
> 처음 클론한 환경에서는 라이브러리 버전 차이로 예전 `*.pkl`이 맞지 않을 수 있으니 `run-full`로 모델을 다시 만드세요.

### Streamlit 대시보드

```bash
pip install -r dashboard/requirements.txt
cd dashboard
streamlit run app_crm_full_workbench.py
```

대시보드 입력 CSV(`06x_expanded_dataset.csv` 등)는 `dashboard/data/`에 둡니다. 데이터를 넣은 상태에서 10개 화면이 모두 오류 없이 열리는 것을 확인했습니다(2026-09-11). Gemini 문구 생성까지 보려면 `.streamlit/secrets.toml.example`을 `.streamlit/secrets.toml`로 복사해 API 키를 넣습니다.

---

## 저장소 구조

```
.
├── notebooks/      분석 과정 (01_preprocessing → 06_xai_segmentation)
├── app/            운영 파이프라인 (FastAPI, step00~07) + 보고서·에이전트(Dify)
├── dashboard/      Streamlit CRM 대시보드
├── data/           원본·중간 데이터 (gitignore)
├── docs/           기준 보고서 PDF · 인수인계 · 아키텍처
├── requirements.txt
└── .gitignore
```
