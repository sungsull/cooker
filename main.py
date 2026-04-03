import os
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
from google import genai
from google.genai import types  # 추가 설정용
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# API 키 설정
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")

# [핵심 수정] v1 정식 버전을 사용하도록 클라이언트 설정
# http_options를 통해 API 버전을 v1으로 고정합니다.
client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options={'api_version': 'v1'}
)

youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

class VideoURL(BaseModel):
    url: str

def get_video_id(url: str):
    if "v=" in url: return url.split("v=")[-1].split("&")[0]
    elif "youtu.be/" in url: return url.split("youtu.be/")[-1].split("?")[0]
    return url.split("/")[-1]

def get_transcript_robustly(video_id: str):
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        try:
            transcript = transcript_list.find_transcript(['ko', 'ko-KR', 'en'])
        except:
            first = next(iter(transcript_list))
            transcript = first.translate('ko')
        return " ".join([t['text'] for t in transcript.fetch()])
    except:
        return None

@app.get("/", response_class=HTMLResponse)
def root():
    return """
    <!DOCTYPE html>
    <html lang="ko">
    <head>
      <meta charset="UTF-8" />
      <title>Cooker</title>
      <link href="https://fonts.googleapis.com/css2?family=Gowun+Dodum&display=swap" rel="stylesheet">
      <style>
        body { background: #fdfdf5; font-family: 'Gowun Dodum', sans-serif; display: flex; flex-direction: column; align-items: center; padding: 50px; }
        .card { background: white; padding: 30px; border-radius: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); width: 100%; max-width: 500px; }
        input { width: 100%; padding: 12px; border: 1px solid #d4e8b0; border-radius: 10px; margin-bottom: 10px; outline: none; }
        button { width: 100%; padding: 12px; background: #c8e6a0; border: none; border-radius: 10px; font-weight: bold; cursor: pointer; }
        #result { margin-top: 20px; white-space: pre-wrap; line-height: 1.6; background: #f9f9f0; padding: 15px; border-radius: 10px; display: none; }
        .loading { color: #7a7a60; font-size: 0.9rem; margin-top: 10px; display: none; }
      </style>
    </head>
    <body>
      <h1>Cooker</h1>
      <p>유튜브 요리 영상 링크를 레시피로 바꿔드려요</p>
      <div class="card">
        <input id="urlInput" type="text" placeholder="유튜브 링크를 붙여넣으세요" />
        <button onclick="fetchRecipe()">레시피 요약하기</button>
        <div id="loading" class="loading">AI가 열심히 영상을 분석 중입니다...</div>
        <div id="result"></div>
      </div>
      <script>
        async function fetchRecipe() {
          const url = document.getElementById('urlInput').value;
          const resDiv = document.getElementById('result');
          const loading = document.getElementById('loading');
          if(!url) return alert("링크를 입력해주세요!");
          resDiv.style.display = 'none'; loading.style.display = 'block';
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
            } else { alert(data.message); }
          } catch (e) { alert("서버 연결에 실패했습니다."); }
          finally { loading.style.display = 'none'; }
        }
      </script>
    </body>
    </html>
    """

@app.post("/cook")
def create_recipe(item: VideoURL):
    try:
        video_id = get_video_id(item.url)
        video_response = youtube.videos().list(part="snippet", id=video_id).execute()
        if not video_response['items']:
            return {"status": "error", "message": "영상을 찾을 수 없습니다."}
        
        snippet = video_response['items'][0]['snippet']
        title = snippet['title']
        description = snippet['description'][:800]
        full_text = get_transcript_robustly(video_id)
        
        content_source = full_text if full_text else description
        
        # v1 통로를 통해 gemini-1.5-flash 호출
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=f"제목: {title}\\n내용: {content_source}\\n\\n요리 이름, 재료, 순서, 팁 순으로 요약해줘. 특수문자(*)는 쓰지마."
        )
        return {"status": "success", "recipe": response.text.strip()}
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
