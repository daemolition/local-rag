"""
Custom preprocess
"""

# Standard library
import os
import base64
import shutil

# Third party
from unstructured.partition.pdf import partition_pdf
from langchain_core.documents import Document
from PIL import Image
import imagehash

# Custom imports
from src.llm.local_llm import VisionLLM

class PreprocessPDF:
    
    def __init__(self):
        """Initialisiert die Preprocess Pipeline"""
        self.model = VisionLLM()
        self.duplicate_images = set()
    
    
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
        images_dir = "./images"    
    
        # Sicherstellen dass der Ordner leer ist, damit nur die Images pro PDF verarbeitet werden
        if os.path.exists(images_dir):
            shutil.rmtree(images_dir)
        os.makedirs(images_dir)
        
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
                    print(f"Verarbeite Bild {current_image}/{unique_image_count}")
                    
                    b64image = self.encode_image(image_path)
                    message = self.model.generate_image_message(b64image)
                    description = self.model.generate(message)
                    desc_text = description.content if hasattr(description, 'content') else str(description)
                    
                    current_chunk['content'].append({'image': desc_text})
            else:
                if el.text.strip():
                    current_chunk['content'].append(el.text)
        
        # Den letzten Chunk verarbeiten
        if current_chunk['content']:  
            chunks.append(create_langchain_doc(current_chunk))
                            
        if os.path.exists(images_dir):
            shutil.rmtree(images_dir)      
            
        return chunks

        
        