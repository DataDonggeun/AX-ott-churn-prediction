"""Dify 워크플로우 연동 모듈"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()
DIFY_API_KEY  = os.getenv("DIFY_API_KEY", "")
DIFY_BASE_URL = os.getenv("DIFY_BASE_URL", "https://api.dify.ai/v1")


def run_churn_prevention(age: int, days_inactive: int, genre: str, gender: str = "M") -> str:
    """이탈 방지 메시지 생성 워크플로우 실행"""
    if not DIFY_API_KEY:
        return "Dify API 키가 설정되지 않았습니다."

    try:
        r = requests.post(
            f"{DIFY_BASE_URL}/workflows/run",
            headers={
                "Authorization": f"Bearer {DIFY_API_KEY}",
                "Content-Type":  "application/json",
            },
            json={
                "inputs": {
                    "age":          str(age),
                    "days_inactive": str(days_inactive),
                    "genre":        genre,
                    "gender":       gender,
                },
                "response_mode": "blocking",
                "user":          "ott-agent",
            },
            timeout=30,
        )
        data = r.json()
        outputs = data.get("data", {}).get("outputs", {})
        return outputs.get("message", outputs.get("text", str(outputs)))
    except Exception as e:
        return f"Dify 연결 오류: {e}"
