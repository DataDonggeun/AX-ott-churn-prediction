"""
파이프라인 결과 보고서 생성 모듈

GET /pipeline/report       → HTML 보고서 (브라우저에서 바로 확인)
GET /pipeline/report/json  → JSON 원본 데이터
"""
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, FileResponse

from cache import load_json, load_state, list_cache

router = APIRouter(prefix="/pipeline", tags=["Pipeline"])


def _fmt(v, suffix="") -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.4f}{suffix}"
    return f"{v}{suffix}"


def _auc_bar(auc: float) -> str:
    """AUC 값을 시각적 바로 표현"""
    if auc is None:
        return "—"
    pct = int((auc - 0.5) / 0.5 * 100)
    pct = max(0, min(100, pct))
    color = "#2ecc71" if auc >= 0.80 else "#f39c12" if auc >= 0.75 else "#e74c3c"
    return (
        f'<div style="display:flex;align-items:center;gap:8px;">'
        f'<div style="background:{color};width:{pct}%;height:14px;border-radius:4px;min-width:4px;"></div>'
        f'<span style="font-weight:600;color:{color}">{auc:.4f}</span>'
        f'</div>'
    )


def build_report() -> dict:
    """모든 캐시 JSON을 읽어 보고서 데이터 구조 반환"""
    state       = load_state()
    step05_oof  = load_json("step05_oof")
    step05_meta = load_json("step05_meta")
    test_score  = load_json("test_score")
    step06      = load_json("step06_shap_global")
    step07      = load_json("step07_segment_summary")
    cache_files = list_cache()

    completed = sorted(state.keys())
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "completed_steps": completed,
        "state": state,
        "step05_oof":  step05_oof,
        "step05_meta": step05_meta,
        "test_score":  test_score,
        "step06": step06,
        "step07": step07,
        "cache_files": cache_files,
    }


