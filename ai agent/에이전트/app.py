"""비서 에이전트 메인 앱 — @st.fragment 탭 독립 실행"""
import calendar
import hashlib
import html as _html
import re
from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="OTT 비서 에이전트", layout="wide")

# ─── 세션 상태 ─────────────────────────────────────────────────────────────────
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = True  # 다크모드 고정

# ─── 다크/라이트 테마 변수 ─────────────────────────────────────────────────────
_dm = st.session_state.dark_mode
THEME = {
    "app_bg":      "#000000"   if _dm else "#f5f5f5",
    "content_bg":  "#111111"   if _dm else "#ffffff",
    "card_bg":     "#161616"   if _dm else "#f0f0f0",
    "text":        "#e2e2f0"   if _dm else "#111111",
    "muted":       "#888888"   if _dm else "#555555",
    "border":      "#222222"   if _dm else "#dddddd",
    "stat_color":  "white"     if _dm else "#111111",
}

def _inject_css():
    dm = st.session_state.dark_mode
    app_bg     = "#000000" if dm else "#f0f0f0"
    content_bg = "#111111" if dm else "#ffffff"
    card_bg    = "#161616" if dm else "#f4f4f4"
    text_col   = "#e2e2f0" if dm else "#111111"
    muted_col  = "#aaaaaa" if dm else "#444444"
    border_col = "#2e2e40" if dm else "#cccccc"
    stat_col   = "#e2e2f0" if dm else "#111111"

    st.markdown(f"""
<style>
/* GPT 스타일 레이아웃 */
.stApp {{ background:{app_bg} !important; }}
.block-container {{
    max-width: 1100px !important;
    margin: 0 auto !important;
    background: {content_bg} !important;
    padding: 2rem 3rem !important;
}}

/* 전체 텍스트 색상 */
body, p, li {{ color:{text_col} !important; }}
h1, h2, h3, h4 {{ color:{stat_col} !important; }}
.stMarkdown p, .stMarkdown span, .stMarkdown div {{ color:{text_col} !important; }}

/* Streamlit 기본 컴포넌트 텍스트 */
.stSelectbox label, .stSlider label, .stRadio label {{ color:{muted_col} !important; }}
.stCaption, [data-testid="stCaptionContainer"] p {{ color:{muted_col} !important; }}
[data-testid="stMetricLabel"] {{ color:{muted_col} !important; }}
[data-testid="stMetricValue"] {{ color:{stat_col} !important; }}
[data-testid="stMetricDelta"] {{ color:{muted_col} !important; }}

/* 탭 텍스트 */
[data-testid="stTab"] p, button[data-baseweb="tab"] {{ color:{text_col} !important; }}

/* 토글 레이블 */
[data-testid="stToggle"] label, [data-testid="stToggle"] span,
.stToggle label, .stToggle p {{ color:{text_col} !important; }}

/* selectbox 텍스트 */
[data-testid="stSelectbox"] div, [data-testid="stSelectbox"] span,
[data-testid="stSelectbox"] p {{ color:{text_col} !important; }}

/* 서브헤더 */
[data-testid="stHeading"] {{ color:{stat_col} !important; }}

/* 일반 div/span — 너무 광범위하면 Streamlit 내부 UI 깨질 수 있으므로 클래스 한정 */
.element-container p, .element-container span {{ color:{text_col} !important; }}

/* 지표 클래스 */
.stat-label {{ font-size:13px; color:{muted_col} !important; margin-bottom:4px; }}
.stat-big   {{ font-size:2.4rem; font-weight:700; color:{stat_col} !important; line-height:1.1; }}
.stat-mid   {{ font-size:1.7rem; font-weight:700; color:{stat_col} !important; line-height:1.1; }}
.badge-red  {{ display:inline-block; background:#ef4444; color:white !important;
               padding:2px 12px; border-radius:12px; font-size:12px; margin-top:6px; }}
.badge-grn  {{ display:inline-block; background:#22c55e; color:white !important;
               padding:2px 12px; border-radius:12px; font-size:12px; margin-top:6px; }}
.sec-title  {{ font-size:15px; font-weight:600; color:{stat_col} !important; margin-bottom:12px; }}
.msg-box    {{ background:{card_bg} !important; border-radius:12px; padding:18px;
               font-size:15px; line-height:1.8; color:{text_col} !important; }}

/* 탭 */
[data-testid="stTab"] {{ color:{text_col} !important; }}

/* 데이터프레임 가운데 정렬 */
[data-testid="stDataFrame"] td,
[data-testid="stDataFrame"] th,
.col_heading, .data {{ text-align:center !important; justify-content:center !important; }}

/* 사이드바 숨기기 */
[data-testid="stSidebar"] {{ display:none; }}
</style>
""", unsafe_allow_html=True)

_inject_css()

# ─── 마크다운 제거 함수 ────────────────────────────────────────────────────────
def strip_md(text: str) -> str:
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"\*{1,3}([^*\n]+)\*{1,3}", r"\1", text)
    text = re.sub(r"^[\s]*[-*+]\s+", "• ", text, flags=re.MULTILINE)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ─── 공용 함수 ────────────────────────────────────────────────────────────────
def date_picker(label: str, default: date, key: str) -> date:
    st.caption(label)
    c1, c2, c3 = st.columns(3)
    with c1:
        y = st.selectbox("년", [2021], key=f"{key}_y")
    with c2:
        m = st.selectbox("월", list(range(1, 13)), index=default.month - 1, key=f"{key}_m")
    with c3:
        max_d = calendar.monthrange(y, m)[1]
        # month 바뀔 때 day 값이 범위 초과하면 clamp → 3월1일로 리셋되는 버그 방지
        day_key = f"{key}_d"
        if day_key in st.session_state and st.session_state[day_key] > max_d:
            st.session_state[day_key] = max_d
        d = st.selectbox("일", list(range(1, max_d + 1)), key=day_key)
    return date(y, m, d)


