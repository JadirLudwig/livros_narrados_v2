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

async def generate_chapter_audio(chapter_text: str, output_path: str, voice: str = "pt-BR-FranciscaNeural"):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            communicate = edge_tts.Communicate(chapter_text, voice)
            await communicate.save(output_path)
            return
        except Exception as e:
            if attempt == max_retries - 1:
                raise e
            wait = (attempt + 1) * 5
            print(f"Erro no TTS (tentativa {attempt+1}): {e}. Retentando em {wait}s...")
            await asyncio.sleep(wait)

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
