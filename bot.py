import os
import base64
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import telebot
from telebot import types

# === CONFIGURACIÓN GENERAL ===
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8043272067:AAGdUtbRpnd-NNaKhcJdJkpWQRyvLT1XKZw")
URL_CONSULTA = "https://mktper.enel.com/app-web-recibo/consulta-tu-recibo"
URL_DESCARGA = "https://mktper.enel.com/app-web-recibo/descargar-recibo"
bot = telebot.TeleBot(TOKEN)
user_data = {}

# === CHROME ULTRA LIGERO ===
def iniciar_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--blink-settings=imagesEnabled=false")
    options.add_argument("user-agent=Mozilla/5.0")
    return webdriver.Chrome(options=options)

# === MENÚ CON COMANDOS RÁPIDOS ===
@bot.message_handler(commands=["start", "menu"])
def mostrar_menu(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🔍 Consultar Recibo", "❓ Ayuda")
    bot.send_message(message.chat.id, "👋 Bienvenido al bot de Enel Perú.", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "❓ Ayuda")
def ayuda(message):
    bot.send_message(message.chat.id,
        "📌 Para usar este bot:\n1️⃣ Pulsa '🔍 Consultar Recibo'\n"
        "2️⃣ Ingresa tu número de suministro\n"
        "3️⃣ Escribe el CAPTCHA\n"
        "4️⃣ ¡Listo! Recibirás tu recibo en PDF.")

@bot.message_handler(func=lambda m: m.text == "🔍 Consultar Recibo")
def solicitar_suministro(message):
    bot.send_message(message.chat.id, "📨 Ingresa tu número de suministro:")
    bot.register_next_step_handler(message, recibir_suministro)

# === CONSULTAR SUMINISTRO ===
def recibir_suministro(message):
    suministro = message.text.strip()
    if not suministro.isdigit():
        return bot.send_message(message.chat.id, "⚠️ Ingresa solo números.")

    bot.send_message(message.chat.id, f"⏱️ Consultando suministro {suministro}...")
    driver = iniciar_driver()
    driver.get(URL_CONSULTA)

    try:
        wait = WebDriverWait(driver, 10, 0.3)
        input_sum = wait.until(EC.presence_of_element_located((By.NAME, "nroSuministro")))
        input_sum.send_keys(suministro, Keys.RETURN)

        wait.until(EC.presence_of_element_located((By.NAME, "captcha")))
        img = driver.find_element(By.XPATH, "//img[contains(@class, 'captcha-image')]")
        src = img.get_attribute("src")

        image_data = base64.b64decode(src.split(",")[1]) if "data:image" in src else requests.get(src).content
        bot.send_photo(message.chat.id, image_data, caption="✍️ Escribe el CAPTCHA que aparece.")
        user_data[message.chat.id] = {"driver": driver, "suministro": suministro}
        bot.register_next_step_handler(message, recibir_captcha)

    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Error: {e}")
        driver.quit()

# === CAPTCHA ===
def recibir_captcha(message):
    captcha = message.text.strip()
    session = user_data.get(message.chat.id)
    if not session:
        return bot.send_message(message.chat.id, "⚠️ Sesión no válida. Escribe /start para reiniciar.")

    driver = session["driver"]
    try:
        driver.find_element(By.NAME, "captcha").send_keys(captcha, Keys.RETURN)

        wait = WebDriverWait(driver, 10, 0.3)
        form = wait.until(EC.presence_of_element_located((By.XPATH, "//form[contains(@action, 'descargar-recibo')]")))

        data = {
            elem.get_attribute("name"): elem.get_attribute("value")
            for elem in form.find_elements(By.TAG_NAME, "input")
        }

        s = requests.Session()
        for c in driver.get_cookies():
            s.cookies.set(c['name'], c['value'])
        r = s.post(URL_DESCARGA, data=data, headers={"User-Agent": "Mozilla/5.0"})

        if r.ok and "application/pdf" in r.headers.get("Content-Type", ""):
            bot.send_document(message.chat.id, r.content, visible_file_name=f"Recibo_{session['suministro']}.pdf")
            bot.send_message(message.chat.id, "✅ Recibo listo.")
        else:
            bot.send_message(message.chat.id, "❌ No se pudo descargar el recibo.")

    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Error: {e}")
    finally:
        driver.quit()
        user_data.pop(message.chat.id, None)

# === EJECUCIÓN ===
def main():
    print("🚀 Bot Enel (modo turbo) iniciado.")
    bot.infinity_polling(timeout=45, long_polling_timeout=45)

if __name__ == "__main__":
    main()
