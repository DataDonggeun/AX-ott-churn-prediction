"""
Step 09: SHAP + Permutation Importance 해석

역할: FastAPI
목적: Step 07 튜닝 모델에 대해 SHAP과 Permutation Importance를 계산해
      피처별 중요도를 두 가지 관점에서 비교한다.
      SHAP은 모델 설명이며 인과가 아님.
출력: SHAP 상위 20개, Permutation Importance 상위 20개, 패밀리별 합계
캐시: step09_shap_global.json
"""
import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
import pandas as pd
import numpy as np
from sklearn.base import clone
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import roc_auc_score

from config import RANDOM_STATE, PAYMENT_FEATURES
from cache import is_done, mark_done, save_json, load_json, load_df, load_artifact

router = APIRouter(prefix="/09", tags=["09. SHAP + Permutation Importance"])

FEATURE_FAMILY = {
    "usage_retention_behavior": [
        "watch_time", "watch_session", "retention", "diff_between",
        "only_w", "cold_start", "recency", "gap", "inactive",
        "active_ratio", "watch_per_day", "rewatch", "weekend",
    ],
    "content_preference": [
        "drama", "comedy", "romance", "thriller", "sf", "horror",
        "action", "family", "documentary", "historical", "other",
        "movie", "release", "genre",
    ],
    "membership_context": [
        "is_standard", "is_premium", "is_basic",
        "is_churn_prevented", "is_user_verified",
        "reg_is_weekend", "reg_hour",
        "age_group", "is_female", "is_male",
    ],
    "acquisition_split": ["is_promotion"],
    "payment_proxy":     PAYMENT_FEATURES,
}


def _family_of(feature: str) -> str:
    fn = feature.lower()
    for fam, keywords in FEATURE_FAMILY.items():
        if any(kw in fn for kw in keywords):
            return fam
    return "other"


def run_shap(df_scope: pd.DataFrame, features: list, model) -> dict:
    """SHAP TreeExplainer로 mean absolute SHAP 계산"""
    try:
        import shap
    except ImportError:
        return {"status": "FAIL", "reason": "shap 미설치. pip install shap"}

    X = df_scope[features].apply(pd.to_numeric, errors="coerce").fillna(0)
    y = (1 - df_scope["is_repurchase"].astype(int)).to_numpy()

    # 최대 5000샘플로 제한 (속도)
    if len(X) > 5000:
        idx = np.random.RandomState(RANDOM_STATE).choice(len(X), 5000, replace=False)
        X_sample = X.iloc[idx]
    else:
        X_sample = X

    fitted = clone(model)
    fitted.fit(X, y)

    explainer = shap.TreeExplainer(fitted)
    vals = explainer.shap_values(X_sample)
    if isinstance(vals, list):
        vals = vals[1] if len(vals) > 1 else vals[0]
    vals = np.asarray(vals)
    if vals.ndim == 3:
        vals = vals[:, :, 1] if vals.shape[2] > 1 else vals[:, :, 0]

    mean_abs = np.abs(vals).mean(axis=0)
    importance = pd.DataFrame({
        "feature":        features,
        "mean_abs_shap":  mean_abs,
        "family":         [_family_of(f) for f in features],
    }).sort_values("mean_abs_shap", ascending=False).reset_index(drop=True)

    top20 = importance.head(20).round(6).to_dict("records")

    # 패밀리별 합계
    family_sum = (
        importance.groupby("family")["mean_abs_shap"]
        .sum().sort_values(ascending=False).round(6).to_dict()
    )

    # Beeswarm용 raw SHAP값 (top 20 피처, 최대 1000 샘플)
    top_features = [r["feature"] for r in top20]
    feat_list = list(features)
    top_feat_idx = [feat_list.index(f) for f in top_features if f in feat_list]
    shap_top = vals[:, top_feat_idx]
    X_top = X_sample[top_features].values

    n_bee = min(len(shap_top), 1000)
    bee_idx = np.random.RandomState(RANDOM_STATE).choice(len(shap_top), n_bee, replace=False)
    shap_bee = shap_top[bee_idx]
    X_bee = X_top[bee_idx]
    X_min = X_bee.min(axis=0)
    X_max = X_bee.max(axis=0)
    X_norm = ((X_bee - X_min) / (X_max - X_min + 1e-8)).clip(0, 1)

    beeswarm_data = {
        feat: {
            "shap_values":     shap_bee[:, i].round(5).tolist(),
            "feat_vals_norm":  X_norm[:, i].round(3).tolist(),
        }
        for i, feat in enumerate(top_features)
    }

    return {
        "status":         "PASS",
        "top20":          top20,
        "family_sum":     family_sum,
        "beeswarm_data":  beeswarm_data,
        "beeswarm_n":     n_bee,
        "sample_size":    int(len(X_sample)),
        "note": "SHAP은 모델 설명이며 인과 주장이 아님.",
    }


