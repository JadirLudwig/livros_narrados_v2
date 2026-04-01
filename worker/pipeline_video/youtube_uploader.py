import os
import google.oauth2.credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Escopo necessário para anexar vídeos diretos ao canal da conta
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

def upload_video_to_youtube(video_path: str, title: str, description_text: str, tags: list = None, privacy_status: str = "private"):
    """
    Submete um arquivo .mp4 cru para o YouTube usando MediaFileUpload (permite resuming e grandes tamanhos).
    Utiliza as credenciais globais guardadas em '/app/data/youtube_token.json'.
    Se não encontrar, abortará com log detalhado e retornará None.
    """
    token_path = "/app/data/youtube_token.json"
    
    if not os.path.exists(token_path):
        print("Upload para o YouTube falhou: Arquivo de credenciais (Token JSON) não foi encontrado no volume persistente.")
        return None
        
    if not tags:
        tags = ["audiolivro", "audiobook", "livro completo", "literatura", "narração", "livro em áudio"]
        
    # Limpar e truncar descrição para respeitar os limites do YouTube (5000 caracteres)
    description_text = description_text.replace('<', '').replace('>', '')
    if len(description_text) > 4800:
        description_text = description_text[:4800] + "\n...[Descrição truncada pelo limite do YouTube]"
        
    try:
        # Carregando a chave mágica salva na rotina de Auth
        creds = google.oauth2.credentials.Credentials.from_authorized_user_file(token_path, SCOPES)
        youtube = build('youtube', 'v3', credentials=creds)
        
        # Meta Dados do Vídeo YouTube 
        body = {
            'snippet': {
                'title': title,
                'description': description_text,
                'tags': tags,
                'categoryId': '27' # Categoria 27: Educação / Literatura
            },
            'status': {
                'privacyStatus': privacy_status,
                'selfDeclaredMadeForKids': False
            }
        }
        
        # O Uploader trabalha em blocos para evitar falha de memória RAM
        media = MediaFileUpload(
            video_path,
            chunksize=-1, # Envio auto-gerido do TCP
            resumable=True
        )
        
        print(f"[{title}] - Disparando injeção via YouTube API...")
        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )
        
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"Progresso de Upload YouTube: {int(status.progress() * 100)}%")
                
        video_id = response.get("id")
        print(f"✅ Upload do Livro concluído! ID gerado no YouTube: {video_id}")
        return video_id
        
    except Exception as e:
        print(f"Erro fatídico de upload: {e}")
        return None
