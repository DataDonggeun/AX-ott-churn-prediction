import json, sys
sys.stdout.reconfigure(encoding='utf-8')

with open('c:/Users/USER/OneDrive/바탕 화면/AX/EDA/charts_b64.json') as f:
    C = json.load(f)

def img(key, caption='', width='100%'):
    return f'''
<figure style="margin:16px 0;">
  <img src="data:image/png;base64,{C[key]}" style="width:{width};border-radius:8px;box-shadow:0 2px 10px rgba(0,0,0,0.10);" alt="{caption}">
  {f'<figcaption style="text-align:center;font-size:12px;color:#888;margin-top:6px;">{caption}</figcaption>' if caption else ''}
</figure>'''

html = f'''<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <title>Membership EDA 보고서</title>
  <style>
    body {{
      font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif;
      background: #f4f6fb;
      color: #222;
      margin: 0;
      padding: 30px 0;
    }}
    .container {{
      max-width: 1100px;
      margin: 0 auto;
      background: #fff;
      border-radius: 12px;
      box-shadow: 0 4px 24px rgba(0,0,0,0.10);
      padding: 40px 50px 60px 50px;
    }}
    h1 {{
      font-size: 26px;
      color: #1a3a6b;
      border-bottom: 3px solid #2962a2;
      padding-bottom: 10px;
      margin-bottom: 6px;
    }}
    .subtitle {{
      color: #888;
      font-size: 13px;
      margin-bottom: 30px;
    }}
    h2 {{
      font-size: 17px;
      color: #fff;
      background: #2962a2;
      padding: 8px 16px;
      border-radius: 6px;
      margin-top: 40px;
      margin-bottom: 12px;
    }}
    h3 {{
      font-size: 14px;
      color: #1a3a6b;
      background: #dce8f7;
      padding: 5px 12px;
      border-radius: 4px;
      margin-top: 22px;
      margin-bottom: 10px;
    }}
    ul {{
      margin: 6px 0 6px 20px;
      padding: 0;
    }}
    li {{
      font-size: 13px;
      margin-bottom: 4px;
      line-height: 1.7;
    }}
    .warn {{
      background: #fff8e1;
      border-left: 4px solid #f59e0b;
      padding: 8px 14px;
      border-radius: 4px;
      font-size: 13px;
      margin: 10px 0;
    }}
    .info {{
      background: #e8f4fd;
      border-left: 4px solid #2962a2;
      padding: 8px 14px;
      border-radius: 4px;
      font-size: 13px;
      margin: 10px 0;
    }}
    .done {{
      background: #e8f5e9;
      border-left: 4px solid #43a047;
      padding: 8px 14px;
      border-radius: 4px;
      font-size: 13px;
      margin: 10px 0;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 12.5px;
      margin: 10px 0 14px 0;
    }}
    thead tr {{
      background: #2962a2;
      color: #fff;
    }}
    thead th {{
      padding: 7px 10px;
      text-align: left;
      font-weight: bold;
    }}
    tbody tr:nth-child(even) {{ background: #f0f5ff; }}
    tbody tr:nth-child(odd)  {{ background: #fff; }}
    tbody td {{
      padding: 6px 10px;
      border-bottom: 1px solid #e0e8f5;
      vertical-align: top;
    }}
    .tag {{
      display: inline-block;
      padding: 2px 8px;
      border-radius: 10px;
      font-size: 11px;
      font-weight: bold;
    }}
    .tag-red    {{ background:#fde8e8; color:#c0392b; }}
    .tag-orange {{ background:#fff3e0; color:#e65100; }}
    .tag-green  {{ background:#e8f5e9; color:#2e7d32; }}
    .tag-blue   {{ background:#e3f2fd; color:#1565c0; }}
    .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 14px;
      margin: 16px 0;
    }}
    .kpi {{
      background: #f0f5ff;
      border-radius: 8px;
      padding: 14px 16px;
      text-align: center;
      border: 1px solid #c5d8f5;
    }}
    .kpi .val {{
      font-size: 22px;
      font-weight: bold;
      color: #1a3a6b;
    }}
    .kpi .lbl {{
      font-size: 11px;
      color: #666;
      margin-top: 4px;
    }}
    hr {{ border: none; border-top: 1px solid #e0e8f5; margin: 32px 0; }}
    .footer {{
      margin-top: 40px;
      font-size: 12px;
      color: #aaa;
      text-align: right;
    }}
    .two-col {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 20px;
    }}
    .insight {{
      background: #fffde7;
      border: 1px solid #ffe082;
      border-radius: 6px;
      padding: 10px 14px;
      font-size: 13px;
      margin: 10px 0;
    }}
    .insight strong {{ color: #e65100; }}
  </style>
</head>
<body>
<div class="container">

  <h1>Membership EDA 보고서</h1>
  <div class="subtitle">OTT 고객 이탈 예측 프로젝트 · 탐색적 데이터 분석 결과 · 2021-03</div>

  <!-- KPI 카드 -->
  <div class="kpi-grid">
    <div class="kpi"><div class="val">18,183</div><div class="lbl">전체 레코드</div></div>
    <div class="kpi"><div class="val">17,845</div><div class="lbl">고유 user_no</div></div>
    <div class="kpi"><div class="val" style="color:#e53935;">34.4%</div><div class="lbl">이탈률 (미재결제)</div></div>
    <div class="kpi"><div class="val">16</div><div class="lbl">컬럼 수 (파생 포함)</div></div>
  </div>

  <!-- ══════════════════════════════════════════ -->
  <h2>1. 데이터 품질 — 결측치</h2>

  <div class="info">
    promotion_yn / repurchase / is_churn_prevented 의 결측(NaN)은 진짜 결측이 아닌 <strong>"미해당(N)"</strong> 의미.
    세 컬럼 모두 값이 알파벳 대문자 O 하나뿐.
  </div>

  {img('missing', '컬럼별 결측치 비율')}

  <table>
    <thead><tr><th>컬럼</th><th>결측 수</th><th>결측률</th><th>해석</th><th>전처리 방향</th></tr></thead>
    <tbody>
      <tr><td>is_churn_prevented</td><td>14,926</td><td><span class="tag tag-red">82.1%</span></td><td>NaN = 미해당</td><td>NaN→0, O→1 이진 인코딩</td></tr>
      <tr><td>promotion_yn</td><td>8,980</td><td><span class="tag tag-red">49.4%</span></td><td>NaN = 미참여</td><td>NaN→0, O→1 이진 인코딩</td></tr>
      <tr><td>repurchase</td><td>6,252</td><td><span class="tag tag-orange">34.4%</span></td><td>NaN = 이탈 <strong>(타겟)</strong></td><td>NaN→0, O→1 이진 인코딩</td></tr>
      <tr><td>is_user_verified</td><td>600</td><td><span class="tag tag-blue">3.3%</span></td><td>Y/N 이진값</td><td>최빈값(Y) 대체 또는 Unknown</td></tr>
      <tr><td>gender / age</td><td>164</td><td><span class="tag tag-green">0.9%</span></td><td>미인증 고객 연동</td><td>Unknown 처리 또는 미인증 플래그</td></tr>
      <tr><td>concurrent_streams</td><td>70</td><td><span class="tag tag-green">0.4%</span></td><td>소량</td><td>중앙값(1.0) 대체</td></tr>
    </tbody>
  </table>

  <hr>

  <!-- ══════════════════════════════════════════ -->
  <h2>2. 타겟 변수 — repurchase (이탈 여부)</h2>

  {img('target', '왼쪽: 타겟 분포 | 오른쪽: 세그먼트별 재결제율')}

  <div class="insight">
    <strong>핵심:</strong> 전체 재결제율 65.6% vs 해지방어 고객 재결제율은 훨씬 낮음 →
    해지방어를 받은 고객은 오히려 이탈 위험이 높은 집단임을 시사.
  </div>

  <hr>

  <!-- ══════════════════════════════════════════ -->
  <h2>3. 수치형 변수 분포</h2>

  <h3>3-1. amount (결제 금액)</h3>
  <div class="warn">
    원화(₩)와 달러($) 혼재 — 9.99, 10.99, 13.49 등 소수점 금액은 달러 단위.
    달러 케이스 약 <strong>3,062건 (16.8%)</strong>.  IQR 분석 전 통화 통일 필수.
  </div>
  {img('amount', 'amount 분포 (좌: 금액별 건수, 중: 히스토그램, 우: 박스플롯)')}
  <ul>
    <li>중앙값: <strong>100원</strong> (프로모션 참여 고객 다수)</li>
    <li>주요 금액 tier: 100원 / 7,900원 / 10,900원 / 소수점(달러)</li>
    <li>min: 7.69 / max: 16,400</li>
  </ul>

  <h3>3-2. age (연령대)</h3>
  <div class="warn">max = <strong>950</strong> (미인증 입력 오류) — 100세 초과 이상값 제거 후 표시.</div>
  {img('age', '100세 초과 이상값 제거, 전체(주황) vs 인증 고객(파랑) 중첩 히스토그램')}
  <ul>
    <li>인증 고객 분포: 20~45세 집중, 중앙값 35세</li>
    <li>미인증 고객 age 신뢰 불가 → 모델링 시 인증 고객 기준 분석 권장</li>
  </ul>

  <h3>3-3. concurrent_streams / reg_hour</h3>
  {img('streams_hour', '좌: 동시 시청 수 분포 | 우: 가입 시간대 (빨강=심야)')}
  <div class="warn">
    <strong>concurrent_streams=3 이상값:</strong> 실제 분포 — 1(11,354) / 2(3,804) / <strong style="color:#c0392b;">3(7건)</strong> / 4(2,948).
    상품 tier는 1/2/4만 존재. 3은 7건뿐 → <strong>입력 오류</strong> 의심, 제거 또는 인접 tier(2 or 4)로 대체 필요.
  </div>
  <ul>
    <li>concurrent_streams: 상품 tier 1/2/4 정상. 값=3은 7건만 존재 → 전처리 필요</li>
    <li>reg_hour: <strong>0시가 1,500건으로 최다</strong> — 자정 직후 가입 spike. 22시(1,483)도 높음</li>
  </ul>

  <h3>3-4. duration_days (멤버십 지속 기간)</h3>
  {img('duration', '좌: 히스토그램 | 우: 값별 건수')}
  <ul>
    <li>대부분 <strong>31일</strong>에 집중 → IQR=0, IQR 방식 부적합</li>
    <li>0일(당일 해지): 별도 플래그 처리 필요</li>
    <li>max=32 (윤달 등 월 길이 차이)</li>
  </ul>

  <hr>

  <!-- ══════════════════════════════════════════ -->
  <h2>4. 범주형 변수 분포</h2>

  {img('categorical', '상품코드 / 결제기기 / 결제수단 / 성별')}

  <hr>

  <!-- ══════════════════════════════════════════ -->
  <h2>5. 시계열 패턴</h2>

  {img('timeseries', '좌: 일별 가입 추이 | 우: 요일별 가입 건수 (빨강=주말)')}

  <ul>
    <li>데이터 기간: 2021-03-01 ~ 2021-03-15 (가입일 기준)</li>
    <li>주말 가입이 소폭 높은 경향</li>
  </ul>

  <hr>

  <!-- ══════════════════════════════════════════ -->
  <h2>6. 세그먼트 분석 — 프로모션</h2>

  {img('promo_seg', '프로모션 참여 여부 × 결제기기 / 상품별 비교')}

  <ul>
    <li>프로모션 참여(O): 9,203건 (50.6%)</li>
    <li>프로모션 참여 시 amount = 100원 → 재결제율에 직접 영향</li>
  </ul>

  <hr>

  <!-- ══════════════════════════════════════════ -->
  <h2>7. 교차 분석 — 해지방어 × 프로모션 / 상품별 재결제율</h2>

  {img('churn_cross', '좌: 해지방어×프로모션 교차표 | 우: 해지방어 여부별 재결제율')}

  <div class="insight">
    <strong>발견:</strong> 해지방어(is_churn_prevented=O) 고객의 재결제율이 비해당 고객보다 낮음.
    해지 신청 경험 자체가 이탈 위험 신호.
  </div>

  {img('prod_repurchase', '상품별 재결제율 (상위 10개)')}

  <h3>product_cd 코드 체계</h3>
  <div class="info">
    PK = Package 약자. <strong>플랜(동시 시청 수) × 결제 수단(원화 구/신/달러)</strong> 조합으로 코드 부여.
    중간 금액(3,950 / 5,450 / 6,950원)은 월 중간 가입 일할 계산 추정.
  </div>
  <table>
    <thead>
      <tr><th>플랜</th><th>동시 시청</th><th>정가(원화)</th><th>원화 구 플랜 (13x)</th><th>원화 신 플랜 (151)</th><th>달러 iOS (140)</th></tr>
    </thead>
    <tbody>
      <tr><td><strong>베이직</strong></td><td>1스트림</td><td>7,900원</td>
          <td>pk_1487 (6,693건)</td><td>pk_2025 (2,237건)</td><td>pk_1508 · $9.99 (2,130건)</td></tr>
      <tr><td><strong>스탠다드</strong></td><td>2스트림</td><td>10,900원</td>
          <td>pk_1488 (2,546건)</td><td>pk_2026 (632건)</td><td>pk_1506 · $13.49 (614건)</td></tr>
      <tr><td><strong>프리미엄</strong></td><td>4스트림</td><td>13,900원</td>
          <td>pk_1489 (2,191건)</td><td>pk_2027 (547건)</td><td>pk_1507 · $16.49 (208건)</td></tr>
    </tbody>
  </table>
  <ul>
    <li>위 9개 코드가 전체 53개 중 <strong>96%</strong> 차지. 나머지 44개는 구형/특수 플랜</li>
    <li>달러 상품(pk_1508·1506·1507)이 amount 소수점의 원인 → product_cd로 통화 식별 가능</li>
    <li>billing_method: 13x = 국내카드, 151 = 간편결제, 140 = iOS 앱스토어, 18x = 모바일결제</li>
  </ul>


  <hr>

  <!-- ══════════════════════════════════════════ -->
  <h2>8. 세그먼트 상세 비교 — 인증 여부</h2>

  <div class="info">
    각 변수의 분포를 <strong>전체 / 인증(Y) / 미인증(N)</strong> 3개 패널로 분리. 점선 = 평균값.
  </div>
  {img('seg_verified', '인증 여부 세그먼트 × 수치형 변수 분포 (전체 / 인증Y / 미인증N)')}
  <ul>
    <li>미인증 고객: gender=N 비율 67.3%, ios 기기 53.1% → 소셜 로그인 추정</li>
    <li>미인증 고객 age 신뢰 불가 (이상값 포함) → 모델링 시 is_user_verified 플래그 피처로 활용</li>
  </ul>

  <hr>

  <!-- ══════════════════════════════════════════ -->
  <h2>9. 세그먼트 상세 비교 — 프로모션 여부</h2>

  <div class="info">
    <strong>전체 / 프로모션 참여(O) / 미참여(NaN)</strong> 3개 패널.
  </div>
  {img('seg_promo', '프로모션 여부 세그먼트 × 수치형 변수 분포')}
  <ul>
    <li>프로모션 참여(O) 그룹: amount=100원 고정(std=0), 연령 평균 32세로 전체(34세)보다 낮음</li>
    <li>프로모션 참여 시 concurrent_streams 평균 1.85 — 미참여(1.56)보다 다중 스트림 많음</li>
  </ul>

  <hr>

  <!-- ══════════════════════════════════════════ -->
  <h2>10. 세그먼트 상세 비교 — 재결제 여부 (타겟)</h2>

  <div class="info">
    <strong>전체 / 재결제(O) / 미재결제=이탈(NaN)</strong> 3개 패널. 이탈 예측 핵심 비교.
  </div>
  {img('seg_repurchase', '재결제 여부 세그먼트 × 수치형 변수 분포')}
  <div class="insight">
    <strong>발견:</strong> 이탈 고객과 재결제 고객의 amount/age/duration_days 분포 차이를 확인.
    두 그룹의 분포가 다를수록 해당 변수가 예측에 유용한 피처.
  </div>

  <hr>

  <!-- ══════════════════════════════════════════ -->
  <h2>11. 시계열 패턴 — 요일×시간대 히트맵</h2>

  {img('hour_weekday_heatmap', '가입 시간대 × 요일 히트맵')}
  <ul>
    <li>월요일 0시 spike — 주말 이후 자정 가입 패턴</li>
    <li>토/일 22~23시 집중 — 주말 심야 가입 다수</li>
  </ul>

  <hr>

  <!-- ══════════════════════════════════════════ -->
  <h2>12. 성별 × 연령대 분포 (인증 고객)</h2>

  {img('gender_age_heatmap', '성별 × 연령대 교차표 (인증 고객만)')}
  <ul>
    <li>F: 25~30대 집중 (1,510 / 1,898건)</li>
    <li>M: 25~35대 고른 분포 (812 / 992 / 991건)</li>
    <li>두 성별 모두 20~35세가 핵심 고객층</li>
  </ul>

  <hr>

  <!-- ══════════════════════════════════════════ -->
  <h2>13. 상관관계 분석</h2>

  <div class="info">billing_method는 범주형이므로 제외. 수치형 5개 컬럼만 분석.</div>
  {img('corr', '좌: 전체 고객 | 우: 인증 고객')}
  <ul>
    <li>전반적으로 수치형 변수 간 상관관계 낮음</li>
    <li>인증/미인증 고객 간 상관 구조 차이 확인 필요</li>
  </ul>

  <hr>

  <!-- ══════════════════════════════════════════ -->
  <h2>14. 전처리 필요 사항 요약</h2>

  <table>
    <thead><tr><th>항목</th><th>내용</th><th>우선순위</th></tr></thead>
    <tbody>
      <tr><td>통화 통일</td><td>amount 달러($) 3,062건 → 환율 적용 또는 제거</td><td><span class="tag tag-red">높음</span></td></tr>
      <tr><td>타겟 인코딩</td><td>repurchase NaN→0, O→1</td><td><span class="tag tag-red">높음</span></td></tr>
      <tr><td>이진 컬럼 인코딩</td><td>promotion_yn, is_churn_prevented, is_user_verified</td><td><span class="tag tag-red">높음</span></td></tr>
      <tr><td>billing_method</td><td>int → 범주형 인코딩 (OHE or Label)</td><td><span class="tag tag-orange">중간</span></td></tr>
      <tr><td>age 이상값</td><td>max=950 등 미인증 이상값 처리 / 인증 플래그</td><td><span class="tag tag-orange">중간</span></td></tr>
      <tr><td>user_no 중복</td><td>338건 → duration_days 최대 레코드 유지</td><td><span class="tag tag-orange">중간</span></td></tr>
      <tr><td>duration_days=0</td><td>당일 해지 플래그 생성</td><td><span class="tag tag-blue">낮음</span></td></tr>
      <tr><td>concurrent_streams</td><td>결측 70건 → 중앙값(1) 대체</td><td><span class="tag tag-green">완료예정</span></td></tr>
    </tbody>
  </table>

  <div class="footer">OTT 고객 이탈 예측 프로젝트 · EDA 보고서</div>
</div>
</body>
</html>'''

OUT = 'c:/Users/USER/OneDrive/바탕 화면/AX/EDA/eda_report.html'
with open(OUT, 'w', encoding='utf-8') as f:
    f.write(html)
print('Done:', OUT)
