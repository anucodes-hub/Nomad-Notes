import os
import json
import asyncio
from google import genai

class NearbyAgent:
    async def execute(self, state):
        location = state.get("location")
        context = state.get("context")
        
        nearby_places = await self.run(location, context)
        state.set("nearby_places", nearby_places)
        return state

    async def run(self, location, context):
        if not location or not context:
            return []
            
        place_name = location.get("place", "Unknown location")
        
        # Extract lat/lng which are nested inside the 'geo' object returned by LocationAgent
        geo = location.get("geo", {})
        lat = geo.get("lat", "Unknown")
        lng = geo.get("lng", "Unknown")
        city = geo.get("city", "")
        state = geo.get("state", "")
        country = geo.get("country", "")
        
        qualified_place = f"{place_name}, {city}, {state}, {country}".strip(", ")
        
        interests = context.get("interests", [])
        age = context.get("age", "Unknown")
        background = context.get("background", "General Explorer")
        
        prompt = (
            f"You are a helpful travel assistant. The user is currently at {qualified_place} (Coordinates: {lat}, {lng}). "
            f"Based on their interests ({', '.join(interests) if interests else 'general exploration'}), age ({age}), and background ({background}), "
            f"suggest 4-5 of the most visited and famous historical spots or popular food spots nearby. "
            f"Return ONLY a valid JSON array. Each object in the array MUST have the following keys: "
            f"'name' (string, name of the place), "
            f"'distance' (string, estimated walking or driving distance, e.g., '5 mins walk'), "
            f"'description' (string, a short one-sentence engaging description tailored to the user), "
            f"'maps_url' (string, a Google Maps directions URL, e.g., 'https://www.google.com/maps/dir/?api=1&destination=ENCODED_PLACE_NAME_OR_LAT_LNG'). "
            f"Do NOT include markdown formatting like ```json or any other text. Output strictly the JSON array."
        )

        try:
            api_key = os.getenv("GOOGLE_API_KEY")
            client = genai.Client(api_key=api_key) if api_key else genai.Client()
            
            creds = os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
            
            try:
                loop = asyncio.get_running_loop()
                response = await loop.run_in_executor(
                    None, 
                    lambda: client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
                )
                text = response.text.strip()
                if text.startswith("```json"):
                    text = text.replace("```json", "", 1)
                if text.endswith("```"):
                    text = text[:-3]
                
                places = json.loads(text.strip())
                return places
            finally:
                if creds is not None:
                    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds
                    
        except Exception as e:
            print(f"Nearby places generation failed: {type(e).__name__} - {e}")
            return []
