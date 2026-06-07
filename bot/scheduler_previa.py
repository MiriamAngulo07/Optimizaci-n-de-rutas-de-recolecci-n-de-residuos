"""
Notificación PREVIA — SIROCA  (opción A)
La DISPARA EL OPERADOR cuando corresponde (no es automática diaria).
Puede limitarse a un solo camión vía camion_id.

Uso manual (todos):       python scheduler_previa.py
Uso manual (un camión):   python scheduler_previa.py 1
Daemon opcional:          python scheduler_previa.py --daemon
"""
import sys
import threading
import requests
from datetime import date
from notificador import enviar
from residentes import cargar_residentes, guardar_residentes

HORA_RECOLECCION = "8:00 AM"


def notificar_previa(camion_id=None):
    """Avisa a los residentes registrados que viene su recolección.
    camion_id=None → todos.  camion_id=N → solo ese camión.
    No re-envía a quien ya fue avisado hoy. Devuelve cuántos se enviaron."""
    data = cargar_residentes()
    hoy = date.today().isoformat()
    enviados = 0
    for r in data["residentes"]:
        # filtro por camión (clave correcta de segmentación: no hay nombres de zona)
        if camion_id is not None and str(r.get("camion_id")) != str(camion_id):
            continue
        # no duplicar en el mismo día
        if r.get("notificado_previa") == hoy:
            continue
        res = enviar(
            r["chat_id"],
            f"🗑️ <b>Recolección próxima</b>\n\n"
            f"Hola {r['nombre']}, pronto pasa el camión por tu calle "
            f"a las <b>{HORA_RECOLECCION}</b>.\n"
            f"Saca tu basura antes de esa hora. 🙌",
        )
        if res.get("ok"):                       # solo marca si de verdad se envió
            r["notificado_previa"] = hoy
            enviados += 1
    guardar_residentes(data)
    destino = f"camión #{camion_id}" if camion_id is not None else "todos"
    print(f"✅ Previa enviada a {enviados} residente(s) [{destino}].")
    return enviados                              # ⬅ el fix que faltaba

if __name__ == "__main__":
    if "--daemon" in sys.argv:
        import schedule
        import time
        schedule.every().day.at("20:00").do(notificar_previa)
        print("⏰ Programado: previa diaria 20:00. Ctrl+C para salir.")
        while True:
            schedule.run_pending()
            time.sleep(30)
    else:
        cid = next((a for a in sys.argv[1:] if a.isdigit()), None)
        notificar_previa(cid)