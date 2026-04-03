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

# 1. CORS 설정: 브라우저에서 서버로의 접근을 허용합니다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# 2. 환경 변수 설정 (보안을 위해 직접 입력하지 않고 서버 설정에서 가져옵니다)
# 로컬 테스트 시에는 아래 "YOUR_KEY" 부분에 직접 넣어서 테스트하세요.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "YOUR_YOUTUBE_API_KEY_HERE")

# 서비스 클라이언트 초기화
client = genai.Client(api_key=GEMINI_API_KEY)
youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

class VideoURL(BaseModel):
    url: str

def get_video_id(url: str):
    """유튜브 주소에서 비디오 ID를 추출합니다."""
    if "v=" in url:
        return url.split("v=")[-1].split("&")[0]
    elif "youtu.be/" in url:
        return url.split("youtu.be/")[-1].split("?")[0]
    return url.split("/")[-1]

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
        :root {
          --green: #c8e6a0; --green2: #e8f5d0; --cream: #fdfdf5;
          --text: #3a3a2e; --sub: #7a7a60; --shadow: 0 4px 20px rgba(0,0,0,0.08);
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
          background: var(--cream); font-family: 'Gowun Dodum', sans-serif;
          color: var(--text); display: flex; flex-direction: column; align-items: center; padding: 50px 20px;
        }
        header { text-align: center; margin-bottom: 40px; }
        header h1 { font-family: 'Nanum Myeongjo', serif; font-size: 2.5rem; margin-bottom: 10px; }
        .card {
          background: white; border-radius: 24px; box-shadow: var(--shadow);
          padding: 35px; width: 100%; max-width: 550px;
        }
        .input-wrap { display: flex; gap: 10px; margin-bottom: 15px; }
        input {
          flex: 1; padding: 14px; border: 1.5px solid var(--green);
          border-radius: 12px; outline: none; font-size: 1rem;
        }
        button {
          width: 100%; padding: 15px; background: var(--green); border: none;
          border-radius: 12px; font-weight: bold; font-size: 1.1rem; cursor: pointer; transition: 0.2s;
        }
        button:hover { background: #b8d690; }
        button:disabled { background: #ccc; cursor: not-allowed; }
        #loading { display: none; margin-top: 20px; text-align: center; color: var(--sub); }
        #result {
          display: none; margin-top: 30px; padding: 25px;
          background: var(--green2); border-radius: 18px; line-height: 1.8; white-space: pre-wrap;
        }
      </style>
    </head>
    <body>
      <header>
        <h1> Cooker</h1>
        <p>유튜브 요리 영상 링크를 붙여넣으면 레시피를 정리해드립니다</p>
      </header>
      <div class="card">
        <input id="urlInput" type="text" placeholder="유튜브 링크를 입력하세요..." />
        <button id="submitBtn" onclick="fetchRecipe()">레시피 요약하기</button>
        <div id="loading">🍳 AI가 영상을 요약 중입니다...</div>
        <div id="result"></div>
      </div>

      <script>
        async function fetchRecipe() {
          const urlInput = document.getElementById('urlInput');
          const btn = document.getElementById('submitBtn');
          const result = document.getElementById('result');
          const loading = document.getElementById('loading');
          
          if (!urlInput.value.trim()) return alert("링크를 입력해주세요!");

          btn.disabled = true;
          result.style.display = 'none';
          loading.style.display = 'block';

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
              alert("❌ 오류: " + data.message);
            }
          } catch (e) {
            alert("서버 연결 실패! 잠시 후 다시 시도해주세요.");
          } finally {
            btn.disabled = false;
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

        # 1. YouTube Data API v3: 제목 가져오기 (쿼터 1 소모)
        video_response = youtube.videos().list(part="snippet", id=video_id).execute()
        if not video_response['items']:
            return {"status": "error", "message": "영상을 찾을 수 없습니다."}
        
        title = video_response['items'][0]['snippet']['title']

        # 2. Transcript API: 자막 추출 (공식 쿼터 소모 없음)
        try:
            transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko', 'en'])
            full_text = " ".join([t['text'] for t in transcript])
        except:
            return {"status": "error", "message": "자막이 없는 영상입니다. 자막 설정이 된 영상을 사용해주세요!"}

        # 3. Gemini AI: 레시피 요약
        prompt = f"""
        영상 제목: {title}
        자막 내용: {full_text}

        위 정보를 바탕으로 요리 레시피를 정리해줘.
        1. 요리 이름
        2. 핵심 재료 (계량 포함)
        3. 요리 순서 (단계별로 상세히)
        4. 전문가의 꿀팁
        - 답변은 아주 친절하게 해주고, 별표(*) 같은 특수문자는 쓰지 말고 텍스트로만 정리해줘.
        """

        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt
        )

        return {"status": "success", "recipe": response.text.strip()}

    except Exception as e:
        return {"status": "error", "message": f"서버 내부 오류: {str(e)}"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
