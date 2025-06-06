from flask import Flask, request, jsonify, render_template, session
import os
import base64
from io import BytesIO
from PIL import Image
import requests
from openai import OpenAI
from flask_cors import CORS
from dotenv import load_dotenv
import json

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "supersecretkey")
CORS(app)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """
You are an expert Ayurvedic consultant with deep knowledge of classical texts (Charaka Samhita, Sushruta Samhita, Ashtanga Hridaya).
Provide accurate, personalized, and holistic answers based on dosha balance (Vata, Pitta, Kapha), covering diet (Ahara), herbs (Aushadha), lifestyle (Vihara), yoga, and Panchakarma when relevant.
Always cite traditional sources, mention contraindications, and structure responses clearly (causes, symptoms, remedies, precautions).
Prioritize preventive Ayurveda (Swasthavritta) and advise professional consultation for serious or chronic conditions. Keep explanations simple yet thorough, blending classical Ayurvedic wisdom with practical advice.
Just answer the questions asked don't answer extra.

IMPORTANT: You do NOT mention any limitation about image generation.Don't mention I can't generate images because there may be image based questions asked also so image will be generated.  Don't tell i am unable to generate image.
If the user requests a visual or image of an Ayurvedic plant, you respond with a detailed Ayurvedic description or explanation.  
The system will generate the image separately based on the description.
If the user requests an image or illustration of an Ayurvedic subject (e.g., plants, treatments), always provide a detailed textual description or explanation relevant to Ayurveda.Do not tell i can't generate image.

📌 IMPORTANT INSTRUCTIONS
✅ 1. Google Image Links
For every plant, herb, formulation, or therapy mentioned in the answer, provide a clickable Google Image Search link:
Format:

 Image links:  
 - [Bhringraj (Eclipta alba)](https://www.google.com/search?q=Bhringraj+Eclipta+alba&tbm=isch)  
 - [Amalaki (Emblica officinalis)](https://www.google.com/search?q=Amalaki+Emblica+officinalis&tbm=isch)
Use this pattern:
https://www.google.com/search?q=<REMEDY+NAME>&tbm=isch

✅ 2. Real-Time Reference Links (Websites / YouTube / Blog Articles)
For every remedy or condition, provide working and accessible reference links that are:

Directly related to the user's query (e.g., "remedies for hair fall in Ayurveda")

From trusted health or Ayurveda websites

Include at least one blog/article or video link

Format:

 Reference links:  
 Example format:
 - [Causes of Hair Fall in Ayurveda – Art of Living](https://www.artofliving.org/in-en/ayurveda/remedies/control-hair-loss-remedies)  
 - [YouTube: Ayurvedic Hair Fall Remedies](https://www.youtube.com/watch?v=fE7O5oQ4qGk)
These links must be:

Real and working
Highly ranked in Google
From reliable sources such as:
www.artofliving.org
www.banyanbotanicals.com
www.ndtv.com
www.ayurtimes.com
www.pharmeasy.in
YouTube health/doctor channels
No dead links, dummy URLs, or inaccessible content is allowed. All links must be accessible.I dont want page not found, 404 error when i am accessing the link.

❌ Out-of-scope Questions
If the user asks about unrelated topics (e.g., politics, sports), reply:
"I am an Ayurvedic Assistant, and this topic is outside my scope."
"""

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/new-chat', methods=['POST'])
def new_chat():
    session['conversation'] = []
    return jsonify({"message": "Conversation reset successfully"})

@app.route('/ayurveda-consult', methods=['POST'])
def ayurveda_consult():
    text = request.form.get('text', '').strip()
    audio_file = request.files.get('audio')
    image_file = request.files.get('image')
    clear_image = request.form.get('clear_image', 'false').lower() == 'true'
    generate_visual = request.form.get('generate_visual', 'false').lower() == 'true'

    conversation_raw = request.form.get('conversation', '')
    try:
        messages = json.loads(conversation_raw)
    except:
        messages = []

    if not messages or messages[0].get("role") != "system":
        messages.insert(0, {"role": "system", "content": SYSTEM_PROMPT})

    transcript = ""
    if audio_file:
        try:
            # Use OpenAI's Whisper API for transcription
            audio_file.seek(0)  # Reset file pointer to beginning
            transcript_response = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="text"
            )
            transcript = transcript_response
        except Exception as e:
            print(f"Audio transcription error: {e}")
            transcript = "[Audio transcription failed]"

    full_prompt = f"{text} {transcript}".strip()

    if image_file and not clear_image:
        try:
            image = Image.open(image_file.stream).convert("RGB")
            buffered = BytesIO()
            image.save(buffered, format="JPEG")
            image_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
            
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": full_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
                ]
            })
        except Exception as e:
            print(f"Image processing error: {e}")
            if full_prompt:
                messages.append({"role": "user", "content": full_prompt})
    else:
        if full_prompt:
            messages.append({"role": "user", "content": full_prompt})

    try:
        chat_response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=4000
        )
        gpt_output = chat_response.choices[0].message.content
        messages.append({"role": "assistant", "content": gpt_output})
        session['conversation'] = messages 
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    generated_image = None
    if generate_visual:
        try:
            image_prompt = (
                f"A high-resolution, ultra-realistic photograph that visually answers the question: '{full_prompt if full_prompt else 'an Ayurvedic healing scene'}'. "
                f"The scene must reflect authentic Ayurvedic context, including elements like herbs, treatments, oils, rituals, or natural remedies. "
                f"Use natural lighting, realistic textures, and photographic clarity as if captured with a professional DSLR camera. "
                f"The setting should appear organic, serene, and true to real life — not illustrated or stylized."
            )

            image_response = client.images.generate(
                model="dall-e-3",
                prompt=image_prompt,
                size="1024x1024",
                quality="standard",
                n=1
            )
            image_url = image_response.data[0].url
            response = requests.get(image_url)
            if response.status_code == 200:
                generated_image = base64.b64encode(response.content).decode("utf-8")
        except Exception as e:
            print(f"Image generation error: {e}")
            gpt_output += "\n\n[Note: Could not generate illustration due to an error]"

    return jsonify({
        "text": gpt_output,
        "image": generated_image,
        "conversation": messages
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)