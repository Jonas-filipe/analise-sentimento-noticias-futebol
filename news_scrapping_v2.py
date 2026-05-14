import requests
from bs4 import BeautifulSoup
from datetime import datetime
import csv
import os

def extrair_noticias_portal(portal: str, url_time: str, clube: str, palavras_chave: list[str]):
    """Extrai notícias de UM portal/URL específica."""
    try:
        resp = requests.get(
            url_time,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10  # segundos
        )
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        # qualquer erro de rede, HTTP 4xx/5xx, timeout etc.
        print(f"Falha ao acessar {portal} {clube} ({url_time}): {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    noticias = []
    data_rodagem = datetime.now().strftime("%Y-%m-%d")

    for bloco in soup.select("a"):
        titulo = bloco.get_text(strip=True)
        link = bloco.get("href")
        
        if not titulo or not link:
            continue
        
        titulo_lower = titulo.lower()
        link_lower = link.lower()
        
        if not any(p.lower() in titulo_lower or p.lower() in link_lower for p in palavras_chave):
            continue
        
        if link.startswith("/"):
            # MELHOR seletor baseado no HTML do Lance
            if portal == "lance":
                blocos = soup.select("a[href*='/palmeiras/'], a[href*='/corinthians/'], "
                                    "a[href*='/sao-paulo/'], a[href*='/santos/'], "
                                    "a[href*='/flamengo/'], a[href*='/vasco/'], "
                                    "h2 a, h3 a, .news-title a, article a")
            elif portal == "uol":
                blocos = soup.select("a[href*='/times/'], h2 a, .feed-post-card a")
            else:  # ge
                blocos = soup.select("a")

            # filtro EXTRA pro Lance: só links que parecem notícia real
            for bloco in blocos:
                titulo = bloco.get_text(strip=True)
                link = bloco.get("href")
                
                if not titulo or not link or len(titulo) < 10:  # títulos muito curtos = lixo
                    continue

        
        data_publicacao = bloco.find("time")
        if data_publicacao:
            data_publicacao = data_publicacao.get("datetime") or data_publicacao.get_text(strip=True)
        
        noticias.append({
            "titulo": titulo,
            "link": link,
            "clube": clube,
            "portal": portal,
            "data_rodagem": data_rodagem,
            "data_publicacao": data_publicacao
        })
    
    return noticias

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

    with open(arquivo_csv, "w", newline="", encoding="utf-8") as f:
        campos = ["titulo", "link", "clube", "portal", "data_rodagem", "data_publicacao"]
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        for n in todas_noticias:
            writer.writerow(n)

    print(f"\nSalvou {len(todas_noticias)} notícias totais em: {arquivo_csv}")
