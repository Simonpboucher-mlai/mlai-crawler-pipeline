# crawler.py
import requests
import re
from bs4 import BeautifulSoup
from collections import deque
from html.parser import HTMLParser
from urllib.parse import urlparse, unquote
import os
import time
from tqdm import tqdm
import logging
import openai
from dotenv import load_dotenv
import json

from utils import sanitize_filename, normalize_url, clean_text
from pdf_handler import extract_text_from_pdf

# Classe pour parser les hyperliens
class HyperlinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hyperlinks = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and "href" in attrs:
            self.hyperlinks.append(attrs["href"])

def get_hyperlinks(url, user_agent):
    headers = {
        'User-Agent': user_agent
    }
    try:
        with requests.get(url, headers=headers, timeout=30) as response:
            response.raise_for_status()
            if not response.headers.get('Content-Type', '').startswith("text/html"):
                return []
            html = response.text
    except requests.RequestException as e:
        logging.error(f"Erreur lors de la récupération de {url} : {e}")
        return []

    parser = HyperlinkParser()
    parser.feed(html)
    return parser.hyperlinks

def get_domain_hyperlinks(local_domain, url, user_agent):
    HTTP_URL_PATTERN = r'^http[s]*://.+'
    clean_links = []
    for link in set(get_hyperlinks(url, user_agent)):
        clean_link = None
        if re.search(HTTP_URL_PATTERN, link):
            url_obj = urlparse(link)
            if url_obj.netloc == local_domain:
                clean_link = link
        else:
            if link.startswith("/"):
                link = link[1:]
            elif link.startswith("#") or link.startswith("mailto:"):
                continue
            clean_link = f"https://{local_domain}/{link}"

        if clean_link:
            if clean_link.endswith("/"):
                clean_link = clean_link[:-1]

            # Ignorer les URL de postulation en ligne
            if "postulez-en-ligne" not in clean_link:
                clean_links.append(clean_link)

    return list(set(clean_links))

def extract_text_from_html(html_content):
    soup = BeautifulSoup(html_content, "html.parser")
    for script in soup(["script", "style", "nav", "footer", "header", "aside"]):
        script.decompose()

    text = ""
    for element in soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li']):
        text += element.get_text() + "\n"

    return clean_text(text)

def extract_text_alternative(html_content):
    soup = BeautifulSoup(html_content, "html.parser")
    return clean_text(soup.get_text(separator=' ', strip=True))

