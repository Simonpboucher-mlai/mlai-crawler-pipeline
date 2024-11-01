# pdf_handler.py
import io
from PyPDF2 import PdfReader
import logging

def extract_text_from_pdf(pdf_content):
    try:
        pdf_reader = PdfReader(io.BytesIO(pdf_content))
        text = ""
        for page in pdf_reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text
    except Exception as e:
        logging.error(f"Erreur lors de l'extraction du contenu du PDF : {e}")
        return ""
