import os
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

# API 키 설정
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")

# 클라이언트 초기화
client = genai.Client(api_key=GEMINI_API_KEY)
youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

class VideoURL(BaseModel):
    url: str

def get_video_id(url: str):
    if "v=" in url: return url.split("v=")[-1].split("&")[0]
    elif "youtu.be/" in url: return url.split("youtu.be/")[-1].split("?")[0]
    return url.split("/")[-1]

def get_transcript_robustly(video_id: str):
    """CC 자막을 샅샅이 뒤져서 가져오는 로직"""
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        try:
            # 수동/자동 포함 한국어 우선 시도
            transcript = transcript_list.find_transcript(['ko', 'ko-KR', 'en'])
        except:
            # 안 되면 첫 번째 자막을 한국어로 번역
            first = next(iter(transcript_list))
            transcript = first.translate('ko')
        return " ".join([t['text'] for t in transcript.fetch()])
    except:
        return None

@app.get("/", response_class=HTMLResponse)
def root():
    # 재욱님 디자인 유지 (이모티콘 및 불필요 문구 제거)
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
        
        # 404 에러 방지를 위해 모델명을 문자열로 정확히 전달
        # 최신 google-genai는 이 방식을 가장 잘 인식합니다.
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=f"제목: {title}\\n내용: {content_source}\\n\\n요리 이름, 재료, 순서, 팁 순으로 요약해줘. 특수문자(*)는 쓰지마."
        )
        return {"status": "success", "recipe": response.text.strip()}
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    # Render 환경에서 "0.0.0.0"은 필수입니다.
    uvicorn.run(app, host="0.0.0.0", port=port)
