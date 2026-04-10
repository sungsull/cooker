import os
import re
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

# 현재 살아있는 인스턴스 위주로 업데이트
# 최신 목록: https://api.invidious.io
INVIDIOUS_INSTANCES = [
    "https://inv.nadeko.net",
    "https://invidious.privacyredirect.com",
    "https://inv.thepixora.com",
    "https://yt.chocolatemoo53.com",
    "https://invidious.io.lol",
    "https://iv.datura.network",
]

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

def download_audio_from_invidious(video_id: str):
    """URL 추출 + 즉시 다운로드까지 한 번에 처리 (URL 만료 방지)"""
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

            audio_formats = [
                f for f in data.get('adaptiveFormats', [])
                if f.get('type', '').startswith('audio/')
            ]

            if not audio_formats:
                print(f"[{instance}] 오디오 포맷 없음, 다음 시도")
                continue

            best_audio = max(audio_formats, key=lambda x: x.get('bitrate', 0))
            audio_url = best_audio.get('url')

            if audio_url and audio_url.startswith('/'):
                audio_url = instance + audio_url

            if not audio_url:
                continue

            # URL 획득 즉시 다운로드 (만료 방지)
            print(f"✅ [{instance}] 다운로드 시작...")
            dl_resp = requests.get(audio_url, headers=headers, stream=True, timeout=60)
            dl_resp.raise_for_status()

            tmp_path = None
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
                downloaded = 0
                for chunk in dl_resp.iter_content(chunk_size=1024 * 1024):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if downloaded > 50 * 1024 * 1024:
                        break
                tmp_path = f.name

            print(f"✅ [{instance}] 다운로드 완료 ({downloaded // 1024}KB)")
            return {"title": title, "tmp_path": tmp_path}

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

# /get_audio_url + /transcribe를 /process 하나로 통합
@app.post("/process")
async def process_video(url: str = Form(...)):
    tmp_path = None
    try:
        video_id = extract_video_id(url)
        if not video_id:
            return {"status": "error", "message": "유효한 YouTube URL이 아닙니다."}

        # 1단계: 오디오 다운로드
        result = download_audio_from_invidious(video_id)
        if not result:
            return {"status": "error", "message": "모든 Invidious 인스턴스 접근 실패. 잠시 후 다시 시도해주세요."}

        tmp_path = result["tmp_path"]
        title = result["title"]

        # 2단계: Whisper 변환
        transcribe_result = whisper_model.transcribe(tmp_path, language="ko")
        transcript = transcribe_result["text"]

        # 3단계: Gemini 요약
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
            os.remove(tmp_path)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)
