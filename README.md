# 📚 Livros Narrados — Plataforma de Narração de Audiolivros

> Transforme PDF/EPUB em audiolivros narrados com síntese de voz Edge-TTS

**Imagem Docker Hub:** `ludwig91/livros_narrados_v2`  
**Versão:** V2.0  
**Status:** ✅ Produção  
**Última atualização:** 2026-04-01

---

## ✨ Novidades V2.0

- **Upload de capa personalizada** - Envie sua própria imagem de capa
- **Campo de Observações** - Narração personalizada após o autor
- **Upload de áudio/video existente** - Gere vídeo a partir de MP3 ou faça upload de MP4 para YouTube
- **Divisão de áudio longo** - Áudios >60min com capítulo único são automaticamente dividos
- **Mais vozes masculinas** - Novas opções de voz adicionadas

---

## 🚀 Como Executar

### Opção 1: Docker Compose (Recomendado)

Baixe o arquivo `docker-compose.yml` e execute:

```bash
docker-compose up --build
```

Acesse: `http://localhost:8088`

### Opção 2: Docker Run Standalone

**Servidor Web:**
```bash
docker run -d -p 8000:8000 ludwig91/livros_narrados_v2 web
```

**Worker (necessário Redis separado):**
```bash
docker run -d -e CELERY_BROKER_URL=redis://host:6379/0 ludwig91/livros_narrados_v2 worker
```

### Opção 3: Docker Run com Redis Integrado

```bash
# Iniciar Redis
docker run -d --name redis redis:alpine

# Iniciar Web
docker run -d -p 8000:8000 --link redis -e CELERY_BROKER_URL=redis://redis:6379/0 ludwig91/livros_narrados_v2 web

# Iniciar Worker
docker run -d --link redis -e CELERY_BROKER_URL=redis://redis:6379/0 ludwig91/livros_narrados_v2 worker
```

---

## 📋 Serviços Disponíveis

| Serviço | Descrição | Porta |
|---------|-----------|-------|
| `web` | Servidor FastAPI (Web UI) | 8000 |
| `worker` | Celery Worker (Processamento) | - |
| `redis` | Message Broker | 6379 |

---

## 🔧 Variáveis de Ambiente

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `CELERY_BROKER_URL` | `redis://redis:6379/0` | URL do Redis |
| `CELERY_RESULT_BACKEND` | `redis://redis:6379/0` | Backend de resultados |

---

## 📦 Entregáveis Gerados

- **MP3 Masterizado** — Áudio único com normalização e efeitos
- **Pacote Spotify** — Capa, metadados ID3, descrição
- **Pacote YouTube** — Vídeo HD, thumbnail, metadata com timestamps
- **Feed RSS** — Podcast feed XML

---

## 🛠️ Desenvolvimento Local

```bash
# Clone o projeto
git clone <repo-url>
cd Projeto_Livros_Narrados

# Execute
docker-compose up --build

# Logs
docker-compose logs -f
```

---

## 📄 Arquitetura

```
├── web/              # FastAPI + Frontend
├── worker/           # Celery Tasks
├── data/             # Volumes de dados
├── docker-compose.yml
├── Dockerfile
├── entrypoint.sh
└── requirements.txt
```

---

## ⚙️ Requisitos do Sistema

- Docker
- Docker Compose
- 4GB+ RAM recomendado
- Conexão com internet (Edge-TTS)