def run_permutation_importance(df_scope: pd.DataFrame, features: list, model) -> dict:
    """Permutation Importance 계산 — AUC 기반."""
    X = df_scope[features].apply(pd.to_numeric, errors="coerce").fillna(0)
    y = (1 - df_scope["is_repurchase"].astype(int)).to_numpy()

    fitted = clone(model)
    fitted.fit(X, y)

    result = permutation_importance(
        fitted, X, y,
        scoring="roc_auc",
        n_repeats=5,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )

    importance = pd.DataFrame({
        "feature":         features,
        "perm_importance": result.importances_mean,
        "perm_std":        result.importances_std,
        "family":          [_family_of(f) for f in features],
    }).sort_values("perm_importance", ascending=False).reset_index(drop=True)

    top20 = importance.head(20).round(6).to_dict("records")
    family_sum = (
        importance.groupby("family")["perm_importance"]
        .sum().sort_values(ascending=False).round(6).to_dict()
    )

    return {
        "status":     "PASS",
        "top20":      top20,
        "family_sum": family_sum,
        "note": "Permutation Importance: 피처 섞었을 때 AUC 감소량. 클수록 중요.",
    }


def run_shap_all_scopes(exp_df: pd.DataFrame) -> dict:
    scopes = {
        "overall":           (exp_df, True),
        "promotion_only":    (exp_df[exp_df["is_promotion"] == 1].copy(), False),
        "nonpromotion_only": (exp_df[exp_df["is_promotion"] == 0].copy(), False),
    }

    results = {}
    for scope_name, (df_scope, inc_promo) in scopes.items():
        model = load_artifact(f"tuned_model_{scope_name}")
        if model is None:
            model = HistGradientBoostingClassifier(
                max_iter=200, learning_rate=0.05, random_state=RANDOM_STATE
            )

        exclude  = {"USER_KEY", "is_repurchase"} | (set() if inc_promo else {"is_promotion"})
        features = [c for c in exp_df.columns if c not in exclude and c in df_scope.columns]

        results[scope_name] = {
            "shap":        run_shap(df_scope, features, model),
            "permutation": run_permutation_importance(df_scope, features, model),
        }

    return {"status": "PASS", "by_scope": results}


@router.post("/shap")
def shap_interpretation(force: bool = False):
    """Step 09: SHAP + Permutation Importance 피처 중요도 계산. force=false면 캐시 사용."""
    if not force and is_done("step09"):
        cached = load_json("step09_shap_global")
        if cached:
            cached["from_cache"] = True
            return cached

    exp_df = load_df("expanded_dataset")
    if exp_df is None:
        return {"status": "FAIL", "reason": "Step 00 먼저 실행 필요"}

    result = run_shap_all_scopes(exp_df)

    save_json("step09_shap_global", result)
    mark_done("step09", {"scopes": list(result["by_scope"].keys())})

    result["from_cache"] = False
    return result


