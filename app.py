import os
import google.generativeai as genai
import base64
import json
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from PIL import Image
import io

# --- ИМПОРТ ДЛЯ REPLICATE ---
import replicate
# --- КОНЕЦ ИМПОРТОВ ---

from dotenv import load_dotenv

app = Flask(__name__)
CORS(app) # Разрешает кросс-доменные запросы

load_dotenv() # Загружает переменные окружения из файла .env

# Настройка Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError(
        "GEMINI_API_KEY environment variable not set. Check your .env file."
    )
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash") # Используем 'gemini-1.5-flash'

# --- НАСТРОЙКА REPLICATE API ---
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
if not REPLICATE_API_TOKEN:
    raise ValueError(
        "REPLICATE_API_TOKEN environment variable not set. Check your .env file."
    )
# Replicate API клиент инициализируется автоматически при наличии REPLICATE_API_TOKEN
# в переменных окружения.

# Отрицательный промпт
NEGATIVE_PROMPT_TEXT = (
    "bad anatomy, ugly, deformed, disfigured, blurry, low resolution, "
    "low quality, noise, grainy, monochrome, bad composition, watermark, "
    "signature, text, human, person, body, multiple limbs, extra digits, "
    "shadows, background objects, complex background, text, writing"
)
# --- КОНЕЦ НАСТРОЙКИ REPLICATE ---

# Простая база данных товаров (для MVP)
PRODUCTS_DB = {
    "P101": {
        "name": "Мужская рубашка",
        "type": "рубашка",
        "gender": "мужской",
        "styles": {
            "casual": "светлая голубая в полоску, из хлопка, облегающая",
            "office": "белая классическая, из сатина",
            "party": "черная шелковая, свободного кроя",
        },
        "body_type_advice": {
            "стандартный": "отлично сидит любая посадка",
            "плотный": "рекомендуется прямой крой, вертикальные полоски",
            "атлетический": "подчеркивает фигуру, можно выбрать приталенный крой",
            "худощавый": "прямой крой, не слишком облегающая",
            "полный": "свободный крой, не приталенная",
        },
    },
    "P102": {
        "name": "Мужские брюки",
        "type": "брюки",
        "gender": "мужской",
        "styles": {
            "casual": "светлые джинсы, прямой крой",
            "office": "темно-серые классические, шерстяные",
            "party": "черные зауженные, из кожи",
        },
        "body_type_advice": {
            "стандартный": "любой фасон",
            "плотный": "прямой крой, темные цвета",
            "атлетический": "можно выбрать слегка зауженные, не слишком облегающие",
            "худощавый": "свободный или прямой крой",
            "полный": "классический прямой крой",
        },
    },
    "P103": {
        "name": "Мужской пиджак",
        "type": "пиджак",
        "gender": "мужской",
        "styles": {
            "casual": "льняной, бежевый, без подкладки",
            "office": "темно-синий, шерстяной, классический",
            "party": "бархатный, бордовый, приталенный",
        },
        "body_type_advice": {
            "стандартный": "любой крой",
            "плотный": "однобортный, прямой крой, темные цвета",
            "атлетический": "приталенный, но не сковывающий движения",
            "худощавый": "классический, немного приталенный",
            "полный": "однобортный, не слишком облегающий",
        },
    },
    "F201": {
        "name": "Женское платье",
        "type": "платье",
        "gender": "женский",
        "styles": {
            "casual": "летнее хлопковое, свободного кроя, с цветочным принтом",
            "evening": "черное коктейльное, облегающее, с пайетками",
        },
        "body_type_advice": {
            "стандартный": "любой фасон",
            "плотный": "А-силуэт, темные цвета",
            "атлетический": "подчеркивает талию, но не слишком обтягивает",
            "худощавый": "свободный крой, пышные юбки",
            "полный": "трапеция, вертикальные линии",
        },
    },
}

# --- ИЗМЕНЕННАЯ ФУНКЦИЯ ДЛЯ ГЕНЕРАЦИИ ИЗОБРАЖЕНИЙ (ТЕПЕРЬ ИСПОЛЬЗУЕТ REPLICATE) ---
def generate_image(prompt):
    try:
        # Используем модель Stable Diffusion XL от Stability AI, доступную на Replicate
        # Вы можете найти другие модели на Replicate.com/explore
        output = replicate.run(
            "stability-ai/sdxl:39ed520a238c488d452592ce2d5f0e30d282c3b8e4", # ID модели SDXL
            input={
                "prompt": prompt,
                "negative_prompt": NEGATIVE_PROMPT_TEXT,
                "width": 1024,
                "height": 1024,
                "num_inference_steps": 40,
                "guidance_scale": 8.0,
                "num_outputs": 1,
            }
        )
        # Replicate обычно возвращает список URL-адресов изображений
        if output and len(output) > 0:
            image_url = output[0]
            # Загружаем изображение по URL
            response = requests.get(image_url)
            response.raise_for_status() # Вызывает исключение для плохих статусов (4xx или 5xx)
            image_bytes = response.content
            return base64.b64encode(image_bytes).decode("utf-8")
        return None
    except Exception as e:
        print(f"Error generating image with Replicate AI: {e}")
        return None
