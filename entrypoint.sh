#!/bin/bash
set -e

case "${1:-}" in
    web)
        echo "Iniciando Web Server..."
        exec uvicorn web.main:app --host 0.0.0.0 --port 8000
        ;;
    worker)
        echo "Iniciando Celery Worker..."
        exec celery -A worker.celery_app worker --loglevel=info
        ;;
    *)
        echo "Livros Narrados - Docker Image"
        echo ""
        echo "Uso: docker run <imagem> <servico>"
        echo ""
        echo "Serviços disponíveis:"
        echo "  web     - Inicia o servidor web (FastAPI)"
        echo "  worker  - Inicia o worker (Celery)"
        echo ""
        echo "Exemplo:"
        echo "  docker run minha-imagem web"
        echo "  docker run minha-imagem worker"
        echo ""
        echo "Para usar com docker-compose, o arquivo compose já contém os comandos corretos."
        exit 1
        ;;
esac
