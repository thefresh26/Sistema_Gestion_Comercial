# Imagen con Chrome/Chromium instalado -- necesaria porque el módulo
# Documentos (Acta de Subasta, Informe de Subasta) hace scraping real de
# activosporcolombia.com con Selenium + Chrome headless para leer fechas
# exactas del cronograma. El resto del sistema (SAE, FRV, Vista_Inmuebles,
# Dashboard, Admin) no usa Chrome para nada -- esto solo se agrega para
# que el módulo Documentos pueda scrapear.
FROM python:3.11-slim

# Chrome necesita estas librerías del sistema para correr en modo headless
# (aunque nunca se abra una ventana real).
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg ca-certificates fonts-liberation \
    && wget -q -O /tmp/google-chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get install -y --no-install-recommends /tmp/google-chrome.deb \
    && rm /tmp/google-chrome.deb \
    && rm -rf /var/lib/apt/lists/*

ENV CHROME_BIN=/usr/bin/google-chrome
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# webdriver_manager descarga el chromedriver correcto la primera vez que se
# usa (necesita salida a internet, que Render sí permite). Se deja el
# directorio de caché con permisos abiertos para que funcione sin ser root.
ENV WDM_LOCAL=1
RUN mkdir -p /app/.wdm && chmod -R 777 /app/.wdm

EXPOSE 10000
CMD gunicorn app:app --bind 0.0.0.0:${PORT:-10000} --timeout 120
