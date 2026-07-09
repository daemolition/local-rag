# Local Document RAG - A privacy-focused, local RAG system
# Copyright (C) 2026 Christopher Abanilla
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""
Custom preprocess
"""

# Standard library
import os
import base64
import shutil
import time
import logging
import tempfile

# Third party
from unstructured.partition.pdf import partition_pdf


def _clear_dir(path: str) -> None:
    """Leert den Inhalt eines Verzeichnisses, ohne das Verzeichnis selbst zu
    loeschen. Notwendig, weil ./images (./data/images) in Docker unter dem
    /app/data-Mountpoint liegt und shutil.rmtree() auf einem Mountpoint mit
    [Errno 16] Device or resource busy fehlschlaegt. Legt das Verzeichnis an,
    falls es nicht existiert."""
    os.makedirs(path, exist_ok=True)
    for entry in os.listdir(path):
        entry_path = os.path.join(path, entry)
        if os.path.isdir(entry_path) and not os.path.islink(entry_path):
            shutil.rmtree(entry_path)
        else:
            try:
                os.remove(entry_path)
            except IsADirectoryError:
                shutil.rmtree(entry_path)
from langchain_core.documents import Document
from PIL import Image
import imagehash

# Custom imports
from app.llm.local_llm import VisionLLM

logger = logging.getLogger(__name__)

class PreprocessPDF:
    
    def __init__(self, model: VisionLLM = None, max_retries: int = 3, retry_delay: float = 2.0):
        """
        Initialisiert die Preprocess Pipeline
        
        Args:
            model: Optionale VisionLLM-Instanz (wird sonst neu erstellt)
            max_retries: Maximale Retry-Versuche für LLM-Calls (default: 3)
            retry_delay: Wartezeit zwischen Retries in Sekunden (default: 2.0)
        """
        self.model = model or VisionLLM()
        self.duplicate_images = set()
        self.max_retries = max_retries
        self.retry_delay = retry_delay
    
    
    def find_duplicate_images(self, images_dir: str, threshold: int = 5) -> set:
        """
        Findet ähnliche Bilder basierend auf phash (perceptual hash).
        
        Args:
            images_dir (str): Verzeichnis mit den extrahierten Bildern
            threshold (int): Hamming-Distanz-Schwelle (niedriger = strikter)
            
        Returns:
            set: Menge der Duplikat-Pfade
        """
        hashes = {}
        duplicates = set()
        
        if not os.path.exists(images_dir):
            return duplicates
        
        image_files = sorted([
            f for f in os.listdir(images_dir) 
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif'))
        ])
        
        for img_file in image_files:
            img_path = os.path.join(images_dir, img_file)
            try:
                img = Image.open(img_path)
                h = imagehash.phash(img)
                
                for existing_path, existing_hash in hashes.items():
                    if h - existing_hash < threshold:
                        duplicates.add(img_path)
                        break
                else:
                    hashes[img_path] = h
            except Exception:
                continue
        
        return duplicates
    

    def process_image_with_retry(self, b64image: str, image_path: str, current_image: int, unique_image_count: int) -> dict:
        """
        Verarbeitet ein Bild mit Retry-Logik für LLM-Timeouts.
        
        Args:
            b64image: Base64-kodiertes Bild
            image_path: Pfad zum Bild (für Logging)
            current_image: Aktuelle Bild-Nummer
            unique_image_count: Gesamtzahl der einzigartigen Bilder
            
        Returns:
            dict: {'image': description_text} oder {'error': error_message}
        """
        message = self.model.generate_image_message(b64image)
        
        retry_count = 0
        last_error = None
        
        while retry_count < self.max_retries:
            try:
                description = self.model.generate(message)
                desc_text = description.content if hasattr(description, 'content') else str(description)
                return {'image': desc_text}
            except Exception as e:
                retry_count += 1
                last_error = e
                logger.warning(f"Bild {current_image}/{unique_image_count} - Versuch {retry_count}/{self.max_retries} fehlgeschlagen: {str(e)[:100]}")
                
                if retry_count < self.max_retries:
                    time.sleep(self.retry_delay * retry_count)  # Exponentielles Backoff
                
        logger.error(f"Bild {current_image}/{unique_image_count} - Alle {self.max_retries} Versuche fehlgeschlagen: {image_path}")
        return {'error': f"LLM-Error nach {self.max_retries} Versuchen: {str(last_error)[:100]}"}
    
    def encode_image(self, image_path: str) -> base64:
        """
        Helferfunktion zum Encodieren des Bildes in Base64
        
        Args: 
            image_path (str): Pfad zur Bilddatei
            
        Returns:
            base64 (string): Encodierter Binary String
        """
        with open(image_path, 'rb') as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8').replace("\n", "")
        
    
    def process_with_unstructured(self, file_path: str) -> list:
        """Verarbeitet die PDF und gibt eine Liste mit Dictionaies zurück"""
        
        # Bilderberzeichnis für die extrahierten Bilder aus den PDFs
        images_dir = "./data/images"

        # Sicherstellen dass der Ordner leer ist, damit nur die Images pro PDF
        # verarbeitet werden. Inhalte leeren statt rmtree, da ./data/images in
        # Docker unter dem /app/data-Mountpoint liegt (s. _clear_dir).
        _clear_dir(images_dir)
        
        # strategy="hi_res" nutzt ein Model zur Layouterkennung (langsam, aber gut)
        elements = partition_pdf(
            filename=file_path,
            strategy="hi_res", 
            languages=["deu"],
            # Das hier ist wichtig für deine Bilder/Grafiken:
            extract_images_in_pdf=True, 
            extract_image_block_output_dir=images_dir,
            infer_table_structure=False,
            pdf_image_dpi=150
        )
        
        # Duplikate/Logos filtern mit phash
        self.duplicate_images = self.find_duplicate_images(images_dir)
        
        # Anzahl einzigartiger Bilder zählen (für Progress-Anzeige)
        unique_image_count = sum(
            1 for el in elements 
            if el.category == 'Image' 
            and getattr(el.metadata, "image_path", None)
            and os.path.exists(getattr(el.metadata, "image_path", None))
            and getattr(el.metadata, "image_path", None) not in self.duplicate_images
        )
        current_image = 0
        
        # Chunks Liste
        chunks = []
        
        # Chunks dictionary zum Befüllen durch die Pipeline
        current_chunk = {
            'title': os.path.basename(file_path), 
            'content': [],
            'metadata': {}
        }
        
        def create_langchain_doc(chunk_dict):
            """Hilfsfunktion: Wandelt unser Dict in ein echtes Document um"""
            text_parts = []
            for item in chunk_dict['content']:
                if isinstance(item, dict) and 'image' in item:
                    # Bildbeschreibung lesbar in den Text einbetten
                    text_parts.append(f"[BILD-BESCHREIBUNG: {item['image']}]")
                else:
                    text_parts.append(str(item))
            
            return Document(
                page_content="\n".join(text_parts),
                metadata={
                    "source": file_path,
                    "filename": os.path.basename(file_path),
                    "title": chunk_dict.get('title', 'kein Titel'),
                    "type": "pdf_chunk",
                    **chunk_dict.get('metadata', {}) 
                }
            )

        for el in elements:            
            if el.category == 'Title':
                if current_chunk['content']:
                    # Jetzt erstellen wir hier auch schon ein Document-Objekt
                    chunks.append(create_langchain_doc(current_chunk))
                    
                current_chunk = {
                    'title': el.text,
                    'content': [],
                    'metadata': el.metadata.to_dict()
                }
            elif el.category == 'Image':
                image_path = getattr(el.metadata, "image_path", None)
                if image_path and os.path.exists(image_path):
                    # Duplikat/Logo überspringen
                    if image_path in self.duplicate_images:
                        continue
                    
                    current_image += 1
                    print(f"Verarbeite Bild {current_image}/{unique_image_count}", flush=True)
                    
                    b64image = self.encode_image(image_path)
                    result = self.process_image_with_retry(b64image, image_path, current_image, unique_image_count)
                    
                    if 'image' in result:
                        current_chunk['content'].append({'image': result['image']})
                    elif 'error' in result:
                        logger.error(f"Bild übersprungen: {result['error']}")
                        # Optional: Fehler-Platzhalter hinzufügen
                        # current_chunk['content'].append({'error': result['error']})
            else:
                if el.text.strip():
                    current_chunk['content'].append(el.text)
        
        # Den letzten Chunk verarbeiten
        if current_chunk['content']:  
            chunks.append(create_langchain_doc(current_chunk))
                            
        if os.path.exists(images_dir):
            _clear_dir(images_dir)

        return chunks

        
        