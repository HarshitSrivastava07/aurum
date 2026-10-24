FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY backend ./backend
COPY frontend ./frontend
COPY data/specifications ./data/specifications
COPY .streamlit ./.streamlit
RUN pip install --no-cache-dir .
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
