import logging
import datetime
from telegram.ext import ContextTypes
from src.services.proactive_alerts import ProactiveAlertsService

logger = logging.getLogger(__name__)

async def run_morning_alerts(context: ContextTypes.DEFAULT_TYPE):
    """
    Função engatilhada pelo JobQueue do Telegram rodando diariamente ou via comando de teste.
    Faz a varredura e envia o push para os administradores.
    """
    logger.info("⏰ Cron Job Disparado: executando varredura matinal de alertas")
    try:
        service = ProactiveAlertsService()
        alert_text = service.generate_morning_briefing()
        
        if alert_text:
            from src.db.supabase_client import get_supabase_client
            supabase = get_supabase_client()
            
            # Dispara o Push (Notificação) no Telegram de toda a Diretoria (Admins)
            resp = supabase.table('bot_users').select('telegram_id').eq('role', 'admin').execute()
            
            if not resp.data:
                logger.warning("Nenhum admin cadastrado para receber alertas passivos.")
                return
                
            for admin in resp.data:
                await context.bot.send_message(chat_id=admin['telegram_id'], text=alert_text)
                
    except Exception as e:
        logger.error(f"Erro catastrófico no disparo de alertas matinais: {e}")
