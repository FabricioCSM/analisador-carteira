#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ANALISADOR INTELIGENTE DE CARTEIRA v2.2
# 100% APIs gratuitas (yfinance + AwesomeAPI + BCB) + Gemini AI
# See full documentation in the repository README.md

import requests, json, os, sys, time, html as html_module
from datetime import datetime
from pathlib import Path

# Carteira é carregada do arquivo carteira.json (editável pelo painel web)
_carteira_file = Path(__file__).parent / "carteira.json"
if _carteira_file.exists():
    CARTEIRA = json.loads(_carteira_file.read_text(encoding="utf-8"))
else:
    # Carteira padrão (será usada se carteira.json não existir)
    CARTEIRA = [
        {"ticker": "VALE3",  "quantidade": 7,  "preco_medio": 79.50},
        {"ticker": "CMIG4",  "quantidade": 17, "preco_medio": 12.00},
        {"ticker": "SAPR11", "quantidade": 3,  "preco_medio": 40.87},
        {"ticker": "MATD3",  "quantidade": 20, "preco_medio": 5.78},
    ]
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
WATCHLIST_ACOES = ["TAEE11","ISAE4","CPLE6","EGIE3","AURE3","ITUB4","BBAS3","BBSE3","CXSE3","BBDC4","TIMS3","VIVT3","SBSP3","PSSA3","ALUP11","ALOS3"]
WATCHLIST_FIIS = ["MXRF11","KNSC11","RBRR11","MCCI11","XPLG11","HGLG11","XPML11","VISC11","HGBS11","KNRI11","JSAF11"]
WATCHLIST_ETFS = ["DIVD11","NDIV11","DIVO11","GOLD11","BIAU39","BSLV39"]
OUTPUT_DIR = Path(__file__).parent / "relatorios"
OUTPUT_DIR.mkdir(exist_ok=True)
SETOR_MAP = {"VALE3":{"setor":"Mineração","tipo":"Ação","ciclico":True},"CMIG4":{"setor":"Energia","tipo":"Ação","ciclico":False},"SAPR11":{"setor":"Saneamento","tipo":"Ação","ciclico":False},"MATD3":{"setor":"Saúde","tipo":"Ação","ciclico":False},"TAEE11":{"setor":"Transmissão","tipo":"Ação","ciclico":False},"ISAE4":{"setor":"Transmissão","tipo":"Ação","ciclico":False},"CPLE6":{"setor":"Energia","tipo":"Ação","ciclico":False},"EGIE3":{"setor":"Energia","tipo":"Ação","ciclico":False},"AURE3":{"setor":"Energia","tipo":"Ação","ciclico":False},"ITUB4":{"setor":"Bancário","tipo":"Ação","ciclico":False},"BBAS3":{"setor":"Bancário","tipo":"Ação","ciclico":False},"BBSE3":{"setor":"Seguros","tipo":"Ação","ciclico":False},"CXSE3":{"setor":"Seguros","tipo":"Ação","ciclico":False},"BBDC4":{"setor":"Bancário","tipo":"Ação","ciclico":False},"TIMS3":{"setor":"Telecom","tipo":"Ação","ciclico":False},"VIVT3":{"setor":"Telecom","tipo":"Ação","ciclico":False},"SBSP3":{"setor":"Saneamento","tipo":"Ação","ciclico":False},"PSSA3":{"setor":"Seguros","tipo":"Ação","ciclico":False},"ALUP11":{"setor":"Transmissão","tipo":"Ação","ciclico":False},"ALOS3":{"setor":"Shoppings","tipo":"Ação","ciclico":True},"MXRF11":{"setor":"FII Papel","tipo":"FII","ciclico":False},"KNSC11":{"setor":"FII Papel","tipo":"FII","ciclico":False},"RBRR11":{"setor":"FII Papel","tipo":"FII","ciclico":False},"MCCI11":{"setor":"FII Papel","tipo":"FII","ciclico":False},"XPLG11":{"setor":"FII Log","tipo":"FII","ciclico":False},"HGLG11":{"setor":"FII Log","tipo":"FII","ciclico":False},"XPML11":{"setor":"FII Shop","tipo":"FII","ciclico":True},"VISC11":{"setor":"FII Shop","tipo":"FII","ciclico":True},"HGBS11":{"setor":"FII Shop","tipo":"FII","ciclico":True},"KNRI11":{"setor":"FII Lajes","tipo":"FII","ciclico":False},"JSAF11":{"setor":"FII FoF","tipo":"FII","ciclico":False},"DIVD11":{"setor":"ETF Div","tipo":"ETF","ciclico":False},"NDIV11":{"setor":"ETF Div","tipo":"ETF","ciclico":False},"DIVO11":{"setor":"ETF Div","tipo":"ETF","ciclico":False},"GOLD11":{"setor":"ETF Ouro","tipo":"ETF","ciclico":False},"BIAU39":{"setor":"BDR Ouro","tipo":"ETF","ciclico":False},"BSLV39":{"setor":"BDR Prata","tipo":"ETF","ciclico":False}}

