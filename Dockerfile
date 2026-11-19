# Immagine di produzione di PlantCare (solo inferenza e interfaccia web).
# Costruzione:   docker build -t plantcare .
# Esecuzione:    docker run -p 8000:8000 -e PLANTCARE_CKPT=/app/models/baseline/model.pt -v $PWD/models:/app/models plantcare
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# PyTorch CPU: più leggero della build con CUDA, sufficiente per l'inferenza.
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch torchvision \
 && pip install "timm>=1.0" "fastapi>=0.110" "uvicorn>=0.27" "python-multipart>=0.0.9" \
      "PyYAML>=6.0" "Pillow>=10.0" "numpy>=1.24" "scikit-learn>=1.3"

COPY src ./src
COPY configs ./configs

# Utente senza privilegi
RUN useradd --create-home --uid 10001 plantcare \
 && mkdir -p /app/feedback && chown plantcare /app/feedback
USER plantcare

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status==200 else 1)"

CMD ["uvicorn", "plantcare.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
