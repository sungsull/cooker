import os
import re
import time
import tempfile
import requests
import uvicorn
import google.generativeai as genai
from fastapi import FastAPI, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import whisper

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('models/gemini-1.5-flash')

print("Whisper 모델 로딩 중...")
whisper_model = whisper.load_model("base")
print("Whisper 모델 로딩 완료!")

# 공개 Invidious 인스턴스 목록 (순서대로 시도)
INVIDIOUS_INSTANCES = [
    "https://invidious.io.lol",
    "https://inv.nadeko.net",
    "https://invidious.nerdvpn.de",
    "https://yt.drgnz.club",
    "https://iv.datura.network",
    "https://invidious.privacyredirect.com",
    "https://inv.thepixora.com",
    "https://yt.chocolatemoo53.com",
]

def extract_video_id(url: str) -> str | None:
    """YouTube URL에서 video ID 추출"""
    patterns = [
        r'(?:v=)([a-zA-Z0-9_-]{11})',       # watch?v=
        r'(?:youtu\.be/)([a-zA-Z0-9_-]{11})', # youtu.be/
        r'(?:shorts/)([a-zA-Z0-9_-]{11})',     # shorts/
        r'(?:embed/)([a-zA-Z0-9_-]{11})',      # embed/
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def get_audio_from_invidious(video_id: str):
    """여러 Invidious 인스턴스를 순서대로 시도해서 오디오 URL 반환"""
    headers = {"User-Agent": "Mozilla/5.0"}

    for instance in INVIDIOUS_INSTANCES:
        try:
            api_url = f"{instance}/api/v1/videos/{video_id}"
            resp = requests.get(api_url, headers=headers, timeout=8)

            if resp.status_code != 200:
                print(f"[{instance}] 응답 코드: {resp.status_code}, 다음 시도")
                continue

            data = resp.json()
            title = data.get('title', '요리 영상')

            # adaptiveFormats에서 오디오만 추출 (bitrate 높은 순)
            audio_formats = [
                f for f in data.get('adaptiveFormats', [])
                if f.get('type', '').startswith('audio/')
            ]

            if not audio_formats:
                print(f"[{instance}] 오디오 포맷 없음, 다음 시도")
                continue

            # bitrate 높은 것 선택
            best_audio = max(audio_formats, key=lambda x: x.get('bitrate', 0))
            audio_url = best_audio.get('url')

            # Invidious 프록시 URL이면 해당 인스턴스 도메인 붙이기
            if audio_url and audio_url.startswith('/'):
                audio_url = instance + audio_url

            if audio_url:
                print(f"✅ [{instance}] 오디오 URL 획득 성공")
                return {"title": title, "audio_url": audio_url, "instance": instance}

        except requests.exceptions.Timeout:
            print(f"[{instance}] 타임아웃, 다음 시도")
        except Exception as e:
            print(f"[{instance}] 에러: {e}, 다음 시도")

    return None

@app.get("/")
def home():
    return FileResponse("index.html")

@app.get("/script.js")
def serve_script():
    return FileResponse("script.js")

@app.post("/get_audio_url")
async def get_audio_url(url: str = Form(...)):
    try:
        video_id = extract_video_id(url)
        if not video_id:
            return {"status": "error", "message": "유효한 YouTube URL이 아닙니다."}

        result = get_audio_from_invidious(video_id)
        if not result:
            return {"status": "error", "message": "모든 Invidious 인스턴스 접근 실패. 잠시 후 다시 시도해주세요."}

        return {
            "status": "success",
            "audio_url": result["audio_url"],
            "title": result["title"]
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/transcribe")
async def transcribe_audio(audio_url: str = Form(...)):
    tmp_path = None
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(audio_url, headers=headers, stream=True, timeout=60)
        response.raise_for_status()

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            downloaded = 0
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)
                downloaded += len(chunk)
                if downloaded > 50 * 1024 * 1024:
                    break
            tmp_path = f.name

        result = whisper_model.transcribe(tmp_path, language="ko")
        return {"status": "success", "text": result["text"]}

    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

@app.post("/summarize")
async def summarize_recipe(transcript: str = Form(...), video_title: str = Form(...)):
    try:
        prompt = (
            f"요리 전문가로서 다음 내용을 아래 형식으로 요약해줘. 마크다운(**) 금지.\n\n"
            f"[요리 이름]\n[재료]\n[조리 순서]\n[꿀팁]\n\n"
            f"제목: {video_title}\n내용: {transcript[:8000]}"
        )
        response = gemini_model.generate_content(prompt)
        return {"status": "success", "recipe": response.text.strip()}
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)