def log(msg, level="INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    icons = {"INFO":"📊","OK":"✅","WARN":"⚠️","ERR":"❌","AI":"🤖"}
    print(f"  {icons.get(level,'•')} [{ts}] {msg}")

def fetch_json(url, params=None, label=""):
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=20)
            if r.status_code == 200: return r.json()
            else: log(f"{label} HTTP {r.status_code} (tentativa {attempt+1})", "WARN")
        except Exception as e: log(f"{label} Erro: {e} (tentativa {attempt+1})", "WARN")
        time.sleep(2)
    log(f"{label} Falhou", "ERR")
    return None

def coletar_cotacoes_yf(tickers_list):
    import yfinance as yf
    resultados = {}
    for ticker in tickers_list:
        try:
            t = yf.Ticker(f"{ticker}.SA")
            info = t.info
            preco = info.get("regularMarketPrice") or info.get("currentPrice", 0)
            if not preco: log(f"  {ticker}: sem dados", "WARN"); continue
            dy_raw = info.get("dividendYield", 0) or 0
            divs_hist = []
            try:
                divs = t.dividends.tail(5)
                for d, v in divs.items(): divs_hist.append({"paymentDate": str(d.date()), "rate": round(float(v), 4), "label": "DIV"})
            except: pass
            resultados[ticker] = {"nome": info.get("longName") or info.get("shortName", ticker), "nome_curto": info.get("shortName", ticker), "preco": preco, "variacao_dia": info.get("regularMarketChangePercent", 0) or 0, "volume": info.get("regularMarketVolume", 0) or 0, "market_cap": info.get("marketCap", 0) or 0, "max_52sem": info.get("fiftyTwoWeekHigh", 0) or 0, "min_52sem": info.get("fiftyTwoWeekLow", 0) or 0, "dividend_yield": round(dy_raw * 100, 2), "earnings_per_share": info.get("trailingEps", 0) or 0, "price_earnings": info.get("trailingPE", 0) or 0, "dividendos_historico": divs_hist}
            log(f"  {ticker}: R$ {preco:.2f} | DY: {resultados[ticker]['dividend_yield']:.1f}%", "OK")
        except Exception as e: log(f"  {ticker}: erro - {str(e)[:60]}", "WARN")
        time.sleep(0.3)
    return resultados

def coletar_cotacoes(carteira):
    log(f"Buscando cotações: {', '.join(a['ticker'] for a in carteira)}")
    return coletar_cotacoes_yf([a["ticker"] for a in carteira])

