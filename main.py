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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept"],
    expose_headers=["*"],
)

# API 키 환경변수로 로드
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("환경변수 GEMINI_API_KEY가 설정되지 않았습니다.")

# ✅ 신규 SDK: client 방식으로 초기화
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

# 수정된 ydl_opts 부분
ydl_opts = {
    'format': 'm4a/bestaudio/best',  # 처음부터 m4a를 찾거나 가장 좋은 오디오 선택
    'outtmpl': f'{audio_template}.%(ext)s',
    'quiet': True,
}

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([item.url])

        matched = glob.glob(f"{audio_template}.*")
        if not matched:
            return {"status": "error", "message": "오디오 파일 다운로드에 실패했습니다."}
        audio_path = matched[0]
        print(f"다운로드된 파일: {audio_path}")

        print("--- 2. Gemini에게 오디오 파일 전송 중 ---")

        # ✅ 신규 SDK: client.files.upload() 방식
        with open(audio_path, 'rb') as f:
            uploaded_file = client.files.upload(
                file=f,
                config={"mime_type": "audio/mp4"}
            )

        # 파일 처리 대기 (최대 60초)
        max_wait = 60
        waited = 0
        while uploaded_file.state.name == "PROCESSING" and waited < max_wait:
            time.sleep(2)
            waited += 2
            uploaded_file = client.files.get(name=uploaded_file.name)

        if uploaded_file.state.name == "PROCESSING":
            return {"status": "error", "message": "Gemini 파일 처리 시간이 초과됐습니다. 잠시 후 다시 시도해주세요."}

        if uploaded_file.state.name == "FAILED":
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

        # ✅ 신규 SDK: client.models.generate_content() 방식
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
        # 로컬 파일 삭제
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)
            print(f"로컬 파일 삭제 완료: {audio_path}")

        # Gemini 업로드 파일 삭제
        if uploaded_file:
            try:
                client.files.delete(name=uploaded_file.name)
                print(f"Gemini 파일 삭제 완료: {uploaded_file.name}")
            except Exception as cleanup_err:
                print(f"Gemini 파일 삭제 실패 (무시): {cleanup_err}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
