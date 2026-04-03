FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04

# Evitar prompts durante a instalação
ENV DEBIAN_FRONTEND=noninteractive

# Instalar Python 3.11 e dependências do sistema
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3-pip \
    python3.11-dev \
    ffmpeg \
    libass-dev \
    fontconfig \
    curl \
    libsndfile1 \
    libasound2 \
    espeak-ng \
    imagemagick \
    && rm -rf /var/lib/apt/lists/*

# Definir Python 3.11 como o padrão
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 \
    && update-alternatives --set python3 /usr/bin/python3.11

# Garantir que o pip esteja atualizado
RUN python3 -m pip install --upgrade pip setuptools wheel

WORKDIR /app

# Instalação UNIFICADA para garantir resolução de dependências correta
# Instalamos Torch GPU e as libs de IA pesadas em um único comando
RUN python3 -m pip install --no-cache-dir \
    torch==2.1.2+cu118 \
    torchaudio==2.1.2+cu118 \
    --extra-index-url https://download.pytorch.org/whl/cu118

COPY requirements.txt .
# Instalamos o resto (kokoro, transformers, etc) e deixamos o pip resolver o link com o torch já instalado
RUN python3 -m pip install --no-cache-dir -r requirements.txt

# Verificação crítica de sanidade durante o build
RUN python3 -c "import torch; print(f'PyTorch OK: {torch.__version__} (CUDA: {torch.cuda.is_available()})')"

COPY . .

RUN chmod +x entrypoint.sh

# Garante que o diretório data exista e tenha permissões
RUN mkdir -p /app/data/uploads /app/data/outputs && chmod -R 777 /app/data

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["web"]
