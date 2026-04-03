import os
import time
import glob
import uuid
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import yt_dlp
from google import genai
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept"],
    expose_headers=["*"],
)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("환경변수 GEMINI_API_KEY가 설정되지 않았습니다.")

client = genai.Client(api_key=GEMINI_API_KEY)

class VideoURL(BaseModel):
    url: str

@app.get("/", response_class=HTMLResponse)
def root():
    return """<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Cooker </title>
  <link href="https://fonts.googleapis.com/css2?family=Gowun+Dodum&family=Nanum+Myeongjo:wght@400;700&display=swap" rel="stylesheet"/>
  <style>
    :root {
      --green:   #c8e6a0;
      --green2:  #e8f5d0;
      --cream:   #fdfdf5;
      --text:    #3a3a2e;
      --sub:     #7a7a60;
      --red:     #e57373;
      --shadow:  0 4px 24px rgba(100,120,60,.10);
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--cream);
      font-family: 'Gowun Dodum', sans-serif;
      color: var(--text);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 48px 16px 80px;
    }
    header { text-align: center; margin-bottom: 40px; }
    header h1 { font-family: 'Nanum Myeongjo', serif; font-size: 2.2rem; font-weight: 700; }
    header p { margin-top: 6px; color: var(--sub); font-size: .95rem; }
    .card { background: white; border-radius: 24px; box-shadow: var(--shadow); padding: 32px 28px; width: 100%; max-width: 560px; }
    .input-wrap { display: flex; align-items: center; gap: 10px; border: 1.5px solid #d4e8b0; border-radius: 12px; padding: 10px 14px; background: var(--green2); }
    .input-wrap input { flex: 1; border: none; background: transparent; outline: none; font-family: 'Gowun Dodum', sans-serif; font-size: 1rem; }
    button#submitBtn { margin-top: 16px; width: 100%; padding: 14px; background: var(--green); border: none; border-radius: 12px; font-weight: 700; cursor: pointer; }
    button#submitBtn:disabled { background: #ddd; }
    .result-box { margin-top: 28px; background: var(--green2); border-radius: 16px; padding: 24px 20px; white-space: pre-wrap; line-height: 1.9; }
    .copy-btn { display: none; margin-top: 14px; background: none; border: 1px solid #ccc; border-radius: 8px; padding: 6px 14px; cursor: pointer; float: right; }
    .copy-btn.visible { display: inline-block; }
    .spinner { display: inline-block; width: 18px; height: 18px; border: 2px solid #aaa; border-top-color: var(--text); border-radius: 50%; animation: spin .7s linear infinite; vertical-align: middle; margin-right: 8px; }
    @keyframes spin { to { transform: rotate(360deg); } }
  </style>
</head>
<body>
<header>
  <h1> Cooker</h1>
  <p>유튜브 요리 영상 링크를 붙여넣으면 레시피를 정리해드립니다</p>
</header>
<div class="card">
  <div class="input-wrap">
    <input id="urlInput" type="url" placeholder="유튜브 링크를 입력하세요..." />
  </div>
  <button id="submitBtn" onclick="fetchRecipe()">레시피 요약하기</button>
  <div class="result-box" id="result"> 요약 실행하기</div>
  <button class="copy-btn" id="copyBtn" onclick="copyResult()"> 레시피 복사</button>
</div>
<script>
  async function fetchRecipe() {
    const input = document.getElementById('urlInput');
    const btn = document.getElementById('submitBtn');
    const result = document.getElementById('result');
    const copyBtn = document.getElementById('copyBtn');
    const url = input.value.trim();
    if (!url) return;

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span>분석 중...';
    result.innerText = 'AI가 영상을 분석하고 있습니다... ';
    copyBtn.classList.remove('visible');

    try {
      const res = await fetch('/cook', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url })
      });
      const data = await res.json();
      if (data.status === 'success') {
        result.innerText = data.recipe;
        copyBtn.classList.add('visible');
      } else {
        result.innerText = '❌ 오류: ' + data.message;
      }
    } catch (e) {
      result.innerText = '❌ 연결 오류가 발생했습니다.';
    } finally {
      btn.disabled = false;
      btn.innerHTML = '레시피 요약하기';
    }
  }
  function copyResult() {
    navigator.clipboard.writeText(document.getElementById('result').innerText);
    alert('복사되었습니다!');
  }
</script>
</body>
</html>"""

@app.post("/cook")
def create_recipe(item: VideoURL):
    unique_id = uuid.uuid4().hex
    audio_template = f"temp_audio_{unique_id}"
    audio_path = None
    uploaded_file = None

    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'{audio_template}.%(ext)s',
            'quiet': True,
            'nocheckcertificate': True,
            'extractor_args': {'youtube': {'player_client': ['web_creator', 'android']}},
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([item.url])

        matched = glob.glob(f"{audio_template}.*")
        if not matched:
            return {"status": "error", "message": "다운로드 실패 (유튜브 차단)"}
        
        audio_path = matched[0]
        # 확장자 확인 (.m4a, .webm 등)
        mime_type = "audio/mp4" if audio_path.endswith(".m4a") else "audio/webm"

        uploaded_file = client.files.upload(file=audio_path, config={"mime_type": mime_type})

        while uploaded_file.state == "PROCESSING":
            time.sleep(2)
            uploaded_file = client.files.get(name=uploaded_file.name)

        prompt = "요리 영상 오디오야. 1. 요리이름 2. 재료 3. 순서 4. 팁 순서로 친절하게 요약해줘. 특수문자(*)는 쓰지마."
        response = client.models.generate_content(model="gemini-1.5-flash", contents=[uploaded_file, prompt])

        return {"status": "success", "recipe": response.text.strip()}

    except Exception as e:
        return {"status": "error", "message": str(e)}

    finally:
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)
        if uploaded_file:
            try: client.files.delete(name=uploaded_file.name)
            except: pass

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
