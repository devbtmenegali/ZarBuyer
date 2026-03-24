import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is runing!")
        
    def log_message(self, format, *args):
        pass # Silenciar logs do servidor fake

def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    try:
        server = HTTPServer(('0.0.0.0', port), DummyHandler)
        server.serve_forever()
    except Exception:
        pass

if os.environ.get("RENDER") or os.environ.get("PORT"):
    threading.Thread(target=run_dummy_server, daemon=True).start()

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
    
    from src.bot.handlers import start_command, handle_document, cmd_analisar, cmd_micos, cmd_pendencias, cmd_negociar, cmd_comprar, cmd_comparar, cmd_cotar, cmd_admin, cmd_sou_fornecedor, cmd_caixa, cmd_giro, cmd_reprecificar, cmd_chargeback, cmd_docas, handle_text
    from telegram.ext import MessageHandler, filters
    
    start_handler = CommandHandler('start', start_command)
    analisar_handler = CommandHandler('analisar', cmd_analisar)
    micos_handler = CommandHandler('micos', cmd_micos)
    pendencias_handler = CommandHandler('pendencias', cmd_pendencias)
    negociar_handler = CommandHandler('negociar', cmd_negociar)
    comprar_handler = CommandHandler('comprar', cmd_comprar)
    comparar_handler = CommandHandler('comparar', cmd_comparar)
    cotar_handler = CommandHandler('cotar', cmd_cotar)
    admin_handler = CommandHandler('admin', cmd_admin)
    sou_fornecedor_handler = CommandHandler('sou_fornecedor', cmd_sou_fornecedor)
    caixa_handler = CommandHandler('caixa', cmd_caixa)
    giro_handler = CommandHandler('giro', cmd_giro)
    reprecificar_handler = CommandHandler('reprecificar', cmd_reprecificar)
    chargeback_handler = CommandHandler('chargeback', cmd_chargeback)
    docas_handler = CommandHandler('docas', cmd_docas)
    doc_handler = MessageHandler(filters.Document.ALL, handle_document)
    text_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
    
    application.add_handler(start_handler)
    application.add_handler(admin_handler)
    application.add_handler(sou_fornecedor_handler)
    application.add_handler(caixa_handler)
    application.add_handler(giro_handler)
    application.add_handler(reprecificar_handler)
    application.add_handler(chargeback_handler)
    application.add_handler(docas_handler)
    application.add_handler(analisar_handler)
    application.add_handler(micos_handler)
    application.add_handler(pendencias_handler)
    application.add_handler(negociar_handler)
    application.add_handler(comprar_handler)
    application.add_handler(comparar_handler)
    application.add_handler(cotar_handler)
    application.add_handler(doc_handler)
    application.add_handler(text_handler)
    
    logger.info("Bot ZAR iniciado com Inteligência Artificial!")
    application.run_polling()
