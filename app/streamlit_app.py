"""
O Oráculo do LoL — Painel de Controle
Rodar com:
    streamlit run app/streamlit_app.py --server.address=0.0.0.0
"""
from __future__ import annotations

import json
import logging
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Oráculo do LoL",
    page_icon="⚔️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Estilo
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;600;700&family=Inter:wght@300;400;500&display=swap');

    .stApp { background: #0d0d14; }

    h1, h2, h3 { font-family: 'Rajdhani', sans-serif !important; }

    .metric-card {
        background: #16161f;
        border: 1px solid #2a2a3a;
        border-radius: 10px;
        padding: 16px 20px;
        margin-bottom: 12px;
    }
    .metric-label {
        font-family: 'Inter', sans-serif;
        font-size: 11px;
        font-weight: 500;
        color: #666;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-bottom: 4px;
    }
    .metric-value {
        font-family: 'Rajdhani', sans-serif;
        font-size: 26px;
        font-weight: 700;
        color: #e8e8f0;
    }
    .metric-sub {
        font-family: 'Inter', sans-serif;
        font-size: 12px;
        color: #555;
        margin-top: 2px;
    }
    .status-ok { color: #4ade80; }
    .status-warn { color: #facc15; }
    .status-err { color: #f87171; }

    .match-card {
        background: #16161f;
        border: 1px solid #2a2a3a;
        border-radius: 10px;
        padding: 16px 20px;
        margin-bottom: 10px;
    }
    .match-title {
        font-family: 'Rajdhani', sans-serif;
        font-size: 20px;
        font-weight: 700;
        color: #e8e8f0;
    }
    .match-meta {
        font-family: 'Inter', sans-serif;
        font-size: 12px;
        color: #666;
        margin-top: 2px;
    }
    .badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 20px;
        font-size: 11px;
        font-weight: 600;
        font-family: 'Inter', sans-serif;
    }
    .badge-green { background: #14532d; color: #4ade80; }
    .badge-yellow { background: #422006; color: #facc15; }
    .badge-gray { background: #1e1e2e; color: #888; }

    .post-preview {
        background: #0f0f1a;
        border: 1px solid #2a2a3a;
        border-left: 3px solid #7c3aed;
        border-radius: 6px;
        padding: 14px 16px;
        font-family: 'Inter', sans-serif;
        font-size: 13px;
        color: #ccc;
        white-space: pre-wrap;
        line-height: 1.6;
    }
    .log-line {
        font-family: 'JetBrains Mono', monospace;
        font-size: 11px;
        padding: 2px 0;
        border-bottom: 1px solid #1a1a2a;
    }
    .log-info { color: #60a5fa; }
    .log-warning { color: #facc15; }
    .log-error { color: #f87171; }

    div[data-testid="stTab"] button {
        font-family: 'Rajdhani', sans-serif !important;
        font-size: 16px !important;
        font-weight: 600 !important;
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Helpers de dados
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
PREDICTIONS_DIR = DATA_DIR / "predictions"
CONTEXT_DIR = DATA_DIR / "context"
LOG_FILE = DATA_DIR / "scheduler.log"
PLIST_LABEL = "com.oraculo.lol.scheduler"


def _parse_dt(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        if value.endswith("Z"):
            value = value.replace("Z", "+00:00")
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _fmt_dt(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    local = dt.astimezone()
    return local.strftime("%d/%m/%Y %H:%M")


def _time_until(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    now = datetime.now(timezone.utc)
    delta = dt.astimezone(timezone.utc) - now
    if delta.total_seconds() < 0:
        return "já passou"
    hours = int(delta.total_seconds() // 3600)
    minutes = int((delta.total_seconds() % 3600) // 60)
    if hours > 0:
        return f"{hours}h {minutes}min"
    return f"{minutes}min"


@st.cache_data(ttl=30)
def get_scheduler_status() -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["launchctl", "list", PLIST_LABEL],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return {"running": False, "pid": None}
        lines = result.stdout.strip().splitlines()
        pid = None
        for line in lines:
            if '"PID"' in line:
                pid = line.split("=")[1].strip().rstrip(";")
        return {"running": True, "pid": pid}
    except Exception:
        return {"running": False, "pid": None}


@st.cache_data(ttl=60)
def get_upcoming_matches() -> list[dict[str, Any]]:
    try:
        from oraculo_lol.datasources.pandascore import upcoming_br_lol_matches
        return upcoming_br_lol_matches(max_pages=2)
    except Exception as e:
        return []


@st.cache_data(ttl=10)
def get_predictions() -> list[dict[str, Any]]:
    if not PREDICTIONS_DIR.exists():
        return []
    preds = []
    for f in sorted(PREDICTIONS_DIR.glob("*.json"), reverse=True):
        try:
            preds.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    return preds


@st.cache_data(ttl=10)
def get_log_lines(n: int = 200) -> list[str]:
    if not LOG_FILE.exists():
        return []
    try:
        lines = LOG_FILE.read_text(encoding="utf-8").splitlines()
        return lines[-n:]
    except Exception:
        return []


def get_threads_days_left() -> int | None:
    try:
        from oraculo_lol.settings import load_settings
        s = load_settings()
        if not s.threads_token_created_at:
            return None
        created = datetime.fromisoformat(s.threads_token_created_at).replace(tzinfo=timezone.utc)
        expires = created + timedelta(days=60)
        return max(0, (expires - datetime.now(timezone.utc)).days)
    except Exception:
        return None


def get_next_match(matches: list[dict]) -> dict | None:
    now = datetime.now(timezone.utc)
    future = []
    for m in matches:
        dt = _parse_dt(m.get("begin_at"))
        if dt and dt > now:
            future.append((dt, m))
    if not future:
        return None
    return sorted(future, key=lambda x: x[0])[0][1]


def has_prediction(match_id: int) -> bool:
    return (PREDICTIONS_DIR / f"pandascore_match_{match_id}.json").exists()


def load_prediction(match_id: int) -> dict | None:
    p = PREDICTIONS_DIR / f"pandascore_match_{match_id}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown("""
<div style="padding: 24px 0 8px 0;">
    <h1 style="font-size: 36px; font-weight: 700; color: #e8e8f0; margin: 0; letter-spacing: 1px;">
        ⚔️ ORÁCULO DO LOL
    </h1>
    <p style="font-family: 'Inter', sans-serif; color: #555; font-size: 13px; margin: 4px 0 0 2px;">
        Painel de Controle — CBLOL & Circuito Desafiante
    </p>
</div>
""", unsafe_allow_html=True)

st.divider()

# ---------------------------------------------------------------------------
# Abas
# ---------------------------------------------------------------------------
tab1, tab2, tab3, tab4 = st.tabs(["📊 Status", "🎮 Partidas", "🔮 Previsões", "📋 Logs"])


# ============================================================================
# ABA 1 — STATUS
# ============================================================================
with tab1:
    st.markdown("### Visão Geral do Sistema")

    col1, col2, col3, col4 = st.columns(4)

    # Scheduler
    sched = get_scheduler_status()
    with col1:
        if sched["running"]:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">Scheduler</div>
                <div class="metric-value status-ok">● ATIVO</div>
                <div class="metric-sub">PID {sched['pid']}</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="metric-card">
                <div class="metric-label">Scheduler</div>
                <div class="metric-value status-err">● PARADO</div>
                <div class="metric-sub">launchd não encontrou o processo</div>
            </div>
            """, unsafe_allow_html=True)

    # Próxima partida
    with col2:
        matches = get_upcoming_matches()
        next_m = get_next_match(matches)
        if next_m:
            name = next_m.get("name", "?")
            dt = _parse_dt(next_m.get("begin_at"))
            time_left = _time_until(dt)
            color = "status-warn" if dt and (dt.astimezone(timezone.utc) - datetime.now(timezone.utc)).total_seconds() < 7200 else "status-ok"
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">Próxima Partida</div>
                <div class="metric-value {color}">{time_left}</div>
                <div class="metric-sub">{name} · {_fmt_dt(dt)}</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="metric-card">
                <div class="metric-label">Próxima Partida</div>
                <div class="metric-value" style="color:#555;">—</div>
                <div class="metric-sub">Nenhuma partida agendada</div>
            </div>
            """, unsafe_allow_html=True)

    # Token Threads
    with col3:
        days = get_threads_days_left()
        if days is None:
            st.markdown("""
            <div class="metric-card">
                <div class="metric-label">Token Threads</div>
                <div class="metric-value" style="color:#555;">N/A</div>
                <div class="metric-sub">THREADS_TOKEN_CREATED_AT não configurado</div>
            </div>
            """, unsafe_allow_html=True)
        elif days <= 5:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">Token Threads</div>
                <div class="metric-value status-err">{days}d restantes</div>
                <div class="metric-sub">⚠️ Renove em breve!</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">Token Threads</div>
                <div class="metric-value status-ok">{days}d restantes</div>
                <div class="metric-sub">Expira em 60 dias após criação</div>
            </div>
            """, unsafe_allow_html=True)

    # Previsões geradas
    with col4:
        preds = get_predictions()
        acertos = sum(1 for p in preds if p.get("predicted_winner") and not p.get("parse_error"))
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Previsões Geradas</div>
            <div class="metric-value" style="color:#a78bfa;">{len(preds)}</div>
            <div class="metric-sub">{acertos} com vencedor previsto</div>
        </div>
        """, unsafe_allow_html=True)

    # Partidas na janela
    st.markdown("### Partidas nas Próximas 6h")
    now = datetime.now(timezone.utc)
    window = [
        m for m in matches
        if (dt := _parse_dt(m.get("begin_at"))) and dt > now
        and (dt - now).total_seconds() <= 21600
    ]
    if window:
        for m in window:
            dt = _parse_dt(m.get("begin_at"))
            name = m.get("name", "?")
            league = (m.get("league") or {}).get("name", "?")
            mid = m.get("id")
            has_pred = has_prediction(int(mid)) if mid else False
            badge = '<span class="badge badge-green">✓ Previsão gerada</span>' if has_pred else '<span class="badge badge-yellow">Sem previsão</span>'
            st.markdown(f"""
            <div class="match-card">
                <span class="match-title">{name}</span>
                {badge}
                <div class="match-meta">{league} · {_fmt_dt(dt)} · {_time_until(dt)}</div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.markdown('<p style="color:#555; font-family:Inter,sans-serif; font-size:13px;">Nenhuma partida nas próximas 6 horas.</p>', unsafe_allow_html=True)

    if st.button("🔄 Atualizar Status", key="refresh_status"):
        st.cache_data.clear()
        st.rerun()


# ============================================================================
# ABA 2 — PARTIDAS
# ============================================================================
with tab2:
    st.markdown("### Próximas Partidas BR")

    col_filter1, col_filter2 = st.columns([2, 1])
    with col_filter1:
        search = st.text_input("Filtrar por time", placeholder="Ex: RED, FURIA, Fluxo...", label_visibility="collapsed")
    with col_filter2:
        if st.button("🔄 Recarregar partidas"):
            st.cache_data.clear()
            st.rerun()

    matches = get_upcoming_matches()
    now = datetime.now(timezone.utc)

    future_matches = [
        m for m in matches
        if (dt := _parse_dt(m.get("begin_at"))) and dt > now
    ]
    future_matches.sort(key=lambda m: _parse_dt(m.get("begin_at")) or now)

    if search:
        future_matches = [
            m for m in future_matches
            if search.lower() in (m.get("name") or "").lower()
        ]

    if not future_matches:
        st.info("Nenhuma partida encontrada.")
    else:
        for m in future_matches:
            dt = _parse_dt(m.get("begin_at"))
            name = m.get("name", "?")
            league = (m.get("league") or {}).get("name", "?")
            mid = int(m.get("id", 0))
            ng = m.get("number_of_games", "?")
            has_pred = has_prediction(mid)

            with st.container():
                st.markdown(f"""
                <div class="match-card">
                    <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                        <div>
                            <span class="match-title">{name}</span>
                            <div class="match-meta">
                                {league} · MD{ng} · {_fmt_dt(dt)} · {_time_until(dt)}
                            </div>
                        </div>
                        <div>
                            {'<span class="badge badge-green">✓ Previsão pronta</span>' if has_pred else '<span class="badge badge-gray">Sem previsão</span>'}
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 4])

                with btn_col1:
                    if st.button("🔮 Gerar previsão", key=f"gen_{mid}", use_container_width=True):
                        with st.spinner("Gerando contexto e previsão..."):
                            try:
                                from oraculo_lol.runtime import init_runtime
                                from oraculo_lol.agregador.build_context import build_match_context, save_context_json
                                from oraculo_lol.oraculo.runner import run_prediction
                                from oraculo_lol.oraculo.prediction import save_prediction_json
                                init_runtime()
                                ctx = build_match_context(pandascore_match_id=mid, include_payloads=False)
                                save_context_json(ctx)
                                pred = run_prediction(match_id=mid)
                                save_prediction_json(pred)
                                st.success(f"✓ Favorito: **{pred.predicted_winner}** ({pred.confidence})")
                                st.cache_data.clear()
                            except Exception as e:
                                st.error(f"Erro: {e}")

                with btn_col2:
                    pred_data = load_prediction(mid)
                    if st.button(
                        "📤 Postar agora",
                        key=f"post_{mid}",
                        use_container_width=True,
                        disabled=not has_pred,
                    ):
                        if pred_data:
                            with st.spinner("Postando..."):
                                try:
                                    from oraculo_lol.oraculo.prediction import Prediction
                                    from oraculo_lol.publisher.formatter import format_for_twitter_long, format_for_threads
                                    from oraculo_lol.publisher.twitter import post_tweet_safe
                                    from oraculo_lol.publisher.threads import post_thread_safe
                                    pred_obj = Prediction.model_validate(pred_data)
                                    tw = format_for_twitter_long(pred_obj)
                                    th = format_for_threads(pred_obj)
                                    tw_ok = post_tweet_safe(tw)
                                    th_ok = post_thread_safe(th)
                                    status = []
                                    if tw_ok: status.append("X ✓")
                                    else: status.append("X ✗")
                                    if th_ok: status.append("Threads ✓")
                                    else: status.append("Threads ✗")
                                    st.success(f"Postado: {' | '.join(status)}")
                                except Exception as e:
                                    st.error(f"Erro ao postar: {e}")

                # Preview dos posts se previsão existir
                if has_pred and pred_data:
                    with st.expander("👁 Ver posts", expanded=False):
                        try:
                            from oraculo_lol.oraculo.prediction import Prediction
                            from oraculo_lol.publisher.formatter import format_for_twitter_long, format_for_threads
                            pred_obj = Prediction.model_validate(pred_data)
                            tw_text = format_for_twitter_long(pred_obj)
                            th_text = format_for_threads(pred_obj)

                            c1, c2 = st.columns(2)
                            with c1:
                                st.caption(f"𝕏 Post ({len(tw_text)} chars)")
                                st.markdown(f'<div class="post-preview">{tw_text}</div>', unsafe_allow_html=True)
                            with c2:
                                st.caption(f"Threads ({len(th_text)} chars)")
                                st.markdown(f'<div class="post-preview">{th_text}</div>', unsafe_allow_html=True)
                        except Exception as e:
                            st.error(f"Erro ao gerar preview: {e}")

                st.markdown("<div style='margin-bottom:4px;'></div>", unsafe_allow_html=True)


# ============================================================================
# ABA 3 — PREVISÕES
# ============================================================================
with tab3:
    st.markdown("### Histórico de Previsões")

    preds = get_predictions()

    if not preds:
        st.info("Nenhuma previsão gerada ainda.")
    else:
        # Filtros
        col_f1, col_f2 = st.columns([2, 1])
        with col_f1:
            search_pred = st.text_input("Filtrar", placeholder="Ex: RED, FURIA...", label_visibility="collapsed", key="search_pred")
        with col_f2:
            only_errors = st.checkbox("Só com erro de parse", value=False)

        filtered = preds
        if search_pred:
            filtered = [p for p in filtered if search_pred.lower() in json.dumps(p).lower()]
        if only_errors:
            filtered = [p for p in filtered if p.get("parse_error")]

        st.caption(f"{len(filtered)} previsões")

        for pred in filtered:
            mid = pred.get("pandascore_match_id", "?")
            winner = pred.get("predicted_winner", "?")
            confidence = pred.get("confidence", "?")
            created = _parse_dt(pred.get("created_at"))
            reasoning = pred.get("reasoning", "")
            reasoning_long = pred.get("reasoning_long", "")
            parse_error = pred.get("parse_error", False)
            model = pred.get("llm_model", "?")
            teams = pred.get("teams", [])

            conf_color = {"alta": "#4ade80", "média": "#facc15", "baixa": "#f87171"}.get(confidence or "", "#888")
            badge_err = '<span class="badge" style="background:#450a0a;color:#f87171;">⚠ parse error</span>' if parse_error else ""

            # Probabilidades
            probs_html = ""
            if len(teams) == 2:
                a, b = teams[0], teams[1]
                pa = f"{a['win_probability']*100:.0f}%" if a.get("win_probability") is not None else "?"
                pb = f"{b['win_probability']*100:.0f}%" if b.get("win_probability") is not None else "?"
                probs_html = f"<span style='color:#888; font-size:12px;'>{a.get('name','?')} {pa} × {pb} {b.get('name','?')}</span>"

            with st.container():
                st.markdown(f"""
                <div class="match-card">
                    <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                        <div>
                            <span style="font-family:Rajdhani,sans-serif; font-size:18px; font-weight:700; color:#e8e8f0;">
                                Match #{mid}
                            </span>
                            {badge_err}
                            <div style="margin-top:4px;">{probs_html}</div>
                        </div>
                        <div style="text-align:right;">
                            <div style="font-family:Rajdhani,sans-serif; font-size:16px; font-weight:700; color:{conf_color};">
                                {winner}
                            </div>
                            <div style="font-size:11px; color:#555; font-family:Inter,sans-serif;">
                                {(confidence or '?').upper()} · {model}
                            </div>
                            <div style="font-size:11px; color:#444; font-family:Inter,sans-serif;">
                                {_fmt_dt(created)}
                            </div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                with st.expander("Ver análise e posts", expanded=False):
                    if reasoning:
                        st.caption("💬 Reasoning (Threads)")
                        st.markdown(f'<div class="post-preview">{reasoning}</div>', unsafe_allow_html=True)
                        st.markdown("<div style='margin:8px 0;'></div>", unsafe_allow_html=True)

                    if reasoning_long:
                        st.caption("📝 Reasoning Long (X)")
                        st.markdown(f'<div class="post-preview">{reasoning_long}</div>', unsafe_allow_html=True)
                        st.markdown("<div style='margin:8px 0;'></div>", unsafe_allow_html=True)

                    # Preview dos posts formatados
                    try:
                        from oraculo_lol.oraculo.prediction import Prediction as PredModel
                        from oraculo_lol.publisher.formatter import format_for_twitter_long, format_for_threads
                        pred_obj = PredModel.model_validate(pred)
                        tw_text = format_for_twitter_long(pred_obj)
                        th_text = format_for_threads(pred_obj)

                        c1, c2 = st.columns(2)
                        with c1:
                            st.caption(f"𝕏 Post formatado ({len(tw_text)} chars)")
                            st.markdown(f'<div class="post-preview">{tw_text}</div>', unsafe_allow_html=True)
                        with c2:
                            st.caption(f"Threads formatado ({len(th_text)} chars)")
                            st.markdown(f'<div class="post-preview">{th_text}</div>', unsafe_allow_html=True)
                    except Exception:
                        pass

                    # Botão repostar
                    if not parse_error:
                        if st.button("📤 Repostar", key=f"repost_{mid}"):
                            with st.spinner("Postando..."):
                                try:
                                    from oraculo_lol.oraculo.prediction import Prediction as PredModel
                                    from oraculo_lol.publisher.formatter import format_for_twitter_long, format_for_threads
                                    from oraculo_lol.publisher.twitter import post_tweet_safe
                                    from oraculo_lol.publisher.threads import post_thread_safe
                                    pred_obj = PredModel.model_validate(pred)
                                    tw_ok = post_tweet_safe(format_for_twitter_long(pred_obj))
                                    th_ok = post_thread_safe(format_for_threads(pred_obj))
                                    st.success(f"X: {'✓' if tw_ok else '✗'} | Threads: {'✓' if th_ok else '✗'}")
                                except Exception as e:
                                    st.error(f"Erro: {e}")


# ============================================================================
# ABA 4 — LOGS
# ============================================================================
with tab4:
    st.markdown("### Logs do Scheduler")

    col_l1, col_l2, col_l3 = st.columns([1, 1, 2])
    with col_l1:
        n_lines = st.selectbox("Últimas linhas", [50, 100, 200, 500], index=1, label_visibility="visible")
    with col_l2:
        level_filter = st.selectbox("Nível", ["Todos", "INFO", "WARNING", "ERROR"], index=0)
    with col_l3:
        st.markdown("<div style='margin-top:26px;'></div>", unsafe_allow_html=True)
        if st.button("🔄 Atualizar logs"):
            st.cache_data.clear()
            st.rerun()

    lines = get_log_lines(n=int(n_lines))

    if level_filter != "Todos":
        lines = [l for l in lines if level_filter in l]

    if not lines:
        st.info("Nenhum log encontrado." if not LOG_FILE.exists() else "Nenhuma linha corresponde ao filtro.")
    else:
        # Renderiza logs com cor por nível
        log_html = ""
        for line in reversed(lines):
            if "ERROR" in line or "CRITICAL" in line:
                css = "log-error"
            elif "WARNING" in line:
                css = "log-warning"
            else:
                css = "log-info"
            safe_line = line.replace("<", "&lt;").replace(">", "&gt;")
            log_html += f'<div class="log-line {css}">{safe_line}</div>'

        st.markdown(
            f'<div style="background:#0a0a12; border:1px solid #1e1e2e; border-radius:8px; padding:12px; max-height:600px; overflow-y:auto;">{log_html}</div>',
            unsafe_allow_html=True,
        )

    # Arquivo de erros
    error_log = DATA_DIR / "scheduler_error.log"
    if error_log.exists() and error_log.stat().st_size > 0:
        with st.expander("⚠️ Erros do sistema (scheduler_error.log)"):
            try:
                content = error_log.read_text(encoding="utf-8")[-5000:]
                st.code(content, language="text")
            except Exception:
                st.error("Não foi possível ler o arquivo de erros.")