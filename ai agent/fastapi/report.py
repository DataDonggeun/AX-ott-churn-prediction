"""
파이프라인 결과 보고서 생성 모듈

GET /pipeline/report       → HTML 보고서 (브라우저에서 바로 확인)
GET /pipeline/report/json  → JSON 원본 데이터
"""
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

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
    step04      = load_json("step04_result")
    step06      = load_json("step06_result")
    step07      = load_json("step07_result")
    step08      = load_json("step08_result")
    step09      = load_json("step09_shap_global")
    step10      = load_json("step10_segment_summary")
    cache_files = list_cache()

    completed = sorted(state.keys())
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "completed_steps": completed,
        "state": state,
        "step04": step04,
        "step06": step06,
        "step07": step07,
        "step08": step08,
        "step09": step09,
        "step10": step10,
        "cache_files": cache_files,
    }


def render_html(data: dict) -> str:
    state     = data["state"]
    step04    = data.get("step04")
    step06    = data.get("step06")
    step07    = data.get("step07")
    step08    = data.get("step08")
    step09    = data.get("step09")
    step10    = data.get("step10")
    gen_at    = data["generated_at"]
    completed = data["completed_steps"]

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
    .S1,.S2,.S3 { background: #d5f5e3; }
    .S4,.S5,.S6 { background: #fdebd0; }
    """

    # ── 완료 단계 배지 ────────────────────────────────────────────────────────────
    all_steps = ["step00","step01","step02","step03","step04",
                 "step05","step06","step07","step08","step09","step10"]
    badges = ""
    for s in all_steps:
        if s in completed:
            badges += f'<span class="badge badge-done">{s} ✓</span> '
        else:
            badges += f'<span class="badge badge-none">{s}</span> '

    # ── Section 1: Step 04 모델 선정 ─────────────────────────────────────────────
    sec04 = ""
    if step04 and "summary" in step04:
        rows_html = ""
        for r in step04["summary"]:
            auc_html = _auc_bar(r.get("oof_auc"))
            gap = r.get("train_valid_gap", 0) or 0
            gap_color = "#e74c3c" if abs(gap) > 0.03 else "#2ecc71"
            rows_html += (
                f"<tr><td>{r['scope']}</td><td>{r['model']}</td>"
                f"<td>{auc_html}</td>"
                f"<td style='color:{gap_color}'>{_fmt(r.get('train_valid_gap'))}</td>"
                f"<td>{_fmt(r.get('fold_auc_std'))}</td></tr>"
            )

        cands = step04.get("candidates", {})
        cand_html = ""
        for sc, info in cands.items():
            cand_html += (
                f"<tr><td>{sc}</td>"
                f"<td><b>{info.get('model','—')}</b></td>"
                f"<td>{_auc_bar(info.get('oof_auc'))}</td></tr>"
            )

        sec04 = f"""
        <div class="card">
          <h2>🏆 Step 04 — 모델 선정 (3개 모델 비교)</h2>
          <table>
            <tr><th>Scope</th><th>모델</th><th>OOF AUC</th><th>Train-Val Gap</th><th>Fold Std</th></tr>
            {rows_html}
          </table>
          <br>
          <b>🎯 Scope별 우승 모델 (→ Step 06 입력)</b>
          <table style="margin-top:8px">
            <tr><th>Scope</th><th>우승 모델</th><th>OOF AUC</th></tr>
            {cand_html}
          </table>
        </div>
        """

    # ── Section 2: Step 06 모델 패밀리 비교 ──────────────────────────────────────
    sec06 = ""
    if step06 and "summary" in step06:
        rows_html = ""
        for r in step06["summary"]:
            auc_html = _auc_bar(r.get("oof_auc"))
            rows_html += (
                f"<tr><td>{r['scope']}</td><td>{r['model']}</td>"
                f"<td>{r.get('family','—')}</td>"
                f"<td>{auc_html}</td>"
                f"<td>{_fmt(r.get('fold_auc_std'))}</td></tr>"
            )

        cands = step06.get("candidates", {})
        cand_html = ""
        for sc, info in cands.items():
            cand_html += (
                f"<tr><td>{sc}</td>"
                f"<td><b>{info.get('model','—')}</b></td>"
                f"<td>{_auc_bar(info.get('oof_auc'))}</td></tr>"
            )

        sec06 = f"""
        <div class="card">
          <h2>🔬 Step 06 — 모델 패밀리 비교</h2>
          <table>
            <tr><th>Scope</th><th>모델</th><th>계열</th><th>OOF AUC</th><th>Fold Std</th></tr>
            {rows_html}
          </table>
          <br>
          <b>🎯 Scope별 Optuna 튜닝 후보 (→ Step 07 입력)</b>
          <table style="margin-top:8px">
            <tr><th>Scope</th><th>후보 모델</th><th>OOF AUC</th></tr>
            {cand_html}
          </table>
        </div>
        """

    # ── Section 3: Step 07 Optuna 튜닝 결과 ──────────────────────────────────────
    sec07 = ""
    if step07 and "by_scope" in step07:
        rows_html = ""
        for sc, info in step07["by_scope"].items():
            tuned = info.get("tuned_auc")
            base  = info.get("baseline_auc")
            delta = info.get("delta_auc")
            delta_color = "#2ecc71" if (delta or 0) >= 0 else "#e74c3c"
            rows_html += (
                f"<tr><td>{sc}</td><td>{info.get('model','—')}</td>"
                f"<td>{_auc_bar(base)}</td>"
                f"<td>{_auc_bar(tuned)}</td>"
                f"<td style='color:{delta_color};font-weight:600'>{_fmt(delta)}</td>"
                f"<td>{info.get('n_trials','—')}</td></tr>"
            )
        sec07 = f"""
        <div class="card">
          <h2>⚡ Step 07 — Optuna 튜닝 결과</h2>
          <table>
            <tr><th>Scope</th><th>모델</th><th>Baseline AUC</th><th>Tuned AUC</th><th>Δ AUC</th><th>Trials</th></tr>
            {rows_html}
          </table>
          <p class="note">✅ 튜닝된 모델은 cache/tuned_model_{{scope}}.pkl로 저장됨</p>
        </div>
        """

    # ── Section 4: Step 08 Scoring ────────────────────────────────────────────────
    sec08 = ""
    if step08 and "by_scope" in step08:
        rows_html = ""
        for r in step08["by_scope"]:
            rows_html += (
                f"<tr><td>{r['scope']}</td>"
                f"<td>{_auc_bar(r.get('oof_auc'))}</td>"
                f"<td>{r.get('rows', '—'):,}</td></tr>"
            )
        sec08 = f"""
        <div class="card">
          <h2>🎯 Step 08 — OOF 예측 점수</h2>
          <table>
            <tr><th>Scope</th><th>OOF AUC</th><th>행 수</th></tr>
            {rows_html}
          </table>
          <p class="note">→ step08_oof.csv 저장 완료. Step 10 세그멘테이션에 사용됨.</p>
        </div>
        """

    # ── Section 5: Step 09 SHAP Top 20 ───────────────────────────────────────────
    sec09 = ""
    if step09 and "by_scope" in step09:
        scope_key = "overall_with_promotion"
        shap_data = step09["by_scope"].get(scope_key, {}).get("shap", {})
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

            sec09 = f"""
            <div class="card">
              <h2>🔎 Step 09 — SHAP 피처 중요도 Top 20 <small style="font-weight:400;color:#999">(scope: overall_with_promotion)</small></h2>
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

    # ── Section 6: Step 10 세그멘테이션 ──────────────────────────────────────────
    sec10 = ""
    if step10 and "segments" in step10:
        segs = step10["segments"]
        seg_cards = ""
        total = step10.get("total_rows", 1)
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
        ei = step10.get("early_intervention", {})
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

        sec10 = f"""
        <div class="card">
          <h2>👥 Step 10 — 세그먼테이션 결과 (S1~S6)</h2>
          <p style="font-size:0.85rem;color:#555;margin-bottom:16px">
            {step10.get('note','기준: w1+w2 중앙값 × w3 75th percentile')}
          </p>
          <div class="seg-grid">{seg_cards}</div>
          <br>
          <b>📅 조기 개입 타이밍</b>
          <table style="margin-top:8px">
            <tr><th>시점</th><th>기준</th><th>현황</th></tr>
            {ei_html}
          </table>
          <p class="note" style="margin-top:8px">
            🎯 CRM 우선 타겟: S3(상위 3주차 無), S6(하위 3주차 無) — 이탈률 최고
          </p>
        </div>
        """

    # ── KPI 카드 ─────────────────────────────────────────────────────────────────
    best_auc = "—"
    if step07 and "by_scope" in step07:
        aucs = [v.get("tuned_auc") for v in step07["by_scope"].values() if v.get("tuned_auc")]
        if aucs:
            best_auc = f"{max(aucs):.4f}"

    total_rows = "—"
    if step10:
        total_rows = f"{step10.get('total_rows', 0):,}"

    n_segs = "—"
    if step10 and "segments" in step10:
        n_segs = str(len(step10["segments"]))

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

  {sec04}
  {sec06}
  {sec07}
  {sec08}
  {sec09}
  {sec10}
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
