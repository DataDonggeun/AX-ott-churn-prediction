"""
LangGraph 멀티에이전트 시스템
Supervisor → [데이터/모델/CRM 전문가 병렬] → Judge → conditional loop
"""
import os
import requests
from typing import TypedDict, Literal
from langgraph.graph import StateGraph, END, START
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

BASE_URL = "http://localhost:8000"
MAX_ITERATIONS = 3
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "YOUR_GEMINI_API_KEY")

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-pro",
    google_api_key=GOOGLE_API_KEY,
    temperature=0,
)

# ── 상태 스키마 ────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    user_question: str      # 사용자 질문
    plan: str               # Supervisor 계획
    data_result: str        # 데이터 전문가 결과 (step01~03)
    model_result: str       # 모델 전문가 결과 (step04~05)
    crm_result: str         # CRM 전문가 결과 (step07)
    judge_verdict: str      # "sufficient" or "insufficient"
    judge_feedback: str     # 부족할 때 Supervisor에게 전달할 피드백
    iteration: int          # 현재 루프 횟수 (MAX_ITERATIONS 초과 시 강제 종료)
    final_answer: str       # 최종 답변

# ── FastAPI 데이터 로더 ─────────────────────────────────────────────────────

def _fetch(endpoint: str) -> str:
    try:
        res = requests.get(f"{BASE_URL}{endpoint}", timeout=10)
        return res.text
    except Exception as e:
        return f'{{"error": "FastAPI 연결 실패 — 서버가 켜져 있는지 확인하세요. ({e})"}}'

# ── 노드: Supervisor ────────────────────────────────────────────────────────

def supervisor_node(state: AgentState) -> dict:
    """질문 의도 분석 + 3개 전문가에게 작업 계획 수립"""
    feedback_section = (
        f"\n[Judge 피드백 — 이전 결과의 부족한 점]\n{state['judge_feedback']}"
        if state.get("judge_feedback") else ""
    )

    response = llm.invoke([
        SystemMessage(content="""당신은 OTT 이탈 분석팀 슈퍼바이저입니다.
사용자 질문을 분석하여 3개 전문가(데이터/모델/CRM)에게 무엇을 조사할지 계획을 세우세요.
Judge 피드백이 있으면 반드시 계획을 수정하세요.
계획은 3줄 이내로 간결하게 작성하세요."""),
        HumanMessage(content=f"질문: {state['user_question']}{feedback_section}")
    ])

    return {
        "plan": response.content,
        "iteration": state.get("iteration", 0) + 1,
        "judge_feedback": "",   # 다음 루프 시작 시 초기화
    }

# ── 노드: 데이터 전문가 ─────────────────────────────────────────────────────

def data_specialist_node(state: AgentState) -> dict:
    """데이터 품질 검증 및 코호트 분석 (step01~03 영역)"""
    raw = _fetch("/pipeline/report/json")

    response = llm.invoke([
        SystemMessage(content="""당신은 OTT 데이터 품질 및 코호트 분석 전문가입니다.
다음을 분석하세요:
- 데이터 품질: 결측값, 중복, 컬럼 검증 결과
- 프로모션 vs 비프로모션 재구매율 차이
- 코호트(4개 그룹)별 시청 행동 프로필
핵심 수치 위주로 간결하게 요약하세요."""),
        HumanMessage(content=f"[계획]\n{state['plan']}\n\n[파이프라인 데이터]\n{raw[:3000]}")
    ])

    return {"data_result": response.content}

# ── 노드: 모델 전문가 ──────────────────────────────────────────────────────

def model_specialist_node(state: AgentState) -> dict:
    """모델 성능 비교 및 SHAP 피처 중요도 분석 (step04~09 영역)"""
    raw = _fetch("/pipeline/report/json")

    response = llm.invoke([
        SystemMessage(content="""당신은 ML 모델 성능 및 SHAP 해석 전문가입니다.
다음을 분석하세요:
- 모델 선정 근거: AUC, train-valid gap (과적합 여부)
- 튜닝 전후 AUC 비교 (overall / promotion / nonpromotion)
- SHAP 상위 10개 피처와 이탈 관련성
인과관계 단정 금지: "~때문에" X → "~와 연관된다" O
수치 기반으로 간결하게 요약하세요."""),
        HumanMessage(content=f"[계획]\n{state['plan']}\n\n[파이프라인 데이터]\n{raw[:3000]}")
    ])

    return {"model_result": response.content}

# ── 노드: CRM 전문가 ───────────────────────────────────────────────────────

def crm_specialist_node(state: AgentState) -> dict:
    """세그먼트 현황 분석 및 CRM 전략 수립 (step07 영역)"""
    raw = _fetch("/pipeline/report/json")

    response = llm.invoke([
        SystemMessage(content="""당신은 OTT CRM 전략 전문가입니다.
다음을 분석하세요:
- S1~S6 세그먼트별 인원, 재구매율, 이탈위험
- 조기 개입 기준 (Day7, Day14)
- 세그먼트별 권장 CRM 전략

[중요] CRM 메시지 생성 요청 시:
- 반드시 연령대·성별 정보가 있어야 생성 가능
- 정보 없으면 "어떤 연령대와 성별 유저를 대상으로 하시나요?" 라고 명시"""),
        HumanMessage(content=f"[계획]\n{state['plan']}\n\n[파이프라인 데이터]\n{raw[:3000]}")
    ])

    return {"crm_result": response.content}