# --- КОНЕЦ ИЗМЕНЕННОЙ ФУНКЦИИ ---


def get_gemini_response(prompt_parts, image_data=None):
    try:
        if image_data:
            img_bytes = base64.b64decode(image_data)
            img = Image.open(io.BytesIO(img_bytes))
            contents = [img, *prompt_parts]
            response = model.generate_content(contents)
        else:
            response = model.generate_content(prompt_parts)

        return response.text
    except Exception as e:
        print(f"Error getting Gemini response: {e}")
        return "Не удалось получить ответ от AI."


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json()
        user_message = data.get("message", "").strip()
        user_body_type = data.get("body_type", "стандартный")
        user_image_base64 = data.get("image", None)

        if not user_message and not user_image_base64:
            return (
                jsonify(
                    {
                        "error": "Необходимо ввести текст запроса или загрузить фотографию."
                    }
                ),
                400,
            )

        if not user_message and user_image_base64:
            user_message = "Проанализируй это фото и дай стилистические рекомендации."

        # --- УЛУЧШЕННЫЙ ПРОМПТ ДЛЯ GEMINI (ДЛЯ ФОРМАТИРОВАНИЯ) ---
        gemini_prompt_parts = [
            f"Ты AI стилист StyleSynth. Твоя задача - подбирать одежду и давать стильные советы, учитывая запросы пользователя и тип телосложения '{user_body_type}'. "
            "Отвечай кратко, но информативно. "
            "Если пользователь загрузил фото, сначала **определи пол человека на фото** и **кратко проанализируй общий стиль или основные элементы одежды на этом фото**. Затем, используя этот анализ, **дай рекомендации по одежде, подходящей для определенного пола, из нашей базы данных (`P101`, `P102`, `P103` и `F201` если добавили женскую одежду)**. Объясни, как она дополнит или изменит текущий образ, и как она подходит к телосложению и полу. "
            "Если запрос касается предмета одежды (без фото), просто найди подходящий в нашей базе данных, укажи артикул и **обязательно учти пол, если он указан в запросе, или предложи универсальный вариант/спроси уточнение**. "
            "**Важно: Ответ должен быть максимально структурирован, в формате списка. Для каждого рекомендованного предмета одежды используй формат: "
            " - [Название предмета]: [Краткое описание предмета и его преимущества для фигуры]. Артикул: [Артикул].** "
            "Пример ответа: "
            "На фото (мужчина/женщина) в (краткий анализ стиля/одежды). Отличный выбор! Для вашего (ТипТелосложения) телосложения, рекомендую:"
            " - Мужская рубашка: Светлая голубая в полоску, из хлопка, облегающая, подчеркнет ваш торс. Артикул: P101."
            " - Мужские брюки: Темно-серые классические, шерстяные, создадут строгий образ. Артикул: P102."
            "Если подходящего товара нет в базе данных, так и скажи и предложи поискать что-то другое."
        ]
        # --- КОНЕЦ УЛУЧШЕННОГО ПРОМПТА ---

        gemini_prompt_parts.append(f"Запрос пользователя: '{user_message}'")

        gemini_response_text = get_gemini_response(
            gemini_prompt_parts, user_image_base64
        )

        found_product_id = None
        # Ищем артикул в ответе Gemini
        for pid, product_info in PRODUCTS_DB.items():
            if pid in gemini_response_text:
                found_product_id = pid
                break

        image_data_uri = None
        if found_product_id:
            product = PRODUCTS_DB[found_product_id]
            product_description_for_image = product["styles"].get(
                "casual", product["name"]
            )
            
            image_prompt = (
                f"{product_description_for_image}, "
                f"isolated, on pure white background, no human, no person, "
                f"clean product photography, studio lighting, "
                f"high resolution, photorealistic, best quality, masterwork, "
                f"perfectly cut out, white backdrop, no shadows"
            )

            print(
                f"Attempting to generate image with Replicate AI using prompt: {image_prompt}"
            )
            image_base64_data = generate_image(image_prompt)
            if image_base64_data:
                image_data_uri = f"data:image/png;base64,{image_base64_data}"
                print("Image generation request sent. Data URI returned.")
            else:
                print("Failed to generate image. Check server logs for Replicate AI errors.")
        else:
            print("No product ID found in Gemini response or product not in DB, skipping image generation.")

        return jsonify({"response": gemini_response_text, "image_url": image_data_uri})

    except Exception as e:
        print(f"An error occurred in /chat: {e}")
        return (
            jsonify({"error": f"An internal server error occurred: {str(e)}"}),
            500,
        )


if __name__ == "__main__":
    app.run(debug=True)