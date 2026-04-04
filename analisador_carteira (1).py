#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════╗
║      ANALISADOR INTELIGENTE DE CARTEIRA v2.1                 ║
║  Coleta dados macro + carteira + oportunidades               ║
║  + Commodities (ouro, prata, petróleo)                       ║
║  → Análise com Gemini AI (metodologia Suno)                  ║
╚══════════════════════════════════════════════════════════════╝

Requisitos:
  pip install requests

Uso:
  python3 analisador_carteira.py

Configuração:
  - BRAPI_TOKEN: token da brapi.dev (grátis em brapi.dev/dashboard)
  - GEMINI_API_KEY: chave da API Gemini (aistudio.google.com)
"""

import requests
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
import html as html_module
import time

# ============================================================
# CONFIGURAÇÃO DA CARTEIRA — EDITE AQUI
# ============================================================
CARTEIRA = [
    {"ticker": "VALE3",  "quantidade": 7,  "preco_medio": 79.50},
    {"ticker": "CMIG4",  "quantidade": 17, "preco_medio": 12.00},
    {"ticker": "SAPR11", "quantidade": 3,  "preco_medio": 40.87},
    {"ticker": "MATD3",  "quantidade": 20, "preco_medio": 5.78},
]

# ============================================================
# CONFIGURAÇÃO DE APIs — EDITE AQUI
# ============================================================
BRAPI_TOKEN = os.environ.get("BRAPI_TOKEN", "COLOQUE_SEU_TOKEN_AQUI")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "COLOQUE_SUA_CHAVE_GEMINI_AQUI")

# ============================================================
# WATCHLIST DE OPORTUNIDADES — Ativos para monitorar
# ============================================================
WATCHLIST_ACOES = [
    "TAEE11", "ISAE4", "CPLE6", "EGIE3", "AURE3",
    "ITUB4", "BBAS3", "BBSE3", "CXSE3", "BBDC4",
    "TIMS3", "VIVT3",
    "SBSP3",
    "PSSA3",
    "ALUP11", "ALOS3",
]

WATCHLIST_FIIS = [
    "MXRF11", "KNSC11", "RBRR11", "MCCI11",
    "XPLG11", "HGLG11",
    "XPML11", "VISC11", "HGBS11",
    "KNRI11",
    "JSAF11",
]

WATCHLIST_ETFS = [
    # ETFs de Dividendos
    "DIVD11", "NDIV11", "DIVO11",
    # ETFs de Ouro e Prata (hedge/proteção)
    "GOLD11",  # ETF Ouro - replica LBMA Gold Price via iShares Gold Trust
    "BIAU39",  # BDR ETF Ouro - iShares Gold Trust (BlackRock), taxa menor
    "BSLV39",  # BDR ETF Prata - iShares Silver Trust (BlackRock)
]

# Diretório de saída
OUTPUT_DIR = Path(__file__).parent / "relatorios"
OUTPUT_DIR.mkdir(exist_ok=True)


# ============================================================
# UTILS
# ============================================================
def log(msg, level="INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    icons = {"INFO": "📊", "OK": "✅", "WARN": "⚠️", "ERR": "❌", "AI": "🤖"}
    print(f"  {icons.get(level, '•')} [{ts}] {msg}")


def fetch_json(url, params=None, headers=None, label=""):
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=20)
            if r.status_code == 200:
                return r.json()
            else:
                log(f"{label} HTTP {r.status_code} (tentativa {attempt+1})", "WARN")
        except Exception as e:
            log(f"{label} Erro: {e} (tentativa {attempt+1})", "WARN")
        time.sleep(2)
    log(f"{label} Falhou após 3 tentativas", "ERR")
    return None


def _brapi_headers():
    """Headers para brapi (vazio, token vai via query param)."""
    return {}


def _brapi_params(**extra):
    """Monta params para brapi incluindo token."""
    params = dict(extra)
    if BRAPI_TOKEN and BRAPI_TOKEN != "COLOQUE_SEU_TOKEN_AQUI":
        params["token"] = BRAPI_TOKEN
    return params


def _parse_quote(item):
    symbol = item.get("symbol", "")
    return {
        "nome": item.get("longName") or item.get("shortName", symbol),
        "nome_curto": item.get("shortName", symbol),
        "preco": item.get("regularMarketPrice", 0),
        "variacao_dia": item.get("regularMarketChangePercent", 0),
        "abertura": item.get("regularMarketOpen", 0),
        "maxima": item.get("regularMarketDayHigh", 0),
        "minima": item.get("regularMarketDayLow", 0),
        "volume": item.get("regularMarketVolume", 0),
        "market_cap": item.get("marketCap", 0),
        "max_52sem": item.get("fiftyTwoWeekHigh", 0),
        "min_52sem": item.get("fiftyTwoWeekLow", 0),
        "dividend_yield": item.get("dividendYield", 0),
        "earnings_per_share": item.get("earningsPerShare", 0),
        "price_earnings": item.get("priceEarnings", 0),
        "dividendos_historico": (
            item.get("dividendsData", {}).get("cashDividends", [])[:10]
            if item.get("dividendsData") else []
        ),
    }


# ============================================================
# 1. COLETA DE DADOS DA CARTEIRA
# ============================================================
def coletar_cotacoes(carteira):
    tickers = ",".join([a["ticker"] for a in carteira])
    log(f"Buscando cotações: {tickers}")
    url = f"https://brapi.dev/api/quote/{tickers}"
    data = fetch_json(url, params=_brapi_params(fundamental="true", dividends="true"), label="Cotações")
    if not data or "results" not in data:
        log("Não foi possível obter cotações da brapi.dev", "ERR")
        return {}
    resultados = {}
    for item in data["results"]:
        symbol = item.get("symbol", "")
        resultados[symbol] = _parse_quote(item)
        log(f"  {symbol}: R$ {resultados[symbol]['preco']:.2f} ({resultados[symbol]['variacao_dia']:+.2f}%)", "OK")
    return resultados


# ============================================================
# 2. COLETA DE DADOS MACRO / COMMODITIES / INDICADORES
# ============================================================
def coletar_commodities():
    """Coleta câmbio, metais preciosos, petróleo, minério e indicadores macro."""
    log("Buscando commodities, câmbio e indicadores macro...")
    dados = {}

    # --- CÂMBIO via brapi ---
    d = fetch_json("https://brapi.dev/api/v2/currency?currency=USD-BRL,EUR-BRL", label="Câmbio")
    if d and "currency" in d:
        for c in d["currency"]:
            key = f"{c.get('fromCurrency','')}/{c.get('toCurrency','')}"
            dados[key] = {
                "valor": float(c.get("bidPrice", 0)),
                "variacao": float(c.get("percentageChange", 0)),
                "nome": c.get("name", key),
                "categoria": "cambio",
                "emoji": "💵" if "USD" in key else "💶",
            }
            log(f"  {key}: R$ {dados[key]['valor']:.4f} ({dados[key]['variacao']:+.2f}%)", "OK")

    # --- BITCOIN via brapi ---
    btc = fetch_json("https://brapi.dev/api/v2/crypto?coin=BTC&currency=BRL", label="Crypto")
    if btc and "coins" in btc and len(btc["coins"]) > 0:
        coin = btc["coins"][0]
        dados["BTC/BRL"] = {
            "valor": float(coin.get("regularMarketPrice", 0)),
            "variacao": float(coin.get("regularMarketChangePercent", 0)),
            "nome": "Bitcoin",
            "categoria": "crypto",
            "emoji": "₿",
        }
        log(f"  BTC/BRL: R$ {dados['BTC/BRL']['valor']:,.0f}", "OK")

    # --- OURO, PRATA, PETRÓLEO via AwesomeAPI (gratuita, sem token) ---
    # Códigos: XAU=Ouro, XAG=Prata
    # AwesomeAPI usa formato MOEDA-BRL para converter
    awesome_commodities = {
        "XAU": {"nome": "Ouro (oz troy)", "emoji": "🥇", "categoria": "metal"},
        "XAG": {"nome": "Prata (oz troy)", "emoji": "🥈", "categoria": "metal"},
    }
    for code, info in awesome_commodities.items():
        url = f"https://economia.awesomeapi.com.br/last/{code}-BRL"
        d = fetch_json(url, label=info["nome"])
        if d:
            key_api = f"{code}BRL"
            if key_api in d:
                item = d[key_api]
                valor = float(item.get("bid", 0))
                variacao = float(item.get("pctChange", 0))
                dados[f"{code}/BRL"] = {
                    "valor": valor,
                    "variacao": variacao,
                    "nome": info["nome"],
                    "categoria": info["categoria"],
                    "emoji": info["emoji"],
                    "high": float(item.get("high", 0)),
                    "low": float(item.get("low", 0)),
                }
                log(f"  {info['nome']}: R$ {valor:,.2f} ({variacao:+.2f}%)", "OK")

    # --- PETRÓLEO (Brent e WTI) via Google News scraping de preço ---
    # Usamos a brapi para buscar ETFs de petróleo como proxy
    oil_etfs = {"PETR4": "Petrobras (proxy petróleo)"}
    for ticker, nome in oil_etfs.items():
        url = f"https://brapi.dev/api/quote/{ticker}"
        d = fetch_json(url, params=_brapi_params(), label=nome)
        if d and "results" in d and len(d["results"]) > 0:
            r = d["results"][0]
            dados[f"{ticker} (Petróleo)"] = {
                "valor": r.get("regularMarketPrice", 0),
                "variacao": r.get("regularMarketChangePercent", 0),
                "nome": nome,
                "categoria": "energia",
                "emoji": "🛢️",
            }
            log(f"  {nome}: R$ {r.get('regularMarketPrice',0):.2f} ({r.get('regularMarketChangePercent',0):+.2f}%)", "OK")

    # --- SELIC e IPCA via API do Banco Central do Brasil (SGS) ---
    # Série 432 = Selic Meta, Série 433 = IPCA mensal
    bcb_series = {
        "Selic Meta": {"serie": 432, "emoji": "📊", "categoria": "macro"},
        "IPCA Mensal": {"serie": 433, "emoji": "📈", "categoria": "macro"},
    }
    for nome_ind, info in bcb_series.items():
        url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{info['serie']}/dados/ultimos/1?formato=json"
        d = fetch_json(url, label=nome_ind)
        if d and len(d) > 0:
            valor = float(d[0].get("valor", "0").replace(",", "."))
            dados[nome_ind] = {
                "valor": valor,
                "variacao": 0,
                "nome": nome_ind,
                "categoria": info["categoria"],
                "emoji": info["emoji"],
                "data": d[0].get("data", ""),
            }
            unidade = "% a.a." if "Selic" in nome_ind else "%"
            log(f"  {nome_ind}: {valor:.2f}{unidade}", "OK")

    return dados


def coletar_indices():
    log("Buscando índices de mercado...")
    indices = {}
    for idx_ticker, idx_nome in [("^BVSP", "Ibovespa"), ("^IFIX", "IFIX")]:
        url = f"https://brapi.dev/api/quote/{idx_ticker}"
        d = fetch_json(url, params=_brapi_params(), label=idx_nome)
        if d and "results" in d and len(d["results"]) > 0:
            r = d["results"][0]
            indices[idx_nome] = {
                "valor": r.get("regularMarketPrice", 0),
                "variacao": r.get("regularMarketChangePercent", 0),
            }
            log(f"  {idx_nome}: {indices[idx_nome]['valor']:,.0f} pts ({indices[idx_nome]['variacao']:+.2f}%)", "OK")
    return indices


# ============================================================
# 3. SCANNER DE OPORTUNIDADES
# ============================================================
def escanear_oportunidades():
    log("Escaneando oportunidades de mercado...", "INFO")
    em_carteira = {a["ticker"] for a in CARTEIRA}
    acoes_scan = [t for t in WATCHLIST_ACOES if t not in em_carteira]
    fiis_scan = [t for t in WATCHLIST_FIIS if t not in em_carteira]
    etfs_scan = [t for t in WATCHLIST_ETFS if t not in em_carteira]

    resultados = {"acoes": {}, "fiis": {}, "etfs": {}}

    def buscar_lote(tickers, categoria):
        if not tickers:
            return
        for i in range(0, len(tickers), 8):
            lote = tickers[i:i+8]
            joined = ",".join(lote)
            log(f"  Buscando {categoria}: {joined}")
            url = f"https://brapi.dev/api/quote/{joined}"
            data = fetch_json(url, params=_brapi_params(fundamental="true", dividends="true"),
                              label=f"Scan {categoria}")
            if data and "results" in data:
                for item in data["results"]:
                    symbol = item.get("symbol", "")
                    resultados[categoria][symbol] = _parse_quote(item)
                    dy = resultados[categoria][symbol]["dividend_yield"]
                    log(f"    {symbol}: R$ {resultados[categoria][symbol]['preco']:.2f} | DY: {dy:.1f}%", "OK")
            time.sleep(1)

    buscar_lote(acoes_scan, "acoes")
    buscar_lote(fiis_scan, "fiis")
    buscar_lote(etfs_scan, "etfs")

    total = sum(len(v) for v in resultados.values())
    log(f"Scanner concluído: {total} ativos analisados", "OK")
    return resultados


# ============================================================
# 4. NOTÍCIAS
# ============================================================
def buscar_noticias_google(query):
    noticias = []
    try:
        url = "https://news.google.com/rss/search"
        params = {"q": query, "hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-419"}
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(r.content)
            items = root.findall(".//item")[:5]
            for item in items:
                title = item.find("title")
                pub_date = item.find("pubDate")
                link = item.find("link")
                if title is not None:
                    noticias.append({
                        "titulo": title.text or "",
                        "data": pub_date.text[:16] if pub_date is not None and pub_date.text else "",
                        "link": link.text if link is not None else "",
                    })
    except Exception:
        pass
    return noticias


# ============================================================
# 5. ANÁLISE COM CLAUDE AI
# ============================================================
def analisar_com_claude(carteira, cotacoes, commodities, indices,
                        noticias_macro, noticias_ativos, oportunidades=None):
    log("Enviando dados para Gemini AI analisar...", "AI")

    dados_carteira = []
    total_investido = 0
    total_atual = 0

    # Mapa de setores dos ativos (edite conforme necessário)
    SETOR_MAP = {
        # Carteira atual
        "VALE3": {"setor": "Mineração", "tipo": "Ação", "ciclico": True},
        "CMIG4": {"setor": "Energia Elétrica", "tipo": "Ação", "ciclico": False},
        "SAPR11": {"setor": "Saneamento", "tipo": "Ação", "ciclico": False},
        "MATD3": {"setor": "Saúde", "tipo": "Ação", "ciclico": False},
        # Watchlist ações
        "TAEE11": {"setor": "Energia - Transmissão", "tipo": "Ação", "ciclico": False},
        "ISAE4": {"setor": "Energia - Transmissão", "tipo": "Ação", "ciclico": False},
        "CPLE6": {"setor": "Energia Elétrica", "tipo": "Ação", "ciclico": False},
        "EGIE3": {"setor": "Energia Elétrica", "tipo": "Ação", "ciclico": False},
        "AURE3": {"setor": "Energia Elétrica", "tipo": "Ação", "ciclico": False},
        "ITUB4": {"setor": "Bancário", "tipo": "Ação", "ciclico": False},
        "BBAS3": {"setor": "Bancário", "tipo": "Ação", "ciclico": False},
        "BBSE3": {"setor": "Seguros", "tipo": "Ação", "ciclico": False},
        "CXSE3": {"setor": "Seguros", "tipo": "Ação", "ciclico": False},
        "BBDC4": {"setor": "Bancário", "tipo": "Ação", "ciclico": False},
        "TIMS3": {"setor": "Telecomunicações", "tipo": "Ação", "ciclico": False},
        "VIVT3": {"setor": "Telecomunicações", "tipo": "Ação", "ciclico": False},
        "SBSP3": {"setor": "Saneamento", "tipo": "Ação", "ciclico": False},
        "PSSA3": {"setor": "Seguros", "tipo": "Ação", "ciclico": False},
        "ALUP11": {"setor": "Energia - Transmissão", "tipo": "Ação", "ciclico": False},
        "ALOS3": {"setor": "Shoppings", "tipo": "Ação", "ciclico": True},
        # Watchlist FIIs
        "MXRF11": {"setor": "FII - Papel (CRI)", "tipo": "FII", "ciclico": False},
        "KNSC11": {"setor": "FII - Papel (CRI)", "tipo": "FII", "ciclico": False},
        "RBRR11": {"setor": "FII - Papel (CRI)", "tipo": "FII", "ciclico": False},
        "MCCI11": {"setor": "FII - Papel (CRI)", "tipo": "FII", "ciclico": False},
        "XPLG11": {"setor": "FII - Logística", "tipo": "FII", "ciclico": False},
        "HGLG11": {"setor": "FII - Logística", "tipo": "FII", "ciclico": False},
        "XPML11": {"setor": "FII - Shoppings", "tipo": "FII", "ciclico": True},
        "VISC11": {"setor": "FII - Shoppings", "tipo": "FII", "ciclico": True},
        "HGBS11": {"setor": "FII - Shoppings", "tipo": "FII", "ciclico": True},
        "KNRI11": {"setor": "FII - Lajes/Logística", "tipo": "FII", "ciclico": False},
        "JSAF11": {"setor": "FII - Fundo de Fundos", "tipo": "FII", "ciclico": False},
        # ETFs
        "DIVD11": {"setor": "ETF - Dividendos", "tipo": "ETF", "ciclico": False},
        "NDIV11": {"setor": "ETF - Dividendos", "tipo": "ETF", "ciclico": False},
        "DIVO11": {"setor": "ETF - Dividendos", "tipo": "ETF", "ciclico": False},
        "GOLD11": {"setor": "ETF - Ouro (hedge)", "tipo": "ETF", "ciclico": False},
        "BIAU39": {"setor": "BDR ETF - Ouro (hedge)", "tipo": "ETF", "ciclico": False},
        "BSLV39": {"setor": "BDR ETF - Prata (hedge)", "tipo": "ETF", "ciclico": False},
    }

    for ativo in carteira:
        t = ativo["ticker"]
        cot = cotacoes.get(t, {})
        preco_atual = cot.get("preco", 0)
        investido = ativo["quantidade"] * ativo["preco_medio"]
        valor_atual = ativo["quantidade"] * preco_atual
        lucro = valor_atual - investido
        lucro_pct = (lucro / investido * 100) if investido > 0 else 0
        total_investido += investido
        total_atual += valor_atual
        setor_info = SETOR_MAP.get(t, {"setor": "Outros", "tipo": "Ação", "ciclico": False})
        dados_carteira.append({
            "ticker": t, "nome": cot.get("nome_curto", t),
            "quantidade": ativo["quantidade"], "preco_medio": ativo["preco_medio"],
            "preco_atual": preco_atual, "investido": round(investido, 2),
            "valor_atual": round(valor_atual, 2),
            "lucro_reais": round(lucro, 2), "lucro_pct": round(lucro_pct, 2),
            "variacao_dia": cot.get("variacao_dia", 0),
            "dividend_yield": cot.get("dividend_yield", 0),
            "price_earnings": cot.get("price_earnings", 0),
            "max_52sem": cot.get("max_52sem", 0), "min_52sem": cot.get("min_52sem", 0),
            "volume": cot.get("volume", 0),
            "ultimos_dividendos": cot.get("dividendos_historico", [])[:5],
            "setor": setor_info["setor"],
            "tipo_ativo": setor_info["tipo"],
            "ciclico": setor_info["ciclico"],
        })

    # Calcula PESOS e CONCENTRAÇÃO SETORIAL
    composicao_setorial = {}
    composicao_tipo = {}
    peso_ciclico = 0
    peso_perene = 0
    for d in dados_carteira:
        pct = (d["valor_atual"] / total_atual * 100) if total_atual > 0 else 0
        d["peso_carteira_pct"] = round(pct, 2)
        setor = d["setor"]
        tipo = d["tipo_ativo"]
        composicao_setorial[setor] = composicao_setorial.get(setor, 0) + pct
        composicao_tipo[tipo] = composicao_tipo.get(tipo, 0) + pct
        if d["ciclico"]:
            peso_ciclico += pct
        else:
            peso_perene += pct

    analise_composicao = {
        "total_ativos": len(dados_carteira),
        "total_investido": round(total_investido, 2),
        "total_atual": round(total_atual, 2),
        "composicao_setorial": {k: round(v, 2) for k, v in sorted(composicao_setorial.items(), key=lambda x: -x[1])},
        "composicao_por_tipo": {k: round(v, 2) for k, v in composicao_tipo.items()},
        "peso_ciclico_pct": round(peso_ciclico, 2),
        "peso_perene_pct": round(peso_perene, 2),
        "maior_posicao": max(dados_carteira, key=lambda x: x["peso_carteira_pct"])["ticker"] if dados_carteira else "—",
        "maior_posicao_pct": max(d["peso_carteira_pct"] for d in dados_carteira) if dados_carteira else 0,
        "tem_fiis": any(d["tipo_ativo"] == "FII" for d in dados_carteira),
        "tem_etfs": any(d["tipo_ativo"] == "ETF" for d in dados_carteira),
        "tem_hedge": any("hedge" in d["setor"].lower() or "ouro" in d["setor"].lower() for d in dados_carteira),
        "dy_medio_carteira": round(sum(d["dividend_yield"] * d["peso_carteira_pct"] for d in dados_carteira) / 100, 2) if dados_carteira else 0,
    }

    opp_acoes = json.dumps(oportunidades.get("acoes", {}) if oportunidades else {}, indent=2, ensure_ascii=False)
    opp_fiis = json.dumps(oportunidades.get("fiis", {}) if oportunidades else {}, indent=2, ensure_ascii=False)
    opp_etfs = json.dumps(oportunidades.get("etfs", {}) if oportunidades else {}, indent=2, ensure_ascii=False)

    prompt = f"""Você é um analista financeiro sênior especializado no mercado brasileiro,
