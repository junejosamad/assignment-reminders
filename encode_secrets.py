"""
encode_secrets.py — run this ONCE locally before pushing to GitHub.
It prints the base64 values you need to paste into GitHub Secrets.
"""
import base64

for filename in ["token.json", "credentials.json"]:
    try:
        with open(filename, "rb") as f:
            encoded = base64.b64encode(f.read()).decode()
        print(f"\n{'='*60}")
        print(f"Secret name: GOOGLE_{filename.replace('.json','').upper().replace('.','_')}_B64")
        print(f"Secret value (copy everything below this line):")
        print(encoded)
    except FileNotFoundError:
        print(f"[!] {filename} not found — make sure you're in the right folder")
