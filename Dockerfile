FROM python:3.10-slim

# 루트 권한 확보 및 필수 라이브러리 설치
USER root
WORKDIR /app

# faster-whisper 구동을 위해 libgomp1이 필수입니다.
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libgomp1 \
    git \
    && rm -rf /var/lib/apt/lists/*

# requirements.txt 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -U pip && \
    pip install --no-cache-dir -r requirements.txt

# 소스 복사 및 권한 부여
COPY . .
RUN chmod -R 777 /app

# 포트 노출
EXPOSE 7860

# 실행
CMD ["python", "main.py"]