com profundo conhecimento das metodologias da Suno Research.

PERFIL DO INVESTIDOR:
- Perfil MODERADO, foco em DIVIDENDOS e renda passiva
- Aporta R$ 500/mês em renda variável
- Já tem bastante renda fixa (diversificação é o objetivo)
- Investidor de LONGO PRAZO, estratégia buy and hold

METODOLOGIA DE ANÁLISE (baseada nos Guias Suno):

1. MÉTODO BAZIN: Priorize ações com Dividend Yield > 6% nos últimos 12 meses.
2. MÉTODO BARSI: Foque em setores perenes (energia, saneamento, bancos, telecom).
   Empresas que entregam dividendos crescentes ao longo dos anos são as melhores.
3. QUALIDADE DO DIVIDENDO:
   - Payout Ratio ideal entre 25% e 80%. Acima de 100% é insustentável.
   - Dívida Líquida/EBITDA ideal < 2x, máximo 3x.
   - Fluxo de caixa operacional positivo e crescente.
   - ROE consistente.
4. VANTAGENS COMPETITIVAS: Marca forte, escala, receitas previsíveis, contratos longos.
5. SETORES CÍCLICOS vs PERENES:
   - Cíclicos (mineração, construção): voláteis, cuidado em crise.
   - Perenes (energia, saneamento, bancos): estáveis, ideais para dividendos.
