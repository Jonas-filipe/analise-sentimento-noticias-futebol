import requests
from bs4 import BeautifulSoup
from datetime import datetime
import csv
import os
import re
import unicodedata
from urllib.parse import urljoin

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    )
}

BASE_URL = {
    "ge": "https://ge.globo.com",
    "uol": "https://www.uol.com.br",
    "lance": "https://www.lance.com.br",
}


def limpar_texto(valor: str | None) -> str:
    return " ".join(str(valor or "").split())


def normalizar_busca(valor: str) -> str:
    valor = unicodedata.normalize("NFKD", valor.lower())
    valor = "".join(c for c in valor if not unicodedata.combining(c))
    valor = re.sub(r"[^a-z0-9]+", " ", valor)
    return limpar_texto(valor)


def contem_palavra_chave(titulo: str, link: str, palavras_chave: list[str]) -> bool:
    alvo = normalizar_busca(f"{titulo} {link}")
    return any(normalizar_busca(p) in alvo for p in palavras_chave)


def link_absoluto(portal: str, link: str) -> str:
    return urljoin(BASE_URL.get(portal, ""), link)


def extrair_data_proxima(bloco):
    tag_time = bloco.find("time")
    if tag_time:
        return tag_time.get("datetime") or limpar_texto(tag_time.get_text(" ", strip=True))

    parent = bloco.parent
    if parent:
        tag_time = parent.find("time")
        if tag_time:
            return tag_time.get("datetime") or limpar_texto(tag_time.get_text(" ", strip=True))
    return None


def titulo_lance_por_contexto(bloco) -> str:
    for paragrafo in bloco.find_all_previous("p", limit=6):
        texto = limpar_texto(paragrafo.get_text(" ", strip=True))
        if len(texto) >= 12 and texto.lower() != "publicidade":
            return texto

    for img in bloco.find_all_previous("img", alt=True, limit=8):
        texto = limpar_texto(img.get("alt"))
        if len(texto) >= 12 and "imagem " not in texto.lower():
            return texto

    return ""


def extrair_noticias_lance(soup: BeautifulSoup, clube: str, palavras_chave: list[str], data_rodagem: str):
    """Extrai notícias do Lance.

    A página do Lance renderiza o título em imagem/parágrafo e depois um link
    com texto acessível no formato "Link para <título>". Usar somente o texto
    visível da tag <a> gera títulos artificiais ou vazios.
    """
    noticias = []
    vistos = set()

    for bloco in soup.select("main a[href$='.html'], a[href$='.html']"):
        link = link_absoluto("lance", bloco.get("href"))
        titulo = limpar_texto(bloco.get_text(" ", strip=True))

        if titulo.lower().startswith("link para "):
            titulo = titulo[len("Link para ") :].strip()

        if not titulo:
            titulo = titulo_lance_por_contexto(bloco)

        if len(titulo) < 12:
            continue
        if not contem_palavra_chave(titulo, link, palavras_chave):
            continue
        if link in vistos:
            continue

        vistos.add(link)
        times_anteriores = bloco.find_all_previous("time", limit=2)
        data_publicacao = None
        if times_anteriores:
            valores = [limpar_texto(t.get("datetime") or t.get_text(" ", strip=True)) for t in reversed(times_anteriores)]
            data_publicacao = " ".join(v for v in valores if v) or None

        noticias.append({
            "titulo": titulo,
            "link": link,
            "clube": clube,
            "portal": "lance",
            "data_rodagem": data_rodagem,
            "data_publicacao": data_publicacao
        })

    return noticias


def link_parece_noticia(portal: str, link: str) -> bool:
    link_lower = link.lower()
    if portal == "ge":
        return "/noticia/" in link_lower or "/video/" in link_lower
    if portal == "uol":
        return (
            ".htm" in link_lower
            or "/colunas/" in link_lower
            or "/esporte/ultimas-noticias/" in link_lower
        )
    return True


def extrair_noticias_generico(portal: str, soup: BeautifulSoup, clube: str, palavras_chave: list[str], data_rodagem: str):
    noticias = []
    vistos = set()

    for bloco in soup.select("main a[href], article a[href], a[href]"):
        titulo = limpar_texto(bloco.get_text(" ", strip=True))
        link = bloco.get("href")

        if not titulo or not link or len(titulo) < 12:
            continue

        link = link_absoluto(portal, link)
        if link in vistos:
            continue
        if not link_parece_noticia(portal, link):
            continue
        if not contem_palavra_chave(titulo, link, palavras_chave):
            continue

        vistos.add(link)
        noticias.append({
            "titulo": titulo,
            "link": link,
            "clube": clube,
            "portal": portal,
            "data_rodagem": data_rodagem,
            "data_publicacao": extrair_data_proxima(bloco)
        })

    return noticias


