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
CHARS_PER_MINUTE = 150
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
    auto_continue = options.get("auto_continue", False)
    upload_youtube = options.get("upload_youtube", False)
    
    capa_path = os.path.join(output_dir, "capa.jpg")
    metadata_path = os.path.join(output_dir, "youtube_metadata.txt")
    
    state_file = os.path.join(output_dir, "state.txt")
    
    self.update_state(state='PROGRESS', meta={'message': f'Lendo arquivo: {filename}'})
    if filename.lower().endswith('.pdf'):
        full_text = extract_pdf_content(file_path, output_dir, custom_cover_path=cover_path)
    elif filename.lower().endswith('.epub'):
        full_text = extract_epub_content(file_path, output_dir, custom_cover_path=cover_path)
    else:
        raise ValueError("Formato de arquivo não suportado!")
    
    self.update_state(state='PROGRESS', meta={'message': 'Limpando texto...'})
    cleaned_data = clean_text(full_text)
    if isinstance(cleaned_data, dict):
        cleaned_text = cleaned_data.get("full_text", "")
    else:
        cleaned_text = cleaned_data
    
    if not cleaned_text:
        cleaned_text = "Texto do livro."
    
    intro_text = ""
    if title:
        intro_text = f"Livro: {title}."
        if author:
            intro_text += f" de {author}."
        if observations:
            intro_text += f" Observações: {observations}."
    
    chunks = split_text_into_time_chunks(cleaned_text, MAX_CHARS_PER_CHUNK)
    total_chunks = len(chunks)
    
    self.update_state(state='PROGRESS', meta={'message': f'Dividindo texto em {total_chunks} partes de 5 minutos...'})
    
    async def process_chunks_parallel():
        sem = asyncio.Semaphore(5)
        completed = 0
        audio_files = []
        
        if intro_text:
            intro_path = os.path.join(output_dir, "audio_000.mp3")
            self.update_state(state='PROGRESS', meta={'message': 'Sintetizando introdução...'})
            intro_text_adapted = adapt_for_tts(intro_text)
            if estimate_audio_duration(intro_text_adapted) > 60 * 60:
                await generate_long_audio(intro_text_adapted, intro_path, voice)
            else:
                await generate_chapter_audio(intro_text_adapted, intro_path, voice=voice)
            audio_files.append(intro_path)
        
        async def process_one(idx, chunk_text):
            nonlocal completed
            async with sem:
                audio_path = os.path.join(output_dir, f"audio_{idx+1:03d}.mp3")
                chunk_text_adapted = adapt_for_tts(chunk_text)
                
                if estimate_audio_duration(chunk_text_adapted) > 60 * 60:
                    await generate_long_audio(chunk_text_adapted, audio_path, voice)
                else:
                    await generate_chapter_audio(chunk_text_adapted, audio_path, voice=voice)
                
                completed += 1
                self.update_state(state='PROGRESS', 
                                  meta={'message': f'Sintetizando: {completed}/{total_chunks} concluídos (Lote de 5)'})
                return audio_path
        
        tasks = [process_one(i, chunk) for i, chunk in enumerate(chunks)]
        results = await asyncio.gather(*tasks)
        audio_files.extend(results)
        
        return audio_files
    
    audio_files = asyncio.run(process_chunks_parallel())
    
    with open(state_file, 'w') as f:
        f.write(f"audio_ready\n")
        f.write(f"title={title}\n")
        f.write(f"author={author}\n")
        f.write(f"observations={observations}\n")
        f.write(f"auto_continue={auto_continue}\n")
        f.write(f"upload_youtube={upload_youtube}\n")
    
    if auto_continue:
        self.update_state(state='PROGRESS', meta={'message': 'Prosseguindo automaticamente para geração de vídeo...'})
        generate_video_task.apply_async(args=[task_id])
    else:
        self.update_state(state='AUDIO_READY', meta={'message': f'Áudio pronto! {len(audio_files)} partes de 5 min geradas.'})
    
    return {"status": "AUDIO_READY", "task_id": task_id, "audio_count": len(audio_files)}

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
def generate_video_task(self, task_id: str):
    output_dir = os.path.join("/app/data/outputs", task_id)
    state_file = os.path.join(output_dir, "state.txt")
    
    title = ""
    author = ""
    observations = ""
    upload_youtube = False
    
    if os.path.exists(state_file):
        with open(state_file, 'r') as f:
            for line in f:
                if line.startswith("title="):
                    title = line.replace("title=", "").strip()
                elif line.startswith("author="):
                    author = line.replace("author=", "").strip()
                elif line.startswith("observations="):
                    observations = line.replace("observations=", "").strip()
                elif line.startswith("upload_youtube="):
                    upload_youtube = line.replace("upload_youtube=", "").strip() == "True"
    
    capa_path = os.path.join(output_dir, "capa.jpg")
    if not os.path.exists(capa_path):
        capa_path = None
    
    self.update_state(state='PROGRESS', meta={'message': 'Gerando vídeos de 5 minutos (lotes de 5)...'})
    
    audio_files = sorted([f for f in os.listdir(output_dir) if f.startswith("audio_") and f.endswith(".mp3")])
    total_videos = len(audio_files)
    
    video_files = []
    
    for i, audio_file in enumerate(audio_files):
        audio_path = os.path.join(output_dir, audio_file)
        video_path = os.path.join(output_dir, f"video_{i+1:03d}.mp4")
        
        self.update_state(state='PROGRESS', meta={'message': f'Compondo vídeo {i+1}/{total_videos}...'})
        
        if capa_path:
            compose_video(capa_path, audio_path, video_path)
        else:
            compose_video(None, audio_path, video_path)
        
        video_files.append(video_path)
    
    if len(video_files) > 1:
        self.update_state(state='PROGRESS', meta={'message': 'Unindo todos os vídeos em um só...'})
        final_video = os.path.join(output_dir, "video_final.mp4")
        merge_video_files(video_files, final_video)
        final_video_path = final_video
    else:
        final_video_path = video_files[0]
    
    metadata_path = os.path.join(output_dir, "youtube_metadata.txt")
    with open(metadata_path, "w") as f:
        f.write(f"TÍTULO: {title if title else 'Livro Narrado'}\n")
        f.write(f"AUTOR: {author if author else 'Não informado'}\n")
        if observations:
            f.write(f"OBSERVAÇÕES: {observations}\n")
        f.write("-" * 30 + "\n")
        f.write("Partes:\n")
        for i, vf in enumerate(video_files):
            minutes = (i + 1) * 5
            f.write(f"Parte {i+1}: {minutes} min\n")
    
    with open(state_file, 'a') as f:
        f.write("video_ready\n")
    
    if upload_youtube and os.path.exists(final_video_path):
        self.update_state(state='PROGRESS', meta={'message': 'Enviando para YouTube...'})
        upload_youtube_task.apply_async(args=[task_id])
    else:
        self.update_state(state='VIDEO_READY', meta={'message': 'Vídeo pronto! Enviar para YouTube?'})
    
    return {"status": "VIDEO_READY", "task_id": task_id, "video_path": final_video_path}

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