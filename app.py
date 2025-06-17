import os
import google.generativeai as genai
import replicate
import requests
from PIL import Image
from io import BytesIO
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv

# Импортируем необходимые классы из Flask-SQLAlchemy
from flask_sqlalchemy import SQLAlchemy

load_dotenv()

app = Flask(__name__)
CORS(app) # Enable CORS for all routes

# --- Database Configuration (НОВАЯ ЧАСТЬ) ---
# Получаем URL базы данных из переменных окружения Render.com
# Для локальной разработки, используем .env, для Render - напрямую из переменных окружения
app.config['postgresql://stylesynth_db_user:J9ENRI4k3tWz9PXdMx5xQ2rkfSlC3yfC@dpg-d18stijuibrs73e142p0-a.singapore-postgres.render.com/stylesynth_db'] = os.environ.get('DATABASE_URL') or "YOUR_POSTGRES_EXTERNAL_DATABASE_URL"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False # Отключаем, чтобы избежать предупреждений

# Инициализируем SQLAlchemy
db = SQLAlchemy(app)

# Определяем модель данных для пользователя (НОВАЯ ЧАСТЬ)
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    # Отношение к предметам гардероба
    wardrobe_items = db.relationship('WardrobeItem', backref='owner', lazy=True)

    def __repr__(self):
        return '<User %r>' % self.username

# Определяем модель данных для предмета гардероба (НОВАЯ ЧАСТЬ)
class WardrobeItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    image_url = db.Column(db.String(255), nullable=False) # URL для хранения изображения (например, на облачном хранилище)
    category = db.Column(db.String(50), nullable=True) # Рубашка, брюки, платье
    color = db.Column(db.String(50), nullable=True)    # Красный, синий, и т.д.
    style = db.Column(db.String(50), nullable=True)     # Повседневный, деловой, вечерний
    # Дополнительные поля могут быть добавлены позже

    def __repr__(self):
        return '<WardrobeItem %r>' % self.image_url


# --- Existing API Key Setup (проверьте, что они есть в Render Environment Variables) ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

if not GEMINI_API_KEY:
    raise ValueError(
        "GEMINI_API_KEY environment variable not set. Check your .env file or Render.com settings."
    )
if not REPLICATE_API_TOKEN:
    raise ValueError(
        "REPLICATE_API_TOKEN environment variable not set. Check your .env file or Render.com settings."
    )

genai.configure(api_key=GEMINI_API_KEY)
# Настройка Replicate API (если требуется, обычно он работает через os.environ.get)
# os.environ["REPLICATE_API_TOKEN"] = REPLICATE_API_TOKEN


# Функция для анализа изображения с помощью Gemini Pro Vision
def analyze_image_with_gemini(image_data):
    try:
        model = genai.GenerativeModel('gemini-pro-vision')
        # Отправляем изображение и запрос модели
        response = model.generate_content([
            "Analyze this image of clothing. Identify the type of garment (e.g., shirt, pants, dress, shoe, jacket), its primary color(s), and its general style (e.g., casual, formal, sporty, elegant). "
            "Return the answer as a JSON object with keys: 'category', 'colors', 'style'. "
            "Example: {'category': 'dress', 'colors': ['blue', 'white'], 'style': 'summer casual'}.",
            image_data
        ])
        # Парсим ответ, ожидая JSON
        try:
            return response.text.strip().replace("```json", "").replace("```", "").strip()
        except ValueError:
            return response.text.strip() # Возвращаем текст, если не удалось распарсить JSON
    except Exception as e:
        print(f"Error analyzing image with Gemini: {e}")
        return None

# Функция для анализа селфи пользователя для определения цвета кожи/тона внешности
def analyze_user_appearance(image_data):
    try:
        model = genai.GenerativeModel('gemini-pro-vision')
        response = model.generate_content([
            "Analyze this portrait image of a person. Identify their primary skin tone (e.g., fair, light, medium, dark), and describe their overall appearance tone (e.g., warm, cool, neutral). "
            "Return the answer as a JSON object with keys: 'skin_tone', 'appearance_tone'. "
            "Example: {'skin_tone': 'light', 'appearance_tone': 'cool'}.",
            image_data
        ])
        try:
            return response.text.strip().replace("```json", "").replace("```", "").strip()
        except ValueError:
            return response.text.strip()
    except Exception as e:
        print(f"Error analyzing user appearance with Gemini: {e}")
        return None