6. SMALL CAPS: Podem complementar (5-15%), balanço sólido, endividamento controlado.
7. DIVERSIFICAÇÃO: Mínimo 8-15 ativos entre ações e FIIs.
   FIIs pagam dividendos mensais isentos de IR.
8. REINVESTIMENTO: 100% dos dividendos nos primeiros anos.

═══ CARTEIRA DO INVESTIDOR ═══
{json.dumps(dados_carteira, indent=2, ensure_ascii=False)}

Total Investido: R$ {total_investido:,.2f}
Valor Atual: R$ {total_atual:,.2f}
Resultado: R$ {total_atual - total_investido:,.2f} ({((total_atual/total_investido)-1)*100:.2f}%)

═══ COMPOSIÇÃO E CONCENTRAÇÃO DA CARTEIRA ═══
{json.dumps(analise_composicao, indent=2, ensure_ascii=False)}

ATENÇÃO: Analise CRITICAMENTE a composição acima. Verifique:
- Se há concentração excessiva em um único ativo (ideal: nenhum ativo > 20%)
- Se há concentração setorial (ideal: nenhum setor > 30%)
- Proporção cíclico vs perene (ideal para perfil moderado: máx 30% cíclico)
- Se faltam classes de ativos (FIIs, ETFs, hedge com ouro)
- Se o DY médio ponderado está adequado (ideal > 6% para estratégia de dividendos)
- Se a quantidade de ativos é suficiente (ideal 8-15 posições)
- CONSIDERE os pesos ao sugerir oportunidades: priorize setores SUB-REPRESENTADOS

