"""
OTT 이탈 방지 파이프라인 FastAPI 서버

실행 방법:
    cd "ai agent/fastapi"
    uvicorn main:app --reload --port 8000

운영 방식:
    Full run  (최초 / 6개월 재학습): POST /pipeline/run-full
    Fast run  (새 데이터 유입 시):   POST /pipeline/run-fast
    잡 상태 확인:                    GET  /pipeline/job/{job_id}
    전체 상태 확인:                   GET  /pipeline/status
    캐시 초기화:                      POST /pipeline/reset

인증:
    PIPELINE_API_KEY 환경변수를 설정하면 X-Api-Key 헤더 검증 활성화.
    빈 문자열(기본값)이면 인증 비활성화 — 개발/로컬 환경 전용.

파이프라인 순서 (FastAPI 담당 단계):
    01 → 03 → 06 → 08 → 09 → 10 → 11 → 12 → 14 → 15 → 16 → 17
    (02·04·05·07은 Dify 정책 기록만, 13은 없음)
"""
import sys
import uuid
import importlib
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse

sys.path.insert(0, str(Path(__file__).parent))

from cache import load_state, list_cache, reset_pipeline, needs_retrain
from config import API_KEY

# ── 단계별 모듈 로드 ────────────────────────────────────────────────────────────
step01 = importlib.import_module("01_data_contract.step01")
step03 = importlib.import_module("03_observation_window.step03")
step06 = importlib.import_module("06_dataset_generation.step06")
step08 = importlib.import_module("08_promotion_eda.step08")
step09 = importlib.import_module("09_2x2_eda.step09")
step10 = importlib.import_module("10_feature_audit.step10")
step11 = importlib.import_module("11_baseline_comparison.step11")
step12 = importlib.import_module("12_model_family_comparison.step12")
step14 = importlib.import_module("14_tuning.step14")
step15 = importlib.import_module("15_payment_sensitivity.step15")
step16 = importlib.import_module("16_shap.step16")
step17 = importlib.import_module("17_segmentation.step17")

app = FastAPI(
    title="OTT 이탈 방지 파이프라인",
    description="Step 01~17 순차 실행 / 캐시 기반 빠른 재실행 지원",
    version="2.1",
)

# ── 라우터 등록 ────────────────────────────────────────────────────────────────
app.include_router(step01.router)
app.include_router(step03.router)
app.include_router(step06.router)
app.include_router(step08.router)
app.include_router(step09.router)
app.include_router(step10.router)
app.include_router(step11.router)
app.include_router(step12.router)
app.include_router(step14.router)
app.include_router(step15.router)
app.include_router(step16.router)
app.include_router(step17.router)


# ── 인증 ───────────────────────────────────────────────────────────────────────
def verify_api_key(x_api_key: str = Header(default="")):
    """PIPELINE_API_KEY 환경변수가 설정된 경우에만 헤더 검증."""
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")


# ── 비동기 잡 관리 ──────────────────────────────────────────────────────────────
_jobs: dict = {}


def _run_step(name: str, fn, results: dict, **kwargs) -> dict:
    """
    단계 함수 실행 후 results에 기록.
    status == 'FAIL' 이면 StopIteration을 발생시켜 파이프라인 중단.
    """
    try:
        r = fn(**kwargs)
    except Exception as exc:
        r = {"status": "FAIL", "summary": str(exc)}

    results[name] = {
        "status":  r.get("status"),
        "summary": r.get("summary"),
    }
    if r.get("status") == "FAIL":
        raise StopIteration(name)
    return r


def _run_full(job_id: str):
    """전체 파이프라인 백그라운드 실행."""
    _jobs[job_id] = {"status": "RUNNING", "results": {}}
    results = _jobs[job_id]["results"]

    try:
        _run_step("step01", step01.data_contract,          results, force=True)
        _run_step("step03", step03.observation_window,     results, force=True)
        _run_step("step06", step06.dataset_generation,     results, force=True)
        _run_step("step08", step08.promotion_eda,          results, force=True)
        _run_step("step09", step09.eda_2x2,                results, force=True)
        _run_step("step10", step10.feature_audit,          results, force=True)
        _run_step("step11", step11.baseline_comparison,    results, force=True)
        _run_step("step12", step12.model_family_comparison,results, force=True)
        _run_step("step14", step14.tuning,                 results, force=True)
        _run_step("step15", step15.payment_sensitivity,    results, force=True)
        _run_step("step16", step16.shap_interpretation,    results, force=True)
        _run_step("step17", step17.segmentation,           results, force=True)
        _jobs[job_id]["status"] = "DONE"

    except StopIteration as failed_step:
        _jobs[job_id]["status"] = f"FAILED_AT_{failed_step}"

    except Exception as exc:
        _jobs[job_id]["status"] = "ERROR"
        _jobs[job_id]["error"]  = str(exc)


