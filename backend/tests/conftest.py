import os

# Run every test in demo mode, so no test ever calls the real Gemini API.
# This must be set before the app modules are imported.
os.environ["MOCK_LLM"] = "1"
os.environ.pop("GEMINI_API_KEY", None)
