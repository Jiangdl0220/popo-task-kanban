FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

COPY . .

EXPOSE 5151

CMD ["gunicorn", "--bind", "0.0.0.0:5151", "--workers", "2", "app:app"]
