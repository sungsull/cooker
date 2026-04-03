import os

import time

import hashlib

import uvicorn

from fastapi import FastAPI

from fastapi.responses import HTMLResponse

from pydantic import BaseModel

from googleapiclient.discovery import build

from youtube_transcript_api import YouTubeTranscriptApi

from google import genai

from fastapi.middleware.cors import CORSMiddleware



app = FastAPI()



# CORS

app.add_middleware(

    CORSMiddleware,

    allow_origins=["*"],

    allow_methods=["GET", "POST", "OPTIONS"],

    allow_headers=["*"],

)



# 환경변수

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")



client = genai.Client(api_key=GEMINI_API_KEY)

youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)



class VideoURL(BaseModel):

    url: str



#  캐시 (간단 버전)

cache = {}



#  설정값

MAX_TRANSCRIPT_LENGTH = 3000

REQUEST_DELAY = 1.2  # rate limit 방지



# ---------------------------

# 유틸 함수

# ---------------------------

def get_video_id(url: str):

    if "v=" in url:

        return url.split("v=")[-1].split("&")[0]

    elif "youtu.be/" in url:

        return url.split("youtu.be/")[-1].split("?")[0]

    return url.split("/")[-1]



def get_transcript(video_id: str):

    try:

        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

        try:

            transcript = transcript_list.find_transcript(['ko', 'en'])

        except:

            transcript = next(iter(transcript_list)).translate('ko')



        text = " ".join([t['text'] for t in transcript.fetch()])

        return text[:MAX_TRANSCRIPT_LENGTH]  #  토큰 제한

    except:

        return None



def make_cache_key(video_id: str):

    return hashlib.md5(video_id.encode()).hexdigest()



# ---------------------------

# Gemini 호출 (안정 버전)

# ---------------------------

def generate_recipe(title, content):

    prompt = f"""

제목: {title}

내용: {content}



다음 형식으로 요약:

요리 이름:

재료:

순서:

팁:



간결하고 보기 좋게 작성.

특수문자(*, #) 사용 금지.

"""



    for attempt in range(3):

        try:

            time.sleep(REQUEST_DELAY)



            response = client.models.generate_content(

                model="models/gemini-2.0-flash",

                contents=prompt

            )



            return response.text.strip()



        except Exception as e:

            if "429" in str(e):

                time.sleep(2 * (attempt + 1))

            else:

                raise e



    raise Exception("AI 요청 실패 (rate limit)")



# ---------------------------

# API

# ---------------------------

@app.get("/", response_class=HTMLResponse)

def root():

    return """

    <html>

    <body>

        <h2> Cooker</h2>

        <input id="url" style="width:300px"/>

        <button onclick="go()">요약</button>

        <pre id="result"></pre>



        <script>

        async function go() {

            const btn = document.querySelector("button");

            btn.disabled = true;



            const url = document.getElementById("url").value;

            const res = await fetch("/cook", {

                method: "POST",

                headers: {"Content-Type":"application/json"},

                body: JSON.stringify({url})

            });



            const data = await res.json();

            document.getElementById("result").innerText =

                data.recipe || data.message;



            btn.disabled = false;

        }

        </script>

    </body>

    </html>

    """



@app.post("/cook")

def cook(item: VideoURL):

    try:

        video_id = get_video_id(item.url)

        cache_key = make_cache_key(video_id)



        # ✅ 캐시 먼저 확인

        if cache_key in cache:

            return {"status": "success", "recipe": cache[cache_key]}



        # 유튜브 정보

        video = youtube.videos().list(

            part="snippet",

            id=video_id

        ).execute()



        if not video['items']:

            return {"status": "error", "message": "영상 없음"}



        snippet = video['items'][0]['snippet']

        title = snippet['title']

        description = snippet['description'][:500]



        # 자막 가져오기

        transcript = get_transcript(video_id)



        content = transcript if transcript else description



        # Gemini 호출

        recipe = generate_recipe(title, content)



        # 캐싱

        cache[cache_key] = recipe



        return {"status": "success", "recipe": recipe}



    except Exception as e:

        return {"status": "error", "message": str(e)}



# ---------------------------

# 실행

# ---------------------------

if __name__ == "__main__":

    port = int(os.environ.get("PORT", 10000))

    uvicorn.run(app, host="0.0.0.0", port=port)
