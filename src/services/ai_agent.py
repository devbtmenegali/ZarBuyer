import os
import json
import logging
from google import genai
from google.genai import types
from datetime import datetime

logger = logging.getLogger(__name__)

class ZarAIAgent:
    def __init__(self):
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("Chave GEMINI_API_KEY não encontrada.")
        # O Client moderno usa `genai.Client`
        self.client = genai.Client(api_key=api_key)
        self.model_name = "gemini-2.5-flash"  # Modelo rápido e barato para análise

    def analyze_inventory_health(self, products_data: list) -> str:
        """
        Gera relatórios sobre dead stock, sugestões de queima e bundling
        com base nos dados crus do banco.
        """
        # Obviamente, p/ muitos dados precisaríamos filtrar antes ou enviar em batch,
        # Mas para fins do módulo ZAR, pegaremos destaques (produtos com baixo giro, etc).
        
        prompt = f"""
        Você é o ZAR, um Consultor de Compras e Estoque de Varejo altamente inteligente.
        
        Sua tarefa: Analisar os dados de estoque atuais e gerar insights matadores:
        1. Identificação de Dead Stock ("Micos"): Produtos com alto saldo que precisam de "Queima". Sugira um % de desconto.
        2. Sugestão de Combos (Bundling): Una produtos de baixo giro com alto giro da mesma marca ou categoria complementar.
        3. Elasticidade: Destaque o que pode ter o preço reajustado para ganhar margem.

        Hoje é {datetime.now().strftime('%d/%m/%Y')}.
        
        DADOS DE ESTOQUE:
        {json.dumps(products_data[:200], default=str)} # Limitado p/ token window

        Formate sua resposta num relatório em Markdown (para ser enviado via Telegram).
        """

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.3,
                )
            )
            return response.text
        except Exception as e:
            logger.error(f"Erro ao chamar o Gemini: {e}")
            return "❌ Erro ao processar inteligência do estoque com o ZAR AI."
            
    def analyze_negotiation(self, current_margin: float, proposed_cost: float, selling_price: float) -> str:
        """
        Ruptura de margem e reprecificação dinâmica numa negociação ao vivo.
        """
        prompt = f"""
        Você é o ZAR. Recebemos uma proposta de um fornecedor:
        Custo proposto: R$ {proposed_cost}
        Preço de Venda Praticado: R$ {selling_price}
        Margem ideal exigida: {current_margin}%
        
        Calcule instantaneamente:
        1. A margem nova.
        2. Isso inviabiliza nosso preço de venda local? (Ruptura de Margem)
        3. Podemos aceitar subindo o preço atual do estoque parado? (Reprecificação Dinâmica)
        Seja direto e aja como o conselheiro da mesa de negociação.
        """
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            return response.text
        except Exception as e:
            return f"❌ Erro ZAR: {str(e)}"

# agent = ZarAIAgent()
# report = agent.analyze_inventory_health(dados)
