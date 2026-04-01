import pdfplumber
import ebooklib
from ebooklib import epub
import html2text
import os
import fitz
from PIL import Image
import io
import shutil

def extract_pdf_content(pdf_path: str, output_dir: str, custom_cover_path: str | None = None):
    """
    Extrai texto página a página de um PDF e salva a primeira como capa,
    ou usa a capa personalizada se fornecida.
    """
    full_text = ""
    capa_path = os.path.join(output_dir, "capa.jpg")
    
    if custom_cover_path and os.path.exists(custom_cover_path):
        shutil.copy(custom_cover_path, capa_path)
    else:
        doc = fitz.open(pdf_path)
        if len(doc) > 0:
            page = doc[0]
            pix = page.get_pixmap(dpi=150)
            img = Image.open(io.BytesIO(pix.tobytes()))
            img.convert('RGB').save(capa_path, "JPEG", quality=90)
        doc.close()

    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text(x_tolerance=3, y_tolerance=3)
            if text:
                full_text += text + "\n\n"
                
    return full_text.strip()

def extract_epub_content(epub_path: str, output_dir: str, custom_cover_path: str | None = None):
    """
    Extrai texto e tenta localizar a capa de um EPUB.
    """
    book = epub.read_epub(epub_path)
    full_text = ""
    capa_path = os.path.join(output_dir, "capa.jpg")
    
    if custom_cover_path and os.path.exists(custom_cover_path):
        shutil.copy(custom_cover_path, capa_path)
    else:
        cover_item = None
        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_IMAGE and ('cover' in item.get_id().lower() or 'cover' in item.get_name().lower()):
                cover_item = item
                break
        
        if cover_item:
            img = Image.open(io.BytesIO(cover_item.get_content()))
            img.convert('RGB').save(capa_path, "JPEG", quality=90)

    h = html2text.HTML2Text()
    h.ignore_links = True
    h.ignore_images = True
    h.ignore_emphasis = True
    
    for item in book.get_items():
        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            content = item.get_content().decode('utf-8')
            text = h.handle(content)
            if text.strip():
                full_text += text + "\n\n"
                
    return full_text.strip()
