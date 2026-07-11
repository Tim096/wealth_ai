# wealth-agent — Task 1 public frontend + API.
# python:3.12-slim (NOT the mcr playwright image): pyproject requires-python>=3.12
# and mcr tags pin their own python; slim keeps the build deterministic.
FROM python:3.12-slim
LABEL "language"="python"

ENV PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /src
COPY . .

# repo packages (browser extra) + service deps, then Chromium + its OS libs
RUN pip install --no-cache-dir -e ".[browser]" -r apps/services/agent/requirements.txt \
 && playwright install --with-deps chromium \
 && rm -rf /var/lib/apt/lists/*

EXPOSE 8080
CMD ["sh", "-c", "uvicorn main:app --app-dir apps/services/agent --host 0.0.0.0 --port ${PORT:-8080}"]
