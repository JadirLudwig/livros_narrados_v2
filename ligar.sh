#!/bin/bash

# Script para ligar o sistema de Audiolivros
# Desenvolvido para: Jadir Ludwig

echo "🚀 Iniciando Livros Narrados fastGPU (v6)..."

# Sobe os containers em background
sudo docker compose up -d

echo ""
echo "✅ Sistema iniciado com sucesso!"
echo "--------------------------------------------------"
echo "🌐 Acesse no seu navegador: http://localhost:8088"
echo "--------------------------------------------------"
echo "Dica: Use ./desligar.sh para liberar a GPU quando terminar."
