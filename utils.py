# utils.py
import re
import unicodedata
import string
from urllib.parse import urlparse, unquote

def sanitize_filename(filename):
    filename = unicodedata.normalize('NFKD', filename).encode('ASCII', 'ignore').decode('ASCII')
    valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)
    filename = ''.join(c for c in filename if c in valid_chars)
    filename = filename.rstrip('.')
    return filename

def normalize_url(url):
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

def clean_text(text):
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    return text
