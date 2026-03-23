from src.db.supabase_client import get_supabase_client

class InventoryDataService:
    def __init__(self):
        self.supabase = get_supabase_client()

    def get_brand_summary(self, brand: str = None) -> list:
        """
        Busca os produtos agrupados. Para fins de IA, pegamos 
        uma amostra representativa (os mais caros/com mais estoque) da marca.
        """
        query = self.supabase.table('inventory_snapshots') \
            .select('*, products(sku, name, brand)') \
            .order('stock_balance', desc=True) \
            .limit(100)
            
        resp = query.execute()
        data = resp.data
        
        # Filtra pela marca se fornecida (case insensitive basic)
        if brand:
            data = [d for d in data if d['products'] and brand.lower() in str(d['products'].get('brand', '')).lower()]
            
        # Simplifica o payload para a IA (economizar tokens)
        simplified = []
        for row in data:
            simplified.append({
                "Nome": row['products']['name'],
                "Marca": row['products']['brand'],
                "Estoque_Qtd": row['stock_balance'],
                "Custo_Total": row['total_cost'],
                "Preco_Venda": row['sale_price']
            })
        return simplified

    def get_highest_stock_items(self) -> list:
        """
        Busca os itens com maior custo imobilizado ou quantidade p/ análise de Bundling e Dead Stock.
        """
        query = self.supabase.table('inventory_snapshots') \
            .select('*, products(name, brand)') \
            .order('total_cost', desc=True) \
            .limit(50)
            
        resp = query.execute()
        return [{
            "Nome": r['products']['name'],
            "Quantidade": r['stock_balance'],
            "Valor_Parado": r['total_cost']
        } for r in resp.data]
