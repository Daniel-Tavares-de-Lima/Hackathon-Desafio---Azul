# Painel ÓRBITA. Pressupõe data/ e ml/resultados/ já gerados (make all) no contexto do build.
FROM python:3.13-slim
WORKDIR /orbita
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8501
CMD ["sh", "-c", "python -I app/lote.py && python -I -m streamlit run app/main.py --server.address=0.0.0.0 --server.headless=true"]
