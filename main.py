import logging
import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Olá! Eu sou o ZAR, seu agente de gestão de estoque e compras. Envie sua planilha diária para iniciarmos a análise."
    )

if __name__ == '__main__':
    TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN not found in environment variables.")
        
    application = ApplicationBuilder().token(TOKEN).build()
    
    from src.bot.handlers import start_command, handle_document, cmd_analisar, cmd_micos
    from telegram.ext import MessageHandler, filters
    
    start_handler = CommandHandler('start', start_command)
    analisar_handler = CommandHandler('analisar', cmd_analisar)
    micos_handler = CommandHandler('micos', cmd_micos)
    doc_handler = MessageHandler(filters.Document.ALL, handle_document)
    
    application.add_handler(start_handler)
    application.add_handler(analisar_handler)
    application.add_handler(micos_handler)
    application.add_handler(doc_handler)
    
    logger.info("Bot ZAR iniciado com Inteligência Artificial!")
    application.run_polling()
