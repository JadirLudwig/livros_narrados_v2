from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, APIC, error
import os

def inject_metadata(mp3_path: str, title: str, author: str, image_path: str = None):
    """
    Grava Título, Autor e a Imagem da Capa diretamente dentro do arquivo MP3 (Tags ID3).
    """
    if not os.path.exists(mp3_path):
        print(f"Erro: Arquivo MP3 não encontrado ({mp3_path})")
        return False

    try:
        audio = MP3(mp3_path, ID3=ID3)
        
        # Adicionar tags se não existirem
        try:
            audio.add_tags()
        except error:
            pass # As tags já existem

        # Título do Livro
        if title:
            audio.tags.add(TIT2(encoding=3, text=title))
        
        # Autor
        if author:
            audio.tags.add(TPE1(encoding=3, text=author))

        # Capa do Livro (APIC)
        if image_path and os.path.exists(image_path):
            with open(image_path, "rb") as img:
                audio.tags.add(APIC(
                    encoding=3,
                    mime='image/jpeg',
                    type=3, # Tipo 3 é para Capa Frontal
                    desc='Capa do Livro Narrado',
                    data=img.read()
                ))

        audio.save()
        return True
    except Exception as e:
        print(f"Erro ao injetar metadados ID3: {e}")
        return False
