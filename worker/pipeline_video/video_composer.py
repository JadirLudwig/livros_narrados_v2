import subprocess
import os

def compose_video(image_path: str, audio_path: str, output_path: str):
    """
    Cria um vídeo MP4 de alta qualidade usando uma imagem estática (capa) 
    e o áudio do livro. Redimensiona para 1080p.
    """
    if not os.path.exists(image_path) or not os.path.exists(audio_path):
        print(f"Erro: Arquivos de entrada não encontrados para vídeo ({image_path}, {audio_path})")
        return None

    # Comando FFmpeg otimizado (Reduzido para 720p para uploads mais velozes):
    # 1. -loop 1: Repetir a imagem
    # 2. -shortest: Parar quando o áudio acabar
    # 3. scale e pad: Centra a capa num fundo preto de 1280x720
    command = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", image_path,
        "-i", audio_path,
        "-c:v", "libx264", "-tune", "stillimage",
        "-b:v", "1000k",
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2",
        "-shortest",
        output_path
    ]

    try:
        # Executar comando (pode demorar alguns minutos dependendo do tamanho do livro)
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return output_path
    except subprocess.CalledProcessError as e:
        print(f"Erro ao gerar vídeo com FFmpeg: {e.stderr.decode()}")
        return None
