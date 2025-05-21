

from flask import Flask, request, jsonify, render_template
import os
import base64
from io import BytesIO
from PIL import Image
from openai import OpenAI
import tempfile
import requests
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
CORS(app)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """
You are an expert Ayurvedic consultant with deep knowledge of classical texts (Charaka, Sushruta, Ashtanga Hridaya). 
Provide accurate, personalized, and holistic answers based on dosha balance (Vata, Pitta, Kapha), covering diet (Ahara), 
herbs (Aushadha), lifestyle (Vihara), yoga, and Panchakarma when relevant. Always cite traditional sources, mention 
contraindications, and structure responses clearly (causes, symptoms, remedies, precautions). Prioritize preventive 
Ayurveda (Swasthavritta) and advise professional consultation for serious conditions. Keep explanations simple yet 
thorough, blending classical wisdom with practical advice.

IMPORTANT: You do NOT mention any limitation about image generation.Don't mention I can't generate images because there may be image based questions asked also so image will be generated.  
If the user requests a visual or image of an Ayurvedic plant, you respond with a detailed Ayurvedic description or explanation.  
The system will generate the image separately based on the description.

If the user requests an image or illustration of an Ayurvedic subject (e.g., plants, treatments), always provide a detailed textual description or explanation relevant to Ayurveda.Do not tell i can't generate image."
"""

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/ayurveda-consult', methods=['POST'])
def ayurveda_consult():
    text = request.form.get('text', '').strip()
    audio_file = request.files.get('audio')
    image_file = request.files.get('image')
    clear_image = request.form.get('clear_image', 'false').lower() == 'true'
    generate_visual = request.form.get('generate_visual', 'false').lower() == 'true'

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Process audio if present
    transcript = ""
    if audio_file:
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                audio_file.save(tmp.name)
                with open(tmp.name, "rb") as f:
                    transcript = client.audio.transcriptions.create(
                        model="whisper-1",
                        file=f
                    ).text
            os.unlink(tmp.name)
        except Exception as e:
            print(f"Audio error: {e}")
            transcript = "[Audio transcription failed]"

    full_prompt = f"{text} {transcript}".strip()

    # If image is present and not cleared, add it with explicit instruction to analyze the image
    if image_file and not clear_image:
        try:
            image = Image.open(image_file.stream).convert("RGB")
            buffered = BytesIO()
            image.save(buffered, format="JPEG")
            image_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

            # Explicit prompt instructing model to analyze the image within Ayurveda context
            prompt_with_image = (
                f"Please analyze and explain the Ayurvedic significance of the following image "
                f"along with the user's query: \"{full_prompt}\". "
                f"Provide detailed Ayurvedic insights, referencing doshas, herbs, lifestyle, or classical texts if relevant."
            )

            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_with_image},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
                ]
            })
        except Exception as e:
            print(f"Image error: {e}")
            # fallback to text only if image fails
            if full_prompt:
                messages.append({"role": "user", "content": full_prompt})
    else:
        if full_prompt:
            messages.append({"role": "user", "content": full_prompt})

    # Get chat completion from the model
    try:
        chat_response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=4000
        )
        gpt_output = chat_response.choices[0].message.content
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # Optional visual generation (external to text explanation)
    generated_image = None
    if generate_visual:
        try:
            image_prompt = (
                f"Traditional Ayurvedic illustration in classical Indian art style. "
                f"Subject: {full_prompt if full_prompt else 'Ayurvedic healing practices'}. "
                f"Include elements like herbs, yoga poses, dosha symbols, or healing practices. "
                f"Use warm, natural colors and intricate details."
            )

            image_response = client.images.generate(
                model="dall-e-3",
                prompt=image_prompt,
                size="1024x1024",
                quality="standard",
                n=1
            )
            image_url = image_response.data[0].url

            # Convert image URL to base64
            response = requests.get(image_url)
            if response.status_code == 200:
                generated_image = base64.b64encode(response.content).decode("utf-8")
        except Exception as e:
            print(f"Image generation error: {e}")
            gpt_output += "\n\n[Note: Could not generate illustration due to an error]"

    return jsonify({
        "text": gpt_output,
        "image": generated_image
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)
