import os
import time
import asyncio
import logging
from threading import Thread

from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from google import genai
from google.genai import types

# Configurazione log
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("libro_risposte")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    raise RuntimeError("Mancano TELEGRAM_TOKEN o GEMINI_API_KEY nelle variabili d'ambiente.")

# Client Gemini
client = genai.Client(api_key=GEMINI_API_KEY)
MODEL = "gemini-2.5-flash"

# Server web per Render (va pingato dall'esterno, es. UptimeRobot, per evitare lo sleep)
app_web = Flask(__name__)


@app_web.route("/")
def home():
    return "Bot attivo e operativo, zio!"


def run_web():
    port = int(os.environ.get("PORT", 10000))
    app_web.run(host="0.0.0.0", port=port)


# Personalità del bot
SYSTEM_PROMPT = """
Sei il "Libro delle Risposte", ma in versione cinica, tagliente, ironica e schietta, con un linguaggio colorito, strada e leggermente volgare.
Gli utenti ti scriveranno nel gruppo o in privato per chiederti consigli o porre domande esistenziali.
Il tuo compito è rispondere in modo imprevedibile, prendendo in giro con ironia l'utente per le sue ansie, ma dando comunque una specie di responso (sì, no, forse, scordatelo).
Mantieni le risposte brevi e dirette, massimo 2-3 frasi. Usa liberamente imprecazioni leggere o intercalari popolari per rendere il tutto verace.
Rispondi sempre in italiano.
"""

# Safety settings allentati, utili con un prompt volgare/sarcastico
SAFETY_SETTINGS = [
    types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_ONLY_HIGH"),
    types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_ONLY_HIGH"),
    types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_ONLY_HIGH"),
    types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_ONLY_HIGH"),
]

GEN_CONFIG = types.GenerateContentConfig(
    system_instruction=SYSTEM_PROMPT,
    temperature=0.9,
    max_output_tokens=300,
    safety_settings=SAFETY_SETTINGS,
    # Niente "thinking": risposte più rapide e il budget di token resta per il testo
    thinking_config=types.ThinkingConfig(thinking_budget=0),
)

FALLBACK_ERRORE = "Oh, cazzo, il cervello mi è andato in pappa. Riprova più tardi."
FALLBACK_VUOTO = "Neanche io so che dirti, scordatelo."
FALLBACK_SPAM = "Calma, cazzo, una domanda alla volta. Respira e riprova tra qualche secondo."

# Rate limit semplice per utente (secondi tra una richiesta e l'altra)
COOLDOWN_SECONDI = 5
_ultima_richiesta: dict[int, float] = {}


def troppo_veloce(user_id: int) -> bool:
    ora = time.monotonic()
    ultima = _ultima_richiesta.get(user_id, 0.0)
    if ora - ultima < COOLDOWN_SECONDI:
        return True
    _ultima_richiesta[user_id] = ora
    return False


async def rispondi_con_ia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text:
        return

    bot_username = context.bot.username or ""

    in_privato = msg.chat.type == "private"
    reply_al_bot = (
        msg.reply_to_message is not None
        and msg.reply_to_message.from_user is not None
        and msg.reply_to_message.from_user.id == context.bot.id
    )
    menzionato = bool(bot_username) and f"@{bot_username}".lower() in msg.text.lower()

    # Nei gruppi risponde solo se menzionato o se è un reply a un suo messaggio
    if not (in_privato or reply_al_bot or menzionato):
        return

    user_id = msg.from_user.id if msg.from_user else 0
    if troppo_veloce(user_id):
        await msg.reply_text(FALLBACK_SPAM)
        return

    testo_utente = msg.text
    if bot_username:
        testo_utente = testo_utente.replace(f"@{bot_username}", "").strip()
    if not testo_utente:
        testo_utente = "(nessuna domanda, l'utente ti ha solo chiamato)"

    try:
        # Client async: non blocca l'event loop
        response = await client.aio.models.generate_content(
            model=MODEL,
            contents=f"Domanda dell'utente: '{testo_utente}'",
            config=GEN_CONFIG,
        )
        testo_risposta = response.text or FALLBACK_VUOTO
    except Exception:
        logger.exception("Errore chiamata Gemini")
        testo_risposta = FALLBACK_ERRORE

    await msg.reply_text(testo_risposta)


def main():
    # Server web in un thread separato
    t = Thread(target=run_web, daemon=True)
    t.start()

    # Bot Telegram
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Il filtro fine è dentro la funzione (privato / reply al bot / menzione)
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, rispondi_con_ia)
    )

    logger.info("Bot IA avviato su cloud con server web integrato...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
