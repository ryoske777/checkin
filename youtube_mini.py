"""194x110 항상 위 YouTube 미니 플레이어.

설치:
    pip install pywebview

실행:
    python youtube_mini.py

목록에서 ◀ ▶ (또는 좌우 방향키) 로 영상 이동, 제목 클릭(또는 Enter) 으로 재생.
재생 중 Esc 또는 좌측 상단 버튼으로 목록 복귀.
"""
import json
import os
import tempfile

import webview

VIDEOS = [
    {"title": "lofi hip hop radio", "id": "jfKfPfyJRdk"},
    {"title": "chillhop radio", "id": "5yx6BWlEVcY"},
    {"title": "coding music", "id": "n61ULEU7CO0"},
]

HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body {
    width: 100vw; height: 100vh;
    background: #111; color: #fff;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    overflow: hidden;
    user-select: none;
  }
  #list {
    width: 100%; height: 100%;
    display: flex; align-items: center;
    padding: 0 4px;
  }
  .arrow {
    background: transparent; border: none; color: #fff;
    font-size: 14px; cursor: pointer; padding: 6px 4px;
    opacity: 0.6;
  }
  .arrow:hover { opacity: 1; }
  #title {
    flex: 1; text-align: center;
    font-size: 12px; line-height: 1.3;
    cursor: pointer;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    padding: 0 2px;
  }
  #title:hover { color: #ff5252; }
  #index {
    position: absolute; top: 3px; right: 5px;
    font-size: 9px; opacity: 0.5;
  }
  #hint {
    position: absolute; bottom: 2px; left: 0; right: 0;
    text-align: center;
    font-size: 8px; opacity: 0.35;
  }
  #player {
    width: 100%; height: 100%;
    display: none;
    background: #000;
  }
  #player iframe { width: 100%; height: 100%; border: none; }
  #back {
    position: absolute; top: 2px; left: 3px;
    background: rgba(0,0,0,0.55); border: none; color: #fff;
    font-size: 10px; padding: 2px 6px; cursor: pointer;
    border-radius: 3px; z-index: 10; display: none;
  }
  #back.show { display: block; }
</style>
</head>
<body>
  <div id="list">
    <button class="arrow" id="prev">&#9664;</button>
    <div id="title"></div>
    <button class="arrow" id="next">&#9654;</button>
    <div id="index"></div>
    <div id="hint">Enter &middot; play</div>
  </div>
  <div id="player"></div>
  <button id="back">&larr;</button>
<script>
  const videos = __VIDEOS__;
  let idx = 0;

  const $title = document.getElementById('title');
  const $index = document.getElementById('index');
  const $list = document.getElementById('list');
  const $player = document.getElementById('player');
  const $back = document.getElementById('back');

  function render() {
    $title.textContent = videos[idx].title;
    $index.textContent = (idx + 1) + '/' + videos.length;
  }

  function play() {
    $list.style.display = 'none';
    $player.style.display = 'block';
    $back.classList.add('show');
    $player.innerHTML =
      '<iframe src="https://www.youtube-nocookie.com/embed/' + videos[idx].id +
      '?autoplay=1&mute=1&rel=0&playsinline=1" ' +
      'referrerpolicy="strict-origin-when-cross-origin" ' +
      'allow="autoplay; encrypted-media" allowfullscreen></iframe>';
  }

  function stop() {
    $player.innerHTML = '';
    $player.style.display = 'none';
    $list.style.display = 'flex';
    $back.classList.remove('show');
  }

  document.getElementById('prev').onclick = () => { idx = (idx - 1 + videos.length) % videos.length; render(); };
  document.getElementById('next').onclick = () => { idx = (idx + 1) % videos.length; render(); };
  $title.onclick = play;
  $back.onclick = stop;

  document.addEventListener('keydown', e => {
    if ($player.style.display === 'block') {
      if (e.key === 'Escape') stop();
      return;
    }
    if (e.key === 'ArrowLeft')  { idx = (idx - 1 + videos.length) % videos.length; render(); }
    if (e.key === 'ArrowRight') { idx = (idx + 1) % videos.length; render(); }
    if (e.key === 'Enter')      play();
  });

  render();
</script>
</body>
</html>
"""


def main():
    html = HTML_TEMPLATE.replace("__VIDEOS__", json.dumps(VIDEOS, ensure_ascii=False))
    # YouTube 임베드는 Referer 없는 요청을 오류 153으로 차단하므로,
    # HTML 문자열 대신 파일로 저장해 pywebview 내장 HTTP 서버로 서빙한다.
    tmp_dir = tempfile.mkdtemp(prefix="yt_mini_")
    page = os.path.join(tmp_dir, "index.html")
    with open(page, "w", encoding="utf-8") as f:
        f.write(html)
    webview.create_window(
        "YT Mini",
        url=page,
        width=194,
        height=110,
        on_top=True,
        resizable=False,
    )
    webview.start(http_server=True)


if __name__ == "__main__":
    main()
