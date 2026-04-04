#!/bin/bash

# Script para desligar o sistema de Audiolivros
# Desenvolvido para: Jadir Ludwig

echo "🛑 Desligando Livros Narrados fastGPU..."

# Para e remove os containers
sudo docker compose down

echo ""
echo "✅ Sistema encerrado e GPU liberada!"
