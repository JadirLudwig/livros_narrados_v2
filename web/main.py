from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request
from celery.result import AsyncResult
from worker.tasks import process_pdf_task, continue_full_process_task, upload_youtube_task
from fastapi.staticfiles import StaticFiles
import os
import uuid
import shutil
import json
import subprocess
import zipfile
import time

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

try:
    from google_auth_oauthlib.flow import Flow
except ImportError:
    pass

YOUTUBE_SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
CLIENT_SECRETS_FILE = "/app/data/client_secret.json"
TOKEN_FILE = "/app/data/youtube_token.json"

oauth_flow_session = {}

app = FastAPI(title="Livros Narrados V3")
templates = Jinja2Templates(directory="web/templates")

if not os.path.exists("web/static"):
    os.makedirs("web/static")
UPLOAD_DIR = "/app/data/uploads"
OUTPUT_DIR = "/app/data/outputs"

app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse(request, "index.html")

def cleanup_old_data():
    for folder in [UPLOAD_DIR, OUTPUT_DIR]:
        if not os.path.exists(folder):
            continue
        for filename in os.listdir(folder):
            file_path = os.path.join(folder, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f"Erro ao deletar {file_path}: {e}")

@app.post("/api/process_book")
async def process_book(
    file: UploadFile = File(None),
    voice: str = Form("pt-BR-FranciscaNeural"),
    title: str = Form(""),
    author: str = Form(""),
    observations: str = Form(""),
    cover: UploadFile = File(None),
    auto_continue: bool = Form(False),
    upload_youtube: bool = Form(False),
    reuse_id: str = Form(None)
):
    task_id = reuse_id if reuse_id else str(uuid.uuid4())
    book_dir = os.path.join(UPLOAD_DIR, task_id)
    os.makedirs(book_dir, exist_ok=True)
    
    if file and file.filename:
        # Se um novo arquivo for enviado, salvamos
        pdf_path = os.path.join(book_dir, file.filename)
        with open(pdf_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        filename = file.filename
    else:
        # Tentar localizar o PDF já existente no diretório (Modo Refatoração)
        existing_files = [f for f in os.listdir(book_dir) if f.lower().endswith(('.pdf', '.epub'))]
        if not existing_files:
            return JSONResponse({"error": "Nenhum arquivo enviado ou existente no servidor."}, status_code=400)
        filename = existing_files[0]
        pdf_path = os.path.join(book_dir, filename)
    
    cover_path = None
    if cover and cover.filename:
        cover_path = os.path.join(book_dir, "custom_cover.jpg")
        with open(cover_path, "wb") as buffer:
            shutil.copyfileobj(cover.file, buffer)
    
    options = {
        "filename": filename, 
        "voice": voice,
        "title": title,
        "author": author,
        "observations": observations,
        "cover_path": cover_path,
        "auto_continue": auto_continue,
        "upload_youtube": upload_youtube
    }
    task = process_pdf_task.apply_async(args=[pdf_path, options], task_id=task_id)
    
    return {"task_id": task.id, "status": "PENDING"}

@app.get("/api/status/{task_id}")
async def get_status(task_id: str):
    task_result = AsyncResult(task_id)
    
    # Se a task principal acabou, verificar se ela deixou um estado especial no state.txt
    output_dir = os.path.join(OUTPUT_DIR, task_id)
    state_file = os.path.join(output_dir, "state.txt")
    
    status = task_result.status
    message = ""
    
    state_data = {}
    if os.path.exists(state_file):
        with open(state_file, 'r') as f:
            lines = f.readlines()
            if lines and lines[0].strip() == "SAMPLE_READY" and status == "SUCCESS":
                status = "SAMPLE_READY"
            for line in lines:
                if "=" in line:
                    k, v = line.split("=", 1)
                    state_data[k.strip()] = v.strip()
    
    if task_result.status == 'PROGRESS':
        message = task_result.info.get('message', '')
    elif status == 'SAMPLE_READY':
        message = "Amostra de 5 minutos pronta!"
    elif task_result.status == 'SUCCESS':
        message = "Processamento concluído!"
    elif task_result.status == 'FAILURE':
        message = str(task_result.info)
        
    return JSONResponse({
        "status": status,
        "message": message,
        "sample_url": f"/outputs/{task_id}/video_sample.mp4" if status == "SAMPLE_READY" else None,
        "sample_audio_url": f"/outputs/{task_id}/{state_data.get('sample_audio')}" if state_data.get('sample_audio') else None,
        "total_chunks": state_data.get('total_chunks')
    })

@app.get("/api/download_pack/{task_id}")
async def download_pack(task_id: str):
    zip_path = os.path.join(OUTPUT_DIR, f"{task_id}_pack.zip")
    
    if not os.path.exists(zip_path):
        return JSONResponse({"error": "Arquivo ainda não gerado ou expirado."}, status_code=404)
        
    return FileResponse(zip_path, media_type='application/zip', filename=f"livro_narrado_{task_id}.zip")

@app.get("/api/download_audio_zip/{task_id}")
async def download_audio_zip(task_id: str):
    output_dir = os.path.join(OUTPUT_DIR, task_id)
    zip_path = os.path.join(OUTPUT_DIR, f"{task_id}_audio.zip")
    
    if not os.path.exists(output_dir):
        return JSONResponse({"error": "Pasta não encontrada."}, status_code=404)
    
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for filename in os.listdir(output_dir):
            if filename.endswith('.mp3'):
                zipf.write(os.path.join(output_dir, filename), arcname=filename)
    
    return FileResponse(zip_path, media_type='application/zip', filename=f"audio_{task_id}.zip")

@app.get("/api/download_video_zip/{task_id}")
async def download_video_zip(task_id: str):
    output_dir = os.path.join(OUTPUT_DIR, task_id)
    zip_path = os.path.join(OUTPUT_DIR, f"{task_id}_video.zip")
    
    if not os.path.exists(output_dir):
        return JSONResponse({"error": "Pasta não encontrada."}, status_code=404)
    
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for filename in os.listdir(output_dir):
            if filename.endswith('.mp4') or filename.endswith('.mp3'):
                zipf.write(os.path.join(output_dir, filename), arcname=filename)
    
    return FileResponse(zip_path, media_type='application/zip', filename=f"video_{task_id}.zip")

@app.post("/api/continue_process")
async def continue_process(request: Request):
    data = await request.json()
    task_id = data.get("task_id")
    if not task_id:
        return JSONResponse({"success": False, "error": "ID ausente"}, status_code=400)
    
    from worker.tasks import continue_full_process_task
    task = continue_full_process_task.apply_async(args=[task_id], task_id=f"full_{task_id}")
    return {"success": True, "task_id": task.id}

@app.post("/api/refactor_process")
async def refactor_process(request: Request):
    data = await request.json()
    task_id = data.get("task_id")
    if not task_id:
        return JSONResponse({"success": False, "error": "ID ausente"}, status_code=400)
    
    # Limpa apenas os outputs do ID específico, mantém o upload
    output_path = os.path.join(OUTPUT_DIR, task_id)
    if os.path.exists(output_path):
        shutil.rmtree(output_path)
    
    return {"success": True}

@app.get("/api/youtube_status")
async def youtube_status():
    has_secret = os.path.exists(CLIENT_SECRETS_FILE)
    is_authenticated = os.path.exists(TOKEN_FILE)
    return JSONResponse({"has_secret": has_secret, "is_authenticated": is_authenticated})

@app.get("/auth/youtube")
async def auth_youtube(request: Request):
    if not os.path.exists(CLIENT_SECRETS_FILE):
        return JSONResponse({"error": "Coloque o arquivo client_secret.json na pasta data primeiro."}, status_code=400)
    
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=YOUTUBE_SCOPES,
        redirect_uri=request.base_url._url.rstrip('/') + "/oauth2callback"
    )
    
    auth_url, _ = flow.authorization_url(prompt='consent')
    oauth_flow_session['flow'] = flow
    
    from fastapi.responses import RedirectResponse
    return RedirectResponse(auth_url)

