import os
import time
import glob
import uuid
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
import yt_dlp
import google.generativeai as genai
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ 수정 1: API 키 하드코딩 제거 → 환경변수로 안전하게 로드
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("환경변수 GEMINI_API_KEY가 설정되지 않았습니다.")

genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-1.5-flash')


class VideoURL(BaseModel):
    url: str


# ✅ 수정 7: async → def (동기 함수로 변경하여 blocking 문제 해결)
@app.post("/cook")
def create_recipe(item: VideoURL):

    # ✅ 수정 3: uuid로 고유 파일명 생성 → 동시 요청 충돌 방지
    unique_id = uuid.uuid4().hex
    audio_template = f"temp_audio_{unique_id}"
    audio_path = None
    uploaded_file = None

    try:
        print(f"--- 1. 유튜브 오디오 추출 시작: {item.url} ---")

        # ✅ 수정 2: postprocessor로 m4a 강제 변환 → 파일 경로 불일치 해결
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

        # 실제로 저장된 파일 경로를 동적으로 탐색
        matched = glob.glob(f"{audio_template}.*")
        if not matched:
            return {"status": "error", "message": "오디오 파일 다운로드에 실패했습니다."}
        audio_path = matched[0]
        print(f"다운로드된 파일: {audio_path}")

        print("--- 2. Gemini에게 오디오 파일 전송 중 ---")

        # ✅ 수정 4: mime_type 오류 수정 (audio/mpeg → audio/mp4)
        uploaded_file = genai.upload_file(path=audio_path, mime_type="audio/mp4")

        # ✅ 수정 6: 무한 루프 방지 → 최대 대기 시간(60초) 설정
        max_wait = 60
        waited = 0
        while uploaded_file.state.name == "PROCESSING" and waited < max_wait:
            time.sleep(2)
            waited += 2
            uploaded_file = genai.get_file(uploaded_file.name)

        if uploaded_file.state.name == "PROCESSING":
            return {"status": "error", "message": "Gemini 파일 처리 시간이 초과되었습니다. 잠시 후 다시 시도해주세요."}

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

        response = gemini_model.generate_content([uploaded_file, prompt])

        print("--- 4. 요약 완료! ---")
        return {"status": "success", "recipe": response.text.strip()}

    except Exception as e:
        print(f"!!! 에러 발생: {str(e)} !!!")
        return {"status": "error", "message": str(e)}

    finally:
        # ✅ 수정 5: finally 블록에서 항상 임시 파일 정리 (에러 발생해도 동작)
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)
            print(f"로컬 파일 삭제 완료: {audio_path}")

        if uploaded_file:
            try:
                genai.delete_file(uploaded_file.name)
                print(f"Gemini 파일 삭제 완료: {uploaded_file.name}")
            except Exception as cleanup_err:
                print(f"Gemini 파일 삭제 실패 (무시): {cleanup_err}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
