import os
import uvicorn
import google.generativeai as genai
from fastapi import FastAPI, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

app = FastAPI()

# CORS 설정 (프론트와 백엔드 통신 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- [Gemini 설정] ---
# Hugging Face Settings에서 GEMINI_API_KEY를 반드시 등록하세요.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('models/gemini-1.5-flash')

@app.get("/")
def home():
    # index.html 파일을 반환하여 프론트엔드 서빙
    return FileResponse("index.html")

@app.post("/summarize")
async def summarize_recipe(
    transcript: str = Form(...), 
    video_title: str = Form("알 수 없는 요리")
):
    try:
        print(f"--- 요약 요청 수신: {video_title} (텍스트 길이: {len(transcript)}자) ---")
        
        prompt = f"""
너는 최고의 요리 에디터야. 아래의 음성 전사 내용을 바탕으로 아주 깔끔한 레시피 요약본을 만들어줘.
마크다운 특수문자(**)는 절대 사용하지 마.

[영상 제목]: {video_title}
[전사 내용]: {transcript[:8000]}

[출력 형식]:
1. 요리 이름:
2. 핵심 재료:
3. 요리 순서:
4. 꿀팁:
"""
        response = gemini_model.generate_content(prompt)
        
        return {"status": "success", "recipe": response.text.strip()}

    except Exception as e:
        print(f"!!! 요약 에러 발생: {str(e)} !!!")
        return {"status": "error", "message": f"서버 요약 중 오류: {str(e)}"}

if __name__ == "__main__":
    # Hugging Face Spaces 기본 포트인 7860 사용
    uvicorn.run(app, host="0.0.0.0", port=7860)