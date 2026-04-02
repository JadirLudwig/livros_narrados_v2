import asyncio
import edge_tts
import os
import io
import pydub
import numpy as np
from pydub import AudioSegment
from pydub.effects import normalize
from pedalboard import Pedalboard, Compressor, HighpassFilter, Reverb, LowShelfFilter
from pedalboard.io import AudioFile

MAX_CHUNK_CHARS = 8000
# Limite conservador por requisição edge-tts (evita "No audio was received")
EDGE_TTS_MAX_CHARS = 2000

def _sanitize_for_tts(text: str) -> str:
    """Limpeza agressiva para garantir texto pronunciável pelo edge-tts."""
    import unicodedata, re
    # 1. Remove caracteres de controle (exceto espaço e newline)
    text = ''.join(c for c in text if unicodedata.category(c)[0] != 'C' or c in ' \n')
    # 2. Remove URLs
    text = re.sub(r'https?://\S+|www\.\S+', '', text)
    # 3. Remove linhas que são só números/símbolos/pontuação (ISBN, número de página, etc.)
    clean_lines = []
    for line in text.split('\n'):
        stripped = line.strip()
        if not stripped:
            continue
        # Conta quantos caracteres são letras
        letter_count = sum(1 for c in stripped if c.isalpha())
        # Só inclui a linha se tiver pelo menos 5 letras e 30% do conteúdo for letras
        if letter_count >= 5 and (letter_count / max(len(stripped), 1)) >= 0.3:
            clean_lines.append(stripped)
    result = ' '.join(clean_lines).strip()
    # 4. Colapsa espaços múltiplos
    result = re.sub(r' {2,}', ' ', result)
    return result

async def _try_generate_audio(text: str, output_path: str, voice: str) -> bool:
    """Tenta gerar áudio. Retorna True se sucesso, False se falhar."""
    try:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_path)
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return True
        return False
    except Exception as e:
        print(f"[TTS] Falha ao gerar áudio: {e}")
        return False

async def _generate_silence(output_path: str, duration_ms: int = 1000):
    """Gera arquivo de silêncio como fallback."""
    silence = AudioSegment.silent(duration=duration_ms)
    silence.export(output_path, format="mp3")

async def generate_chapter_audio(chapter_text: str, output_path: str, voice: str = "pt-BR-FranciscaNeural"):
    """Gera áudio de um capítulo com estratégia fail-safe total.
    
    - Sanitiza o texto agressivamente
    - Divide em sub-chunks de 2000 chars (limite seguro edge-tts)
    - Sub-chunks que falham viram silêncio (nunca para o processo)
    """
    # Sanitiza e valida
    clean = _sanitize_for_tts(chapter_text)
    if not clean or len(clean) < 10:
        print(f"[AVISO] Texto insuficiente após sanificação ({len(clean)} chars), gerando silêncio.")
        await _generate_silence(output_path)
        return

    # Divide em sub-chunks por palavras (nunca corta no meio de uma)
    sub_chunks = []
    words = clean.split()
    current = []
    current_len = 0
    for word in words:
        if current_len + len(word) + 1 > EDGE_TTS_MAX_CHARS and current:
            sub_chunks.append(' '.join(current))
            current = [word]
            current_len = len(word)
        else:
            current.append(word)
            current_len += len(word) + 1
    if current:
        sub_chunks.append(' '.join(current))

    if len(sub_chunks) == 1:
        # Texto curto: tenta com até 3 retentativas
        for attempt in range(5):
            success = await _try_generate_audio(sub_chunks[0], output_path, voice)
            if success:
                return
            await asyncio.sleep((attempt + 1) * 10)
        # Fallback: silêncio
        print(f"[FALLBACK] Sub-chunk único falhou, gerando silêncio: {output_path}")
        await _generate_silence(output_path)
        return

    print(f"[TTS] Dividindo em {len(sub_chunks)} sub-chunks ({len(clean)} chars total).")
    temp_files = []
    combined = AudioSegment.empty()

    for i, sub in enumerate(sub_chunks):
        temp_path = output_path.replace('.mp3', f'_sub{i}.mp3')
        temp_files.append(temp_path)

        success = False
        for attempt in range(5):
            success = await _try_generate_audio(sub, temp_path, voice)
            if success:
                break
            await asyncio.sleep((attempt + 1) * 10)

        if not success:
            print(f"[FALLBACK] Sub-chunk {i+1}/{len(sub_chunks)} falhou, inserindo silêncio.")
            await _generate_silence(temp_path, duration_ms=800)

    # Combina todos os sub-chunks (inclusive os silêncio de fallback)
    for tp in temp_files:
        if os.path.exists(tp) and os.path.getsize(tp) > 0:
            try:
                combined += AudioSegment.from_mp3(tp)
            except Exception as e:
                print(f"[AVISO] Não foi possível carregar {tp}: {e}")
        if os.path.exists(tp):
            os.remove(tp)

    if len(combined) == 0:
        print(f"[FALLBACK TOTAL] Nenhum sub-chunk gerou áudio, gerando silêncio para {output_path}")
        await _generate_silence(output_path, duration_ms=2000)
    else:
        combined.export(output_path, format="mp3")

