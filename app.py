"""
Punto de entrada del Sistema de Gestión Comercial.

Este archivo es a propósito mínimo: solo crea la aplicación. Todo el
código está en el paquete `backend/` — empieza por `backend/__init__.py`,
que explica cómo está organizado.

  - Producción (Render): `gunicorn app:app`
  - Local:               `python app.py`
"""
from backend import create_app

app = create_app()

if __name__ == "__main__":
    import os

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
