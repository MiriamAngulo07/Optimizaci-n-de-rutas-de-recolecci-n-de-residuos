import os
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Configuración
PROYECTO = os.getenv("PROYECTO_NOMBRE", "SIROCA")
VERSION = os.getenv("PROYECTO_VERSION", "1.0")
UBICACION = os.getenv("UBICACION", "Puerto Caimito, Panamá")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Validar credenciales
if not BOT_TOKEN or not CHAT_ID:
    raise ValueError("❌ Falta TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID en .env")

BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"


def enviar_mensaje(mensaje, parse_mode="HTML"):
    """Envía un mensaje de texto"""
    url = f"{BASE_URL}/sendMessage"
    data = {
        "chat_id": CHAT_ID,
        "text": mensaje,
        "parse_mode": parse_mode
    }
    response = requests.post(url, json=data)
    return response.json()


def enviar_ubicacion(lat, lon, titulo="Ubicación"):
    """Envía una ubicación en el mapa"""
    url = f"{BASE_URL}/sendLocation"
    data = {
        "chat_id": CHAT_ID,
        "latitude": lat,
        "longitude": lon,
        "title": titulo
    }
    return requests.post(url, json=data).json()


def iniciar_sesion():
    """Mensaje de bienvenida del sistema"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    mensaje = f"""
<b>🚀 {PROYECTO} v{VERSION}</b>
<i>Sistema Inteligente de Rutas de Optimización</i>

📍 <b>Localización:</b> {UBICACION}
⏰ <b>Activado:</b> {timestamp}

✅ Bot conectado y listo para optimizar rutas de recolección
    """
    result = enviar_mensaje(mensaje)
    print(f"✅ {PROYECTO} iniciado - {result.get('ok')}")
    return result


def enviar_ruta_asignada(numero_vehiculo, trabajador, paradas, distancia_km, puntos_ruta=None):
    """Envía notificación detallada de ruta asignada"""
    mensaje = f"""
<b>🚗 Nueva Ruta Asignada - {PROYECTO}</b>

<b>Vehículo:</b> Camión #{numero_vehiculo}
<b>Operador:</b> {trabajador}
📍 <b>Paradas:</b> {paradas}
📏 <b>Distancia Total:</b> {distancia_km} km

<b>⏳ Estado:</b> Pendiente de confirmación

¿Confirmas que <b>inicias</b> la ruta?
Responde: ✅ CONFIRMO
    """
    return enviar_mensaje(mensaje)


def enviar_ruta_iniciada(numero_vehiculo, trabajador):
    """Confirmación de inicio de ruta"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    mensaje = f"""
<b>✅ Ruta Iniciada</b>

🚗 Camión #{numero_vehiculo}
👤 Operador: {trabajador}
⏰ Hora de inicio: {timestamp}

💚 Sistema {PROYECTO} monitoreando...
    """
    return enviar_mensaje(mensaje)


def enviar_alerta_retraso(numero_vehiculo, minutos_retraso):
    """Alerta si hay retraso en la ruta"""
    mensaje = f"""
<b>⚠️ Alerta de Retraso</b>

🚗 Camión #{numero_vehiculo}
⏰ Retraso estimado: {minutos_retraso} minutos

Verificar si hay inconvenientes en la ruta.
    """
    return enviar_mensaje(mensaje)


def enviar_ruta_completada(numero_vehiculo, trabajador, paradas_completadas, distancia, tiempo_total):
    """Notificación de ruta completada"""
    mensaje = f"""
<b>🎉 Ruta Completada</b>

🚗 Camión #{numero_vehiculo}
👤 Operador: {trabajador}
✅ Paradas completadas: {paradas_completadas}
📏 Distancia recorrida: {distancia} km
⏱️ Tiempo total: {tiempo_total}

<b>Gracias por tu trabajo en {PROYECTO}</b>
    """
    return enviar_mensaje(mensaje)


def enviar_resumen_diario(total_vehiculos, total_paradas, distancia_total, eficiencia):
    """Resumen diario de operaciones"""
    fecha = datetime.now().strftime("%d/%m/%Y")
    mensaje = f"""
<b>📊 Resumen Diario - {PROYECTO}</b>

📅 Fecha: {fecha}
🚗 Vehículos en operación: {total_vehiculos}
📍 Total de paradas: {total_paradas}
📏 Distancia acumulada: {distancia_total} km
⚡ Eficiencia: {eficiencia}%

✨ Operación completada exitosamente
    """
    return enviar_mensaje(mensaje)


def test_conexion():
    """Prueba la conexión con el bot"""
    try:
        resultado = enviar_mensaje(f"🔧 Test de conexión {PROYECTO} - OK")
        if resultado.get('ok'):
            print("✅ Conexión exitosa con Telegram")
            return True
        else:
            print("❌ Error en respuesta de Telegram")
            return False
    except Exception as e:
        print(f"❌ Error de conexión: {e}")
        return False


if __name__ == "__main__":
    # Iniciar
    iniciar_sesion()
    
    # Test
    test_conexion()
    
    # Ejemplos
    print("\n--- Ejemplos de notificaciones ---\n")
    
    # Ruta asignada
    enviar_ruta_asignada(
        numero_vehiculo=1,
        trabajador="Juan López",
        paradas=92,
        distancia_km=31.3
    )
    
    # Resumen
    enviar_resumen_diario(
        total_vehiculos=2,
        total_paradas=238,
        distancia_total=65.5,
        eficiencia=92
    )