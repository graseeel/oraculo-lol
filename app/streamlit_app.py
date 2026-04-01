from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd
import streamlit as st

from oraculo_lol.agregador.build_context import build_match_context, save_context_json
from oraculo_lol.agregador.rosters import save_rosters_snapshot, sync_rosters_from_upcoming
from oraculo_lol.datasources.pandascore import upcoming_br_lol_matches
from oraculo_lol.runtime import init_runtime


@dataclass(frozen=True)
class LogLine:
    level: str
    name: str
    msg: str


class StreamlitLogHandler(logging.Handler):
    def __init__(self, buffer: list[LogLine]) -> None:
        super().__init__()
        self._buffer = buffer

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001
            msg = str(record.msg)
        self._buffer.append(LogLine(level=record.levelname, name=record.name, msg=msg))


def _setup_logging_for_ui(*, verbose: bool) -> list[LogLine]:
    """
    Captura logs em memória e filtra ruído.
    """
    buf: list[LogLine] = []

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)

    handler = StreamlitLogHandler(buf)
    handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    root.addHandler(handler)

    # Silencia logs muito verbosos por padrão
    logging.getLogger("httpx").setLevel(logging.WARNING if not verbose else logging.INFO)
    return buf


def _render_logs(lines: list[LogLine], *, mode: Literal["useful", "all"]) -> None:
    if not lines:
        st.caption("Sem logs.")
        return

    if mode == "useful":
        shown = [l for l in lines if l.level in {"WARNING", "ERROR", "CRITICAL"}]
    else:
        shown = lines

    if not shown:
        st.caption("Sem warnings/erros.")
        return

    for l in shown[-200:]:
        st.text(f"{l.level} {l.name} - {l.msg}")


def _as_df(items: list[dict[str, Any]]) -> pd.DataFrame:
    if not items:
        return pd.DataFrame()
    # achata o suficiente para visualizar lista de matches
    rows = []
    for m in items:
        rows.append(
            {
                "id": m.get("id"),
                "begin_at": m.get("begin_at"),
                "name": m.get("name"),
                "number_of_games": m.get("number_of_games"),
                "league": (m.get("league") or {}).get("name") if isinstance(m.get("league"), dict) else None,
                "serie": (m.get("serie") or {}).get("full_name") if isinstance(m.get("serie"), dict) else None,
                "tournament": (m.get("tournament") or {}).get("name")
                if isinstance(m.get("tournament"), dict)
                else None,
                "status": m.get("status"),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    st.set_page_config(page_title="O Oráculo do LoL (Operador)", layout="wide")
    st.title("O Oráculo do LoL — Painel do Operador")

    with st.sidebar:
        st.subheader("Preferências")
        verbose = st.toggle("Mostrar logs detalhados", value=False)
        log_mode: Literal["useful", "all"] = "all" if verbose else "useful"

    log_lines = _setup_logging_for_ui(verbose=verbose)
    init_runtime()

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Pandascore — Próximas partidas (BR)")
        max_pages = st.number_input("Max pages", min_value=1, max_value=10, value=2, step=1)
        if st.button("Buscar próximas partidas BR", use_container_width=True):
            try:
                matches = upcoming_br_lol_matches(max_pages=int(max_pages))
                st.session_state["upcoming_matches"] = matches
                st.success(f"OK: {len(matches)} partidas carregadas.")
            except Exception as exc:  # noqa: BLE001
                st.error(f"Falha ao buscar partidas: {exc!r}")

        matches = st.session_state.get("upcoming_matches") or []
        df = _as_df(matches) if isinstance(matches, list) else pd.DataFrame()
        if not df.empty:
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.caption("Nenhuma partida carregada ainda.")

    with col2:
        st.subheader("Rosters / Contexto")

        if st.button("Sync Rosters (BR)", use_container_width=True):
            try:
                snapshot = sync_rosters_from_upcoming(max_pages=5)
                path = save_rosters_snapshot(snapshot)
                st.success(f"OK: {len(snapshot.teams)} times. Salvo em: {path}")
                st.session_state["rosters_snapshot"] = snapshot.model_dump(mode="json")
            except Exception as exc:  # noqa: BLE001
                st.error(f"Falha no sync-rosters: {exc!r}")

        st.divider()
        st.caption("Build Context (Pandascore match_id)")
        match_id = st.text_input("Match ID", value="")
        include_payloads = st.toggle("Incluir payloads crus (debug)", value=True)
        if st.button("Build Context", use_container_width=True, disabled=not match_id.strip()):
            try:
                ctx = build_match_context(
                    pandascore_match_id=int(match_id.strip()),
                    include_payloads=bool(include_payloads),
                )
                path = save_context_json(ctx)
                st.success(f"OK: contexto salvo em {path}")
                st.session_state["match_context"] = ctx.model_dump(mode="json")
            except Exception as exc:  # noqa: BLE001
                st.error(f"Falha ao gerar contexto: {exc!r}")

    st.subheader("Saídas")
    out_col1, out_col2 = st.columns([1, 1])
    with out_col1:
        st.caption("Snapshot de rosters (última execução)")
        rosters = st.session_state.get("rosters_snapshot")
        if rosters:
            st.json(rosters)
        else:
            st.caption("—")
    with out_col2:
        st.caption("Match context (última execução)")
        ctx = st.session_state.get("match_context")
        if ctx:
            st.json(ctx)
        else:
            st.caption("—")

    st.subheader("Logs")
    _render_logs(log_lines, mode=log_mode)

    st.caption(
        "Dica: se algo falhar e você quiser depurar, ative “Mostrar logs detalhados” na lateral."
    )


if __name__ == "__main__":
    main()

