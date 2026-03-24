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
        self.model_name = "gemini-2.5-flash"  # Modelo rápido e barato para anális
    def _get_style_guide(self) -> str:
        return """
[GUIA DE ESTILO VISUAL ZAR - OBRIGATÓRIO]:
1. Títulos: Use emojis e negrito (ex: 💎 *TÍTULO*) na primeira linha.
2. Divisores: Use a linha '━━━━━━━━━━━━━━━━━━━━' para separar seções.
3. Bullets: Use 🔹 ou 🔸 para itens de lista.
4. Espaçamento: Use sempre UMA LINHA EM BRANCO entre blocos de informação para não amontoar.
5. Markdown: Use *negrito* para valores em R$ e nomes de produtos.
6. Tom: Profundo, executivo e focado em lucro/estratégia.
"""

    def analyze_inventory_health(self, products_data: list) -> str:
        """
        Gera relatórios sobre dead stock, sugestões de queima e bundling
        com base nos dados crus do banco.
        """
        total_items = sum([float(p.get("Estoque_Qtd", p.get("Quantidade", 0))) for p in products_data])
        total_value = sum([float(p.get("Custo_Total", p.get("Valor_Parado", 0))) for p in products_data])
        
        prompt = f"""
Você é o ZAR Agent. {self._get_style_guide()}

Sua tarefa: Gerar Diagnóstico de Saúde de Estoque:
1. "Micos" (Dead Stock): Produtos parados que precisam de desconto agressivo.
2. Combos (Bundling): Una o que não vende com o que voa da prateleira.
3. Alertas Imprevistos: Algum SKU com custo subindo demais ou margem sumindo.

[RESUMO FINANCEIRO]:
- Total Itens: {int(total_items)}
- Valor Parado: R$ {total_value:,.2f}

DADOS DE ESTOQUE:
{json.dumps(products_data[:100], default=str)}

Gere o relatório seguindo o GUIA DE ESTILO acima.
"""

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.3)
            )
            return response.text
        except Exception as e:
            logger.error(f"Erro ao chamar o Gemini: {e}")
            return f"❌ Erro na inteligência ZAR: {str(e)}"
            
    def analyze_brand_summary(self, products_data: list, brand: str) -> str:
        total_items = sum([float(p.get("Estoque_Qtd", p.get("Quantidade", 0))) for p in products_data])
        total_value = sum([float(p.get("Custo_Total", p.get("Valor_Parado", 0))) for p in products_data])
        
        precos = [float(p.get("Preco_Venda", 0)) for p in products_data if float(p.get("Preco_Venda", 0)) > 0]
        media_venda = sum(precos) / len(precos) if precos else 0
        brand_name = (brand or "Geral").upper()
        
        prompt = f"""
Você é o ZAR Agent. {self._get_style_guide()}

Resuma a marca *{brand_name}* com foco em performance:
- Mostre o Valor Total e Qtd de Itens.
- Liste os 3 MAIS VENDIDOS (Giro Alto).
- Liste os 3 PIORES (Micos).

DADOS: {json.dumps(products_data[:100], default=str)}

Siga RIGOROSAMENTE o GUIA DE ESTILO para um visual limpo e premium.
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
        prompt = f"""
Você é o ZAR Agent na mesa de negociação. {self._get_style_guide()}

Analise esta proposta de custo:
- Custo Proposto: R$ {proposed_cost}
- Venda Atual: R$ {selling_price}
- Margem Alvo: {current_margin}%

Dê o veredito rápido: Aceitar, Recusar ou Reprecificar?
Siga o estilo visual LIMPO (com divisores).
"""
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.1)
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
Você é o ZAR Agent. {self._get_style_guide()}

Sugira um PEDIDO DE COMPRA para a marca *{brand_name}* focando apenas no crítico (Risco de Ruptura).
- Liste SKU, Preço de Custo e Qtd Sugerida.
- Use emojis 🚨 para itens zerados.

DADOS: {json.dumps(custom_data[:100], default=str)}

Siga o estilo visual PREMIUM (Divisores e Espaçamento).
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
Você é o ZAR Agent. {self._get_style_guide()}

Analise a comparação de produtos para o termo *{keyword}*.
- Identifique quem está caro ou barato demais.
- Sugira ajustes de Markup.
- Use emojis ⚖️ para comparações.

DADOS: {json.dumps(custom_data, default=str)}

Siga o padrão visual PREMIUM e limpo.
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
Você é o Diretor de Compras do ZAR. {self._get_style_guide()}

Escreva um PITCH para o representante da *{brand}* via WhatsApp.
- Use nossa performance de giro como alavanca de negociação.
- Peça desconto para lote fechado.
- Seja direto, profissional e use emojis 🤝💵.

DADOS DE SUCESSO: {json.dumps(custom_data, default=str)}

Gere a mensagem pronta para copiar, respeitando o espaçamento clean.
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
Você é o CFO do ZAR. {self._get_style_guide()}

Gere o RELATÓRIO DE FLUXO DE CAIXA (Boletos das NFes).
- Mostre os picos de pagamento na semana.
- Alerte sobre boletos pesados.
- Dê um insight sobre alongar prazo ou antecipar.

PAGAMENTOS PENDENTES:
{json.dumps(payables, indent=2, ensure_ascii=False)}

Mantenha o visual CLEAN e EXECUTIVO. Use divisores.
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
Você é o Diretor de Supply Chain do ZAR. {self._get_style_guide()} {self._get_seasonality_context()}

Gere o DIAGNÓSTICO DE GIRO DE ESTOQUE para *{brand}*.
- Mostre os DIAS DE COBERTURA (quem acaba primeiro).
- Indique quem vende como água (Curva A).
- Revele os "Micos" parados (999 dias).

DADOS:
{json.dumps(data, indent=2, ensure_ascii=False)}

Foque no visual ORGANIZADO (Use divisores e emojis táticos).
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
Você é o Pricing Manager do ZAR. {self._get_style_guide()}

Gere a AUDITORIA DE INFLAÇÃO E REPRECIFICAÇÃO para *{brand}*.
- Liste itens onde o custo na NF veio maior que o custo em estoque.
- Sugira o *Preço novo* para proteger a margem.
- Dê o veredito: manter ou descontinuar o produto.

DADOS DE INFLAÇÃO:
{json.dumps(data, indent=2, ensure_ascii=False)}

Gere o relatório em blocos bem separados e destacados.
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
Você é o ZAR Jurídico. {self._get_style_guide()}

Escreva uma CARTA DE PROTESTO DE FATURA para a NFe *{invoice_num}*.
- Reclame das faltas e avarias citadas.
- Exija desconto/abatimento.
- Deixe campos [ ] para preenchimento.

DIVERGÊNCIAS:
{divergences}

Gere o documento seguindo o visual ORGANIZADO (Use divisores).
"""
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
