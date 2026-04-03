import os
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
from google import genai
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_GEMINI_KEY")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "YOUR_YOUTUBE_KEY")

client = genai.Client(api_key=GEMINI_API_KEY)
youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

class VideoURL(BaseModel):
    url: str

def get_video_id(url: str):
    if "v=" in url:
        return url.split("v=")[-1].split("&")[0]
    elif "youtu.be/" in url:
        return url.split("youtu.be/")[-1].split("?")[0]
    return url.split("/")[-1]

def get_transcript_robustly(video_id: str):
    """자막 목록을 싹 다 뒤져서 뭐라도 가져오는 최종 병기 로직"""
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # 1. 한국어 관련 모든 자막(수동/자동/KR/ko 등)을 우선 시도
        try:
            # 최대한 관대하게 'ko'가 포함된 자막을 찾습니다.
            transcript = transcript_list.find_transcript(['ko', 'ko-KR', 'en'])
        except:
            # 2. 만약 없다면, 목록에 있는 첫 번째 자막을 가져와서 한국어로 번역 시도
            try:
                # 사용 가능한 첫 번째 자막을 그냥 집어듭니다.
                first_transcript = next(iter(transcript_list))
                transcript = first_transcript.translate('ko')
            except:
                return None
        
        return " ".join([t['text'] for t in transcript.fetch()])
    except Exception as e:
        print(f"로그: 자막 추출 실패 원인 -> {e}")
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
          resDiv.style.display = 'none';
          loading.style.display = 'block';
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
              alert(data.message);
            }
          } catch (e) {
            alert("서버 연결에 실패했습니다.");
          } finally {
            loading.style.display = 'none';
          }
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
        description = snippet['description'][:1000] # 자막 실패 대비 설명란 확보

        full_text = get_transcript_robustly(video_id)
        
        # 자막 추출에 실패했을 때, 설명란(Description)을 대신 사용하는 '생존 로직' 추가
        content_source = full_text if full_text else description
        
        if not content_source or len(content_source) < 20:
             return {"status": "error", "message": "영상 정보를 읽어올 수 없습니다. 다른 영상을 시도해 주세요!"}

        prompt = f"제목: {title}\n내용: {content_source}\n\n위 내용을 바탕으로 요리 이름, 재료, 순서, 팁 순서로 요약해줘. 특수문자(*)는 사용하지 마."
        
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt
        )
        return {"status": "success", "recipe": response.text.strip()}
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
