import { pipeline } from 'https://cdn.jsdelivr.net/npm/@xenova/transformers@2.17.1';

const btn = document.getElementById('btn');
const status = document.getElementById('status');
const urlInput = document.getElementById('urlInput');
const result = document.getElementById('result');
let transcriber;

// 1. 모델 초기화
async function init() {
    try {
        status.innerText = "🤖 Whisper 모델 로딩 중... (약 1분 소요)";
        transcriber = await pipeline('automatic-speech-recognition', 'Xenova/whisper-base');
        status.innerText = "✅ 준비 완료! 링크를 넣으세요.";
        btn.disabled = false;
        btn.innerText = "레시피 요약하기";
    } catch(e) { 
        console.error(e);
        status.innerText = "❌ 로딩 에러: " + e.message; 
    }
}

// 2. 분석 실행
async function processVideo() {
    const url = urlInput.value;
    if(!url) return;

    btn.disabled = true;
    status.innerText = "🔍 1단계: 오디오 주소 추출 중...";

    try {
        const fd1 = new FormData(); fd1.append("url", url);
        const res1 = await fetch('/get_audio_url', { method: 'POST', body: fd1 });
        const data1 = await res1.json();
        
        if(data1.status !== "success") throw new Error(data1.message);

        status.innerText = "🧠 2단계: 기기 AI 분석 중 (오디오 길이에 따라 소요)...";
        const output = await transcriber(data1.audio_url, { 
            language: 'korean', task: 'transcribe' 
        });

        status.innerText = "✍️ 3단계: Gemini 레시피 요약 중...";
        const fd2 = new FormData();
        fd2.append("transcript", output.text);
        fd2.append("video_title", data1.title);

        const res2 = await fetch('/summarize', { method: 'POST', body: fd2 });
        const data2 = await res2.json();
        
        result.innerText = data2.recipe;
        status.innerText = "✨ 요약 완료!";
    } catch (e) {
        status.innerText = "❌ 실패: " + e.message;
    } finally {
        btn.disabled = false;
    }
}

// 이벤트 리스너 등록
btn.addEventListener('click', processVideo);
init();