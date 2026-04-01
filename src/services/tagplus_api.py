import os
import requests

class TagPlusAPI:
    BASE_URL = "https://api.tagplus.com.br"
    
    def __init__(self, token=None):
        self.token = token or os.environ.get("TAGPLUS_ACCESS_TOKEN", "NJQ1U7Gquw9lpJv3zctLkzTJbwk6HZz5")
        if not self.token:
            raise ValueError("TagPlus Access Token is required.")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "X-Api-Version": "2.0"
        }

    def get_products(self):
        url = f"{self.BASE_URL}/produtos"
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching products: {e}")
            if e.response is not None:
                print(f"Response status: {e.response.status_code}")
                print(f"Response body: {e.response.text}")
            return None

if __name__ == "__main__":
    import sys
    token = "NJQ1U7Gquw9lpJv3zctLkzTJbwk6HZz5"
    api = TagPlusAPI(token=token)
    
    print("Fetching products from TagPlus...")
    products = api.get_products()
    
    if products is not None:
        if isinstance(products, list):
            print(f"Successfully fetched {len(products)} products.")
            for p in products:
                print(f"- [{p.get('id')}] {p.get('descricao')} | R$ {p.get('valor_venda_padrao', 'N/A')}")
        else:
            print("Received unexpected JSON structure:")
            print(products)
    else:
        sys.exit(1)
