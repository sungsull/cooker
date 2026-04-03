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

# 1. CORS 설정 (배포 시 필수)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# 2. API 키 설정 (환경 변수)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_GEMINI_KEY")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "YOUR_YOUTUBE_KEY")

# 3. 서비스 클라이언트 초기화
# 최신 google-genai 라이브러리 규격을 따릅니다.
client = genai.Client(api_key=GEMINI_API_KEY)
youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

class VideoURL(BaseModel):
    url: str

def get_video_id(url: str):
    """유튜브 URL에서 ID 추출"""
    if "v=" in url:
        return url.split("v=")[-1].split("&")[0]
    elif "youtu.be/" in url:
        return url.split("youtu.be/")[-1].split("?")[0]
    return url.split("/")[-1]

def get_transcript_robustly(video_id: str):
    """CC가 있는 모든 영상을 샅샅이 뒤져서 자막을 가져오는 무적 로직"""
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # 1. 한국어(ko)나 영어(en) 수동/자동 자막을 우선 검색
        try:
            transcript = transcript_list.find_transcript(['ko', 'ko-KR', 'en'])
        except:
            # 2. 없으면 목록에 있는 첫 번째 자막을 가져와서 한국어로 번역 시도
            try:
                first_transcript = next(iter(transcript_list))
                transcript = first_transcript.translate('ko')
            except:
                return None
        
        return " ".join([t['text'] for t in transcript.fetch()])
    except Exception as e:
        print(f"로그: 자막 추출 실패 -> {e}")
        return None

@app.get("/", response_class=HTMLResponse)
def root():
    # 재욱님의 디자인과 문구 (이모티콘 제거 버전) 유지
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
        
        # 1. 유튜브 제목 및 설명 가져오기
        video_response = youtube.videos().list(part="snippet", id=video_id).execute()
        if not video_response['items']:
            return {"status": "error", "message": "영상을 찾을 수 없습니다."}
        
        snippet = video_response['items'][0]['snippet']
        title = snippet['title']
        description = snippet['description'][:1000]

        # 2. 자막 추출 (강화된 로직)
        full_text = get_transcript_robustly(video_id)
        
        # 자막이 정말 없을 경우 설명란을 활용하는 보험 로직
        content_source = full_text if full_text else description
        
        if not content_source or len(content_source) < 20:
             return {"status": "error", "message": "영상 정보를 충분히 가져오지 못했습니다."}

        # 3. Gemini 요약 (에러 해결을 위해 모델 이름 명시적 호출)
        # model="gemini-1.5-flash" 혹은 "models/gemini-1.5-flash" 둘 다 시도 가능하게 설계
        prompt = f"제목: {title}\n내용: {content_source}\n\n위 내용을 보고 요리 이름, 재료, 순서, 팁 순으로 친절하게 요약해줘. 특수문자(*)는 쓰지마."
        
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt
        )

        return {"status": "success", "recipe": response.text.strip()}

    except Exception as e:
        # 에러 발생 시 상세 내용을 확인하기 위해 에러 메시지 반환
        return {"status": "error", "message": f"오류 발생: {str(e)}"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
