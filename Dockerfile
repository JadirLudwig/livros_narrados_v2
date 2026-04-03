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

# INSTALAÇÃO UNIFICADA E BLOQUEADA (ESTRATÉGIA FINAL)
# Instalamos absolutamente tudo que o motor de IA precisa em um único passo
# Isso evita que o pip tente "resolver" dependências depois e quebre o link do Torch
RUN python3 -m pip install --no-cache-dir \
    torch==2.1.2+cu118 \
    torchvision==0.16.2+cu118 \
    torchaudio==2.1.2+cu118 \
    --extra-index-url https://download.pytorch.org/whl/cu118

COPY requirements.txt .
# Instalamos as demais libs. Note que transformers e scipy estão no requirements.txt
RUN python3 -m pip install --no-cache-dir -r requirements.txt

# Verificação crítica: se este comando falhar, o build para aqui e sabemos o motivo
RUN python3 -c "import torch; import transformers; print('✅ AMBIENTE ML OK'); print(f'Torch: {torch.__version__}'); print(f'CUDA: {torch.cuda.is_available()}')"

COPY . .

RUN chmod +x entrypoint.sh

# Garante que o diretório data exista e tenha permissões
RUN mkdir -p /app/data/uploads /app/data/outputs && chmod -R 777 /app/data

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["web"]