def render_html(data: dict) -> str:
    state       = data["state"]
    step05_oof  = data.get("step05_oof")
    step05_meta = data.get("step05_meta")
    test_score  = data.get("test_score")
    step06      = data.get("step06")
    step07      = data.get("step07")
    gen_at     = data["generated_at"]
    completed  = data["completed_steps"]

    # ── 스타일 ───────────────────────────────────────────────────────────────────
    css = """
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Segoe UI', system-ui, sans-serif; background: #f0f2f5; color: #2c3e50; }
    .page { max-width: 1100px; margin: 0 auto; padding: 32px 16px; }
    h1 { font-size: 1.8rem; font-weight: 700; color: #1a252f; margin-bottom: 4px; }
    .subtitle { color: #7f8c8d; font-size: 0.9rem; margin-bottom: 32px; }
    .card { background: #fff; border-radius: 12px; padding: 24px; margin-bottom: 24px;
            box-shadow: 0 1px 4px rgba(0,0,0,.08); }
    .card h2 { font-size: 1.1rem; font-weight: 700; color: #2c3e50; margin-bottom: 16px;
               padding-bottom: 8px; border-bottom: 2px solid #ecf0f1; }
    table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
    th { background: #f8f9fa; padding: 10px 12px; text-align: left; color: #555;
         font-weight: 600; border-bottom: 2px solid #dee2e6; }
    td { padding: 9px 12px; border-bottom: 1px solid #f0f0f0; }
    tr:hover td { background: #f8f9fa; }
    .badge { display:inline-block; padding:3px 10px; border-radius:20px; font-size:0.78rem; font-weight:600; }
    .badge-pass { background:#d5f5e3; color:#1e8449; }
    .badge-done { background:#d6eaf8; color:#1a5276; }
    .badge-none { background:#fdfefe; color:#aaa; border:1px solid #eee; }
    .kpi-row { display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 0; }
    .kpi { flex: 1; min-width: 160px; background: #f8f9fa; border-radius: 10px;
           padding: 16px; text-align: center; }
    .kpi-val { font-size: 1.6rem; font-weight: 700; color: #2980b9; }
    .kpi-label { font-size: 0.8rem; color: #7f8c8d; margin-top: 4px; }
    .note { font-size: 0.82rem; color: #95a5a6; margin-top: 10px; }
    .seg-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 12px; }
    .seg-card { border-radius: 10px; padding: 16px; text-align: center; }
    .seg-label { font-size: 1.3rem; font-weight: 800; }
    .seg-count { font-size: 1.1rem; font-weight: 600; margin: 4px 0; }
    .seg-risk  { font-size: 0.85rem; color: #555; }
    .A1,.A2,.A3 { background: #d5f5e3; }
    .B1,.B2,.B3 { background: #fdebd0; }
    """

    # ── 완료 단계 배지 ────────────────────────────────────────────────────────────
    all_steps = ["step00","step01","step02","step03","step04",
                 "step05_tune","step05_oof","step05_meta","step05_score","step05_test",
                 "step06","step07"]
    badges = ""
    for s in all_steps:
        if s in completed:
            badges += f'<span class="badge badge-done">{s} ✓</span> '
        else:
            badges += f'<span class="badge badge-none">{s}</span> '

    # ── Section 1: Step 05 스태킹 OOF 결과 ──────────────────────────────────────
    sec05_oof = ""
    if step05_oof and "by_scope" in step05_oof:
        rows_html = ""
        for scope_name, models in step05_oof["by_scope"].items():
            for model_name, info in models.items():
                auc   = info.get("oof_auc")
                gap   = info.get("gap", 0) or 0
                gap_color = "#e74c3c" if abs(gap) > 0.05 else "#2ecc71"
                overfit_flag = "⚠️" if info.get("overfit") else "✅"
                rows_html += (
                    f"<tr><td>{scope_name}</td><td>{model_name}</td>"
                    f"<td>{_auc_bar(auc)}</td>"
                    f"<td style='color:{gap_color}'>{_fmt(gap)}</td>"
                    f"<td>{overfit_flag}</td></tr>"
                )
        sec05_oof = f"""
        <div class="card">
          <h2>📊 Step 05 — 스태킹 OOF 결과 (5개 Base Learner)</h2>
          <table>
            <tr><th>Scope</th><th>모델</th><th>OOF AUC</th><th>Gap</th><th>과적합</th></tr>
            {rows_html}
          </table>
        </div>
        """

    # ── Section 2: Step 05 Meta 채택 결과 ────────────────────────────────────────
    sec05_meta = ""
    if step05_meta and "by_scope" in step05_meta:
        rows_html = ""
        for scope_name, info in step05_meta["by_scope"].items():
            adopted = info.get("adopted", False)
            adopted_label = '<span style="color:#1e8449;font-weight:600">채택 ✅</span>' if adopted else '<span style="color:#e74c3c;font-weight:600">미채택 ❌</span>'
            fallback = info.get("fallback") or "—"
            rows_html += (
                f"<tr><td>{scope_name}</td>"
                f"<td>{_auc_bar(info.get('meta_auc'))}</td>"
                f"<td>{_auc_bar(info.get('best_base_auc'))}</td>"
                f"<td>{adopted_label}</td>"
                f"<td>{fallback}</td></tr>"
            )
        sec05_meta = f"""
        <div class="card">
          <h2>🏆 Step 05 — Meta LR 채택 결과</h2>
          <table>
            <tr><th>Scope</th><th>Meta AUC</th><th>Best Base AUC</th><th>채택 여부</th><th>Fallback</th></tr>
            {rows_html}
          </table>
          <p class="note">채택 조건: meta_auc ≥ best_base_auc AND meta_gap ≤ 0.05 / 미채택 시 CatBoost fallback</p>
        </div>
        """

    # ── Section 2-1: Test AUC 결과 ───────────────────────────────────────────────
    sec_test = ""
    if test_score and "by_scope" in test_score:
        rows_html = ""
        for r in test_score["by_scope"]:
            test_auc = r.get("test_auc")
            oof_auc  = r.get("oof_auc")
            delta    = r.get("delta")
            delta_color = "#2ecc71" if (delta or 0) >= 0 else "#e74c3c"
            delta_str   = f'<span style="color:{delta_color};font-weight:600">{delta:+.4f}</span>' if delta is not None else "—"
            rows_html += (
                f"<tr><td>{r['scope']}</td>"
                f"<td>{r.get('final_model','—')}</td>"
                f"<td>{_auc_bar(oof_auc)}</td>"
                f"<td>{_auc_bar(test_auc)}</td>"
                f"<td>{delta_str}</td>"
                f"<td>{r['test_rows']:,}</td></tr>" if isinstance(r.get('test_rows'), int) else f"<td>—</td></tr>"
            )
        sec_test = f"""
        <div class="card">
          <h2>🧪 Test 성능 (OOF vs Test AUC 비교)</h2>
          <table>
            <tr><th>Scope</th><th>최종 모델</th><th>OOF AUC</th><th>Test AUC</th><th>Δ(test-OOF)</th><th>test 행 수</th></tr>
            {rows_html}
          </table>
          <p class="note">⚠️ test set은 1회 평가 완료. Δ > 0: 일반화 양호 / Δ &lt; 0: 과적합 의심</p>
        </div>
        """

    # ── Section 3: Step 06 SHAP Top 20 ───────────────────────────────────────────
    sec06_shap = ""
    if step06 and "by_scope" in step06:
        scope_key = "overall"
        shap_data = step06["by_scope"].get(scope_key, {}).get("shap", {})
        top20 = shap_data.get("top20", [])

        if top20:
            rows_html = ""
            max_val = top20[0]["mean_abs_shap"] if top20 else 1
            for i, r in enumerate(top20[:20], 1):
                val = r.get("mean_abs_shap", 0)
                bar_w = int(val / max_val * 120)
                fam_color = {
                    "usage_retention_behavior": "#2980b9",
                    "content_preference":       "#8e44ad",
                    "membership_context":       "#16a085",
                    "acquisition_split":        "#e67e22",
                    "payment_proxy":            "#e74c3c",
                }.get(r.get("family",""), "#95a5a6")
                rows_html += (
                    f"<tr>"
                    f"<td style='color:#999'>{i}</td>"
                    f"<td style='font-weight:600'>{r['feature']}</td>"
                    f"<td><div style='background:{fam_color};color:#fff;padding:2px 8px;"
                    f"border-radius:4px;font-size:0.78rem;display:inline-block'>"
                    f"{r.get('family','other')}</div></td>"
                    f"<td><div style='background:#3498db;height:12px;width:{bar_w}px;"
                    f"border-radius:3px;display:inline-block'></div> "
                    f"{val:.5f}</td>"
                    f"</tr>"
                )

            fam_sum = shap_data.get("family_sum", {})
            fam_html = ""
            for fam, val in fam_sum.items():
                fam_html += (
                    f"<tr><td>{fam}</td>"
                    f"<td>{val:.5f}</td></tr>"
                )

            sec06_shap = f"""
            <div class="card">
              <h2>🔎 Step 06 — SHAP 피처 중요도 Top 20 <small style="font-weight:400;color:#999">(scope: overall)</small></h2>
              <div style="display:grid;grid-template-columns:2fr 1fr;gap:20px;">
                <table>
                  <tr><th>#</th><th>피처</th><th>계열</th><th>Mean |SHAP|</th></tr>
                  {rows_html}
                </table>
                <div>
                  <b style="font-size:0.9rem">계열별 합계</b>
                  <table style="margin-top:8px">
                    <tr><th>계열</th><th>합계 SHAP</th></tr>
                    {fam_html}
                  </table>
                  <p class="note" style="margin-top:8px">⚠️ SHAP은 모델 설명이며 인과 주장이 아님</p>
                </div>
              </div>
            </div>
            """

    # ── Section 4: Step 07 세그멘테이션 ──────────────────────────────────────────
    sec07_seg = ""
    if step07 and "segments" in step07:
        segs = step07["segments"]
        seg_cards = ""
        total = step07.get("total_rows", 1)
        for seg in segs:
            pct  = round(seg.get("row_share", 0) * 100, 1)
            risk = seg.get("mean_churn_risk")
            rr   = seg.get("repurchase_rate")
            seg_name = seg["segment"]
            seg_cards += f"""
            <div class="seg-card {seg_name}">
              <div class="seg-label">{seg_name}</div>
              <div class="seg-count">{seg['row_count']:,}명 ({pct}%)</div>
              <div class="seg-risk">재구매율 {_fmt(rr)}</div>
              <div class="seg-risk">이탈 위험 {_fmt(risk)}</div>
            </div>
            """

        # 개입 타이밍
        ei = step07.get("early_intervention", {})
        ei_html = ""
        for day, info in ei.items():
            note = info.get("note", "")
            thr  = (info.get("threshold_w1", "") or
                    info.get("threshold_w1w2", "") or
                    info.get("threshold_w3", ""))
            n_needed = info.get("개입필요", "")
            ei_html += (
                f"<tr><td><b>{day}</b></td>"
                f"<td>threshold = {_fmt(thr)}분</td>"
                f"<td>{n_needed:,}명 개입필요" if n_needed != "" else f"<td>{note}</td>"
            )
            ei_html += "</td></tr>"

        sec07_seg = f"""
        <div class="card">
          <h2>👥 Step 07 — 세그먼테이션 결과 (A1~B3)</h2>
          <p style="font-size:0.85rem;color:#555;margin-bottom:16px">
            {step07.get('note','기준: w1+w2 중앙값 × w3 75th percentile')}
          </p>
          <div class="seg-grid">{seg_cards}</div>
          <br>
          <b>📅 조기 개입 타이밍</b>
          <table style="margin-top:8px">
            <tr><th>시점</th><th>기준</th><th>현황</th></tr>
            {ei_html}
          </table>
          <p class="note" style="margin-top:8px">
            🎯 CRM 우선 타겟: A3(상위 3주차 無), B3(하위 3주차 無) — 이탈률 최고
          </p>
        </div>
        """

    # ── KPI 카드 ─────────────────────────────────────────────────────────────────
    best_auc = "—"
    if step05_meta and "by_scope" in step05_meta:
        aucs = [v.get("meta_auc") or v.get("best_base_auc")
                for v in step05_meta["by_scope"].values()
                if v.get("meta_auc") or v.get("best_base_auc")]
        if aucs:
            best_auc = f"{max(a for a in aucs if a):.4f}"

    total_rows = "—"
    if step07:
        total_rows = f"{step07.get('total_rows', 0):,}"

    n_segs = "—"
    if step07 and "segments" in step07:
        n_segs = str(len(step07["segments"]))

    n_steps = str(len(data["completed_steps"]))

    kpi_html = f"""
    <div class="kpi-row">
      <div class="kpi"><div class="kpi-val">{n_steps}/11</div><div class="kpi-label">완료된 단계</div></div>
      <div class="kpi"><div class="kpi-val">{total_rows}</div><div class="kpi-label">총 유저 수</div></div>
      <div class="kpi"><div class="kpi-val">{best_auc}</div><div class="kpi-label">최고 Tuned AUC</div></div>
      <div class="kpi"><div class="kpi-val">{n_segs}</div><div class="kpi-label">세그먼트 수</div></div>
    </div>
    """

    # ── 완료 상태 ─────────────────────────────────────────────────────────────────
    status_rows = ""
    for s in all_steps:
        if s in state:
            ts = state[s].get("completed_at", "")[:19]
            status_rows += (
                f"<tr><td>{s}</td>"
                f'<td><span class="badge badge-done">완료</span></td>'
                f"<td>{ts}</td></tr>"
            )
        else:
            status_rows += (
                f"<tr><td>{s}</td>"
                f'<td><span class="badge badge-none">미실행</span></td>'
                f"<td>—</td></tr>"
            )

    status_card = f"""
    <div class="card">
      <h2>📋 파이프라인 실행 현황</h2>
      <table>
        <tr><th>단계</th><th>상태</th><th>완료 시각</th></tr>
        {status_rows}
      </table>
    </div>
    """

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>OTT 이탈 방지 파이프라인 — 결과 보고서</title>
  <style>{css}</style>
