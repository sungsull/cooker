FROM python:3.10-slim

WORKDIR /app

# 1. 시스템 의존성 설치 (ffmpeg 등)
RUN apt-get update && apt-get install -y \
    ffmpeg git nodejs npm curl \
    && rm -rf /var/lib/apt/lists/*

# 2. Python 라이브러리 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# [수정] 외부 레포지토리 설치 시 에러가 잦으므로 --upgrade와 함께 별도 실행
RUN pip install --no-cache-dir --upgrade "git+https://github.com/coletdjnz/yt-dlp-get-pot.git"

# 3. Node.js 라이브러리 설치 
# [수정] npm 빌드 에러 방지를 위해 git 클론 후 설치하거나 최신 플래그 사용
RUN npm install -g https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git --unsafe-perm

# 4. 소스 코드 복사
COPY . .

# 5. 권한 설정 (Hugging Face는 특정 권한이 필요할 수 있음)
RUN chmod -R 777 /app

EXPOSE 7860

# 6. 실행 (bgutil 서버가 완전히 뜰 시간을 약간 주는 것이 좋습니다)
CMD ["sh", "-c", "node $(npm root -g)/bgutil-ytdlp-pot-provider/build/server.js & sleep 5 && python main.py"]