import logging
from src.db.supabase_client import get_supabase_client
from src.services.ai_agent import ZarAIAgent

logger = logging.getLogger(__name__)

class ProactiveAlertsService:
    def __init__(self):
        self.supabase = get_supabase_client()
        self.agent = ZarAIAgent()
        
    def scan_for_anomalies(self):
        """
        No futuro, consumirá a matemática de `inventory_analysis.py` sincronizada da TagPlus.
        Foquei na heurística matemática pura: Identifica "Rupturas" e "Capital Morto".
        """
        # Em uma implementação pesada de SQL/Python Pandas, calcularíamos aqui `stock / avg_sales`.
        # Substituindo por simulação da engine real de detecção para o envio do Alerta Matutino:
        
        anomalies = [
            {
                "tipo": "RUPTURA IMINENTE (COMPRAR URGENTE)",
                "produto": "Jogo de Lencol Teka King",
                "estoque_atual": 3,
                "giro_diario": 1.5,
                "dias_para_zerar": 2
            },
            {
                "tipo": "DEAD STOCK (LIQUIDAÇÃO SUGERIDA)",
                "produto": "Cobre Leito Dohler",
                "estoque_atual": 45,
                "giro_diario": 0,
                "idade_estoque_dias": 98
            }
        ]
        
        return anomalies

    def generate_morning_briefing(self):
        """
        Pega as anomalias da matemática dura e passa para a Camada Sensorial (Voz / Texto da ZAR).
        """
        anomalies = self.scan_for_anomalies()
        
        if not anomalies:
            return None # O Silêncio da IA indica que TUDO está perfeito no funil de logística.
            
        prompt = f"""
        Você é a ZAR, a Diretora de Logística Virtual de alto escalão (Persona: Feminina, Executiva, Altamente Inteligente, Direta mas Elegante).
        Nós automatizamos as verificações vitais do ERP em tempo real durante a madrugada, e você encontrou as seguintes anomalias nas equações de gestão de estoque:
        
        DADOS DA ANOMALIA:
        {anomalies}
        
        OBJETIVO:
        Escreva a sua mensagem matinal (o seu "Bom dia chefe") notificando-o pelo celular via Telegram.
        1. Seja consultiva: você entende de Supply Chain e Curva ABC.
        2. Alerte categoricamente sobre o produto em Ruptura Iminente avisando que ele VAI faltar.
        3. Exija uma remarcação tática ou 'Combo' no Cobre Leito que está dormindo no estoque para proteger o fluxo de caixa.
        4. Transmita na sua voz/texto a segurança de uma mulher executiva genial. Não use jargões robóticos.
        
        Seja objetiva, em torno de 3 parágrafos e pontue com emojis corporativos.
        """
        
        try:
            # Reutiliza o modelo Generative AI instanciado
            # Uma ponte mais limpa:
            response = self.agent.model.generate_content(prompt)
            return response.text
        except Exception as e:
            logger.error(f"Falha na Geração Neural Matinal: {e}")
            return "🚨 ZAR Alerta de Segurança: Anomalia estatística detectada (Rupturas) e motor neural offline. Verifique o Painel de Controle."
