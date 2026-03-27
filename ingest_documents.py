"""
Document Ingestion starter
"""

# Standard library
import os

import logging
from logging import getLogger
from dotenv import load_dotenv
import pytesseract

# Custom imports
from src.vector import DocumentIngestion

# Environmentvariables
load_dotenv()

# 1. Definieren der Pfade
#TESS_DIR = r"C:\Program Files\Tesseract-OCR"
#TESS_EXE = os.path.join(TESS_DIR, "tesseract.exe")
#POPPLER_BIN = r"C:\Users\christopher.abanilla\Desktop\python\local-document-rag\tools\poppler\Library\bin"

# 2. PATH komplett neu aufbauen (Nicht nur anhängen!)
# Wir setzen unsere Tools ganz nach vorne
#os.environ["PATH"] = f"{TESS_DIR};{POPPLER_BIN};" + os.environ.get("PATH", "")

# 3. Tesseract zwingen, den richtigen Datenordner zu nehmen
#os.environ["TESSDATA_PREFIX"] = os.path.join(TESS_DIR, "tessdata")
#pytesseract.pytesseract.tesseract_cmd = TESS_EXE

# 4. Temp-Ordner Fix (WICHTIG für den .hocr Fehler)
# Erstelle einen Ordner direkt unter C:\ ohne Punkte im Namen
#local_temp = r"C:\tess_tmp"
#if not os.path.exists(local_temp):
#    os.makedirs(local_temp)
#os.environ["TMP"] = local_temp
#os.environ["TEMP"] = local_temp

# Logger
logger = getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(message)s')

ingest = DocumentIngestion()

def load_documents():
    """Loads all documents into local vectorstore"""

    logger.info("Ingesting into vectorstore")
    ingest.ingest_documents()   
    logger.info("Ingestions finished")     
        
if __name__ == "__main__":
    load_documents()