═══ DADOS MACRO ═══
Commodities/Câmbio: {json.dumps(commodities, indent=2, ensure_ascii=False)}
Índices: {json.dumps(indices, indent=2, ensure_ascii=False)}

═══ NOTÍCIAS ═══
Macro: {json.dumps(noticias_macro, indent=2, ensure_ascii=False)}
Ativos: {json.dumps(noticias_ativos, indent=2, ensure_ascii=False)}

═══ OPORTUNIDADES (ativos fora da carteira) ═══
Ações: {opp_acoes}
FIIs: {opp_fiis}
ETFs: {opp_etfs}

Data: {datetime.now().strftime("%d/%m/%Y %H:%M")}

RESPONDA EM JSON VÁLIDO COM ESTA ESTRUTURA EXATA:
{{
  "resumo_geral": "Visão geral do mercado e da carteira hoje",
  "score_carteira": 7,
  "sentimento_mercado": "neutro|positivo|negativo",
  "analise_ativos": [
    {{
      "ticker": "VALE3",
      "recomendacao": "MANTER|COMPRAR|VENDER|AUMENTAR|REDUZIR",
      "score": 8,
      "analise": "Análise detalhada...",
      "riscos": "Riscos...",
      "pontos_positivos": "Pontos fortes...",
      "impacto_macro": "Impacto do macro..."
    }}
  ],
  "oportunidades_acoes": [
    {{
      "ticker": "ITUB4",
      "nome": "Itau Unibanco",
      "preco": 35.50,
      "dividend_yield": 6.5,
      "score": 9,
      "setor": "Bancário",
      "motivo": "Por que comprar...",
      "riscos": "Riscos...",
      "urgencia": "ALTA|MEDIA|BAIXA"
    }}
  ],
  "oportunidades_fiis": [
    {{
      "ticker": "MXRF11",
      "nome": "Maxi Renda",
      "preco": 10.50,
      "dividend_yield": 11.5,
      "score": 8,
      "tipo": "Papel|Tijolo|FoF|Híbrido",
      "motivo": "Por que comprar...",
      "riscos": "Riscos...",
      "urgencia": "ALTA|MEDIA|BAIXA"
    }}
  ],
  "oportunidades_etfs": [
    {{
      "ticker": "DIVD11",
      "nome": "ETF Dividendos",
      "preco": 65.00,
      "dividend_yield": 8.0,
      "score": 7,
      "motivo": "Vantagens...",
      "riscos": "Riscos..."
    }}
  ],
  "top3_comprar_agora": [
    {{
      "ticker": "TICKER",
      "tipo": "Ação|FII|ETF",
      "motivo_curto": "Frase curta",
      "valor_sugerido": 200
    }}
  ],
  "sugestao_aporte": "Como alocar os R$ 500 incluindo ativos novos e da carteira, CONSIDERANDO os pesos atuais e setores sub-representados",
  "analise_composicao": {{
    "diagnostico": "Análise da concentração atual, riscos de concentração setorial e o que está faltando",
    "setores_sobre_representados": ["Lista de setores com peso excessivo"],
    "setores_faltantes": ["Lista de setores importantes que faltam na carteira"],
    "classes_faltantes": ["Lista de classes de ativos que faltam (FII, ETF, hedge, internacional)"],
    "plano_diversificacao": "Plano de 3-6 meses para atingir diversificação ideal de 8-15 ativos"
  }},
  "alertas": ["Alertas importantes, incluindo alertas de concentração"],
  "proximos_eventos": ["Eventos para ficar de olho"]
}}

