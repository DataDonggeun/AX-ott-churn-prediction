"""
LangGraph 멀티노드 에이전트
- 일별 7노드 에이전트
- 주간 2노드 에이전트
- 경영진 요약 2노드 에이전트
- 나이별 Duolingo 스타일 리텐션 메시지
"""
import ctypes
import ctypes.wintypes
from concurrent.futures import ThreadPoolExecutor
from typing import TypedDict, Optional
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END
from analyzer import get_churn_risk, get_weekly_segments, get_summary_stats


# ─── Gemini API 키 (Windows 자격증명 관리자) ───────────────────────────────────
def _get_api_key() -> str:
    target = "GEMINI_API_KEY"
    try:
        class CREDENTIAL(ctypes.Structure):
            _fields_ = [
                ("Flags",              ctypes.wintypes.DWORD),
                ("Type",               ctypes.wintypes.DWORD),
                ("TargetName",         ctypes.c_wchar_p),
                ("Comment",            ctypes.c_wchar_p),
                ("LastWritten",        ctypes.wintypes.FILETIME),
                ("CredentialBlobSize", ctypes.wintypes.DWORD),
                ("CredentialBlob",     ctypes.c_char_p),
                ("Persist",            ctypes.wintypes.DWORD),
                ("AttributeCount",     ctypes.wintypes.DWORD),
                ("Attributes",         ctypes.c_void_p),
                ("TargetAlias",        ctypes.c_wchar_p),
                ("UserName",           ctypes.c_wchar_p),
            ]
        cred_ptr = ctypes.pointer(CREDENTIAL())
        ctypes.windll.advapi32.CredReadW(target, 1, 0, ctypes.byref(cred_ptr))
        blob_size = cred_ptr.contents.CredentialBlobSize
        blob      = cred_ptr.contents.CredentialBlob
        return blob[:blob_size].decode("utf-16-le")
    except Exception:
        import os
        return os.getenv("GEMINI_API_KEY", "")


def _llm(temperature: float = 0.7) -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=_get_api_key(),
        temperature=temperature,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 일별 7노드 에이전트
# ══════════════════════════════════════════════════════════════════════════════
class DailyState(TypedDict):
    date:        Optional[str]
    risk_df:     Optional[object]
    churn_text:  Optional[str]
    trend_text:  Optional[str]
    action_text: Optional[str]
    merged_text: Optional[str]
    reviewed:    Optional[str]


def daily_load_node(state: DailyState) -> DailyState:
    df = get_churn_risk(top_n=20, min_prob=0.5)
    return {**state, "risk_df": df}


def daily_churn_node(state: DailyState) -> DailyState:
    df = state["risk_df"]
    if df is None or df.empty:
        return {**state, "churn_text": "데이터 없음"}
    summary = df[["USER_KEY", "churn_risk", "age", "gender"]].head(10).to_string(index=False)
    prompt = (
        "당신은 냉철한 이탈분석가입니다.\n"
        f"아래 고위험 고객 데이터를 분석해 핵심 패턴을 3줄로 요약하세요.\n\n{summary}"
    )
    return {**state, "churn_text": _llm(0.1).invoke(prompt).content}


def daily_trend_node(state: DailyState) -> DailyState:
    segs = get_weekly_segments()
    prompt = (
        "당신은 트렌드 애널리스트입니다.\n"
        f"전체 {segs['total']:,}명 중 고위험 {segs['high_risk']:,}명, "
        f"중위험 {segs['medium_risk']:,}명, 안정 {segs['low_risk']:,}명입니다.\n"
        f"프로모션 고위험: {segs['promo_high']:,}명.\n"
        "이 트렌드의 의미와 주의사항을 3줄로 분석하세요."
    )
    return {**state, "trend_text": _llm(0.3).invoke(prompt).content}


