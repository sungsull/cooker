import os
import time
from fastapi import FastAPI
from pydantic import BaseModel
import yt_dlp
import google.generativeai as genai
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI()

# CORS 설정: Flutter 앱과의 통신을 위해 필수입니다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- [1단계] 설정 구간 ---
# Render의 Environment Variables에 설정한 키를 가져옵니다.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

# 오디오를 직접 이해할 수 있는 1.5 Flash 모델을 사용합니다.
gemini_model = genai.GenerativeModel('models/gemini-1.5-flash')

class VideoURL(BaseModel):
    url: str

@app.get("/")
def home():
    return {"message": "정상 가동 중입니다."}

# --- [2단계] 핵심 기능: 유튜브 오디오 직접 분석 요약 ---
@app.post("/cook")
async def create_recipe(item: VideoURL):
    audio_file = "temp_audio.m4a"
    
    try:
        print(f"--- 1. 작업 시작: {item.url} ---")
        
        # 기존 임시 파일 청소
        if os.path.exists(audio_file):
            os.remove(audio_file)

        # A. 오디오 다운로드 (yt-dlp 사용)
        ydl_opts = {
            'format': 'm4a/bestaudio/best',
            'outtmpl': 'temp_audio.%(ext)s',
            'quiet': True
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([item.url])
        
        print("--- 2. Gemini에게 오디오 전달 중 ---")
        
        # B. Gemini File API로 오디오 업로드 (Whisper 없이 직접 분석)
        sample_file = genai.upload_file(path=audio_file, mime_type="audio/mpeg")
        
        # 파일이 분석 가능한 상태가 될 때까지 대기
        while sample_file.state.name == "PROCESSING":
            time.sleep(2)
            sample_file = genai.get_file(sample_file.name)

        print("--- 3. 레시피 요약 중 ---")
        
        # C. Gemini 프롬프트 설정
        prompt = """
        너는 최고의 요리 전문 에디터야. 첨부된 오디오를 듣고, 
        다른 잡다한 설명 없이 오직 깔끔한 **레시피 요약본**만 작성해줘.
        
        [출력 형식]:
        1. 요리 이름: 
        2. 핵심 재료: (계량 포함)
        3. 요리 순서: (단계별 번호 사용)
        4. 꿀팁: (맛의 비결 등)
        
        - 마크다운 특수 기호(**)는 절대 사용하지 마.
        - 순수 텍스트(Plain Text)로 한국어로 작성해줘.
        """
        
        # 오디오 파일과 프롬프트를 함께 전달
        response = gemini_model.generate_content([sample_file, prompt])
        
        # D. 리소스 정리 (파일 삭제)
        if os.path.exists(audio_file):
            os.remove(audio_file)
        genai.delete_file(sample_file.name)
            
        print("--- 4. 모든 작업 완료! ---")
        return {
            "status": "success",
            "recipe": response.text.strip()
        }
        
    except Exception as e:
        print(f"!!! 에러 발생: {str(e)} !!!")
        return {"status": "error", "message": f"오류 발생: {str(e)}"}
    
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
