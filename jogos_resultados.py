import csv
import os
import re
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


TEMPORADA = 2026
PASTA_SAIDA = "jogos"

HEADERS = {
    # A ESPN retorna 202 com corpo vazio para alguns User-Agents completos.
    # O User-Agent genérico abaixo retorna o HTML estático com as tabelas.
    "User-Agent": "Mozilla/5.0"
}

CLUBES = {
    "Palmeiras": {"espn_id": "2029", "aliases": ["Palmeiras"]},
    "Corinthians": {"espn_id": "874", "aliases": ["Corinthians"]},
    "São Paulo": {"espn_id": "2026", "aliases": ["São Paulo", "Sao Paulo"]},
    "Santos": {"espn_id": "2674", "aliases": ["Santos"]},
    "Flamengo": {"espn_id": "819", "aliases": ["Flamengo"]},
    "Vasco": {"espn_id": "3454", "aliases": ["Vasco", "Vasco da Gama"]},
}

MESES = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}


def limpar_texto(valor: str | None) -> str:
    return " ".join(str(valor or "").split())


def normalizar_nome(valor: str | None) -> str:
    return limpar_texto(valor).casefold()


def eh_clube(clube: str, nome_time: str) -> bool:
    aliases = CLUBES[clube]["aliases"]
    return normalizar_nome(nome_time) in {normalizar_nome(alias) for alias in aliases}


def parse_data_espn(valor: str) -> str | None:
    match = re.search(r"\b([A-Z][a-z]{2})\s+(\d{1,2})\b", valor or "")
    if not match:
        return None
    mes = MESES.get(match.group(1))
    if not mes:
        return None
    dia = int(match.group(2))
    return f"{TEMPORADA}-{mes:02d}-{dia:02d}"


def parse_placar(valor: str) -> tuple[int | None, int | None]:
    match = re.search(r"\b(\d+)\s*-\s*(\d+)\b", valor or "")
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def resultado_para_clube(clube: str, mandante: str, gols_mandante, gols_visitante) -> str | None:
    if gols_mandante is None or gols_visitante is None:
        return None
    if gols_mandante == gols_visitante:
        return "E"

    clube_mandante = eh_clube(clube, mandante)
    venceu_mandante = gols_mandante > gols_visitante
    venceu_clube = venceu_mandante if clube_mandante else not venceu_mandante
    return "V" if venceu_clube else "D"


def url_espn(clube_cfg: dict, tipo: str) -> str:
    return (
        "https://www.espn.com/soccer/team/"
        f"{tipo}/_/id/{clube_cfg['espn_id']}/season/{TEMPORADA}"
    )


