# XAI 기반 OTT 신규 고객 이탈 요인 분석 및 리텐션 전략

> SK_AX 기업연계 프로젝트 (ASAC 10기) · 신통방통팀
> 기준 보고서: [docs/XAI 기반 OTT 신규 고객 이탈 요인 분석 및 리텐션 전략.pdf](docs/XAI%20기반%20OTT%20신규%20고객%20이탈%20요인%20분석%20및%20리텐션%20전략.pdf)

OTT 신규 구독자의 가입 후 21일(day0~day20) 시청 행동을 분석해 이탈 가능성이 높은 유저를 예측하고,
SHAP 기반 XAI 해석으로 이탈 요인을 규명하여 세그먼트별 리텐션 전략까지 도출한 프로젝트입니다.

이 저장소는 원본 데이터에서 출발해 어떤 과정을 거쳐 결론에 도달했는가를 단계별로 보여주는 것을 중심으로 정리했습니다.
Dify 챗봇, HTML 보고서, 대시보드는 그 과정의 최종 산출물입니다.

---

## 분석 여정 (notebooks/)

원본 → 전처리 → 피처 → EDA → 모델링 → 튜닝 → XAI/세그먼트 순으로 하나씩 진행한 기록입니다.

### `01_preprocessing/` — 전처리, 데이터 정의
| # | 노트북 | 내용 |
|---|---|---|
| 01 | data_processing | 원본(Membership·Views·Movies·mapping) 병합·정제 |
| 02 | data_contract | 행/열·중복·필수 컬럼 데이터 계약 |
| 03 | target_score_orientation | 타겟 방향 정의 (이탈=1, `y = 1 - is_repurchase`) |
| 04 | observation_window_policy | 관측창 정책 (가입 후 21일 코호트) |
| 05 | promotion_split | 프로모션 / 비프로모션 분리 기준 |

### `02_feature_engineering/` — 피처 설계
| # | 노트북 | 내용 |
|---|---|---|
| 01~02 | feature_contract_rebuild (+patch) | 피처 계약 재구축 |
| 03~04 | feature_approval_and_dictionary (+patch2) | 피처 승인·딕셔너리 정리 |
| 05 | dataset_generation | 최종 학습 데이터셋 생성 (23,081행 × 91피처) |
| 06 | feature_mapping_AARRR | AARRR 프레임 매핑 |

### `03_eda/` — 탐색적 분석
| # | 노트북 | 내용 |
|---|---|---|
| 01 | promotion_nonpromotion_EDA | 프로모션/비프로모션 분포 비교 |
| 02 | promotion_repurchase_2x2_EDA | 프로모션 × 재구매 2×2 교차 분석 |
| 03 | feature_distribution_redundancy_audit | 분포·다중공선성(VIF) 감사 |

### `04_modeling/` — 모델링
| # | 노트북 | 내용 |
|---|---|---|
| 01 | baseline_growth_comparison | 베이스라인 비교 |
| 02 | model_family_comparison | 모델 패밀리 비교 (LR·RF·XGBoost·CatBoost·SVM) |

### `05_tuning/` — 튜닝, 민감도
| # | 노트북 | 내용 |
|---|---|---|
| 01 | lightweight_candidate_tuning | 후보 모델 Optuna 하이퍼파라미터 튜닝 |
| 02 | payment_device_sensitivity | 결제 기기 피처 민감도 분석 |

### `06_xai_segmentation/` — XAI, 세그먼트, 제언
| # | 노트북 | 내용 |
|---|---|---|
| 01 | SHAP_interpretation | SHAP 기반 이탈 요인 해석 |
| 02 | segmentation_design | 위험도 기반 세그먼트 설계 |
| 03 | business_recommendation_storyline | 세그먼트별 리텐션 전략 스토리라인 |

> 노트북은 과정의 기록물(결과 셀 임베드)입니다. 당시 중간 데이터 기준이라 그대로 재실행은 일부 제한될 수 있습니다.

---

## 최종 산출물

위 여정이 도달한 결과물입니다.

### 1) 운영 파이프라인 — `app/` (FastAPI)
노트북에서 확정된 결론을 재현 가능한 파이프라인으로 정리한 버전.

| Step | 모듈 | 대응 여정 |
|---|---|---|
| 00 | `00_feature_engineering` | 01·02 전처리/피처 |
| 01 | `01_data_contract` | 데이터 계약 |
| 02·03 | `02_promotion_eda` · `03_2x2_eda` | 03 EDA |
| 04 | `04_feature_audit` | 피처 감사 |
| 05 | `05_stacking` | 04·05 모델링·튜닝 → 스태킹 앙상블 (Optuna + Meta LR) |
| 06 | `06_XAI` | SHAP 해석 |
| 07 | `07_segmentation` | 세그먼트 |

### 2) Dify 챗봇, LLM 보고서
- `app/report.py` → `/pipeline/report/*` 가 역할별 HTML 보고서 생성 (CEO·CRM·Dev·SHAP)
- Dify 워크플로우 + Gemini 연동으로 보고서/챗봇 서빙

### 3) Streamlit 대시보드 — `dashboard/`
- `dashboard/app_crm_full_workbench.py` — CRM 워크벤치 (세그먼트별 이탈 분석·전략 시연, Gemini 문구 생성)
- 실행: `cd dashboard && streamlit run app_crm_full_workbench.py`

> PDF 05 운영 적용의 두 축 = Agent(Dify) + Streamlit 대시보드 가 각각 `app/`(보고서·에이전트)과 `dashboard/`에 대응합니다.

---

## 핵심 결과

| 지표 | 값 |
|---|---|
| 학습 데이터 | 23,081명 (가입 후 21일 코호트) |
| 최종 피처 | 91개 (VIF 정제 완료) |
| 최종 모델 | 스태킹 앙상블 (RF·XGBoost·CatBoost·SVM + Meta LR) |
| 예측 목표 | 이탈 여부 (`y = 1 - is_repurchase`, 이탈=1) |

---

## 저장소 구조

```
.
├── notebooks/      분석 여정 (01_preprocessing → 06_xai_segmentation)
├── app/            운영 파이프라인 (FastAPI, step00~07) + 리포트/에이전트(Dify)
├── dashboard/      Streamlit CRM 대시보드 (운영 적용)
├── data/           원본·중간 데이터 (gitignore)
├── docs/           기준 보고서 PDF · 인수인계 · 아키텍처
├── requirements.txt
└── .gitignore
```

> 데이터, 학습된 모델(.pkl), 캐시는 용량/재현성을 위해 git에서 제외하며, 코드로 재생성합니다.

---

## 실행 방법 (운영 파이프라인)

```bash
python -m venv .venv && .venv/Scripts/activate     # Windows
pip install -r requirements.txt
# 원본 데이터를 data/01_raw/ 에 배치
cd app
uvicorn main:app --reload --port 8000
```

| 동작 | 엔드포인트 |
|---|---|
| 전체 실행 (최초 / 재학습) | `POST /pipeline/run-full` (00→05 스태킹→06→07) |
| 빠른 실행 (새 데이터) | `POST /pipeline/run-fast` |
| 상태 확인 | `GET /pipeline/status` |

> 처음 클론한 환경에서는 라이브러리 버전 차이로 기존 `*.pkl` 이 호환되지 않을 수 있습니다. `run-full` 로 모델을 재생성하세요.
