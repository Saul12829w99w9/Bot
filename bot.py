import os
import time
import base64
import requests
import threading
from io import BytesIO
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import telebot
from telebot import types
import tkinter as tk
from tkinter import ttk

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

# === GUI ===
class BotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Bot Enel - Monitoreo")
        self.root.geometry("400x400")
        self.root.resizable(False, False)

        self.estado_var = tk.StringVar(value="⏳ Iniciando bot...")
        self.lista_usuarios = tk.Listbox(self.root, height=10)

        ttk.Label(root, text="Estado del bot:").pack(pady=5)
        ttk.Label(root, textvariable=self.estado_var, foreground="blue").pack()

        ttk.Label(root, text="Chats activos:").pack(pady=5)
        self.lista_usuarios.pack(fill=tk.BOTH, expand=True, padx=10)

        self.boton_salir = ttk.Button(root, text="🛑 Detener bot", command=self.salir)
        self.boton_salir.pack(pady=10)

    def actualizar_estado(self, mensaje):
        self.estado_var.set(mensaje)

    def agregar_chat(self, chat_id):
        if str(chat_id) not in self.lista_usuarios.get(0, tk.END):
            self.lista_usuarios.insert(tk.END, str(chat_id))

    def eliminar_chat(self, chat_id):
        for i in range(self.lista_usuarios.size()):
            if self.lista_usuarios.get(i) == str(chat_id):
                self.lista_usuarios.delete(i)
                break

    def salir(self):
        self.actualizar_estado("⛔ Cerrando bot...")
        os._exit(0)

# === GUI thread ===
root = tk.Tk()
gui = BotGUI(root)

def iniciar_gui():
    root.mainloop()

gui_thread = threading.Thread(target=iniciar_gui)
gui_thread.daemon = True
gui_thread.start()

# === Limpieza de sesiones ===
def limpiar_sesiones_expiradas():
    while True:
        ahora = datetime.now()
        expirados = [cid for cid, d in user_data.items()
                     if (ahora - d["timestamp"]).seconds > 300]
        for cid in expirados:
            try:
                d = user_data.pop(cid)
                d["driver"].quit()
                gui.eliminar_chat(cid)
            except:
                pass
        time.sleep(60)

threading.Thread(target=limpiar_sesiones_expiradas, daemon=True).start()

# === /start ===
@bot.message_handler(commands=["start"])
def start(message):
    gui.actualizar_estado("📨 Nuevo usuario")
    gui.agregar_chat(message.chat.id)
    bot.reply_to(message, "Bienvenido 👋\nEnvía tu número de suministro para consultar tu recibo Enel.")

# === Ingreso de suministro ===
@bot.message_handler(func=lambda msg: msg.text.strip().isdigit())
def recibir_suministro(message):
    suministro = message.text.strip()
    gui.actualizar_estado(f"🔎 Consultando suministro: {suministro}")
    bot.reply_to(message, f"🔎 Buscando recibo para suministro: {suministro}...")

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
        bot.reply_to(message, f"❌ No se pudo ingresar el número de suministro.\n{e}")
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

        bot.send_photo(message.chat.id, image_data, caption="✍️ Ingresa el código CAPTCHA que aparece.")
        user_data[message.chat.id] = {
            "driver": driver,
            "suministro": suministro,
            "esperando_captcha": True,
            "timestamp": datetime.now()
        }
        gui.actualizar_estado(f"📸 Esperando CAPTCHA de {suministro}")
    except Exception as e:
        bot.reply_to(message, f"❌ Error al obtener el CAPTCHA.\n{e}")
        driver.quit()

# === Ingreso de CAPTCHA ===
@bot.message_handler(func=lambda msg: user_data.get(msg.chat.id, {}).get("esperando_captcha"))
def recibir_captcha(message):
    captcha = message.text.strip()
    session = user_data.get(message.chat.id)
    if not session:
        bot.reply_to(message, "Sesión no encontrada. Escribe /start para comenzar de nuevo.")
        return

    gui.actualizar_estado(f"✅ Procesando CAPTCHA de {session['suministro']}")
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
        payload = {
            "idDocumento": form.find_element(By.NAME, "idDocumento").get_attribute("value"),
            "nroSuministro": form.find_element(By.NAME, "nroSuministro").get_attribute("value"),
            "tipoServElectrico": form.find_element(By.NAME, "tipoServElectrico").get_attribute("value")
        }

        s = requests.Session()
        for cookie in driver.get_cookies():
            s.cookies.set(cookie['name'], cookie['value'])
        s.headers.update({"User-Agent": "Mozilla/5.0"})

        r = s.post(URL_DESCARGA, data=payload)

        if r.status_code == 200 and "application/pdf" in r.headers.get("Content-Type", ""):
            bot.send_document(message.chat.id, r.content, visible_file_name=f"Recibo_{suministro}.pdf")
            bot.reply_to(message, "✅ Aquí está tu recibo.")
            gui.actualizar_estado(f"📄 Recibo enviado ({suministro})")
        else:
            bot.reply_to(message, "❌ No se pudo descargar el recibo.")
            gui.actualizar_estado(f"⚠️ Fallo en descarga ({suministro})")

    except Exception as e:
        bot.reply_to(message, f"⚠️ Error al validar el CAPTCHA o descargar el recibo.\n{e}")
        gui.actualizar_estado(f"⚠️ Error CAPTCHA ({suministro})")

    finally:
        driver.quit()
        user_data.pop(message.chat.id, None)
        gui.eliminar_chat(message.chat.id)

# === Inicio del bot ===
def main():
    print("🤖 Bot Enel iniciado correctamente.")
    gui.actualizar_estado("✅ Bot en línea")
    bot.infinity_polling()

if __name__ == "__main__":
    main()
