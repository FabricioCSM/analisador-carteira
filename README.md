# 📈 Analisador Inteligente de Carteira v2.1

Sistema automatizado de análise de carteira de investimentos com IA.

## O que faz

- Coleta cotações da carteira (brapi.dev)
- Busca preço do ouro, prata, dólar, euro, Bitcoin, Selic, IPCA
- Escaneia 30+ oportunidades de compra (ações, FIIs, ETFs)
- Analisa composição setorial e concentração da carteira
- Envia tudo para Claude AI que gera análise com metodologia Suno (Bazin/Barsi)
- Gera dashboard HTML com relatório completo

## Execução automática

O GitHub Actions roda automaticamente nos dias úteis:
- **08:30** — Antes da abertura do mercado
- **14:00** — Meio do pregão
- **17:30** — Fechamento do mercado

Os relatórios ficam na pasta `relatorios/`.

## Como ver os relatórios

1. Vá na pasta `relatorios/` neste repositório
2. Clique no arquivo `relatorio_latest.html`
3. Baixe e abra no navegador

Ou acesse pelo celular via GitHub app.

## Configuração

As chaves de API estão configuradas em **Settings → Secrets → Actions**:
- `BRAPI_TOKEN` — Token da brapi.dev
- `ANTHROPIC_API_KEY` — Chave da API Anthropic
