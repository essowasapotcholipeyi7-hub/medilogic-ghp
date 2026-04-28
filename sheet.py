import base64, json

with open("credentials.json", "r") as f:
    creds_data = json.load(f)
    encoded = base64.b64encode(json.dumps(creds_data).encode()).decode()
    print("COPIEZ LE TEXTE SUIVANT :")
    print(encoded)