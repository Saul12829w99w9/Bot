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

# === Configuración general ===
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8043272067:AAGdUtbRpnd-NNaKhcJdJkpWQRyvLT1XKZw")
URL_CONSULTA = "https://mktper.enel.com/app-web-recibo/consulta-tu-recibo"
URL_DESCARGA = "https://mktper.enel.com/app-web-recibo/descargar-recibo"
bot = telebot.TeleBot(TOKEN)
user_data = {}

# === Función para iniciar Selenium ===
def iniciar_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(options=options)

# === /start ===
@bot.message_handler(commands=["start"])
def start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton("🔎 Consultar Recibo")
    btn2 = types.KeyboardButton("ℹ️ Ayuda")
    markup.add(btn1, btn2)
    bot.send_message(message.chat.id, "👋 Bienvenido al Bot de Enel Perú\nElige una opción:", reply_markup=markup)

# === Ayuda ===
@bot.message_handler(func=lambda m: m.text == "ℹ️ Ayuda")
def ayuda(message):
    texto = (
        "📄 Este bot te permite consultar y descargar tu recibo de Enel Perú.\n"
        "1. Pulsa '🔎 Consultar Recibo'\n"
        "2. Escribe tu número de suministro\n"
        "3. Ingresa el CAPTCHA que aparece\n"
        "✅ ¡Y recibirás tu recibo en PDF!"
    )
    bot.send_message(message.chat.id, texto)

# === Consultar Recibo ===
@bot.message_handler(func=lambda m: m.text == "🔎 Consultar Recibo")
def solicitar_suministro(message):
    bot.send_message(message.chat.id, "✍️ Por favor, ingresa tu número de suministro:")
    bot.register_next_step_handler(message, recibir_suministro)

# === Ingreso de suministro ===
def recibir_suministro(message):
    suministro = message.text.strip()
    if not suministro.isdigit():
        bot.send_message(message.chat.id, "⚠️ Número inválido. Solo números.")
        return

    bot.send_message(message.chat.id, f"🔎 Buscando recibo para suministro: {suministro}...")
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
    except:
        bot.send_message(message.chat.id, "❌ No se pudo ingresar el número de suministro.")
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

        bot.send_photo(message.chat.id, image_data, caption="✍️ Ingresa el código CAPTCHA que aparece:")
        user_data[message.chat.id] = {"driver": driver, "suministro": suministro}
        bot.register_next_step_handler(message, recibir_captcha)
    except:
        bot.send_message(message.chat.id, "❌ Error al obtener el CAPTCHA.")
        driver.quit()

# === Ingreso de CAPTCHA ===
def recibir_captcha(message):
    captcha = message.text.strip()
    session = user_data.get(message.chat.id)
    if not session:
        bot.send_message(message.chat.id, "⚠️ Sesión no encontrada. Escribe /start para comenzar de nuevo.")
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

        # Copiar cookies desde Selenium a requests
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
            bot.send_message(message.chat.id, "✅ Aquí está tu recibo.")
        else:
            bot.send_message(message.chat.id, "❌ No se pudo descargar el recibo.")
    except:
        bot.send_message(message.chat.id, "⚠️ Error al validar el CAPTCHA o descargar el recibo.")
    finally:
        driver.quit()
        user_data.pop(message.chat.id, None)

# === Inicio del bot ===
def main():
    print("🤖 Bot Enel iniciado correctamente.")
    bot.infinity_polling()

if __name__ == "__main__":
    main()
