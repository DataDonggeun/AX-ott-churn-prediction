import os
import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import seaborn as sns
import anthropic
from pathlib import Path

# ─── 페이지 설정 ──────────────────────────────────────────────
st.set_page_config(
    page_title="OTT 이탈 분석 대시보드",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

BASE = Path(__file__).parent.parent  # 대쉬보드/ 한 단계 위 (kwon.donggeun/)

# ─── 폰트 설정 ────────────────────────────────────────────────
@st.cache_resource
def setup_font():
    fonts = sorted({f.name for f in fm.fontManager.ttflist})
    candidates = ["Malgun Gothic", "NanumGothic", "AppleGothic"]
    found = next((c for c in candidates if c in fonts), "DejaVu Sans")
    plt.rcParams["font.family"] = found
    plt.rcParams["axes.unicode_minus"] = False
    sns.set_theme(font=found, rc={"axes.unicode_minus": False})
    return found

FONT = setup_font()

# ─── 데이터 로드 ──────────────────────────────────────────────
@st.cache_data
def load_membership():
    p = BASE / "data" / "Membership_processing.csv"
    return pd.read_csv(p) if p.exists() else None

@st.cache_data
def load_v2():
    p = BASE / "data" / "Membership_v2.csv"
    return pd.read_csv(p) if p.exists() else None

# ─── RAG 컨텍스트 로드 (프롬프트 캐싱용) ────────────────────────
@st.cache_resource
def load_rag_context():
    parts = [
        "당신은 OTT 서비스 고객 이탈 예측 프로젝트의 AI 데이터 분석 어시스턴트입니다. "
        "아래 프로젝트 문서와 데이터 통계를 바탕으로 질문에 답변해주세요. "
        "한국어로 답변하고, 데이터 근거를 들어 설명해주세요.\n"
    ]

    # CLAUDE.md 로드
    claude_md = BASE / "CLAUDE.md"
    if claude_md.exists():
        parts.append("# 프로젝트 문서 (CLAUDE.md)\n\n" + claude_md.read_text(encoding="utf-8"))

    # 데이터 통계 추가
    df = load_membership()
    if df is not None:
        num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        parts.append(f"""
# 실시간 데이터 현황

## Membership_processing.csv 기본 통계
- 총 유저 수: {len(df):,}명
- 컬럼 수: {df.shape[1]}개
- 재결제율 (타겟): {df['repurchase'].mean():.1%} — 재결제 {df['repurchase'].sum():,}건 / 이탈 {(df['repurchase']==0).sum():,}건
- 해지방어 비율: {df['is_churn_prevented'].mean():.1%}
- 프로모션 참여율: {df['promotion_yn'].mean():.1%}
- 평균 나이: {df['age'].mean():.1f}세
- 평균 가입기간: {df['duration_days'].mean():.1f}일
- 시청이력 보유율: {df['has_watch_history'].mean():.1%}

## 수치형 피처 기술통계
{df[num_cols].describe().round(3).to_string()}

## 재결제율 세그먼트 (성별)
{df.groupby('gender')['repurchase'].agg(['mean','count']).rename(columns={'mean':'재결제율','count':'유저수'}).to_string()}

## 재결제율 세그먼트 (해지방어)
{df.groupby('is_churn_prevented')['repurchase'].agg(['mean','count']).rename(columns={'mean':'재결제율','count':'유저수'}).to_string()}
""")

    return "\n\n---\n\n".join(parts)

# ─── 사이드바 ──────────────────────────────────────────────────
api_key_input = ""

with st.sidebar:
    st.title("📊 OTT 이탈 분석")
    st.caption("고객 이탈 예측 기업연계 프로젝트")
    st.divider()

    page = st.radio(
        "페이지 선택",
        ["🏠 홈", "📈 EDA", "🔗 다중공선성", "🤖 모델 성능", "💬 AI 챗봇"],
        label_visibility="collapsed",
    )

    st.divider()

    if "챗봇" in page:
        api_key_input = st.text_input(
            "🔑 Anthropic API Key",
            type="password",
            placeholder="sk-ant-...",
            help="환경변수 ANTHROPIC_API_KEY 설정 시 자동 사용. 입력값은 저장되지 않습니다.",
        )

    st.divider()
    df_info = load_membership()
    if df_info is not None:
        st.caption(f"데이터: {len(df_info):,}행 × {df_info.shape[1]}열")
    st.caption("Membership_processing.csv\nMembership_v2.csv (53 피처)")

# ═══════════════════════════════════════════════════════════════
# 페이지: 홈
# ═══════════════════════════════════════════════════════════════
if page == "🏠 홈":
    st.title("OTT 고객 이탈 예측 분석 대시보드")
    st.markdown("**EDA → 전처리 → 다중공선성 → 피처엔지니어링 → 모델링** 프로세스 전체를 대시보드로 제공합니다.")

    df = load_membership()
    if df is not None:
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("총 유저 수", f"{len(df):,}")
        c2.metric("재결제율", f"{df['repurchase'].mean():.1%}")
        c3.metric("이탈율", f"{1-df['repurchase'].mean():.1%}")
        c4.metric("해지방어율", f"{df['is_churn_prevented'].mean():.1%}")
        c5.metric("시청이력 보유율", f"{df['has_watch_history'].mean():.1%}")

    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📋 프로젝트 단계")
        st.markdown("""
| 단계 | 내용 | 상태 |
|------|------|------|
| EDA | 결측치·분포·이상값 탐색 | ✅ 완료 |
| 전처리 | 인코딩·스케일링·피처 정리 | ✅ 완료 |
| 다중공선성 | VIF / 상관계수 분석 | ✅ 완료 |
| 피처 엔지니어링 | v2 (53개 피처) 생성 | ✅ 완료 |
| 모델링 | LGB / CatBoost / HistGB + Optuna | 🔄 진행 중 |
        """)

    with col2:
        st.subheader("📁 주요 파일")
        st.markdown("""
```
kwon.donggeun/
├── 대쉬보드/app.py              ← 이 대시보드
├── data/
│   ├── Membership_processing.csv  (29컬럼)
│   └── Membership_v2.csv          (53 피처)
├── 모델링/
│   ├── model_churn.ipynb          (메인 모델링)
│   └── model_final_merged.ipynb   (CatBoost Optuna)
├── 모델링/다중공선성_v3.ipynb
└── EDA/
    └── eda_report.html
```
        """)

    st.divider()
    st.subheader("💡 사용 방법")
    cols = st.columns(4)
    cols[0].info("**EDA**\n\n기본 통계, 분포, 히트맵을 확인합니다.")
    cols[1].info("**다중공선성**\n\n상관계수 행렬로 중복 피처를 파악합니다.")
    cols[2].info("**모델 성능**\n\n각 알고리즘의 AUC/F1 결과를 비교합니다.")
    cols[3].info("**AI 챗봇**\n\nAPI 키 입력 후 데이터에 대해 질문하세요.")


# ═══════════════════════════════════════════════════════════════
# 페이지: EDA
# ═══════════════════════════════════════════════════════════════
elif page == "📈 EDA":
    st.title("📈 탐색적 데이터 분석 (EDA)")

    df = load_membership()
    if df is None:
        st.error("❌ data/Membership_processing.csv 파일을 찾을 수 없습니다.")
        st.stop()

    tab1, tab2, tab3, tab4 = st.tabs(["📊 기본 통계", "🎯 타겟 분포", "📉 수치형 분포", "🗺️ 세그먼트 히트맵"])

    with tab1:
        col1, col2 = st.columns([3, 2])
        with col1:
            st.subheader("기술통계")
            st.dataframe(df.describe().T.style.format("{:.2f}"), height=420)
        with col2:
            st.subheader("컬럼 정보")
            info = pd.DataFrame({
                "dtype": df.dtypes,
                "결측치": df.isnull().sum(),
                "고유값": df.nunique(),
            })
            st.dataframe(info, height=420)

    with tab2:
        col1, col2, col3 = st.columns(3)
        with col1:
            fig, ax = plt.subplots(figsize=(5, 5))
            sizes = [df['repurchase'].sum(), (df['repurchase']==0).sum()]
            ax.pie(sizes, labels=['재결제 (1)', '이탈 (0)'],
                   colors=['#48BB78','#FC8181'], autopct='%1.1f%%', startangle=90)
            ax.set_title('재결제 vs 이탈')
            st.pyplot(fig); plt.close()

        with col2:
            fig, ax = plt.subplots(figsize=(5, 5))
            df['is_churn_prevented'].value_counts().sort_index().plot(
                kind='bar', color=['#A0AEC0','#F6AD55'], ax=ax, width=0.5)
            ax.set_xticklabels(['미해당(0)','해당(1)'], rotation=0)
            ax.set_title('해지방어 여부'); ax.set_ylabel('유저 수')
            st.pyplot(fig); plt.close()

        with col3:
            fig, ax = plt.subplots(figsize=(5, 5))
            df['promotion_yn'].value_counts().sort_index().plot(
                kind='bar', color=['#A0AEC0','#68D391'], ax=ax, width=0.5)
            ax.set_xticklabels(['미참여(0)','참여(1)'], rotation=0)
            ax.set_title('프로모션 참여 여부'); ax.set_ylabel('유저 수')
            st.pyplot(fig); plt.close()

        # 재결제율 by 주요 변수
        st.subheader("변수별 재결제율")
        col1, col2 = st.columns(2)
        with col1:
            vc = df.groupby('concurrent_streams')['repurchase'].mean()
            fig, ax = plt.subplots(figsize=(6, 3))
            vc.plot(kind='bar', color='#4299E1', ax=ax, width=0.5)
            ax.set_title('동시시청수별 재결제율'); ax.set_ylabel('재결제율')
            ax.set_xticklabels(vc.index, rotation=0)
            ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x:.0%}'))
            st.pyplot(fig); plt.close()
        with col2:
            vc = df.groupby('billing_method')['repurchase'].agg(['mean','count'])
            vc = vc[vc['count'] > 100].sort_values('mean', ascending=False).head(10)
            fig, ax = plt.subplots(figsize=(6, 3))
            vc['mean'].plot(kind='barh', color='#48BB78', ax=ax)
            ax.set_title('결제수단별 재결제율'); ax.set_xlabel('재결제율')
            ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x:.0%}'))
            st.pyplot(fig); plt.close()

    with tab3:
        col1, col2 = st.columns(2)
        with col1:
            fig, ax = plt.subplots(figsize=(6, 4))
            ax.hist(df['age'].clip(upper=80), bins=35, color='#4299E1', edgecolor='white', alpha=0.8)
            ax.axvline(df['age'].mean(), color='red', linestyle='--', label=f'평균 {df["age"].mean():.1f}세')
            ax.set_title('나이 분포'); ax.set_xlabel('나이'); ax.set_ylabel('유저 수'); ax.legend()
            st.pyplot(fig); plt.close()

        with col2:
            fig, ax = plt.subplots(figsize=(6, 4))
            ax.hist(df['duration_days'], bins=33, color='#48BB78', edgecolor='white', alpha=0.8)
            ax.axvline(df['duration_days'].mean(), color='red', linestyle='--',
                       label=f'평균 {df["duration_days"].mean():.1f}일')
            ax.set_title('가입기간 분포'); ax.set_xlabel('일수'); ax.set_ylabel('유저 수'); ax.legend()
            st.pyplot(fig); plt.close()

        if 'amount' in df.columns:
            fig, ax = plt.subplots(figsize=(10, 3))
            vc = df['amount'].value_counts().sort_index()
            bar_colors = ['#FC8181' if v == 100 else '#4299E1' for v in vc.index]
            ax.bar(vc.index.astype(str), vc.values, color=bar_colors)
            ax.set_title('결제 금액 분포 (빨간색 = 100원 프로모션)')
            ax.set_xlabel('금액(원)'); ax.set_ylabel('유저 수')
            st.pyplot(fig); plt.close()

    with tab4:
        st.subheader("성별 × 연령대 재결제율")
        if 'age_group' in df.columns:
            pivot = df.pivot_table(values='repurchase', index='age_group',
                                   columns='gender', aggfunc='mean')
            pivot.columns = [f'성별 {c}' for c in pivot.columns]
            fig, ax = plt.subplots(figsize=(8, 7))
            sns.heatmap(pivot, annot=True, fmt='.2%', cmap='RdYlGn',
                        center=0.65, linewidths=0.5, ax=ax, vmin=0.4, vmax=0.9)
            ax.set_title('연령대 × 성별 재결제율')
            st.pyplot(fig); plt.close()
        else:
            st.info("age_group 컬럼이 없습니다. Membership_processing.csv를 확인하세요.")

        st.subheader("시청이력 여부 × 재결제율")
        col1, col2 = st.columns(2)
        with col1:
            vc = df.groupby('has_watch_history')['repurchase'].mean()
            fig, ax = plt.subplots(figsize=(5, 4))
            vc.plot(kind='bar', color=['#FC8181','#48BB78'], ax=ax, width=0.5)
            ax.set_xticklabels(['시청이력 없음','시청이력 있음'], rotation=0)
            ax.set_title('시청이력 여부별 재결제율')
            ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x:.0%}'))
            st.pyplot(fig); plt.close()
        with col2:
            vc2 = df.groupby('is_user_verified')['repurchase'].mean()
            fig, ax = plt.subplots(figsize=(5, 4))
            vc2.plot(kind='bar', color=['#FC8181','#68D391'], ax=ax, width=0.5)
            ax.set_xticklabels(['미인증','인증'], rotation=0)
            ax.set_title('본인인증 여부별 재결제율')
            ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x:.0%}'))
            st.pyplot(fig); plt.close()


