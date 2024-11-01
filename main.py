# main.py
import os
import json
import logging
from dotenv import load_dotenv
from crawler import crawl

def setup_logging(log_file):
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

def load_config(config_path):
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def main():
    # Charger les variables d'environnement depuis le fichier .env
    load_dotenv()

    # Charger la configuration depuis le fichier JSON
    config = load_config('config.json')

    # Configurer le logging
    setup_logging(config.get('log_file', 'crawler_log.txt'))
    logging.info("Configuration du logging terminée.")

    # Configurer l'API OpenAI
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if openai_api_key is None:
        logging.error("La clé API OpenAI n'est pas définie. Veuillez vérifier votre fichier .env.")
        print("Erreur : La clé API OpenAI n'est pas définie. Veuillez vérifier votre fichier .env.")
        exit(1)
    else:
        logging.info("Clé API OpenAI chargée avec succès.")
        print("Clé API OpenAI chargée avec succès.")

    # Ajouter les configurations OpenAI au dictionnaire de configuration
    config['openai_api_key'] = openai_api_key

    # Exécuter le crawler
    crawl(config)

if __name__ == "__main__":
    main()
