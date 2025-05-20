# import os
# import base64
# from io import BytesIO
# from PIL import Image
# from dotenv import load_dotenv
# from flask import Flask, render_template, request, send_from_directory, jsonify
# from openai import OpenAI
# import requests
# from werkzeug.utils import secure_filename

# # Setup
# load_dotenv()
# client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# app = Flask(__name__)
# app.config['UPLOAD_FOLDER'] = 'uploads'
# os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# SYSTEM_PROMPT = """<your full Ayurvedic system prompt goes here>"""

# def pil_to_base64(image):
#     buffered = BytesIO()
#     image.save(buffered, format="JPEG")
#     return base64.b64encode(buffered.getvalue()).decode("utf-8")

# def download_image_as_pil(url):
#     try:
#         response = requests.get(url, timeout=10)
#         response.raise_for_status()
#         return Image.open(BytesIO(response.content)).convert("RGB")
#     except Exception as e:
#         print(f"[ERROR] Failed to download image: {e}")
#         return None

# @app.route("/", methods=["GET", "POST"])
# def index():
#     if request.method == "POST":
#         prompt = request.form.get("text", "")
#         generate_visual = request.form.get("generate_visual") == "on"

#         audio_file = request.files.get("audio")
#         image_file = request.files.get("image")

#         # Transcribe audio
#         if audio_file and audio_file.filename:
#             audio_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(audio_file.filename))
#             audio_file.save(audio_path)
#             try:
#                 with open(audio_path, "rb") as f:
#                     transcript = client.audio.transcriptions.create(
#                         model="whisper-1", 
#                         file=f
#                     )
#                 prompt += " " + transcript.text
#             except Exception as e:
#                 print(f"[ERROR] Audio transcription failed: {e}")
#                 prompt += " [Note: Audio transcription failed.]"

#         # Prepare messages
#         messages = [{"role": "system", "content": SYSTEM_PROMPT}]
#         image_obj = None

#         if image_file and image_file.filename:
#             image_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(image_file.filename))
#             image_file.save(image_path)
#             try:
#                 image_obj = Image.open(image_path).convert("RGB")
#                 base64_img = pil_to_base64(image_obj)
#                 messages.append({
#                     "role": "user",
#                     "content": [
#                         {"type": "text", "text": prompt or "Interpret this image as per Ayurveda."},
#                         {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}}
#                     ]
#                 })
#             except Exception as e:
#                 print(f"[ERROR] Image processing failed: {e}")
#         elif prompt.strip():
#             messages.append({"role": "user", "content": prompt.strip()})

#         # Get GPT response
#         try:
#             chat_response = client.chat.completions.create(
#                 model="gpt-4o",
#                 messages=messages,
#                 max_tokens=4000
#             )
#             gpt_output = chat_response.choices[0].message.content
#         except Exception as e:
#             gpt_output = f"[ERROR] GPT response failed: {e}"
#             return render_template("index.html", response=gpt_output)

#         # Generate image
#         generated_img_base64 = None
#         if generate_visual:
#             try:
#                 img_prompt = (
#                     f"Traditional Ayurvedic illustration in classical Indian art style. "
#                     f"Subject: {prompt}. Include herbs, yoga, dosha symbols. Warm natural colors."
#                 )
#                 image_response = client.images.generate(
#                     model="dall-e-3",
#                     prompt=img_prompt,
#                     size="1024x1024",
#                     quality="standard",
#                     n=1
#                 )
#                 image_url = image_response.data[0].url
#                 generated_img = download_image_as_pil(image_url)
#                 if generated_img:
#                     generated_img_base64 = pil_to_base64(generated_img)
#             except Exception as e:
#                 print(f"[ERROR] DALL·E generation failed: {e}")
#                 gpt_output += "\n\n[Note: Image generation failed.]"

#         return render_template("index.html", response=gpt_output, generated_img=generated_img_base64)

#     return render_template("index.html")


# if __name__ == "__main__":
#     app.run(debug=True)

from flask import Flask, request, jsonify,render_template
import os
import base64
from io import BytesIO
from PIL import Image
from openai import OpenAI
import tempfile
import requests
from flask_cors import CORS 
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

IMPORTANT: Do not say you cannot generate images. If the user asks for a visual or illustration, respond as usual with textual explanation. 
The system will generate the image externally based on context. You are not responsible for saying whether image generation is possible.
"""
@app.route('/')
def home():
    return render_template('index.html')
@app.route('/ayurveda-consult', methods=['POST'])
def ayurveda_consult():
    text = request.form.get('text', '')
    audio_file = request.files.get('audio')
    image_file = request.files.get('image')
    generate_visual = request.form.get('generate_visual', 'false').lower() == 'true'
    
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    # Process audio if provided
    transcript = ""
    if audio_file:
        try:
            # Save to temp file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                audio_file.save(tmp.name)
                with open(tmp.name, "rb") as f:
                    transcript = client.audio.transcriptions.create(
                        model="whisper-1", 
                        file=f
                    ).text
            os.unlink(tmp.name)
        except Exception as e:
            print(f"Audio transcription error: {e}")
            transcript = "[Audio transcription failed]"
    
    full_prompt = f"{text} {transcript}".strip()
    
    # Process image if provided
    image_base64 = None
    if image_file:
        try:
            image = Image.open(image_file.stream).convert("RGB")
            buffered = BytesIO()
            image.save(buffered, format="JPEG")
            image_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
            
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": full_prompt or "Interpret this image as per Ayurveda."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
                ]
            })
        except Exception as e:
            print(f"Image processing error: {e}")
            image_base64 = None
    
    if not image_file and full_prompt:
        messages.append({"role": "user", "content": full_prompt})
    
    # Get GPT response
    try:
        chat_response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=4000
        )
        gpt_output = chat_response.choices[0].message.content
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
    # Generate image if requested
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
            
            # Download and convert to base64
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
    app.run(debug=True)