def get_page_info(text, openai_api_key, model, max_tokens, temperature):
    try:
        prompt = (
            "Vous êtes un assistant qui aide à extraire des informations spécifiques. "
            "À partir du texte fourni ci-dessous, veuillez fournir les informations suivantes de manière structurée :\n"
            "1. Mots clés en anglais.\n"
            "2. Mots clés en français.\n"
            "3. Résumé en anglais (deux phrases).\n"
            "4. Résumé en français (deux phrases).\n"
            "5. Numéro de produit principal (si disponible).\n"
            "Si un numéro de produit n'est pas disponible, indiquez 'no'.\n\n"
            "Texte:\n"
            f"{text}\n\n"
            "Format de réponse:\n"
            "Keywords (EN): [vos mots clés en anglais]\n"
            "Keywords (FR): [vos mots clés en français]\n"
            "Summary (EN): [votre résumé en anglais]\n"
            "Summary (FR): [votre résumé en français]\n"
            "Product Number: [numéro de produit ou 'no']"
        )

        response = openai.ChatCompletion.create(
            model=model,
            messages=[
                {"role": "system", "content": "Vous êtes un assistant compétent en extraction d'informations."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )

        content = response['choices'][0]['message']['content'].strip()

        # Parse the response
        info = {
            "keywords_en": "",
            "keywords_fr": "",
            "summary_en": "",
            "summary_fr": "",
            "product_number": "no"
        }

        for line in content.split('\n'):
            if line.startswith("Keywords (EN):"):
                info["keywords_en"] = line.replace("Keywords (EN):", "").strip()
            elif line.startswith("Keywords (FR):"):
                info["keywords_fr"] = line.replace("Keywords (FR):", "").strip()
            elif line.startswith("Summary (EN):"):
                info["summary_en"] = line.replace("Summary (EN):", "").strip()
            elif line.startswith("Summary (FR):"):
                info["summary_fr"] = line.replace("Summary (FR):", "").strip()
            elif line.startswith("Product Number:"):
                prod_num = line.replace("Product Number:", "").strip()
                info["product_number"] = prod_num if prod_num.lower() != 'no' else "no"

        return info

    except Exception as e:
        logging.error(f"Erreur lors de l'extraction des informations de la page : {e}")
        return {
            "keywords_en": "",
            "keywords_fr": "",
            "summary_en": "",
            "summary_fr": "",
            "product_number": "no"
        }

def crawl(config):
    print(f"Démarrage du crawl sur : {config['start_url']}")
    logging.info(f"Démarrage du crawl sur : {config['start_url']}")
    local_domain = urlparse(config['start_url']).netloc
    queue = deque([config['start_url']])
    seen = set()
    processed_count = 0

    if not os.path.exists(config['output_directory']):
        os.makedirs(config['output_directory'])
        logging.info(f"Création du dossier {config['output_directory']}/")
    domain_output = os.path.join(config['output_directory'], local_domain)
    if not os.path.exists(domain_output):
        os.makedirs(domain_output)
        logging.info(f"Création du dossier {domain_output}/")

    with tqdm(total=config['max_pages'], desc="Pages crawled") as pbar:
        while queue and processed_count < config['max_pages']:
            current_url = queue.pop()
            normalized_url = normalize_url(current_url)
            if normalized_url in seen:
                pbar.update(1)
                continue
            seen.add(normalized_url)

            logging.info(f"Crawling: {current_url}")
            print(f"Crawling: {current_url}")

            if urlparse(current_url).netloc != local_domain:
                pbar.update(1)
                continue

            try:
                headers = {
                    'User-Agent': config['user_agent']
                }
                response = requests.get(current_url, headers=headers, timeout=30, allow_redirects=True)
                final_url = response.url

                if response.status_code == 404:
                    logging.warning(f"Page non trouvée : {current_url}")
                    print(f"Page non trouvée : {current_url}")
                    pbar.update(1)
                    continue

                response.raise_for_status()

                content_type = response.headers.get('Content-Type', '').lower()
                extracted_text = ""

                if 'application/pdf' in content_type or final_url.lower().endswith('.pdf'):
                    extracted_text = extract_text_from_pdf(response.content)
                    if not extracted_text.strip():
                        logging.warning(f"Contenu PDF vide : {final_url}")
                        print(f"Contenu PDF vide : {final_url}")
                        pbar.update(1)
                        continue
                elif 'text/html' in content_type:
                    extracted_text = extract_text_from_html(response.content)
                    if not extracted_text.strip():
                        extracted_text = extract_text_alternative(response.content)
                    if not extracted_text.strip():
                        logging.warning(f"Contenu HTML vide : {final_url}")
                        print(f"Contenu HTML vide : {final_url}")
                        pbar.update(1)
                        continue
                else:
                    logging.info(f"Type de contenu non supporté pour : {final_url}")
                    pbar.update(1)
                    continue

                # Extraire les informations de la page via OpenAI
                page_info = get_page_info(
                    extracted_text,
                    config['openai_api_key'],
                    config['openai_model'],
                    config['openai_max_tokens'],
                    config['openai_temperature']
                )

                # Préparer l'en-tête avec les informations extraites
                header = (
                    f"lien: {final_url}\n"
                    f"mot clé anglais: {page_info['keywords_en']}\n"
                    f"mot clé français: {page_info['keywords_fr']}\n"
                    f"résumé (EN): {page_info['summary_en']}\n"
                    f"résumé (FR): {page_info['summary_fr']}\n\n"
                )

                # Ajouter le numéro de produit
                if page_info["product_number"].lower() != "no":
                    header += f"#pro : {page_info['product_number']}\n"
                else:
                    header += "#pro: no\n"

                header += "\n------\n\n"

                # Générer un nom de fichier sécurisé
                filename = sanitize_filename(unquote(final_url[8:]).replace("/", "_"))
                filepath = os.path.join(domain_output, f"{filename}.txt")
                with open(filepath, "w", encoding='utf-8') as f:
                    f.write(header + extracted_text)
                logging.info(f"Contenu sauvegardé : {final_url}")
                print(f"Contenu sauvegardé : {final_url}")

                processed_count += 1
                pbar.update(1)

                for link in get_domain_hyperlinks(local_domain, final_url, config['user_agent']):
                    normalized_link = normalize_url(link)
                    if normalized_link not in seen:
                        queue.append(link)
                        logging.info(f"Ajouté à la queue : {link}")
                        print(f"Ajouté à la queue : {link}")

                time.sleep(config['delay_between_requests'])

            except requests.RequestException as e:
                logging.error(f"Erreur lors du crawl de {current_url} : {e}")
                print(f"Erreur lors du crawl de {current_url} : {e}")
                pbar.update(1)
                continue

    logging.info("Crawling et extraction de texte terminés.")
    print("Crawling et extraction de texte terminés.")
