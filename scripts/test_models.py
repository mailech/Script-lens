import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("API Key not found")
else:
    genai.configure(api_key=api_key)
    # List of common models to try
    test_models = [
        "gemini-1.5-flash",
        "gemini-1.5-flash-latest",
        "gemini-1.5-flash-8b",
        "gemini-1.5-pro",
        "gemini-pro"
    ]
    
    print("--- Testing Model Availability ---")
    for model_name in test_models:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content("Hi", generation_config={"max_output_tokens": 5})
            print(f"✅ {model_name}: Success! Response: {response.text.strip()}")
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg:
                print(f"❌ {model_name}: 429 Quota Exceeded (Limit 0)")
            elif "404" in err_msg:
                print(f"❌ {model_name}: 404 Not Found")
            else:
                print(f"❌ {model_name}: {err_msg[:100]}...")
