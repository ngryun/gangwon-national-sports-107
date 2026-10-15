# 제107회 전국체육대회 · 강원 경기일정

강원 출전 경기 일정·결과를 한 페이지(`index.html`)로 보여 줍니다. GitHub Pages로 배포하고, GitHub Actions가 매시간 대한체육회 공식 홈페이지 자료로 갱신합니다.

- `update_official.py` — 공식 홈페이지에서 토너먼트·기록 종목 일정, 승패·순위·기록, 강원 종합순위·메달을 받아 `index.html`의 `OFFICIAL` 데이터를 바꿉니다. 표준 라이브러리만 씁니다.
- `import_daily_pdf.py` — ‘오늘의 경기’ PDF에서 기록 종목 출전선수·예상메달을 읽어 `DAILY` 데이터를 바꿉니다. `pip install pdfplumber`가 필요하고, PDF가 바뀔 때만 로컬에서 실행합니다.
- `.github/workflows/update.yml` — 매시 7분쯤 갱신 → 바뀌면 커밋 → Pages 배포. Actions 탭에서 수동 실행도 됩니다.

로컬에서 고치기 전에는 Actions가 올린 갱신을 먼저 받으세요: `git pull`
