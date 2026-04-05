#!/bin/bash
# Script de Publicação Automática: Projeto Livros Narrados

echo "=== Publicando no GitHub ==="
git add .
git commit -m "update: Atualização de funcionalidades via Agent"
git push

echo "=== Publicando no DockerHub (saviogl/livros-narrados-web) ==="
# docker login  # Descomente e faça login caso ainda não tenha autenticado seu CLI
docker build -t saviogl/livros-narrados-web:latest -f Dockerfile .
docker push saviogl/livros-narrados-web:latest

echo "✅ Deploy Concluído!"
