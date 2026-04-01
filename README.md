# O Oráculo do LoL

Bot automatizado de análise e previsão de esports (League of Legends), começando pelo cenário brasileiro (CBLOL, Circuitão e torneios não-oficiais como CBLoW).

## Estrutura (MVP)

- `src/oraculo_lol/`: pacote principal (config, logging, modelos, utilitários)
- `scripts/`: entrypoints (rodados via `python -m ...`)
  - `scripts/agregador.py`: compila o JSON de contexto da partida
  - `scripts/oraculo.py`: gera previsão usando LLM a partir do contexto
  - `scripts/scheduler.py`: checa novos jogos a cada hora
- `data/`: arquivos locais (SQLite, caches, dumps de contexto)

## Requisitos

- Python 3.13
- `pip` + `venv`

## Setup rápido

Crie e ative o ambiente virtual:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt -r requirements-dev.txt
pip install -e .
```

Crie seu `.env`:

```bash
cp .env.example .env
```

## Execução (esqueleto)

```bash
python -m scripts.scheduler
```

## App (UI) — Painel do Operador

Se você não quiser usar terminal para cada comando, rode o app Streamlit:

```bash
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pip install -e .
streamlit run app/streamlit_app.py
```

## Comandos úteis (CLI do agregador)

### Pandascore

- Buscar ligas:

```bash
python -m scripts.agregador pandascore-leagues --q "CBLOL"
```

- Próximas partidas BR (CBLOL + Circuitão):

```bash
python -m scripts.agregador pandascore-upcoming-br --max-pages 2
```

### Riot

- Status do servidor BR1:

```bash
python -m scripts.agregador riot-status --platform br1
```

- Conta por Riot ID (gameName#tagLine):

```bash
python -m scripts.agregador riot-account --regional americas --game-name "fade" --tag-line "void"
```

### Agregação (Contexto / Rosters)

- Baixar snapshot de rosters (descoberto via próximas partidas):

```bash
python -m scripts.agregador sync-rosters --max-pages 5
```

- Gerar contexto de um match Pandascore:

```bash
python -m scripts.agregador build-context --match-id 123456
```

## Notas de design

- Configuração via variáveis de ambiente (`.env`) para chaves/API tokens e paths.
- Logging padronizado em JSON (útil para scheduler) + modo humano para debug.
- Os scripts em `scripts/` apenas orquestram; a lógica fica no pacote `oraculo_lol/`.