REGRAS:
- Máx 5 ações, 5 FIIs, 3 ETFs nas oportunidades (ordene por score, melhor primeiro)
- Priorize: DY > 6%, setores perenes, P/L razoável, vantagens competitivas
- FIIs: priorize desconto sobre VP e dividendos consistentes
- top3_comprar_agora: ranking final dos 3 melhores para HOJE
- Investidor tem R$ 500/mês, priorize ativos acessíveis
- APENAS JSON, sem markdown, sem backticks, sem texto extra."""

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
        r = requests.post(
            url,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": GEMINI_API_KEY,
            },
            json={
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "maxOutputTokens": 8192,
                    "temperature": 0.3,
                    "responseMimeType": "application/json",
                },
            },
            timeout=180,
        )
        if r.status_code != 200:
            log(f"Erro na API Gemini: {r.status_code} - {r.text[:300]}", "ERR")
            return None
        resp = r.json()
        # Gemini response: candidates[0].content.parts[0].text
        texto = ""
        candidates = resp.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            for part in parts:
                texto += part.get("text", "")
        texto = texto.strip()
        if texto.startswith("```"):
            texto = texto.split("\n", 1)[1] if "\n" in texto else texto[3:]
        if texto.endswith("```"):
            texto = texto[:-3]
        texto = texto.strip()
        analise = json.loads(texto)
        log("Análise Gemini recebida com sucesso!", "OK")
        return analise
    except json.JSONDecodeError as e:
        log(f"Erro ao parsear JSON do Gemini: {e}", "ERR")
        return None
    except Exception as e:
        log(f"Erro ao chamar Gemini: {e}", "ERR")
        return None


# ============================================================
# 6. GERAÇÃO DO DASHBOARD HTML
# ============================================================
def gerar_html(carteira, cotacoes, commodities, indices, analise, noticias_macro, noticias_ativos):
    agora = datetime.now().strftime("%d/%m/%Y às %H:%M")
    esc = html_module.escape

    total_investido = sum(a["quantidade"] * a["preco_medio"] for a in carteira)
    total_atual = sum(a["quantidade"] * cotacoes.get(a["ticker"], {}).get("preco", 0) for a in carteira)
    lucro_total = total_atual - total_investido
    lucro_pct = ((total_atual / total_investido) - 1) * 100 if total_investido > 0 else 0

    # Build dados_carteira with sector info for composition display
    SETOR_MAP_HTML = {
        "VALE3": {"setor": "Mineração", "ciclico": True},
        "CMIG4": {"setor": "Energia Elétrica", "ciclico": False},
        "SAPR11": {"setor": "Saneamento", "ciclico": False},
        "MATD3": {"setor": "Saúde", "ciclico": False},
    }
    dados_carteira = []
    for a in carteira:
        t = a["ticker"]
        cot = cotacoes.get(t, {})
        valor_atual = a["quantidade"] * cot.get("preco", 0)
        pct = (valor_atual / total_atual * 100) if total_atual > 0 else 0
        si = SETOR_MAP_HTML.get(t, {"setor": "Outros", "ciclico": False})
        dados_carteira.append({
            "ticker": t, "valor_atual": valor_atual,
            "peso_carteira_pct": round(pct, 2),
            "setor": si["setor"], "ciclico": si["ciclico"],
            "dividend_yield": cot.get("dividend_yield", 0),
        })

    sentimento = analise.get("sentimento_mercado", "neutro") if analise else "neutro"
    sent_color = {"positivo": "#22c55e", "negativo": "#ef4444", "neutro": "#f59e0b"}.get(sentimento, "#f59e0b")
    sent_emoji = {"positivo": "🟢", "negativo": "🔴", "neutro": "🟡"}.get(sentimento, "🟡")
    score_carteira = analise.get("score_carteira", "—") if analise else "—"
    lucro_color_total = "#22c55e" if lucro_total >= 0 else "#ef4444"

    # --- COMPOSIÇÃO DA CARTEIRA ---
    composicao_html = ""
    if analise and analise.get("analise_composicao"):
        ac = analise["analise_composicao"]
        composicao_html += f'<div class="analysis-section" style="margin-bottom:20px"><h4>🔍 Diagnóstico de Composição</h4><p>{esc(str(ac.get("diagnostico","")))}</p></div>'
        cols_html = ""
        sf = ac.get("setores_faltantes", [])
        if sf:
            cols_html += '<div class="analysis-col negative"><h4>📌 Setores Faltantes</h4><p>' + ", ".join(esc(str(s)) for s in sf) + '</p></div>'
        ss = ac.get("setores_sobre_representados", [])
        if ss:
            cols_html += '<div class="analysis-col" style="border-left:3px solid var(--red)"><h4 style="color:var(--red)">⚠️ Sobre-representados</h4><p>' + ", ".join(esc(str(s)) for s in ss) + '</p></div>'
        cf = ac.get("classes_faltantes", [])
        if cf:
            cols_html += '<div class="analysis-col positive"><h4>💡 Classes Faltantes</h4><p>' + ", ".join(esc(str(s)) for s in cf) + '</p></div>'
        if cols_html:
            composicao_html += f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px;margin-bottom:16px">{cols_html}</div>'
        plano = ac.get("plano_diversificacao", "")
        if plano:
            composicao_html += f'<div class="analysis-section macro"><h4>📋 Plano de Diversificação (3-6 meses)</h4><p>{esc(str(plano))}</p></div>'

    # Gera cards de peso por ativo
    pesos_html = ""
    for d in sorted(dados_carteira, key=lambda x: -x.get("peso_carteira_pct", 0)):
        pct = d.get("peso_carteira_pct", 0)
        bar_color = "var(--red)" if pct > 40 else ("var(--yellow)" if pct > 25 else "var(--green)")
        setor = d.get("setor", "")
        ciclico_tag = '<span style="color:var(--yellow);font-size:10px;margin-left:6px">⚡CÍCLICO</span>' if d.get("ciclico") else '<span style="color:var(--green);font-size:10px;margin-left:6px">🛡️PERENE</span>'
        pesos_html += f'''<div style="display:flex;align-items:center;gap:12px;padding:8px 0;border-bottom:1px solid var(--border)">
          <span style="font-family:'JetBrains Mono',monospace;font-weight:700;width:70px">{d["ticker"]}</span>
          <div style="flex:1">
            <div style="background:var(--bg4);border-radius:4px;height:20px;overflow:hidden">
              <div style="background:{bar_color};height:100%;width:{min(pct, 100):.0f}%;border-radius:4px;display:flex;align-items:center;padding-left:6px">
                <span style="font-size:11px;font-family:'JetBrains Mono',monospace;font-weight:700;color:var(--bg)">{pct:.1f}%</span>
              </div>
            </div>
          </div>
          <span style="font-size:11px;color:var(--text2);width:160px;text-align:right">{setor}{ciclico_tag}</span>
        </div>'''

    # --- ATIVOS CARDS ---
    ativos_html = ""
    analise_ativos = {a["ticker"]: a for a in analise.get("analise_ativos", [])} if analise else {}
    for ativo in carteira:
        t = ativo["ticker"]
        cot = cotacoes.get(t, {})
        an = analise_ativos.get(t, {})
        preco = cot.get("preco", 0)
        investido = ativo["quantidade"] * ativo["preco_medio"]
        valor_atual = ativo["quantidade"] * preco
        lucro = valor_atual - investido
        lucro_p = (lucro / investido * 100) if investido > 0 else 0
        var_dia = cot.get("variacao_dia", 0)
        dy = cot.get("dividend_yield", 0)
        pe = cot.get("price_earnings", 0)
        rec = an.get("recomendacao", "—")
        rec_colors = {"COMPRAR": ("#22c55e", "↑"), "AUMENTAR": ("#22c55e", "↑"),
                      "MANTER": ("#f59e0b", "→"), "VENDER": ("#ef4444", "↓"), "REDUZIR": ("#ef4444", "↓")}
        rec_color, rec_arrow = rec_colors.get(rec, ("#94a3b8", "•"))
        lc = "#22c55e" if lucro >= 0 else "#ef4444"
        vc = "#22c55e" if var_dia >= 0 else "#ef4444"
        divs = cot.get("dividendos_historico", [])[:5]
        divs_html = ""
        for div in divs:
            dd = div.get("paymentDate", div.get("approvedDate", ""))[:10] if (div.get("paymentDate") or div.get("approvedDate")) else "—"
            dv = div.get("rate", div.get("value", 0))
            dt = div.get("label", div.get("type", ""))
            divs_html += f'<div class="div-row"><span class="div-date">{dd}</span><span class="div-val">R$ {dv:.4f}</span><span class="div-type">{dt}</span></div>'
        if not divs_html:
            divs_html = '<div class="div-row"><span style="color:var(--text2);font-style:italic">Sem dados recentes</span></div>'
        ativos_html += f"""
        <div class="ativo-card">
          <div class="ativo-header">
            <div><h3 style="font-family:'JetBrains Mono',monospace;font-size:22px;font-weight:700">{t}</h3>
            <span style="color:var(--text2);font-size:13px">{esc(cot.get('nome_curto', t))}</span></div>
            <div class="recomendacao" style="background:{rec_color}20;color:{rec_color};border:1px solid {rec_color}40;padding:6px 16px;border-radius:8px;font-family:'JetBrains Mono',monospace;font-size:14px;font-weight:700">{rec_arrow} {rec}</div>
          </div>
          <div class="ativo-metrics">
            <div class="metric-box"><span class="metric-label">Preço Atual</span><span class="metric-value">R$ {preco:.2f}</span><span class="metric-sub" style="color:{vc}">{var_dia:+.2f}% hoje</span></div>
            <div class="metric-box"><span class="metric-label">Resultado</span><span class="metric-value" style="color:{lc}">R$ {lucro:+,.2f}</span><span class="metric-sub" style="color:{lc}">{lucro_p:+.2f}%</span></div>
            <div class="metric-box"><span class="metric-label">Qtd × PM</span><span class="metric-value">{ativo['quantidade']} × R$ {ativo['preco_medio']:.2f}</span><span class="metric-sub">Invest: R$ {investido:,.2f}</span></div>
            <div class="metric-box"><span class="metric-label">Score / DY</span><span class="metric-value">{an.get('score','—')}/10</span><span class="metric-sub">DY: {dy:.1f}% | P/L: {pe:.1f}</span></div>
          </div>
          <div style="margin-bottom:16px">
            <div class="analysis-section"><h4>📊 Análise</h4><p>{esc(an.get('analise', 'Análise não disponível'))}</p></div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px">
              <div class="analysis-col positive"><h4>✅ Pontos Positivos</h4><p>{esc(an.get('pontos_positivos', '—'))}</p></div>
              <div class="analysis-col negative"><h4>⚠️ Riscos</h4><p>{esc(an.get('riscos', '—'))}</p></div>
            </div>
            <div class="analysis-section macro"><h4>🌍 Impacto Macro</h4><p>{esc(an.get('impacto_macro', '—'))}</p></div>
          </div>
          <div class="dividendos-section"><h4>💰 Últimos Dividendos</h4><div>{divs_html}</div></div>
        </div>"""

    # --- OPORTUNIDADES ---
    oportunidades_html = ""
    if analise:
        # TOP 3
        top3 = analise.get("top3_comprar_agora", [])
        if top3:
            oportunidades_html += '<div style="margin-bottom:24px"><h3 style="font-family:\'JetBrains Mono\',monospace;font-size:16px;color:#22c55e;margin-bottom:12px">🏆 Top 3 — Comprar Agora</h3><div class="top3-grid">'
            for i, item in enumerate(top3, 1):
                oportunidades_html += f'''<div class="top3-card">
                  <span class="top3-rank">#{i}</span>
                  <div class="top3-ticker">{esc(str(item.get("ticker","")))}</div>
                  <div class="top3-tipo">{esc(str(item.get("tipo","")))}</div>
                  <div class="top3-motivo">{esc(str(item.get("motivo_curto","")))}</div>
                  <div class="top3-valor">Sugestão: R$ {item.get("valor_sugerido",0):,.0f}</div>
                </div>'''
            oportunidades_html += '</div></div>'

        for cat, cat_label in [("oportunidades_acoes", "📈 Ações Recomendadas"), ("oportunidades_fiis", "🏢 FIIs Recomendados"), ("oportunidades_etfs", "📦 ETFs Recomendados")]:
            items = analise.get(cat, [])
            if items:
                oportunidades_html += f'<div style="margin-bottom:24px"><h3 style="font-family:\'JetBrains Mono\',monospace;font-size:16px;color:var(--accent);margin-bottom:12px">{cat_label}</h3><div class="opp-grid">'
                for item in items:
                    urg = str(item.get("urgencia", "")).lower()
                    urg_class = urg if urg in ("alta", "media", "baixa") else "media"
                    urg_label = urg.upper() if urg else "—"
                    d_y = item.get("dividend_yield", 0)
                    sc = item.get("score", 0)
                    oportunidades_html += f'''<div class="opp-card">
                      <div class="opp-card-header">
                        <span class="opp-ticker">{esc(str(item.get("ticker","")))}</span>
                        <span class="opp-badge {urg_class}">{urg_label}</span>
                      </div>
                      <div style="font-size:12px;color:var(--text2);margin-bottom:10px">{esc(str(item.get("nome","")))}</div>
                      <div class="opp-metrics">
                        <div class="opp-metric"><span class="label">Preço</span><span class="val">R$ {item.get("preco",0):.2f}</span></div>
                        <div class="opp-metric"><span class="label">DY</span><span class="val" style="color:var(--green)">{d_y:.1f}%</span></div>
                        <div class="opp-metric"><span class="label">Score</span><span class="val">{sc}/10</span></div>
                      </div>
                      <div style="font-size:13px;color:var(--text2);line-height:1.6;margin-bottom:8px">{esc(str(item.get("motivo","")))}</div>
                      <div style="font-size:12px;color:var(--yellow);background:#f59e0b08;padding:8px;border-radius:6px">⚠️ {esc(str(item.get("riscos","")))}</div>
                    </div>'''
                oportunidades_html += '</div></div>'

    if not oportunidades_html:
        oportunidades_html = '<p style="color:var(--text2)">Configure BRAPI_TOKEN e GEMINI_API_KEY para ver oportunidades.</p>'

    # --- MACRO ---
    commodities_html = ""
    # Group by categoria
    categorias_order = ["cambio", "metal", "energia", "crypto", "macro"]
    cat_labels = {"cambio": "💱 Câmbio", "metal": "🥇 Metais", "energia": "🛢️ Energia", "crypto": "₿ Crypto", "macro": "📊 Indicadores"}
    for cat in categorias_order:
        items_cat = [(k, v) for k, v in commodities.items() if v.get("categoria") == cat]
        if not items_cat:
            continue
        for key, val in items_cat:
            vc2 = "#22c55e" if val.get("variacao", 0) >= 0 else "#ef4444"
            emoji = val.get("emoji", "")
            is_macro = cat == "macro"
            if is_macro:
                unidade = "% a.a." if "Selic" in key else "%"
                val_str = f'{val["valor"]:.2f}{unidade}'
                var_str = val.get("data", "")
            else:
                val_str = f'R$ {val["valor"]:,.2f}'
                var_str = f'{val["variacao"]:+.2f}%'
            commodities_html += f'<div class="commodity-card"><span class="comm-name">{emoji} {key}</span><span class="comm-val">{val_str}</span><span class="comm-var" style="color:{vc2 if not is_macro else "var(--text2)"}">{var_str}</span></div>'
    indices_html = ""
    for key, val in indices.items():
        vic = "#22c55e" if val.get("variacao", 0) >= 0 else "#ef4444"
        indices_html += f'<div class="commodity-card indice"><span class="comm-name">{key}</span><span class="comm-val">{val["valor"]:,.0f}</span><span class="comm-var" style="color:{vic}">{val["variacao"]:+.2f}%</span></div>'

    # --- NOTÍCIAS ---
    noticias_html = ""
    for n in (noticias_macro + noticias_ativos)[:10]:
        la = f'href="{esc(n["link"])}" target="_blank"' if n.get("link") else 'href="#"'
        noticias_html += f'<a class="news-item" {la}><span class="news-title">{esc(n.get("titulo",""))}</span><span class="news-date">{esc(n.get("data",""))}</span></a>'

    # --- ALERTAS / EVENTOS ---
    alertas_html = "".join(f'<div class="alerta-item">⚡ {esc(a)}</div>' for a in (analise.get("alertas", []) if analise else []))
    eventos_html = "".join(f'<div class="evento-item">📅 {esc(e)}</div>' for e in (analise.get("proximos_eventos", []) if analise else []))
    sugestao = esc(analise.get("sugestao_aporte", "Análise não disponível")) if analise else "Configure as chaves de API."
    resumo = esc(analise.get("resumo_geral", "")) if analise else "Configure BRAPI_TOKEN e GEMINI_API_KEY para análises."

    html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Analisador de Carteira v2.1 — {agora}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=DM+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {{ --bg:#0a0e17;--bg2:#111827;--bg3:#1a2235;--bg4:#243049;--text:#e2e8f0;--text2:#94a3b8;--accent:#3b82f6;--accent2:#8b5cf6;--green:#22c55e;--red:#ef4444;--yellow:#f59e0b;--border:#1e293b; }}
  * {{ margin:0;padding:0;box-sizing:border-box; }}
  body {{ font-family:'DM Sans',sans-serif;background:var(--bg);color:var(--text);line-height:1.6; }}
  .container {{ max-width:1400px;margin:0 auto;padding:24px; }}
  .header {{ background:linear-gradient(135deg,var(--bg2),var(--bg3));border:1px solid var(--border);border-radius:16px;padding:32px;margin-bottom:24px;position:relative;overflow:hidden; }}
  .header::before {{ content:'';position:absolute;top:-50%;right:-20%;width:400px;height:400px;background:radial-gradient(circle,{sent_color}10 0%,transparent 70%);pointer-events:none; }}
  .header-top {{ display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:16px; }}
  .header h1 {{ font-family:'JetBrains Mono',monospace;font-size:28px;font-weight:700;background:linear-gradient(135deg,var(--accent),var(--accent2));-webkit-background-clip:text;-webkit-text-fill-color:transparent; }}
  .header .date {{ color:var(--text2);font-size:14px;margin-top:4px; }}
  .sentimento {{ display:flex;align-items:center;gap:8px;padding:8px 16px;border-radius:8px;background:{sent_color}15;border:1px solid {sent_color}30;font-weight:600;color:{sent_color}; }}
  .resumo {{ margin-top:20px;color:var(--text2);font-size:15px;line-height:1.7; }}
  .totals {{ display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;margin-bottom:24px; }}
  .total-card {{ background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:20px;text-align:center; }}
  .total-card .label {{ font-size:12px;color:var(--text2);text-transform:uppercase;letter-spacing:1px; }}
  .total-card .value {{ font-family:'JetBrains Mono',monospace;font-size:24px;font-weight:700;margin-top:8px; }}
  .macro-row {{ display:flex;gap:12px;flex-wrap:wrap;margin-bottom:24px; }}
  .commodity-card {{ background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:14px 18px;display:flex;align-items:center;gap:12px;flex:1;min-width:180px; }}
  .commodity-card.indice {{ border-left:3px solid var(--accent); }}
  .comm-name {{ font-size:13px;color:var(--text2);font-weight:600; }}
  .comm-val {{ font-family:'JetBrains Mono',monospace;font-weight:700;font-size:15px; }}
  .comm-var {{ font-family:'JetBrains Mono',monospace;font-size:13px;font-weight:600; }}
  .ativo-card {{ background:var(--bg2);border:1px solid var(--border);border-radius:16px;padding:28px;margin-bottom:20px;transition:border-color .2s; }}
  .ativo-card:hover {{ border-color:var(--accent); }}
  .ativo-header {{ display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;flex-wrap:wrap;gap:12px; }}
  .ativo-metrics {{ display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:16px;margin-bottom:20px; }}
  .metric-box {{ background:var(--bg3);border-radius:10px;padding:14px; }}
  .metric-label {{ font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:.8px;display:block; }}
  .metric-value {{ font-family:'JetBrains Mono',monospace;font-size:18px;font-weight:700;display:block;margin-top:6px; }}
  .metric-sub {{ font-family:'JetBrains Mono',monospace;font-size:12px;display:block;margin-top:4px; }}
  .analysis-section {{ background:var(--bg3);border-radius:10px;padding:16px;margin-bottom:12px; }}
  .analysis-section.macro {{ border-left:3px solid var(--accent2); }}
  .analysis-section h4 {{ font-size:13px;color:var(--accent);margin-bottom:8px; }}
  .analysis-section p {{ font-size:14px;color:var(--text2);line-height:1.7; }}
  .analysis-col {{ background:var(--bg3);border-radius:10px;padding:16px; }}
  .analysis-col h4 {{ font-size:13px;margin-bottom:8px; }}
  .analysis-col.positive {{ border-left:3px solid var(--green); }}
  .analysis-col.positive h4 {{ color:var(--green); }}
  .analysis-col.negative {{ border-left:3px solid var(--yellow); }}
  .analysis-col.negative h4 {{ color:var(--yellow); }}
  .analysis-col p {{ font-size:13px;color:var(--text2);line-height:1.6; }}
  .dividendos-section {{ background:var(--bg3);border-radius:10px;padding:16px; }}
  .dividendos-section h4 {{ font-size:13px;color:var(--accent);margin-bottom:10px; }}
  .div-row {{ display:flex;gap:16px;padding:6px 0;border-bottom:1px solid var(--bg4);font-size:13px; }}
  .div-row:last-child {{ border-bottom:none; }}
  .div-date {{ color:var(--text2);width:100px;font-family:'JetBrains Mono',monospace; }}
  .div-val {{ color:var(--green);font-family:'JetBrains Mono',monospace;font-weight:600;width:120px; }}
  .div-type {{ color:var(--text2);font-size:12px; }}
  .opp-grid {{ display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px; }}
  .opp-card {{ background:var(--bg2);border:1px solid var(--border);border-radius:14px;padding:20px;transition:border-color .2s,transform .15s; }}
  .opp-card:hover {{ border-color:var(--green);transform:translateY(-2px); }}
  .opp-card-header {{ display:flex;justify-content:space-between;align-items:center;margin-bottom:12px; }}
  .opp-ticker {{ font-family:'JetBrains Mono',monospace;font-size:18px;font-weight:700; }}
  .opp-badge {{ padding:4px 10px;border-radius:6px;font-size:11px;font-weight:700;font-family:'JetBrains Mono',monospace; }}
  .opp-badge.alta {{ background:#22c55e20;color:#22c55e;border:1px solid #22c55e40; }}
  .opp-badge.media {{ background:#f59e0b20;color:#f59e0b;border:1px solid #f59e0b40; }}
  .opp-badge.baixa {{ background:var(--bg4);color:var(--text2);border:1px solid var(--border); }}
  .opp-metrics {{ display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:12px; }}
  .opp-metric {{ text-align:center;background:var(--bg3);border-radius:8px;padding:8px 4px; }}
  .opp-metric .label {{ font-size:10px;color:var(--text2);text-transform:uppercase;letter-spacing:.5px; }}
  .opp-metric .val {{ font-family:'JetBrains Mono',monospace;font-size:14px;font-weight:700;display:block;margin-top:2px; }}
  .top3-grid {{ display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px; }}
  .top3-card {{ background:linear-gradient(135deg,var(--bg2),var(--bg3));border:2px solid var(--green);border-radius:14px;padding:24px;position:relative;overflow:hidden; }}
  .top3-card::before {{ content:'';position:absolute;top:-30%;right:-15%;width:200px;height:200px;background:radial-gradient(circle,#22c55e10 0%,transparent 70%);pointer-events:none; }}
  .top3-rank {{ font-family:'JetBrains Mono',monospace;font-size:40px;font-weight:700;color:var(--green);opacity:.3;position:absolute;top:10px;right:18px; }}
  .top3-ticker {{ font-family:'JetBrains Mono',monospace;font-size:22px;font-weight:700;color:var(--green); }}
  .top3-tipo {{ font-size:11px;color:var(--text2);margin:4px 0 12px; }}
  .top3-motivo {{ font-size:14px;color:var(--text);line-height:1.6; }}
  .top3-valor {{ margin-top:12px;font-family:'JetBrains Mono',monospace;font-size:16px;color:var(--green);font-weight:700; }}
  .grid-bottom {{ display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:24px; }}
  .side-card {{ background:var(--bg2);border:1px solid var(--border);border-radius:14px;padding:24px; }}
  .side-card h3 {{ font-family:'JetBrains Mono',monospace;font-size:16px;margin-bottom:16px;color:var(--accent); }}
  .sugestao {{ background:linear-gradient(135deg,var(--bg2),var(--bg3));border:1px solid var(--accent);border-radius:14px;padding:24px;margin-top:24px; }}
  .sugestao h3 {{ font-family:'JetBrains Mono',monospace;font-size:16px;color:var(--accent);margin-bottom:12px; }}
  .sugestao p {{ color:var(--text2);font-size:14px;line-height:1.7; }}
  .alerta-item {{ background:#ef444410;border-left:3px solid var(--red);padding:10px 14px;margin-bottom:8px;border-radius:0 8px 8px 0;font-size:13px; }}
  .evento-item {{ padding:10px 14px;margin-bottom:8px;background:var(--bg3);border-radius:8px;font-size:13px;color:var(--text2); }}
  .news-item {{ display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid var(--border);text-decoration:none;transition:background .15s;gap:12px; }}
  .news-item:hover {{ background:var(--bg3);border-radius:8px;padding-left:8px; }}
  .news-title {{ font-size:13px;color:var(--text); }}
  .news-date {{ font-size:11px;color:var(--text2);white-space:nowrap; }}
  .fontes {{ background:var(--bg2);border:1px solid var(--border);border-radius:14px;padding:24px;margin-top:24px; }}
  .fontes h3 {{ font-family:'JetBrains Mono',monospace;font-size:16px;color:var(--accent);margin-bottom:12px; }}
  .fonte-item {{ display:flex;align-items:center;gap:8px;margin-bottom:6px;font-size:13px; }}
  .fonte-item a {{ color:var(--accent);text-decoration:none; }}
  .fonte-badge {{ background:var(--bg4);padding:2px 8px;border-radius:4px;font-size:11px;color:var(--text2);font-family:'JetBrains Mono',monospace; }}
  .footer {{ text-align:center;padding:32px;color:var(--text2);font-size:12px;border-top:1px solid var(--border);margin-top:32px; }}
  .footer a {{ color:var(--accent);text-decoration:none; }}
  @media (max-width:768px) {{ .header h1 {{ font-size:20px; }} .grid-bottom,.analysis-columns {{ grid-template-columns:1fr; }} .container {{ padding:12px; }} .opp-grid {{ grid-template-columns:1fr; }} .top3-grid {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div class="header-top">
      <div><h1>📈 Analisador de Carteira v2.1</h1><div class="date">Relatório gerado em {agora}</div></div>
      <div class="sentimento">{sent_emoji} Mercado {sentimento.upper()}</div>
    </div>
    <div class="resumo">{resumo}</div>
  </div>
  <div class="totals">
    <div class="total-card"><div class="label">Investido</div><div class="value">R$ {total_investido:,.2f}</div></div>
    <div class="total-card"><div class="label">Valor Atual</div><div class="value">R$ {total_atual:,.2f}</div></div>
    <div class="total-card"><div class="label">Resultado</div><div class="value" style="color:{lucro_color_total}">R$ {lucro_total:+,.2f}</div></div>
    <div class="total-card"><div class="label">Rentabilidade</div><div class="value" style="color:{lucro_color_total}">{lucro_pct:+.2f}%</div></div>
    <div class="total-card"><div class="label">Score Carteira</div><div class="value" style="color:var(--accent)">{score_carteira}/10</div></div>
  </div>
  <div class="macro-row">{indices_html}{commodities_html}</div>

  <h2 style="font-family:'JetBrains Mono',monospace;font-size:20px;margin-bottom:16px">⚖️ Composição da Carteira</h2>
  <div class="ativo-card" style="margin-bottom:24px">
    <div style="margin-bottom:16px">{pesos_html}</div>
    {composicao_html}
  </div>

  <h2 style="font-family:'JetBrains Mono',monospace;font-size:20px;margin-bottom:16px">🏦 Análise por Ativo</h2>
  {ativos_html}

  <h2 style="font-family:'JetBrains Mono',monospace;font-size:20px;margin:32px 0 16px;background:linear-gradient(135deg,var(--green),var(--accent));-webkit-background-clip:text;-webkit-text-fill-color:transparent">🎯 Oportunidades de Mercado</h2>
  {oportunidades_html}

  <div class="sugestao"><h3>💡 Sugestão de Aporte Mensal (R$ 500)</h3><p>{sugestao}</p></div>

  <div class="grid-bottom">
    <div class="side-card"><h3>⚡ Alertas</h3>{alertas_html if alertas_html else '<p style="color:var(--text2);font-size:13px">Nenhum alerta</p>'}</div>
    <div class="side-card"><h3>📅 Próximos Eventos</h3>{eventos_html if eventos_html else '<p style="color:var(--text2);font-size:13px">Nenhum evento</p>'}</div>
  </div>

  <div class="side-card" style="margin-top:20px"><h3>📰 Notícias Relevantes</h3>{noticias_html if noticias_html else '<p style="color:var(--text2);font-size:13px">Nenhuma notícia</p>'}</div>

  <div class="fontes">
    <h3>📋 Fontes de Dados</h3>
    <div class="fonte-item"><span class="fonte-badge">COTAÇÕES</span> <a href="https://brapi.dev">brapi.dev</a> — Cotações, dividendos, fundamentalista</div>
    <div class="fonte-item"><span class="fonte-badge">CÂMBIO</span> <a href="https://brapi.dev/docs/moedas">brapi.dev/currency</a> — USD/BRL, EUR/BRL</div>
    <div class="fonte-item"><span class="fonte-badge">METAIS</span> <a href="https://docs.awesomeapi.com.br">AwesomeAPI</a> — Ouro (XAU), Prata (XAG) em tempo real</div>
    <div class="fonte-item"><span class="fonte-badge">ENERGIA</span> <a href="https://brapi.dev">brapi.dev</a> — Petrobras (PETR4) como proxy de petróleo</div>
    <div class="fonte-item"><span class="fonte-badge">MACRO</span> <a href="https://dadosabertos.bcb.gov.br">API BCB (SGS)</a> — Selic Meta, IPCA mensal</div>
    <div class="fonte-item"><span class="fonte-badge">SCANNER</span> <a href="https://brapi.dev">brapi.dev</a> — {len(WATCHLIST_ACOES)} ações + {len(WATCHLIST_FIIS)} FIIs + {len(WATCHLIST_ETFS)} ETFs monitorados</div>
    <div class="fonte-item"><span class="fonte-badge">NOTÍCIAS</span> <a href="https://news.google.com">Google News RSS</a> — Notícias macro e por ativo</div>
    <div class="fonte-item"><span class="fonte-badge">ANÁLISE IA</span> <a href="https://ai.google.dev">Gemini AI (Google)</a> — Análise com metodologia Suno Research</div>
    <div class="fonte-item"><span class="fonte-badge">MÉTODO</span> Guia Suno Dividendos (Bazin/Barsi) + Guia Small Caps + 101 Perguntas</div>
  </div>

  <div class="footer">
    <p>⚠️ Este relatório é meramente informativo e NÃO constitui recomendação de investimento.</p>
    <p>Sempre consulte um assessor certificado. Dados com delay de até 15 min.</p>
    <p style="margin-top:8px">Gerado por <strong>Analisador de Carteira v2.1</strong> — <a href="https://brapi.dev">brapi.dev</a> + <a href="https://ai.google.dev">Gemini AI</a></p>
  </div>
</div>
</body>
</html>"""
    return html_content


