"""194x110 항상 위 YouTube 미니 플레이어 (프레임리스).

설치:
    pip install pywebview

실행:
    python youtube_mini.py

조작법:
  - 우클릭: 메뉴 (재생/일시정지, 음소거, 이전/다음, 목록, 항상 위,
            크기 2배, 전체화면, 최소화, 종료)
  - 목록 화면: 휠/좌우 방향키로 이동, 제목 클릭 또는 Enter 로 재생
  - 재생 화면: Esc 로 목록 복귀, 상단 가장자리를 잡고 창 이동
  - 창 이동: 빈 영역 아무 곳이나 드래그 (재생 중엔 상단 띠)
"""
import json
import os
import tempfile

import webview

BASE_W, BASE_H = 194, 110

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
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Malgun Gothic", sans-serif;
    overflow: hidden;
    user-select: none;
  }
  #list {
    width: 100%; height: 100%;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    gap: 4px; padding: 0 8px;
  }
  #title {
    max-width: 100%;
    text-align: center;
    font-size: 12px; line-height: 1.3;
    cursor: pointer;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  #title:hover { color: #ff5252; }
  #index { font-size: 9px; opacity: 0.5; }
  #hint {
    position: absolute; bottom: 3px; left: 0; right: 0;
    text-align: center; font-size: 8px; opacity: 0.35;
  }
  #player {
    width: 100%; height: 100%;
    display: none; background: #000;
  }
  #player iframe { width: 100%; height: 100%; border: none; }
  /* 재생 중 창 이동/우클릭용 상단 띠 (iframe 이 이벤트를 삼키므로 필요) */
  #dragbar {
    position: absolute; top: 0; left: 0; right: 0; height: 12px;
    z-index: 20; display: none;
  }
  #dragbar:hover {
    background: linear-gradient(rgba(255,255,255,0.25), transparent);
  }
  #menu {
    position: fixed; z-index: 100; display: none;
    background: #1e1e1e; border: 1px solid #444; border-radius: 4px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.6);
    padding: 2px;
    display: none;
    grid-template-columns: 1fr 1fr;
    gap: 1px;
  }
  .mi {
    font-size: 10px; line-height: 1;
    padding: 4px 7px; border-radius: 3px;
    cursor: pointer; white-space: nowrap;
  }
  .mi:hover { background: #ff5252; }
</style>
</head>
<body>
  <div id="list">
    <div id="title"></div>
    <div id="index"></div>
    <div id="hint">클릭 재생 · 휠 이동 · 우클릭 메뉴</div>
  </div>
  <div id="player"></div>
  <div id="dragbar" class="pywebview-drag-region"></div>
  <div id="menu"></div>
<script>
  const videos = __VIDEOS__;
  let idx = 0;
  let inPlay = false;
  let playing = false;
  let muted = true;      // 자동재생 정책 때문에 음소거로 시작
  let onTop = true;
  let scale = 1;

  const $title = document.getElementById('title');
  const $index = document.getElementById('index');
  const $list = document.getElementById('list');
  const $player = document.getElementById('player');
  const $dragbar = document.getElementById('dragbar');
  const $menu = document.getElementById('menu');

  const api = () => (window.pywebview && window.pywebview.api) || null;

  function render() {
    $title.textContent = videos[idx].title;
    $index.textContent = (idx + 1) + '/' + videos.length;
  }

  function loadVideo() {
    $player.innerHTML =
      '<iframe id="yt" src="https://www.youtube-nocookie.com/embed/' + videos[idx].id +
      '?autoplay=1&mute=' + (muted ? 1 : 0) +
      '&rel=0&playsinline=1&enablejsapi=1" ' +
      'referrerpolicy="strict-origin-when-cross-origin" ' +
      'allow="autoplay; encrypted-media" allowfullscreen></iframe>';
    playing = true;
  }

  function ytCmd(func) {
    const f = document.getElementById('yt');
    if (f) f.contentWindow.postMessage(
      JSON.stringify({event: 'command', func: func, args: []}), '*');
  }

  function play() {
    inPlay = true;
    $list.style.display = 'none';
    $player.style.display = 'block';
    $dragbar.style.display = 'block';
    loadVideo();
  }

  function stop() {
    inPlay = false;
    playing = false;
    $player.innerHTML = '';
    $player.style.display = 'none';
    $dragbar.style.display = 'none';
    $list.style.display = 'flex';
    render();
  }

  function prev() { idx = (idx - 1 + videos.length) % videos.length; inPlay ? loadVideo() : render(); }
  function next() { idx = (idx + 1) % videos.length; inPlay ? loadVideo() : render(); }

  function togglePlay() {
    if (!inPlay) { play(); return; }
    ytCmd(playing ? 'pauseVideo' : 'playVideo');
    playing = !playing;
  }

  function toggleMute() {
    ytCmd(muted ? 'unMute' : 'mute');
    muted = !muted;
  }

  function toggleOnTop() {
    onTop = !onTop;
    const a = api(); if (a) a.set_on_top(onTop);
  }

  function toggleScale() {
    scale = scale === 1 ? 2 : 1;
    const a = api(); if (a) a.set_scale(scale);
  }

  function fullscreen() { const a = api(); if (a) a.fullscreen(); }
  function minimize()   { const a = api(); if (a) a.minimize(); }
  function quit()       { const a = api(); if (a) a.quit(); }

  function buildMenu() {
    const items = [];
    if (inPlay) {
      items.push([playing ? '&#9208; 일시정지' : '&#9654; 재생', togglePlay]);
      items.push([muted ? '&#128266; 소리 켜기' : '&#128263; 음소거', toggleMute]);
    } else {
      items.push(['&#9654; 재생', play]);
    }
    items.push(['&#9198; 이전 영상', prev]);
    items.push(['&#9197; 다음 영상', next]);
    if (inPlay) items.push(['&#9776; 목록으로', stop]);
    items.push([(onTop ? '&#10003; ' : '') + '항상 위', toggleOnTop]);
    items.push([scale === 1 ? '크기 2배' : '크기 1배', toggleScale]);
    items.push(['전체화면', fullscreen]);
    items.push(['&#8212; 최소화', minimize]);
    items.push(['&#10005; 종료', quit]);

    $menu.innerHTML = '';
    for (const [label, fn] of items) {
      const d = document.createElement('div');
      d.className = 'mi';
      d.innerHTML = label;
      d.onclick = () => { hideMenu(); fn(); };
      $menu.appendChild(d);
    }
  }

  function showMenu(x, y) {
    buildMenu();
    $menu.style.display = 'grid';
    // 창 밖으로 나가지 않게 위치 보정
    const mw = $menu.offsetWidth, mh = $menu.offsetHeight;
    $menu.style.left = Math.max(0, Math.min(x, window.innerWidth - mw)) + 'px';
    $menu.style.top  = Math.max(0, Math.min(y, window.innerHeight - mh)) + 'px';
  }

  function hideMenu() { $menu.style.display = 'none'; }

  document.addEventListener('contextmenu', e => {
    e.preventDefault();
    showMenu(e.clientX, e.clientY);
  });
  document.addEventListener('click', e => {
    if (!$menu.contains(e.target)) hideMenu();
  });

  document.addEventListener('wheel', e => {
    if (!inPlay) (e.deltaY > 0 ? next() : prev());
  });

  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') { inPlay ? stop() : hideMenu(); return; }
    if (inPlay) return;
    if (e.key === 'ArrowLeft')  prev();
    if (e.key === 'ArrowRight') next();
    if (e.key === 'Enter')      play();
  });

  $title.onclick = play;
  render();