def daily_parallel_node(state: DailyState) -> DailyState:
    """이탈분석 + 트렌드분석 병렬 실행"""
    with ThreadPoolExecutor(max_workers=2) as exe:
        f_c = exe.submit(daily_churn_node, state)
        f_t = exe.submit(daily_trend_node, state)
        sc  = f_c.result()
        st_ = f_t.result()
    return {**state, "churn_text": sc["churn_text"], "trend_text": st_["trend_text"]}


def daily_action_node(state: DailyState) -> DailyState:
    prompt = (
        "당신은 전략기획자입니다.\n"
        f"[이탈분석]\n{state['churn_text']}\n\n"
        f"[트렌드분석]\n{state['trend_text']}\n\n"
        "위 분석을 바탕으로 오늘 실행할 구체적인 액션 3가지를 제안하세요."
    )
    return {**state, "action_text": _llm(0.5).invoke(prompt).content}


def daily_merge_node(state: DailyState) -> DailyState:
    prompt = (
        "당신은 편집장입니다. 아래 분석을 하나의 일별 보고서로 통합하세요.\n\n"
        f"[이탈분석]\n{state['churn_text']}\n\n"
        f"[트렌드]\n{state['trend_text']}\n\n"
        f"[전략액션]\n{state['action_text']}\n\n"
        "형식: ## 제목 / ### 핵심요약 / ### 세부내용 / ### 오늘의 액션"
    )
    return {**state, "merged_text": _llm(0.4).invoke(prompt).content}


def daily_review_node(state: DailyState) -> DailyState:
    prompt = (
        "당신은 QA 검토자입니다. 아래 보고서를 검토하고 최종본을 출력하세요.\n"
        "오류나 과장된 표현이 있으면 수정하고, 없으면 그대로 출력하세요.\n\n"
        f"{state['merged_text']}"
    )
    return {**state, "reviewed": _llm(0.1).invoke(prompt).content}


def run_daily_agent(date: str = "") -> str:
    g = StateGraph(DailyState)
    g.add_node("load",     daily_load_node)
    g.add_node("parallel", daily_parallel_node)
    g.add_node("action",   daily_action_node)
    g.add_node("merge",    daily_merge_node)
    g.add_node("review",   daily_review_node)
    g.set_entry_point("load")
    g.add_edge("load",     "parallel")
    g.add_edge("parallel", "action")
    g.add_edge("action",   "merge")
    g.add_edge("merge",    "review")
    g.add_edge("review",   END)
    result = g.compile().invoke({
        "date": date, "risk_df": None,
        "churn_text": None, "trend_text": None,
        "action_text": None, "merged_text": None, "reviewed": None,
    })
    return result.get("reviewed", "보고서 생성 실패")


# ══════════════════════════════════════════════════════════════════════════════
# 주간 2노드 에이전트
# ══════════════════════════════════════════════════════════════════════════════
class WeeklyState(TypedDict):
    segs:   Optional[dict]
    report: Optional[str]


def weekly_load_node(state: WeeklyState) -> WeeklyState:
    return {**state, "segs": get_weekly_segments()}


def weekly_summary_node(state: WeeklyState) -> WeeklyState:
    s = state["segs"]
    prompt = (
        "당신은 주간 보고서 전문가입니다.\n"
        f"전체 코호트: {s['total']:,}명 (23,079 기준)\n"
        f"- 고위험 (이탈 확률 70%+): {s['high_risk']:,}명\n"
        f"- 중위험 (40~70%):         {s['medium_risk']:,}명\n"
        f"- 안정 (40% 미만):          {s['low_risk']:,}명\n"
        f"- 프로모션 고위험:           {s['promo_high']:,}명\n"
        f"- 프로모션 중위험:           {s['promo_medium']:,}명\n"
        f"- 전체 재구매율:             {s['repurchase_rate']}%\n\n"
        "주간 세그먼트 보고서를 작성하세요.\n"
        "형식: ## 이번 주 요약 / ### 세그먼트별 현황 / ### 우선 대응 대상 / ### 권고사항"
    )
    return {**state, "report": _llm(0.4).invoke(prompt).content}