def _run_fast(job_id: str):
    """
    빠른 실행 — 새 데이터 유입 시.

    흐름: 01(데이터 검증) → 03(코호트) → 06(데이터셋 생성)
          → 15/scoring(저장된 모델로 점수만 계산, 재학습 없음)
          → 17(세그먼트 재배정)

    모델(step11·12·14)은 캐시 사용. 6개월 경과 시 run-full로 재학습.
    """
    _jobs[job_id] = {"status": "RUNNING", "results": {}}
    results = _jobs[job_id]["results"]

    try:
        _run_step("step01", step01.data_contract,      results, force=True)
        _run_step("step03", step03.observation_window, results, force=True)
        _run_step("step06", step06.dataset_generation, results, force=True)
        _run_step("step15_scoring", step15.scoring,    results, force=True)
        _run_step("step17", step17.segmentation,       results, force=True)
        _jobs[job_id]["status"] = "DONE"

    except StopIteration as failed_step:
        _jobs[job_id]["status"] = f"FAILED_AT_{failed_step}"

    except Exception as exc:
        _jobs[job_id]["status"] = "ERROR"
        _jobs[job_id]["error"]  = str(exc)


# ── 파이프라인 관리 엔드포인트 ──────────────────────────────────────────────────

@app.get("/pipeline/status", tags=["Pipeline"])
def pipeline_status():
    """완료된 단계, 캐시 파일, 재학습 필요 여부 확인."""
    state = load_state()
    return {
        "completed_steps": list(state.keys()),
        "needs_retrain":   needs_retrain(),
        "cache_files":     list_cache(),
        "step_details":    state,
    }


@app.get("/pipeline/job/{job_id}", tags=["Pipeline"])
def pipeline_job_status(job_id: str):
    """비동기 파이프라인 잡 상태 조회."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return _jobs[job_id]


@app.get("/pipeline/jobs", tags=["Pipeline"])
def pipeline_all_jobs():
    """현재 서버에 등록된 모든 잡 목록."""
    return _jobs


@app.post(
    "/pipeline/reset",
    tags=["Pipeline"],
    dependencies=[Depends(verify_api_key)],
)
def pipeline_reset():
    """캐시·상태 전체 초기화."""
    reset_pipeline()
    return {"status": "OK", "message": "초기화 완료. 다음 run-full이 처음부터 실행됩니다."}


@app.post(
    "/pipeline/run-full",
    tags=["Pipeline"],
    dependencies=[Depends(verify_api_key)],
)
def pipeline_run_full(background_tasks: BackgroundTasks):
    """
    전체 파이프라인 비동기 실행 (최초 또는 6개월 재학습).

    - 즉시 job_id를 반환하고 백그라운드에서 실행.
    - GET /pipeline/job/{job_id} 로 진행 상황 확인.
    - Step 11·12·14는 수십 분 소요될 수 있음.
    """
    job_id = str(uuid.uuid4())[:8]
    _jobs[job_id] = {"status": "QUEUED"}
    background_tasks.add_task(_run_full, job_id)
    return {
        "job_id":    job_id,
        "status":    "QUEUED",
        "check_url": f"/pipeline/job/{job_id}",
        "message":   "파이프라인이 백그라운드에서 실행됩니다.",
    }


@app.post(
    "/pipeline/run-fast",
    tags=["Pipeline"],
    dependencies=[Depends(verify_api_key)],
)
def pipeline_run_fast(background_tasks: BackgroundTasks):
    """
    빠른 실행 (새 데이터 유입 시).

    흐름: 01 → 03 → 06 → 15/scoring → 17

    - 데이터 검증·코호트·데이터셋 생성 후 저장된 모델로 점수만 계산.
    - 모델 재학습(Step 11·12·14) 없음 — 캐시 사용.
    - 6개월 경과 시 /pipeline/run-full 로 전체 재학습 필요.
    - 즉시 job_id 반환 후 백그라운드 실행.
    """
    job_id = str(uuid.uuid4())[:8]
    _jobs[job_id] = {"status": "QUEUED"}
    background_tasks.add_task(_run_fast, job_id)
    return {
        "job_id":    job_id,
        "status":    "QUEUED",
        "check_url": f"/pipeline/job/{job_id}",
        "message":   "빠른 실행이 백그라운드에서 시작됩니다. 모델(14단계)은 캐시 사용.",
    }


@app.get("/", tags=["Health"])
def root():
    return {
        "message": "OTT 이탈 방지 파이프라인 서버 실행 중",
        "docs":    "/docs",
        "steps":   "01→03→06→08→09→10→11→12→14→15→16→17",
    }
