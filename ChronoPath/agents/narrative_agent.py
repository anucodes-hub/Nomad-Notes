import os
import asyncio
from google import genai

class NarrativeAgent:
    async def execute(self, state):
        context = state.get("context")
        narrative = await self.run(context)
        state.set("story", narrative)
        return state

    async def run(self, context):
        place = context["place"]
        era = context["context"]
        language = context["language"]
        interests = context.get("interests", [])
        age = context.get("age")
        origin = context.get("origin")
        background = context.get("background")
        name = context.get("name")
        visited = context.get("visited_places", [])
        
        recent_place = visited[0].get("name") if visited and isinstance(visited[0], dict) and "name" in visited[0] else (visited[0] if visited else None)

        prompt = (
            f"You are Chrono, a friendly, soft-toned, and immensely knowledgeable AI travel buddy. "
            f"Write a detailed, comprehensive, and highly engaging 8-10 sentence historical explanation for a user standing near {place}. "
            f"The historical context is {era}. "
            f"Ensure you discuss both the deep history of {place} and how it has evolved over the years to its present state. "
            f"The user is interested in: {', '.join(interests) if interests else 'general history'}. "
        )
        
        if name:
            if recent_place:
                prompt += f"Start the narrative with a highly personalized, conversational greeting using the user's name ({name}). For example, 'Hey {name}, you know this place has a significance like you saw in the previous case {recent_place}.' "
            else:
                prompt += f"Start the narrative with a warm, conversational greeting using the user's name ({name}). For example, 'Hey {name}, welcome to {place}!' "
        else:
            prompt += f"Start the narrative with a warm, friendly greeting as Chrono. "
        
        if age:
            prompt += f"The user is {age} years old; adapt the reading level, tone, and analogies appropriately for this age. "
        if origin:
            prompt += f"The user is originally from {origin}; draw deeply relatable historical parallels between {place} and the history of {origin}. "
        if background:
            prompt += f"The user's background/profession is '{background}'; emphasize historical aspects, architecture, or events that align with this background. "

        feedback_score = context.get("feedback_score", 0)
        if feedback_score < 0:
            prompt += f"Note: The user has generally disliked your previous stories (score: {feedback_score}). Try to be more engaging, concise, and accurate in this generation to win back their approval. "
        elif feedback_score > 0:
            prompt += f"Note: The user has generally liked your previous stories (score: {feedback_score}). Keep up the great storytelling style! "

            
        feedback = context.get("feedback")
        if feedback:
            prompt += f"\n\nCRITICAL FEEDBACK FROM REVIEWER: Your previous draft was rejected. You MUST fix these issues in this rewrite:\n{feedback}\n\n"

        prompt += f"Make the story vivid, educational, and immersive. Write it in {language}."
        
        try:
            api_key = os.getenv("GOOGLE_API_KEY")
            # We can configure transport if needed, but client handles HTTP default now.
            client = genai.Client(api_key=api_key) if api_key else genai.Client()
            
            # Temporary hack: google-genai may automatically grab GOOGLE_APPLICATION_CREDENTIALS 
            # and ignore the API key. We must temporarily hide it during generation.
            creds = os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
            
            try:
                loop = asyncio.get_running_loop()
                # Run sync generate_content via executor to not block, preserving existing behavior
                response = await loop.run_in_executor(
                    None, 
                    lambda: client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
                )
                story = response.text
            finally:
                if creds is not None:
                    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds
                    
        except Exception as e:
            print(f"Narrative generation failed: {type(e).__name__} - {e}")
            story = f"Welcome to {place}. This location holds deep historical significance from the {era}."

        return {
            "story": story.strip(),
            "facts": context.get("facts", []),
            "language": language,
        }
