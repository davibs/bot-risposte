import os
import logging
from threading import Thread
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from google import genai

# Configurazione log
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Inizializza il client di Gemini
client = genai.Client(api_key=GEMINI_API_KEY)

# Server web fittizio per tenere felice Render
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "Bot attivo e operativo, zio!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app_web.run(host="0.0.0.0", port=port)

# Personalità del bot
SYSTEM_PROMPT = """
Sei il "Libro delle Risposte", ma in versione cinica, tagliente, ironica e schietta, con un linguaggio colorito, strada e leggermente volgare.
Gli utenti ti scriveranno nel gruppo o in privato per chiederti consigli o porre domande esistenziali.
Il tuo compito è rispondere in modo imprevedibile, insultando ironicamente l'utente o prendendolo in giro per le sue ansie, ma dando comunque una specie di responso (sì, no, forse, scordatelo).
Mantieni le risposte brevi e dirette, massimo 2-3 frasi. Usa liberamente imprecazioni leggere o intercalari popolari per rendere il tutto verace.
"""

async def rispondi_con_ia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    
    testo_utente = update.message.text
    bot_username = context.bot.username
    if bot_username:
        testo_utente = testo_utente.replace(f"@{bot_username}", "").strip()

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=f"Domanda dell'utente: '{testo_utente}'",
            config={
                'system_instruction': SYSTEM_PROMPT,
                'temperature': 0.9,
            }
        )
        testo_risposta = response.text
    except Exception as e:
        testo_risposta = "Oh, cazzo, il cervello mi è andato in pappa. Riprova più tardi."
        print(f"Errore IA: {e}")

    await update.message.reply_text(testo_risposta)

def main():
    # Avvia il server web in un thread separato
    t = Thread(target=run_web)
    t.daemon = True
    t.start()

    # Avvia il bot Telegram
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Filtro: risponde in chat privata OPPURE nei gruppi se c'è un reply o una menzione
    app.add_handler(MessageHandler(
        filters.TEXT & filters.UpdateType.MESSAGE & 
        (filters.ChatType.PRIVATE | filters.REPLY | filters.Entity("mention")), 
        rispondi_con_ia
    ))
    
    print("Bot IA avviato su cloud con server web integrato...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
