from flask import Flask, request, jsonify
from openai import OpenAI
from pydantic import BaseModel, ValidationError
from typing import List, Union
import os
import json
import time
import re
# Globala variabler
assistant_id = None
thread_id = None

# Starta Flask
app = Flask(__name__)

# Setup OpenAI
api_key = os.getenv("API_KEY")
api = OpenAI(api_key="")

# System prompt
system_prompt = '''Always return a JSON in this exact format:

{
  "actions": [
    { "name": "move", "parameters": [x, y, z] },
    { "name": "jump", "parameters": [5] },
    { "name": "outputText", "parameters": ["text"] },
    { "name": "rotate", "parameters": [x, y, z] }
  ]
}

Function Definitions:
- move: Takes exactly 3 parameters (x, y, z). The function uses pathfinding to reach the target.
- jump: Takes one parameter, the amount of times the player want to jump
- delay: Takes 1 parameter (duration in seconds).
- rotate: Takes 3 parameters representing a world-space point the player should look at.
- outputText: Takes one string parameter used to provide a response or explanation.
- putOutFire: Takes no parameters. Triggered when the player wants to extinguish a fire.

Behavior Rules:
- All coordinates are in Unreal Engine world space. Z is vertical (up), X and Y define the horizontal plane.
- If no user input is given, return no actions.
- If the user requests multiple actions in a single command, list them in order within the `actions` array.
- If a command includes relative directions (e.g., “walk 3 steps north”), adjust coordinates accordingly.
- Areas with relatively higher Z values can be referred to as "mountains."
- Avoid redundant or purposeless actions (e.g., jumping repeatedly with no context).
- When a command is vague (e.g., “go over there”), use contextual clues such as the nearest tagged object or the player’s current position to infer the destination.
- If objects/components in the environment include tags, use them to infer meaning (e.g., “house”, “door”, “fire”).
- When targeting locations like houses or buildings, choose an accessible and walkable position near or inside (e.g., entry points or open areas). Avoid non-navigable geometry like walls or rooftops unless explicitly asked.
- If an object is tagged as partOfHouse, it might refer to a wall, roof, or other part of the structure. Do not return coordinates on these surfaces. When the user asks to go into or near the house, return coordinates that are walkable and accessible — such as at a doorway or just inside the entrance. Walls and roofs are not valid destinations for movement.
'''

# JSON-format för AI-svaret
class Action(BaseModel):
    name: str
    parameters: List[Union[str, float, int, List[float]]]

class JsonFormat(BaseModel):
    actions: List[Action]



def extract_json(text: str) -> str:
    # Ta ut JSON från eventuella kodblock
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return match.group(0).strip()
    else:
        raise Exception("No JSON object found in Assistant response.")

def get_ai_response(user_input: str, system_add: str) -> dict:
    global assistant_id, thread_id
    if not assistant_id or not thread_id:
        raise Exception("Assistant has not been started.")

    # Lägg till användarens meddelande
    api.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=user_input
    )

    # Starta en körning med extra systeminfo
    run = api.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id,
        additional_instructions=system_add
    )

    # Vänta tills körningen är klar
    while True:
        status = api.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
        if status.status == "completed":
            break
        time.sleep(0.5)

    # Vänta på nytt meddelande från Assistant
    assistant_message = None
    for _ in range(20):  # max ~10 sekunder
        messages = api.beta.threads.messages.list(thread_id=thread_id)
        for msg in messages.data:
            if msg.role == "assistant":
                assistant_message = msg
                break
        if assistant_message:
            break
        time.sleep(0.5)

    if not assistant_message:
        raise Exception("No assistant message found after run completion.")

    content = assistant_message.content[0].text.value

    try:
        json_text = extract_json(content)
        parsed_json = json.loads(json_text)
        validated_json = JsonFormat(**parsed_json)
        return validated_json.dict()
    except (json.JSONDecodeError, ValidationError) as e:
        raise Exception(f"Invalid JSON format from Assistant: {e + json_text}")
    except Exception as e:
        raise Exception(f"Error extracting JSON: {e}")

# Flask-endpoint
@app.route("/ai", methods=["POST"])
def ai_endpoint():
    try:
        data = request.get_json()
        prompt = data.get("prompt", "")
        system_add = data.get("system", "")
        result = get_ai_response(prompt, system_add)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/start", methods=["POST"])
def start_game():
    global assistant_id, thread_id

    try:
        data = request.get_json()
        start_coords = data.get("start_coords", [0, 0, 0])
        extra_instr = data.get("extra_instructions", "")

        # Ta bort gammalt
        if thread_id:
            try:
                api.beta.threads.delete(thread_id=thread_id)
            except:
                pass
        if assistant_id:
            try:
                api.beta.assistants.delete(assistant_id=assistant_id)
            except:
                pass

        # Skapa nya instruktioner
        instructions = f"""{system_prompt}

Startkoordinater: {start_coords}.
{extra_instr}
"""

        # Skapa Assistant
        assistant = api.beta.assistants.create(
            name="Game Memory Assistant",
            instructions=instructions,
            tools=[],
            model="gpt-4.1"  # Obs: den här modellen är troligen bättre!
        )
        assistant_id = assistant.id

        # Skapa Thread
        thread = api.beta.threads.create()
        thread_id = thread.id

        # Bygg actions JSON
        response_json = {
            "actions": [
                {
                    "name": "start_game",
                    "parameters": start_coords
                }
            ]
        }

        return jsonify(response_json)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Kör servern
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
