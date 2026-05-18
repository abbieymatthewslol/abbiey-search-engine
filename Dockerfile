FROM python:3.12.8-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN adduser --disabled-password --no-create-home appuser
USER appuser

# First-run defaults make a fresh pull usable immediately without any cloud
# account. Override in production (docker run -e, compose, or k8s) as needed.
#   ABBIEY_OPEN_ACCESS=1        disables rate limits (intended for private
#                               self-hosts only; unset before exposing publicly)
#   ABBIEY_SKIP_WELCOME_SCREEN=1 skip /welcome on first visit
#   PORT=8000                   gunicorn bind port
ENV ABBIEY_OPEN_ACCESS=1 \
    ABBIEY_SKIP_WELCOME_SCREEN=1 \
    PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os, urllib.request; port = os.environ.get('PORT', '8000'); urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=3)"

CMD gunicorn -w 4 -b 0.0.0.0:${PORT:-8000} app:app
