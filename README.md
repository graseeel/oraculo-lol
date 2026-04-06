# ⚔️ Oráculo do LoL

Bot automatizado de previsão de partidas do cenário brasileiro de League of Legends. Analisa dados de rosters, histórico, H2H e drafts para gerar previsões fundamentadas antes de cada jogo do CBLOL e Circuito Desafiante.

> Dados fornecidos por [Pandascore](https://pandascore.co) e [Liquipedia](https://liquipedia.net/leagueoflegends)

---

## O que o bot faz

- **Pré-jogo** — 1 hora antes de cada partida, posta uma análise com favorito, probabilidades e reasoning baseado em forma recente, H2H e picks históricos
- **Pós-jogo** — ao término de cada game, posta o resultado com duração e placar da série
- **Resultado final** — ao fim da série, compara com a previsão e indica acerto ou erro
- **Alertas operacionais** — notificações via Telegram sobre postagens, falhas e expiração de tokens

Plataformas: **X** (posts longos com Premium Basic) e **Threads** (500 chars).

---

## Fontes de dados

| Fonte | Uso |
|---|---|
| Pandascore | Partidas, rosters, histórico, H2H |
| Liquipedia | Picks, bans e KDA por jogador |
| OpenAI GPT-4o | Geração da análise e previsão |

---

## Stack

- Python 3.13
- Streamlit (painel de controle)
- launchd (scheduler autônomo no macOS)
- Telegram Bot API (alertas)

---

## Configuração

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pip install -e .
cp .env.example .env
```

Preencha o `.env` com as chaves das APIs.

---

## Rodando

**Scheduler** (autônomo via launchd):
```bash
python -m scripts.setup_launchd
```

**Painel de controle**:
```bash
streamlit run app/streamlit_app.py --server.address=0.0.0.0
```

---

## Testes

```bash
pytest tests/ -v
```

75 testes cobrindo formatter, layout e pós-jogo.

---

## Licença

Open source — dados da Liquipedia usados sob licença [CC-BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/us/).