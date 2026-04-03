# 📚 Livros Narrados fastGPU — Plataforma de Alta Performance com IA Local

> Transforme PDF/EPUB em audiolivros usando a potência da sua GPU (NVIDIA CUDA)

**Imagem Docker Hub:** `ludwig91/livros_narrados_fastgpu`  
**Versão:** fastGPU (CUDA)
**Status:** ✅ Produção / Aceleração por Hardware
**Última atualização:** 2026-04-03

---

- **Aceleração por GPU (CUDA)** - Processamento 10x mais rápido usando NVIDIA GTX/RTX
- **Vozes Locais (Kokoro-82M)** - Sem dependência de internet ou limites de API
- **Codificação de Vídeo NVENC** - Geração de vídeos para YouTube em segundos
- **Processamento por tempo** - Áudio dividido em trechos de 5 minutos
- **Interface redesign** - Design moderno com gradientes e tipografia atualizada
- **Checkbox prosseguir automaticamente** - Execute todo o fluxo sem confirmações
- **Capa no início** - Campo para enviar capa no formulário inicial

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
docker run -d -p 8000:8000 ludwig91/livros_narrados_v3 web
```

**Worker (necessário Redis separado):**
```bash
docker run -d -e CELERY_BROKER_URL=redis://host:6379/0 ludwig91/livros_narrados_v3 worker
```

### Opção 3: Pull da imagem pronta

```bash
docker pull ludwig91/livros_narrados_v3
docker run -d -p 8088:8088 ludwig91/livros_narrados_v3
```

---

## 📋 Fluxo de Processamento

```
1. PDF/EPUB → Áudio (trechos de 5 min, lotes de 5)
            ↓
2. Confirmação: "Prosseguir para Vídeo?"
   - SIM: Transforma áudio em vídeo
   - NÃO: Baixar ZIP do áudio
            ↓
3. Vídeo pronto → Confirmação: "Enviar para YouTube?"
   - SIM: Upload automático
   - NÃO: Baixar ZIP do vídeo
            ↓
4. Pacote Final (ZIP)
```

---

## 📋 Campos do Formulário

| Campo | Descrição |
|-------|-----------|
| Arquivo (PDF/EPUB) | Livro a narrar |
| Título do Livro | Título do livro |
| Autor | Autor do livro |
| Observações | Notas adicionais |
| Capa | Imagem para o vídeo/YouTube |
| Voz de Narração | 4 opções (2 femininas, 2 masculinas) |
| Prosseguir Automaticamente | Pula confirmações |

---

## 📋 Serviços Disponíveis

| Serviço | Descrição | Porta |
|---------|-----------|-------|
| `web` | Servidor FastAPI (Web UI) | 8088 |
| `worker` | Celery Worker (Processamento) | - |
| `redis` | Message Broker | 6388 |

---

## 🔧 Variáveis de Ambiente

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `CELERY_BROKER_URL` | `redis://redis:6388/0` | URL do Redis |
| `CELERY_RESULT_BACKEND` | `redis://redis:6388/0` | Backend de resultados |

---

## 📦 Entregáveis

- **Áudio ZIP** - Todos os áudios de 5 minutos
- **Vídeo MP4** - Vídeo unico com áudio + capa
- **Pacote Final** - MP3, Vídeo, Metadata YouTube
- **Upload YouTube** - Opcional automático

---

## 🛠️ Desenvolvimento Local

```bash
# Clone o projeto
git clone https://github.com/JadirLudwig/livros_narrados_v3.git
cd livros_narrados_v3

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
│   ├── pipeline_audio/   # Extração, Limpeza, TTS
│   └── pipeline_video/   # Composição, YouTube
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