@app.get("/oauth2callback")
async def oauth2callback(request: Request):
    flow = oauth_flow_session.get('flow')
    
    if not flow:
        return JSONResponse({"error": "Sessão de fluxo expirada. Recomece."}, status_code=400)
    
    flow.fetch_token(authorization_response=str(request.url))
    credentials = flow.credentials
    
    oauth_flow_session.clear()
    
    with open(TOKEN_FILE, 'w') as token_file:
        token_data = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        }
        json.dump(token_data, token_file)
        
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/?youtube=success")

@app.post("/api/upload_existing_video")
async def upload_existing_video(
    video: UploadFile = File(...),
    title: str = Form(...),
    description: str = Form("")
):
    from worker.pipeline_video.youtube_uploader import upload_video_to_youtube
    
    task_id = str(uuid.uuid4())
    work_dir = os.path.join(OUTPUT_DIR, task_id)
    os.makedirs(work_dir, exist_ok=True)
    
    video_path = os.path.join(work_dir, "video.mp4")
    with open(video_path, "wb") as buffer:
        shutil.copyfileobj(video.file, buffer)
    
    video_id = upload_video_to_youtube(video_path, title, description)
    
    if video_id:
        return JSONResponse({"success": True, "video_id": video_id})
    else:
        return JSONResponse({"success": False, "error": "Falha no upload para o YouTube"}, status_code=500)

@app.post("/api/cleanup_all")
async def cleanup_all():
    try:
        # Limpar Outputs
        if os.path.exists(OUTPUT_DIR):
            for filename in os.listdir(OUTPUT_DIR):
                file_path = os.path.join(OUTPUT_DIR, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                except Exception as e:
                    print(f"Erro ao deletar output {file_path}: {e}")
        
        # Limpar Uploads
        if os.path.exists(UPLOAD_DIR):
            for filename in os.listdir(UPLOAD_DIR):
                file_path = os.path.join(UPLOAD_DIR, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                except Exception as e:
                    print(f"Erro ao deletar upload {file_path}: {e}")
                    
        return JSONResponse({"success": True})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)