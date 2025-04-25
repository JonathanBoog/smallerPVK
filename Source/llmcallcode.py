from flask import Flask, request, jsonify
from openai import OpenAI
from pydantic import BaseModel
from typing import List, Union
import os

# Starta Flask
app = Flask(__name__)

# Setup OpenAI
api_key = os.getenv("API_KEY")
api = OpenAI(api_key="")

# System prompt
system_prompt = '''Translate necessary parameters for the functions and return in given format.,  
the move to location function is called move with parameters x,y,z, DET SKA ALLTID FINNAS tre parameterar "
positivt Z är uppåt
to make the character jump, jump har inga parametrar.
delay : en parameter (i sekunder)
outputText: en parameter, det som finns ska vara som eventuellt SVAR på fråga som användaren har. Det kan vara frågor om beräkningar också då du eventuellt kommer behöva läsa av miljön för att beräkningarna

om spelaren ber om att få göra saker i rad. varje del ska finnas i actions listan
x=1 innebär i princip en 1 cm 
om jag säger att jag vill gå x antal steg i en viss riktning, då ska ju du såklart öka koordinat värdena
om användaren inte anger något -> inga actions
'''

# JSON-format för AI-svaret
class Action(BaseModel):
    name: str
    parameters: List[Union[str, float, int, List[float]]]

class JsonFormat(BaseModel):
    actions: List[Action]

# Funktion för att få AI-respons
def get_ai_response(user_input: str, sys_inp: str) -> str:
    full_prompt = sys_inp + system_prompt
    completion = api.beta.chat.completions.parse(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": full_prompt},
            {"role": "user", "content": user_input}
        ],
        response_format=JsonFormat,
    )
    return completion.choices[0].message.content

# Flask-endpoint
@app.route("/ai", methods=["POST"])
def ai_endpoint():
    try:
        data = request.get_json()
        prompt = data.get("prompt", "")
        system_add = data.get("system", "")
        result = get_ai_response(prompt, system_add)
        return result
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Kör servern
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
