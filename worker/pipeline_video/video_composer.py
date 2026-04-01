import subprocess
import os

def compose_video(image_path: str | None, audio_path: str, output_path: str):
    """
    Cria um vídeo MP4 de alta qualidade usando uma imagem estática (capa) 
    e o áudio do livro. Redimensiona para 720p.
    Se image_path for None, cria uma capa padrão com texto.
    """
    if not os.path.exists(audio_path):
        print(f"Erro: Arquivo de áudio não encontrado: {audio_path}")
        return None
    
    final_image_path = image_path
    
    if not image_path or not os.path.exists(image_path):
        print("Capa não encontrada, criando capa padrão...")
        final_image_path = os.path.join(os.path.dirname(output_path), "temp_cover.jpg")
        
        result = subprocess.run([
            "convert", "-size", "1280x720", "gradient:#1a1a2e-#16213e",
            "-fill", "white", "-pointsize", "48", "-gravity", "center",
            "-annotate", "+0+0", "Livros Narrados V3",
            final_image_path
        ], capture_output=True)
        
        if result.returncode != 0:
            subprocess.run([
                "convert", "-size", "1280x720", "xc:black",
                "-fill", "white", "-pointsize", "48", "-gravity", "center",
                "-annotate", "+0+0", "Livros Narrados",
                final_image_path
            ], check=True)
    
    command = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", final_image_path,
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
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        if final_image_path != image_path and os.path.exists(final_image_path):
            try:
                os.remove(final_image_path)
            except:
                pass
        
        return output_path
    except subprocess.CalledProcessError as e:
        print(f"Erro ao gerar vídeo com FFmpeg: {e.stderr.decode()}")
        return None