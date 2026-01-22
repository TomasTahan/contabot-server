# Conta Bot - Guía de Deployment

## Opción 1: Local (desarrollo)

### Paso 1: Iniciar el túnel cloudflared
```bash
cloudflared tunnel --url http://localhost:8000
```

### Paso 2: Actualizar el .env con la nueva URL
Editar `/Users/mac-tomy/Documents/conta-bot/server/.env`:
```
WEBHOOK_URL=https://[nueva-url].trycloudflare.com
```

### Paso 3: Iniciar el servidor
```bash
cd /Users/mac-tomy/Documents/conta-bot/server
source .venv/bin/activate
python main.py
```

---

## Opción 2: Easypanel (producción)

### Prerrequisitos en el VPS
1. Tener Claude Code CLI instalado y autenticado en el host
2. Saber la ruta de la config: normalmente `~/.claude/` o `/root/.claude/`

### Paso 1: Subir el código a GitHub
```bash
cd /Users/mac-tomy/Documents/conta-bot
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/TU_USUARIO/conta-bot.git
git push -u origin main
```

### Paso 2: Crear App en Easypanel

1. En Easypanel, crear nueva App > "App from Dockerfile"
2. Conectar el repositorio de GitHub
3. Configurar:
   - **Build context**: `server`
   - **Dockerfile path**: `server/Dockerfile`

### Paso 3: Configurar Variables de Entorno

En Easypanel > App > Environment, agregar las variables del archivo `.env.example`:
```
TELEGRAM_BOT_TOKEN=tu_token_de_telegram
POCKETBASE_URL=tu_url_de_pocketbase
POCKETBASE_ADMIN_EMAIL=tu_email
POCKETBASE_ADMIN_PASSWORD=tu_password
GROQ_API_KEY=tu_api_key_de_groq
WEBHOOK_URL=https://[tu-app].easypanel.host
ANTHROPIC_API_KEY=tu_api_key_de_anthropic
```

### Paso 4: Configurar Dominio

1. En Easypanel > App > Domains
2. Habilitar el dominio automático o configurar uno custom
3. Asegurarse de que HTTPS esté habilitado
4. Actualizar `WEBHOOK_URL` con el dominio final

### Paso 5: Montar Config de Claude (IMPORTANTE)

En Easypanel > App > Mounts, agregar un volumen:
- **Host path**: `/root/.claude` (o donde esté la config en tu VPS)
- **Container path**: `/root/.claude`

Esto permite que el contenedor use la autenticación de Claude Code del host.

### Paso 6: Deploy

1. Click en "Deploy"
2. Verificar en los logs que aparezca:
   ```
   Webhook set to: https://[tu-dominio]/webhook
   Conta Bot server started
   ```

---

## Verificación

Envía un mensaje al bot de Telegram. Deberías recibir respuesta.

## Troubleshooting

- **Error de autenticación Claude**: Verificar que el volumen `/root/.claude` esté montado correctamente
- **Webhook no funciona**: Verificar que WEBHOOK_URL tenga el dominio correcto con HTTPS
- **Error de PocketBase**: Verificar credenciales en variables de entorno
