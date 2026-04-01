from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request
from celery.result import AsyncResult
from worker.tasks import process_pdf_task
from fastapi.staticfiles import StaticFiles
import os
import uuid
import shutil
import json
import subprocess

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

try:
    from google_auth_oauthlib.flow import Flow
except ImportError:
    pass

YOUTUBE_SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
CLIENT_SECRETS_FILE = "/app/data/client_secret.json"
TOKEN_FILE = "/app/data/youtube_token.json"

oauth_flow_session = {}

app = FastAPI(title="Livros Narrados V2")
templates = Jinja2Templates(directory="web/templates")

if not os.path.exists("web/static"):
    os.makedirs("web/static")
app.mount("/static", StaticFiles(directory="web/static"), name="static")

UPLOAD_DIR = "/app/data/uploads"
OUTPUT_DIR = "/app/data/outputs"

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
    file: UploadFile = File(...),
    gen_video: bool = Form(True),
    voice: str = Form("pt-BR-FranciscaNeural"),
    title: str = Form(""),
    author: str = Form(""),
    observations: str = Form(""),
    cover: UploadFile = File(None),
    upload_youtube: bool = Form(False)
):
    cleanup_old_data()
    task_id = str(uuid.uuid4())
    book_dir = os.path.join(UPLOAD_DIR, task_id)
    os.makedirs(book_dir, exist_ok=True)
    
    pdf_path = os.path.join(book_dir, file.filename)
    with open(pdf_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    cover_path = None
    if cover and cover.filename:
        cover_path = os.path.join(book_dir, "custom_cover.jpg")
        with open(cover_path, "wb") as buffer:
            shutil.copyfileobj(cover.file, buffer)
    
    options = {
        "gen_video": gen_video, 
        "filename": file.filename, 
        "voice": voice,
        "title": title,
        "author": author,
        "observations": observations,
        "cover_path": cover_path,
        "upload_youtube": upload_youtube
    }
    task = process_pdf_task.apply_async(args=[pdf_path, options], task_id=task_id)
    
    return {"task_id": task.id, "status": "PENDING"}

@app.get("/api/status/{task_id}")
async def get_status(task_id: str):
    task_result = AsyncResult(task_id)
    
    result = {
        "status": task_result.status,
        "message": ""
    }
    
    if task_result.status == 'PROGRESS':
        result["message"] = task_result.info.get('message', '')
    elif task_result.status == 'SUCCESS':
        result["message"] = "Tudo pronto!"
    elif task_result.status == 'FAILURE':
        result["message"] = str(task_result.info)
        
    return JSONResponse(result)

@app.get("/api/download_pack/{task_id}")
async def download_pack(task_id: str):
    zip_path = os.path.join(OUTPUT_DIR, f"{task_id}_pack.zip")
    
    if not os.path.exists(zip_path):
        return JSONResponse({"error": "Arquivo ainda não gerado ou expirado."}, status_code=404)
        
    return FileResponse(zip_path, media_type='application/zip', filename=f"livro_narrado_{task_id}.zip")

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

@app.post("/api/process_audio_only")
async def process_audio_only(
    audio: UploadFile = File(...),
    title: str = Form(...),
    cover: UploadFile = File(None)
):
    task_id = str(uuid.uuid4())
    work_dir = os.path.join(OUTPUT_DIR, task_id)
    os.makedirs(work_dir, exist_ok=True)
    
    audio_path = os.path.join(work_dir, "audio.mp3")
    with open(audio_path, "wb") as buffer:
        shutil.copyfileobj(audio.file, buffer)
    
    cover_path = None
    if cover and cover.filename:
        cover_path = os.path.join(work_dir, "cover.jpg")
        with open(cover_path, "wb") as buffer:
            shutil.copyfileobj(cover.file, buffer)
    
    if not cover_path:
        cover_path = os.path.join(work_dir, "default_cover.jpg")
        subprocess.run([
            "convert", "-size", "1280x720", "xc:black", "-fill", "white",
            "-pointsize", "72", "-gravity", "center",
            "-annotate", "+0+0", "Livros Narrados", cover_path
        ], check=True)
    
    video_path = os.path.join(work_dir, "video_output.mp4")
    
    command = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", cover_path,
        "-i", audio_path,
        "-c:v", "libx264", "-tune", "stillimage",
        "-b:v", "1000k",
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2",
        "-shortest",
        video_path
    ]
    
    try:
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return JSONResponse({
            "success": True,
            "video_path": video_path,
            "download_url": f"/api/download_video/{task_id}"
        })
    except subprocess.CalledProcessError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.get("/api/download_video/{task_id}")
async def download_video(task_id: str):
    video_path = os.path.join(OUTPUT_DIR, task_id, "video_output.mp4")
    
    if not os.path.exists(video_path):
        return JSONResponse({"error": "Vídeo não encontrado."}, status_code=404)
        
    return FileResponse(video_path, media_type='video/mp4', filename=f"video_{task_id}.mp4")

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

@app.post("/api/cleanup_outputs")
async def cleanup_outputs():
    try:
        if os.path.exists(OUTPUT_DIR):
            for filename in os.listdir(OUTPUT_DIR):
                file_path = os.path.join(OUTPUT_DIR, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                except Exception as e:
                    print(f"Erro ao deletar {file_path}: {e}")
        return JSONResponse({"success": True})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)
