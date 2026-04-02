from worker.celery_app import celery_app
import time
import os
import asyncio
import zipfile
from worker.pipeline_audio.extractor import extract_pdf_content, extract_epub_content
from worker.pipeline_audio.cleaner import clean_text, adapt_for_tts
from worker.pipeline_audio.audio_processor import generate_chapter_audio, merge_audio_files, generate_long_audio, estimate_audio_duration
from worker.pipeline_audio.metadata_injector import inject_metadata
from worker.pipeline_video.video_composer import compose_video
from worker.pipeline_video.youtube_uploader import upload_video_to_youtube

CHUNK_DURATION_MINUTES = 5
CHARS_PER_MINUTE = 1100  # Ajustado para ~160 palavras por minuto (velocidade natural)
MAX_CHARS_PER_CHUNK = CHUNK_DURATION_MINUTES * CHARS_PER_MINUTE

@celery_app.task(bind=True)
def process_pdf_task(self, file_path: str, options: dict):
    task_id = self.request.id
    output_dir = os.path.join("/app/data/outputs", task_id)
    os.makedirs(output_dir, exist_ok=True)
    
    filename = options.get("filename", "livro")
    voice = options.get("voice", "pt-BR-FranciscaNeural")
    title = options.get("title", "").strip()
    author = options.get("author", "").strip()
    observations = options.get("observations", "").strip()
    cover_path = options.get("cover_path")
    
    capa_path = os.path.join(output_dir, "capa.jpg")
    state_file = os.path.join(output_dir, "state.txt")
    
    def extraction_progress(current, total):
        self.update_state(state='PROGRESS', meta={'message': f'📄 Lendo página {current} de {total}...'})

    if filename.lower().endswith('.pdf'):
        full_text = extract_pdf_content(file_path, output_dir, custom_cover_path=cover_path, progress_callback=extraction_progress)
    elif filename.lower().endswith('.epub'):
        self.update_state(state='PROGRESS', meta={'message': '📖 Extraindo conteúdo do EPUB...'})
        full_text = extract_epub_content(file_path, output_dir, custom_cover_path=cover_path)
    else:
        raise ValueError("Formato de arquivo não suportado!")
    
    self.update_state(state='PROGRESS', meta={'message': f'🧹 Limpando {len(full_text)} caracteres...'})
    cleaned_data = clean_text(full_text)
    cleaned_text = cleaned_data.get("full_text", "") if isinstance(cleaned_data, dict) else cleaned_data
    
    if not cleaned_text:
        cleaned_text = "Texto do livro vazio ou não extraível."
    
    intro_text = ""
    if title:
        intro_text = f"Livro: {title}. de {author}. {observations}" if author else f"Livro: {title}. {observations}"
    
    chunks = split_text_into_time_chunks(cleaned_text, MAX_CHARS_PER_CHUNK)
    total_chunks = len(chunks)
    self.update_state(state='PROGRESS', meta={'message': f'📦 Livro dividido em {total_chunks} blocos de 5 min.'})
    
    # Salvar chunks restantes para continuação posterior (Separador Robusto)
    chunks_file = os.path.join(output_dir, "chunks_remaining.txt")
    with open(chunks_file, 'w') as f:
        f.write("|||CHUNK_SEP|||".join(chunks))

    self.update_state(state='PROGRESS', meta={'message': 'Gerando amostra inicial (5 min)...'})
    
    # Processar Amostra (Intro + Chunk 1)
    async def process_sample():
        audio_items = []
        if intro_text:
            intro_path = os.path.join(output_dir, "audio_000.mp3")
            await generate_chapter_audio(adapt_for_tts(intro_text), intro_path, voice=voice)
            audio_items.append({"path": intro_path, "title": "Introdução"})
        
        # Primeiro Chunk
        chunk_1_audio = os.path.join(output_dir, "audio_001.mp3")
        await generate_chapter_audio(adapt_for_tts(chunks[0]), chunk_1_audio, voice=voice)
        audio_items.append({"path": chunk_1_audio, "title": "Parte 1"})
        
        # Gerar Áudio da Amostra (Unindo intro se houver)
        sample_audio_file = "sample_audio.mp3"
        sample_audio_path = os.path.join(output_dir, sample_audio_file)
        if len(audio_items) > 1:
            merge_audio_files(audio_items, sample_audio_path)
        else:
            # Caso não tenha intro, copiar o audio_001 como sample_audio
            import shutil
            shutil.copy(audio_items[0]["path"], sample_audio_path)
            
        return sample_audio_file

    sample_audio_name = asyncio.run(process_sample())
    
    with open(state_file, 'w') as f:
        f.write(f"SAMPLE_READY\n")
        f.write(f"voice={voice}\n")
        f.write(f"title={title}\n")
        f.write(f"author={author}\n")
        f.write(f"observations={observations}\n")
        f.write(f"total_chunks={total_chunks}\n")
        f.write(f"sample_audio={sample_audio_name}\n")
    
    return {"status": "SAMPLE_READY", "task_id": task_id, "total_chunks": total_chunks}

def split_text_into_time_chunks(text: str, max_chars: int):
    chunks = []
    paragraphs = text.split('\n\n')
    current_chunk = ""
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
            
        if len(current_chunk) + len(para) <= max_chars:
            current_chunk += para + "\n\n"
        else:
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            
            if len(para) > max_chars:
                sentences = para.split('. ')
                current_chunk = ""
                for sent in sentences:
                    if len(current_chunk) + len(sent) <= max_chars:
                        current_chunk += sent + ". "
                    else:
                        if current_chunk.strip():
                            chunks.append(current_chunk.strip())
                        current_chunk = sent + ". "
                current_chunk = current_chunk.strip()
            else:
                current_chunk = para + "\n"
    
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    
    return chunks

