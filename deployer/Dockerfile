FROM python:3.11-slim@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY engines.py app.py ./

# Läuft als root im Container, weil der Docker-Socket des Hosts eingehängt wird. Das Risiko
# begrenzt die schmale API (app.py): feste Images und Argumente, nur das Modellvolume als Mount,
# Zugriff nur mit Token und nur im internen Compose-Netzwerk (kein veröffentlichter Port).
EXPOSE 9000
HEALTHCHECK --interval=30s --timeout=5s --retries=5 CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:9000/health', timeout=3).status == 200 else 1)"
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9000"]
