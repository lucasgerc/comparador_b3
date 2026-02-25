
import os
import requests
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime


API_KEY = "API_VAROS"  # Coloque sua chave API aqui ou em uma variável de ambiente
DATA_INICIO = "2022-01-01"

ACOES = ["PETR4","WEGE3"]
FIIS  = ["HGLG11","XPML11"]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

URL_BASE = "https://api.fintz.com.br"
HEADERS  = {"X-API-Key": API_KEY}


PALETA_ACOES = ["#f97316", "#facc15", "#fb7185", "#a78bfa", "#38bdf8", "#4ade80"]
PALETA_FIIS  = ["#f97316", "#facc15", "#fb7185", "#a78bfa", "#38bdf8", "#4ade80"]
COR_BENCH    = "#94a3b8" 

BG        = "#0f172a"
BG_PAINEL = "#1e293b"
TEXTO     = "#e2e8f0"
SUBTEXT   = "#64748b"
BORDA     = "#334155"



#  Coleta da base de dados


def buscar_cotacao(ticker: str) -> pd.Series | None:
    try:
        res = requests.get(
            URL_BASE + "/bolsa/b3/avista/cotacoes/historico",
            headers=HEADERS,
            params={"ticker": ticker, "dataInicio": DATA_INICIO},
            timeout=15,
        )
        res.raise_for_status()
        df = pd.DataFrame(res.json())
        if df.empty:
            print(f"  ⚠  {ticker}: sem dados")
            return None
        df["data"] = pd.to_datetime(df["data"])
        df = df.set_index("data").sort_index()
        serie = pd.to_numeric(df["precoFechamentoAjustado"], errors="coerce").dropna()
        print(f"  ✅  {ticker}: {len(serie)} dias")
        return serie.rename(ticker)
    except Exception as e:
        print(f"  ⚠  {ticker}: {e}")
        return None


def buscar_indice(indice: str) -> pd.Series | None:
   
    for endpoint, params in [
        ("/indices/historico",{"indice": indice,  "dataInicio": DATA_INICIO}),
        ("/bolsa/b3/avista/cotacoes/historico", {"ticker": indice, "dataInicio": DATA_INICIO}),
    ]:
        try:
            res = requests.get(URL_BASE + endpoint, headers=HEADERS, params=params, timeout=15)
            if res.status_code != 200:
                continue
            dados = res.json()
            if not dados:
                continue
            df = pd.DataFrame(dados)
            if df.empty:
                continue

            # Normalizando coluna de data
            if "data" in df.columns:
                df["data"] = pd.to_datetime(df["data"])
                df = df.set_index("data").sort_index()

    
            candidatas = [c for c in df.columns if c not in ("data", "ticker", "indice")]
            serie = None
            for col in candidatas:
                s = pd.to_numeric(df[col], errors="coerce").dropna()
                if len(s) > 10:
                    serie = s
                    break

            if serie is not None and len(serie) > 0:
                print(f"  ✅  {indice}: {len(serie)} dias  (col={col}, endpoint={endpoint})")
                return serie.rename(indice)

        except Exception as e:
            print(f"  ⚠  {indice} [{endpoint}]: {e}")
            continue

    print(f"  ⚠  {indice}: não foi possível buscar dados. Será ignorado.")
    return None



def normalizar(serie: pd.Series) -> pd.Series | None:
    s = serie.dropna()
    if len(s) == 0:
        return None
    return (s / s.iloc[0]) * 100


def calcular_drawdown(serie_norm: pd.Series) -> pd.Series:
    pico = serie_norm.cummax()
    return (serie_norm - pico) / pico * 100


def calcular_metricas(serie_norm: pd.Series) -> tuple:
    retorno = serie_norm.iloc[-1] - 100
    vol     = serie_norm.pct_change().dropna().std() * (252 ** 0.5) * 100
    dd_max  = calcular_drawdown(serie_norm).min()
    return round(retorno, 1), round(vol, 1), round(dd_max, 1)


