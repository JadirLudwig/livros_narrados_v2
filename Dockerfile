FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

# Evitar prompts durante a instalação
ENV DEBIAN_FRONTEND=noninteractive

# Instalar Python 3.11 e dependências do sistema
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3-pip \
    python3.11-dev \
    python3.11-venv \
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
    && ln -s /usr/bin/python3 /usr/bin/python

# Garantir que o pip esteja atualizado e apontando para o 3.11
RUN python3 -m pip install --upgrade pip setuptools

WORKDIR /app

COPY requirements.txt .
# Instalar dependências usando o módulo python3 para evitar conflitos de ambiente
RUN python3 -m pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x entrypoint.sh

# Garante que o diretório data exista e tenha permissões
RUN mkdir -p /app/data/uploads /app/data/outputs && chmod -R 777 /app/data

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["web"]
