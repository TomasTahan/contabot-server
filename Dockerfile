# Dockerfile para Conta Bot
FROM python:3.12-slim

# Instalar Node.js (requerido para Claude Code CLI)
RUN apt-get update && apt-get install -y \
    curl \
    git \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Instalar Claude Code CLI globalmente
RUN npm install -g @anthropic-ai/claude-code

# Crear directorio de trabajo
WORKDIR /app

# Copiar requirements primero (para cache de Docker)
COPY requirements.txt .

# Instalar dependencias Python
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código
COPY . .

# Exponer puerto
EXPOSE 8000

# Variables de entorno por defecto
ENV HOST=0.0.0.0
ENV PORT=8000

# Crear directorio para config de Claude (se montará desde el host)
RUN mkdir -p /root/.claude

# Comando para iniciar
CMD ["python", "main.py"]
