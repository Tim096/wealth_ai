FROM python:3.12-slim
LABEL "language"="python"

WORKDIR /src
COPY . .

# core packages (sec extras: httpx/lxml/bs4/edgartools) + the web layer
RUN pip install --no-cache-dir -e ".[sec]" -r apps/services/sec/requirements.txt

EXPOSE 8080
# PORT is injected by Zeabur; fall back to 8080 locally
CMD ["sh", "-c", "uvicorn apps.services.sec.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