</script>
</body>
</html>
"""


class Api:
    def __init__(self):
        self.window = None

    def set_on_top(self, flag):
        try:
            self.window.on_top = bool(flag)
        except Exception:
            pass

    def set_scale(self, scale):
        self.window.resize(BASE_W * int(scale), BASE_H * int(scale))

    def fullscreen(self):
        self.window.toggle_fullscreen()

    def minimize(self):
        self.window.minimize()

    def quit(self):
        self.window.destroy()


def main():
    html = HTML_TEMPLATE.replace("__VIDEOS__", json.dumps(VIDEOS, ensure_ascii=False))
    # YouTube 임베드는 Referer 없는 요청을 오류 153으로 차단하므로,
    # HTML 문자열 대신 파일로 저장해 pywebview 내장 HTTP 서버로 서빙한다.
    tmp_dir = tempfile.mkdtemp(prefix="yt_mini_")
    page = os.path.join(tmp_dir, "index.html")
    with open(page, "w", encoding="utf-8") as f:
        f.write(html)

    api = Api()
    window = webview.create_window(
        "YT Mini",
        url=page,
        js_api=api,
        width=BASE_W,
        height=BASE_H,
        on_top=True,
        resizable=False,
        frameless=True,
        easy_drag=True,
    )
    api.window = window
    webview.start(http_server=True)


if __name__ == "__main__":
    main()
