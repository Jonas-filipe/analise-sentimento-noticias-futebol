import csv
import os
import re
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


TEMPORADAS = [2026, 2025]
PASTA_SAIDA = "serie_a_jogos"
LIGA = "bra.1"
FONTE = "ESPN"

HEADERS = {
    # A ESPN retorna HTML estático com tabelas para este User-Agent genérico.
    "User-Agent": "Mozilla/5.0"
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


def parse_data_espn(valor: str, temporada: int) -> str | None:
    match = re.search(r"\b([A-Z][a-z]{2})\s+(\d{1,2})\b", valor or "")
    if not match:
        return None
    mes = MESES.get(match.group(1))
    if not mes:
        return None
    dia = int(match.group(2))
    return f"{temporada}-{mes:02d}-{dia:02d}"


def parse_placar(valor: str) -> tuple[int | None, int | None]:
    match = re.search(r"\b(\d+)\s*-\s*(\d+)\b", valor or "")
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def baixar_json(url: str) -> dict:
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json()


def baixar_html(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    if not resp.text:
        raise RuntimeError(f"Resposta vazia ao acessar {url}")
    return resp.text


def clubes_serie_a(temporada: int) -> list[dict]:
    url = f"https://site.web.api.espn.com/apis/v2/sports/soccer/{LIGA}/standings?season={temporada}"
    data = baixar_json(url)
    entries = data["children"][0]["standings"]["entries"]
    clubes = []

    for entry in entries:
        team = entry["team"]
        clubes.append({
            "temporada": temporada,
            "clube": team["displayName"],
            "espn_id": str(team["id"]),
            "fonte_lista_clubes": url,
        })

    return clubes


def url_espn_time(espn_id: str, temporada: int, tipo: str) -> str:
    return f"https://www.espn.com/soccer/team/{tipo}/_/id/{espn_id}/season/{temporada}"


def extrair_id_time(celula) -> str | None:
    link = celula.find("a", href=re.compile(r"/soccer/team/_/id/"))
    if not link:
        return None
    match = re.search(r"/id/(\d+)", link.get("href", ""))
    return match.group(1) if match else None


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


def resultado_para_clube(clube_id: str, mandante_id: str | None, gols_mandante, gols_visitante) -> str | None:
    if gols_mandante is None or gols_visitante is None:
        return None
    if gols_mandante == gols_visitante:
        return "E"

    clube_mandante = mandante_id == clube_id
    venceu_mandante = gols_mandante > gols_visitante
    venceu_clube = venceu_mandante if clube_mandante else not venceu_mandante
    return "V" if venceu_clube else "D"


def extrair_resultados(clube: dict) -> list[dict]:
    temporada = clube["temporada"]
    url = url_espn_time(clube["espn_id"], temporada, "results")
    soup = BeautifulSoup(baixar_html(url), "html.parser")
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
            mandante_id = extrair_id_time(colunas[1])
            visitante_id = extrair_id_time(colunas[3])
            link = extrair_link_partida(colunas[2])

            jogos.append({
                "temporada": temporada,
                "clube": clube["clube"],
                "clube_espn_id": clube["espn_id"],
                "data": parse_data_espn(data_txt, temporada),
                "data_original": data_txt,
                "hora": None,
                "competicao": competicao,
                "mandante": mandante,
                "mandante_espn_id": mandante_id,
                "visitante": visitante,
                "visitante_espn_id": visitante_id,
                "gols_mandante": gols_mandante,
                "gols_visitante": gols_visitante,
                "placar": placar_txt,
                "status": status or "FT",
                "resultado_clube": resultado_para_clube(clube["espn_id"], mandante_id, gols_mandante, gols_visitante),
                "mando_clube": "casa" if mandante_id == clube["espn_id"] else "fora",
                "id_partida": extrair_id_partida(link),
                "link": link,
                "fonte": FONTE,
                "url_fonte": url,
            })

    return jogos


def extrair_fixtures(clube: dict) -> list[dict]:
    temporada = clube["temporada"]
    url = url_espn_time(clube["espn_id"], temporada, "fixtures")
    soup = BeautifulSoup(baixar_html(url), "html.parser")
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

            mandante_id = extrair_id_time(colunas[1])
            visitante_id = extrair_id_time(colunas[3])
            link = extrair_link_partida(colunas[2])

            jogos.append({
                "temporada": temporada,
                "clube": clube["clube"],
                "clube_espn_id": clube["espn_id"],
                "data": parse_data_espn(data_txt, temporada),
                "data_original": data_txt,
                "hora": hora,
                "competicao": competicao,
                "mandante": mandante,
                "mandante_espn_id": mandante_id,
                "visitante": visitante,
                "visitante_espn_id": visitante_id,
                "gols_mandante": None,
                "gols_visitante": None,
                "placar": None,
                "status": "agendado",
                "resultado_clube": None,
                "mando_clube": "casa" if mandante_id == clube["espn_id"] else "fora",
                "id_partida": extrair_id_partida(link),
                "link": link,
                "fonte": FONTE,
                "url_fonte": url,
            })

    return jogos


def chave_partida(jogo: dict) -> tuple:
    if jogo.get("id_partida"):
        return ("id", jogo["id_partida"])
    return (
        "fallback",
        jogo.get("temporada"),
        jogo.get("data"),
        jogo.get("competicao"),
        jogo.get("mandante_espn_id") or jogo.get("mandante"),
        jogo.get("visitante_espn_id") or jogo.get("visitante"),
    )


def deduplicar_partidas(jogos_por_clube: list[dict]) -> list[dict]:
    partidas = {}

    for jogo in jogos_por_clube:
        chave = chave_partida(jogo)
        if chave not in partidas:
            partida = {
                k: v
                for k, v in jogo.items()
                if k not in {"clube", "clube_espn_id", "resultado_clube", "mando_clube", "url_fonte"}
            }
            partida["clubes_serie_a"] = [jogo["clube"]]
            partidas[chave] = partida
        elif jogo["clube"] not in partidas[chave]["clubes_serie_a"]:
            partidas[chave]["clubes_serie_a"].append(jogo["clube"])

    for partida in partidas.values():
        partida["clubes_serie_a"] = "; ".join(sorted(partida["clubes_serie_a"]))

    return sorted(
        partidas.values(),
        key=lambda x: (x.get("temporada") or 0, x.get("data") or "", x.get("hora") or "", x.get("mandante") or ""),
    )


def salvar_csv(path: str, linhas: list[dict], campos: list[str]):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        writer.writerows(linhas)


def salvar_resumo(path: str, jogos_por_clube: list[dict], partidas: list[dict]):
    linhas = [
        f"Fonte: {FONTE}",
        f"Data de geração: {datetime.now().isoformat(timespec='seconds')}",
        f"Linhas por clube: {len(jogos_por_clube)}",
        f"Partidas deduplicadas: {len(partidas)}",
        "",
    ]

    for temporada in sorted({j["temporada"] for j in jogos_por_clube}):
        sub = [j for j in jogos_por_clube if j["temporada"] == temporada]
        datas = sorted(j["data"] for j in sub if j.get("data"))
        linhas.append(f"Temporada {temporada}: {datas[0]} a {datas[-1]} ({len(sub)} linhas por clube)")
        clubes = sorted({j["clube"] for j in sub})
        for clube in clubes:
            cj = [j for j in sub if j["clube"] == clube]
            cdatas = sorted(j["data"] for j in cj if j.get("data"))
            linhas.append(f"  - {clube}: {cdatas[0]} a {cdatas[-1]} ({len(cj)} jogos)")
        linhas.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas))


