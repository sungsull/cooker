import os
import uvicorn
import google.generativeai as genai
from fastapi import FastAPI, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.middleware.base import BaseHTTPMiddleware
import yt_dlp

# CSP 보안 헤더를 강제로 주입하는 미들웨어
class CSPMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src * 'unsafe-inline' 'unsafe-eval' data: blob:; "
            "script-src * 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
            "connect-src *; img-src * data:; frame-src *; style-src * 'unsafe-inline';"
        )
        return response

app = FastAPI()
app.add_middleware(CSPMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('models/gemini-1.5-flash')

@app.get("/")
def home():
    return FileResponse("index.html")

@app.post("/get_audio_url")
async def get_audio_url(url: str = Form(...)):
    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'extractor_args': {'youtube': {'player_client': ['android', 'web']}}
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {"status": "success", "audio_url": info['url'], "title": info.get('title', '요리 영상')}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/summarize")
async def summarize_recipe(transcript: str = Form(...), video_title: str = Form(...)):
    try:
        prompt = f"요리 전문가로서 다음 내용을 요리 이름, 재료, 순서, 꿀팁으로 요약해줘. 마크다운(**) 금지.\n\n제목: {video_title}\n내용: {transcript[:8000]}"
        response = gemini_model.generate_content(prompt)
        return {"status": "success", "recipe": response.text.strip()}
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)