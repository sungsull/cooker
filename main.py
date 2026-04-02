import os
import time
from fastapi import FastAPI
from pydantic import BaseModel
import yt_dlp
import google.generativeai as genai
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI()

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- [1단계] 설정 구간 ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

# 최신 모델 설정 (오디오 직접 분석 가능)
gemini_model = genai.GenerativeModel('models/gemini-1.5-flash')

class VideoURL(BaseModel):
    url: str

@app.get("/")
def home():
    return {"message": "메모리 최적화 완료."}

# --- [2단계] 핵심 기능: 유튜브 오디오 직접 분석 ---
@app.post("/cook")
async def create_recipe(item: VideoURL):
    audio_file = "temp_audio.m4a"
    
    try:
        print(f"--- 1. 작업 시작: {item.url} ---")
        
        # 이전 임시 파일 삭제
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
        
        print("--- 2. 오디오 전달 중 ---")
        
        # B. Gemini File API로 오디오 업로드
        sample_file = genai.upload_file(path=audio_file, mime_type="audio/mpeg")
        
        # 업로드된 파일이 처리될 때까지 아주 잠시 대기 (안정성을 위해)
        while sample_file.state.name == "PROCESSING":
            time.sleep(1)
            sample_file = genai.get_file(sample_file.name)

        print("--- 3. 레시피 요약 중 ---")
        
        # C. Gemini 프롬프트 (오디오 파일과 함께 전달)
        prompt = """
        너는 최고의 요리 전문 에디터야. 첨부된 오디오를 듣고, 
        다른 잡다한 설명 없이 오직 깔끔한 **레시피 요약본**만 작성해줘.
        
        [반드시 지켜야 할 출력 형식]:
        1. 요리 이름: 
        2. 핵심 재료: (양념 포함, 계량 위주 정리)
        3. 요리 순서: (단계별로 번호를 매겨 상세히 설명)
        4. 꿀팁: (주의사항이나 맛을 내는 비결)
        
        - 모든 텍스트에서 '**' 같은 특수 기호나 마크다운 강조 표시를 절대 사용하지 마.
        - 오직 순수 텍스트(Plain Text)로만 작성해줘.
        - 한국어로 친절하게 작성해줘.
        """
        
        response = gemini_model.generate_content([sample_file, prompt])
        
        # D. 사용한 임시 파일 및 Gemini 서버 측 파일 삭제 (정리)
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
        return {"status": "error", "message": f"작업 중 오류 발생: {str(e)}"}
    
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)