from dotenv import load_dotenv
load_dotenv(override=True)
from services.ai_service import CohereService, GroqService, OpenRouterService, GeminiService

providers = [
    ("Cohere", CohereService()),
    ("Groq", GroqService()),
    ("OpenRouter", OpenRouterService()),
    ("Gemini", GeminiService()),
]

print("=" * 60)
print("  Tes Koneksi Multi-Provider AI")
print("=" * 60)

for name, svc in providers:
    r = svc.cek_koneksi()
    status = "[OK]   " if r["ok"] else "[GAGAL]"
    pesan = r["pesan"][:75]
    print(f"{status} {name:12}: {pesan}")

print("=" * 60)
