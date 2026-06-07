"""
OTT 이탈 방지 파이프라인 FastAPI 서버 (스태킹 앙상블 버전)

실행 방법:
    cd "stacking/_data/fastapi"
    uvicorn main:app --reload --port 8000

운영 방식:
    Full run  (최초 / 6개월 재학습): POST /pipeline/run-full
    Fast run  (새 데이터 유입 시):   POST /pipeline/run-fast
    잡 상태 확인:                    GET  /pipeline/job/{job_id}
    전체 상태 확인:                   GET  /pipeline/status
    캐시 초기화:                      POST /pipeline/reset

파이프라인 순서 (run-full):
    00 → 01 → 02 → 03 → 04
    → 05/run-oof (5개 Base Learner OOF 병렬)
    → 05/train-meta (Meta LR 학습, 채택 판정)
    → 05/score (최종 점수 → step05_scores.csv)
    → 06 (SHAP) → 07 (세그먼트)

파이프라인 순서 (run-fast):
    00 → 01 → 05/score-fast (저장 모델로 직접 예측) → 07

변경 이력:
    - (구) step06·step07·step08 제거: 스태킹은 5개 전부 사용, 200 trial best_params 이미 확보
    - (구) step09·step10 → step06(SHAP)·step07(세그먼트)로 번호 정리
    - step05 = 스태킹 앙상블 (tune·run-oof·train-meta·score 4단계)
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
import report as _report_module

# ── 단계별 모듈 로드 ────────────────────────────────────────────────────────────
step00 = importlib.import_module("00_feature_engineering.step00")
step01 = importlib.import_module("01_data_contract.step01")
step02 = importlib.import_module("02_promotion_eda.step02")
step03 = importlib.import_module("03_2x2_eda.step03")
step04 = importlib.import_module("04_feature_audit.step04")
step05 = importlib.import_module("05_stacking.step05")
step06 = importlib.import_module("06_XAI.step06")
step07 = importlib.import_module("07_segmentation.step07")

app = FastAPI(
    title="OTT 이탈 방지 파이프라인 (스태킹 앙상블)",
    description="Step 00~04 → Step 05(스태킹) → Step 06~07 / 캐시 기반 빠른 재실행 지원",
    version="4.0",
)

# ── 라우터 등록 ────────────────────────────────────────────────────────────────
app.include_router(step00.router)
app.include_router(step01.router)
app.include_router(step02.router)
app.include_router(step03.router)
app.include_router(step04.router)
app.include_router(step05.router)
app.include_router(step06.router)
app.include_router(step07.router)
app.include_router(_report_module.router)


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
    """
    전체 파이프라인 백그라운드 실행.

    흐름:
      00 → 01 → 02 → 03 → 04
      → 05/tune → 05/run-oof (~8분) → 05/train-meta → 05/score
      → 05/evaluate-test (test_expanded.csv 없으면 SKIP)
      → 06 (SHAP) → 07 (세그먼트)
    """
    _jobs[job_id] = {"status": "RUNNING", "results": {}}
    results = _jobs[job_id]["results"]

    try:
        _run_step("step00", step00.feature_engineering,    results)
        _run_step("step01", step01.data_contract,          results)
        _run_step("step02", step02.promotion_eda,          results)
        _run_step("step03", step03.eda_2x2,                results)
        _run_step("step04", step04.feature_audit,          results)
        # ── 스태킹 ───────────────────────────────────────────────────────────
        _run_step("step05_tune",  step05.stacking_tune,      results, force=True)   # Optuna 200 trial → 캐시 저장
        _run_step("step05_oof",   step05.stacking_run_oof,   results, force=True)   # 캐시 파라미터로 OOF 생성
        _run_step("step05_meta",  step05.stacking_train_meta, results, force=True)
        _run_step("step05_score", step05.stacking_score,     results, force=True)
        # ── Test 평가 (test_expanded.csv 없으면 스킵, 파이프라인 중단 안 함) ──
        try:
            _run_step("step05_test", step05.stacking_evaluate_test, results)
        except StopIteration:
            results["step05_test"] = {"status": "SKIP", "summary": "test_expanded.csv 없음"}
        # ── 해석 + 세그먼트 ───────────────────────────────────────────────────
        _run_step("step06", step06.shap_interpretation,    results)
        _run_step("step07", step07.segmentation,           results)
        _jobs[job_id]["status"] = "DONE"

    except StopIteration as failed_step:
        _jobs[job_id]["status"] = f"FAILED_AT_{failed_step}"

    except Exception as exc:
        _jobs[job_id]["status"] = "ERROR"
        _jobs[job_id]["error"]  = str(exc)


def _run_fast(job_id: str):
    """
    빠른 실행 — 새 데이터 유입 시.

    흐름: 00(피처생성) → 01(데이터 검증)
          → 05/score-fast(저장된 모델로 직접 예측, 재학습 없음)
          → 07(세그먼트 재배정)

    스태킹 모델(step05)은 캐시 사용. 6개월 경과 시 run-full로 전체 재학습.
    """
    _jobs[job_id] = {"status": "RUNNING", "results": {}}
    results = _jobs[job_id]["results"]

    try:
        _run_step("step00", step00.feature_engineering,     results)
        _run_step("step01", step01.data_contract,           results)
        _run_step("step05_fast", step05.stacking_score_fast, results)
        _run_step("step07", step07.segmentation,            results)
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
    - Step 05/run-oof (5개 모델 OOF 병렬) 가 가장 오래 걸림 (~8분).
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

    흐름: 00 → 01 → 05/score-fast → 07

    - 피처 생성·데이터 검증 후 저장된 스태킹 모델로 점수만 계산.
    - 모델 재학습(Step 05/run-oof) 없음 — 캐시 사용.
    - 6개월 경과 시 /pipeline/run-full 로 전체 재학습 필요.
    """
    job_id = str(uuid.uuid4())[:8]
    _jobs[job_id] = {"status": "QUEUED"}
    background_tasks.add_task(_run_fast, job_id)
    return {
        "job_id":    job_id,
        "status":    "QUEUED",
        "check_url": f"/pipeline/job/{job_id}",
        "message":   "빠른 실행이 백그라운드에서 시작됩니다. 스태킹 모델은 캐시 사용 (05/score-fast).",
    }


@app.get("/", tags=["Health"])
def root():
    return {
        "message": "OTT 이탈 방지 파이프라인 서버 실행 중 (스태킹 앙상블 v4.0)",
        "docs":    "/docs",
        "steps":   "00→01→02→03→04→05(oof→meta→score)→06→07",
    }
