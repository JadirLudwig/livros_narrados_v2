# Projeto: PDF → Audiolivro + Vídeo YouTube/Spotify
**Data de criação:** 2026-03-26  
**Última atualização:** 2026-03-28  
**Status:** 📋 Planejamento Web App

---

## 🎯 Objetivo

Criar uma aplicação Web (Site rodando localmente) em Python + Docker que receba PDFs, processe-os em background e entregue todos os arquivos necessários para publicação em duas frentes:
1. **Pacote Genérico/Spotify** — Áudio MP3 completo do livro em um único arquivo de alta qualidade, arte de capa em proporção 1:1 e arquivo `spotify_metadata.txt`.
2. **Pacote YouTube** — Vídeo MP4 em 1080p, arte de miniatura customizada e arquivo `youtube_metadata.txt` com as marcações de tempo necessárias e tags SEO.

---

## 🏗️ Arquitetura Geral (Web App)

```
                     [Navegador Local]
                     Upload do PDF
                           │
                 [FastAPI (Web Server)]
            Recebe o arquivo e insere tarefa na
            Fila (Celery) → Responde status "Processando"
                           │
      ┌────────────────────┴────────────────────┐
      ▼                                         ▼
 [Redis] (Message Broker)                [Volumes Docker]
      │                                    (Armazenamento)
      ▼
 [Celery Worker] (Processamento Assíncrono)
      │
      ├─► 1. EXTRAÇÃO: pdfplumber → Extrai texto e Capa (1ª página)
      ├─► 2. LIMPEZA: Remove lixo, detecta capítulos
      ├─► 3. NARRADOR: Ajusta metadados textuais para locução fluida
      ├─► 4. SÍNTESE (TTS): edge-tts → Áudio Base + Legendas VTT
      │
      ├─► 5a. PACOTE SPOTIFY
      │     └─► pydub embute tudo num MP3 único e completo (-16 LUFS)
      │     └─► Imagem 1:1 tirada diretamente da capa original extraída
      │     └─► `spotify_metadata.txt` (Notas do show)
      │
      ├─► 5b. PACOTE YOUTUBE
      │     └─► ffmpeg cruza áudio e frame do Modo A ou Modo B resultando em MP4
      │     └─► Thumbnail 16:9 gerada em background
      │     └─► `youtube_metadata.txt` com capítulos para marcação nativa de timeline
      │
      └─► UI Notifica Status "CONCLUÍDO" para ZIP download respectivo
```

---

## 📁 Estrutura de Pastas do Projeto Expandida

```text
Projeto_Livros_Narrados/
│
├── audiolivro-pdf-plano.md       ← (Este Arquivo)
├── implementation_plan.md        ← Passos de implementação práticos
├── Memorial                      ← Histórico e log de mudanças
├── README.md                     ← Explicação geral
│
├── docker-compose.yml            ← Orquestração
├── Dockerfile                    ← Imagem do worker e do servidor web
├── requirements.txt              ← Dependências (FastAPI, Celery, FFmpeg etc.)
│
├── web/                          ← Frontend e servidor assíncrono
│   ├── main.py                   ← Rotas com FastAPI
│   ├── templates/                ← HTML Simples + Vanilla CSS minimalista/Dark
│   └── static/                   ← Assets Vanilla JS
│
├── worker/                       ← Fila processual distribuída
│   ├── celery_app.py             ← Bootstrap do Worker
│   ├── tasks.py                  ← Entradas principais das tarefas longas
│   ├── pipeline_audio/           ← Extração e Montagem (.MP3)
│   └── pipeline_video/           ← Montagem de Vídeo (.MP4)
│
├── config/                       ← .yaml globais (estilos de texto e tuning de TTS)
├── assets/                       ← Fontes de texto, backgrounds limpos de uso geral
└── data/                         ← Volumes ignorados por versionamento
    ├── uploads/                  ← Onde os PDFs do frontend param
    └── outputs/                  ← Pastas dos resultados dos Jobs e pacotes ZIP
```

---

## 🧩 Modificações Chaves e Módulos

### Extração de Capa Direta da Ferramenta (`pipeline_audio/extractor.py`)
- O extrator continua tirando todas as strings por folha, porém **obrigatoriamente tira um "snapshot" em alta qualidade da página 1 do PDF**. Essa será nossa premissa estática de Capa Artística para Spotify e Base da Miniatura pro YouTube, dado que ela é frequentemente a folha correta de capa.

### O Áudio (`pipeline_audio/audio_processor.py`)
- Na versão simplificada, gerávamos áudios por capítulos individualmente. O **requisito estrito agora é o empacotamento em um único MP3 completo**, montado com transições suaves (1500ms fade-out/fade-in nas divisas dos capítulos) de todo o conteúdo.

### Tratamento e Montagem `(Modo Vídeo)` (`pipeline_video/video_composer.py`)
- A depender da flag enviada pela Interface de uso local (Modo A para Imagens Escaneadas mescladas; Modo B para Tela Fixa Clássica + Scrolling de legenda visível), finaliza o MP4 compatível perfeitamente com 1080p, sem restrições ou quebras bruscas. 

---

## 🚀 Módulo Independente A: Automação Spotify 
> Upload de conteúdo via plataforma estrita de podcasting, a serem tratadas inteiramente à parte.

Como não existe rota universal unificada para contas simples do **Spotify for Podcasters**, o site hospedará nativamente uma rota permanente como `/feed/podcast.xml` debaixo da estrutura do FastAPI.
- A aplicação se comporta como um pequeno Servidor RSS.
- Toda conversão insere um bloco `<item>` no RSS, linkando o URL direto para baixar o arquivo completo MP3 armazenado de forma estática em nossos volumes. 
- Assim, enviamos só nosso link único RSS ao Spotify que fará pull semanal absorvendo cada obra sem exigir trabalho extra do administrador.

## 📺 Módulo Independente B: Automação YouTube
> Exige chaves credenciadas e complexidades sensíveis, tratando-se exclusivamente num subsistema de push.

Para enviar o "Pacote YouTube" direto da plataforma sem intervenção humana:
- Desenvolveremos uma aba na "Interface Local" de "Sincronização Integrada" baseada na biblioteca `google-api-python-client`.
- Pede credencial OAuth2 na máquina do usuário uma única vez, salvando o `.pickle` de token.
- Um Job Celery dispara as chamadas via POST do arquivo MP4, do arquivo .JPG de Thumbnail gerado no worker, e faz leitura atenta do arquivo estruturado (txt) preenchendo as caixas de Título, Descrição do Youtube (as Tags temporais ficam em texto lá em formato de marcações HH:MM:SS ativando nativamente os Capítulos Youtube) permitindo envio silencioso para o canal de destino.
