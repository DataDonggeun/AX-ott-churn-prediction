"""파이프라인 아티팩트 캐시 — 모델/결과 저장·로드·상태 관리"""
import json
import math
import joblib
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from config import CACHE_DIR, RETRAIN_MONTHS


def _json_safe(obj: Any) -> Any:
    """
    float inf / nan → None 으로 재귀 변환.
    JSON은 inf/nan을 지원하지 않아 json.dumps가 ValueError를 냄.
    """
    if isinstance(obj, float):
        if math.isinf(obj) or math.isnan(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    return obj

STATE_FILE = CACHE_DIR / "pipeline_state.json"


# ── 상태 관리 ──────────────────────────────────────────────────────────────────

def load_state() -> dict:
    """파이프라인 실행 상태 로드"""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict):
    STATE_FILE.write_text(
        json.dumps(state, default=str, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def mark_done(step: str, meta: dict = None):
    """단계 완료 기록"""
    state = load_state()
    state[step] = {
        "completed_at": datetime.now().isoformat(),
        "meta": meta or {},
    }
    save_state(state)


def is_done(step: str) -> bool:
    """해당 단계가 이미 완료되었는지 확인"""
    return step in load_state()


def get_step_meta(step: str) -> dict:
    state = load_state()
    return state.get(step, {}).get("meta", {})


def needs_retrain() -> bool:
    """마지막 스태킹 학습으로부터 RETRAIN_MONTHS 이상 경과했는지 확인"""
    state = load_state()
    # step05_meta: 스태킹 Meta LR 학습 완료 기준
    if "step05_meta" not in state:
        return True
    last = datetime.fromisoformat(state["step05_meta"]["completed_at"])
    months_elapsed = (datetime.now() - last).days / 30
    return months_elapsed >= RETRAIN_MONTHS


def reset_pipeline():
    """전체 파이프라인 상태 초기화 (강제 재실행용)"""
    if STATE_FILE.exists():
        STATE_FILE.unlink()


def _step_num(key: str) -> Optional[int]:
    """'step05' → 5 변환. 파싱 실패 시 None 반환."""
    try:
        return int(key.replace("step", ""))
    except ValueError:
        return None


def reset_step(step: str):
    """
    특정 단계부터 다시 실행되도록 해당 단계 이후 상태 삭제.
    'stepXX' 형식이 아닌 키는 건드리지 않음.
    """
    target = _step_num(step)
    if target is None:
        return

    state = load_state()
    keys_to_remove = [
        k for k in state
        if _step_num(k) is not None and _step_num(k) >= target
    ]
    for k in keys_to_remove:
        del state[k]
    save_state(state)


# ── 아티팩트 저장/로드 ─────────────────────────────────────────────────────────

def save_artifact(name: str, obj: Any):
    """모델·Optuna study 등 pkl로 저장"""
    path = CACHE_DIR / f"{name}.pkl"
    joblib.dump(obj, path)


def load_artifact(name: str) -> Optional[Any]:
    path = CACHE_DIR / f"{name}.pkl"
    if not path.exists():
        return None
    return joblib.load(path)


def save_df(name: str, df: pd.DataFrame):
    """DataFrame을 CSV로 저장"""
    path = CACHE_DIR / f"{name}.csv"
    df.to_csv(path, index=False, encoding="utf-8-sig")


def load_df(name: str) -> Optional[pd.DataFrame]:
    path = CACHE_DIR / f"{name}.csv"
    if not path.exists():
        return None
    return pd.read_csv(path)


def save_json(name: str, data: Any):
    path = CACHE_DIR / f"{name}.json"
    path.write_text(
        json.dumps(_json_safe(data), default=str, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def load_json(name: str) -> Optional[Any]:
    path = CACHE_DIR / f"{name}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def list_cache() -> dict:
    """캐시된 파일 목록과 크기 반환"""
    files = {}
    for p in sorted(CACHE_DIR.iterdir()):
        if p.is_file():
            files[p.name] = {
                "size_kb": round(p.stat().st_size / 1024, 1),
                "modified": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds"),
            }
    return files
