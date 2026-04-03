import os
import io
import pydub
from pydub import AudioSegment
from pydub.effects import normalize
from pedalboard import Pedalboard, Compressor, HighpassFilter, Reverb, LowShelfFilter
from pedalboard.io import AudioFile
import soundfile as sf

# Cache do pipeline para o Kokoro
_kokoro_pipeline = None

def _get_pipeline():
    global _kokoro_pipeline
    if _kokoro_pipeline is None:
        from kokoro import KPipeline
        import onnxruntime as ort
        
        # Verifica se CUDA está disponível no ONNX Runtime
        providers = ort.get_available_providers()
        device = 'cuda' if 'CUDAExecutionProvider' in providers else 'cpu'
        
        print(f"[INFO] Inicializando Kokoro Pipeline no dispositivo: {device}")
        # O Kokoro-python aceita o argumento device ou infere do onnxruntime-gpu
        _kokoro_pipeline = KPipeline(lang_code='p', device=device)
    return _kokoro_pipeline

MAX_CHUNK_CHARS = 1000 # Kokoro lida bem com chunks menores de 1k para estabilidade

def _sanitize_for_tts(text: str) -> str:
    """Limpeza para o Kokoro."""
    import unicodedata, re
    text = ''.join(c for c in text if unicodedata.category(c)[0] != 'C' or c in ' \n')
    text = re.sub(r'https?://\S+|www\.\S+', '', text)
    clean_lines = []
    for line in text.split('\n'):
        stripped = line.strip()
        if not stripped: continue
        letter_count = sum(1 for c in stripped if c.isalpha())
        if letter_count >= 3:
            clean_lines.append(stripped)
    result = ' '.join(clean_lines).strip()
    result = re.sub(r' {2,}', ' ', result)
    return result

async def generate_chapter_audio(chapter_text: str, output_path: str, voice: str = "pf_dora"):
    """Gera áudio usando Kokoro-82M Local."""
    clean = _sanitize_for_tts(chapter_text)
    if not clean or len(clean) < 5:
        print(f"[AVISO] Texto insuficiente, gerando silêncio.")
        silence = AudioSegment.silent(duration=1000)
        silence.export(output_path, format="mp3")
        return

    pipeline = _get_pipeline()
    
    # Kokoro gera geradores de áudio (processa por sentença)
    generator = pipeline(clean, voice=voice, speed=1.0, split_pattern=r'\n+')
    
    import numpy as np
    all_audio = []
    
    # Processa as sentenças geradas
    for gs, ps, audio in generator:
        if audio is not None:
            all_audio.append(audio)
    
    if not all_audio:
        print("[ERRO] Kokoro não gerou áudio.")
        return

    # Concatena os arrays numpy do Kokoro
    combined_np = np.concatenate(all_audio)
    
    # Salva temporário em WAV e converte para MP3 via pydub para manter compatibilidade
    temp_wav = output_path.replace(".mp3", "_tmp.wav")
    sf.write(temp_wav, combined_np, 24000)
    
    segment = AudioSegment.from_wav(temp_wav)
    segment.export(output_path, format="mp3")
    
    if os.path.exists(temp_wav):
        os.remove(temp_wav)

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
