FROM python:3.14-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY schemas/ schemas/
COPY I3/ I3/
COPY main.py .
ENV PYTHONPATH=/app/I3
ENTRYPOINT ["python", "-u", "main.py"]
