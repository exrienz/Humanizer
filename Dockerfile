FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir flask==3.0.0 ollama==0.6.2 python-dotenv==1.0.0

COPY app.py /app/
COPY templates /app/templates
COPY skills /app/skills

ENV OLLAMA_MODEL=gemma4:31b-cloud
ENV OLLAMA_BASE_URL=https://ollama.com
ENV SKILLS_DIR=/app/skills

EXPOSE 8000

CMD ["python", "app.py"]