# CRM 워크벤치 (Streamlit 대시보드)

프로모션(100원 딜)으로 가입한 고객을 세그먼트로 나누고, 세그먼트별 이탈 패턴과 CRM 전략을 보여 주는 대시보드입니다. 팀 공동 작업물입니다.

## 실행

PowerShell 기준:

```powershell
python -m pip install -r requirements.txt
streamlit run app_crm_full_workbench.py
```

입력 CSV는 `data/`에 둡니다. 기업이 제공한 비공개 데이터라 저장소에는 포함하지 않았습니다. 파일이 없으면 앱이 안내 메시지를 띄웁니다.

| 파일 | 용도 |
|---|---|
| `06x_expanded_dataset.csv` | 공식 입력 (파생변수 포함 분석 데이터셋) |
| `Membership_v2.csv`, `User_Mapping_v2.csv`, `View_History_v2.csv`, `Movie_Master_v2.csv` | W4 관측 분석, 메시지 시연용 원천 |

Gemini 문구 생성까지 보려면 `.streamlit\secrets.toml.example`을 `.streamlit\secrets.toml`로 복사한 뒤 API 키를 입력합니다. 실제 키는 Git에 올리지 않습니다.

```toml
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY"
```

## 화면 구성

| 화면 | 포함 내용 |
|---|---|
| Executive Summary | 전체·프로모션 모집단, 관측 이탈률, S1~S6 구성 |
| 데이터셋 소개 | 입력 파일, 분석 단위, 컬럼 역할, 사용하지 않는 주장 |
| 기초 EDA | 프로모션/비프로모션 비교, 주차 시청, 요금제·연령·성별 기술통계 |
| 세그먼트 설계 | hard gate 제거 기준, 기존 hard gate와 이동 규모 비교 |
| 심화 EDA | 세그먼트별 이탈/재구매 행동 차이, 실행 분기별 프로파일 |
| W4 관측 분석 | Day 21~27 관측 시청과 이탈의 동반 패턴, 연결 감사 |
| CRM 플레이북 | 메시지 후킹·복귀보상·체크포인트·리퍼럴, 내부 부류별 전략 |
| Gemini 메시지 시연 | 익명 사례 선택, 실제 시청 소재 통제, API 문구 생성 |
| 실험 설계 | 실험군·대조군·측정 지표 |
| 검증·한계 | 해시, 적용/금지 기준, 후속 필요 데이터 |

## 기준

- 공식 입력: `data/06x_expanded_dataset.csv`
- 메인 시연 대상: `is_promotion == 1`인 프로모션 구독 이벤트 11,904건
- 분석 단위: 고객 수가 아닌 구독 이벤트 수
- 메인 세그먼트: `watch_ratio_under_5m` hard gate 제거 S1~S6
- `watch_ratio_under_5m`: 메시지 보조 플래그로만 사용
- Gemini: 전략이나 대상 선정을 하지 않고 승인된 조건 안에서 문구만 생성

## 넣지 않은 것

초기 목업에 있던 C0~C3 군집, 난수 위험점수, 고정 SHAP/ROC-AUC/LTV/매출 수치, 실제 발송처럼 보이는 버튼, 작품 재구매율 기반 추천 문장은 넣지 않았습니다. 최종 기준과 맞지 않거나 원천 검증이 되지 않은 내용이기 때문입니다.

## W4 관측 분석 주의

W4 화면은 Day 21~27 시청의 관측 분석입니다. 프로모션·재구매·본인인증이 일치하는 구독 이벤트의 가입일을 우선 연결한 재구성값을 쓰고, 별도 검토 자료와 W4 시청 건수가 2건 다릅니다. 그래서 확정 수치가 아닌 관측값으로 다룹니다.

## 폴더

- `app_crm_full_workbench.py`: 앱
- `data/`: 입력 CSV (gitignore)
- `tools/validate_workbench_inputs.py`: 입력·세그먼트·W4 재계산 스크립트
- `VALIDATION_REPORT.md`: 재계산 검증 결과
