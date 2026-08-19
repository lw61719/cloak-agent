FROM cloakhq/cloakbrowser:latest

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app/cloak-agent

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir .

EXPOSE 8000

# CloakBrowser requires asyncio instead of uvloop when launched by Uvicorn.
CMD ["sh", "-c", "exec uvicorn cloak_agent.web:app --host 0.0.0.0 --port \"${PORT:-8000}\" --loop asyncio --workers 1 --proxy-headers --forwarded-allow-ips='*' --timeout-graceful-shutdown 60"]
