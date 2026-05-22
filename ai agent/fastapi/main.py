"""
OTT 이탈 방지 파이프라인 FastAPI 서버

실행 방법:
    cd "ai agent/fastapi"
    uvicorn main:app --reload --port 8000

운영 방식:
    Full run  (최초 / 6개월 재학습): POST /pipeline/run-full
    Fast run  (새 데이터 유입 시):   POST /pipeline/run-fast
    상태 확인:                        GET  /pipeline/status
    캐시 초기화:                      POST /pipeline/reset

파이프라인 순서 (FastAPI 담당 단계):
    01 → 03 → 06 → 08 → 09 → 10 → 11 → 12 → 14 → 15 → 16 → 17
    (02·04·05·07은 Dify 정책 기록만, 13은 없음)
"""
import sys
import importlib
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import JSONResponse

sys.path.insert(0, str(Path(__file__).parent))

from cache import load_state, list_cache, reset_pipeline, needs_retrain

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
    version="2.0",
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


# ── 파이프라인 관리 ─────────────────────────────────────────────────────────────

@app.get("/pipeline/status", tags=["Pipeline"])
def pipeline_status():
    """완료된 단계, 캐시 파일, 재학습 필요 여부 확인"""
    state = load_state()
    return {
        "completed_steps": list(state.keys()),
        "needs_retrain":   needs_retrain(),
        "cache_files":     list_cache(),
        "step_details":    state,
    }


@app.post("/pipeline/reset", tags=["Pipeline"])
def pipeline_reset():
    """캐시·상태 전체 초기화"""
    reset_pipeline()
    return {"status": "OK", "message": "초기화 완료. 다음 run-full이 처음부터 실행됩니다."}


@app.post("/pipeline/run-full", tags=["Pipeline"])
def pipeline_run_full():
    """
    전체 파이프라인 실행 (최초 또는 6개월 재학습).
    각 단계를 force=True로 캐시 무시하고 재계산.
    주의: Step 11·12·14는 수십 분 소요될 수 있음.
    """
    results = {}

    def run(step_name, fn, *args, **kwargs):
        r = fn(*args, force=True, **kwargs)
        results[step_name] = {
            "status":  r.get("status"),
            "summary": r.get("summary"),
        }
        return r

    # Step 01: 데이터 계약
    r01 = run("step01", step01.data_contract)
    if r01.get("status") == "FAIL":
        return JSONResponse(status_code=422,
            content={"error": "Step 01 FAIL — 파이프라인 중단", "detail": r01})

    # Step 03: 관측창
    run("step03", step03.observation_window)

    # Step 06: 데이터셋 생성 (가장 무거움)
    r06 = run("step06", step06.dataset_generation)
    if r06.get("status") == "FAIL":
        return JSONResponse(status_code=422,
            content={"error": "Step 06 FAIL", "detail": r06})

    # Step 08~10: EDA + 피처 감사
    run("step08", step08.promotion_eda)
    run("step09", step09.eda_2x2)
    run("step10", step10.feature_audit)

    # Step 11~12: 모델 비교 (수 분 소요)
    run("step11", step11.baseline_comparison)
    run("step12", step12.model_family_comparison)

    # Step 14: Optuna 튜닝 (15~30분 소요)
    run("step14", step14.tuning)

    # Step 15~17: 민감도·SHAP·세그멘테이션
    run("step15", step15.payment_sensitivity)
    run("step16", step16.shap_interpretation)
    run("step17", step17.segmentation)

    return {
        "status":  "DONE",
        "message": "전체 파이프라인 완료.",
        "results": results,
    }


@app.post("/pipeline/run-fast", tags=["Pipeline"])
def pipeline_run_fast():
    """
    캐시된 모델로 빠른 실행 (새 데이터 유입 시).
    Step 01·03·06·08·09·17만 재실행하고
    모델(Step 11·12·14)은 캐시 사용.
    """
    results = {}

    def run_cached(step_name, fn, *args, **kwargs):
        r = fn(*args, force=True, **kwargs)
        results[step_name] = {"status": r.get("status"), "summary": r.get("summary")}
        return r

    r01 = run_cached("step01", step01.data_contract)
    if r01.get("status") == "FAIL":
        return JSONResponse(status_code=422,
            content={"error": "데이터 계약 실패", "detail": r01})

    run_cached("step03", step03.observation_window)
    r06 = run_cached("step06", step06.dataset_generation)
    if r06.get("status") == "FAIL":
        return JSONResponse(status_code=422,
            content={"error": "데이터셋 생성 실패", "detail": r06})

    run_cached("step08", step08.promotion_eda)
    run_cached("step09", step09.eda_2x2)
    run_cached("step15", step15.payment_sensitivity)  # OOF 재계산
    run_cached("step17", step17.segmentation)           # 세그먼트 재배정

    return {
        "status":  "DONE",
        "message": "빠른 실행 완료. 모델(14단계)은 캐시 사용.",
        "results": results,
    }


@app.get("/", tags=["Health"])
def root():
    return {
        "message": "OTT 이탈 방지 파이프라인 서버 실행 중",
        "docs":    "/docs",
        "steps":   "01→03→06→08→09→10→11→12→14→15→16→17",
    }