</head>
<body>
<div class="page">
  <h1>📊 OTT 이탈 방지 파이프라인</h1>
  <p class="subtitle">결과 보고서 · 생성 시각: {gen_at}</p>

  <div class="card">
    <h2>🚦 전체 요약</h2>
    {kpi_html}
    <div style="margin-top:16px">{badges}</div>
  </div>

  {sec05_oof}
  {sec05_meta}
  {sec_test}
  {sec06_shap}
  {sec07_seg}
  {status_card}

  <p class="note" style="text-align:center;padding:16px">
    OTT 이탈 방지 파이프라인 v3.0 · 파이프라인 실행 후 <b>/pipeline/report</b> 새로고침
  </p>
</div>
</body>
</html>"""
    return html


@router.get("/report", response_class=HTMLResponse, tags=["Pipeline"])
def pipeline_report():
    """전체 파이프라인 결과 HTML 보고서. 브라우저에서 바로 확인 가능."""
    data = build_report()
    return HTMLResponse(content=render_html(data))


@router.get("/report/json", tags=["Pipeline"])
def pipeline_report_json():
    """전체 파이프라인 결과 JSON (raw)."""
    return build_report()


# ── AI 생성 보고서 저장/조회 ───────────────────────────────────────────────────

_CACHE_DIR = Path(__file__).parent / "cache"
_AI_REPORT_PATH = _CACHE_DIR / "ai_report.html"

_REPORT_META = {
    "crm": {
        "path":     _CACHE_DIR / "ai_report_crm.html",
        "title":    "OTT 이탈 방지 — 고객관리팀 보고서",
        "footer":   "신통방통팀 | OTT 이탈 방지 파이프라인 | 고객관리팀 보고서",
        "filename": "OTT_고객관리팀_보고서.html",
    },
    "dev": {
        "path":     _CACHE_DIR / "ai_report_dev.html",
        "title":    "OTT 이탈 방지 — 개발자 보고서",
        "footer":   "신통방통팀 | OTT 이탈 방지 파이프라인 | 개발자 보고서",
        "filename": "OTT_개발자_보고서.html",
    },
    "ceo": {
        "path":     _CACHE_DIR / "ai_report_ceo.html",
        "title":    "OTT 이탈 방지 — 경영진 보고서",
        "footer":   "신통방통팀 | OTT 이탈 방지 파이프라인 | 경영진 보고서",
        "filename": "OTT_경영진_보고서.html",
    },
}

_BASE_STYLE = """
  body { font-family: 'Segoe UI', sans-serif; max-width: 1100px; margin: 40px auto; padding: 0 20px; color: #333; line-height: 1.7; }
  h1 { color: #1a1a2e; border-bottom: 3px solid #1a1a2e; padding-bottom: 10px; }
  h2 { color: #16213e; margin-top: 40px; border-left: 4px solid #2980b9; padding-left: 12px; }
  h3 { color: #444; }
  table { width: 100%; border-collapse: collapse; margin: 16px 0; }
  th { background: #1a1a2e; color: white; padding: 10px 14px; text-align: left; }
  td { padding: 9px 14px; border-bottom: 1px solid #e0e0e0; }
  tr:nth-child(even) { background: #f8f9fa; }
  hr { border: none; border-top: 1px solid #e0e0e0; margin: 30px 0; }
  .danger { color: #e74c3c; font-weight: bold; }
  .footer { text-align: center; color: #aaa; font-size: 0.85rem; margin-top: 40px; }
"""


def _wrap_html(content: str, title: str, footer: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>{_BASE_STYLE}</style>
</head>
<body>
{content}
<div class="footer">{footer}</div>
</body>
</html>"""


async def _save_report_by_type(request: Request, report_type: str):
    meta = _REPORT_META[report_type]
    html_content = (await request.body()).decode("utf-8")
    if not html_content:
        return {"status": "FAIL", "reason": "html이 비어있음"}
    meta["path"].write_text(
        _wrap_html(html_content, meta["title"], meta["footer"]),
        encoding="utf-8",
    )
    return {"status": "OK", "url": f"/pipeline/report/ai-html/{report_type}"}


def _get_report_by_type(report_type: str):
    meta = _REPORT_META[report_type]
    if not meta["path"].exists():
        return HTMLResponse(content="<h2>보고서가 아직 생성되지 않았습니다.</h2>")
    return HTMLResponse(content=meta["path"].read_text(encoding="utf-8"))


def _download_report_by_type(report_type: str):
    meta = _REPORT_META[report_type]
    if not meta["path"].exists():
        return {"status": "FAIL", "reason": "보고서가 아직 생성되지 않았습니다."}
    return FileResponse(
        path=meta["path"],
        filename=meta["filename"],
        media_type="text/html",
    )


# ── 기존 단일 보고서 (하위 호환) ──────────────────────────────────────────────

@router.post("/report/save-html", tags=["Pipeline"])
async def save_ai_report(request: Request):
    """Dify LLM이 생성한 HTML 보고서를 저장. Body: raw text (HTML 전체)"""
    html_content = (await request.body()).decode("utf-8")
    if not html_content:
        return {"status": "FAIL", "reason": "html 필드가 비어있음"}
    _AI_REPORT_PATH.write_text(
        _wrap_html(html_content, "OTT 이탈 방지 분석 보고서", "신통방통팀 | OTT 이탈 방지 파이프라인 | AI 생성 보고서"),
        encoding="utf-8",
    )
    return {"status": "OK", "url": "/pipeline/report/ai-html"}


@router.get("/report/ai-html", response_class=HTMLResponse, tags=["Pipeline"])
def get_ai_report():
    """Dify AI가 생성한 최신 보고서 조회."""
    if not _AI_REPORT_PATH.exists():
        return HTMLResponse(content="<h2>보고서가 아직 생성되지 않았습니다. 워크플로우를 먼저 실행해주세요.</h2>")
    return HTMLResponse(content=_AI_REPORT_PATH.read_text(encoding="utf-8"))


@router.get("/report/download", tags=["Pipeline"])
def download_ai_report():
    """Dify AI가 생성한 최신 보고서 다운로드."""
    if not _AI_REPORT_PATH.exists():
        return {"status": "FAIL", "reason": "보고서가 아직 생성되지 않았습니다."}
    return FileResponse(
        path=_AI_REPORT_PATH,
        filename="OTT_이탈방지_분석보고서.html",
        media_type="text/html",
    )


# ── 고객관리팀 보고서 ──────────────────────────────────────────────────────────

@router.post("/report/save-html/crm", tags=["Pipeline"])
async def save_crm_report(request: Request):
    """고객관리팀 보고서 저장. Body: raw HTML"""
    return await _save_report_by_type(request, "crm")

@router.get("/report/ai-html/crm", response_class=HTMLResponse, tags=["Pipeline"])
def get_crm_report():
    """고객관리팀 보고서 조회."""
    return _get_report_by_type("crm")

@router.get("/report/download/crm", tags=["Pipeline"])
def download_crm_report():
    """고객관리팀 보고서 다운로드."""
    return _download_report_by_type("crm")


# ── 개발자 보고서 ─────────────────────────────────────────────────────────────

@router.post("/report/save-html/dev", tags=["Pipeline"])
async def save_dev_report(request: Request):
    """개발자 보고서 저장. Body: raw HTML"""
    return await _save_report_by_type(request, "dev")

@router.get("/report/ai-html/dev", response_class=HTMLResponse, tags=["Pipeline"])
def get_dev_report():
    """개발자 보고서 조회."""
    return _get_report_by_type("dev")

@router.get("/report/download/dev", tags=["Pipeline"])
def download_dev_report():
    """개발자 보고서 다운로드."""
    return _download_report_by_type("dev")


# ── 경영진 보고서 ─────────────────────────────────────────────────────────────

@router.post("/report/save-html/ceo", tags=["Pipeline"])
async def save_ceo_report(request: Request):
    """경영진 보고서 저장. Body: raw HTML"""
    return await _save_report_by_type(request, "ceo")

@router.get("/report/ai-html/ceo", response_class=HTMLResponse, tags=["Pipeline"])
def get_ceo_report():
    """경영진 보고서 조회."""
    return _get_report_by_type("ceo")

@router.get("/report/download/ceo", tags=["Pipeline"])
def download_ceo_report():
    """경영진 보고서 다운로드."""
    return _download_report_by_type("ceo")
