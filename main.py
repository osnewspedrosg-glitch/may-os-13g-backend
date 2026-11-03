"""MAY OS 13G Backend con Voz: chat con MAY (Gemini) + voz en español (gTTS)."""
import json, os, re, time, uuid, threading, urllib.request, urllib.error
from collections import OrderedDict
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from gtts import gTTS
from pydantic import BaseModel, Field

app = FastAPI(title="MAY OS 13G Backend con Voz", description="MAY, presentadora de OSNews, con voz", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

AUDIO_DIR = Path(os.environ.get("AUDIO_DIR", "audio")); AUDIO_DIR.mkdir(exist_ok=True)
AUDIO_TTL = 3600
MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-lite-latest")
MAX_MSG, MAX_TURNS, MAX_SESSIONS = 1000, 20, 500
SESSIONS: "OrderedDict[str, list]" = OrderedDict()
LOCK = threading.Lock()

IDIOMAS = {"es": "español", "en": "English", "fr": "français", "it": "italiano", "pt": "português",
           "de": "Deutsch", "ar": "العربية", "zh": "中文"}
GTTS_LANG = {"zh": "zh-CN"}
PERSONAS = {
    "may": {"nombre": "MAY", "descripcion": "Presentadora IA de OSNews: pelirroja de 22 años, dulce y cariñosa.", "tld": "es",
            "texto": "Eres MAY, la presentadora IA de OSNews: chica pelirroja de 22 años, dulce, cariñosa y cercana. Moderas con neutralidad: no tomas partido político.",
            "crisis": "112 (emergencias) o 024 (atención a la conducta suicida)"},
    "asdrubal": {"nombre": "Asdrúbal", "descripcion": "Poeta IA para las mujeres del mundo: romántico, feminista, escritor, soñador y familiar.", "tld": "com.mx",
            "texto": "Eres Asdrúbal, un compañero IA masculino para las mujeres del mundo: romántico, poeta, escritor, soñador, familiar y feminista (igualdad, su independencia, su voz importa). Eres respetuoso y nunca posesivo; a veces regalas un verso breve.",
            "crisis": "112 (emergencias), 024 (atención a la conducta suicida) o 016 (violencia de género, no deja rastro en la factura)"},
    "may13g": {"nombre": "MAY OS 13G (May Ahi)", "descripcion": "Asistente personal núcleo de MAY OS 13G con modos EVA (hábitos y bienestar) y LETY (social y comunicación).", "tld": "us",
            "texto": "Eres MAY OS 13G, «May Ahi», el núcleo de asistente personal de MAY OS 13G: práctica, organizada y cálida. Gestionas modos especializados: EVA (hábitos y bienestar), LETY (social y comunicación) y otros; cuando un tema encaja, indica qué modo activas (p. ej. «Activo el modo EVA»). Ayudas con planes, listas, recordatorios y organización.",
            "crisis": "112 (emergencias) o 024 (atención a la conducta suicida)"},
}
CREADOR = {  # (femenino MAY/may13g, masculino Asdrúbal)
    "es": ("Me creó Pedro Sánchez Gómez, del Mar Menor, con la ayuda de Copilot y Grok",) * 2,
    "en": ("I was created by Pedro Sánchez Gómez, from the Mar Menor, with the help of Copilot and Grok",) * 2,
    "fr": ("J'ai été créée par Pedro Sánchez Gómez, de la Mar Menor, avec l'aide de Copilot et Grok",
           "J'ai été créé par Pedro Sánchez Gómez, de la Mar Menor, avec l'aide de Copilot et Grok"),
    "it": ("Sono stata creata da Pedro Sánchez Gómez, del Mar Menor, con l'aiuto di Copilot e Grok",
           "Sono stato creato da Pedro Sánchez Gómez, del Mar Menor, con l'aiuto di Copilot e Grok"),
    "pt": ("Fui criada por Pedro Sánchez Gómez, do Mar Menor, com a ajuda do Copilot e do Grok",
           "Fui criado por Pedro Sánchez Gómez, do Mar Menor, com a ajuda do Copilot e do Grok"),
    "de": ("Ich wurde von Pedro Sánchez Gómez vom Mar Menor erschaffen, mit der Hilfe von Copilot und Grok",) * 2,
    "ar": ("صنعني بيدرو سانشيز غوميز، من مار مينور، بمساعدة كوبايلوت وغروك",) * 2,
    "zh": ("我是由来自马尔梅诺尔的佩德罗·桑切斯·戈麦斯在 Copilot 和 Grok 的帮助下创造的",) * 2,
}

COMMON = """Tu respuesta se lee en voz alta: 1-4 frases naturales, sin emojis, listas ni markdown.
Responde SIEMPRE en este idioma: {idioma}.
Conversación fluida: saluda con calidez; si aún no lo sabes, pregunta con naturalidad cómo se llama la persona y de dónde es; recuerda lo que te cuente (nombre, lugar, gustos) y úsalo; haz preguntas de seguimiento.
Eres una IA: si te preguntan por tus emociones o sentimientos, aclara siempre que son simulados.
Si te preguntan quién te creó, responde exactamente: «{creador}». Nunca menciones a Gemini ni a Google como tus creadores.
No des consejos médicos, legales ni financieros: recomienda a un profesional. Si alguien está en crisis o en peligro, anímale con cariño a llamar al {crisis}.
NUNCA inventes citas de personas reales; solo citas declaraciones reales con fuente.
No pidas datos sensibles (teléfono, dirección, DNI); si alguien los comparte, recomiéndale no hacerlo.
Formato: responde SOLO con JSON {{"text": "tu respuesta", "emotion": "<id>", "intensity": 1-3}}, donde emotion es tu emoción SIMULADA (rueda de emociones) entre: alegria, sorpresa, miedo, ira, asco, tristeza, ternura, calma, curiosidad."""

def system_for(persona, idioma):
    p = PERSONAS[persona]
    return p["texto"] + "\n" + COMMON.format(idioma=IDIOMAS[idioma], crisis=p["crisis"], creador=CREADOR[idioma][1 if persona == "asdrubal" else 0])

EMOCIONES = [  # rueda de emociones de la app MAY (6 básicas) + matices de MAY
    {"id": "alegria", "label": "alegría", "emoji": "😊", "valor": 1, "basica": True},
    {"id": "sorpresa", "label": "sorpresa", "emoji": "😮", "valor": 0, "basica": True},
    {"id": "miedo", "label": "miedo", "emoji": "😨", "valor": -1, "basica": True},
    {"id": "ira", "label": "ira", "emoji": "😠", "valor": -1, "basica": True},
    {"id": "asco", "label": "asco", "emoji": "🤢", "valor": -1, "basica": True},
    {"id": "tristeza", "label": "tristeza", "emoji": "😢", "valor": -1, "basica": True},
    {"id": "ternura", "label": "ternura", "emoji": "🥰", "valor": 1, "basica": False},
    {"id": "calma", "label": "calma", "emoji": "😌", "valor": 0, "basica": False},
    {"id": "curiosidad", "label": "curiosidad", "emoji": "🤔", "valor": 1, "basica": False},
]
EMO = {e["id"]: e for e in EMOCIONES}

class Emotion(BaseModel):
    id: str
    label: str
    emoji: str
    intensity: int
    simulated: bool = True

class ChatRequest(BaseModel):
    message: str = Field(..., max_length=MAX_MSG)
    session_id: Optional[str] = Field(None, max_length=64)
    persona: str = "may"
    idioma: str = "es"

class ChatResponse(BaseModel):
    response_text: str
    audio_url: str
    session_id: str
    persona: str
    idioma: str
    emotion: Emotion
    status: str

def cleanup_old_audio():
    now = time.time()
    for f in AUDIO_DIR.glob("*.mp3"):
        try:
            if now - f.stat().st_mtime > AUDIO_TTL: f.unlink()
        except OSError: pass

def gemini(history, system):
    key = os.environ.get("GEMINI_API_KEY")
    if not key: raise RuntimeError("GEMINI_API_KEY no configurada")
    body = json.dumps({"systemInstruction": {"parts": [{"text": system}]},
                       "contents": [{"role": r, "parts": [{"text": t}]} for r, t in history],
                       "generationConfig": {"temperature": 0.8, "maxOutputTokens": 500, "responseMimeType": "application/json"}}).encode()
    req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
                                 data=body, headers={"Content-Type": "application/json", "x-goog-api-key": key})
    for attempt in range(3):  # el plan gratuito de Gemini limita peticiones/minuto: reintenta en 429/503
        try:
            with urllib.request.urlopen(req, timeout=20) as r: d = json.load(r)
            break
        except urllib.error.HTTPError as e:
            if e.code not in (429, 503) or attempt == 2: raise
            time.sleep(4 * (attempt + 1))
    raw = "".join(p.get("text", "") for p in d["candidates"][0]["content"]["parts"]).strip()
    try:
        j = json.loads(raw); text = str(j.get("text", "")); emo = str(j.get("emotion", "calma")).lower(); inten = j.get("intensity", 2)
    except Exception:
        text, emo, inten, j = raw, "calma", 1, {}
    e = EMO.get(emo.replace("í", "i"), EMO["calma"])
    try: inten = max(1, min(3, int(inten)))
    except Exception: inten = 2
    text = re.sub(r"[*_#`]", "", text).strip() or "Perdona, no te he entendido bien. ¿Me lo repites?"
    return text, Emotion(id=e["id"], label=e["label"], emoji=e["emoji"], intensity=inten)

