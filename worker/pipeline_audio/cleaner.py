import re
from num2words import num2words
import unicodedata

def clean_text(raw_pages: list):
    """
    Remove lixos (números de página, hífens de quebra de linha)
    e tenta detectar capítulos.
    """
    full_text = ""
    for p in raw_pages:
        t = p['text']
        # Corrigir quebra de linha de hífens (pala- \nvra -> palavra)
        t = re.sub(r'(\w+)-\s*\n\s*(\w+)', r'\1\2', t)
        # Unir paragrafos quebrados por novas linhas indevidas
        t = re.sub(r'(?<!\n)\n(?!\n)', ' ', t)
        full_text += t + "\n\n"
        
    # Detectar capítulos usando regex (Ex: Capítulo 1, CAPÍTULO I, etc)
    pattern = r'(?m)^\s*(?:CAPÍTULO|Capítulo|Cap\.)\s+([0-9IVXLCDM]+)(?:\s*[-:]\s*(.*?))?$'
    chapters = []
    
    parts = list(re.finditer(pattern, full_text))
    if not parts:
        # Se não achar nada, trata o livro todo como capítulo único
        chapters.append({"title": "Início", "text": full_text})
    else:
        for i, match in enumerate(parts):
            title = f"Capítulo {match.group(1)}"
            if match.group(2):
                title += f" - {match.group(2).strip()}"
                
            start = match.end()
            end = parts[i+1].start() if i + 1 < len(parts) else len(full_text)
            chapters.append({
                "title": title,
                "text": full_text[start:end].strip()
            })
            
    return chapters

def adapt_for_tts(text: str):
    """
    Expande abreviações e números para uma leitura fluida.
    """
    # 1. Expandir Abreviações
    replacements = {
        r'\bSr\.': 'Senhor',
        r'\bSra\.': 'Senhora',
        r'\bDra\.': 'Doutora',
        r'\bDr\.': 'Doutor',
        r'\bD\.': 'Dona',
        r'\bp\.': 'página',
        r'\betc\.': 'etcétera',
    }
    for k, v in replacements.items():
        text = re.sub(k, v, text)
        
    # 2. Expandir Números (Inteiros simples)
    def num_to_pt(match):
        return num2words(int(match.group(0)), lang='pt_BR')
        
    text = re.sub(r'\b\d+\b', num_to_pt, text)
    
    return text