def baixar_html(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    if not resp.text:
        raise RuntimeError(f"Resposta vazia ao acessar {url}")
    return resp.text


def extrair_link_partida(celula) -> str | None:
    link = celula.find("a", href=re.compile(r"/soccer/match/_/gameId/"))
    if not link:
        return None
    return urljoin("https://www.espn.com", link.get("href"))


def extrair_id_partida(link: str | None) -> str | None:
    if not link:
        return None
    match = re.search(r"/gameId/(\d+)", link)
    return match.group(1) if match else None


def extrair_resultados(clube: str, clube_cfg: dict) -> list[dict]:
    html = baixar_html(url_espn(clube_cfg, "results"))
    soup = BeautifulSoup(html, "html.parser")
    jogos = []

    for tabela in soup.select("table"):
        headers = [limpar_texto(th.get_text(" ", strip=True)) for th in tabela.select("thead th")]
        if headers[:4] != ["DATE", "MATCH", "RESULT", "COMPETITION"]:
            continue

        for linha in tabela.select("tbody tr"):
            colunas = linha.find_all("td")
            valores = [limpar_texto(td.get_text(" ", strip=True)) for td in colunas]
            if len(valores) < 6:
                continue

            data_txt, mandante, placar_txt, visitante, status, competicao = valores[:6]
            gols_mandante, gols_visitante = parse_placar(placar_txt)
            link = extrair_link_partida(colunas[2])

            jogos.append({
                "clube": clube,
                "data": parse_data_espn(data_txt),
                "data_original": data_txt,
                "hora": None,
                "competicao": competicao,
                "mandante": mandante,
                "visitante": visitante,
                "gols_mandante": gols_mandante,
                "gols_visitante": gols_visitante,
                "placar": placar_txt,
                "status": status or "FT",
                "resultado_clube": resultado_para_clube(clube, mandante, gols_mandante, gols_visitante),
                "mando_clube": "casa" if eh_clube(clube, mandante) else "fora",
                "id_partida": extrair_id_partida(link),
                "link": link,
                "fonte": "ESPN",
                "url_fonte": url_espn(clube_cfg, "results"),
            })

    return jogos


def extrair_fixtures(clube: str, clube_cfg: dict) -> list[dict]:
    html = baixar_html(url_espn(clube_cfg, "fixtures"))
    soup = BeautifulSoup(html, "html.parser")
    jogos = []

    for tabela in soup.select("table"):
        headers = [limpar_texto(th.get_text(" ", strip=True)) for th in tabela.select("thead th")]
        if headers[:4] != ["DATE", "MATCH", "TIME", "COMPETITION"]:
            continue

        for linha in tabela.select("tbody tr"):
            colunas = linha.find_all("td")
            valores = [limpar_texto(td.get_text(" ", strip=True)) for td in colunas]
            if len(valores) < 6:
                continue

            data_txt, mandante, marcador, visitante, hora, competicao = valores[:6]
            if marcador.lower() != "v":
                continue

            link = extrair_link_partida(colunas[2]) if len(colunas) > 2 else None
            jogos.append({
                "clube": clube,
                "data": parse_data_espn(data_txt),
                "data_original": data_txt,
                "hora": hora,
                "competicao": competicao,
                "mandante": mandante,
                "visitante": visitante,
                "gols_mandante": None,
                "gols_visitante": None,
                "placar": None,
                "status": "agendado",
                "resultado_clube": None,
                "mando_clube": "casa" if eh_clube(clube, mandante) else "fora",
                "id_partida": extrair_id_partida(link),
                "link": link,
                "fonte": "ESPN",
                "url_fonte": url_espn(clube_cfg, "fixtures"),
            })

    return jogos


def chave_partida(jogo: dict) -> tuple:
    if jogo.get("id_partida"):
        return ("id", jogo["id_partida"])
    return (
        "fallback",
        jogo.get("data"),
        jogo.get("competicao"),
        jogo.get("mandante"),
        jogo.get("visitante"),
    )


def deduplicar_partidas(jogos_por_clube: list[dict]) -> list[dict]:
    partidas = {}
    for jogo in jogos_por_clube:
        chave = chave_partida(jogo)
        if chave not in partidas:
            partida = {k: v for k, v in jogo.items() if k not in {"clube", "resultado_clube", "mando_clube", "url_fonte"}}
            partida["clubes_monitorados"] = [jogo["clube"]]
            partidas[chave] = partida
        elif jogo["clube"] not in partidas[chave]["clubes_monitorados"]:
            partidas[chave]["clubes_monitorados"].append(jogo["clube"])

    for partida in partidas.values():
        partida["clubes_monitorados"] = "; ".join(sorted(partida["clubes_monitorados"]))

    return sorted(partidas.values(), key=lambda x: (x.get("data") or "", x.get("hora") or "", x.get("mandante") or ""))


def salvar_csv(path: str, linhas: list[dict], campos: list[str]):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        writer.writerows(linhas)


def main():
    jogos_por_clube = []
    for clube, cfg in CLUBES.items():
        resultados = extrair_resultados(clube, cfg)
        fixtures = extrair_fixtures(clube, cfg)
        jogos = resultados + fixtures
        jogos_por_clube.extend(jogos)
        print(f"{clube}: {len(resultados)} resultados + {len(fixtures)} jogos futuros = {len(jogos)}")

    if not jogos_por_clube:
        raise SystemExit("Nenhum jogo coletado. CSV não foi criado.")

    os.makedirs(PASTA_SAIDA, exist_ok=True)
    data_rodagem = datetime.now().strftime("%Y-%m-%d")
    jogos_por_clube = sorted(
        jogos_por_clube,
        key=lambda x: (x.get("clube") or "", x.get("data") or "", x.get("hora") or "", x.get("mandante") or ""),
    )

    campos_clube = [
        "clube",
        "data",
        "data_original",
        "hora",
        "competicao",
        "mandante",
        "visitante",
        "gols_mandante",
        "gols_visitante",
        "placar",
        "status",
        "resultado_clube",
        "mando_clube",
        "id_partida",
        "link",
        "fonte",
        "url_fonte",
    ]
    arquivo_clube = f"{PASTA_SAIDA}/jogos_clubes_{TEMPORADA}_{data_rodagem}.csv"
    salvar_csv(arquivo_clube, jogos_por_clube, campos_clube)

    partidas = deduplicar_partidas(jogos_por_clube)
    campos_partida = [
        "data",
        "data_original",
        "hora",
        "competicao",
        "mandante",
        "visitante",
        "gols_mandante",
        "gols_visitante",
        "placar",
        "status",
        "id_partida",
        "link",
        "fonte",
        "clubes_monitorados",
    ]
    arquivo_partidas = f"{PASTA_SAIDA}/jogos_partidas_{TEMPORADA}_{data_rodagem}.csv"
    salvar_csv(arquivo_partidas, partidas, campos_partida)

    print(f"\nSalvou {len(jogos_por_clube)} linhas por clube em: {arquivo_clube}")
    print(f"Salvou {len(partidas)} partidas deduplicadas em: {arquivo_partidas}")


if __name__ == "__main__":
    main()
