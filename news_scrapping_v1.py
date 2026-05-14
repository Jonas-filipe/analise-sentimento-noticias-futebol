import requests
from bs4 import BeautifulSoup
from datetime import datetime
import csv
import os


PORTAL = "globoesporte"

def extrair_noticias_time(
    url_time: str,
    clube: str,
    palavras_chave: list[str]
):
    """
    Lê a página do time no ge.globo.com e retorna
    uma lista de notícias com metadados básicos.
    """
    resp = requests.get(url_time, headers={
        "User-Agent": "Mozilla/5.0"
    })
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    noticias = []
    data_rodagem = datetime.now().strftime("%Y-%m-%d")

    # seletor genérico: todos os <a>; depois vc pode refinar
    for bloco in soup.select("a"):
        titulo = bloco.get_text(strip=True)
        link = bloco.get("href")

        # filtro básico pra evitar lixo
        if not titulo or not link:
            continue

        # normaliza pra facilitar filtros
        titulo_lower = titulo.lower()
        link_lower = link.lower()

        # aplica palavras‑chave configuráveis por clube (em título OU link)
        # se nenhuma palavra-chave bater, pula
        if not any(p.lower() in titulo_lower or p.lower() in link_lower
                   for p in palavras_chave):
            continue

        # links relativos -> absolutos
        if link.startswith("/"):
            link = "https://ge.globo.com" + link

        # tentar achar data de publicação no próprio bloco ou ancestrais
        data_publicacao = None
        # exemplos típicos: <time>, span com classe de data etc.
        tag_time = bloco.find("time")
        if tag_time and tag_time.get("datetime"):
            data_publicacao = tag_time["datetime"]
        elif tag_time and tag_time.get_text(strip=True):
            data_publicacao = tag_time.get_text(strip=True)

        noticias.append({
            "titulo": titulo,
            "link": link,
            "clube": clube,
            "portal": PORTAL,
            "data_rodagem": data_rodagem,
            "data_publicacao": data_publicacao
        })

    return noticias


if __name__ == "__main__":
    # exemplo de configuração por clube
    config_clubes = {
        "Palmeiras": {
            "url": "https://ge.globo.com/futebol/times/palmeiras/",
            "palavras": ["palmeiras", "verdao", "verdão"]
        },
        "Corinthians": {
            "url": "https://ge.globo.com/futebol/times/corinthians/",
            "palavras": ["corinthians", "timao", "timão"]
        },
        "São Paulo": {
            "url": "https://ge.globo.com/futebol/times/sao-paulo/",
            "palavras": ["sao paulo", "são paulo", "tricolor", "tricolor paulista"]
        },
        "Santos": {
            "url": "https://ge.globo.com/sp/santos-e-regiao/futebol/times/santos/",
            "palavras": ["santos", "peixe", "alvinegro praiano"]
        },
        "Flamengo": {
            "url": "https://ge.globo.com/futebol/times/flamengo/",
            "palavras": ["flamengo", "mengao", "mengão", "rubronegro", "rubro-negro"]
        },
        "Vasco": {
            "url": "https://ge.globo.com/futebol/times/vasco/",
            "palavras": ["vasco", "vasco da gama", "gigante da colina"]
        }
    }

    todas_noticias = []
    for clube, cfg in config_clubes.items():
        noticias = extrair_noticias_time(
            url_time=cfg["url"],
            clube=clube,
            palavras_chave=cfg["palavras"]
        )
        todas_noticias.extend(noticias)

    # cria pasta noticias se não existir
    import os
    os.makedirs("noticias", exist_ok=True)

    # nome do arquivo por data: noticias_ge_YYYY-MM-DD.csv
    data_hoje = datetime.now().strftime("%Y-%m-%d")
    arquivo_csv = f"noticias/noticias_ge_{data_hoje}.csv"

    # salva com cabeçalho sempre (pra ser independente)
    with open(arquivo_csv, "w", newline="", encoding="utf-8") as f:
        campos = ["titulo", "link", "clube", "portal",
                  "data_rodagem", "data_publicacao"]
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()  # cabeçalho sempre
        for n in todas_noticias:
            writer.writerow(n)

    print(f"Salvou {len(todas_noticias)} notícias em: {arquivo_csv}")
