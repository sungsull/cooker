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

# CORS 설정: 플러터 앱 및 외부 접근 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# 환경변수 로드 (Render 대시보드 설정 확인)
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")

# 클라이언트 초기화
groq_client = Groq(api_key=GROQ_API_KEY)
youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

class VideoURL(BaseModel):
    url: str

# 메모리 캐시 및 설정
cache = {}
MAX_TRANSCRIPT_LENGTH = 5000 

# ---------------------------
# 1. 유튜브 ID 추출 (쇼츠/일반/단축 주소 완벽 대응)
# ---------------------------
def get_video_id(url: str):
    pattern = r'(?:v=|\/shorts\/|youtu\.be\/)([a-zA-Z0-9_-]{11})'
    match = re.search(pattern, url)
    if match:
        return match.group(1)
    return None

# ---------------------------
# 2. 자막 추출 로직 (한국어 우선 및 자동번역)
# ---------------------------
def get_transcript(video_id: str):
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        try:
            transcript = transcript_list.find_transcript(['ko'])
        except:
            try:
                # 영어, 일본어, 중국어 자막을 한국어로 자동번역 시도
                transcript = transcript_list.find_transcript(['en', 'ja', 'zh']).translate('ko')
            except:
                # 그 외 가능한 첫 번째 자막을 한국어로 번역
                transcript = next(iter(transcript_list)).translate('ko')
        
        text = " ".join([t['text'] for t in transcript.fetch()])
        return text[:MAX_TRANSCRIPT_LENGTH]
    except:
        return ""

