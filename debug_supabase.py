import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

URL = os.getenv("SUPABASE_URL")
KEY = os.getenv("SUPABASE_SERVICE_KEY")
supabase = create_client(URL, KEY)

def testar():
    print("--- DIAGNÓSTICO DE DADOS SUPABASE ---")
    
    # 1. Testa Mercadoria_Grade
    try:
        res = supabase.table("mercadoria_grade").select("*").limit(5).execute()
        print(f"\n[Mercadoria_Grade] Total de linhas retornadas: {len(res.data)}")
        if res.data:
            print("Exemplo de dado (primeira linha):")
            print(res.data[0])
            dados = res.data[0].get('dados', {})
            print(f"Colunas dentro de 'dados': {list(dados.keys())}")
            print(f"Valor de saldo1: {dados.get('saldo1')}")
    except Exception as e:
        print(f"Erro em Mercadoria_Grade: {e}")

    # 2. Testa Mercadoria_Cad
    try:
        res = supabase.table("mercadoria_cad").select("*").limit(5).execute()
        print(f"\n[Mercadoria_Cad] Total de linhas retornadas: {len(res.data)}")
        if res.data:
            dados = res.data[0].get('dados', {})
            print(f"Exemplo de saldo1 em Mercadoria_Cad: {dados.get('saldo1')}")
    except Exception as e:
        print(f"Erro em Mercadoria_Cad: {e}")

if __name__ == "__main__":
    testar()
