import os
import time
import base64
import logging
import threading
from io import BytesIO
import requests

import telebot
from telebot import types

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# -------------------- Configuración y Logging --------------------
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN",
                  "8043272067:AAGdUtbRpnd-NNaKhcJdJkpWQRyvLT1XKZw")
URL_CONSULTA = "https://mktper.enel.com/app-web-recibo/consulta-tu-recibo"
URL_DESCARGA = "https://mktper.enel.com/app-web-recibo/descargar-recibo"

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# Diccionarios globales para gestionar sesiones, historial, configuración y feedback.
user_data = {
}  # Datos temporales de la sesión (driver, suministro, captcha_bytes, retry_count, timestamp)
receipt_history = {}  # Último recibo descargado (en memoria) por chat
user_settings = {}  # Configuración personalizada por usuario (ej. timeout)
feedback_list = []  # Feedback recibido (en memoria)

WAIT_TIME = 10  # Tiempo de espera para Selenium (segundos)
