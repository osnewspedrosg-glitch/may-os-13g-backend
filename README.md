---
title: MAY OS 13G Backend
emoji: 🎙️
colorFrom: red
colorTo: pink
sdk: docker
app_port: 7860
---
# MAY OS 13G · Backend con voz

MAY, la presentadora de OSNews, conversa contigo (IA vía API de Gemini, modelo `gemini-flash-lite-latest`) y responde con voz en español (gTTS).

Creado por Pedro Sánchez Gómez, del Mar Menor, con la ayuda de Copilot y Grok.

## Uso
- `GET /` → estado
- `POST /api/chat` → `{"message": "Hola", "session_id": "opcional", "persona": "may|asdrubal|may13g", "idioma": "es|en|fr|it|pt|de|ar|zh"}` devuelve `response_text`, `audio_url`, `session_id`, `emotion` (emoción simulada de MAY: etiqueta, emoji, intensidad 1-3) (reenvíalo para que MAY recuerde la charla)
- `GET /api/personas`, `GET /api/idiomas`
- `GET /web` → página de prueba (elige compañía e idioma, ves la emoción y oyes el audio)
- `GET /api/emociones` → rueda de emociones (simuladas)
- `GET /api/audio/{archivo}.mp3` → audio (se borra solo tras ~1 h)

## Local
```bash
pip install -r requirements.txt
export GEMINI_API_KEY=tu_clave   # nunca la subas al repo
uvicorn main:app --port 8000
```

## Despliegue gratis
- **Render** (plan free): New → Blueprint → este repo (usa `render.yaml`), añade `GEMINI_API_KEY`.
- **Hugging Face Spaces** (Docker): usa el `Dockerfile`, añade el secreto `GEMINI_API_KEY`.
