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

# CORS 설정 (개발 환경 대응)
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
    # 기존에 작성하신 HTML 코드를 그대로 유지합니다.
    return """
    (여기에 기존의 긴 HTML/CSS/JS 코드를 그대로 넣으세요)
    """

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
            'nocheckcertificate': True,
            # [보안 우회 1] 클라이언트 정보를 web_creator와 android로 위장
            'extractor_args': {
                'youtube': {
                    'player_client': ['web_creator', 'android'],
                }
            },
            # [보안 우회 2] 브라우저 신분증(User-Agent) 위조
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            # [참고] 만약 cookies.txt를 쓰신다면 아래 주석을 해제하세요
            # 'cookiefile': 'cookies.txt',
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
            return {"status": "error", "message": "오디오 파일 다운로드에 실패했습니다. (유튜브 차단 가능성)"}
        
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
            return {"status": "error", "message": "Gemini 파일 처리 시간이 초과됐습니다."}

        print("--- 3. Gemini가 요약 중 ---")
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
        # 에러 메시지에 'confirm you're not a bot'이 포함되어 있으면 사용자에게 안내
        if "bot" in str(e).lower():
            return {"status": "error", "message": "유튜브가 자동 다운로드를 차단했습니다. 잠시 후 다시 시도하거나 다른 영상을 시도해주세요."}
        return {"status": "error", "message": str(e)}

    finally:
        # 파일 삭제 로직
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)
        if uploaded_file:
            try:
                client.files.delete(name=uploaded_file.name)
            except:
                pass

if __name__ == "__main__":
    # Render.com 등 배포 환경을 위한 포트 설정
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