def show_movies(movies: list):
    if not movies:
        st.info("영화를 불러오지 못했어요.")
        return
    cols = st.columns(5)
    for i, m in enumerate(movies[:5]):
        with cols[i]:
            if m.get("poster"):
                st.image(m["poster"], use_container_width=True)
            st.markdown(f"**{m.get('title', '')}**")
            st.caption(f"★ {m.get('vote_average', 0):.1f}")
            ov = m.get("overview", "")
            st.write((ov[:90] + "...") if len(ov) > 90 else ov)


def get_churn_message(age: int, days_inactive: int, genre: str, gender: str) -> tuple:
    try:
        from dify_agent import run_churn_prevention
        msg = run_churn_prevention(age, days_inactive, genre, gender)
        if msg and len(msg) > 10 and "오류" not in msg:
            return msg, "Dify"
    except Exception:
        pass
    try:
        from agent import generate_retention_message
        return generate_retention_message(age, days_inactive, gender, genre), "Gemini"
    except Exception as e:
        return f"메시지 생성 실패: {e}", "오류"


st.title("OTT 비서 에이전트")
st.caption("LangGraph + Gemini AI | 자동 분석 리포트")

tab1, tab2, tab3, tab4 = st.tabs([
    "일별 리포트", "주간 보고서", "경영진 요약", "영화 추천 챗봇",
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — 일별 리포트  (@st.fragment → 독립 실행)
# ══════════════════════════════════════════════════════════════════════════════

def _tc():
    """현재 테마의 텍스트 색상"""
    return "#111111" if not st.session_state.get("dark_mode", True) else "#e2e2f0"

def _cc():
    """현재 테마의 카드 배경색"""
    return "#e8e8e8" if not st.session_state.get("dark_mode", True) else "#1e1e2e"

def _bc():
    """현재 테마의 테두리 색상"""
    return "#cccccc" if not st.session_state.get("dark_mode", True) else "#2e2e40"

def _mc():
    """현재 테마의 설명 텍스트 색상 (muted)"""
    return "#444444" if not st.session_state.get("dark_mode", True) else "#aaaaaa"

def _stat(label, value, unit="", color=None, small=False):
    if color is None:
        color = _tc()
    sz = "1.6rem" if small else "2.4rem"
    return (f'<div class="stat-label">{label}</div>'
            f'<div style="font-size:{sz};font-weight:700;color:{color};line-height:1.1">'
            f'{value}{unit}</div>')

def _section_header(title, desc, color="#4f9cf9"):
    tc = _tc()
    return f"""
<div style="border-left:3px solid {color};padding-left:12px;margin:20px 0 12px">
  <div style="font-size:16px;font-weight:700;color:{tc}">{title}</div>
  <div style="font-size:12px;color:#888;margin-top:4px;line-height:1.6">{desc}</div>
</div>"""

def _customer_panel(sel_key, selected, df, source_df):
    from analyzer import get_top_genre_as_of, get_retention_info
    genre   = get_top_genre_as_of(sel_key, selected)
    info    = get_retention_info(sel_key)
    age     = info.get("age",    30)
    gender  = info.get("gender", "M")
    act_row = source_df[source_df["USER_KEY"].astype(str) == sel_key]
    days_in = int(act_row["days_inactive"].iloc[0]) if (not act_row.empty and "days_inactive" in act_row.columns) else 14
    prob    = float(act_row["churn_risk"].iloc[0]) * 100 if (not act_row.empty and "churn_risk" in act_row.columns) else None

    st.markdown(f'<div class="sec-title">고객 {sel_key[:20]}... 맞춤 추천</div>', unsafe_allow_html=True)
    meta_parts = [f"나이 {age}세", f"성별 {gender}", f"{selected} 기준 선호장르: {genre}", f"미접속 {days_in}일"]
    if prob is not None:
        meta_parts.append(f"이탈확률 {prob:.1f}%")
    st.caption("  |  ".join(meta_parts))

    col_mv, col_msg = st.columns([6, 4])
    with col_mv:
        with st.spinner("영화 가져오는 중..."):
            from tmdb import add_reasons, get_movies
            page_num = (int(hashlib.md5(sel_key.encode()).hexdigest(), 16) % 3) + 1
            movies   = get_movies(genre=genre, year_gte=2018, page=page_num)[:5]
            movies   = add_reasons(movies, genre, age, gender)
        show_movies(movies)

    with col_msg:
        st.markdown('<div class="sec-title">발송할 이탈 방지 메시지</div>', unsafe_allow_html=True)
        with st.spinner("메시지 생성 중..."):
            msg, source = get_churn_message(age, days_in, genre, gender)
        st.caption(f"생성 방식: {source}")
        st.markdown(f'<div class="msg-box">{_html.escape(msg)}</div>', unsafe_allow_html=True)


@st.fragment
def tab_daily():
    # ── 날짜 선택 (왼쪽) + 설명 (오른쪽) ─────────────────────────────────
    col_date, col_date_desc = st.columns([1, 2])
    with col_date:
        selected = date_picker("날짜 선택", date(2021, 3, 1), "daily")
        clicked = st.button("조회", type="primary", key="daily_query_btn", use_container_width=True)
        if clicked:
            st.session_state["daily_queried"] = selected
    with col_date_desc:
        st.markdown(f"""
<div style="background:{_cc()};border:1px solid {_bc()};border-radius:10px;padding:16px 20px;margin-top:8px;font-size:13px;color:{_mc()};line-height:1.8">
<b style="color:{_tc()}">날짜 선택 안내</b><br>
• 날짜를 선택하고 <b>조회</b> 버튼을 누르면 리포트가 나와요<br>
• <span style="color:#f97316">14일 이상 미접속</span> 고객은 <b>3월 15일</b>부터 등장해요<br>
• <span style="color:#ef4444">이탈 예측</span>은 가입 후 <b>21일 경과</b>한 고객만 가능해요 (3월 22일~)<br>
• 고객을 클릭하면 맞춤 영화 추천과 메시지를 볼 수 있어요
</div>""", unsafe_allow_html=True)

    # 조회 버튼 누르기 전에는 아무것도 표시 안 함
    queried = st.session_state.get("daily_queried", None)
    if queried is None:
        st.divider()
        st.markdown(
            f'<div style="text-align:center;padding:60px 0;color:{_mc()};font-size:15px">'
            f'날짜를 선택하고 <b style="color:{_tc()}">조회</b> 버튼을 눌러주세요.</div>',
            unsafe_allow_html=True)
        return

    selected = queried   # 조회 버튼 눌렀을 때의 날짜 사용
    st.markdown(f"**{selected.year}년 {selected.month:02d}월 {selected.day:02d}일 리포트**")
    st.divider()

    try:
        from analyzer import get_churn_risk, get_inactive_users, get_retention_info, load_data
        df, _ = load_data()
        df["_reg"] = pd.to_datetime(df["reg_date"]).dt.date
        df["_end"] = pd.to_datetime(df["end_date"]).dt.date

        df_21           = df[df["duration_days"] >= 21]
        today_df        = df[df["_reg"] == selected]
        cum_df          = df[df["_reg"] <= selected]
        eligible_cutoff = selected - timedelta(days=21)
        eligible_df     = df_21[df_21["_reg"] <= eligible_cutoff]
        eligible_prev   = df_21[df_21["_reg"] <= (eligible_cutoff - timedelta(days=1))]

        risk_all = get_churn_risk(top_n=5000, min_prob=0.5)
        hr_cum   = risk_all[risk_all["USER_KEY"].isin(eligible_df["USER_KEY"])   & (risk_all["churn_risk"] >= 0.7)].reset_index(drop=True)
        hr_prev  = risk_all[risk_all["USER_KEY"].isin(eligible_prev["USER_KEY"]) & (risk_all["churn_risk"] >= 0.7)]

        inactive_df  = get_inactive_users(selected, min_days=14)
        inactive_cnt = len(inactive_df)
        eligible_cnt = len(eligible_df)
        risk_cnt     = len(hr_cum)
        churn_rate   = risk_cnt / max(eligible_cnt, 1) * 100
        retain_rt    = 100 - churn_rate
        delta        = risk_cnt - len(hr_prev)
        new_today    = len(today_df)
        total_cum    = len(cum_df)
        retain_cum   = eligible_cnt - risk_cnt

        # ── 지표 2×4 (왼쪽) + 설명 (오른쪽) ─────────────────────────────
        badge = (f'<div class="badge-red">↑ +{delta:,}명 (전날 대비)</div>' if delta > 0
                 else f'<div class="badge-grn">↓ {abs(delta):,}명 (전날 대비)</div>') if eligible_cnt > 0 else ""

        col_metrics, col_metrics_desc = st.columns([2, 3])
        with col_metrics:
            r1, r2 = st.columns(2)
            r1.markdown(_stat("신규 가입",   f"{new_today:,}", "명", small=True), unsafe_allow_html=True)
            r2.markdown(_stat("누적 가입자", f"{total_cum:,}", "명", small=True), unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)
            r3, r4 = st.columns(2)
            r3.markdown(_stat("예측 가능", f"{eligible_cnt:,}", "명", small=True), unsafe_allow_html=True)
            r4.markdown(_stat("안정 고객",  f"{retain_cum:,}", "명", "#22c55e", small=True), unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)
            r5, r6 = st.columns(2)
            r5.markdown(_stat("이탈 고위험군", f"{risk_cnt:,}", "명", "#ef4444", small=True) + badge, unsafe_allow_html=True)
            r6.markdown(_stat("14일 미접속", f"{inactive_cnt:,}", "명", "#f97316", small=True), unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)
            r7, r8 = st.columns(2)
            r7.markdown(_stat("이탈률",  f"{churn_rate:.1f}", "%", "#ef4444", small=True), unsafe_allow_html=True)
            r8.markdown(_stat("유지율",  f"{retain_rt:.1f}",  "%", "#22c55e", small=True), unsafe_allow_html=True)

        with col_metrics_desc:
            st.markdown(f"""
<div style="background:{_cc()};border:1px solid {_bc()};border-radius:10px;padding:16px 20px;font-size:13px;color:{_mc()};line-height:2">
<b style="color:{_tc()}">지표 설명</b><br>
<span style="color:#f97316">■</span> <b>14일 미접속</b>: View History 기반, 14일 이상 앱을 열지 않은 고객 수<br>
<span style="color:#ef4444">■</span> <b>이탈 고위험군</b>: 가입 후 21일 경과한 고객 중 이탈 확률 70%+ 예측 고객<br>
<span style="color:#22c55e">■</span> <b>안정 고객</b>: 예측 가능 고객 중 이탈 확률 70% 미만 고객<br>
<span style="color:#888">■</span> <b>예측 가능</b>: 가입 후 21일 관측창 완료 → 이탈 확률 계산 가능<br><br>
{"⚠️ 아직 관측창(21일)을 완료한 고객이 없어요. 3월 22일부터 이탈 예측이 시작돼요." if eligible_cnt == 0 else f"현재 {eligible_cnt:,}명의 이탈 확률 계산이 가능합니다."}
</div>""", unsafe_allow_html=True)

        st.divider()

        # ── 차트 ──────────────────────────────────────────────────────────
        dates_7d      = [(selected - timedelta(days=i)) for i in range(6, -1, -1)]
        new_per_day   = [len(df[df["_reg"] == d]) for d in dates_7d]
        churn_per_day = [len(df[df["_end"] == d]) for d in dates_7d]
        genre_map     = {"Drama":"drama_ratio","Animation/Family":"family_ratio","SF/Fantasy":"sf_ratio",
                         "Thriller/Crime":"thriller_ratio","Action/Adventure":"action_ratio",
                         "Romance":"romance_ratio","Comedy":"comedy_ratio","Historical/War":"horror_ratio"}
        wtcol = "total_watch_time(min)" if "total_watch_time(min)" in df.columns else None
        genre_totals = {}
        if wtcol:
            for gname, rcol in genre_map.items():
                if rcol in df.columns:
                    genre_totals[gname] = float((df[rcol] * df[wtcol]).sum())

        # ── 트렌드 차트 + 설명 ───────────────────────────────────────────
        ct1, ct2 = st.columns([3, 2])
        with ct1:
            st.markdown('<div class="sec-title">최근 7일 트렌드</div>', unsafe_allow_html=True)
            fig1 = go.Figure()
            fig1.add_trace(go.Scatter(x=dates_7d, y=new_per_day, name="신규가입",
                                      mode="lines+markers", line=dict(color="#4f9cf9", width=2), marker=dict(size=6)))
            fig1.add_trace(go.Scatter(x=dates_7d, y=churn_per_day, name="이탈",
                                      mode="lines+markers", line=dict(color="#ef4444", width=2), marker=dict(size=6)))
            fig1.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                font_color="white", height=220, margin=dict(l=0,r=0,t=10,b=0),
                                xaxis=dict(gridcolor="#333"), yaxis=dict(gridcolor="#333"),
                                legend=dict(orientation="h", y=1.1))
            st.plotly_chart(fig1, use_container_width=True)
        with ct2:
            st.markdown('<div class="sec-title">트렌드 해석</div>', unsafe_allow_html=True)
            peak_day   = dates_7d[new_per_day.index(max(new_per_day))]
            peak_val   = max(new_per_day)
            churn_days = sum(1 for v in churn_per_day if v > 0)
            st.markdown(f"""
<div style="background:{_cc()};border:1px solid {_bc()};border-radius:10px;padding:16px;font-size:13px;color:{_mc()};line-height:1.9">
<b style="color:{_tc()}">신규 가입 추이</b><br>
최근 7일 중 <b style="color:#4f9cf9">{peak_day.strftime('%m/%d')}</b>에 신규 가입이 가장 많았어요 ({peak_val:,}명).<br><br>
<b style="color:{_tc()}">이탈 신호</b><br>
{"이탈 기록이 있는 날이 " + str(churn_days) + "일 관측됐어요. 이탈 방지 액션이 필요해요." if churn_days > 0 else "최근 7일간 이탈 기록이 없어요. 좋은 신호예요."}
</div>""", unsafe_allow_html=True)

        # ── 장르 차트 + 설명 ─────────────────────────────────────────────
        if genre_totals:
            cg1, cg2 = st.columns([3, 2])
            with cg1:
                st.markdown('<div class="sec-title">장르별 시청 현황</div>', unsafe_allow_html=True)
                sg = sorted(genre_totals.items(), key=lambda x: x[1])
                fig2 = go.Figure(go.Bar(x=[v for _,v in sg], y=[k for k,_ in sg],
                                        orientation="h", marker_color="#4f9cf9"))
                fig2.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                    font_color="white", height=220, margin=dict(l=0,r=0,t=10,b=0),
                                    xaxis=dict(gridcolor="#333"), yaxis=dict(gridcolor="#333"))
                st.plotly_chart(fig2, use_container_width=True)
            with cg2:
                st.markdown('<div class="sec-title">장르 해석</div>', unsafe_allow_html=True)
                top_genre   = max(genre_totals, key=genre_totals.get)
                top_pct     = genre_totals[top_genre] / max(sum(genre_totals.values()), 1) * 100
                total_items = len(genre_totals)
                st.markdown(f"""
<div style="background:{_cc()};border:1px solid {_bc()};border-radius:10px;padding:16px;font-size:13px;color:{_mc()};line-height:1.9">
<b style="color:{_tc()}">인기 장르</b><br>
전체 시청 시간의 <b style="color:#4f9cf9">{top_pct:.0f}%</b>가 <b>{top_genre}</b>에 집중돼 있어요.<br><br>
<b style="color:{_tc()}">다양성</b><br>
총 {total_items}개 장르가 시청되고 있어요. 장르 다양성은 고객 만족도와 연관이 높아요.
</div>""", unsafe_allow_html=True)

        st.divider()

        # ── AI 리포트 ────────────────────────────────────────────────────
        rpt_key = f"quick_rpt_{selected}"
        if rpt_key not in st.session_state:
            with st.spinner("일별 보고서 자동 생성 중..."):
                try:
                    from agent import run_quick_daily_report
                    rpt = run_quick_daily_report(
                        str(selected), risk_cnt, churn_rate, new_today, total_cum, delta)
                    st.session_state[rpt_key]             = rpt
                    st.session_state["latest_daily_report"] = rpt  # 경영진 탭용
                except Exception as e:
                    st.session_state[rpt_key] = f"생성 오류: {e}"

        col_rpt, col_rpt_btn = st.columns([4, 1])
        with col_rpt:
            clean_rpt = strip_md(st.session_state.get(rpt_key, ""))
            safe_rpt  = _html.escape(clean_rpt).replace("\n", "<br>")
            st.markdown(
                f'<div style="background:{_cc()};border:1px solid {_bc()};border-radius:12px;padding:20px;'
                f'font-size:14px;line-height:1.75;color:{_tc()}">{safe_rpt}</div>',
                unsafe_allow_html=True)
        with col_rpt_btn:
            if st.button("상세 보고서\n(LangGraph)", type="secondary", key="daily_full_btn"):
                with st.spinner("실행 중..."):
                    try:
                        from agent import run_daily_agent
                        rpt = run_daily_agent(str(selected))
                        st.session_state[rpt_key]               = rpt
                        st.session_state["latest_daily_report"] = rpt
                        st.rerun(scope="fragment")
                    except Exception as e:
                        st.error(f"오류: {e}")

        st.divider()

        # ════════════════════════════════════════════════════════════════
        # 섹션 1: 14일 이상 미접속 고객
        # ════════════════════════════════════════════════════════════════
        st.markdown(_section_header(
            f"섹션 1  |  14일 이상 미접속 고객  —  {inactive_cnt:,}명",
            "View History 기반으로 14일 이상 앱을 열지 않은 고객입니다. "
            "이탈 확률 계산과 무관하게 즉시 메시지를 보내야 할 대상이에요. "
            "고객을 클릭하면 맞춤 영화 추천과 발송 메시지가 표시됩니다.",
            "#f97316"
        ), unsafe_allow_html=True)

        if inactive_cnt > 0:
            act_show = inactive_df.sort_values("days_inactive", ascending=False).reset_index(drop=True)
            avail    = [c for c in ["days_inactive","age","gender","is_promotion"] if c in act_show.columns]
            show1    = act_show[avail].copy()
            show1.insert(0, "Num", range(1, len(show1)+1))
            if "age" in show1.columns:
                show1["age"] = (show1["age"] // 10 * 10).astype(int)
            show1.columns = [{"days_inactive":"미접속일수","age":"age_group",
                              "gender":"성별","is_promotion":"프로모션"}.get(c,c) for c in show1.columns]
            styled1 = show1.style\
                .background_gradient(subset=["미접속일수"], cmap="Oranges", vmin=14, vmax=30)\
                .format({"미접속일수": "{:.0f}일"})\
                .set_properties(**{"text-align":"center","font-size":"13px"})\
                .set_table_styles([
                    {"selector":"th","props":[("text-align","center"),("font-size","13px")]},
                    {"selector":"td","props":[("text-align","center")]},
                ])
            event1 = st.dataframe(styled1, use_container_width=True, height=280,
                                  on_select="rerun", selection_mode="single-row")
            if event1.selection.rows:
                sel_key = str(act_show.iloc[event1.selection.rows[0]]["USER_KEY"])
                st.divider()
                _customer_panel(sel_key, selected, df, act_show)
        else:
            st.markdown("😊 **14일 이상 미접속 고객이 없어요!** 모든 고객이 활발하게 이용 중입니다.")

        st.divider()

        # ════════════════════════════════════════════════════════════════
        # 섹션 2: 21일 완료 이탈 고위험군
        # ════════════════════════════════════════════════════════════════
        st.markdown(_section_header(
            f"섹션 2  |  이탈 고위험군 (21일 관측 완료)  —  {risk_cnt:,}명",
            "가입 후 21일 관측창을 완료한 고객 중 GradientBoosting 모델이 이탈 확률 70% 이상으로 예측한 고객입니다. "
            "3월 22일부터 등장하며, 행을 클릭하면 이탈 확률·영화 추천·메시지를 볼 수 있어요.",
            "#ef4444"
        ), unsafe_allow_html=True)

        if eligible_cnt == 0:
            st.markdown("😊 **아직 관측창(21일)을 완료한 고객이 없어요.** 3월 22일부터 이탈 예측이 시작돼요.")
        elif hr_cum.empty:
            st.markdown("😊 **이탈 확률이 높은 고객이 없어요!** 모든 예측 가능 고객이 안정 상태입니다.")
        else:
            show2 = hr_cum[["churn_risk","age","gender","is_promotion"]].copy() if all(
                c in hr_cum.columns for c in ["age","gender","is_promotion"]
            ) else hr_cum[["churn_risk"]].copy()
            show2.insert(0, "Num", range(1, len(show2)+1))
            show2["churn_risk"] = (show2["churn_risk"] * 100).round(1)
            if "age" in show2.columns:
                show2["age"] = (show2["age"] // 10 * 10).astype(int)
            col_map2 = {"churn_risk":"이탈확률(%)","age":"age_group","gender":"성별","is_promotion":"프로모션"}
            show2.columns = [col_map2.get(c,c) for c in show2.columns]
            styled2 = show2.style\
                .background_gradient(subset=["이탈확률(%)"], cmap="Reds", vmin=70, vmax=100)\
                .format({"이탈확률(%)": "{:.1f}"})\
                .set_properties(**{"text-align":"center","font-size":"13px"})\
                .set_table_styles([
                    {"selector":"th","props":[("text-align","center"),("font-size","13px")]},
                    {"selector":"td","props":[("text-align","center")]},
                ])
            event2 = st.dataframe(styled2, use_container_width=True, height=280,
                                  on_select="rerun", selection_mode="single-row")
            if event2.selection.rows:
                sel_key = str(hr_cum.iloc[event2.selection.rows[0]]["USER_KEY"])
                st.divider()
                _customer_panel(sel_key, selected, df, hr_cum)

    except Exception as e:
        st.error(f"데이터 오류: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — 주간 보고서  (@st.fragment → 독립 실행)
# ══════════════════════════════════════════════════════════════════════════════
@st.fragment
def tab_weekly():
    col_w, col_w_desc = st.columns([1, 2])
    with col_w:
        base_w  = date_picker("기준일 (이전 7일 자동 계산)", date(2021, 3, 22), "w")
        start_w = base_w - timedelta(days=6)
        st.caption(f"분석 기간: {start_w} ~ {base_w}")
    with col_w_desc:
        st.markdown("""
<div style="background:{_cc()};border:1px solid {_bc()};border-radius:10px;padding:16px 20px;margin-top:8px;font-size:13px;color:{_mc()};line-height:1.8">
<b style="color:white">주간 보고서 안내</b><br>
• <span style="color:#f97316">섹션 1</span>: 기준일까지 <b>14일 이상 미접속</b>한 고객 현황 (전체 대상)<br>
• <span style="color:#ef4444">섹션 2</span>: 관측창(21일) <b>완료 고객의 이탈 확률</b> 분포 (3월 22일~)<br>
• 기준일을 바꾸면 두 섹션 모두 자동 업데이트돼요
</div>""", unsafe_allow_html=True)

    st.divider()

    try:
        from analyzer import get_churn_risk, get_inactive_users, load_data
        df_w, _ = load_data()
        df_w["_reg"] = pd.to_datetime(df_w["reg_date"]).dt.date

        # ── 섹션 1: 14일 이상 미접속 ──────────────────────────────────
        st.markdown(_section_header(
            "섹션 1  |  14일 이상 미접속 현황",
            "기준일 기준으로 14일 이상 앱을 열지 않은 고객 수입니다. "
            "이탈 확률과 무관하게 즉각적인 리텐션 액션이 필요한 고객이에요.",
            "#f97316"
        ), unsafe_allow_html=True)

        inactive_w = get_inactive_users(base_w, min_days=14)
        inactive_w_cnt = len(inactive_w)

        # 7일간 일별 미접속 추이
        dates_7  = [(base_w - timedelta(days=i)) for i in range(6, -1, -1)]
        inact_7  = [len(get_inactive_users(d, min_days=14)) for d in dates_7]
        new_7    = [len(df_w[df_w["_reg"] == d]) for d in dates_7]

        c1, c2, c3 = st.columns(3)
        c1.metric("14일+ 미접속", f"{inactive_w_cnt:,}명")
        c2.metric("전체 가입자 대비", f"{inactive_w_cnt / max(len(df_w),1)*100:.1f}%")
        c3.metric("기간 내 신규 가입", f"{sum(new_7):,}명")

        fig_w1 = go.Figure()
        fig_w1.add_trace(go.Bar(x=dates_7, y=new_7,   name="신규가입",    marker_color="#4f9cf9"))
        fig_w1.add_trace(go.Bar(x=dates_7, y=inact_7, name="14일 미접속", marker_color="#f97316"))
        fig_w1.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                              font_color="white", height=220, margin=dict(l=0,r=0,t=10,b=0),
                              xaxis=dict(gridcolor="#333"), yaxis=dict(gridcolor="#333"),
                              barmode="group", legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig_w1, use_container_width=True)

        st.divider()

        # ── 섹션 2: 21일 완료 이탈확률 분포 ─────────────────────────
        st.markdown(_section_header(
            "섹션 2  |  이탈 확률 분포 (관측창 21일 완료 고객)",
            "기준일 기준으로 가입 후 21일이 지나 이탈 확률을 계산할 수 있는 고객의 위험도 분포입니다. "
            "3월 22일(기준일)부터 데이터가 나타납니다.",
            "#ef4444"
        ), unsafe_allow_html=True)

        eligible_cutoff_w = base_w - timedelta(days=21)
        df_w21   = df_w[df_w["duration_days"] >= 21]
        elig_w   = df_w21[df_w21["_reg"] <= eligible_cutoff_w]
        elig_cnt = len(elig_w)

        if elig_cnt == 0:
            st.info(f"기준일 {base_w} 기준 아직 관측창(21일)을 완료한 고객이 없어요. "
                    f"기준일을 3월 22일 이후로 설정해보세요.")
        else:
            risk_all_w = get_churn_risk(top_n=23079, min_prob=0.0)
            in_elig    = risk_all_w["USER_KEY"].isin(elig_w["USER_KEY"])
            hr_w  = risk_all_w[in_elig & (risk_all_w["churn_risk"] >= 0.7)]
            mid_w = risk_all_w[in_elig & (risk_all_w["churn_risk"] >= 0.4) & (risk_all_w["churn_risk"] < 0.7)]
            low_w = risk_all_w[in_elig & (risk_all_w["churn_risk"] < 0.4)]
            ph_w  = hr_w[hr_w["USER_KEY"].isin(df_w[df_w["is_promotion"]==1]["USER_KEY"])] if "is_promotion" in df_w.columns else hr_w

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("예측 가능",       f"{elig_cnt:,}명")
            c2.metric("고위험 (70%+)",   f"{len(hr_w):,}명",  f"{len(hr_w)/max(elig_cnt,1)*100:.1f}%")
            c3.metric("중위험 (40~70%)", f"{len(mid_w):,}명", f"{len(mid_w)/max(elig_cnt,1)*100:.1f}%")
            c4.metric("안정 (40% 미만)", f"{len(low_w):,}명", f"{len(low_w)/max(elig_cnt,1)*100:.1f}%")

            # 위험도 도넛 차트
            fig_w2 = go.Figure(go.Pie(
                labels=["고위험","중위험","안정"],
                values=[len(hr_w), len(mid_w), len(low_w)],
                marker_colors=["#ef4444","#eab308","#22c55e"],
                hole=0.55,
            ))
            fig_w2.update_layout(paper_bgcolor="rgba(0,0,0,0)", font_color="white",
                                  height=220, margin=dict(l=0,r=0,t=10,b=0),
                                  legend=dict(orientation="h", y=-0.1))
            st.plotly_chart(fig_w2, use_container_width=True)

            ph_pct = len(ph_w) / max(len(hr_w),1) * 100
            st.caption(f"프로모션 고위험: {len(ph_w):,}명 (고위험군의 {ph_pct:.0f}%)")

        st.divider()

        # ── 자동 주간 보고서 ─────────────────────────────────────────
        wk_key = f"quick_weekly_{base_w}"
        if wk_key not in st.session_state:
            with st.spinner("주간 보고서 자동 생성 중..."):
                try:
                    from agent import run_quick_weekly_report
                    hr_cnt  = len(hr_w)  if elig_cnt > 0 else 0
                    mid_cnt = len(mid_w) if elig_cnt > 0 else 0
                    low_cnt = len(low_w) if elig_cnt > 0 else 0
                    ph_cnt  = len(ph_w)  if elig_cnt > 0 else 0
                    rpt = run_quick_weekly_report(
                        str(base_w), str(start_w), elig_cnt,
                        hr_cnt, mid_cnt, low_cnt, ph_cnt
                    )
                    st.session_state[wk_key]         = rpt
                    st.session_state["weekly_report"] = rpt
                except Exception as e:
                    st.session_state[wk_key] = f"생성 오류: {e}"

        safe_w = _html.escape(strip_md(st.session_state.get(wk_key, ""))).replace("\n", "<br>")
        st.markdown(
            f'<div style="background:{_cc()};border:1px solid {_bc()};border-radius:12px;padding:20px;'
            f'font-size:14px;line-height:1.75;color:{_tc()}">{safe_w}</div>',
            unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("상세 주간 보고서 (LangGraph 2노드)", type="secondary", key="weekly_full_btn"):
            with st.spinner("생성 중..."):
                try:
                    from agent import run_weekly_agent
                    rpt = run_weekly_agent()
                    st.session_state[wk_key]         = rpt
                    st.session_state["weekly_report"] = rpt
                    st.rerun(scope="fragment")
                except Exception as e:
                    st.error(f"오류: {e}")

    except Exception as e:
        st.error(f"오류: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — 경영진 요약  (@st.fragment → 독립 실행)
# ══════════════════════════════════════════════════════════════════════════════
@st.fragment
def tab_exec():
    st.subheader("경영진 요약 보고서")

    try:
        from analyzer import get_summary_stats
        stats = get_summary_stats()

        total     = stats["total"]
        high      = stats["high_risk"]
        medium    = stats["medium_risk"]
        low_      = stats["low_risk"]
        promo_rt  = stats["promo_repurchase_rate"]
        nonpro_rt = stats["non_promo_repurchase_rate"]
        high_pct  = high / max(total, 1) * 100
        gap       = nonpro_rt - promo_rt
        tc        = _tc()
        cc        = _cc()

        # ── KPI 카드 3개 ─────────────────────────────────────────────────
        k1, k2, k3 = st.columns(3)
        k1.markdown(
            f'<div style="background:{cc};border:1px solid {_bc()};border-radius:10px;padding:18px;text-align:center">'
            f'<div style="font-size:12px;color:{_mc()}">이탈 고위험군</div>'
            f'<div style="font-size:2rem;font-weight:700;color:#ef4444">{high:,}명</div>'
            f'<div style="font-size:12px;color:{_mc()}">전체의 {high_pct:.1f}%</div></div>',
            unsafe_allow_html=True)
        k2.markdown(
            f'<div style="background:{cc};border:1px solid {_bc()};border-radius:10px;padding:18px;text-align:center">'
            f'<div style="font-size:12px;color:{_mc()}">프로모션 재구매율</div>'
            f'<div style="font-size:2rem;font-weight:700;color:#f97316">{promo_rt}%</div>'
            f'<div style="font-size:12px;color:{_mc()}">비프로모션 {nonpro_rt}%</div></div>',
            unsafe_allow_html=True)
        k3.markdown(
            f'<div style="background:{cc};border:1px solid {_bc()};border-radius:10px;padding:18px;text-align:center">'
            f'<div style="font-size:12px;color:{_mc()}">프로모/비프로 격차</div>'
            f'<div style="font-size:2rem;font-weight:700;color:#{"22c55e" if gap > 0 else "ef4444"}">△{abs(gap):.1f}%p</div>'
            f'<div style="font-size:12px;color:{_mc()}">{"비프로모션 우위" if gap > 0 else "프로모션 불리"}</div></div>',
            unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # ── Plotly 차트 2개 ───────────────────────────────────────────────
        ch1, ch2 = st.columns(2)
        with ch1:
            fig1 = go.Figure(go.Bar(
                x=["고위험", "중위험", "안정"],
                y=[high, medium, low_],
                marker_color=["#ef4444","#eab308","#22c55e"],
                text=[f"{v:,}명" for v in [high, medium, low_]],
                textposition="outside",
            ))
            fig1.update_layout(
                title="세그먼트 분포", paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)", font_color=tc,
                height=250, margin=dict(l=0,r=0,t=40,b=0),
                xaxis=dict(gridcolor="#333"), yaxis=dict(gridcolor="#333"),
            )
            st.plotly_chart(fig1, use_container_width=True)

        with ch2:
            fig2 = go.Figure(go.Bar(
                x=["프로모션", "비프로모션"],
                y=[promo_rt, nonpro_rt],
                marker_color=["#f97316","#3b82f6"],
                text=[f"{v}%" for v in [promo_rt, nonpro_rt]],
                textposition="outside",
            ))
            fig2.update_layout(
                title="재구매율 비교 (%)", paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)", font_color=tc,
                height=250, margin=dict(l=0,r=0,t=40,b=0),
                yaxis=dict(range=[0,100], gridcolor="#333"),
                xaxis=dict(gridcolor="#333"),
            )
            st.plotly_chart(fig2, use_container_width=True)

    except Exception as e:
        st.error(f"지표 오류: {e}")


    st.divider()
    # 세션에서 가장 최근 일별 보고서 찾기 (날짜 무관)
    d_rpt = st.session_state.get("latest_daily_report", "")
    w_rpt = st.session_state.get("weekly_report", "")
    c1, c2 = st.columns(2)
    if d_rpt:
        c1.success("일별 보고서 준비됨")
    else:
        c1.warning("일별 보고서 없음 — 탭1에서 날짜 선택")
    if w_rpt:
        c2.success("주간 보고서 준비됨")
    else:
        c2.warning("주간 보고서 없음 — 탭2에서 먼저 생성")

    if st.button("경영진 보고서 생성 (2~3줄 초압축)", type="primary", key="exec_btn"):
        with st.spinner("생성 중..."):
            try:
                from agent import run_exec_agent
                rpt      = run_exec_agent(daily_report=d_rpt, weekly_report=w_rpt)
                clean    = strip_md(rpt)
                safe_rpt = _html.escape(clean).replace("\n", "<br><br>")
                st.success("완료!")
                st.markdown(
                    f'<div style="background:{_cc()};border-left:4px solid #7c3aed;border:1px solid {_bc()};'
                    f'border-radius:8px;padding:24px 28px;font-size:15px;line-height:2;color:{_tc()};'
                    f'font-family:\'Malgun Gothic\',sans-serif">{safe_rpt}</div>',
                    unsafe_allow_html=True)
            except Exception as e:
                st.error(f"오류: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — 영화 추천 챗봇  (@st.fragment → 독립 실행)
# ══════════════════════════════════════════════════════════════════════════════
MOOD_MAP = {
    "힘들":("comedy","힘든 날엔 웃음이 최고의 약이에요"),
    "지쳐":("comedy","지쳤을 땐 가볍게 웃을 수 있는 영화가 제일 좋아요"),
    "스트레스":("comedy","스트레스엔 코미디로 확 날려버려요"),
    "우울":("comedy","우울할 때 웃기는 영화 한 편이 기분을 확 바꿔줘요"),
    "슬프":("romance","슬플 때는 감성적인 로맨스 영화가 잘 어울려요"),
    "외로":("romance","외로울 때 따뜻한 로맨스로 위로받아요"),
    "설레":("romance","설레는 기분엔 로맨스 영화가 딱이에요"),
    "심심":("action","심심할 땐 짜릿한 액션으로 활력을 충전해요"),
    "신나":("action","신나는 기분엔 에너지 넘치는 액션이 어울려요"),
    "무섭":("horror","스릴을 즐기신다면 공포 장르가 딱이에요"),
    "무서":("horror","스릴을 즐기신다면 공포 장르가 딱이에요"),
    "가족":("family","온 가족이 함께 즐길 수 있는 영화가 최고죠"),
    "아이":("family","아이와 함께 보기 좋은 따뜻한 영화예요"),
    "우주":("sf","우주와 미래를 탐험하는 SF 영화 어때요"),
    "판타지":("sf","상상력을 자극하는 SF/판타지가 어울려요"),
}

@st.fragment
def tab_chatbot():
    st.subheader("영화 추천 챗봇")
    st.caption("기분을 말해주세요 — '힘들다', '외롭다', '심심하다', '신난다' 등")

    # ── 대화 기록 (질문 → 답변 순서로 정방향) ────────────────────────────────
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("movies"):
                show_movies(msg["movies"])

    # ── 입력창 (아래 고정, 자연스러운 채팅 흐름) ──────────────────────────────
    if prompt := st.chat_input("기분이나 보고 싶은 영화 종류를 말해주세요..."):

        # 부적절한 입력 필터
        bad_keywords = ["섹스", "야동", "성인", "포르노", "19금", "음란"]
        if any(kw in prompt for kw in bad_keywords):
            with st.chat_message("assistant"):
                st.markdown("영화 추천 챗봇이에요. 기분이나 보고 싶은 장르를 말해주시면 추천해드릴게요!")
            return

        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            genre, mood_desc = next(
                ((g, r) for kw, (g, r) in MOOD_MAP.items() if kw in prompt),
                (None, None)
            )
            if not genre:
                try:
                    from agent import _llm
                    det = _llm(0.1).invoke(
                        f"사용자 메시지: '{prompt}'\n"
                        "영화 장르를 하나만 골라 영어 소문자로만 답하세요.\n"
                        "선택지: drama, action, romance, thriller, horror, family, sf, comedy"
                    ).content.strip().lower()
                    genre     = det if det in ["drama","action","romance","thriller","horror","family","sf","comedy"] else "drama"
                    mood_desc = f"말씀하신 내용에 {genre} 장르가 어울릴 것 같아요"
                except Exception:
                    genre, mood_desc = "drama", "이런 영화 어때요"

            with st.spinner("분석 중..."):
                try:
                    from agent import _llm
                    explain = _llm(0.6).invoke(
                        f"사용자가 '{prompt}'라고 했어요.\n"
                        f"{mood_desc}.\n"
                        f"왜 {genre} 장르를 추천하는지 공감 어린 말투로 2~3문장 설명해주세요.\n"
                        "마지막 문장은 '아래 영화들을 추천해드려요!'로 끝내세요.\n"
                        "자연스러운 한국어로 작성해주세요."
                    ).content
                except Exception:
                    explain = f"{mood_desc}! 아래 영화들을 추천해드려요!"

            st.markdown(explain)

            with st.spinner("영화 찾는 중..."):
                from tmdb import add_reasons, get_movies
                turn     = len(st.session_state.chat_history)
                page_num = (turn % 4) + 1
                movies   = get_movies(genre=genre, year_gte=2018, page=page_num)[:5]
                movies   = add_reasons(movies, genre, 30, "M")

            show_movies(movies)
            st.session_state.chat_history.append(
                {"role": "assistant", "content": explain, "movies": movies}
            )

    if st.session_state.chat_history:
        if st.button("대화 초기화", key="clear_chat"):
            st.session_state.chat_history = []
            st.rerun(scope="fragment")


# ══════════════════════════════════════════════════════════════════════════════
# 탭에 fragment 연결
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    tab_daily()

with tab2:
    tab_weekly()

with tab3:
    tab_exec()

with tab4:
    tab_chatbot()