def coletar_commodities():
    log("Buscando macro...")
    dados = {}
    pares = {"USD-BRL":("Dólar","💵","cambio"),"EUR-BRL":("Euro","💶","cambio"),"BTC-BRL":("Bitcoin","₿","crypto"),"XAU-BRL":("Ouro","🥇","metal"),"XAG-BRL":("Prata","🥈","metal")}
    for par, (nome, emoji, cat) in pares.items():
        d = fetch_json(f"https://economia.awesomeapi.com.br/last/{par}", label=nome)
        if d:
            k = par.replace("-","")
            if k in d:
                v = float(d[k].get("bid",0)); var = float(d[k].get("pctChange",0))
                dados[par.replace("-","/")] = {"valor":v,"variacao":var,"nome":nome,"categoria":cat,"emoji":emoji}
                log(f"  {nome}: R$ {v:,.2f} ({var:+.2f}%)", "OK")
        time.sleep(0.3)
    for nome, serie, emoji in [("Selic Meta",432,"📊"),("IPCA Mensal",433,"📈")]:
        d = fetch_json(f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados/ultimos/1?formato=json", label=nome)
        if d and len(d) > 0:
            v = float(d[0].get("valor","0").replace(",","."))
            dados[nome] = {"valor":v,"variacao":0,"nome":nome,"categoria":"macro","emoji":emoji,"data":d[0].get("data","")}
            u = "% a.a." if "Selic" in nome else "%"
            log(f"  {nome}: {v:.2f}{u}", "OK")
    return dados

def coletar_indices():
    log("Buscando índices...")
    indices = {}
    import yfinance as yf
    try:
        t = yf.Ticker("^BVSP"); info = t.info
        v = info.get("regularMarketPrice",0) or 0; var = info.get("regularMarketChangePercent",0) or 0
        if v: indices["Ibovespa"] = {"valor":v,"variacao":var}; log(f"  Ibovespa: {v:,.0f} ({var:+.2f}%)", "OK")
    except Exception as e: log(f"  Ibovespa: {e}", "WARN")
    return indices

def escanear_oportunidades():
    log("Escaneando oportunidades...")
    em = {a["ticker"] for a in CARTEIRA}
    r = {"acoes":{},"fiis":{},"etfs":{}}
    for cat, wl in [("acoes",WATCHLIST_ACOES),("fiis",WATCHLIST_FIIS),("etfs",WATCHLIST_ETFS)]:
        tks = [t for t in wl if t not in em]
        log(f"  {cat}: {len(tks)} ativos")
        r[cat] = coletar_cotacoes_yf(tks)
    total = sum(len(v) for v in r.values())
    log(f"Scanner: {total} ativos", "OK")
    return r

def buscar_noticias_google(query):
    noticias = []
    try:
        r = requests.get("https://news.google.com/rss/search", params={"q":query,"hl":"pt-BR","gl":"BR","ceid":"BR:pt-419"}, timeout=10)
        if r.status_code == 200:
            import xml.etree.ElementTree as ET
            for item in ET.fromstring(r.content).findall(".//item")[:5]:
                ti = item.find("title"); pd = item.find("pubDate"); li = item.find("link")
                if ti is not None: noticias.append({"titulo":ti.text or "","data":(pd.text[:16] if pd is not None and pd.text else ""),"link":(li.text if li is not None else "")})
    except: pass
    return noticias

def analisar_com_ia(carteira, cotacoes, commodities, indices, nm, na, opp=None):
    if not GEMINI_API_KEY: log("GEMINI_API_KEY não configurada", "WARN"); return None
    log("Enviando para Gemini AI...", "AI")
    dc = []; ti = 0; ta = 0
    for a in carteira:
        t = a["ticker"]; c = cotacoes.get(t,{}); p = c.get("preco",0); inv = a["quantidade"]*a["preco_medio"]; va = a["quantidade"]*p; l = va-inv; lp = (l/inv*100) if inv>0 else 0; ti+=inv; ta+=va
        si = SETOR_MAP.get(t,{"setor":"Outros","ciclico":False})
        dc.append({"ticker":t,"nome":c.get("nome_curto",t),"quantidade":a["quantidade"],"preco_medio":a["preco_medio"],"preco_atual":p,"investido":round(inv,2),"valor_atual":round(va,2),"lucro_pct":round(lp,2),"dividend_yield":c.get("dividend_yield",0),"price_earnings":c.get("price_earnings",0),"setor":si["setor"],"ciclico":si["ciclico"],"peso_pct":round(va/ta*100,2) if ta>0 else 0})
    prompt = f"""Analista financeiro sênior BR. Perfil: MODERADO, DIVIDENDOS, R$500/mês, buy and hold. Metodologia Suno (Bazin DY>6%, Barsi setores perenes, Payout 25-80%, diversificar 8-15 ativos).

CARTEIRA: {json.dumps(dc, ensure_ascii=False)}
Total: R${ti:,.2f} -> R${ta:,.2f} ({((ta/ti)-1)*100:.1f}%)

MACRO: {json.dumps(commodities, ensure_ascii=False)}
Índices: {json.dumps(indices, ensure_ascii=False)}

OPORTUNIDADES:
Ações: {json.dumps(opp.get('acoes',{}) if opp else {}, ensure_ascii=False)}
FIIs: {json.dumps(opp.get('fiis',{}) if opp else {}, ensure_ascii=False)}
ETFs: {json.dumps(opp.get('etfs',{}) if opp else {}, ensure_ascii=False)}

NOTÍCIAS: {json.dumps(nm+na, ensure_ascii=False)}

JSON exato:
{{"resumo_geral":"...","score_carteira":7,"sentimento_mercado":"neutro|positivo|negativo","analise_composicao":{{"diagnostico":"...","setores_faltantes":["..."],"classes_faltantes":["..."],"plano_diversificacao":"..."}},"analise_ativos":[{{"ticker":"X","recomendacao":"MANTER|COMPRAR|VENDER|AUMENTAR|REDUZIR","score":8,"analise":"...","riscos":"...","pontos_positivos":"...","impacto_macro":"..."}}],"oportunidades_acoes":[{{"ticker":"X","nome":"N","preco":0,"dividend_yield":0,"score":9,"setor":"S","motivo":"...","riscos":"...","urgencia":"ALTA|MEDIA|BAIXA"}}],"oportunidades_fiis":[{{"ticker":"X","nome":"N","preco":0,"dividend_yield":0,"score":8,"tipo":"Papel|Tijolo","motivo":"...","riscos":"...","urgencia":"ALTA|MEDIA|BAIXA"}}],"oportunidades_etfs":[{{"ticker":"X","nome":"N","preco":0,"dividend_yield":0,"score":7,"motivo":"...","riscos":"..."}}],"top3_comprar_agora":[{{"ticker":"X","tipo":"Ação|FII|ETF","motivo_curto":"...","valor_sugerido":200}}],"sugestao_aporte":"...","alertas":["..."],"proximos_eventos":["..."]}}

Max 5 ações, 5 FIIs, 3 ETFs. Priorize sub-representados. APENAS JSON."""
    try:
        r = requests.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
            headers={"Content-Type":"application/json","x-goog-api-key":GEMINI_API_KEY},
            json={"contents":[{"role":"user","parts":[{"text":prompt}]}],"generationConfig":{"maxOutputTokens":8192,"temperature":0.3,"responseMimeType":"application/json"}}, timeout=180)
        if r.status_code != 200: log(f"Gemini {r.status_code}: {r.text[:200]}", "ERR"); return None
        texto = ""; 
        for p in r.json().get("candidates",[{}])[0].get("content",{}).get("parts",[]): texto += p.get("text","")
        texto = texto.strip().strip("`").strip()
        if texto.startswith("json"): texto = texto[4:].strip()
        a = json.loads(texto); log("Gemini OK!", "OK"); return a
    except Exception as e: log(f"Gemini erro: {e}", "ERR"); return None

