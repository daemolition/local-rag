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
DOCX/DOC/ODT-spezifisches Preprocessing.

Im Gegensatz zu PDF nutzt DOCX keine Layout-Erkennung für Bilder.
Stattdessen wird die DOCX-Datei als ZIP geöffnet, Bilder aus word/media/
extrahiert und über python-docx in Absatz-Reihenfolge verarbeitet, sodass
Bildbeschreibungen an der richtigen Position im Textfluss stehen.

ODT wird von unstructured via pandoc nach DOCX konvertiert, DOC via LibreOffice.
Daher funktioniert dieser Preprocessor für alle drei Formate.
"""

# Standard library
import os
import zipfile

# Third party
from docx import Document
from docx.oxml.ns import qn
from langchain_core.documents import Document as LangChainDocument

# Custom imports
from app.components.preprocess_base import PreprocessBase, _clear_dir


class PreprocessDOCX(PreprocessBase):
    """DOCX/DOC/ODT-Preprocessing mit ZIP-Bildextraktion und VisionLLM."""

    def _extract_images_from_zip(self, file_path: str, images_dir: str) -> dict:
        """Extrahiert alle Bilder aus der DOCX-ZIP-Datei nach images_dir.

        Returns:
            dict: {relationship_id: image_file_path} z. B. {'rId9': './data/images/image1.png'}
        """
        _clear_dir(images_dir)

        rel_to_path = {}
        try:
            with zipfile.ZipFile(file_path, 'r') as zf:
                # Relationships laden: r:embed ID → media/Dateiname
                rels_xml = zf.read('word/_rels/document.xml.rels').decode()
                import re
                rel_matches = re.findall(
                    r'Id="(rId\d+)"[^>]*Type="[^"]*image"[^>]*Target="([^"]+)"',
                    rels_xml
                )

                for rel_id, target in rel_matches:
                    media_path = f'word/{target}'
                    try:
                        image_data = zf.read(media_path)
                        out_name = os.path.basename(target)
                        out_path = os.path.join(images_dir, out_name)
                        with open(out_path, 'wb') as f:
                            f.write(image_data)
                        rel_to_path[rel_id] = out_path
                    except KeyError:
                        continue
        except (zipfile.BadZipFile, KeyError):
            pass

        return rel_to_path

    def process_with_unstructured(self, file_path: str) -> list:
        """Verarbeitet DOCX/DOC/ODX und gibt LangChain-Dokumente zurück.

        Bilder werden über python-docx in Absatz-Reihenfolge verarbeitet,
        sodass Bildbeschreibungen an der richtigen Position im Textfluss stehen.
        """
        images_dir = "./data/images"
        filename = os.path.basename(file_path)

        # Bilder aus ZIP extrahieren
        rel_to_path = self._extract_images_from_zip(file_path, images_dir)

        # Duplikate filtern
        self.duplicate_images = self.find_duplicate_images(images_dir)

        # DOCX mit python-docx öffnen
        doc = Document(file_path)

        # Bilder deduplizieren: nur einzigartige behalten
        unique_images = {}
        for rel_id, img_path in rel_to_path.items():
            if img_path not in self.duplicate_images:
                unique_images[rel_id] = img_path

        unique_image_count = len(unique_images)
        current_image = 0

        chunks: list[LangChainDocument] = []
        current_chunk: dict = {
            'title': filename,
            'content': [],
            'metadata': {}
        }

        def flush_chunk():
            if current_chunk['content']:
                text_parts = []
                for item in current_chunk['content']:
                    if isinstance(item, dict) and 'image' in item:
                        text_parts.append(f"[BILD-BESCHREIBUNG: {item['image']}]")
                    else:
                        text_parts.append(str(item))

                chunks.append(LangChainDocument(
                    page_content="\n".join(text_parts),
                    metadata={
                        "source": file_path,
                        "filename": filename,
                        "title": current_chunk.get('title', 'kein Titel'),
                        "type": "document_chunk",
                        **current_chunk.get('metadata', {})
                    }
                ))
                current_chunk['content'] = []

        # Über Body-Elemente iterieren (Absätze + Tabellen in Reihenfolge)
        body = doc.element.body
        for child in body:
            tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag

            if tag == 'p':
                # Absatz verarbeiten
                para = None
                for p in doc.paragraphs:
                    if p._element is child:
                        para = p
                        break
                if para is None:
                    continue

                # Heading-Erkennung
                style_name = para.style.name if para.style else ''
                is_heading = style_name.startswith('Heading') or style_name.startswith('Titel')

                if is_heading and para.text.strip():
                    flush_chunk()
                    current_chunk['title'] = para.text.strip()
                    continue

                # Bilder im Absatz finden
                blips = child.findall('.//' + qn('a:blip'))
                embed_ids = []
                for blip in blips:
                    embed = blip.get(qn('r:embed'))
                    if embed:
                        embed_ids.append(embed)

                for embed_id in embed_ids:
                    img_path = unique_images.get(embed_id)
                    if img_path and os.path.exists(img_path):
                        current_image += 1
                        print(f"Verarbeite Bild {current_image}/{unique_image_count}", flush=True)
                        b64image = self.encode_image(img_path)
                        result = self.process_image_with_retry(
                            b64image, img_path, current_image, unique_image_count
                        )
                        if 'image' in result:
                            current_chunk['content'].append({'image': result['image']})
                        elif 'error' in result:
                            pass

                # Text nach dem Bild im gleichen Absatz
                if para.text.strip():
                    current_chunk['content'].append(para.text)

            elif tag == 'tbl':
                # Tabelle als Markdown rendern
                table = None
                for t in doc.tables:
                    if t._element is child:
                        table = t
                        break
                if table is None:
                    continue

                rows = []
                for row in table.rows:
                    cells = [cell.text.strip() for cell in row.cells]
                    rows.append('| ' + ' | '.join(cells) + ' |')

                if rows:
                    # Header-Trennzeile einfügen
                    if len(rows) > 0:
                        col_count = len(table.rows[0].cells)
                        separator = '| ' + ' | '.join(['---'] * col_count) + ' |'
                        rows.insert(1, separator)

                    flush_chunk()
                    current_chunk['content'].append('\n'.join(rows))
                    flush_chunk()

        flush_chunk()

        _clear_dir(images_dir)

        return chunks