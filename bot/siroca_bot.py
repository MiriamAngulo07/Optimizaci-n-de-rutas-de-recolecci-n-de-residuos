"""
Bot SIROCA — registro de vecinos + GPS en vivo de operadores.
- Vecino:    comparte su ubicación (estática) con el botón → se registra.
- Operador:  /camion 1, luego comparte UBICACIÓN EN VIVO → alimenta proximidad.
Ejecutar:  python siroca_bot.py
"""
import os, json, time
from notificador import enviar, obtener_updates
from residentes import registrar_residente
from proximidad import revisar

OPERADORES_FILE = "operadores.json"

TECLADO_UBICACION = {
    "keyboard": [[{"text": "📍 Compartir mi ubicación", "request_location": True}]],
    "resize_keyboard": True,
    "one_time_keyboard": True,
}


def cargar_operadores():
    if not os.path.exists(OPERADORES_FILE):
        return {}
    with open(OPERADORES_FILE, encoding="utf-8") as f:
        return json.load(f)


def guardar_operadores(d):
    with open(OPERADORES_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def manejar_update(upd):
    # las actualizaciones de ubicación EN VIVO llegan como edited_message
    msg = upd.get("message") or upd.get("edited_message")
    if not msg:
        return
    chat_id = msg["chat"]["id"]
    nombre = msg.get("from", {}).get("first_name", "Vecino")
    operadores = cargar_operadores()
    loc = msg.get("location")

    # ── 1) Llegó una ubicación ──────────────────────────────
    if loc:
        es_operador = str(chat_id) in operadores
        es_en_vivo = "live_period" in loc
        if es_operador or es_en_vivo:                 # operador → feed de GPS
            camion_id = operadores.get(str(chat_id))
            if not camion_id:
                enviar(chat_id, "Antes de compartir ubicación dime tu camión:\n<code>/camion 1</code>")
                return
            try:
                avisados = revisar(camion_id, loc["latitude"], loc["longitude"])
                if avisados:
                    print(f"📡 Camión {camion_id}: avisados {avisados} vecino(s)")
            except Exception as e:
                print("Error en revisar:", e)
            return

        # vecino → registrar (ubicación estática)
        reg = registrar_residente(chat_id, nombre, loc["latitude"], loc["longitude"])
        if reg["camion_id"]:
            enviar(chat_id,
                f"✅ <b>¡Listo, {nombre}!</b>\n\n"
                f"Quedaste registrado. Te avisaremos el día antes de tu recolección "
                f"y cuando el camión esté cerca de tu casa.\n\n"
                f"🚛 Te atiende el <b>Camión #{reg['camion_id']}</b>")
        else:
            enviar(chat_id,
                "⚠️ Te registré, pero aún no hay rutas cargadas. "
                "Te asignaremos un camión en cuanto se genere la ruta del día.")
        return

    # ── 2) Texto ────────────────────────────────────────────
    text = (msg.get("text") or "").strip()
    low = text.lower()

    if low.startswith("/camion"):
        partes = text.split()
        if len(partes) == 2 and partes[1].isdigit():
            operadores[str(chat_id)] = partes[1]
            guardar_operadores(operadores)
            enviar(chat_id,
                f"✅ Registrado como operador del <b>Camión #{partes[1]}</b>.\n\n"
                "Al salir a la ruta comparte tu <b>ubicación en tiempo real</b>:\n"
                "📎 → Ubicación → <b>Compartir ubicación en tiempo real</b> → 8 horas.")
        else:
            enviar(chat_id, "Uso: <code>/camion 1</code>")
        return

    if low.startswith("/start"):
        enviar(chat_id,
            "👋 <b>Bienvenido a SIROCA</b>\n"
            "Recolección de desechos — Puerto Caimito.\n\n"
            "Para avisarte cuándo pasa el camión por tu calle, "
            "comparte tu ubicación con el botón de abajo 👇",
            reply_markup=TECLADO_UBICACION)
    else:
        enviar(chat_id,
            "Escribe /start y comparte tu ubicación para registrarte. 📍",
            reply_markup=TECLADO_UBICACION)


def main():
    print("🤖 Bot SIROCA escuchando... (Ctrl+C para salir)")
    offset = None
    while True:
        try:
            res = obtener_updates(offset)
            for upd in res.get("result", []):
                offset = upd["update_id"] + 1
                manejar_update(upd)
        except KeyboardInterrupt:
            print("\n👋 Bot detenido.")
            break
        except Exception as e:
            print("Error:", e)
            time.sleep(3)


if __name__ == "__main__":
    main()