def run_weekly_agent() -> str:
    g = StateGraph(WeeklyState)
    g.add_node("load",    weekly_load_node)
    g.add_node("summary", weekly_summary_node)
    g.set_entry_point("load")
    g.add_edge("load",    "summary")
    g.add_edge("summary", END)
    result = g.compile().invoke({"segs": None, "report": None})
    return result.get("report", "주간 보고서 생성 실패")


# ══════════════════════════════════════════════════════════════════════════════
# 경영진 요약 2노드 에이전트
# ══════════════════════════════════════════════════════════════════════════════
class ExecState(TypedDict):
    stats:         Optional[dict]
    daily_report:  Optional[str]
    weekly_report: Optional[str]
    report:        Optional[str]


def exec_load_node(state: ExecState) -> ExecState:
    return {**state, "stats": get_summary_stats()}


def exec_summary_node(state: ExecState) -> ExecState:
    s = state["stats"]
    daily  = state.get("daily_report", "") or "없음"
    weekly = state.get("weekly_report", "") or "없음"

    high_pct = s['high_risk'] / max(s['total'], 1) * 100
    gap      = s['non_promo_repurchase_rate'] - s['promo_repurchase_rate']
    prompt = (
        "당신은 대기업 OTT 사업부 전략팀장입니다.\n"
        "아래 수치를 보고 임원에게 구두로 보고하는 것처럼 정확히 3문장만 작성하세요.\n\n"
        "절대 규칙:\n"
        "- 3문장 초과 금지. 4문장 쓰면 실패\n"
        "- 마크다운(#, **, -, •) 사용 금지\n"
        "- 형식 레이블(①②③, 첫째, 둘째) 사용 금지\n"
        "- 각 문장에 숫자 1개 이상 반드시 포함\n"
        "- AI처럼 들리는 표현 금지\n\n"
        f"수치: 고위험 {s['high_risk']:,}명({high_pct:.1f}%) | "
        f"프로모션 재구매율 {s['promo_repurchase_rate']}% | "
        f"비프로모션 {s['non_promo_repurchase_rate']}% | "
        f"격차 {abs(gap):.1f}%p\n\n"
        "문장1: 현황 수치 중심\n"
        "문장2: 가장 긴급한 위험 1가지\n"
        "문장3: 이번 주 실행 과제 1가지"
    )
    return {**state, "report": _llm(0.2).invoke(prompt).content}


def run_exec_agent(daily_report: str = "", weekly_report: str = "") -> str:
    g = StateGraph(ExecState)
    g.add_node("load",    exec_load_node)
    g.add_node("summary", exec_summary_node)
    g.set_entry_point("load")
    g.add_edge("load",    "summary")
    g.add_edge("summary", END)
    result = g.compile().invoke({
        "stats": None, "report": None,
        "daily_report": daily_report,
        "weekly_report": weekly_report,
    })
    return result.get("report", "경영진 보고서 생성 실패")


# ══════════════════════════════════════════════════════════════════════════════
# Duolingo 스타일 리텐션 메시지 (나이별)
# ══════════════════════════════════════════════════════════════════════════════
def generate_retention_message(age: int, days_inactive: int,
                               gender: str = "M", genre: str = "drama") -> str:
    if age < 25:
        persona = "MZ세대 감성으로 친근하고 유머있게, 이모티콘 적극 사용, 반말 가능"
    elif age < 35:
        persona = "밀레니얼 감성으로 공감하듯, 적당히 친근하게, 존댓말"
    elif age < 50:
        persona = "신뢰감 있고 따뜻하게, 정중한 존댓말"
    else:
        persona = "정중하고 따뜻하게, 격식체, 간결하게"

    urgency = (
        "가볍게 안부를 묻는" if days_inactive <= 7
        else "걱정스럽게 보고 싶다는" if days_inactive <= 14
        else "간절하게 돌아와달라는"
    )

    prompt = (
        f"당신은 OTT 서비스 리텐션 메시지 전문가입니다.\n"
        f"대상: {age}세 {'여성' if str(gender).upper()=='F' else '남성'}, "
        f"{days_inactive}일째 미접속, 주요 장르: {genre}\n"
        f"말투: {persona}\n"
        f"톤: {urgency} 메시지\n\n"
        "2~3문장으로 자연스러운 리텐션 메시지를 작성하세요."
    )
    return _llm(1.0).invoke(prompt).content