# ═══════════════════════════════════════════════════════════════
# 페이지: 다중공선성
# ═══════════════════════════════════════════════════════════════
elif page == "🔗 다중공선성":
    st.title("🔗 다중공선성 분석")

    source = st.radio("데이터 소스", ["Membership_processing (29 피처)", "Membership_v2 (53 피처)"],
                      horizontal=True)

    if "v2" in source:
        df = load_v2()
        label = "v2 (53 피처)"
    else:
        df = load_membership()
        label = "Membership_processing (29 피처)"

    if df is None:
        st.error("❌ 데이터 파일을 찾을 수 없습니다.")
        st.stop()

    # 수치형 컬럼만 (타겟 제외)
    excl = ['repurchase', 'user_no', 'product_cd', 'reg_date', 'end_date',
            'uid', 'payment_device', 'plan_tier', 'currency_type']
    num_cols = df.select_dtypes(include=[np.number]).columns.difference(excl).tolist()

    st.caption(f"사용 피처 수: {len(num_cols)}개")

    threshold = st.slider("|상관계수| 임계값 (고상관 쌍 필터)", 0.0, 1.0, 0.7, 0.05)

    corr = df[num_cols].corr()

    # 히트맵
    fig_h = max(12, len(num_cols) * 0.5)
    fig, ax = plt.subplots(figsize=(fig_h + 2, fig_h))
    sns.heatmap(
        corr, annot=True, fmt=".2f", cmap="coolwarm",
        center=0, square=True, linewidths=0.4,
        annot_kws={"size": max(5, 9 - len(num_cols) // 10)}, ax=ax,
    )
    ax.set_title(f"상관계수 행렬 — {label}", fontsize=12, pad=12)
    plt.xticks(rotation=45, ha="right", fontsize=7)
    plt.yticks(rotation=0, fontsize=7)
    plt.tight_layout()
    st.pyplot(fig); plt.close()

    # 고상관 쌍 테이블
    high = (
        corr.where(np.triu(np.ones(corr.shape), k=1).astype(bool))
        .stack().reset_index()
    )
    high.columns = ["col1", "col2", "corr"]
    high = high[high["corr"].abs() >= threshold].sort_values("corr", ascending=False)

    st.subheader(f"|상관계수| ≥ {threshold:.2f} 쌍 ({len(high)}개)")
    if high.empty:
        st.success("해당 없음")
    else:
        st.dataframe(
            high.style.background_gradient(subset=["corr"], cmap="RdYlGn", vmin=-1, vmax=1)
                      .format({"corr": "{:.4f}"}),
            use_container_width=True,
            height=min(600, 38 + len(high) * 36),
        )


# ═══════════════════════════════════════════════════════════════
# 페이지: 모델 성능
# ═══════════════════════════════════════════════════════════════
elif page == "🤖 모델 성능":
    st.title("🤖 모델 성능 비교")
    st.caption("model_churn.ipynb 실행 결과를 아래 results 딕셔너리에 붙여넣으면 자동 업데이트됩니다.")

    # ✏️ 여기에 실제 모델 결과를 붙여넣으세요
    results = {
        "모델":    ["Logistic Regression", "Random Forest", "Gradient Boosting",
                    "LightGBM", "XGBoost", "CatBoost", "HistGradientBoosting"],
        "ROC-AUC": [0.652, 0.661, 0.671, 0.674, 0.672, 0.675, 0.673],
        "F1":      [0.743, 0.756, 0.762, 0.765, 0.763, 0.766, 0.764],
        "Accuracy":[0.681, 0.692, 0.698, 0.701, 0.699, 0.702, 0.700],
        "Precision":[0.712, 0.724, 0.731, 0.735, 0.733, 0.736, 0.734],
        "Recall":  [0.776, 0.790, 0.795, 0.797, 0.795, 0.798, 0.796],
    }
    rdf = pd.DataFrame(results).sort_values("ROC-AUC", ascending=False).reset_index(drop=True)

    # 지표 요약
    best = rdf.iloc[0]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("최고 AUC 모델", best["모델"].split()[-1])
    c2.metric("최고 ROC-AUC", f"{best['ROC-AUC']:.4f}")
    c3.metric("최고 F1", f"{best['F1']:.4f}")
    c4.metric("모델 수", len(rdf))

    st.subheader("성능 테이블")
    st.dataframe(
        rdf.style.highlight_max(subset=["ROC-AUC","F1","Accuracy","Precision","Recall"],
                                color="#DCFCE7")
               .format({c: "{:.4f}" for c in ["ROC-AUC","F1","Accuracy","Precision","Recall"]}),
        use_container_width=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        fig, ax = plt.subplots(figsize=(8, 5))
        colors = ["#48BB78" if r == rdf["ROC-AUC"].max() else "#4299E1" for r in rdf["ROC-AUC"]]
        ax.barh(rdf["모델"], rdf["ROC-AUC"], color=colors)
        ax.axvline(0.7, color="red", linestyle="--", alpha=0.6, label="0.7 기준선")
        ax.set_title("ROC-AUC 비교"); ax.set_xlabel("ROC-AUC"); ax.legend()
        ax.set_xlim(0.6, 0.75)
        plt.tight_layout(); st.pyplot(fig); plt.close()

    with col2:
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.barh(rdf["모델"], rdf["F1"], color="#F6AD55")
        ax.set_title("F1 Score 비교"); ax.set_xlabel("F1 Score")
        ax.set_xlim(0.7, 0.82)
        plt.tight_layout(); st.pyplot(fig); plt.close()

    st.info("💡 실제 결과로 업데이트하려면 `results` 딕셔너리의 숫자값을 교체하세요.")


# ═══════════════════════════════════════════════════════════════
# 페이지: AI 챗봇
# ═══════════════════════════════════════════════════════════════
elif page == "💬 AI 챗봇":
    st.title("💬 OTT 분석 AI 챗봇")
    st.caption(
        "CLAUDE.md + 실시간 데이터 통계를 컨텍스트로 사용하는 RAG 챗봇입니다. "
        "프롬프트 캐싱으로 반복 요청 비용을 절감합니다."
    )

    # API 키 결정
    api_key = api_key_input or os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        st.warning("⚠️ 사이드바에서 Anthropic API Key를 입력하거나, 환경변수 ANTHROPIC_API_KEY를 설정하세요.")
        st.stop()

    # 대화 히스토리 초기화
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    # RAG 컨텍스트 (캐시됨)
    system_ctx = load_rag_context()

    with st.expander("📚 RAG 컨텍스트 정보"):
        st.caption(f"시스템 컨텍스트 크기: {len(system_ctx):,}자")
        st.caption("포함 내용: CLAUDE.md (프로젝트 문서) + 실시간 데이터 통계")
        st.caption("모델: claude-haiku-4-5 | 프롬프트 캐싱: 활성화 (ephemeral TTL 5분)")

    # 추천 질문
    if not st.session_state.chat_history:
        st.subheader("💡 추천 질문")
        q_cols = st.columns(3)
        questions = [
            "이탈 예측에 가장 중요한 피처가 뭐야?",
            "재결제율이 높은 고객 세그먼트는?",
            "다중공선성 문제가 있는 피처 쌍은?",
            "v2 피처 엔지니어링에서 추가한 변수들을 설명해줘",
            "AUC가 0.678에서 더 안 올라가는 이유가 뭐야?",
            "해지방어와 재결제 관계를 데이터로 설명해줘",
        ]
        for i, q in enumerate(questions):
            if q_cols[i % 3].button(q, key=f"q{i}", use_container_width=True):
                st.session_state.chat_history.append({"role": "user", "content": q})
                st.rerun()

    # 대화 표시
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # 입력 처리
    if prompt := st.chat_input("데이터나 분석에 대해 질문하세요..."):
        with st.chat_message("user"):
            st.markdown(prompt)
        st.session_state.chat_history.append({"role": "user", "content": prompt})

        with st.chat_message("assistant"):
            try:
                client = anthropic.Anthropic(api_key=api_key)

                # 스트리밍 제너레이터 — 프롬프트 캐싱 적용
                def generate():
                    with client.messages.stream(
                        model="claude-haiku-4-5",
                        max_tokens=2048,
                        system=[{
                            "type": "text",
                            "text": system_ctx,
                            "cache_control": {"type": "ephemeral"},
                        }],
                        messages=[
                            {"role": m["role"], "content": m["content"]}
                            for m in st.session_state.chat_history
                        ],
                    ) as stream:
                        for text in stream.text_stream:
                            yield text

                # 스트리밍 출력 + 전체 텍스트 캡처
                response_text = st.write_stream(generate())

                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": response_text,
                })

            except anthropic.AuthenticationError:
                st.error("❌ API 키가 유효하지 않습니다. 확인 후 다시 입력해주세요.")
                st.session_state.chat_history.pop()
            except anthropic.RateLimitError:
                st.error("⏳ Rate limit 초과. 잠시 후 다시 시도해주세요.")
                st.session_state.chat_history.pop()
            except Exception as e:
                st.error(f"오류 발생: {e}")
                st.session_state.chat_history.pop()

    # 하단 버튼
    if st.session_state.chat_history:
        col1, col2 = st.columns([1, 5])
        if col1.button("🗑️ 대화 초기화", type="secondary"):
            st.session_state.chat_history = []
            st.rerun()
        col2.caption(f"대화 {len(st.session_state.chat_history)//2}턴 | "
                     f"컨텍스트 약 {len(system_ctx)//4:,} 토큰 (캐시됨)")
