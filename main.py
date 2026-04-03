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

# 1. CORS 설정: 모든 접속 허용 (배포 시 필수)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# 2. API 키 설정 (환경 변수 우선, 없으면 직접 입력)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_GEMINI_KEY")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "YOUR_YOUTUBE_KEY")

# 서비스 초기화
client = genai.Client(api_key=GEMINI_API_KEY)
youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

class VideoURL(BaseModel):
    url: str

def get_video_id(url: str):
    """유튜브 주소에서 ID를 정밀하게 추출"""
    if "v=" in url:
        return url.split("v=")[-1].split("&")[0]
    elif "youtu.be/" in url:
        return url.split("youtu.be/")[-1].split("?")[0]
    return url.split("/")[-1]

def get_transcript_robustly(video_id: str):
    """모든 종류의 자막(수동/자동, 한국어/영어)을 샅샅이 뒤지는 함수"""
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # 1순위: 한국어(ko) 또는 영어(en) 수동 자막 시도
        try:
            transcript = transcript_list.find_transcript(['ko', 'en'])
        except:
            # 2순위: 한국어/영어 자동 생성 자막이라도 가져오기
            try:
                transcript = transcript_list.find_generated_transcript(['ko', 'en'])
            except:
                # 3순위: 그 외 사용 가능한 아무 자막이나 한국어로 번역해서 가져오기
                transcript = transcript_list.find_transcript(['ko', 'en']).translate('ko')
        
        return " ".join([t['text'] for t in transcript.fetch()])
    except Exception as e:
        print(f"자막 추출 실패 상세 원인: {e}")
        return None

@app.get("/", response_class=HTMLResponse)
def root():
    return """
    <!DOCTYPE html>
    <html lang="ko">
    <head>
      <meta charset="UTF-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
      <title>Cooker </title>
      <link href="https://fonts.googleapis.com/css2?family=Gowun+Dodum&family=Nanum+Myeongjo:wght@700&display=swap" rel="stylesheet">
      <style>
        :root { --green: #c8e6a0; --green2: #e8f5d0; --cream: #fdfdf5; --text: #3a3a2e; --sub: #7a7a60; }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { background: var(--cream); font-family: 'Gowun Dodum', sans-serif; color: var(--text); display: flex; flex-direction: column; align-items: center; padding: 50px 20px; }
        .card { background: white; border-radius: 24px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); padding: 35px; width: 100%; max-width: 550px; }
        input { width: 100%; padding: 14px; border: 1.5px solid var(--green); border-radius: 12px; outline: none; margin-bottom: 15px; }
        button { width: 100%; padding: 15px; background: var(--green); border: none; border-radius: 12px; font-weight: bold; cursor: pointer; }
        button:disabled { background: #ccc; }
        #loading { display: none; margin-top: 20px; text-align: center; color: var(--sub); }
        #result { display: none; margin-top: 30px; padding: 25px; background: var(--green2); border-radius: 18px; line-height: 1.8; white-space: pre-wrap; }
      </style>
    </head>
    <body>
      <h1> Cooker</h1>
      <div class="card">
        <input id="urlInput" type="text" placeholder="유튜브 링크를 입력하세요..." />
        <button id="submitBtn" onclick="fetchRecipe()">레시피 요약하기</button>
        <div id="loading"> 분석 중입니다... </div>
        <div id="result"></div>
      </div>
      <script>
        async function fetchRecipe() {
          const urlInput = document.getElementById('urlInput');
          const btn = document.getElementById('submitBtn');
          const result = document.getElementById('result');
          const loading = document.getElementById('loading');
          
          if (!urlInput.value.trim()) return alert("링크를 입력해주세요!");
          btn.disabled = true; result.style.display = 'none'; loading.style.display = 'block';

          try {
            const response = await fetch('/cook', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ url: urlInput.value.trim() })
            });
            const data = await response.json();
            if (data.status === 'success') {
              result.innerText = data.recipe;
              result.style.display = 'block';
            } else {
              alert("오류: " + data.message);
            }
          } catch (e) {
            alert("서버 연결 실패!");
          } finally {
            btn.disabled = false; loading.style.display = 'none';
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

        # 1. 제목 가져오기
        video_response = youtube.videos().list(part="snippet", id=video_id).execute()
        if not video_response['items']:
            return {"status": "error", "message": "영상을 찾을 수 없습니다."}
        title = video_response['items'][0]['snippet']['title']

        # 2. 강력한 자막 추출 (수동/자동 모두 포함)
        full_text = get_transcript_robustly(video_id)
        
        if not full_text:
            return {"status": "error", "message": "자막(자동 생성 포함)이 없는 영상입니다. 다른 영상을 시도해 주세요!"}

        # 3. Gemini 요약
        prompt = f"영상제목: {title}\n자막: {full_text}\n\n위 내용을 보고 1.요리이름 2.재료(계량포함) 3.순서 4.팁 순서로 친절하게 요약해줘. 특수문자(*)는 쓰지마."
        
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
