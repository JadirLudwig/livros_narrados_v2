#!/bin/bash
# Script de Publicação Automática: Projeto Livros Narrados

echo "=== Publicando no GitHub ==="
git add .
git commit -m "update: Atualização de funcionalidades via Agent"
git push

echo "=== Publicando no DockerHub (ludwig91/livros_narrados_fastgpu:v8) ==="
# docker login  # Descomente e faça login caso ainda não tenha autenticado seu CLI
docker build -t ludwig91/livros_narrados_fastgpu:v8 -f Dockerfile .
docker push ludwig91/livros_narrados_fastgpu:v8

echo "✅ Deploy Concluído!"
