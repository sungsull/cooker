FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    ffmpeg git nodejs npm \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN pip install --no-cache-dir \
    "yt-dlp-get-pot @ https://github.com/coletdjnz/yt-dlp-get-pot/archive/refs/heads/master.zip"

RUN npm install -g https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git

COPY . .

EXPOSE 7860

CMD ["sh", "-c", "node $(npm root -g)/bgutil-ytdlp-pot-provider/build/server.js & python main.py"]