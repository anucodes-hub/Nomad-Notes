from tools.geo_tool import confidence_score, heritage_lookup, reverse_geocode
from tools.history_tool import fetch_history
from google import genai
from google.genai import types
import os
import json

class LocationAgent:
    async def execute(self, state):
        request = state.get("request")
        location = await self.run(request)
        state.set("location", location)
        return state

    async def run(self, payload):
        lat = payload["lat"]
        lng = payload["lng"]
        geo = await reverse_geocode(lat, lng)
        heritage = await heritage_lookup(lat, lng)
        place_name = heritage["place"]
        
        # Token-Efficient Contextual Scoping
        # We append just the state and country to disambiguate without wasting tokens on full coordinates
        state = geo.get("state", "")
        country = geo.get("country", "")
        qualified_place_name = f"{place_name}, {state}, {country}".strip(', ')
        
        # Agentic RAG Router
        api_key = os.getenv("GOOGLE_API_KEY")
        client = genai.Client(api_key=api_key) if api_key else genai.Client()
            
        config = types.GenerateContentConfig(response_mime_type="application/json")
        router_prompt = (
            f"Do you have deep, accurate historical knowledge about '{qualified_place_name}'? "
            f"If it is a famous landmark, respond with 'is_famous': true and provide a 'context' and a list of 'facts'. "
            f"If it is obscure, respond with 'is_famous': false. "
            f"Return JSON strictly with keys: 'is_famous' (boolean), 'context' (string), 'facts' (list of strings)."
        )
        
        try:
            creds = os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
            response = await client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=router_prompt,
                config=config
            )
            if creds is not None:
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds
                
            router_decision = json.loads(response.text)
        except Exception as e:
            print(f"LocationAgent Gemini Router failed: {type(e).__name__} - {e}")
            router_decision = {"is_famous": False}
            
        if router_decision.get("is_famous"):
            print(f"Agentic Router: Skipping Wikipedia, using internal LLM memory for {qualified_place_name}")
            history = {
                "context": router_decision.get("context", f"{qualified_place_name} History"),
                "facts": router_decision.get("facts", [])
            }
        else:
            print(f"Agentic Router: Place obscure, falling back to Wikipedia for {qualified_place_name}")
            history = await fetch_history(qualified_place_name)
            
        conf = await confidence_score(heritage["distance_km"])

        return {
            "place": heritage["place"],
            "confidence": conf,
            "distance_km": heritage["distance_km"],
            "geo": geo,
            "period": heritage["period"],
            "themes": heritage["themes"],
            "summary": heritage["summary"],
            "historical_context": history["context"],
            "facts": history["facts"],
        }