# ══════════════════════════════════════════════════════════════════════════════
# 빠른 일별 보고서 (단일 Gemini 호출 — 약 3초)
# ══════════════════════════════════════════════════════════════════════════════
def run_quick_daily_report(selected_date: str, risk_cnt: int, churn_rate: float,
                            new_today: int, total_cum: int, delta: int) -> str:
    delta_str = f"+{delta:,}명 증가" if delta > 0 else f"{abs(delta):,}명 감소"
    prompt = (
        f"당신은 OTT 서비스 이탈 분석 AI 비서입니다.\n"
        f"{selected_date} 기준 일별 리포트를 작성하세요.\n\n"
        f"[오늘 데이터]\n"
        f"- 신규 가입: {new_today:,}명\n"
        f"- 누적 고객: {total_cum:,}명\n"
        f"- 이탈 위험 고객 (70%+): {risk_cnt:,}명 (전날 대비 {delta_str})\n"
        f"- 이탈률: {churn_rate:.1f}%\n\n"
        "다음 형식으로 작성하세요:\n\n"
        "오늘의 현황\n[핵심 수치를 포함한 2~3문장]\n\n"
        "주목할 인사이트\n[데이터에서 발견한 패턴 2~3문장]\n\n"
        "추천 액션\n[즉시 실행 가능한 대응 방안 2~3문장]"
    )
    return _llm(0.3).invoke(prompt).content


# ══════════════════════════════════════════════════════════════════════════════
# 빠른 주간 보고서 (단일 Gemini 호출 — 약 3초)
# ══════════════════════════════════════════════════════════════════════════════
def run_quick_weekly_report(base_date: str, start_date: str,
                             total: int, high: int, medium: int, low: int,
                             promo_high: int) -> str:
    # total=0이면 21일 완료자 없음 → 14일 미접속 기반 보고로 전환
    if total == 0:
        prompt = (
            f"{start_date} ~ {base_date} 기간 주간 보고서입니다.\n"
            "이 기간에는 아직 가입 후 21일 관측창을 완료한 고객이 없어 이탈 확률 계산이 불가합니다.\n"
            "대신 14일 이상 미접속 고객 현황을 중심으로 보고서를 작성하세요.\n\n"
            "마크다운 기호(#, **, -) 금지. 자연스러운 한국어 서술형 4~6문장으로 작성하세요."
        )
    else:
        prompt = (
            f"당신은 OTT 사업부 주간 보고서 담당자입니다.\n"
            f"{start_date} ~ {base_date} 주간 보고서를 작성하세요.\n\n"
            f"[이탈 예측 가능 고객 — 가입 후 21일 경과자]\n"
            f"- 예측 대상: {total:,}명\n"
            f"- 고위험 (70%+): {high:,}명 ({high/max(total,1)*100:.1f}%)\n"
            f"- 중위험 (40~70%): {medium:,}명\n"
            f"- 안정 (40% 미만): {low:,}명\n"
            f"- 프로모션 고위험: {promo_high:,}명\n\n"
            "마크다운 기호(#, **, -) 금지. 자연스러운 한국어 서술형으로 작성.\n\n"
            "이번 주 요약 (2문장)\n\n"
            "세그먼트 현황 (고위험/중위험/안정 각 한 줄)\n\n"
            "이번 주 실행 과제 (2가지)"
        )
    return _llm(0.3).invoke(prompt).content