def tabela_html(linhas: list) -> str:
    th_style = f"padding:5px 16px;color:{SUBTEXT};text-align:right;font-weight:normal"
    th_left  = f"padding:5px 16px;color:{SUBTEXT};text-align:left;font-weight:normal"
    td_right = "padding:5px 16px;text-align:right"
    td_left  = f"padding:5px 16px;text-align:left;color:{TEXTO};font-weight:bold"
    tr_sep   = f"<tr><td colspan='4' style='border-top:1px solid {BORDA};padding:0'></td></tr>"

    rows_html = tr_sep
    for i, (nome, ret, vol, dd_max) in enumerate(linhas):
        cor_ret = "#4ade80" if ret >= 0 else "#f87171"
        sinal   = "▲" if ret >= 0 else "▼"
        rows_html += (
            f"<tr>"
            f"<td style='{td_left}'>{nome}</td>"
            f"<td style='{td_right};color:{cor_ret}'>{sinal} {abs(ret):.1f}%</td>"
            f"<td style='{td_right};color:{TEXTO}'>{vol:.1f}%</td>"
            f"<td style='{td_right};color:#f87171'>{dd_max:.1f}%</td>"
            f"</tr>"
            + tr_sep
        )

    return (
        f"<table style='border-collapse:collapse;font-family:monospace;font-size:12px;"
        f"background:{BG_PAINEL};border:1px solid {BORDA};border-radius:6px'>"
        f"<thead><tr>"
        f"<th style='{th_left}'>Ativo</th>"
        f"<th style='{th_style}'>Retorno total</th>"
        f"<th style='{th_style}'>Volatilidade/ano</th>"
        f"<th style='{th_style}'>Drawdown máx.</th>"
        f"</tr></thead><tbody>{rows_html}</tbody></table>"
    )



def build_traces(series_dict: dict, benchmark_nome: str, paleta: list):
    traces_rent = []
    traces_dd   = []
    dados_tab   = []

    ativos = {k: v for k, v in series_dict.items() if k != benchmark_nome}
    bench  = series_dict.get(benchmark_nome)

    for i, (nome, serie) in enumerate(ativos.items()):
        norm = normalizar(serie)
        if norm is None or len(norm) == 0:
            continue
        dd   = calcular_drawdown(norm)
        ret, vol, dd_max = calcular_metricas(norm)
        cor  = paleta[i % len(paleta)]

        traces_rent.append(go.Scatter(
            x=norm.index, y=norm.values, name=nome,
            line=dict(color=cor, width=2.5),
            hovertemplate=f"<b>{nome}</b>  %{{y:.1f}}<extra></extra>",
        ))
        traces_dd.append(go.Scatter(
            x=dd.index, y=dd.values, name=nome,
            line=dict(color=cor, width=1.5),
            showlegend=False,
            hovertemplate=f"<b>{nome}</b>  %{{y:.1f}}%<extra></extra>",
        ))
        dados_tab.append((nome, ret, vol, dd_max))

   
    if bench is not None:
        norm_b = normalizar(bench)
        if norm_b is None or len(norm_b) == 0:
            print(f"  ⚠  {benchmark_nome}: série vazia, ignorando do gráfico")
        else:
            dd_b   = calcular_drawdown(norm_b)
            ret_b, vol_b, dd_b_max = calcular_metricas(norm_b)

            traces_rent.append(go.Scatter(
                x=norm_b.index, y=norm_b.values, name=benchmark_nome,
                line=dict(color=COR_BENCH, width=1.5),
                hovertemplate=f"<b>{benchmark_nome}</b>  %{{y:.1f}}<extra></extra>",
            ))
            traces_dd.append(go.Scatter(
                x=dd_b.index, y=dd_b.values, name=benchmark_nome,
                line=dict(color=COR_BENCH, width=1.5),
                showlegend=False,
                hovertemplate=f"<b>{benchmark_nome}</b>  %{{y:.1f}}%<extra></extra>",
            ))
            dados_tab.append((benchmark_nome, ret_b, vol_b, dd_b_max))

    return traces_rent, traces_dd, tabela_html(dados_tab)


