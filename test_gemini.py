from google import genai
import os

print("Key length:", len(os.environ.get("GEMINI_API_KEY", "")))

client = genai.Client()
try:
    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents="Say hi in one word."
    )
    print("Full response object:", response)
    print("Response text:", response.text)
except Exception as e:
    print("ERROR TYPE:", type(e).__name__)
    print("ERROR MESSAGE:", e)

