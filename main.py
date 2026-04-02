import os
import time
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

# [설정] 재욱님의 API 키를 여기에 넣으세요
GEMINI_API_KEY = "AIzaSyDqVCxdyyOGEOBxd_mr6xTs2yKte0Gzldg"
genai.configure(api_key=GEMINI_API_KEY)

# 중요: 오디오를 직접 들을 수 있는 1.5 Flash 모델 사용
gemini_model = genai.GenerativeModel('gemini-1.5-flash')

class VideoURL(BaseModel):
    url: str

@app.post("/cook")
async def create_recipe(item: VideoURL):
    audio_path = "temp_audio.m4a"
    
    try:
        print(f"--- 1. 유튜브 오디오 추출 시작: {item.url} ---")
        if os.path.exists(audio_path): os.remove(audio_path)

        # A. 유튜브에서 오디오만 뽑아내기
        ydl_opts = {
            'format': 'm4a/bestaudio/best',
            'outtmpl': 'temp_audio.%(ext)s',
            'quiet': True
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([item.url])

        print("--- 2. Gemini에게 오디오 파일 전송 중 ---")
        # B. Gemini에게 파일을 업로드 (Whisper의 역할을 여기서 대신함)
        uploaded_file = genai.upload_file(path=audio_path, mime_type="audio/mpeg")

        # 파일 분석 준비가 될 때까지 잠시 대기
        while uploaded_file.state.name == "PROCESSING":
            time.sleep(2)
            uploaded_file = genai.get_file(uploaded_file.name)

        print("--- 3. Gemini가 오디오를 듣고 요약 중 ---")
        # C. Gemini에게 오디오와 함께 프롬프트 전달
        prompt = """
        첨부된 오디오는 요리 영상이야. 이걸 듣고 아래 형식으로 요약해줘.
        1. 요리 이름
        2. 핵심 재료 (계량 포함)
        3. 요리 순서 (단계별로 상세히)
        4. 꿀팁
        - 별표(*) 같은 특수문자는 쓰지 말고 순수 텍스트로만 답해줘.
        """
        
        # 파일 객체와 텍스트 프롬프트를 리스트로 묶어서 전달!
        response = gemini_model.generate_content([uploaded_file, prompt])

        # D. 사용 완료된 파일 삭제 (로컬 & Gemini 서버)
        if os.path.exists(audio_path): os.remove(audio_path)
        genai.delete_file(uploaded_file.name)

        print("--- 4. 요약 완료! ---")
        return {"status": "success", "recipe": response.text.strip()}

    except Exception as e:
        print(f"!!! 에러 발생: {str(e)} !!!")
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
