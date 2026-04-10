import os
import re
import tempfile
import requests
import uvicorn
import google.generativeai as genai
from fastapi import FastAPI, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import yt_dlp
from faster_whisper import WhisperModel

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 환경 변수 설정
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('models/gemini-1.5-flash')

print("Whisper 모델 로딩 중...")
whisper_model = WhisperModel("tiny", device="cpu", compute_type="int8")
print("Whisper 모델 로딩 완료!")

# 쿠키 파일 처리
COOKIE_FILE_PATH = None
youtube_cookies = os.environ.get("YOUTUBE_COOKIES")

if youtube_cookies:
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
            f.write(youtube_cookies.strip())
            COOKIE_FILE_PATH = f.name
        print(f"✅ 쿠키 파일 생성 완료: {COOKIE_FILE_PATH}")
    except Exception as e:
        print(f"❌ 쿠키 생성 에러: {e}")

def get_ydl_opts():
    opts = {
        # 'ba/b'로 설정하여 오디오가 없으면 비디오라도 가져오도록 유연하게 대처
        'format': 'ba/b',
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        # 차단 회피를 위한 다양한 클라이언트 설정
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'mweb', 'web'],
            }
        },
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    if COOKIE_FILE_PATH:
        opts['cookiefile'] = COOKIE_FILE_PATH
    return opts

def extract_video_id(url: str):
    patterns = [
        r'(?:v=)([a-zA-Z0-9_-]{11})',
        r'(?:youtu\.be/)([a-zA-Z0-9_-]{11})',
        r'(?:shorts/)([a-zA-Z0-9_-]{11})',
        r'(?:embed/)([a-zA-Z0-9_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

@app.get("/")
def home():
    return FileResponse("index.html")

@app.get("/script.js")
def serve_script():
    return FileResponse("script.js")

@app.post("/process")
async def process_video(url: str = Form(...)):
    tmp_path = None
    try:
        video_id = extract_video_id(url)
        if not video_id:
            return {"status": "error", "message": "유효한 YouTube URL이 아닙니다."}

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            tmp_path = f.name

        ydl_opts = get_ydl_opts()
        ydl_opts['outtmpl'] = tmp_path

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                raise Exception("영상을 다운로드할 수 없습니다. 포맷 에러일 가능성이 큽니다.")
            title = info.get('title', '요리 영상')

        # Whisper 변환
        segments, _ = whisper_model.transcribe(tmp_path, language="ko", beam_size=1)
        transcript = " ".join([seg.text for seg in segments])

        if not transcript.strip():
            return {"status": "error", "message": "영상에서 음성을 추출하지 못했습니다."}

        # Gemini 요약
        prompt = (
            f"요리 전문가로서 다음 내용을 아래 형식으로 요약해줘. 마크다운(**) 금지.\n\n"
            f"[요리 이름]\n[재료]\n[조리 순서]\n[꿀팁]\n\n"
            f"제목: {title}\n내용: {transcript[:8000]}"
        )
        gemini_resp = gemini_model.generate_content(prompt)

        return {
            "status": "success",
            "title": title,
            "recipe": gemini_resp.text.strip()
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except:
                pass

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)