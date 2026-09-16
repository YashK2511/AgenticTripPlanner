import os
from dotenv import load_dotenv
from app.agents.profile_agent import extract_profile

load_dotenv()

def test_extraction():
    if not os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_API_KEY") == "your_google_api_key_here":
        print("Please set GOOGLE_API_KEY in the .env file to run the Gemini-based profile extraction test.")
        return

    request = "I want to plan a family trip to Goa for 4 days starting next month on the 10th. We are 2 adults (male and female) and 1 senior (female, needs wheelchair assistance). Our budget is 1,50,000 INR. We love beaches, seafood, and historic Portuguese churches. Please keep daily travel under 2 hours."

    print("Sending Request to Gemini:", request)
    profile = extract_profile(request)
    print("\nResult Extracted by Gemini:")
    print(profile.model_dump_json(indent=2))

if __name__ == "__main__":
    test_extraction()
