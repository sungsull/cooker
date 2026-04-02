import os
from fastapi import FastAPI
from pydantic import BaseModel
import yt_dlp
import whisper
import google.generativeai as genai
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI()

# ... 기존 app = FastAPI() 코드 아래에 추가 ...

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 모든 곳에서 접속 허용 (개발 단계)
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- [1단계] 설정 구간 ---
# 발급받은 새로운 API 키를 입력하세요 (보안 주의!)
GEMINI_API_KEY = "AIzaSyDqVCxdyyOGEOBxd_mr6xTs2yKte0Gzldg" 
genai.configure(api_key=GEMINI_API_KEY)

# 재욱님의 환경에서 확인된 최신 모델명으로 설정합니다.
# (목록에서 확인한 gemini-3.1-flash-lite-preview 사용)
gemini_model = genai.GenerativeModel('models/gemini-3.1-flash-lite-preview')

# Whisper 모델 로드 (가볍고 빠른 base 모델)
whisper_model = whisper.load_model("tiny")

class VideoURL(BaseModel):
    url: str

@app.get("/")
def home():
    return {"message": "Cooker AI 레시피 서버가 가동 중입니다! /docs에서 테스트하세요."}

# --- [2단계] 핵심 기능: 유튜브 요리 요약 ---
@app.post("/cook")
async def create_recipe(item: VideoURL):
    audio_file = "temp_audio.m4a"
    
    try:
        print(f"--- 1. 작업 시작: {item.url} ---")
        
        # 이전 임시 파일이 있다면 삭제
        if os.path.exists(audio_file):
            os.remove(audio_file)

        # A. 오디오 다운로드 (yt-dlp)
        ydl_opts = {
            'format': 'm4a/bestaudio/best',
            'outtmpl': 'temp_audio.%(ext)s',
            'quiet': True
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([item.url])
        
        print("--- 2. 음성 인식 중 (Whisper) ---")
        # B. Whisper로 텍스트 추출
        result = whisper_model.transcribe(audio_file)
        raw_text = result["text"].strip()
        
        if not raw_text:
            return {"status": "error", "message": "음성을 인식하지 못했습니다."}

        print("--- 3. 레시피 요약 중 (Gemini) ---")
        # C. Gemini 프롬프트 (강력한 요약 지시)
        prompt = f"""
        너는 최고의 요리 전문 에디터야. 아래 [유튜브 대본]을 읽고, 
        다른 잡다한 설명 없이 오직 깔끔한 **레시피 요약본**만 작성해줘.
        
        [유튜브 대본]:
        {raw_text}
        
        [반드시 지켜야 할 출력 형식]:
        1. 요리 이름: 
        2. 핵심 재료: (양념 포함, 계량 위주 정리)
        3. 요리 순서: (단계별로 번호를 매겨 상세히 설명)
        4. 꿀팁: (주의사항이나 맛을 내는 비결)
        
        - 모든 텍스트에서 '**' 같은 특수 기호나 마크다운 강조 표시를 절대 사용하지 마.
        - 오직 순수 텍스트(Plain Text)로만 작성해줘.
        한국어로 친절하게 작성해줘.
        """
        
        response = gemini_model.generate_content(prompt)
        
        # D. 사용한 임시 파일 삭제
        if os.path.exists(audio_file):
            os.remove(audio_file)
            
        print("--- 4. 모든 작업 완료! ---")
        return {
            "status": "success",
            "recipe": response.text.strip()
        }
        
    except Exception as e:
        print(f"!!! 에러 발생: {str(e)} !!!")
        return {"status": "error", "message": f"작업 중 오류 발생: {str(e)}"}
    
if __name__ == "__main__":
    # 클라우드 서버가 지정해주는 포트($PORT)를 읽어오고, 없으면 8000을 씁니다.
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)