# ── 노드: Judge ────────────────────────────────────────────────────────────

def judge_node(state: AgentState) -> dict:
    """3개 전문가 결과 품질 검증 → sufficient / insufficient 판정"""
    combined = f"""
[데이터 전문가 결과]
{state.get('data_result', '없음')}

[모델 전문가 결과]
{state.get('model_result', '없음')}

[CRM 전문가 결과]
{state.get('crm_result', '없음')}
"""

    response = llm.invoke([
        SystemMessage(content="""당신은 품질 검증 Judge입니다.
3개 전문가 결과가 사용자 질문에 충분히 답하는지 평가하세요.

판정 기준:
1. 사용자 질문의 핵심 요소가 모두 다뤄졌는가?
2. 구체적인 수치(인원, 비율, AUC 등)가 포함되었는가?
3. 비즈니스 제약 조건이 지켜졌는가? (인과관계 금지, 성별/연령 확인 등)

출력 형식 (반드시 지킬 것):
VERDICT: sufficient
또는
VERDICT: insufficient
FEEDBACK: [부족한 점과 보완 방향]"""),
        HumanMessage(content=f"[사용자 질문]\n{state['user_question']}\n\n[전문가 결과]\n{combined}")
    ])

    content = response.content
    verdict = "sufficient" if "VERDICT: sufficient" in content else "insufficient"
    feedback = ""
    if "FEEDBACK:" in content:
        feedback = content.split("FEEDBACK:")[1].strip()

    return {
        "judge_verdict": verdict,
        "judge_feedback": feedback,
    }

# ── 노드: 최종 답변 ─────────────────────────────────────────────────────────

def final_report_node(state: AgentState) -> dict:
    """3개 전문가 결과 통합 → 사용자에게 최종 답변"""
    response = llm.invoke([
        SystemMessage(content="""당신은 OTT 이탈 방지 AI 어시스턴트입니다.
3개 전문가의 분석을 통합하여 사용자에게 명확하고 실용적인 답변을 작성하세요.
모델 예측임을 명시하고, 인과관계를 단정하지 마세요."""),
        HumanMessage(content=f"""[질문] {state['user_question']}

[데이터 분석 결과]
{state.get('data_result', '')}

[모델 분석 결과]
{state.get('model_result', '')}

[CRM 전략]
{state.get('crm_result', '')}""")
    ])

    return {"final_answer": response.content}

# ── 조건부 분기 ─────────────────────────────────────────────────────────────

def route_after_judge(state: AgentState) -> Literal["final_report", "supervisor"]:
    """Judge 판정 + 최대 반복 횟수 초과 시 강제 종료"""
    if state["judge_verdict"] == "sufficient" or state["iteration"] >= MAX_ITERATIONS:
        return "final_report"
    return "supervisor"

# ── 그래프 조립 ─────────────────────────────────────────────────────────────

builder = StateGraph(AgentState)

builder.add_node("supervisor", supervisor_node)
builder.add_node("data_specialist", data_specialist_node)
builder.add_node("model_specialist", model_specialist_node)
builder.add_node("crm_specialist", crm_specialist_node)
builder.add_node("judge", judge_node)
builder.add_node("final_report", final_report_node)

# 흐름 연결
builder.add_edge(START, "supervisor")

# supervisor → 3개 전문가 (병렬 fan-out: 동시 실행)
builder.add_edge("supervisor", "data_specialist")
builder.add_edge("supervisor", "model_specialist")
builder.add_edge("supervisor", "crm_specialist")

# 3개 전문가 → judge (fan-in: 모두 완료 후 judge 실행)
builder.add_edge("data_specialist", "judge")
builder.add_edge("model_specialist", "judge")
builder.add_edge("crm_specialist", "judge")

# judge → 조건부 분기 (핵심: 이게 진짜 에이전트를 만드는 부분)
builder.add_conditional_edges("judge", route_after_judge, {
    "final_report": "final_report",
    "supervisor": "supervisor",     # ← 피드백 루프
})

builder.add_edge("final_report", END)

graph = builder.compile()

# ── 실행 ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("OTT 멀티에이전트 시스템 시작 (종료: exit)")
    print(f"최대 루프 횟수: {MAX_ITERATIONS}회\n")

    while True:
        user_input = input("질문: ").strip()
        if user_input.lower() == "exit":
            break
        if not user_input:
            continue

        initial_state: AgentState = {
            "user_question": user_input,
            "plan": "",
            "data_result": "",
            "model_result": "",
            "crm_result": "",
            "judge_verdict": "",
            "judge_feedback": "",
            "iteration": 0,
            "final_answer": "",
        }

        print("\n[에이전트 실행 중...]\n")
        result = graph.invoke(initial_state)
        print(f"[총 루프: {result['iteration']}회 / Judge: {result['judge_verdict']}]\n")
        print(f"[최종 답변]\n{result['final_answer']}\n")