# Функция для генерации изображения одежды (Используем Replicate)
def generate_clothing_image(prompt):
    # Здесь используется та же модель, что и ранее, но можно экспериментировать
    # Убедитесь, что эта модель доступна и имеет соответствующий API токен
    output = replicate.run(
        "stability-ai/stable-diffusion:ac732df830a8c0147c2eed5740b2f7667232142477c8ce6d2aca4e79ae402766",
        input={"prompt": prompt}
    )
    if output and isinstance(output, list) and len(output) > 0:
        return output[0]  # Возвращаем URL сгенерированного изображения
    return None

# --- NEW ROUTES FOR DATABASE AND WARDROBE (НОВЫЕ РОУТЫ) ---

@app.route('/create_db')
def create_db_tables():
    """Создает таблицы в базе данных. Вызывать ОДИН раз после деплоя."""
    try:
        with app.app_context(): # Используем app_context для работы с БД
            db.create_all()
        return "Database tables created successfully!"
    except Exception as e:
        return f"Error creating database tables: {e}", 500

@app.route('/api/user/add', methods=['POST'])
def add_user():
    data = request.json
    username = data.get('username')
    if not username:
        return jsonify({"error": "Username is required"}), 400

    try:
        with app.app_context():
            new_user = User(username=username)
            db.session.add(new_user)
            db.session.commit()
            return jsonify({"message": "User added successfully", "user_id": new_user.id}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/wardrobe/add/<int:user_id>', methods=['POST'])
def add_wardrobe_item(user_id):
    if 'image' not in request.files:
        return jsonify({"error": "No image part in the request"}), 400
    file = request.files['image']
    if file.filename == '':
        return jsonify({"error": "No selected image"}), 400

    # Здесь нужно реализовать загрузку изображения на облачное хранилище (например, Cloudinary, AWS S3)
    # Для простоты примера, мы пока просто "анализируем" и предполагаем URL
    # В реальном приложении:
    # 1. Загружаем file на облачное хранилище
    # 2. Получаем public_url
    # image_url_from_cloud = "https://example.com/your_uploaded_image.jpg" # ЗАМЕНИТЕ НА РЕАЛЬНЫЙ URL

    # Пока что для теста: считываем изображение для анализа
    image_data = Image.open(BytesIO(file.read()))

    # Анализ изображения одежды с помощью Gemini
    analysis_result = analyze_image_with_gemini(image_data)
    
    if analysis_result:
        try:
            parsed_analysis = json.loads(analysis_result) # Парсим JSON
            category = parsed_analysis.get('category')
            color = ','.join(parsed_analysis.get('colors', [])) # Преобразуем список в строку
            style = parsed_analysis.get('style')
        except json.JSONDecodeError:
            category = "unknown"
            color = "unknown"
            style = "unknown"
            print(f"Warning: Gemini analysis not in expected JSON format: {analysis_result}")
    else:
        category = "unknown"
        color = "unknown"
        style = "unknown"

    # !!! В реальном приложении тут будет URL загруженного изображения !!!
    # Пока что заглушка:
    mock_image_url = f"https://placehold.co/600x400/png?text=Item_{user_id}_{file.filename}"

    try:
        with app.app_context():
            user = User.query.get(user_id)
            if not user:
                return jsonify({"error": "User not found"}), 404

            new_item = WardrobeItem(
                user_id=user_id,
                image_url=mock_image_url, # Замените на реальный URL с облака!
                category=category,
                color=color,
                style=style
            )
            db.session.add(new_item)
            db.session.commit()
            return jsonify({
                "message": "Wardrobe item added successfully",
                "item_id": new_item.id,
                "analysis": parsed_analysis # Отправляем клиенту, чтобы он видел
            }), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/wardrobe/list/<int:user_id>', methods=['GET'])
def list_wardrobe_items(user_id):
    try:
        with app.app_context():
            user = User.query.get(user_id)
            if not user:
                return jsonify({"error": "User not found"}), 404
            
            items = WardrobeItem.query.filter_by(user_id=user_id).all()
            items_data = [{
                "id": item.id,
                "image_url": item.image_url,
                "category": item.category,
                "color": item.color,
                "style": item.style
            } for item in items]
            return jsonify({"user_id": user_id, "wardrobe": items_data}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/outfit/suggest/<int:user_id>', methods=['POST'])
def suggest_outfit(user_id):
    # Этот роут будет самой сложной частью
    data = request.json
    event = data.get('event', 'casual') # Тип мероприятия
    user_appearance_info = data.get('user_appearance_info', {}) # Например, цвет кожи, если анализировали селфи

    try:
        with app.app_context():
            user = User.query.get(user_id)
            if not user:
                return jsonify({"error": "User not found"}), 404
            
            # Получаем все вещи пользователя из БД
            user_wardrobe = WardrobeItem.query.filter_by(user_id=user_id).all()
            if not user_wardrobe:
                return jsonify({"message": "No items in wardrobe to suggest an outfit."}), 200

            # --- Логика AI для составления образа (Здесь потребуется много работы!) ---
            # Это ОЧЕНЬ упрощенный пример. Реальная логика будет сложнее.
            # 1. Подготовить промпт для Gemini, используя данные о гардеробе, событии и пользователе.
            # 2. Вызвать Gemini, чтобы он предложил комбинации.
            # 3. Вернуть предложенные комбинации.

            wardrobe_description = ""
            for item in user_wardrobe:
                wardrobe_description += f"- {item.category} ({item.color}, {item.style})\n"
            
            # Расширенный промпт для Gemini
            gemini_prompt = (
                f"You are a professional fashion stylist. A user wants an outfit for a '{event}' event. "
                f"Their wardrobe contains the following items:\n{wardrobe_description}\n"
                f"User's appearance: {user_appearance_info.get('skin_tone', 'unknown')} skin tone, {user_appearance_info.get('appearance_tone', 'unknown')} tone. "
                "Suggest 2-3 complete outfit combinations using ONLY items from this wardrobe. "
                "For each outfit, list the specific items (e.g., 'blue jeans', 'white t-shirt') and explain why it's a good choice for the event and user's appearance. "
                "Present the outfits as a list of dictionaries, where each dictionary has 'outfit_name', 'items' (list of strings), and 'reason'."
                "Example: "
                "[\n"
                "  {\n"
                "    \"outfit_name\": \"Classic Evening\",\n"
                "    \"items\": [\"black dress\", \"silver heels\"],\n"
                "    \"reason\": \"Elegant and timeless for an evening event.\"\n"
                "  },\n"
                "  {\n"
                "    \"outfit_name\": \"Casual Day Out\",\n"
                "    \"items\": [\"blue jeans\", \"white t-shirt\", \"sneakers\"],\n"
                "    \"reason\": \"Comfortable and stylish for a relaxed day.\"\n"
                "  }\n"
                "]"
            )

            model = genai.GenerativeModel('gemini-pro') # Используем Gemini Pro для текстового анализа
            gemini_response = model.generate_content(gemini_prompt)
            
            try:
                suggested_outfits = json.loads(gemini_response.text.strip().replace("```json", "").replace("```", "").strip())
            except json.JSONDecodeError:
                suggested_outfits = [{"error": "Could not parse Gemini's outfit suggestions. Raw response: " + gemini_response.text}]

            return jsonify({"user_id": user_id, "suggested_outfits": suggested_outfits}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- Existing /generate route (МОЖЕТЕ ОСТАВИТЬ ИЛИ УДАЛИТЬ ПО ЖЕЛАНИЮ) ---
@app.route('/generate', methods=['POST'])
def generate_image():
    data = request.json
    prompt = data.get('prompt')

    if not prompt:
        return jsonify({"error": "Prompt is required"}), 400

    # Вызываем функцию генерации изображения
    image_url = generate_clothing_image(prompt)

    if image_url:
        return jsonify({"image_url": image_url}), 200
    else:
        return jsonify({"error": "Failed to generate image"}), 500

# --- Existing
if __name__ == "__main__":
    app.run(debug=True)