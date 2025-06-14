import os
import time
import base64
import requests
from io import BytesIO
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import telebot
from telebot import types

# === CONFIGURACIÓN ===
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8043272067:AAGdUtbRpnd-NNaKhcJdJkpWQRyvLT1XKZw")
URL_CONSULTA = "https://mktper.enel.com/app-web-recibo/consulta-tu-recibo"
URL_DESCARGA = "https://mktper.enel.com/app-web-recibo/descargar-recibo"
bot = telebot.TeleBot(TOKEN)
user_data = {}

# === INICIAR SELENIUM HEADLESS ===
def iniciar_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920x1080")
    return webdriver.Chrome(options=options)

# === MENÚ PRINCIPAL ===
@bot.message_handler(commands=["start", "menu"])
def mostrar_menu(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
    markup.add(types.KeyboardButton("🔎 Consultar Recibo"), types.KeyboardButton("ℹ️ Ayuda"))
    bot.send_message(message.chat.id, "👋 Bienvenido al *Bot de Enel Perú*", parse_mode="Markdown")
    bot.send_message(message.chat.id, "Selecciona una opción del menú:", reply_markup=markup)

# === AYUDA ===
@bot.message_handler(func=lambda m: m.text == "ℹ️ Ayuda")
def ayuda(message):
    texto = (
        "🧾 *¿Cómo usar el bot de Enel?*\n\n"
        "1️⃣ Pulsa en '🔎 Consultar Recibo'\n"
        "2️⃣ Ingresa tu número de suministro\n"
        "3️⃣ Ingresa el código CAPTCHA que aparece\n"
        "4️⃣ El bot te enviará tu recibo en PDF\n\n"
        "📬 Si tienes problemas, escribe /start para volver al menú."
    )
    bot.send_message(message.chat.id, texto, parse_mode="Markdown")

# === CONSULTA DE RECIBO ===
@bot.message_handler(func=lambda m: m.text == "🔎 Consultar Recibo")
def solicitar_suministro(message):
    bot.send_message(message.chat.id, "📌 Por favor, escribe tu *número de suministro*:", parse_mode="Markdown")
    bot.register_next_step_handler(message, recibir_suministro)

# === INGRESO DE SUMINISTRO ===
def recibir_suministro(message):
    suministro = message.text.strip()
    if not suministro.isdigit() or len(suministro) < 7:
        bot.send_message(message.chat.id, "⚠️ El número de suministro debe contener solo dígitos y tener al menos 7 caracteres.")
        return

    bot.send_message(message.chat.id, f"🔍 Buscando recibo para suministro *{suministro}*...", parse_mode="Markdown")
    driver = iniciar_driver()
    driver.get(URL_CONSULTA)

    try:
        input_sum = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.NAME, "nroSuministro"))
        )
        input_sum.clear()
        input_sum.send_keys(suministro)
        input_sum.send_keys(Keys.RETURN)
        time.sleep(2)
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Error al ingresar el número de suministro: {e}")
        driver.quit()
        return

    try:
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.NAME, "captcha")))
        captcha_img = driver.find_element(By.XPATH, "//img[contains(@class, 'captcha-image')]")
        src = captcha_img.get_attribute("src")

        if src.startswith("data:image"):
            header, encoded = src.split(",", 1)
            image_data = base64.b64decode(encoded)
        else:
            image_data = requests.get(src).content

        bot.send_photo(message.chat.id, image_data, caption="✍️ Por favor, escribe el código CAPTCHA que aparece:")
        user_data[message.chat.id] = {"driver": driver, "suministro": suministro}
        bot.register_next_step_handler(message, recibir_captcha)
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ No se pudo obtener el CAPTCHA: {e}")
        driver.quit()

# === INGRESO DE CAPTCHA ===
def recibir_captcha(message):
    captcha = message.text.strip()
    session = user_data.get(message.chat.id)

    if not session:
        bot.send_message(message.chat.id, "⚠️ No se encontró una sesión activa. Escribe /start para comenzar de nuevo.")
        return

    driver = session["driver"]
    suministro = session["suministro"]

    try:
        input_captcha = driver.find_element(By.NAME, "captcha")
        input_captcha.clear()
        input_captcha.send_keys(captcha)
        input_captcha.send_keys(Keys.RETURN)
        time.sleep(5)

        form = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//form[contains(@action, 'descargar-recibo')]"))
        )
        id_doc = form.find_element(By.NAME, "idDocumento").get_attribute("value")
        nro_sum = form.find_element(By.NAME, "nroSuministro").get_attribute("value")
        tipo_serv = form.find_element(By.NAME, "tipoServElectrico").get_attribute("value")

        # Transferir cookies a sesión requests
        s = requests.Session()
        for cookie in driver.get_cookies():
            s.cookies.set(cookie['name'], cookie['value'])
        s.headers.update({"User-Agent": "Mozilla/5.0"})

        payload = {
            "idDocumento": id_doc,
            "nroSuministro": nro_sum,
            "tipoServElectrico": tipo_serv
        }

        r = s.post(URL_DESCARGA, data=payload)

        if r.status_code == 200 and "application/pdf" in r.headers.get("Content-Type", ""):
            bot.send_document(message.chat.id, r.content, visible_file_name=f"Recibo_{suministro}.pdf")
            bot.send_message(message.chat.id, "✅ ¡Recibo descargado exitosamente!")
        else:
            bot.send_message(message.chat.id, "❌ No se pudo descargar el recibo. Intenta nuevamente.")
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Error al procesar el CAPTCHA o descargar el recibo: {e}")
    finally:
        driver.quit()
        user_data.pop(message.chat.id, None)

# === INICIO DEL BOT ===
def main():
    print("✅ Bot Enel iniciado. Esperando mensajes...")
    bot.infinity_polling(timeout=60, long_polling_timeout=60)

if __name__ == "__main__":
    main()
