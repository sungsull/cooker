import os
import time
import glob
import uuid
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
import yt_dlp
from google import genai
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# CORS 설정 (Flutter 연동 필수)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept"],
    expose_headers=["*"],
)

# API 키 확인
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    # 로컬 테스트용 (Render 환경변수가 없을 경우 대비)
    GEMINI_API_KEY = "여기에_키를_직접_넣으셔도_되지만_환경변수_설정을_추천합니다"

client = genai.Client(api_key=GEMINI_API_KEY)

class VideoURL(BaseModel):
    url: str

@app.get("/")
def root():
    return {"message": "Pastel Recipe 서버가 정상 작동 중입니다 👨‍🍳"}

@app.post("/cook")
def create_recipe(item: VideoURL):
    unique_id = uuid.uuid4().hex
    audio_template = f"temp_audio_{unique_id}"
    audio_path = None
    uploaded_file = None

    try:
        print(f"--- 1. 유튜브 오디오 추출 시작: {item.url} ---")

        # FFmpeg 없이 추출하는 설정 (SyntaxError 해결 포인트)
        ydl_opts = {
            'format': 'm4a/bestaudio/best',
            'outtmpl': f'{audio_template}.%(ext)s',
            'quiet': True,
            # postprocessors를 삭제하여 FFmpeg 의존성을 없앴습니다.
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([item.url])

        matched = glob.glob(f"{audio_template}.*")
        if not matched:
            return {"status": "error", "message": "오디오 파일 다운로드에 실패했습니다."}
        
        audio_path = matched[0]
        print(f"다운로드된 파일: {audio_path}")

        print("--- 2. Gemini에게 오디오 파일 전송 중 ---")
        with open(audio_path, 'rb') as f:
            uploaded_file = client.files.upload(
                file=f,
                config={"mime_type": "audio/mp4"}
            )

        # 파일 처리 대기
        max_wait = 60
        waited = 0
        while uploaded_file.state.name == "PROCESSING" and waited < max_wait:
            time.sleep(2)
            waited += 2
            uploaded_file = client.files.get(name=uploaded_file.name)

        print("--- 3. Gemini 요약 시작 ---")
        prompt = "이 요리 영상의 오디오를 듣고 요리 이름, 재료, 상세 순서, 꿀팁을 정리해줘. 별표(*)는 쓰지마."

        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=[uploaded_file, prompt]
        )

        return {"status": "success", "recipe": response.text.strip()}

    except Exception as e:
        print(f"!!! 에러 발생: {str(e)} !!!")
        return {"status": "error", "message": str(e)}

    finally:
        # 파일 정리 (이 부분이 아까 문법 에러의 핵심이었습니다)
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)
            print(f"임시 파일 삭제 완료")
        
        if uploaded_file:
            try:
                client.files.delete(name=uploaded_file.name)
            except:
                pass

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