@router.get("/shap/charts", response_class=HTMLResponse)
def shap_charts():
    """SHAP Beeswarm + Permutation Importance 인터랙티브 차트 (Plotly.js)"""
    cached = load_json("step09_shap_global")
    if not cached or "by_scope" not in cached:
        return HTMLResponse(
            content="<h2 style='font-family:sans-serif;padding:40px'>Step 09를 먼저 실행해주세요."
                    " <a href='/docs'>→ Swagger UI</a></h2>"
        )

    data_json = json.dumps(cached["by_scope"], ensure_ascii=False)

    # HTML을 세 부분으로 나눠 data_json을 안전하게 삽입
    head = """<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SHAP & Permutation Importance 차트</title>
  <script src="https://cdn.plot.ly/plotly-2.26.0.min.js"></script>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:'Segoe UI',sans-serif;background:#f0f2f5;color:#2c3e50}
    .page{max-width:1200px;margin:0 auto;padding:28px 16px}
    h1{font-size:1.6rem;font-weight:700;color:#1a252f;margin-bottom:4px}
    .subtitle{color:#7f8c8d;font-size:.9rem;margin-bottom:20px}
    .tabs{display:flex;gap:8px;margin-bottom:20px;flex-wrap:wrap}
    .tab{padding:8px 20px;border-radius:6px;cursor:pointer;background:#fff;
         border:2px solid #dee2e6;font-size:.88rem;font-weight:600;transition:all .15s}
    .tab:hover{border-color:#2980b9;color:#2980b9}
    .tab.active{background:#2980b9;color:#fff;border-color:#2980b9}
    .card{background:#fff;border-radius:12px;padding:24px;margin-bottom:20px;
          box-shadow:0 1px 4px rgba(0,0,0,.08)}
    .card h2{font-size:1.05rem;font-weight:700;color:#2c3e50;margin-bottom:12px;
             padding-bottom:8px;border-bottom:2px solid #ecf0f1}
    .note{font-size:.8rem;color:#95a5a6;margin-top:10px}
    .warn{background:#fef9c3;border:1px solid #fde68a;color:#92400e;
          padding:10px 16px;border-radius:8px;font-size:.85rem;margin-bottom:12px}
    .legend-row{display:flex;gap:12px;flex-wrap:wrap;margin-top:10px;font-size:.8rem}
    .dot{width:10px;height:10px;border-radius:50%;display:inline-block;margin-right:4px}
    a.back{color:#2980b9;font-size:.9rem;text-decoration:none}
    a.back:hover{text-decoration:underline}
  </style>
</head>
<body>
<div class="page">
  <h1>🔎 SHAP Beeswarm &amp; Permutation Importance</h1>
  <p class="subtitle">피처 중요도 인터랙티브 차트 &middot; Step 09 결과</p>

  <div class="tabs">
    <button class="tab active" onclick="switchScope('overall',this)">전체 (Overall)</button>
    <button class="tab" onclick="switchScope('promotion_only',this)">프로모션 (Promotion)</button>
    <button class="tab" onclick="switchScope('nonpromotion_only',this)">비프로모션 (Non-Promotion)</button>
  </div>

  <div class="card">
    <h2>🐝 SHAP Beeswarm &mdash; <span id="bee-label">전체 (Overall)</span></h2>
    <div id="bee-warn" class="warn" style="display:none">
      ⚠️ Beeswarm 차트는 Step 09 재실행이 필요합니다.
      <b>POST /09/shap?force=true</b> 실행 후 이 페이지를 새로고침하세요.
    </div>
    <div id="bee-chart" style="height:640px"></div>
    <p class="note">
      점 색상: 해당 피처의 실제 값 (파랑=낮음, 빨강=높음) &nbsp;|&nbsp;
      X축 양수 → 이탈 확률 증가 기여 &nbsp;|&nbsp; X축 음수 → 이탈 확률 감소 기여
    </p>
  </div>

  <div class="card">
    <h2>📊 Permutation Importance &mdash; <span id="perm-label">전체 (Overall)</span></h2>
    <div id="perm-chart" style="height:540px"></div>
    <div class="legend-row">
      <span><span class="dot" style="background:#2980b9"></span>사용/리텐션 행동</span>
      <span><span class="dot" style="background:#8e44ad"></span>콘텐츠 선호</span>
      <span><span class="dot" style="background:#16a085"></span>멤버십 맥락</span>
      <span><span class="dot" style="background:#e67e22"></span>가입 경로</span>
      <span><span class="dot" style="background:#e74c3c"></span>결제 기기</span>
    </div>
    <p class="note">피처를 무작위로 섞었을 때 AUC 감소량 &middot; 에러바 = 5 repeats 표준편차</p>
  </div>

  <a class="back" href="/pipeline/report">← 전체 보고서로 돌아가기</a>
</div>

<script>
const SCOPE_DATA = """

    tail = """;

const LABELS = {
  overall: '전체 (Overall)',
  promotion_only: '프로모션 (Promotion)',
  nonpromotion_only: '비프로모션 (Non-Promotion)'
};
const FAM_COLORS = {
  usage_retention_behavior: '#2980b9',
  content_preference:       '#8e44ad',
  membership_context:       '#16a085',
  acquisition_split:        '#e67e22',
  payment_proxy:            '#e74c3c',
  other:                    '#95a5a6'
};

function switchScope(scope, btn) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('bee-label').textContent  = LABELS[scope];
  document.getElementById('perm-label').textContent = LABELS[scope];
  renderAll(scope);
}

function renderBeeswarm(sd) {
  const beeData = (sd.shap || {}).beeswarm_data;
  if (!beeData || !Object.keys(beeData).length) {
    document.getElementById('bee-warn').style.display  = 'block';
    document.getElementById('bee-chart').innerHTML = '';
    return;
  }
  document.getElementById('bee-warn').style.display = 'none';

  const features = Object.keys(beeData);
  const n = features.length;
  const traces = features.map((feat, fi) => {
    const sv  = beeData[feat].shap_values;
    const fv  = beeData[feat].feat_vals_norm;
    const yBase = n - 1 - fi;
    const y = sv.map(() => yBase + (Math.random() - 0.5) * 0.55);
    return {
      type: 'scatter', mode: 'markers',
      x: sv, y: y,
      marker: {
        color: fv,
        colorscale: [[0,'#3b82f6'],[0.5,'#f1f5f9'],[1,'#ef4444']],
        size: 4, opacity: 0.72,
        cmin: 0, cmax: 1,
        showscale: fi === n - 1,
        colorbar: {
          title: {text: '피처값<br>(정규화)', side: 'right'},
          thickness: 12, len: 0.5, x: 1.02,
          tickvals: [0, 0.5, 1], ticktext: ['낮음','중간','높음']
        }
      },
      name: feat, showlegend: false,
      hovertemplate: '<b>' + feat + '</b><br>SHAP: %{x:.5f}<extra></extra>'
    };
  });

  Plotly.newPlot('bee-chart', traces, {
    height: 640,
    xaxis: {
      title: 'SHAP 값 (양수=이탈 기여, 음수=유지 기여)',
      zeroline: true, zerolinecolor: '#444', zerolinewidth: 1.5,
      gridcolor: '#eee'
    },
    yaxis: {
      tickmode: 'array',
      tickvals: features.map((_, i) => n - 1 - i),
      ticktext: features,
      range: [-0.5, n - 0.5],
      gridcolor: '#eee'
    },
    shapes: [{
      type: 'line', x0: 0, x1: 0, y0: -0.5, y1: n - 0.5,
      line: {color: '#333', width: 1.5, dash: 'dot'}
    }],
    margin: {l: 215, r: 85, t: 20, b: 60},
    plot_bgcolor: '#fafafa', paper_bgcolor: '#fff',
    hovermode: 'closest'
  }, {responsive: true, displaylogo: false});
}

function renderPerm(sd) {
  const top20 = ((sd.permutation || {}).top20 || []).slice(0, 20).reverse();
  if (!top20.length) {
    document.getElementById('perm-chart').innerHTML =
      '<p style="padding:40px;color:#aaa">Permutation 데이터가 없습니다</p>';
    return;
  }
  const feats  = top20.map(r => r.feature);
  const vals   = top20.map(r => r.perm_importance || 0);
  const errs   = top20.map(r => r.perm_std || 0);
  const colors = top20.map(r => FAM_COLORS[r.family] || '#95a5a6');

  Plotly.newPlot('perm-chart', [{
    type: 'bar', orientation: 'h',
    x: vals, y: feats,
    error_x: {type: 'data', array: errs, visible: true, color: '#666'},
    marker: {color: colors, opacity: 0.85},
    hovertemplate: '<b>%{y}</b><br>AUC 감소량: %{x:.5f}<extra></extra>'
  }], {
    height: 540,
    xaxis: {title: 'AUC 감소량 (클수록 중요)', gridcolor: '#eee'},
    yaxis: {gridcolor: '#eee'},
    margin: {l: 215, r: 40, t: 20, b: 60},
    plot_bgcolor: '#fafafa', paper_bgcolor: '#fff'
  }, {responsive: true, displaylogo: false});
}

function renderAll(scope) {
  const sd = SCOPE_DATA[scope] || {};
  renderBeeswarm(sd);
  renderPerm(sd);
}

renderAll('overall');
</script>
</body>
</html>"""

    return HTMLResponse(content=head + data_json + tail)