# ============================================================
# MAIN
# ============================================================
def main():
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║      ANALISADOR INTELIGENTE DE CARTEIRA v2.0                 ║")
    print("║  Carteira + Oportunidades + Análise IA (Suno)               ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()

    if GEMINI_API_KEY in ("", "COLOQUE_SUA_CHAVE_GEMINI_AQUI"):
        log("GEMINI_API_KEY não configurada! Análise IA omitida.", "WARN")
        log("Configure: export GEMINI_API_KEY='sua-chave-gemini'", "WARN")
        print()

    # 1. Cotações da carteira
    cotacoes = coletar_cotacoes(CARTEIRA)
    if not cotacoes:
        log("Não foi possível obter cotações. Abortando.", "ERR")
        sys.exit(1)

    # 2. Macro
    commodities = coletar_commodities()
    indices = coletar_indices()

    # 3. Scanner de oportunidades
    oportunidades = escanear_oportunidades()

    # 4. Notícias
    noticias_macro = buscar_noticias_google("mercado financeiro Brasil economia Selic")
    noticias_ativos = []
    for ativo in CARTEIRA:
        nome = cotacoes.get(ativo["ticker"], {}).get("nome_curto", ativo["ticker"])
        news = buscar_noticias_google(f"{ativo['ticker']} {nome} ações dividendos")
        noticias_ativos.extend(news)
    seen = set()
    noticias_ativos = [n for n in noticias_ativos if n["titulo"] not in seen and not seen.add(n["titulo"])][:10]

    # 5. Análise IA
    analise = None
    if GEMINI_API_KEY not in ("", "COLOQUE_SUA_CHAVE_GEMINI_AQUI"):
        analise = analisar_com_claude(CARTEIRA, cotacoes, commodities, indices,
                                      noticias_macro, noticias_ativos, oportunidades)

    # 6. Gerar HTML
    log("Gerando dashboard HTML...")
    html = gerar_html(CARTEIRA, cotacoes, commodities, indices, analise, noticias_macro, noticias_ativos)

    filename = f"relatorio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    filepath = OUTPUT_DIR / filename
    filepath.write_text(html, encoding="utf-8")
    log(f"Dashboard salvo: {filepath}", "OK")

    latest = OUTPUT_DIR / "relatorio_latest.html"
    latest.write_text(html, encoding="utf-8")
    log(f"Link rápido: {latest}", "OK")

    print()
    print(f"  🎯 Abra no navegador: file://{filepath.resolve()}")
    print()
    return filepath


if __name__ == "__main__":
    main()
