"""
LangChain 단일 에이전트 (LangChain 1.x 호환)
AgentExecutor 대신 직접 while 루프로 tool calling 구현
FastAPI 서버(localhost:8000)가 켜진 상태에서 실행
"""
import os
import json
import requests
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI

BASE_URL = "http://localhost:8000"
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "YOUR_GEMINI_API_KEY")

# ── 도구 정의 ──────────────────────────────────────────────────────────────

@tool
def get_pipeline_result() -> str:
    """파이프라인 전체 결과를 가져온다. 세그먼트 현황(S1~S6 인원/재구매율/이탈위험), SHAP 피처 중요도, 모델 AUC가 포함된다."""
    try:
        res = requests.get(f"{BASE_URL}/pipeline/report/json", timeout=10)
        return res.text
    except Exception as e:
        return f"오류: FastAPI 서버가 켜져 있는지 확인하세요. ({e})"

@tool
def get_pipeline_status() -> str:
    """파이프라인 각 step(step00~step07)의 완료 여부를 확인한다. 데이터가 준비됐는지 모를 때 먼저 호출한다."""
    try:
        res = requests.get(f"{BASE_URL}/pipeline/status", timeout=10)
        return res.text
    except Exception as e:
        return f"오류: FastAPI 서버가 켜져 있는지 확인하세요. ({e})"

tools = [get_pipeline_result, get_pipeline_status]
tools_map = {t.name: t for t in tools}

SYSTEM_PROMPT = """당신은 OTT 스트리밍 서비스 전문 고객 이탈 방지 AI입니다.
CRM 담당자와 마케터의 질문에 파이프라인 데이터를 기반으로 답변합니다.

[답변 규칙]
- 인과관계 단정 금지: "~때문에 이탈" X → "~와 연관된다" O
- CRM 메시지 생성 시 반드시 연령대·성별 확인 후 작성
- 모델 예측임을 항상 명시 (확정 아님)
- 데이터 없으면 "최신 데이터를 불러올 수 없습니다" 안내

[세그먼트 기준 - 고정]
- 상위군(S1~S3): w1+w2 합계 >= 118분
- 하위군(S4~S6): w1+w2 합계 < 118분
- S1/S4: w3 >= 140분 | S2/S5: 0 < w3 < 140분 | S3/S6: w3 = 0분 (가장 위험)"""

# ── LLM 설정 ──────────────────────────────────────────────────────────────

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-pro",
    google_api_key=GOOGLE_API_KEY,
    temperature=0,
)
llm_with_tools = llm.bind_tools(tools)

# ── 에이전트 루프 ──────────────────────────────────────────────────────────

def run_agent(user_input: str, chat_history: list) -> str:
    messages = [SystemMessage(content=SYSTEM_PROMPT)] + chat_history + [HumanMessage(content=user_input)]

    for _ in range(5):  # 최대 5회 루프
        response = llm_with_tools.invoke(messages)
        messages.append(response)

        if not response.tool_calls:
            return response.content

        # 도구 실행
        for tc in response.tool_calls:
            print(f"\n[도구 호출] {tc['name']}()")
            result = tools_map[tc["name"]].invoke(tc["args"])
            print(f"[도구 결과] {str(result)[:200]}...")
            messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))

    return "최대 반복 횟수를 초과했습니다."

# ── 실행 ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("OTT 이탈 방지 에이전트 시작 (종료: exit)")
    print("FastAPI 서버가 localhost:8000에서 실행 중이어야 합니다.\n")

    chat_history = []

    while True:
        user_input = input("질문: ").strip()
        if user_input.lower() == "exit":
            break
        if not user_input:
            continue

        answer = run_agent(user_input, chat_history)
        chat_history += [HumanMessage(content=user_input), SystemMessage(content=answer)]
        print(f"\n[최종 답변]\n{answer}\n")