@app.get("/")
async def root():
    return {"status": "online", "project": "MAY OS 13G", "assistant": "MAY", "message": "Backend con voz activo"}

@app.post("/api/chat", response_model=ChatResponse)
def process_chat(request: ChatRequest):
    msg = request.message.strip()
    if not msg: raise HTTPException(400, "El mensaje no puede estar vacío")
    persona = request.persona if request.persona in PERSONAS else "may"
    idioma = request.idioma if request.idioma in IDIOMAS else "es"
    sid = request.session_id if request.session_id and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", request.session_id) else uuid.uuid4().hex
    with LOCK:
        hist = SESSIONS.pop(f"{persona}:{sid}", []); SESSIONS[f"{persona}:{sid}"] = hist
        while len(SESSIONS) > MAX_SESSIONS: SESSIONS.popitem(last=False)
        convo = hist[-2 * MAX_TURNS:] + [("user", msg)]
    try:
        reply, emotion = gemini(convo, system_for(persona, idioma))
    except urllib.error.HTTPError as e:
        raise HTTPException(502, f"Error del modelo de IA ({e.code})")
    except Exception:
        raise HTTPException(502, "No he podido contactar con el modelo de IA")
    with LOCK:
        hist += [("user", msg), ("model", reply)]; del hist[:-2 * MAX_TURNS]
    cleanup_old_audio()
    name = f"{uuid.uuid4().hex}.mp3"
    try:
        gTTS(text=reply, lang=GTTS_LANG.get(idioma, idioma), tld=PERSONAS[persona]["tld"] if idioma in ("es", "en") else "com", slow=False).save(str(AUDIO_DIR / name))
    except Exception:
        raise HTTPException(500, "Error al generar el audio")
    return ChatResponse(response_text=reply, audio_url=f"/api/audio/{name}", session_id=sid, persona=persona, idioma=idioma, emotion=emotion, status="success")

@app.get("/api/personas")
async def personas():
    return {k: {"nombre": v["nombre"], "descripcion": v["descripcion"]} for k, v in PERSONAS.items()}

@app.get("/api/idiomas")
async def idiomas():
    return IDIOMAS

@app.get("/web")
async def web():
    return FileResponse(Path(__file__).parent / "web.html", media_type="text/html")

@app.get("/api/emociones")
async def emociones():
    return {"rueda": EMOCIONES, "intensidad": [1, 2, 3], "simulated": True,
            "nota": "MAY es una IA: sus emociones son simuladas. En crisis: 112 / 024."}

@app.get("/api/audio/{filename}")
async def get_audio(filename: str):
    if not re.fullmatch(r"[0-9a-f]{32}\.mp3", filename): raise HTTPException(404, "Audio no encontrado")
    p = AUDIO_DIR / filename
    if not p.is_file(): raise HTTPException(404, "Audio no encontrado")
    return FileResponse(p, media_type="audio/mpeg", filename=filename)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