# ---------------------------
# 3. 레시피 생성 (무한 루프 방지 및 쇼츠 최적화)
# ---------------------------
def generate_recipe(title, content):
    # 8b 모델이 길을 잃지 않도록 구조화된 프롬프트 사용
    prompt = f"""
동영상 제목: {title}
자막 및 내용: {content}

[수행 과제] 위 내용을 바탕으로 실제 '조리법'을 요약해.

[필수 지침 - 반드시 준수]
1. 요리 이름: 요리이름에 쓸데없는 수식어는 빼고, 핵심 명칭만 써. 예를 들어 '김치찌개', '김밥'처럼 핵심 명칭만 작성해.
2. 정확한 분량: 들어간 양(예: 1큰술, 100g, 1/2개)을 정확히 기재해. 분량이 기재되어 있지 않으면 재료 이름만 써.
3. 중복 제거: **동일한 재료나 단어를 무의미하게 반복(Loop)하지 마.** 중복 재료는 한 번만 리스트업해.
2. **불필요한 정보 제거**: '인트로', '00:00' 같은 타임라인과 '구독/좋아요' 멘트는 100% 삭제해.
3. **조리 동작 중심**: 실제 요리 순서대로 번호를 매겨서 간결하게 작성해.

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
                {"role": "system", "content": "너는 중복 없이 정확한 정보만 추출하는 전문 요리 레시피 요약기야."},
                {"role": "user", "content": prompt}
            ],
            model="llama-3.1-8b-instant",
            temperature=0.1,         # 정확도 유지를 위해 낮게 설정
            frequency_penalty=0.8,   # 동일 단어 무한 반복(다진 마늘 지옥) 방지
            presence_penalty=0.5,    # 내용이 한 곳에 머물지 않도록 유도
        )
        return chat_completion.choices[0].message.content.strip()
    except Exception as e:
        return f"요약 중 오류 발생: {str(e)}"

# ---------------------------
# 4. 웹 UI (HTML/CSS/JS)
# ---------------------------
@app.get("/", response_class=HTMLResponse)
def root():
    return """
    <!DOCTYPE html>
    <html lang="ko">
    <head>
      <meta charset="UTF-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>Cooker - 레시피 추출기</title>
      <link href="https://fonts.googleapis.com/css2?family=Gowun+Dodum&display=swap" rel="stylesheet">
      <style>
        body { background: #fdfdf5; font-family: 'Gowun Dodum', sans-serif; display: flex; flex-direction: column; align-items: center; padding: 20px; margin: 0; min-height: 100vh; }
        h1 { color: #5a5a4a; margin-top: 40px; margin-bottom: 5px; }
        .sub-title { color: #8a8a7a; margin-bottom: 30px; font-size: 0.9rem; }
        .card { background: white; padding: 25px; border-radius: 25px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); width: 100%; max-width: 500px; text-align: center; }
        .input-group { display: flex; gap: 8px; margin-bottom: 20px; }
        input { flex: 1; padding: 14px; border: 2px solid #eef5e1; border-radius: 15px; outline: none; transition: 0.3s; font-family: inherit; font-size: 0.95rem; }
        input:focus { border-color: #c8e6a0; }
        button { padding: 0 20px; background: #c8e6a0; border: none; border-radius: 15px; font-weight: bold; color: #4a5a3a; cursor: pointer; transition: 0.2s; font-family: inherit; }
        button:hover { background: #b8d690; transform: translateY(-1px); }
        button:disabled { background: #eee; cursor: not-allowed; }
        #result { margin-top: 25px; white-space: pre-wrap; line-height: 1.8; background: #f9f9f0; padding: 20px; border-radius: 15px; display: none; text-align: left; color: #444; border-left: 5px solid #c8e6a0; font-size: 0.95rem; }
        .loader { display: none; margin: 20px auto; border: 4px solid #f3f3f3; border-top: 4px solid #c8e6a0; border-radius: 50%; width: 28px; height: 28px; animation: spin 1s linear infinite; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
      </style>
    </head>
    <body>
      <h1>🍳 Cooker</h1>
      <p class="sub-title">유튜브 영상을 텍스트 레시피로 요약합니다</p>
      <div class="card">
        <div class="input-group">
          <input id="urlInput" type="text" placeholder="유튜브 영상 또는 쇼츠 링크 입력" />
          <button id="btn" onclick="fetchRecipe()">추출</button>
        </div>
        <div id="loader" class="loader"></div>
        <div id="result"></div>
      </div>
      <script>
        async function fetchRecipe() {
          const url = document.getElementById('urlInput').value.trim();
          const resDiv = document.getElementById('result');
          const loader = document.getElementById('loader');
          const btn = document.getElementById('btn');
          
          if(!url) { alert("유튜브 주소를 입력해주세요!"); return; }
          
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
              alert("실패: " + data.message);
            }
          } catch (e) {
            alert("서버 통신 실패. 대시보드를 확인하세요.");
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
# 5. API 엔드포인트 로직
# ---------------------------
@app.post("/cook")
def cook(item: VideoURL):
    try:
        video_id = get_video_id(item.url)
        if not video_id:
            return {"status": "error", "message": "유효하지 않은 URL 형식입니다."}

        # 간단한 캐시 처리 (메모리)
        cache_key = hashlib.md5(video_id.encode()).hexdigest()
        if cache_key in cache:
            return {"status": "success", "recipe": cache[cache_key]}

        # YouTube Data API로 영상 정보 호출
        video_response = youtube.videos().list(part="snippet", id=video_id).execute()
        if not video_response['items']:
            return {"status": "error", "message": "영상을 찾을 수 없습니다."}

        snippet = video_response['items'][0]['snippet']
        title = snippet['title']
        description = snippet['description'][:1000]
        transcript = get_transcript(video_id)
        
        # 모델 입력 데이터 구성
        combined_content = f"제목: {title}\n설명: {description}\n자막내용: {transcript if transcript else '자막 없음'}"
        
        # 레시피 생성 함수 호출
        recipe = generate_recipe(title, combined_content)
        
        cache[cache_key] = recipe
        return {"status": "success", "recipe": recipe}
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    # Render 환경의 PORT 환경 변수 대응
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
