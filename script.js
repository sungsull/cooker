import { pipeline, env } from 'https://cdn.jsdelivr.net/npm/@xenova/transformers@2.17.1';

// [중요] 보안 환경을 위한 환경 설정
env.allowLocalModels = false;
env.useBrowserCache = true;

const btn = document.getElementById('btn');
const status = document.getElementById('status');
const urlInput = document.getElementById('urlInput');
const result = document.getElementById('result');
let transcriber;

// 1. 모델 초기화
async function init() {
    try {
        status.innerText = "🤖 AI 모델 로딩 중... (최초 1회, 약 1분)";
        // Whisper 모델 로드
        transcriber = await pipeline('automatic-speech-recognition', 'Xenova/whisper-base');
        
        status.innerText = "✅ 준비 완료! 링크를 넣어주세요.";
        btn.disabled = false;
        btn.innerText = "레시피 요약하기";
    } catch(e) { 
        console.error("AI 로딩 에러:", e);
        status.innerText = "❌ 엔진 로딩 실패. 새로고침을 해주세요."; 
    }
}

// 2. 분석 및 요약 실행
async function startProcess() {
    const url = urlInput.value.trim();
    if(!url) return alert("유튜브 링크를 입력해 주세요!");

    btn.disabled = true;
    status.innerText = "🔍 1단계: 영상 정보 확인 중...";

    try {
        // 백엔드로부터 오디오 주소 확보
        const fd1 = new FormData();
        fd1.append("url", url);
        const res1 = await fetch('/get_audio_url', { method: 'POST', body: fd1 });
        const data1 = await res1.json();
        
        if(data1.status !== "success") throw new Error(data1.message);

        // 브라우저 내부 AI로 음성 인식 수행
        status.innerText = "🧠 2단계: AI 음성 분석 중 (기기 성능에 따라 차이가 있습니다)...";
        const output = await transcriber(data1.audio_url, { 
            language: 'korean', 
            task: 'transcribe' 
        });

        // 텍스트를 서버로 보내 Gemini 요약 요청
        status.innerText = "✍️ 3단계: 요리 전문가 Gemini가 요약 중...";
        const fd2 = new FormData();
        fd2.append("transcript", output.text);
        fd2.append("video_title", data1.title);

        const res2 = await fetch('/summarize', { method: 'POST', body: fd2 });
        const data2 = await res2.json();
        
        result.innerText = data2.recipe;
        status.innerText = "✨ 요약이 완료되었습니다!";
    } catch (e) {
        console.error("실행 에러:", e);
        status.innerText = "❌ 에러 발생: " + (e.message.includes("fetch") ? "네트워크 확인 요망" : e.message);
    } finally {
        btn.disabled = false;
        btn.innerText = "다시 요약하기";
    }
}

btn.addEventListener('click', startProcess);
init();