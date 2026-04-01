# 📚 Plano de Implementação — Livros Narrados Web
> Site Local: PDF/EPUB → Extração Background → MP3 Único + YouTube e Spotify Integrados

**Projeto:** `/home/ubu/.antigravity/Projetos/Projeto_Livros_Narrados/`  
**Status atual:** 🏗️ Execução  
**Última atualização:** 2026-03-29

---

## ⚙️ Setup Infraestrutura (Fase 1)

> Execute a fase inicial de montagem da plataforma via **Docker Compose**, focando no isolamento das bibliotecas pesadas de Mídia num serviço unificado. 

### 1.1 — `Dockerfile`
Imagem central capaz de rodar as requisições normais no FastAPI e o Worker em Background do Celery. Extrema importância de injetar os módulos base do GNU/Linux antes dos pacotes em pip:
```dockerfile
# Exemplo ilustrativo de build
FROM python:3.11-slim
RUN apt-get update && apt-get install -y ffmpeg libass-dev fontconfig curl
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
```

### 1.2 — `docker-compose.yml`
Construir ambiente orquestrado focado em rede cruzada.
```yaml
version: '3.8'
services:
  web:
    build: .
    command: uvicorn web.main:app --host 0.0.0.0 --port 8000
    volumes:
      - ./data:/app/data
    ports:
      - "8000:8000"
    depends_on:
      - redis

  worker:
    build: .
    command: celery -A worker.celery_app worker --loglevel=info
    volumes:
      - ./data:/app/data
    depends_on:
      - redis

  redis:
    image: redis:alpine
    ports:
      - "6379:6379"
```

### 1.3 — Requirements Base 
No arquivo `requirements.txt`:
```txt
# Web/Interface e Fila
fastapi>=0.100.0
uvicorn>=0.23.0
celery>=5.3.0
redis>=4.6.0
python-multipart>=0.0.6
jinja2>=3.1.2

# Motor Tradicional de Módulo de Extrações e Sintéticos
pdfplumber>=0.10.0
PyMuPDF>=1.23.0
EbookLib>=0.18
html2text
edge-tts>=6.1.9
webvtt-py>=0.4.6
pydub>=0.25.1
mutagen>=1.47.0
Pillow>=10.0.0
num2words>=0.5.13
rich>=13.0.0
```

---

## 🟢 FASE 2: Interface Local e Servidor Web
> **Meta:** Ter o site operacional em `http://localhost:8000` capaz de receber um PDF do usuário.

### Passo 2.1 — O Servidor (FastAPI na pasta `/web/`)
Criar o servidor web e preparar as rotas centrais:
1. `GET /`: Devolve `index.html` (Nossa página web para uso doméstico).
2. `POST /api/process_book`: Recebe o payload com as configurações (ex: MP3 Apenas, ou Gerar Vídeos também) e o `.pdf`. Salva num volume assinado com Unique ID. Dispara `.delay()` no task do Celery para entrar na fila. Retorna um Json: `{"task_id": "X", "status": "Em processamento"}`.
3. `GET /api/status/{task_id}`: Verifica onde o worker está na barra de progresso.
4. `GET /api/download_pack/{task_id}`: Permite puxar, já encapado, o ZIP montado. 

### Passo 2.2 — Frontend Moderno e Ágil
- HTML e CSS puros instalados em `/web/templates/`.
- Uso de tema obscuro guiado pelas regras de design "Premium/Misterioso", agradável ao uso focado.
- Sem page breaks ou loading massivos - uma View Single Page que muda a UI usando Javascript comunicando em JSON a "barra" preenchendo as etapas vindas do Backend `api/status`.

---

## 🟡 FASE 3: Background Worker Áudio (MP3 Único)
> **Meta:** Assim que a Task entra em estado processando no servidor Redis, iniciar lógicas extensas.

| Responsabilidade | O que faz no Worker Celery |
|---------|-----------------|
| `extractor.py` | Salva o payload texto de página a página. E o crucial: Retém a primeira folha isolada como frame base, salvando como `capa_base.jpg`. |
| `cleaner.py` e `narrator.py` | Expurga traços inuteis; Aplica Regex corrigindo SSML, números complexos expandidos e formata os "Títulos de Capítulos" achados com Regex num array base temporal. |
| `tts_engine.py` | Fragmenta conteúdo e submete ao edge-tts, garantindo o `.vtt` com legenda e os mp3 soltos das faixas lidas. |
| `audio_processor.py` | Consolida. Em vez da quebra estrita de arquivos na regra do projeto antigo, o novo projeto une todos os áudios via `pydub`. Efetua os picos dinâmicos na normalização de `-16 LUFS` montando a renderização absoluta e limpa guardada como: `audio_completo_master.mp3`. |

---

## 🔵 FASE 4: Criação dos Entregáveis (Pacotes) 
> **Meta:** Estruturar visualmente metadados textuais e visuais, antes de compactar em ZIP.

- **Pacote Spotify:**
  1. Utilizando a imagem `capa_base.jpg`, redimensiona internamente e injeta bordas via `Pillow`, salvando um quadrado estrito 1:1 de `cover.jpg`.
  2. Adiciona os metadados ID3 nativos ao arquivo `audio_completo_master.mp3`.
  3. Gera um log impresso legível: `spotify_metadata.txt` apontando sinopse do livro, descrição de capa. Copia tudo para `/outputs/{uuid}/spotify_pack`.

- **Pacote YouTube:**
  1. Invoca os Módulos Visuais Modos A ou B (que já existem e continuam ativos baseados em frames fixos do arquivo texto e ffmpeg). Note que o FFmpeg fará um `.mp4` do conteúdo global referenciando o mesmo áudio masterizado sem ser fatiado.
  2. Thumbnail montada pela subrotina gerando `thumb_16_9.jpg`.
  3. Preenchimento sintático gerado via Backend salvando um `youtube_metadata.txt` que lista todo o array capturado de Capítulos no Módulo de Extração transformados em strings como `00:00 - Introdução` | `10:14 - Capítulo Um` | etc para fins de descrição e player interativo daquele sistema.
  4. Agrega tudo em `/outputs/{uuid}/youtube_pack`. Zipa tudo em background e define barra de progresso do Celery em `100%`.

---

## 🟣 FASES 5 e 6: Automações Extras Isoladas
> Onde inserimos as partes vitais em módulos desconectados base para manter código enxuto da master task.

***Fase 5 - Módulo Spotify através de um Podcast RSS Host:***
- Adicionar no FastAPI a rota raiz `/feed.xml`.
- Arquitetura de inserção base de dados via JSON simples onde os URLs dos áudios publicos que estiverem dentro do diretório estático público geram um formato XML dinâmico (com enclosure link MP3, Image URL padrão cover 1:1, itunes:duration baseado em bytes etc).
- Spotify será avisado desse URL e puxará sempre que formos adicionar um novo arquivo gerado ao XML manual ou automático.

***Fase 6 - Módulo Youtube Google Client Push:***
- Estrutura à parte usando `google-api-python-client`.
- Rotina python via CLI com OAuth2 Flow nativo, autenticando ao menos primariamente o arquivo `/client_secret.json`. 
- Ao obter o refresh Token válido, ele engole do diretório interno os outputs de upload: Manda vídeo via upload bytes Resumable, anexa descrição capturada dos scripts de metadado na task principal, anexa tags e por fim insere thumbnail API request para fechar a veiculação do site inteiro sem navegador logado real.
