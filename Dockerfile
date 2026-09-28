FROM python:3.12-slim

WORKDIR /app
COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt

COPY servidor.py .
COPY siglo_game/src ./siglo_game/src
COPY siglo_game/web ./siglo_game/web

# Un hosting suele fijar PORT; si no, 8080.
ENV PORT=8080
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT','8080'), timeout=2)" || exit 1

# Solo navegador: en un hosting web normal no se abre el TCP crudo.
CMD ["python", "servidor.py", "--sin-tcp"]
