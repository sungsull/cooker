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
  <title>Pastel Recipe 👨‍🍳</title>
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

    /* 헤더 */
    header {
      text-align: center;
      margin-bottom: 40px;
      animation: fadeDown .6s ease both;
    }
    header h1 {
      font-family: 'Nanum Myeongjo', serif;
      font-size: 2.2rem;
      font-weight: 700;
      letter-spacing: -.5px;
    }
    header p {
      margin-top: 6px;
      color: var(--sub);
      font-size: .95rem;
    }

    /* 카드 */
    .card {
      background: white;
      border-radius: 24px;
      box-shadow: var(--shadow);
      padding: 32px 28px;
      width: 100%;
      max-width: 560px;
      animation: fadeUp .6s ease .1s both;
    }

    /* 입력창 */
    .input-wrap {
      display: flex;
      align-items: center;
      gap: 10px;
      border: 1.5px solid #d4e8b0;
      border-radius: 12px;
      padding: 10px 14px;
      background: var(--green2);
      transition: border-color .2s;
    }
    .input-wrap:focus-within { border-color: #8bc34a; }
    .input-wrap svg { flex-shrink: 0; color: #e53935; }
    .input-wrap input {
      flex: 1;
      border: none;
      background: transparent;
      font-family: 'Gowun Dodum', sans-serif;
      font-size: 1rem;
      color: var(--text);
      outline: none;
    }
    .input-wrap input::placeholder { color: #b0c090; }

    /* 버튼 */
    button#submitBtn {
      margin-top: 16px;
      width: 100%;
      padding: 14px;
      background: var(--green);
      border: none;
      border-radius: 12px;
      font-family: 'Gowun Dodum', sans-serif;
      font-size: 1.05rem;
      font-weight: 700;
      color: var(--text);
      cursor: pointer;
      transition: background .2s, transform .1s;
    }
    button#submitBtn:hover:not(:disabled) { background: #b5d98a; transform: translateY(-1px); }
    button#submitBtn:disabled { background: #ddd; color: #aaa; cursor: not-allowed; }

    /* 로딩 스피너 */
    .spinner {
      display: inline-block;
      width: 18px; height: 18px;
      border: 2px solid #aaa;
      border-top-color: var(--text);
      border-radius: 50%;
      animation: spin .7s linear infinite;
      vertical-align: middle;
      margin-right: 8px;
    }

    /* 결과창 */
    .result-box {
      margin-top: 28px;
      background: var(--green2);
      border-radius: 16px;
      padding: 24px 20px;
      font-size: .97rem;
      line-height: 1.9;
      white-space: pre-wrap;
      word-break: break-word;
      min-height: 64px;
      transition: background .3s;
      position: relative;
    }
    .result-box.error {
      background: #fff0f0;
      border: 1px solid #f5c0c0;
      color: var(--red);
    }

    /* 복사 버튼 */
    .copy-btn {
      display: none;
      margin-top: 14px;
      background: none;
      border: 1px solid #ccc;
      border-radius: 8px;
      padding: 6px 14px;
      font-family: 'Gowun Dodum', sans-serif;
      font-size: .88rem;
      color: var(--sub);
      cursor: pointer;
      float: right;
      transition: background .15s;
    }
    .copy-btn:hover { background: #f0f0e8; }
    .copy-btn.visible { display: inline-block; }

    /* 애니메이션 */
    @keyframes fadeDown { from { opacity:0; transform:translateY(-18px); } to { opacity:1; transform:none; } }
    @keyframes fadeUp   { from { opacity:0; transform:translateY(18px);  } to { opacity:1; transform:none; } }
    @keyframes spin     { to { transform: rotate(360deg); } }
  </style>
</head>
<body>

<header>
  <h1>🥘 Pastel Recipe</h1>
  <p>유튜브 요리 영상 링크를 붙여넣으면 AI가 레시피를 정리해드려요</p>
</header>

<div class="card">
  <div class="input-wrap">
    <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
      <path d="M23 7s-.3-2-1.2-2.8c-1.1-1.2-2.4-1.2-3-1.3C16.1 2.8 12 2.8 12 2.8s-4.1 0-6.8.1c-.6.1-1.9.1-3 1.3C1.3 5 1 7 1 7S.7 9.1.7 11.3v2c0 2.1.3 4.2.3 4.2s.3 2 1.2 2.8c1.1 1.2 2.6 1.1 3.3 1.2C7.4 21.6 12 21.6 12 21.6s4.1 0 6.8-.2c.6-.1 1.9-.1 3-1.3.9-.8 1.2-2.8 1.2-2.8s.3-2.1.3-4.2v-2C23.3 9.1 23 7 23 7zm-13.5 8.5v-7.3l6.5 3.7-6.5 3.6z"/>
    </svg>
    <input id="urlInput" type="url" placeholder="https://youtube.com/watch?v=..." />
  </div>

  <button id="submitBtn" onclick="fetchRecipe()">레시피 요약하기</button>

  <div class="result-box" id="result">유튜브 링크를 입력하고 요약을 시작해보세요! 🍳</div>
  <button class="copy-btn" id="copyBtn" onclick="copyResult()">📋 레시피 복사</button>
</div>

<script>
  const input   = document.getElementById('urlInput');
  const btn     = document.getElementById('submitBtn');
  const result  = document.getElementById('result');
  const copyBtn = document.getElementById('copyBtn');

  input.addEventListener('keydown', e => { if (e.key === 'Enter') fetchRecipe(); });

  async function fetchRecipe() {
    const url = input.value.trim();
    if (!url) { alert('유튜브 주소를 입력해주세요.'); return; }
    if (!url.includes('youtube.com') && !url.includes('youtu.be')) {
      alert('올바른 유튜브 주소를 입력해주세요.'); return;
    }

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span>레시피 분석 중...';
    result.className = 'result-box';
    result.innerText = 'AI가 요리 소리를 듣고 있어요... ⏳\\n(약 30초~1분 소요됩니다)';
    copyBtn.classList.remove('visible');

    try {
      const res = await fetch('/cook', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url })
      });
      const data = await res.json();

      if (data.status === 'success') {
        result.innerText = data.recipe.replace(/\\*/g, '').trim();
        copyBtn.classList.add('visible');
      } else {
        result.className = 'result-box error';
        result.innerText = '❌ 오류: ' + data.message;
      }
    } catch (e) {
      result.className = 'result-box error';
      result.innerText = '❌ 연결 오류: ' + e.message;
    } finally {
      btn.disabled = false;
      btn.innerHTML = '레시피 요약하기';
    }
  }

  function copyResult() {
    navigator.clipboard.writeText(result.innerText);
    copyBtn.innerText = '✅ 복사됨!';
    setTimeout(() => copyBtn.innerText = '📋 레시피 복사', 2000);
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
        print(f"--- 1. 유튜브 오디오 추출 시작: {item.url} ---")

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'{audio_template}.%(ext)s',
            'quiet': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'm4a',
                'preferredquality': '128',
            }],
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([item.url])

        matched = glob.glob(f"{audio_template}.*")
        if not matched:
            return {"status": "error", "message": "오디오 파일 다운로드에 실패했습니다."}
        audio_path = matched[0]
        print(f"다운로드된 파일: {audio_path}")

        print("--- 2. Gemini에게 오디오 파일 전송 중 ---")

        uploaded_file = client.files.upload(
            file=audio_path,
            config={"mime_type": "audio/mp4"}
        )

        max_wait = 60
        waited = 0
        while uploaded_file.state == "PROCESSING" and waited < max_wait:
            time.sleep(2)
            waited += 2
            uploaded_file = client.files.get(name=uploaded_file.name)

        if uploaded_file.state == "PROCESSING":
            return {"status": "error", "message": "Gemini 파일 처리 시간이 초과됐습니다. 잠시 후 다시 시도해주세요."}

        if uploaded_file.state == "FAILED":
            return {"status": "error", "message": "Gemini 파일 처리에 실패했습니다."}

        print("--- 3. Gemini가 오디오를 듣고 요약 중 ---")

        prompt = """
        첨부된 오디오는 요리 영상이야. 이걸 듣고 아래 형식으로 요약해줘.
        1. 요리 이름
        2. 핵심 재료 (계량 포함)
        3. 요리 순서 (단계별로 상세히)
        4. 꿀팁
        - 별표(*) 같은 특수문자는 쓰지 말고 순수 텍스트로만 답해줘.
        """

        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=[uploaded_file, prompt]
        )

        print("--- 4. 요약 완료! ---")
        return {"status": "success", "recipe": response.text.strip()}

    except Exception as e:
        print(f"!!! 에러 발생: {str(e)} !!!")
        return {"status": "error", "message": str(e)}

    finally:
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)
            print(f"로컬 파일 삭제 완료: {audio_path}")

        if uploaded_file:
            try:
                client.files.delete(name=uploaded_file.name)
                print(f"Gemini 파일 삭제 완료: {uploaded_file.name}")
            except Exception as cleanup_err:
                print(f"Gemini 파일 삭제 실패 (무시): {cleanup_err}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