# HTML generation function - imported from separate module to keep main script readable
# For the full HTML generation, see the gerar_html function below

def gerar_html(carteira, cotacoes, commodities, indices, analise, nm, na):
    agora = datetime.now().strftime("%d/%m/%Y %H:%M"); esc = html_module.escape
    ti = sum(a["quantidade"]*a["preco_medio"] for a in carteira)
    ta = sum(a["quantidade"]*cotacoes.get(a["ticker"],{}).get("preco",0) for a in carteira)
    lt = ta-ti; lp = ((ta/ti)-1)*100 if ti>0 else 0
    sent = analise.get("sentimento_mercado","neutro") if analise else "neutro"
    sc_map = {"positivo":"#22c55e","negativo":"#ef4444","neutro":"#f59e0b"}
    sent_c = sc_map.get(sent,"#f59e0b"); sent_e = {"positivo":"🟢","negativo":"🔴","neutro":"🟡"}.get(sent,"🟡")
    score = analise.get("score_carteira","—") if analise else "—"; lct = "#22c55e" if lt>=0 else "#ef4444"
    resumo = esc(analise.get("resumo_geral","")) if analise else "Configure GEMINI_API_KEY."
    sugestao = esc(analise.get("sugestao_aporte","N/A")) if analise else "Configure GEMINI_API_KEY."

    # Pesos
    dc = []
    for a in carteira:
        c = cotacoes.get(a["ticker"],{}); va = a["quantidade"]*c.get("preco",0); pct = (va/ta*100) if ta>0 else 0
        si = SETOR_MAP.get(a["ticker"],{"setor":"Outros","ciclico":False})
        dc.append({"ticker":a["ticker"],"peso":round(pct,1),"setor":si["setor"],"ciclico":si["ciclico"]})
    pesos_h = ""
    for d in sorted(dc, key=lambda x:-x["peso"]):
        bc = "var(--red)" if d["peso"]>40 else ("var(--yellow)" if d["peso"]>25 else "var(--green)")
        tag = '<span style="color:var(--yellow);font-size:10px;margin-left:6px">⚡CÍC</span>' if d["ciclico"] else '<span style="color:var(--green);font-size:10px;margin-left:6px">🛡️PER</span>'
        pesos_h += f'<div style="display:flex;align-items:center;gap:12px;padding:8px 0;border-bottom:1px solid var(--border)"><span style="font-family:monospace;font-weight:700;width:70px">{d["ticker"]}</span><div style="flex:1"><div style="background:var(--bg4);border-radius:4px;height:20px;overflow:hidden"><div style="background:{bc};height:100%;width:{min(d["peso"],100):.0f}%;border-radius:4px;display:flex;align-items:center;padding-left:6px"><span style="font-size:11px;font-family:monospace;font-weight:700;color:var(--bg)">{d["peso"]:.1f}%</span></div></div></div><span style="font-size:11px;color:var(--text2);width:140px;text-align:right">{d["setor"]}{tag}</span></div>'

    # Composição IA
    comp_h = ""
    if analise and analise.get("analise_composicao"):
        ac = analise["analise_composicao"]
        comp_h += f'<div style="background:var(--bg3);border-radius:10px;padding:16px;margin:16px 0"><h4 style="font-size:13px;color:var(--accent);margin-bottom:8px">🔍 Diagnóstico</h4><p style="font-size:14px;color:var(--text2);line-height:1.7">{esc(str(ac.get("diagnostico","")))}</p></div>'
        sf = ac.get("setores_faltantes",[]); cf = ac.get("classes_faltantes",[])
        if sf: comp_h += f'<div style="background:var(--bg3);border-left:3px solid var(--yellow);border-radius:10px;padding:12px;margin-bottom:8px"><strong style="color:var(--yellow);font-size:12px">Setores faltantes:</strong> <span style="color:var(--text2);font-size:13px">{", ".join(esc(str(s)) for s in sf)}</span></div>'
        if cf: comp_h += f'<div style="background:var(--bg3);border-left:3px solid var(--green);border-radius:10px;padding:12px;margin-bottom:8px"><strong style="color:var(--green);font-size:12px">Classes faltantes:</strong> <span style="color:var(--text2);font-size:13px">{", ".join(esc(str(s)) for s in cf)}</span></div>'
        pl = ac.get("plano_diversificacao","")
        if pl: comp_h += f'<div style="background:var(--bg3);border-left:3px solid var(--accent2);border-radius:10px;padding:12px"><strong style="color:var(--accent2);font-size:12px">Plano:</strong> <span style="color:var(--text2);font-size:13px">{esc(str(pl))}</span></div>'

    # Ativos
    ativos_h = ""
    am = {a["ticker"]:a for a in analise.get("analise_ativos",[])} if analise else {}
    for ativo in carteira:
        t = ativo["ticker"]; c = cotacoes.get(t,{}); an = am.get(t,{})
        p = c.get("preco",0); inv = ativo["quantidade"]*ativo["preco_medio"]; va = ativo["quantidade"]*p
        l = va-inv; lpp = (l/inv*100) if inv>0 else 0; vd = c.get("variacao_dia",0); dy = c.get("dividend_yield",0); pe = c.get("price_earnings",0)
        rec = an.get("recomendacao","—"); rc = {"COMPRAR":("#22c55e","↑"),"AUMENTAR":("#22c55e","↑"),"MANTER":("#f59e0b","→"),"VENDER":("#ef4444","↓"),"REDUZIR":("#ef4444","↓")}
        rcol,rarr = rc.get(rec,("#94a3b8","•")); lc2 = "#22c55e" if l>=0 else "#ef4444"; vc2 = "#22c55e" if vd>=0 else "#ef4444"
        dh = "".join(f'<span style="font-size:11px;color:var(--text2);margin-right:12px">{d.get("paymentDate","")} R${d.get("rate",0):.4f}</span>' for d in c.get("dividendos_historico",[])[:3]) or '<span style="color:var(--text2);font-size:11px">Sem dados</span>'
        ativos_h += f'<div style="background:var(--bg2);border:1px solid var(--border);border-radius:16px;padding:24px;margin-bottom:16px"><div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:16px"><div><span style="font-family:monospace;font-size:20px;font-weight:700">{t}</span> <span style="color:var(--text2);font-size:12px">{esc(c.get("nome_curto",t))}</span></div><span style="background:{rcol}20;color:{rcol};border:1px solid {rcol}40;padding:4px 12px;border-radius:6px;font-family:monospace;font-size:13px;font-weight:700">{rarr} {rec}</span></div><div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:16px"><div style="background:var(--bg3);border-radius:8px;padding:12px"><div style="font-size:10px;color:var(--text2);text-transform:uppercase">Preço</div><div style="font-family:monospace;font-size:16px;font-weight:700;margin-top:4px">R$ {p:.2f}</div><div style="font-family:monospace;font-size:11px;color:{vc2};margin-top:2px">{vd:+.2f}%</div></div><div style="background:var(--bg3);border-radius:8px;padding:12px"><div style="font-size:10px;color:var(--text2);text-transform:uppercase">Resultado</div><div style="font-family:monospace;font-size:16px;font-weight:700;color:{lc2};margin-top:4px">R$ {l:+,.2f}</div><div style="font-family:monospace;font-size:11px;color:{lc2};margin-top:2px">{lpp:+.2f}%</div></div><div style="background:var(--bg3);border-radius:8px;padding:12px"><div style="font-size:10px;color:var(--text2);text-transform:uppercase">Score</div><div style="font-family:monospace;font-size:16px;font-weight:700;margin-top:4px">{an.get("score","—")}/10</div><div style="font-size:11px;color:var(--text2);margin-top:2px">DY:{dy:.1f}% P/L:{pe:.1f}</div></div></div><div style="background:var(--bg3);border-radius:8px;padding:12px;margin-bottom:8px;font-size:13px;color:var(--text2);line-height:1.6">{esc(an.get("analise","N/A"))}</div><div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px"><div style="background:var(--bg3);border-left:2px solid var(--green);border-radius:8px;padding:10px;font-size:12px;color:var(--text2)"><strong style="color:var(--green)">✅</strong> {esc(an.get("pontos_positivos","—"))}</div><div style="background:var(--bg3);border-left:2px solid var(--yellow);border-radius:8px;padding:10px;font-size:12px;color:var(--text2)"><strong style="color:var(--yellow)">⚠️</strong> {esc(an.get("riscos","—"))}</div></div><div style="font-size:11px;color:var(--text2);padding:8px">💰 {dh}</div></div>'

    # Oportunidades
    opp_h = ""
    if analise:
        top3 = analise.get("top3_comprar_agora",[])
        if top3:
            opp_h += '<div style="margin-bottom:20px"><h3 style="font-family:monospace;font-size:16px;color:#22c55e;margin-bottom:12px">🏆 Top 3</h3><div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px">'
            for i,item in enumerate(top3,1):
                opp_h += f'<div style="background:linear-gradient(135deg,var(--bg2),var(--bg3));border:2px solid var(--green);border-radius:12px;padding:20px;position:relative"><span style="font-family:monospace;font-size:36px;font-weight:700;color:var(--green);opacity:.2;position:absolute;top:8px;right:14px">#{i}</span><div style="font-family:monospace;font-size:20px;font-weight:700;color:var(--green)">{esc(str(item.get("ticker","")))}</div><div style="font-size:11px;color:var(--text2);margin:4px 0 8px">{esc(str(item.get("tipo","")))}</div><div style="font-size:13px;color:var(--text);line-height:1.5">{esc(str(item.get("motivo_curto","")))}</div><div style="margin-top:10px;font-family:monospace;font-size:15px;color:var(--green);font-weight:700">R$ {item.get("valor_sugerido",0):,.0f}</div></div>'
            opp_h += '</div></div>'
        for cat,lab in [("oportunidades_acoes","📈 Ações"),("oportunidades_fiis","🏢 FIIs"),("oportunidades_etfs","📦 ETFs")]:
            items = analise.get(cat,[])
            if items:
                opp_h += f'<div style="margin-bottom:20px"><h3 style="font-family:monospace;font-size:15px;color:var(--accent);margin-bottom:10px">{lab}</h3><div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px">'
                for item in items:
                    urg = str(item.get("urgencia","")).lower()
                    uc = {"alta":"#22c55e","media":"#f59e0b","baixa":"#94a3b8"}.get(urg,"#94a3b8")
                    opp_h += f'<div style="background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:16px"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px"><span style="font-family:monospace;font-size:16px;font-weight:700">{esc(str(item.get("ticker","")))}</span><span style="padding:3px 8px;border-radius:4px;font-size:10px;font-weight:700;background:{uc}20;color:{uc};border:1px solid {uc}40">{urg.upper()}</span></div><div style="font-size:11px;color:var(--text2);margin-bottom:8px">{esc(str(item.get("nome","")))}</div><div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin-bottom:8px"><div style="text-align:center;background:var(--bg3);border-radius:6px;padding:6px"><div style="font-size:9px;color:var(--text2)">PREÇO</div><div style="font-family:monospace;font-size:13px;font-weight:700">R${item.get("preco",0):.2f}</div></div><div style="text-align:center;background:var(--bg3);border-radius:6px;padding:6px"><div style="font-size:9px;color:var(--text2)">DY</div><div style="font-family:monospace;font-size:13px;font-weight:700;color:var(--green)">{item.get("dividend_yield",0):.1f}%</div></div><div style="text-align:center;background:var(--bg3);border-radius:6px;padding:6px"><div style="font-size:9px;color:var(--text2)">SCORE</div><div style="font-family:monospace;font-size:13px;font-weight:700">{item.get("score",0)}/10</div></div></div><div style="font-size:12px;color:var(--text2);line-height:1.5;margin-bottom:6px">{esc(str(item.get("motivo","")))}</div><div style="font-size:11px;color:var(--yellow);background:#f59e0b08;padding:6px;border-radius:4px">⚠️ {esc(str(item.get("riscos","")))}</div></div>'
                opp_h += '</div></div>'
    if not opp_h: opp_h = '<p style="color:var(--text2)">Configure GEMINI_API_KEY.</p>'

    # Macro
    macro_h = ""
    for k,v in commodities.items():
        im = v.get("categoria")=="macro"; vc3 = "#22c55e" if v.get("variacao",0)>=0 else "#ef4444"
        vs = f'{v["valor"]:.2f}{"% a.a." if "Selic" in k else "%"}' if im else f'R$ {v["valor"]:,.2f}'
        vr = v.get("data","") if im else f'{v["variacao"]:+.2f}%'
        macro_h += f'<div style="background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:10px 14px;display:flex;align-items:center;gap:10px;flex:1;min-width:170px"><span style="font-size:12px;color:var(--text2)">{v.get("emoji","")} {k}</span><span style="font-family:monospace;font-weight:700;font-size:14px">{vs}</span><span style="font-family:monospace;font-size:12px;color:{"var(--text2)" if im else vc3}">{vr}</span></div>'
    idx_h = ""
    for k,v in indices.items():
        vic = "#22c55e" if v.get("variacao",0)>=0 else "#ef4444"
        idx_h += f'<div style="background:var(--bg2);border:1px solid var(--border);border-left:3px solid var(--accent);border-radius:8px;padding:10px 14px;display:flex;align-items:center;gap:10px;flex:1;min-width:170px"><span style="font-size:12px;color:var(--text2)">{k}</span><span style="font-family:monospace;font-weight:700;font-size:14px">{v["valor"]:,.0f}</span><span style="font-family:monospace;font-size:12px;color:{vic}">{v["variacao"]:+.2f}%</span></div>'

    news_h = "".join(f'<a style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border);text-decoration:none;gap:8px" href="{esc(n.get("link","#"))}" target="_blank"><span style="font-size:12px;color:var(--text)">{esc(n.get("titulo",""))}</span><span style="font-size:10px;color:var(--text2);white-space:nowrap">{esc(n.get("data",""))}</span></a>' for n in (nm+na)[:8])
    al_h = "".join(f'<div style="background:#ef444410;border-left:3px solid var(--red);padding:8px 12px;margin-bottom:6px;border-radius:0 6px 6px 0;font-size:12px">⚡ {esc(a)}</div>' for a in (analise.get("alertas",[]) if analise else []))
    ev_h = "".join(f'<div style="padding:8px 12px;margin-bottom:6px;background:var(--bg3);border-radius:6px;font-size:12px;color:var(--text2)">📅 {esc(e)}</div>' for e in (analise.get("proximos_eventos",[]) if analise else []))

    return f"""<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>Carteira {agora}</title>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=DM+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>:root{{--bg:#0a0e17;--bg2:#111827;--bg3:#1a2235;--bg4:#243049;--text:#e2e8f0;--text2:#94a3b8;--accent:#3b82f6;--accent2:#8b5cf6;--green:#22c55e;--red:#ef4444;--yellow:#f59e0b;--border:#1e293b}}*{{margin:0;padding:0;box-sizing:border-box}}body{{font-family:'DM Sans',sans-serif;background:var(--bg);color:var(--text);line-height:1.6}}.c{{max-width:1400px;margin:0 auto;padding:20px}}@media(max-width:768px){{.c{{padding:12px}}}}</style></head><body><div class="c">
<div style="background:linear-gradient(135deg,var(--bg2),var(--bg3));border:1px solid var(--border);border-radius:14px;padding:28px;margin-bottom:20px"><div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px"><div><h1 style="font-family:'JetBrains Mono',monospace;font-size:24px;font-weight:700;background:linear-gradient(135deg,var(--accent),var(--accent2));-webkit-background-clip:text;-webkit-text-fill-color:transparent">📈 Analisador v2.2</h1><div style="color:var(--text2);font-size:13px;margin-top:4px">{agora}</div></div><div style="padding:6px 14px;border-radius:6px;background:{sent_c}15;border:1px solid {sent_c}30;font-weight:600;color:{sent_c};font-size:13px">{sent_e} {sent.upper()}</div></div><div style="margin-top:16px;color:var(--text2);font-size:14px;line-height:1.7">{resumo}</div></div>
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:20px"><div style="background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:16px;text-align:center"><div style="font-size:11px;color:var(--text2);text-transform:uppercase">Investido</div><div style="font-family:'JetBrains Mono',monospace;font-size:20px;font-weight:700;margin-top:6px">R$ {ti:,.2f}</div></div><div style="background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:16px;text-align:center"><div style="font-size:11px;color:var(--text2);text-transform:uppercase">Atual</div><div style="font-family:'JetBrains Mono',monospace;font-size:20px;font-weight:700;margin-top:6px">R$ {ta:,.2f}</div></div><div style="background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:16px;text-align:center"><div style="font-size:11px;color:var(--text2);text-transform:uppercase">Resultado</div><div style="font-family:'JetBrains Mono',monospace;font-size:20px;font-weight:700;margin-top:6px;color:{lct}">R$ {lt:+,.2f}</div></div><div style="background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:16px;text-align:center"><div style="font-size:11px;color:var(--text2);text-transform:uppercase">Score</div><div style="font-family:'JetBrains Mono',monospace;font-size:20px;font-weight:700;margin-top:6px;color:var(--accent)">{score}/10</div></div></div>
<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:20px">{idx_h}{macro_h}</div>
<h2 style="font-family:'JetBrains Mono',monospace;font-size:18px;margin-bottom:12px">⚖️ Composição</h2>
<div style="background:var(--bg2);border:1px solid var(--border);border-radius:14px;padding:24px;margin-bottom:20px">{pesos_h}{comp_h}</div>
<h2 style="font-family:'JetBrains Mono',monospace;font-size:18px;margin-bottom:12px">🏦 Ativos</h2>{ativos_h}
<h2 style="font-family:'JetBrains Mono',monospace;font-size:18px;margin:24px 0 12px;background:linear-gradient(135deg,var(--green),var(--accent));-webkit-background-clip:text;-webkit-text-fill-color:transparent">🎯 Oportunidades</h2>{opp_h}
<div style="background:linear-gradient(135deg,var(--bg2),var(--bg3));border:1px solid var(--accent);border-radius:12px;padding:20px;margin-top:20px"><h3 style="font-family:'JetBrains Mono',monospace;font-size:15px;color:var(--accent);margin-bottom:10px">💡 Aporte R$ 500</h3><p style="color:var(--text2);font-size:13px;line-height:1.7">{sugestao}</p></div>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:20px"><div style="background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:20px"><h3 style="font-family:'JetBrains Mono',monospace;font-size:15px;color:var(--accent);margin-bottom:12px">⚡ Alertas</h3>{al_h or '<p style="color:var(--text2);font-size:12px">—</p>'}</div><div style="background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:20px"><h3 style="font-family:'JetBrains Mono',monospace;font-size:15px;color:var(--accent);margin-bottom:12px">📅 Eventos</h3>{ev_h or '<p style="color:var(--text2);font-size:12px">—</p>'}</div></div>
<div style="background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:20px;margin-top:16px"><h3 style="font-family:'JetBrains Mono',monospace;font-size:15px;color:var(--accent);margin-bottom:12px">📰 Notícias</h3>{news_h or '<p style="color:var(--text2)">—</p>'}</div>
<div style="text-align:center;padding:24px;color:var(--text2);font-size:11px;border-top:1px solid var(--border);margin-top:24px"><p>⚠️ Informativo. Consulte assessor.</p><p style="margin-top:6px"><strong>v2.2</strong> — yfinance + AwesomeAPI + BCB + Gemini AI + Suno</p></div>
</div></body></html>"""

