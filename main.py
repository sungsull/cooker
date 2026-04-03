import os
import re
import hashlib
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
from groq import Groq
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# 1. CORS 설정 (재욱님의 기존 설정 유지)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# 2. 환경변수 및 클라이언트 설정
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")

groq_client = Groq(api_key=GROQ_API_KEY)
youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

class VideoURL(BaseModel):
    url: str

# 캐시 및 설정
cache = {}
MAX_TRANSCRIPT_LENGTH = 6000 

# ---------------------------
# [Backend Logic] 유틸리티 함수
# ---------------------------
def get_video_id(url: str):
    """쇼츠, 일반 영상, 단축 주소 완벽 대응 정규식"""
    pattern = r'(?:v=|\/shorts\/|youtu\.be\/)([a-zA-Z0-9_-]{11})'
    match = re.search(pattern, url)
    if match:
        return match.group(1)
    if "v=" in url: return url.split("v=")[-1].split("&")[0]
    return url.split("/")[-1]

def get_transcript(video_id: str):
    """자막 추출 및 한국어 번역 (안정성 강화)"""
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        try:
            transcript = transcript_list.find_transcript(['ko'])
        except:
            try:
                transcript = transcript_list.find_transcript(['en', 'ja', 'zh']).translate('ko')
            except:
                transcript = next(iter(transcript_list)).translate('ko')
        
        text = " ".join([t['text'] for t in transcript.fetch()])
        return text[:MAX_TRANSCRIPT_LENGTH]
    except:
        return ""

def generate_recipe(title, content):
    """재욱님의 지침 + 무한 루프 방지 로직 결합"""
    prompt = f"""
동영상 제목: {title}
내용: {content}

위 내용을 바탕으로 실제 '조리법'을 요약해. 
**계량 및 내용 정확도 지침:**
1. **정확한 분량 추출**: 자막에서 재료를 넣는 장면을 끝까지 확인하고, 최종적으로 들어간 양(예: 1큰술, 100g, 1/2개)을 정확히 기재해. 
자막에 숫자가 상충하면 가장 마지막에 언급된 값을 우선해.
분량이 기재되어 있지 않으면 재료 이름만 써.
2. **불필요한 정보 제거**: '인트로', '00:00' 같은 타임라인과 '구독/좋아요' 멘트는 100% 삭제해.
3. **조리 동작 중심**: 실제 요리 순서대로 번호를 매겨서 간결하게 작성해.
요리이름에 쓸데없는 수식어는 빼고, 핵심 명칭만 써. 예를 들어 '맛있는 김치찌개 끓이는 법'은 '김치찌개'처럼 요리 이름만 작성해.

형식:
요리 이름: (핵심 명칭)

재료: (자막에 언급된 모든 식재료 나열)
순서: (1번부터 번호를 매겨서, 실제 요리 순서대로 상세히 기술)

팁: (요리 꿀팁이 있다면 작성하고, 없으면 '없음'이라고 작성)

반드시 한국어로 작성하고, 가독성 좋게 줄바꿈을 사용해.
"""
    try:
        chat_completion = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": "너는 중복을 피하고 핵심만 짚는 요리 레시피 요약 전문가야."},
                {"role": "user", "content": prompt}
            ],
            model="llama-3.1-8b-instant",
            temperature=1,              # 정확도 고정
            top_p=0-.1,
            frequency_penalty=1.2,     # 다진 마늘 루프 방지 (강력 처방)
            presence_penalty=0.5,      # 내용 정체 방지
        )
        return chat_completion.choices[0].message.content.strip()
    except Exception as e:
        return f"요약 중 오류 발생: {str(e)}"

# ---------------------------
# [Frontend] 재욱님의 원본 UI (HTML/CSS)
# ---------------------------
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
        /* 재욱님의 원본 스타일 복원 */
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
      <h1>🍳 Cooker</h1>
      <p class="sub-title">유튜브 요리 영상 레시피 추출</p>
      <div class="card">
        <div class="input-group">
          <input id="urlInput" type="text" placeholder="유튜브 링크를 입력하세요" />
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
            alert("서버 연결 실패");
          } finally {
            loader.style.display = 'none';
            btn.disabled = false;
          }
        }
      </script>
    </body>
    </html>
    """

# ---------------------------
# [API Endpoint]
# ---------------------------
@app.post("/cook")
def cook(item: VideoURL):
    try:
        video_id = get_video_id(item.url)
        if not video_id:
            return {"status": "error", "message": "URL 인식 실패"}

        cache_key = hashlib.md5(video_id.encode()).hexdigest()
        if cache_key in cache:
            return {"status": "success", "recipe": cache[cache_key]}

        video_response = youtube.videos().list(part="snippet", id=video_id).execute()
        if not video_response['items']:
            return {"status": "error", "message": "영상을 찾을 수 없습니다."}

        snippet = video_response['items'][0]['snippet']
        title = snippet['title']
        description = snippet['description'][:1000]
        transcript = get_transcript(video_id)
        
        # 자막이 부실할 것을 대비해 설명란(description)도 함께 전달
        combined_content = f"설명글: {description}\n\n자막내용: {transcript if transcript else '없음'}"
        
        recipe = generate_recipe(title, combined_content)
        
        cache[cache_key] = recipe
        return {"status": "success", "recipe": recipe}
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
