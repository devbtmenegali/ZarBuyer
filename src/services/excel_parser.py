import pandas as pd
import logging

logger = logging.getLogger(__name__)

class ExcelInventoryParser:
    def __init__(self, filepath: str):
        self.filepath = filepath

    def parse_daily_inventory(self):
        """
        Lê a planilha de Estoque Geral e retorna uma lista de dicionários
        mapeados para a estrutura do banco de dados (ZAR).
        """
        try:
            # Pular possíveis linhas em branco do gerador de relatório
            # A planilha tem um cabeçalho nas primeiras linhas e as colunas começam mais abaixo
            # Descobrimos que "Cód. Mercadoria" é a primeira chave a procurar
            df = pd.read_excel(self.filepath, header=None)
            
            # Encontra a linha de cabeçalho onde tem "Cód. Mercadoria"
            header_row_index = None
            for i in range(min(20, len(df))):
                row_values = df.iloc[i].values
                if any("Cód. Mercadoria" in str(val) for val in row_values):
                    header_row_index = i
                    break
            
            if header_row_index is None:
                raise ValueError("Cabeçalho 'Cód. Mercadoria' não encontrado.")

            # Lê os dados reais a partir do cabeçalho
            df = pd.read_excel(self.filepath, header=header_row_index)
            
            # Limpa colunas indesejadas e vazias
            df.columns = df.columns.astype(str).str.strip()
            # Descobri na sua planilha que o Cód Mercadoria às vezes vem vazio, então filtramos pela Descrição
            if 'Descrição Mercadoria' in df.columns:
                df = df.dropna(subset=['Descrição Mercadoria'])
            else:
                df = df.dropna(subset=['Cód. Mercadoria'])
            
            # Converte e padroniza para um formato estruturado
            parsed_data = []
            for _, row in df.iterrows():
                try:
                    sku_val = str(row.get('Cód. Mercadoria', '')).strip()
                    name_val = str(row.get('Descrição Mercadoria', '')).strip()
                    if sku_val == "" or sku_val.lower() == "nan":
                        sku_val = name_val # Fallback para o nome se não tiver código
                    
                    product_data = {
                        "sku": sku_val,
                        "name": name_val,
                        "unit": str(row.get('UN', '')).strip(),
                        "reference": str(row.get('Referência', '')).strip(),
                        "brand": str(row.get('Marca Descriçao', '')).strip(),
                        "sale_price": float(row.get('Preço Venda', 0) or 0),
                        "cost_price": float(row.get('Preço Custo', 0) or 0),
                        "stock_balance": float(row.get('Saldo Estoque', 0) or 0),
                        "total_cost": float(row.get('Total Custo', 0) or 0),
                    }
                    if product_data["sku"] and product_data["sku"] != "nan":
                        parsed_data.append(product_data)
                except Exception as e:
                    logger.warning(f"Erro ao processar a linha: {row}. Erro: {e}")
                    
            return parsed_data
            
        except Exception as e:
            logger.error(f"Erro fatal ao ler o Excel: {e}")
            raise e

# Uso Exemplo:
# parser = ExcelInventoryParser('caminho/do/arquivo.xlsx')
# dados = parser.parse_daily_inventory()
