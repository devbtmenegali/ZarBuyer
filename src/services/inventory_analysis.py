from src.db.supabase_client import get_supabase_client
from datetime import datetime

class InventoryDataService:
    def __init__(self):
        self.supabase = get_supabase_client()

    def get_brand_summary(self, brand: str = None) -> list:
        # Pega de todos os tempos ordenado
        query = self.supabase.table('inventory_snapshots') \
            .select('*, products(sku, name, brand)') \
            .order('snapshot_date', desc=True) \
            .order('stock_balance', desc=True) \
            .limit(300)
            
        resp = query.execute()
        data = resp.data
        
        # Filtra marca e mantém apenas o registro mais novo por produto
        seen = set()
        unique_latest_data = []
        for row in data:
            if not row['products']: continue
            if brand and brand.lower() not in str(row['products'].get('brand', '')).lower(): continue
            
            p_name = row['products']['name']
            if p_name not in seen:
                seen.add(p_name)
                unique_latest_data.append(row)
                if len(unique_latest_data) >= 100: break
            
        simplified = []
        for row in unique_latest_data:
            simplified.append({
                "Nome": row['products']['name'],
                "Marca": row['products']['brand'],
                "Estoque_Qtd": row['stock_balance'],
                "Custo_Total": row['total_cost'],
                "Preco_Venda": row['sale_price']
            })
        return simplified

    def get_highest_stock_items(self) -> list:
        query = self.supabase.table('inventory_snapshots') \
            .select('*, products(name, brand)') \
            .order('snapshot_date', desc=True) \
            .order('total_cost', desc=True) \
            .limit(300)
            
        resp = query.execute()
        
        # Manter apenas a última ocorrência no banco para evitar somar 2 dias do mesmo produto
        seen = set()
        unique_latest_data = []
        for r in resp.data:
            if not r['products']: continue
            p_name = r['products']['name']
            if p_name not in seen:
                seen.add(p_name)
                unique_latest_data.append({
                    "Nome": p_name,
                    "Quantidade": r['stock_balance'],
                    "Valor_Parado": r['total_cost']
                })
                if len(unique_latest_data) >= 50: break
                
        return unique_latest_data

    def get_low_stock_items(self, brand: str = None) -> list:
        # Busca produtos com estoque menor que 5 para alertar reposição
        query = self.supabase.table('inventory_snapshots') \
            .select('*, products(name, brand)') \
            .order('snapshot_date', desc=True) \
            .order('stock_balance', asc=True) \
            .limit(300)
            
        resp = query.execute()
        
        seen = set()
        low_stock_data = []
        for row in resp.data:
            if not row['products']: continue
            if brand and brand.lower() not in str(row['products'].get('brand', '')).lower(): continue
            
            p_name = row['products']['name']
            if p_name not in seen:
                seen.add(p_name)
                # Consider low stock if balance is <= 5
                if float(row['stock_balance']) <= 5:
                    low_stock_data.append({
                        "Nome": p_name,
                        "Marca": row['products']['brand'],
                        "Estoque_Atual": row['stock_balance'],
                        "Custo_Atual": row['cost_price'],
                        "Preco_Venda": row['sale_price']
                    })
                if len(low_stock_data) >= 100: break
                
        return low_stock_data

    def compare_similar_products(self, keyword: str) -> list:
        # Busca produtos com snapshot recente
        query = self.supabase.table('inventory_snapshots') \
            .select('*, products(name, brand)') \
            .order('snapshot_date', desc=True) \
            .limit(1000)
            
        resp = query.execute()
        
        seen = set()
        comparison_data = []
        for row in resp.data:
            if not row['products']: continue
            p_name = str(row['products'].get('name', ''))
            
            # Filtra por keyword no nome (ex: "Travesseiro")
            if keyword.lower() in p_name.lower():
                if p_name not in seen:
                    seen.add(p_name)
                    comparison_data.append({
                        "Nome": p_name,
                        "Marca": row['products'].get('brand', 'N/A'),
                        "Custo": row['cost_price'],
                        "Preco_Venda": row['sale_price'],
                        "Estoque": row['stock_balance']
                    })
                if len(comparison_data) >= 50: break
                
        return comparison_data

    def get_supplier_opportunities(self, brand: str) -> list:
        # Busca os produtos daquela marca ordenados por data
        query = self.supabase.table('inventory_snapshots') \
            .select('*, products(name, brand)') \
            .order('snapshot_date', desc=True) \
            .limit(1000)
            
        resp = query.execute()
        
        seen = set()
        opportunities = []
        for row in resp.data:
            if not row['products']: continue
            p_brand = str(row['products'].get('brand', ''))
            
            if brand.lower() in p_brand.lower():
                p_name = row['products'].get('name', '')
                if p_name not in seen:
                    seen.add(p_name)
                    # Consideramos oportunidade se o estoque for menor/igual a 30 (indicativo de alto giro se já esteve mais alto)
                    if float(row['stock_balance']) <= 30:
                        opportunities.append({
                            "Nome": p_name,
                            "Estoque": row['stock_balance'],
                            "Preco_Venda": row['sale_price']
                        })
                if len(opportunities) >= 20: break
                
        return opportunities