def main():
    os.makedirs(PASTA_SAIDA, exist_ok=True)
    data_rodagem = datetime.now().strftime("%Y-%m-%d")

    clubes_todas_temporadas = []
    jogos_por_clube = []

    for temporada in TEMPORADAS:
        clubes = clubes_serie_a(temporada)
        clubes_todas_temporadas.extend(clubes)
        print(f"\nSérie A {temporada}: {len(clubes)} clubes")

        for clube in clubes:
            resultados = extrair_resultados(clube)
            fixtures = extrair_fixtures(clube) if temporada >= datetime.now().year else []
            jogos = resultados + fixtures
            jogos_por_clube.extend(jogos)
            print(f"{clube['clube']}: {len(resultados)} resultados + {len(fixtures)} futuros = {len(jogos)}")

    if not jogos_por_clube:
        raise SystemExit("Nenhum jogo coletado. CSV não foi criado.")

    jogos_por_clube = sorted(
        jogos_por_clube,
        key=lambda x: (x.get("temporada") or 0, x.get("clube") or "", x.get("data") or "", x.get("hora") or ""),
    )
    partidas = deduplicar_partidas(jogos_por_clube)

    campos_clubes = ["temporada", "clube", "espn_id", "fonte_lista_clubes"]
    salvar_csv(
        f"{PASTA_SAIDA}/clubes_serie_a_{data_rodagem}.csv",
        clubes_todas_temporadas,
        campos_clubes,
    )

    campos_jogos_clube = [
        "temporada",
        "clube",
        "clube_espn_id",
        "data",
        "data_original",
        "hora",
        "competicao",
        "mandante",
        "mandante_espn_id",
        "visitante",
        "visitante_espn_id",
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
    salvar_csv(
        f"{PASTA_SAIDA}/jogos_por_clube_serie_a_{data_rodagem}.csv",
        jogos_por_clube,
        campos_jogos_clube,
    )

    campos_partidas = [
        "temporada",
        "data",
        "data_original",
        "hora",
        "competicao",
        "mandante",
        "mandante_espn_id",
        "visitante",
        "visitante_espn_id",
        "gols_mandante",
        "gols_visitante",
        "placar",
        "status",
        "id_partida",
        "link",
        "fonte",
        "clubes_serie_a",
    ]
    salvar_csv(
        f"{PASTA_SAIDA}/partidas_serie_a_{data_rodagem}.csv",
        partidas,
        campos_partidas,
    )

    salvar_resumo(
        f"{PASTA_SAIDA}/resumo_coleta_{data_rodagem}.txt",
        jogos_por_clube,
        partidas,
    )

    print(f"\nSalvou {len(jogos_por_clube)} linhas por clube.")
    print(f"Salvou {len(partidas)} partidas deduplicadas.")
    print(f"Pasta: {PASTA_SAIDA}")


if __name__ == "__main__":
    main()