def extrair_noticias_portal(portal: str, url_time: str, clube: str, palavras_chave: list[str]):
    """Extrai notícias de UM portal/URL específica."""
    try:
        resp = requests.get(
            url_time,
            headers=HEADERS,
            timeout=10  # segundos
        )
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        # qualquer erro de rede, HTTP 4xx/5xx, timeout etc.
        print(f"Falha ao acessar {portal} {clube} ({url_time}): {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    data_rodagem = datetime.now().strftime("%Y-%m-%d")

    if portal == "lance":
        return extrair_noticias_lance(soup, clube, palavras_chave, data_rodagem)

    return extrair_noticias_generico(portal, soup, clube, palavras_chave, data_rodagem)

if __name__ == "__main__":
    # CONFIG centralizada: todos os portais + times
    palav_pal = ["palmeiras", "verdao", "verdão"]
    palav_cor = ["corinthians", "timao", "timão"]
    palav_sp = ["sao paulo", "são paulo", "tricolor", "tricolor paulista"]
    palav_san = ["santos", "peixe", "alvinegro praiano"]
    palav_fla = ["flamengo", "mengao", "mengão", "rubronegro", "rubro-negro"]
    palav_vas = ["vasco", "vasco da gama", "gigante da colina"]

    config = {
        "ge": {
            "Palmeiras": {"url": "https://ge.globo.com/futebol/times/palmeiras/", "palavras": palav_pal},
            "Corinthians": {"url": "https://ge.globo.com/futebol/times/corinthians/", "palavras": palav_cor},
            "São Paulo": {"url": "https://ge.globo.com/futebol/times/sao-paulo/", "palavras": palav_sp},
            "Santos": {"url": "https://ge.globo.com/sp/santos-e-regiao/futebol/times/santos/", "palavras": palav_san},
            "Flamengo": {"url": "https://ge.globo.com/futebol/times/flamengo/", "palavras": palav_fla},
            "Vasco": {"url": "https://ge.globo.com/futebol/times/vasco/", "palavras": palav_vas}
        },
        "uol": {
            "Palmeiras": {"url": "https://www.uol.com.br/esporte/futebol/times/palmeiras/", "palavras": palav_pal},
            "Corinthians": {"url": "https://www.uol.com.br/esporte/futebol/times/corinthians/", "palavras": palav_cor},
            "São Paulo": {"url": "https://www.uol.com.br/esporte/futebol/times/sao-paulo/", "palavras": palav_sp},
            "Santos": {"url": "https://www.uol.com.br/esporte/futebol/times/santos/", "palavras": palav_san},
            "Flamengo": {"url": "https://www.uol.com.br/esporte/futebol/times/flamengo/", "palavras": palav_fla},
            "Vasco": {"url": "https://www.uol.com.br/esporte/futebol/times/vasco/", "palavras": palav_vas}
        },
        "lance": {
            "Palmeiras": {"url": "https://www.lance.com.br/palmeiras/mais-noticias", "palavras": palav_pal},
            "Corinthians": {"url": "https://www.lance.com.br/corinthians/mais-noticias", "palavras": palav_cor},
            "São Paulo": {"url": "https://www.lance.com.br/sao-paulo/mais-noticias", "palavras": palav_sp},
            "Santos": {"url": "https://www.lance.com.br/santos/mais-noticias", "palavras": palav_san},
            "Flamengo": {"url": "https://www.lance.com.br/flamengo/mais-noticias", "palavras": palav_fla},
            "Vasco": {"url": "https://www.lance.com.br/vasco/mais-noticias", "palavras": palav_vas}
        }
    }

    todas_noticias = []
    for portal, times in config.items():
        for clube, cfg in times.items():
            try:
                noticias = extrair_noticias_portal(
                    portal, cfg["url"], clube, cfg["palavras"]
                )
            except Exception as e:
                # loga o erro e segue pro próximo
                print(f"ERRO em {portal}/{clube}: {e}")
                continue

            todas_noticias.extend(noticias)
            print(f"{portal}/{clube}: {len(noticias)} notícias")


    # salva consolidado em pasta noticias
    os.makedirs("noticias", exist_ok=True)
    data_hoje = datetime.now().strftime("%Y-%m-%d")
    arquivo_csv = f"noticias/noticias_todos_portais_{data_hoje}.csv"

    if not todas_noticias:
        raise SystemExit("Nenhuma notícia coletada. CSV não foi sobrescrito.")

    with open(arquivo_csv, "w", newline="", encoding="utf-8") as f:
        campos = ["titulo", "link", "clube", "portal", "data_rodagem", "data_publicacao"]
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        for n in todas_noticias:
            writer.writerow(n)

    print(f"\nSalvou {len(todas_noticias)} notícias totais em: {arquivo_csv}")