def main():
    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║      ANALISADOR INTELIGENTE DE CARTEIRA v2.2                 ║")
    print("║  100% APIs gratuitas + Gemini AI                            ║")
    print("╚══════════════════════════════════════════════════════════════╝\n")
    cotacoes = coletar_cotacoes(CARTEIRA)
    if not cotacoes: log("Sem cotações. Abortando.", "ERR"); sys.exit(1)
    commodities = coletar_commodities()
    indices = coletar_indices()
    oportunidades = escanear_oportunidades()
    nm = buscar_noticias_google("mercado financeiro Brasil Selic")
    na = []
    for a in CARTEIRA: na.extend(buscar_noticias_google(f"{a['ticker']} dividendos"))
    seen = set(); na = [n for n in na if n["titulo"] not in seen and not seen.add(n["titulo"])][:8]
    analise = analisar_com_ia(CARTEIRA, cotacoes, commodities, indices, nm, na, oportunidades)
    log("Gerando HTML...")
    html = gerar_html(CARTEIRA, cotacoes, commodities, indices, analise, nm, na)
    fp = OUTPUT_DIR / f"relatorio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    fp.write_text(html, encoding="utf-8")
    (OUTPUT_DIR / "relatorio_latest.html").write_text(html, encoding="utf-8")
    log(f"Salvo: {fp}", "OK")
    print(f"\n  🎯 file://{fp.resolve()}\n")

if __name__ == "__main__": main()
