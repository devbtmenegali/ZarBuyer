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

    def audit_invoice_vs_order(self, order_data: dict, invoice_data: dict) -> dict:
        """
        Inteligência que compara nota com pedido, acha divergências e devolve DADOS para atualizar o saldo no banco de dados.
        """
        prompt = f"""
        Você é o ZAR AUDITOR LOGÍSTICO.
        Sua missão é realizar o MATCHING (cruzamento) inteligente (pois os nomes variam) entre pedido e faturamento.
        
        PEDIDO DE COMPRA ORIGINAL:
        - Fornecedor: {order_data.get('supplier_name')}
        - Itens (Nome e Qtd Pedida): {json.dumps(order_data.get('items', []), default=str)}
        
        NOTA FISCAL RECEBIDA:
        - Itens Faturados (Nome e Qtd Entregue agora): {json.dumps(invoice_data.get('items', []), default=str)}
        
        Sua saída deve ser EXATAMENTE um JSON válido neste formato (sem Markdown):
        {{
            "report_text": "Seu relatório executivo para o Telegram em português, indicando Micos de Preço (Aumentos!), Itens faltantes e sucesso. Use Emojis bonitos. Quebre linha com \\n",
            "matched_items": [
                {{
                    "order_item_name": "Nome EXATO como consta no JSON de 'PEDIDO DE COMPRA ORIGINAL' que está sendo dado baixa com esta NF",
                    "quantity_received_now": 4.0
                }}
            ],
            "is_order_completed": false
        }}
        
        Defina is_order_completed como true apenas se todos os itens do pedido original tiverem sido faturados na mesma quantidade ou mais.
        """
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    response_mime_type="application/json"
                )
            )
            return json.loads(response.text)
        except Exception as e:
            logger.error(f"Erro na auditoria JSON: {e}")
            return None

    def analyze_purchase_recommendations(self, custom_data: list, brand: str) -> str:
        brand_name = (brand or "Geral")
        prompt = f"""
        Você é o ZAR, sugerindo um Pedido de Compra Urgente.
        Recebemos produtos da marca/categoria {brand_name} com ESTOQUE BAIXO ou ZERADO.
        
        Sua tarefa:
        1. Liste os itens críticos a serem repostos.
        2. Dê uma sugestão de quantidade a comprar (pense em pelo menos 10 ou 20 por item dependendo do ticket).
        3. Formate com clareza usando emojis de alerta 🚨.
        
        Seja super conciso. Zero papo furado. Não avise que é uma simulação.

        DADOS:
        {json.dumps(custom_data[:100], default=str)}
        """
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.2)
            )
            return response.text
        except Exception as e:
            return f"❌ Erro ZAR ao prever compras: {str(e)}"

    def analyze_product_comparison(self, custom_data: list, keyword: str) -> str:
        prompt = f"""
        Você é o ZAR. Analise os preços e margens de produtos similares do tipo '{keyword}'.
        
        Sua tarefa:
        1. Identifique discrepâncias de preços (produtos similares com preços muito diferentes).
        2. Destaque se há algum produto "canibalizando" o outro (ex: um produto melhor custando o mesmo que um inferior, ou margens espremidas).
        3. Dê uma sugestão de reajuste de preço (Reprecificação Dinâmica) se aplicável.
        
        Seja super conciso. Use bullet points e emojis. Recomende a ação a ser tomada.
        
        DADOS DE COMPARAÇÃO:
        {json.dumps(custom_data, default=str)}
        """
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.2)
            )
            return response.text
        except Exception as e:
            return f"❌ Erro ZAR ao comparar produtos: {str(e)}"

    def generate_supplier_pitch(self, custom_data: list, brand: str) -> str:
        prompt = f"""
        Você é o ZAR, diretor logístico e de compras.
        Escreva uma mensagem comercial persuasiva (um "Pitch") direcionada ao representante da marca '{brand}'.
        O objetivo é usar nosso ALTO GIRO dos produtos listados abaixo para negociar um lote maior com desconto expressivo.
        
        Sua tarefa:
        1. Crie uma mensagem pronta para ser enviada por WhatsApp (formal mas direta, com emojis moderados).
        2. Destaque o sucesso de giro dos itens listados (que estão com pouco estoque).
        3. Peça uma proposta de preço agressiva para reposição de lote fechado.
        
        DADOS DE OPORTUNIDADE:
        {json.dumps(custom_data, default=str)}
        """
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.4)
            )
            return response.text
        except Exception as e:
            return f"❌ Erro ZAR ao gerar pitch: {str(e)}"

    def analyze_cash_flow(self, payables: list) -> str:
        import json
        prompt = f"""
Você atua como o Diretor Financeiro (CFO) do ZAR Agent.
As notas fiscais enviadas recentemente geraram as seguintes parcelas a pagar:
{json.dumps(payables, indent=2, ensure_ascii=False)}

Gere um sumário executivo focado no Fluxo de Caixa:
1. Quanto teremos que desembolsar em breve? Destaque as maiores concentrações de valores por Data de Vencimento.
2. Quais Fornecedores têm a maior fatia à pagar?
3. Otimização Financeira: Em um curto Insight, informe se caberia renegociar os próximos pedidos focando em prazo alongado de pagamento (para aliviar os picos de desembolso) ou pagamento antecipado (se o caixa estiver folgado em certas semanas).

Regras de Estilo:
Use bullets diretos, não use Markdown exagerado e use um tom cirúrgico.
"""
        from google import genai
        from google.genai import types
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.3)
            )
            return response.text
        except Exception as e:
            return f"❌ Erro na análise de caixa: {str(e)}"

    def analyze_turnover(self, data: list, brand: str) -> str:
        import json
        prompt = f"""
Você é o ZAR Agent, Diretor de Supply Chain. {self._get_seasonality_context()}

Analise este relatório de GIRO DE ESTOQUE (Sales Velocity) da fábrica '{brand}'.
Os produtos estão ordenados por "Dias_Cobertura" (os primeiros vão zerar antes).
Dados Reais:
{json.dumps(data, indent=2, ensure_ascii=False)}

Gere um diagnóstico em bullets destacando:
1. Risco Iminente: Quais produtos vão acabar nos próximos 15 dias (Risco de ruptura)?
2. Curvas A viciadas: Quais produtos vendem rápido (Venda_Dia alta) e precisam de mais volume por pedido de reposição?
3. Tranqueiras (Dead Stock): Destaque (se houver) algum produto com giro nulo (999 dias de cobertura) para o Dono olhar.

Não force formatação excessiva (use emojis controlados) e dê um tom autoritário e logístico.
"""
        from google import genai
        from google.genai import types
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.4)
            )
            return response.text
        except Exception as e:
            return f"❌ falha ZAR no giro: {str(e)}"

    def analyze_repricing(self, data: list, brand: str) -> str:
        import json
        prompt = f"""
Você atua como o Diretor de Pricing (Pricing Manager) do ZAR Agent.
Analise a INFLAÇÃO DE CUSTO (Divergência NFe vs Estoque) da fábrica '{brand}'.
Os itens abaixo chegaram na última Nota Fiscal mais CAROS do que nosso Custo Base Estocado.
Dados Reais de Inflação:
{json.dumps(data, indent=2, ensure_ascii=False)}

Gere um diagnóstico focado em Remarcação de Preços (Reprecificação):
1. Destaque os itens com o maior choque de inflação no custo.
2. Alerte a equipe sobre o "Novo_Preco_Sugerido" para ser aplicado imediatamente nas etiquetas da loja, de modo a não perdermos o markup (a margem bruta) sobre o custo de reposição atualizado.
3. Decisão Drástica: Informe se o custo inflou tanto (ex: acima de 15%) que talvez seria melhor nós pararmos de comprar esse SKU ao invés de aumentar tanto o preço final.

Regras de Estilo:
Use bullets diretos, emojis controlados 📉💰 e seja taxativo.
"""
        from google import genai
        from google.genai import types
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.3)
            )
            return response.text
        except Exception as e:
            return f"❌ Erro ZAR em pricing: {str(e)}"

    def generate_chargeback(self, invoice_num: str, divergences: str) -> str:
        from datetime import datetime
        hj = datetime.now().strftime("%d/%m/%Y")
        prompt = f"""
Você é o Assistente Jurídico/Logístico (ZAR Chargeback) de uma grande empresa de Varejo.
Recebemos hoje ({hj}) a Nota Fiscal de número {invoice_num}, mas após nossa auditoria de recebimento cruzando com o XML, detectamos graves falhas/faltas de envio comparado ao nosso Pedido Original.

Faltas / Divergências Encontradas:
{divergences}

Escreva uma "CARTA DE COBRANÇA E PROTESTO DE FATURA" formal, contundente, pronta para o dono da loja dar CTRL+C e mandar no WhatsApp ou Email do representante da fábrica.
Regras:
1. Exija abatimento imediato no valor do respectivo boleto/duplicata da nota.
2. Formalize que a mercadoria chegou avariada ou faltando.
3. Seja incisivo, use tom jurídico/comercial, e gere os campos em branco (como "[Nome do Fornecedor]") para o dono preencher.
"""
        from google import genai
        from google.genai import types
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.2)
            )
            return response.text
        except Exception as e:
            return f"❌ Falha ao emitir chargeback: {str(e)}"
            
    def _get_seasonality_context(self) -> str:
        from datetime import datetime
        return f"\n[CONTEXTO TEMPORAL/SAZONALIDADE] Hoje é {datetime.now().strftime('%d/%m/%Y')}. Como IA de inteligência de compras, analise a proximidade de datas comemorativas cruciais do Varejo (Dia das Mães, Dia dos Namorados, Inverno, Black Friday, Natal) e avise caso os números do estoque atual apresentem riscos pro futuro próximo."

    def extract_user_intent(self, text: str, user_role: str) -> dict:
        import json
        prompt = f"""
Você é o roteador neurolinguístico (NLP Router) do ZAR Agent.
Analise a seguinte mensagem enviada por um '{user_role}' (admin ou supplier) pelo WhatsApp/Telegram da empresa e extraia de forma pragmática a INTENÇÃO e a MARCA/NOME FÁBRICA.

Mensagem Escrita Pelo Usuário: "{text}"

As intenções base mapeiam para as seguintes funções internas do nosso ERP:
- "analisar": Análise geral de portfólio da marca (Ranking 80/20, Estoque, etc).
- "micos": Produtos parados, sobras de estoque (Dead Stock / Clearence).
- "pendencias": Pedidos de compra que atrasaram ou não foram faturados.
- "negociar": Sugestão ou alerta sobre necessidades de compras / ruptura.
- "comparar": Compara produtos similares (Ex: Travesseiros, Edredons) entre si.
- "comprar": Emissão oficial de pedidos novos para as fábricas.
- "cotar": Anota e precifica cotações rápidas passadas por vendedores de fora.
- "caixa": Avalia os boletos e próximos desembolsos do caixa (Faturas financeiras).
- "giro": Quando o usuário quer saber dias de cobertura, velocidade de saída, ritmo de vendas.
- "reprecificar": Alerta de inflação nas compras ou cálculo de alteração nos preços de venda.
- "chargeback": Devolver mercadoria com avaria, faltantes ou emitir termo de desconto/multa a fábrica.
- "docas": Transporte logístico, agendamento de pátio, carreta, transportadora.

Se a frase é apenas falação normal de chat sem intenção comercial: "chat_normal"

Responda ÚNICA e EXCLUSIVAMENTE com um objeto JSON válido.
Formato:
{{
  "intent": "um dos 12 modulos descritos acima, ou chat_normal",
  "brand": "O nome da marca citada (se citado). Ex: Karsten, Appel, Altenburg",
  "args": "Se for chargeback, ponha o número da NF se vir. Se for doca, ponha nome da transportadora. Senao, deixe vazio"
}}
"""
        from google import genai
        from google.genai import types
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.0)
            )
            raw = response.text.strip()
            if raw.startswith("```json"):
                raw = raw[7:-3]
            elif raw.startswith("```"):
                raw = raw[3:-3]
            return json.loads(raw.strip())
        except Exception as e:
            return {"intent": "chat_normal", "brand": None, "args": None}
