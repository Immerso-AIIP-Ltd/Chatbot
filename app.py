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
import logging
from flask_session import Session
import redis

# Configure logging for better debugging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "supersecretkey")

app.config['SESSION_TYPE'] = 'redis'
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_REDIS'] = redis.from_url(os.getenv("REDIS_URL"))
# redis_url = os.getenv("REDIS_URL")
# if redis_url:
#     app.config['SESSION_REDIS'] = redis.from_url(redis_url)

Session(app)

# Enhanced CORS configuration for Netlify frontend
CORS(app, origins=["*"], supports_credentials=True, 
     allow_headers=["Content-Type", "Authorization"],
     methods=["GET", "POST", "OPTIONS"])

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
    try:
        session['conversation'] = []
        return jsonify({"message": "Conversation reset successfully"})
    except Exception as e:
        logger.error(f"New chat error: {e}")
        return jsonify({"error": "Failed to reset conversation"}), 500

@app.route('/ayurveda-consult', methods=['POST', 'OPTIONS'])
def ayurveda_consult():
    # Handle preflight requests
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    
    try:
        # Enhanced logging for debugging
        logger.info(f"Request method: {request.method}")
        logger.info(f"Content type: {request.content_type}")
        logger.info(f"Form data keys: {list(request.form.keys())}")
        logger.info(f"Files: {list(request.files.keys())}")
        
        text = request.form.get('text', '').strip()
        audio_file = request.files.get('audio')
        image_file = request.files.get('image')
        clear_image = request.form.get('clear_image', 'false').lower() == 'true'
        generate_visual = request.form.get('generate_visual', 'false').lower() == 'true'

        conversation_raw = request.form.get('conversation', '')
        try:
            messages = json.loads(conversation_raw) if conversation_raw else []
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            messages = []

        if not messages or messages[0].get("role") != "system":
            messages.insert(0, {"role": "system", "content": SYSTEM_PROMPT})

        transcript = ""
        if audio_file:
            try:
                logger.info("Processing audio file...")
                # Ensure audio file is valid and readable
                audio_file.seek(0)
                
                # Check file size (Heroku has memory limits)
                audio_file.seek(0, 2)  # Seek to end
                file_size = audio_file.tell()
                audio_file.seek(0)  # Reset to beginning
                
                if file_size > 25 * 1024 * 1024:  # 25MB limit for OpenAI Whisper
                    raise ValueError("Audio file too large")
                
                transcript_response = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="text"
                )
                transcript = transcript_response
                logger.info(f"Audio transcription successful: {len(transcript)} characters")
            except Exception as e:
                logger.error(f"Audio transcription error: {e}")
                transcript = "[Audio transcription failed]"

        full_prompt = f"{text} {transcript}".strip()
        logger.info(f"Full prompt length: {len(full_prompt)}")

        if image_file and not clear_image:
            try:
                logger.info("Processing image file...")
                # Reset file pointer and check file size
                image_file.seek(0, 2)
                file_size = image_file.tell()
                image_file.seek(0)
                
                logger.info(f"Image file size: {file_size} bytes")
                
                # Check file size limit (20MB for safety on Heroku)
                if file_size > 20 * 1024 * 1024:
                    raise ValueError("Image file too large for processing")
                
                # Process image with error handling
                try:
                    image = Image.open(image_file.stream)
                    # Convert to RGB if needed
                    if image.mode != 'RGB':
                        image = image.convert("RGB")
                    
                    # Resize image if too large to save memory
                    max_size = (1024, 1024)
                    image.thumbnail(max_size, Image.Resampling.LANCZOS)
                    
                    buffered = BytesIO()
                    image.save(buffered, format="JPEG", quality=85, optimize=True)
                    image_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
                    
                    logger.info(f"Image processed successfully, base64 length: {len(image_base64)}")
                    
                    messages.append({
                        "role": "user",
                        "content": [
                            {"type": "text", "text": full_prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
                        ]
                    })
                except Exception as img_error:
                    logger.error(f"Image processing error: {img_error}")
                    # Fall back to text-only if image processing fails
                    if full_prompt:
                        messages.append({"role": "user", "content": full_prompt})
                    
            except Exception as e:
                logger.error(f"Image handling error: {e}")
                if full_prompt:
                    messages.append({"role": "user", "content": full_prompt})
        else:
            if full_prompt:
                messages.append({"role": "user", "content": full_prompt})

        # Ensure we have a user message
        if len(messages) <= 1:  # Only system message
            return jsonify({"error": "No user input provided"}), 400

        logger.info(f"Sending {len(messages)} messages to OpenAI")
        
        try:
            chat_response = client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                max_tokens=4000,
                timeout=60  # Add timeout for Heroku
            )
            gpt_output = chat_response.choices[0].message.content
            messages.append({"role": "assistant", "content": gpt_output})
            session['conversation'] = messages
            
            logger.info(f"OpenAI response received, length: {len(gpt_output)}")
            
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return jsonify({"error": f"AI service error: {str(e)}"}), 500

        generated_image = None
        if generate_visual:
            try:
                logger.info("Generating visual...")
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
                    n=1,
                    timeout=120  # Longer timeout for image generation
                )
                image_url = image_response.data[0].url
                
                # Download and encode image with timeout
                response = requests.get(image_url, timeout=60)
                if response.status_code == 200:
                    generated_image = base64.b64encode(response.content).decode("utf-8")
                    logger.info("Image generated successfully")
                else:
                    logger.error(f"Failed to download generated image: {response.status_code}")
                    
            except Exception as e:
                logger.error(f"Image generation error: {e}")
                gpt_output += "\n\n[Note: Could not generate illustration due to an error]"

        response_data = {
            "text": gpt_output,
            "image": generated_image,
            "conversation": messages
        }
        
        logger.info("Request completed successfully")
        return jsonify(response_data)

    except Exception as e:
        logger.error(f"General error in ayurveda_consult: {e}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500

# Add a health check endpoint
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "message": "API is running"}), 200

# Error handlers
@app.errorhandler(413)
def too_large(e):
    return jsonify({"error": "File too large"}), 413

@app.errorhandler(500)
def internal_error(e):
    return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