def split_text_into_chunks(text: str, max_chars: int = MAX_CHUNK_CHARS):
    chunks = []
    paragraphs = text.split('\n\n')
    current_chunk = ""
    
    for para in paragraphs:
        if len(current_chunk) + len(para) <= max_chars:
            current_chunk += para + "\n\n"
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            if len(para) > max_chars:
                sentences = para.split('. ')
                current_chunk = ""
                for sent in sentences:
                    if len(current_chunk) + len(sent) <= max_chars:
                        current_chunk += sent + ". "
                    else:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                        current_chunk = sent + ". "
                current_chunk = current_chunk.strip()
            else:
                current_chunk = para + "\n"
    
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    
    return chunks

def estimate_audio_duration(text: str, words_per_minute: int = 150) -> float:
    word_count = len(text.split())
    return (word_count / words_per_minute) * 60

async def generate_long_audio(text: str, output_path: str, voice: str, max_duration_minutes: int = 60):
    temp_files = []
    
    chunks = split_text_into_chunks(text, MAX_CHUNK_CHARS)
    
    print(f"Texto dividido em {len(chunks)} chunks para evitar limite de 60 minutos")
    
    for i, chunk in enumerate(chunks):
        temp_file = f"{output_path}_chunk_{i}.mp3"
        temp_files.append(temp_file)
        await generate_chapter_audio(chunk, temp_file, voice)
    
    final_audio = AudioSegment.empty()
    silence = AudioSegment.silent(duration=1500)
    
    for i, temp_file in enumerate(temp_files):
        if os.path.exists(temp_file):
            segment = AudioSegment.from_mp3(temp_file)
            final_audio += segment
            if i < len(temp_files) - 1:
                final_audio += silence
    
    final_audio.export(output_path, format="mp3")
    
    for temp_file in temp_files:
        if os.path.exists(temp_file):
            os.remove(temp_file)
    
    return output_path

def apply_voice_enhancement(input_path: str, output_path: str):
    with AudioFile(input_path) as f:
        audio = f.read(f.frames)
        sample_rate = f.samplerate

    board = Pedalboard([
        HighpassFilter(cutoff_frequency_hz=80),
        Compressor(threshold_db=-18, ratio=4),
        LowShelfFilter(cutoff_frequency_hz=400, gain_db=2),
        Reverb(room_size=0.05, dry_level=0.95, wet_level=0.03)
    ])

    effected = board(audio, sample_rate)

    with AudioFile(output_path, 'w', sample_rate, num_channels=effected.shape[0]) as f:
        f.write(effected)

def format_timestamp(ms: int) -> str:
    seconds = int((ms / 1000) % 60)
    minutes = int((ms / (1000 * 60)) % 60)
    hours = int((ms / (1000 * 60 * 60)) % 24)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def merge_audio_files(chapters_info: list, output_path: str, lufs: float = -16.0, pause_duration_ms: int = 2500):
    full_audio = AudioSegment.empty()
    silence = AudioSegment.silent(duration=pause_duration_ms)
    timestamps = []
    current_time_ms = 0
    
    for i, chap in enumerate(chapters_info):
        path = chap["path"]
        title = chap["title"]
        
        if os.path.exists(path):
            segment = AudioSegment.from_mp3(path)
            segment = segment.fade_in(500).fade_out(500)
            
            short_title = title[:50] + "..." if len(title) > 50 else title
            timestamps.append(f"{format_timestamp(current_time_ms)} - {short_title}")
            
            full_audio += segment
            current_time_ms += len(segment)
            
            if i < len(chapters_info) - 1:
                full_audio += silence
                current_time_ms += pause_duration_ms
            
    full_audio = normalize(full_audio)
    
    temp_wav = output_path.replace(".mp3", "_raw.wav")
    full_audio.export(temp_wav, format="wav")
    
    try:
        apply_voice_enhancement(temp_wav, output_path)
    finally:
        if os.path.exists(temp_wav):
            os.remove(temp_wav)
            
    return output_path, timestamps
