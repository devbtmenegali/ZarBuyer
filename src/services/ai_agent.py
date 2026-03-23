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
        
        # Calcula os totais REAIS no Python para a IA não errar a matemática
        total_items = sum([float(p.get("Estoque_Qtd", p.get("Quantidade", 0))) for p in products_data])
        total_value = sum([float(p.get("Custo_Total", p.get("Valor_Parado", 0))) for p in products_data])
        
        prompt = f"""
        Você é o ZAR, um Consultor de Compras e Estoque de Varejo altamente inteligente.
        
        Sua tarefa: Analisar os dados de estoque atuais e gerar insights matadores:
        1. Identificação de Dead Stock ("Micos"): Produtos com alto saldo que precisam de "Queima". Sugira um % de desconto.
        2. Sugestão de Combos (Bundling): Una produtos de baixo giro com alto giro da mesma marca ou categoria complementar.
        3. Elasticidade: Destaque o que pode ter o preço reajustado para ganhar margem.
        
        [DIRETRIZ MÁXIMA PARA O ZAR]:
        - SEJA EXTREMAMENTE OBJETIVO E DIRETO. Nada de textos longos, parágrafos genéricos ou enrolação ("yapping").
        - Seus relatórios devem ser curtos, focados na prática: "O que fazer", "Qual o produto" e "Qual o número".
        - Use listas curtas (bullet points). Menos palavras, mais ação. O gestor tem pouco tempo.
        
        [RESUMO FINANCEIRO EXATO (Não recalcule, use estes números)]:
        - Quantidade Total de Itens nesta amostra: {total_items}
        - Valor Total Parado (Custo) nesta amostra: R$ {total_value:,.2f}

        Hoje é {datetime.now().strftime('%d/%m/%Y')}.
        
        DADOS DE ESTOQUE:
        {json.dumps(products_data[:200], default=str)} # Limitado p/ token window

        Responda da forma mais curta e objetiva possível.
        Evite usar a formatação Markdown (como ** ou #) pois ela foi desabilitada no Telegram. 
        Pode usar quebras de linha e emojis, mas sem poluir.
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
            return f"❌ Erro ao processar inteligência do estoque com o ZAR AI: {str(e)}"
            
    def analyze_brand_summary(self, products_data: list, brand: str) -> str:
        total_items = sum([float(p.get("Estoque_Qtd", p.get("Quantidade", 0))) for p in products_data])
        total_value = sum([float(p.get("Custo_Total", p.get("Valor_Parado", 0))) for p in products_data])
        
        # Média de venda calculada no python p/ não alucinar
        precos = [float(p.get("Preco_Venda", 0)) for p in products_data if float(p.get("Preco_Venda", 0)) > 0]
        media_venda = sum(precos) / len(precos) if precos else 0
        
        brand_name = (brand or "Geral").upper()
        
        prompt = f"""
        Você é o ZAR. Resuma a marca {brand_name} no formato EXATO abaixo:

        📊 RESUMO: {brand_name}
        • Valor Total em Estoque: R$ {total_value:,.2f}
        • Número de Itens em Estoque: {int(total_items)}
        • Média de Preço de Venda: R$ {media_venda:,.2f}
        
        Com base na amostra de dados, separe os produtos em 2 listas diretas:
        🛒 ITENS "MAIS VENDIDOS" / ALTO GIRO (Estoque Baixo)
        - [Nome do Produto]
        
        📦 ITENS DEAD STOCK / MICOS (Estoque Alto parado)
        - [Nome do Produto]
        
        DADOS PARA ANÁLISE: {json.dumps(products_data[:200], default=str)}
        
        [REGRA]: ZERO Markdown (nenhum * ou #). Fiel ao formato acima, sinta-se livre para usar emojis. Nada de enrolação inicial.
        """
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.1)
            )
            return response.text
        except Exception as e:
            return f"❌ Erro na análise de Marca: {str(e)}"

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
            
    def parse_purchase_order_pdf(self, pdf_path: str) -> dict:
        """
        Usa o File API do Gemini para ler um Pedido de Compra em PDF e extrair os DADOS (JSON).
        """
        try:
            uploaded_file = self.client.files.upload(file=pdf_path)
            
            prompt = """
            Você é um sistema extrator de dados de pedidos de compra corporativos. 
            Identifique e extraia do documento anexado os detalhes financeiros do pedido.
            
            Sua saída deve ser EXATAMENTE um objeto JSON válido neste formato:
            {
                "supplier_name": "Nome Limpo da Fábrica (Ex: NIAZITEX)",
                "total_amount": 10412.13,
                "items": [
                    {
                        "product_name": "Nome Completo do Produto",
                        "quantity": 4.0,
                        "unit_price": 84.00
                    }
                ]
            }
            Apenas extraia os valores em números Float ou Inteiros (sem R$). 
            """
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[uploaded_file, prompt],
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    response_mime_type="application/json"
                )
            )
            
            return json.loads(response.text)
        except Exception as e:
            logger.error(f"Erro ao extrair JSON do PDF: {e}")
            return None

    def audit_invoice_vs_order(self, order_data: dict, invoice_data: dict) -> str:
        """
        Inteligência super avançada que compara nota fiscal com pedido e acha fraudes/divergências.
        """
        prompt = f"""
        Você é o ZAR AUDITOR FINANCEIRO. Sua única missão é proteger o dinheiro do seu chefe, Bruno.
        Você verá os dados de um PEDIDO DE COMPRA original e os dados da NOTA FISCAL FATURADA.
        
        Sua missão é realizar o MATCHING (cruzamento) inteligente (pois os nomes podem estar ligeiramente diferentes na NF e no PDF) e encontrar DIVERGÊNCIAS.
        
        PEDIDO DE COMPRA ORIGINAL:
        - Fornecedor: {order_data.get('supplier_name')}
        - Valor Total: R$ {order_data.get('total_amount')}
        - Itens: {json.dumps(order_data.get('items', []), default=str)}
        
        NOTA FISCAL RECEBIDA (FATURADA):
        - Fornecedor: {invoice_data.get('supplier_name')}
        - Valor Total: R$ {invoice_data.get('total_amount')}
        - Itens Faturados: {json.dumps(invoice_data.get('items', []), default=str)}
        
        REGRAS DE AUDITORIA:
        1. Alerte se a quantidade faturada for diferente (faltou entregar algo?).
        2. Alerte MUITO FORTE se o 'unit_price' faturado for MAIOR que o do pedido (aumentaram o preço!).
        3. Fique tranquilo se faltou produto na NF, apenas informe o corte. Mas seja implacável com preço de custo alterado.
        
        Formate seu relatório usando emojis. SE NÃO HOUVER erro (Tudo perfeito), parabenize e diga que a Nota Fiscal bateu 100% centavo por centavo com o PDF do pedido.
        SE HOUVER DIVERGÊNCIA, destaque em bullet points o Produto, Preço no Pedido, Preço na NF e a Diferença cobrada a mais!
        [REGRA DE ESTILO]: Nada de enrolação. SEJA DIRETO! Zero Markdown de formatação pesada (sem asteriscos ou hashtag). 
        """
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.1)
            )
            return response.text
        except Exception as e:
            return f"❌ Erro na Auditoria Cruzada ZAR: {str(e)}"

# agent = ZarAIAgent()
# report = agent.analyze_inventory_health(dados)
