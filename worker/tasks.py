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
    upload_youtube = options.get("upload_youtube", False)
    
    capa_path = os.path.join(output_dir, "capa_base.jpg")
    final_mp3_path = os.path.join(output_dir, "audio_completo_master.mp3")
    metadata_path = os.path.join(output_dir, "youtube_metadata.txt")
    
    self.update_state(state='PROGRESS', meta={'message': f'Lendo arquivo: {filename}'})
    if filename.lower().endswith('.pdf'):
        pages = extract_pdf_content(file_path, output_dir, custom_cover_path=cover_path)
    elif filename.lower().endswith('.epub'):
        pages = extract_epub_content(file_path, output_dir, custom_cover_path=cover_path)
    else:
        raise ValueError("Formato de arquivo não suportado!")
        
    self.update_state(state='PROGRESS', meta={'message': 'Limpando texto e detectando capítulos...'})
    chapters = clean_text(pages)
    
    temp_mp3s = []
    
    if title:
        intro_text = f"Livro: {title}."
        if author:
            intro_text += f" de {author}."
        if observations:
            intro_text += f" Observações: {observations}."
        
        intro_mp3_path = os.path.join(output_dir, "intro.mp3")
        self.update_state(state='PROGRESS', meta={'message': 'Sintetizando Introdução do Livro...'})
        
        full_intro = intro_text + " "
        if estimate_audio_duration(full_intro) > 60 * 60:
            asyncio.run(generate_long_audio(full_intro, intro_mp3_path, voice))
        else:
            asyncio.run(generate_chapter_audio(full_intro, intro_mp3_path, voice=voice))
        
        temp_mp3s.append(intro_mp3_path)

    chapter_count = len(chapters)
    self.update_state(state='PROGRESS', meta={'message': f'Iniciando síntese simultânea de {chapter_count} capítulos...'})
    
    async def process_chapters_parallel():
        sem = asyncio.Semaphore(5)
        completed = 0
        
        async def process_one(i, chap):
            nonlocal completed
            async with sem:
                chap_mp3_path = os.path.join(output_dir, f"chap_{i+1:02d}.mp3")
                to_read = chap["title"] + ". " + chap["text"]
                to_read = adapt_for_tts(to_read)
                
                if estimate_audio_duration(to_read) > 60 * 60:
                    await generate_long_audio(to_read, chap_mp3_path, voice)
                else:
                    await generate_chapter_audio(to_read, chap_mp3_path, voice=voice)
                
                completed += 1
                self.update_state(state='PROGRESS', 
                                  meta={'message': f'Sintetizando: {completed}/{chapter_count} concluídos (Lote de 5)'})
                return chap_mp3_path
                
        tasks = [process_one(i, chap) for i, chap in enumerate(chapters)]
        return await asyncio.gather(*tasks)
        
    chapter_mp3s = asyncio.run(process_chapters_parallel())
    
    self.update_state(state='PROGRESS', meta={'message': 'Unindo áudios e gerando índices de tempo...'})
    
    merge_info = []
    if title:
        merge_info.append({"path": os.path.join(output_dir, "intro.mp3"), "title": "Introdução"})
    
    for i, path in enumerate(chapter_mp3s):
        merge_info.append({
            "path": path,
            "title": chapters[i]["title"]
        })
        
    master_mp3_path_actual, youtube_timestamps = merge_audio_files(merge_info, final_mp3_path)
    
    self.update_state(state='PROGRESS', meta={'message': 'Injetando metadados e arte de capa no MP3...'})
    inject_metadata(final_mp3_path, title if title else filename, author, capa_path if os.path.exists(capa_path) else None)

    with open(metadata_path, "w") as f:
        f.write(f"LIVRO: {title if title else filename}\n")
        f.write(f"AUTOR: {author if author else 'Não informado'}\n")
        if observations:
            f.write(f"OBSERVAÇÕES: {observations}\n")
        f.write("-" * 30 + "\n")
        f.write("\n".join(youtube_timestamps))

    video_path = None
    if os.path.exists(capa_path):
        self.update_state(state='PROGRESS', meta={'message': 'Compondo vídeo em HD (720p)...'})
        target_video = os.path.join(output_dir, "video_youtube.mp4")
        video_path = compose_video(capa_path, final_mp3_path, target_video)

    self.update_state(state='PROGRESS', meta={'message': 'Finalizando pacote ZIP Premium...'})
    zip_path = os.path.join("/app/data/outputs", f"{task_id}_pack.zip")
    
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        zipf.write(final_mp3_path, arcname="audio_completo_master.mp3")
        zipf.write(metadata_path, arcname="youtube_metadata.txt")
        
        if os.path.exists(capa_path):
            zipf.write(capa_path, arcname="cover.jpg")
        if video_path and os.path.exists(video_path):
            zipf.write(video_path, arcname="video_book.mp4")

    if upload_youtube and video_path and os.path.exists(video_path):
        self.update_state(state='PROGRESS', meta={'message': 'Injetando vídeo diretamente no canal do YouTube...'})
        with open(metadata_path, 'r') as desc_file:
            full_description = desc_file.read()
        
        video_id = upload_video_to_youtube(video_path, title if title else filename, full_description)
        if video_id:
            self.update_state(state='PROGRESS', meta={'message': f'Upload no YouTube Completo! ID: {video_id}'})

    import shutil
    try:
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)
        upload_dir = os.path.dirname(file_path)
        if os.path.exists(upload_dir) and "/app/data/uploads" in upload_dir:
            shutil.rmtree(upload_dir)
    except Exception as e:
        print(f"Erro ao limpar arquivos temporários: {e}")
            
    return {"status": "SUCCESS", "zip": zip_path}
