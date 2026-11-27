# IRIS online demo: the local SANDBOX (stand-in sign-in, throwaway database, fictional accounts) as one web service.
# It is a prototype that no clinician has reviewed: always run it with IRIS_DEMO_PASSWORD set, and never invite real people to use it.

FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.10-slim
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY ml/iris_ml ml/iris_ml
COPY ml/configs ml/configs
COPY --from=web /web/dist frontend/dist

ENV PYTHONUNBUFFERED=1 IRIS_DEMO_HOST=0.0.0.0 IRIS_DEMO_WEB_DIR=/app/frontend/dist
WORKDIR /app/backend
EXPOSE 8000
CMD ["python", "-m", "devtools.demo_server"]
