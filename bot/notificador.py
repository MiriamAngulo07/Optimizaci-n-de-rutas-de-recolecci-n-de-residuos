"""
Notificador SIROCA — capa única de Telegram.
La usan: siroca_bot.py, scheduler_previa.py, proximidad.py y app.py

- enviar() / obtener_updates(): API por chat_id (residentes y operadores).
- iniciar_sesion(), enviar_ruta_*, enviar_resumen_diario(): mensajes
  operativos que van al GRUPO DE OPERADORES (CHAT_ID del .env).
"""
import os
import requests
from datetime import datetime
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

# --- Config ---
PROYECTO = os.getenv("PROYECTO_NOMBRE", "SIROCA")
VERSION = os.getenv("PROYECTO_VERSION", "1.0")
UBICACION = os.getenv("UBICACION", "Puerto Caimito, Panamá")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")   # grupo de operadores (opcional)

if not BOT_TOKEN:
    raise ValueError("❌ Falta TELEGRAM_BOT_TOKEN en .env")

BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
TIMEOUT = 10  # segundos


# ─── Núcleo (por chat_id) ─────────────────────────────────
def enviar(chat_id, mensaje, parse_mode="HTML", reply_markup=None):
    """Envía un mensaje a un chat_id específico (residente u operador).
    Nunca lanza excepción: si falla devuelve {'ok': False, 'error': ...}."""
    data = {"chat_id": chat_id, "text": mensaje, "parse_mode": parse_mode}
    if reply_markup:
        data["reply_markup"] = reply_markup
    try:
        r = requests.post(f"{BASE_URL}/sendMessage", json=data, timeout=TIMEOUT)
        return r.json()
    except requests.RequestException as e:
        print(f"⚠️ Error enviando a {chat_id}: {e}")
        return {"ok": False, "error": str(e)}


def obtener_updates(offset=None, timeout=30):
    """Long-polling: trae los mensajes nuevos que llegan al bot."""
    params = {"timeout": timeout}
    if offset:
        params["offset"] = offset
    try:
        r = requests.get(f"{BASE_URL}/getUpdates", params=params, timeout=timeout + 5)
        return r.json()
    except requests.RequestException as e:
        print(f"⚠️ Error en getUpdates: {e}")
        return {"ok": False, "result": []}


def enviar_ubicacion(lat, lon, titulo="Ubicación", chat_id=None):
    """Envía una ubicación en el mapa. Sin chat_id usa el grupo de operadores."""
    destino = chat_id or CHAT_ID
    if not destino:
        return {"ok": False, "error": "Sin chat_id"}
    data = {"chat_id": destino, "latitude": lat, "longitude": lon, "title": titulo}
    try:
        return requests.post(f"{BASE_URL}/sendLocation", json=data, timeout=TIMEOUT).json()
    except requests.RequestException as e:
        return {"ok": False, "error": str(e)}


# ─── Mensajes al grupo de operadores ──────────────────────
def _enviar_operador(mensaje):
    """Envía al CHAT_ID del .env (grupo de operadores/admin)."""
    if not CHAT_ID:
        print("⚠️ TELEGRAM_CHAT_ID no configurado; se omite mensaje de operador.")
        return {"ok": False, "error": "CHAT_ID no configurado"}
    return enviar(CHAT_ID, mensaje)


def iniciar_sesion():
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    mensaje = (
        f"<b>🚀 {PROYECTO} v{VERSION}</b>\n"
        f"<i>Sistema Inteligente de Rutas de Optimización</i>\n\n"
        f"📍 <b>Localización:</b> {UBICACION}\n"
        f"⏰ <b>Activado:</b> {timestamp}\n\n"
        f"✅ Bot conectado y listo para optimizar rutas de recolección"
    )
    result = _enviar_operador(mensaje)
    print(f"✅ {PROYECTO} iniciado - {result.get('ok')}")
    return result


def enviar_ruta_asignada(numero_vehiculo, trabajador, paradas, distancia_km):
    mensaje = (
        f"<b>🚗 Nueva Ruta Asignada - {PROYECTO}</b>\n\n"
        f"<b>Vehículo:</b> Camión #{numero_vehiculo}\n"
        f"<b>Operador:</b> {trabajador}\n"
        f"📍 <b>Paradas:</b> {paradas}\n"
        f"📏 <b>Distancia Total:</b> {distancia_km} km\n\n"
        f"<b>⏳ Estado:</b> Pendiente de confirmación"
    )
    return _enviar_operador(mensaje)


def enviar_ruta_iniciada(numero_vehiculo, trabajador):
    timestamp = datetime.now().strftime("%H:%M:%S")
    mensaje = (
        f"<b>✅ Ruta Iniciada</b>\n\n"
        f"🚗 Camión #{numero_vehiculo}\n"
        f"👤 Operador: {trabajador}\n"
        f"⏰ Hora de inicio: {timestamp}\n\n"
        f"💚 Sistema {PROYECTO} monitoreando..."
    )
    return _enviar_operador(mensaje)


def enviar_alerta_retraso(numero_vehiculo, minutos_retraso):
    mensaje = (
        f"<b>⚠️ Alerta de Retraso</b>\n\n"
        f"🚗 Camión #{numero_vehiculo}\n"
        f"⏰ Retraso estimado: {minutos_retraso} minutos\n\n"
        f"Verificar si hay inconvenientes en la ruta."
    )
    return _enviar_operador(mensaje)


def enviar_ruta_completada(numero_vehiculo, trabajador, paradas_completadas, distancia, tiempo_total):
    mensaje = (
        f"<b>🎉 Ruta Completada</b>\n\n"
        f"🚗 Camión #{numero_vehiculo}\n"
        f"👤 Operador: {trabajador}\n"
        f"✅ Paradas completadas: {paradas_completadas}\n"
        f"📏 Distancia recorrida: {distancia} km\n"
        f"⏱️ Tiempo total: {tiempo_total}\n\n"
        f"<b>Gracias por tu trabajo en {PROYECTO}</b>"
    )
    return _enviar_operador(mensaje)


def enviar_resumen_diario(total_vehiculos, total_paradas, distancia_total, eficiencia):
    fecha = datetime.now().strftime("%d/%m/%Y")
    mensaje = (
        f"<b>📊 Resumen Diario - {PROYECTO}</b>\n\n"
        f"📅 Fecha: {fecha}\n"
        f"🚗 Vehículos en operación: {total_vehiculos}\n"
        f"📍 Total de paradas: {total_paradas}\n"
        f"📏 Distancia acumulada: {distancia_total} km\n"
        f"⚡ Eficiencia: {eficiencia}%\n\n"
        f"✨ Operación completada exitosamente"
    )
    return _enviar_operador(mensaje)


def test_conexion():
    resultado = _enviar_operador(f"🔧 Test de conexión {PROYECTO} - OK")
    ok = bool(resultado.get("ok"))
    print("✅ Conexión exitosa con Telegram" if ok else "❌ Error en respuesta de Telegram")
    return ok