@celery_app.task(bind=True)
def continue_full_process_task(self, task_id: str):
    output_dir = os.path.join("/app/data/outputs", task_id)
    state_file = os.path.join(output_dir, "state.txt")
    chunks_file = os.path.join(output_dir, "chunks_remaining.txt")
    
    voice, title, author, total_chunks = "pt-BR-FranciscaNeural", "", "", 0
    if os.path.exists(state_file):
        with open(state_file, 'r') as f:
            for line in f:
                if line.startswith("voice="): voice = line.split("=")[1].strip()
                if line.startswith("title="): title = line.split("=")[1].strip()
                if line.startswith("author="): author = line.split("=")[1].strip()
                if line.startswith("total_chunks="): total_chunks = int(line.split("=")[1].strip())

    if not os.path.exists(chunks_file):
        return {"status": "ERROR", "message": "Arquivo de chunks não encontrado."}

    chunks = []
    with open(chunks_file, 'r') as f:
        data = f.read()
        chunks = data.split("|||CHUNK_SEP|||")

    capa_path = os.path.join(output_dir, "capa.jpg")
    if not os.path.exists(capa_path): capa_path = None

    self.update_state(state='PROGRESS', meta={'message': f'Processando {total_chunks} partes (Paralelo)...'})

    async def process_pipeline_parallel():
        sem = asyncio.Semaphore(5)
        completed = 0
        
        async def process_one(idx, text):
            nonlocal completed
            async with sem:
                audio_path = os.path.join(output_dir, f"audio_{idx+1:03d}.mp3")
                video_path = os.path.join(output_dir, f"video_{idx+1:03d}.mp4")
                
                await generate_chapter_audio(adapt_for_tts(text), audio_path, voice=voice)
                compose_video(capa_path, audio_path, video_path)
                
                completed += 1
                self.update_state(state='PROGRESS', meta={'message': f'🚀 Lote {completed}/{total_chunks} finalizado (Áudio+Vídeo)'})
                return video_path

        tasks = [process_one(i, chunks[i]) for i in range(len(chunks))]
        video_files = await asyncio.gather(*tasks)
        return video_files

    # Executa o pipeline paralelo e obtém a lista de caminhos dos vídeos
    video_files = asyncio.run(process_pipeline_parallel())

    self.update_state(state='PROGRESS', meta={'message': 'Unindo todos os vídeos e gerando metadata...'})
    final_video = os.path.join(output_dir, "video_final.mp4")
    merge_video_files(video_files, final_video)

    # Gerar metadata para o YouTube
    metadata_path = os.path.join(output_dir, "youtube_metadata.txt")
    with open(metadata_path, "w") as f:
        f.write(f"TÍTULO: {title}\nAUTOR: {author}\n")
        f.write("-" * 30 + "\nCapítulos:\n")
        for i in range(len(video_files)):
            f.write(f"Parte {i+1}: {(i*5):02d}:00\n")

    # Upload Automático para YouTube (Sempre automático agora na fase full)
    self.update_state(state='PROGRESS', meta={'message': 'Enviando para o YouTube...'})
    upload_youtube_task.apply_async(args=[task_id])
    
    return {"status": "SUCCESS", "task_id": task_id}

def merge_video_files(video_paths: list, output_path: str):
    import subprocess
    
    list_file = os.path.join(os.path.dirname(output_path), "videos.txt")
    with open(list_file, 'w') as f:
        for vp in video_paths:
            f.write(f"file '{vp}'\n")
    
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file,
        "-c", "copy", output_path
    ]
    
    subprocess.run(cmd, check=True)
    
    if os.path.exists(list_file):
        os.remove(list_file)

@celery_app.task(bind=True)
def upload_youtube_task(self, task_id: str):
    output_dir = os.path.join("/app/data/outputs", task_id)
    state_file = os.path.join(output_dir, "state.txt")
    
    title = ""
    author = ""
    observations = ""
    
    if os.path.exists(state_file):
        with open(state_file, 'r') as f:
            for line in f:
                if line.startswith("title="):
                    title = line.replace("title=", "").strip()
                elif line.startswith("author="):
                    author = line.replace("author=", "").strip()
                elif line.startswith("observations="):
                    observations = line.replace("observations=", "").strip()
    
    video_path = os.path.join(output_dir, "video_final.mp4")
    if not os.path.exists(video_path):
        video_files = sorted([f for f in os.listdir(output_dir) if f.startswith("video_") and f.endswith(".mp4")])
        if video_files:
            video_path = os.path.join(output_dir, video_files[-1])
    
    metadata_path = os.path.join(output_dir, "youtube_metadata.txt")
    description = ""
    if os.path.exists(metadata_path):
        with open(metadata_path, 'r') as f:
            description = f.read()
    
    video_title = title if title else "Livro Narrado"
    if author:
        video_title += f" - {author}"
    video_title += " | Audiolivro Completo"
    
    self.update_state(state='PROGRESS', meta={'message': 'Fazendo upload para o YouTube...'})
    
    video_id = upload_video_to_youtube(video_path, video_title, description)
    
    if video_id:
        self.update_state(state='SUCCESS', meta={'message': f'Upload concluído! Vídeo ID: {video_id}'})
        
        zip_path = os.path.join("/app/data/outputs", f"{task_id}_pack.zip")
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for filename in os.listdir(output_dir):
                file_path = os.path.join(output_dir, filename)
                if os.path.isfile(file_path):
                    zipf.write(file_path, arcname=filename)
        
        return {"status": "SUCCESS", "video_id": video_id, "zip": zip_path}
    else:
        self.update_state(state='FAILURE', meta={'message': 'Falha no upload para o YouTube'})
        return {"status": "FAILURE", "error": "Upload failed"}