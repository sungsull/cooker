import os
import time
import hashlib
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
from google import genai
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# 환경변수 로드
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")

# 클라이언트 초기화
client = genai.Client(api_key=GEMINI_API_KEY)
youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

class VideoURL(BaseModel):
    url: str

# 메모리 캐시 및 설정
cache = {}
MAX_TRANSCRIPT_LENGTH = 4000  # 2.5버전은 넉넉하니 4000자까지!
REQUEST_DELAY = 1.0

# ---------------------------
# 유틸리티 함수
# ---------------------------
def get_video_id(url: str):
    if "v=" in url: return url.split("v=")[-1].split("&")[0]
    elif "youtu.be/" in url: return url.split("/")[-1].split("?")[0]
    return url.split("/")[-1]

def get_transcript(video_id: str):
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        try:
            transcript = transcript_list.find_transcript(['ko', 'en'])
        except:
            transcript = next(iter(transcript_list)).translate('ko')
        text = " ".join([t['text'] for t in transcript.fetch()])
        return text[:MAX_TRANSCRIPT_LENGTH]
    except:
        return None

def make_cache_key(video_id: str):
    return hashlib.md5(video_id.encode()).hexdigest()

# ---------------------------
# Gemini 2.5 Flash 호출
# ---------------------------
def generate_recipe(title, content):
    prompt = f"제목: {title}\n내용: {content}\n\n위 내용을 바탕으로 요리 이름, 재료, 상세 조리 순서, 팁 순서로 친절하게 요약해줘. 특수문자(*, #)는 쓰지 마."
    
    for attempt in range(2):
        try:
            time.sleep(REQUEST_DELAY)
            # 아까 캡처에서 확인한 한도 살아있는 모델!
            response = client.models.generate_content(
                model="models/gemini-2.5-flash", 
                contents=prompt
            )
            return response.text.strip()
        except Exception as e:
            if "429" in str(e):
                time.sleep(2)
                continue
            raise e
    return "요약 요청이 너무 많습니다. 잠시 후 다시 시도해주세요."

# ---------------------------
# 메인 UI 및 API
# ---------------------------
@app.get("/", response_class=HTMLResponse)
def root():
    return """
    <!DOCTYPE html>
    <html lang="ko">
    <head>
      <meta charset="UTF-8" />
      <title>Cooker </title>
      <link href="https://fonts.googleapis.com/css2?family=Gowun+Dodum&display=swap" rel="stylesheet">
      <style>
        body { background: #fdfdf5; font-family: 'Gowun Dodum', sans-serif; display: flex; flex-direction: column; align-items: center; padding: 50px; margin: 0; }
        h1 { color: #5a5a4a; margin-bottom: 10px; }
        .sub-title { color: #8a8a7a; margin-bottom: 30px; font-size: 0.9rem; }
        .card { background: white; padding: 30px; border-radius: 25px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); width: 100%; max-width: 550px; text-align: center; }
        .input-group { display: flex; gap: 10px; margin-bottom: 20px; }
        input { flex: 1; padding: 15px; border: 2px solid #eef5e1; border-radius: 15px; outline: none; transition: 0.3s; font-family: inherit; }
        input:focus { border-color: #c8e6a0; }
        button { padding: 0 25px; background: #c8e6a0; border: none; border-radius: 15px; font-weight: bold; color: #4a5a3a; cursor: pointer; transition: 0.3s; }
        button:hover { background: #b8d690; transform: translateY(-2px); }
        button:disabled { background: #eee; cursor: not-allowed; }
        #result { margin-top: 25px; white-space: pre-wrap; line-height: 1.8; background: #f9f9f0; padding: 20px; border-radius: 15px; display: none; text-align: left; color: #444; border-left: 5px solid #c8e6a0; }
        .loader { display: none; margin: 20px auto; border: 4px solid #f3f3f3; border-top: 4px solid #c8e6a0; border-radius: 50%; width: 30px; height: 30px; animation: spin 1s linear infinite; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
      </style>
    </head>
    <body>
      <h1> Cooker</h1>
      <p class="sub-title">유튜브 요리 레시피를 요약해드립니다</p>
      <div class="card">
        <div class="input-group">
          <input id="urlInput" type="text" placeholder="여기에 유튜브 링크를 붙여넣으세요" />
          <button id="btn" onclick="fetchRecipe()">요약</button>
        </div>
        <div id="loader" class="loader"></div>
        <div id="result"></div>
      </div>

      <script>
        async function fetchRecipe() {
          const url = document.getElementById('urlInput').value;
          const resDiv = document.getElementById('result');
          const loader = document.getElementById('loader');
          const btn = document.getElementById('btn');

          if(!url) return alert("링크를 입력해주세요!");
          
          resDiv.style.display = 'none';
          loader.style.display = 'block';
          btn.disabled = true;
          
          try {
            const response = await fetch('/cook', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ url })
            });
            const data = await response.json();
            if(data.status === 'success') {
              resDiv.innerText = data.recipe;
              resDiv.style.display = 'block';
            } else {
              alert("에러: " + data.message);
            }
          } catch (e) {
            alert("서버와 통신에 실패했습니다.");
          } finally {
            loader.style.display = 'none';
            btn.disabled = false;
          }
        }
      </script>
    </body>
    </html>
    """

@app.post("/cook")
def cook(item: VideoURL):
    try:
        video_id = get_video_id(item.url)
        cache_key = make_cache_key(video_id)

        if cache_key in cache:
            return {"status": "success", "recipe": cache[cache_key]}

        video = youtube.videos().list(part="snippet", id=video_id).execute()
        if not video['items']:
            return {"status": "error", "message": "영상을 찾을 수 없습니다."}

        snippet = video['items'][0]['snippet']
        title = snippet['title']
        description = snippet['description'][:500]
        transcript = get_transcript(video_id)
        
        content = transcript if transcript else description
        recipe = generate_recipe(title, content)
        
        cache[cache_key] = recipe
        return {"status": "success", "recipe": recipe}
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
