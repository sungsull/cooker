FROM python:3.10-slim

# 1. 루트 권한으로 필수 패키지 설치
USER root
WORKDIR /app

RUN apt-get update && apt-get install -y \
    ffmpeg git nodejs npm curl \
    && rm -rf /var/lib/apt/lists/*

# 2. Python 라이브러리 먼저 설치 (가장 무거운 것부터)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir "git+https://github.com/coletdjnz/yt-dlp-get-pot.git"

# 3. Node.js 서비스 설치 (경로를 /app/bgutil로 변경하여 권한 문제 회피)
RUN git clone https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git /app/bgutil && \
    cd /app/bgutil && \
    npm install && \
    npm run build

# 4. 전체 소스 코드 복사
COPY . .

# 5. 권한 설정 (Hugging Face는 1000번 유저를 사용하므로 범위를 넓게 잡습니다)
RUN chmod -R 777 /app

# 6. 실행 (경로 수정됨)
# bgutil 서버 실행 경로를 /app/bgutil/build/server.js로 맞춤
CMD ["sh", "-c", "node /app/bgutil/build/server.js & sleep 10 && python main.py"]