def gerar_grafico(dados_acoes: dict, dados_fiis: dict):

    tr_rent_a, tr_dd_a, tab_a = build_traces(dados_acoes, "IBOV", PALETA_ACOES)
    tr_rent_f, tr_dd_f, tab_f = build_traces(dados_fiis,  "IFIX", PALETA_FIIS)

    n_rent_a = len(tr_rent_a)
    n_dd_a   = len(tr_dd_a)
    n_rent_f = len(tr_rent_f)
    n_dd_f   = len(tr_dd_f)

    fig = make_subplots(
        rows=2, cols=1,
        row_heights=[0.65, 0.35],
        shared_xaxes=True,
        vertical_spacing=0.07,
        subplot_titles=("Rentabilidade Acumulada (Base 100)", "Drawdown (%)"),
    )

    # Modo Ações — visível por padrão
    for tr in tr_rent_a:
        fig.add_trace(tr, row=1, col=1)
    for tr in tr_dd_a:
        fig.add_trace(tr, row=2, col=1)

    # Modo FIIs — invisível por padrão
    for tr in tr_rent_f:
        tr.visible = False
        fig.add_trace(tr, row=1, col=1)
    for tr in tr_dd_f:
        tr.visible = False
        fig.add_trace(tr, row=2, col=1)

    total_a = n_rent_a + n_dd_a
    total_f = n_rent_f + n_dd_f

    vis_acoes = [True]  * total_a + [False] * total_f
    vis_fiis  = [False] * total_a + [True]  * total_f

    def titulo(modo):
        return (
            f"📊 {modo}<br>"
            f"<sup>Período: {DATA_INICIO} → {datetime.today().strftime('%d/%m/%Y')}  |  Base 100</sup>"
        )

    fig.update_layout(
        title=dict(text=titulo("Ações vs IBOV"), font=dict(color=TEXTO, size=17), x=0.5),
        paper_bgcolor=BG,
        plot_bgcolor=BG,
        font=dict(color=SUBTEXT, family="monospace", size=11),
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.02,
            xanchor="right", x=1,
            bgcolor=BG_PAINEL,
            bordercolor=BORDA, borderwidth=1,
            font=dict(color=TEXTO, size=12),
        ),
        hovermode="x unified",
        hoverlabel=dict(bgcolor=BG_PAINEL, bordercolor=BORDA, font_color=TEXTO),
        margin=dict(t=130, b=300, l=60, r=30),
        updatemenus=[dict(
            type="buttons",
            direction="left",
            x=0.0, y=1.15,
            xanchor="left", yanchor="top",
            bgcolor=BG_PAINEL,
            bordercolor=BORDA,
            borderwidth=1,
            font=dict(color=TEXTO, size=12),
            pad=dict(r=8, t=5, b=5),
            showactive=True,
            active=0,
            buttons=[
                dict(
                    label="  📈  Ações vs IBOV  ",
                    method="update",
                    args=[
                        {"visible": vis_acoes},
                        {"title.text": titulo("Ações vs IBOV"),
                         "annotations[2].text": tab_a},
                    ],
                ),
                dict(
                    label="  🏢  FIIs vs IFIX  ",
                    method="update",
                    args=[
                        {"visible": vis_fiis},
                        {"title.text": titulo("FIIs vs IFIX"),
                         "annotations[2].text": tab_f},
                    ],
                ),
            ],
        )],
    )

 
    for row in [1, 2]:
        fig.update_xaxes(gridcolor=BG_PAINEL, linecolor=BORDA, row=row, col=1)
        fig.update_yaxes(gridcolor=BG_PAINEL, linecolor=BORDA, zeroline=False, row=row, col=1)

    fig.add_hline(y=100, line=dict(color=BORDA, width=1,   dash="dot"), row=1, col=1)
    fig.add_hline(y=0,   line=dict(color="#f87171", width=0.8, dash="dot"), row=2, col=1)

    # Estilo títulos dos subplots
    for ann in fig.layout.annotations[:2]:
        ann.font.color = SUBTEXT
        ann.font.size  = 11

    # Tabela de métricas
    fig.add_annotation(
        text=tab_a,
        xref="paper", yref="paper",
        x=0.0, y=-0.30,
        xanchor="left", yanchor="top",
        showarrow=False,
        borderpad=0,
        align="left",
    )

    nome_arquivo = f"comparador_b3_{datetime.today().strftime('%Y%m%d')}.html"
    fig.write_html(nome_arquivo, include_plotlyjs="cdn")
    print(f"\n✅ Salvo: {nome_arquivo}")
    fig.show()



#  MAIN


def main():
    print("━" * 50)
    print("  Comparador B3  |  Ações vs IBOV  /  FIIs vs IFIX")
    print(f"  Período: {DATA_INICIO} → hoje")
    print("━" * 50)

    dados_acoes: dict[str, pd.Series] = {}
    dados_fiis:  dict[str, pd.Series] = {}

    print("\n📈 Buscando ações...")
    for t in ACOES:
        s = buscar_cotacao(t)
        if s is not None:
            dados_acoes[t] = s

    print("\n📡 Buscando IBOV...")
    ibov = buscar_indice("IBOV")
    if ibov is not None:
        dados_acoes["IBOV"] = ibov

    print("\n🏢 Buscando FIIs...")
    for t in FIIS:
        s = buscar_cotacao(t)
        if s is not None:
            dados_fiis[t] = s

    print("\n📡 Buscando IFIX...")
    ifix = buscar_indice("IFIX")
    if ifix is not None:
        dados_fiis["IFIX"] = ifix

    if not dados_acoes and not dados_fiis:
        print("\n❌ Nenhum dado coletado. Verifique sua chave API.")
        return

    print(f"\n📊 Gerando gráfico ({len(dados_acoes)} ações, {len(dados_fiis)} FIIs)...")
    gerar_grafico(dados_acoes, dados_fiis)


if __name__ == "__main__":

    main()
