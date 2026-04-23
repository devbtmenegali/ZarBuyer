import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

URL = os.getenv("SUPABASE_URL")
KEY = os.getenv("SUPABASE_SERVICE_KEY")
supabase = create_client(URL, KEY)

def totalizar():
    print("--- RELATÓRIO DE SAÚDE DOS DADOS (SUPABASE) ---")
    
    # 1. Contagem Total de Mercadorias
    try:
        res = supabase.table("mercadoria_cad").select("id", count="exact").execute()
        total = res.count
        print(f"Total de itens em Mercadoria_Cad: {total}")
    except: pass

    # 2. Contagem de Itens com Saldo > 0
    # Como não podemos filtrar fácil no Supabase em colunas JSON, vamos puxar uma amostra maior
    try:
        res = supabase.table("mercadoria_grade").select("dados").limit(1000).execute()
        itens = [r['dados'] for r in res.data]
        com_saldo = [i for i in itens if float(i.get('saldo1', '0')) > 0]
        print(f"Na amostra de 1000 da GRADE, {len(com_saldo)} tem saldo > 0.")
        if com_saldo:
            print(f"Exemplo de item com saldo: {com_saldo[0].get('cod_mercadoria')} - Saldo: {com_saldo[0].get('saldo1')}")
    except Exception as e:
        print(f"Erro na contagem de grade: {e}")

    # 3. Teste de busca por nome (Bella Janela)
    print("\nTestando busca por 'Bella Janela' no cadastro...")
    try:
        res = supabase.table("mercadoria_cad").select("dados").limit(2000).execute()
        encontrados = [r['dados'] for r in res.data if "BELLA" in str(r['dados'].get('descricao', '')).upper()]
        print(f"Encontramos {len(encontrados)} produtos Bella Janela nos primeiros 2000 itens.")
    except: pass

if __name__ == "__main__":
    totalizar()
