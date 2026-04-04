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
    && update-alternatives --set python3 /usr/bin/python3.11 \
    && ln -sf /usr/bin/python3 /usr/bin/python

# Garantir que o pip esteja atualizado
RUN python3 -m pip install --upgrade pip setuptools wheel

WORKDIR /app

# PASSO 1: Instalar PyTorch cu118 (compatível com GTX 1060 / Pascal)
# Deve ser o PRIMEIRO passo de ML para que os outros pacotes não sobrescrevam
RUN python3 -m pip install --no-cache-dir \
    torch==2.1.2+cu118 \
    torchvision==0.16.2+cu118 \
    torchaudio==2.1.2+cu118 \
    --extra-index-url https://download.pytorch.org/whl/cu118

# PASSO 2: Fixar numpy<2 ANTES de instalar qualquer outra dependência
# Pacotes como transformers e scipy tentam puxar numpy>=2 se não estiver fixado
# numpy>=2 é incompatível com torch 2.1.x (causa o erro _ARRAY_API not found)
RUN python3 -m pip install --no-cache-dir "numpy<2.0.0"

# PASSO 3: Instalar demais dependências do projeto
COPY requirements.txt .
RUN python3 -m pip install --no-cache-dir -r requirements.txt

# PASSO 4: Verificação crítica de ambiente de ML no momento do build
# Se qualquer import falhar aqui, o build para e identificamos o problema
RUN python3 -c "\
import torch; \
import transformers; \
import numpy; \
print('✅ AMBIENTE ML OK'); \
print(f'  Torch:        {torch.__version__}'); \
print(f'  NumPy:        {numpy.__version__}'); \
print(f'  Transformers: {transformers.__version__}'); \
print(f'  CUDA Device:  {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"CPU only\"}') \
"

COPY . .

RUN chmod +x entrypoint.sh

# Garante que o diretório data exista e tenha permissões
RUN mkdir -p /app/data/uploads /app/data/outputs && chmod -R 777 /app/data

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["web"]
