"""194x110 항상 위 YouTube 미니 플레이어 (프레임리스).

설치:
    pip install pywebview

실행:
    python youtube_mini.py

조작법:
  - 우클릭(화면 어디서나): 메뉴
      재생/일시정지, 음소거, 이전/다음, 목록, URL 열기,
      YT 홈/구독 별도 창, 브라우저 영상 가져오기,
      항상 위, 크기 2배, 전체화면, 최소화, 종료
  - 홈/구독 창에서 영상 클릭: 그 창은 닫히고 미니 플레이어에서 재생
  - 재생 중 좌클릭: 재생/일시정지 토글
  - 창 이동: 아무 곳이나 드래그
  - 목록 화면: 휠/좌우 방향키 이동, 클릭/Enter 재생
  - Esc: URL 창 → 메뉴 → 목록 복귀 순으로 닫기

로그인:
  크롬 로그인과는 별개(WebView2 자체 프로필 사용). YT 홈/구독 창에서
  한 번 로그인하면 ~/.yt_mini_profile 에 저장되어 다음 실행에도 유지됨.
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

BROWSER_URLS = {
    "home": "https://www.youtube.com/",
    "subs": "https://www.youtube.com/feed/subscriptions",
}

# 홈/구독 창에 주입: 영상 링크 클릭을 가로채 미니 플레이어로 넘긴다.
BROWSER_HOOK_JS = """
(function(){
  if (window.__miniHooked) return; window.__miniHooked = true;
  function idFrom(href){
    var m = (href||'').match(/(?:youtu\\.be\\/|[?&]v=|shorts\\/|live\\/)([A-Za-z0-9_-]{11})/);
    return m ? m[1] : null;
  }
  function titleFor(a){
    if (a.title) return a.title;
    var r = a.closest('ytd-rich-item-renderer,ytd-video-renderer,ytd-grid-video-renderer,ytd-compact-video-renderer,ytd-rich-grid-media');
    if (r){ var t = r.querySelector('#video-title'); if (t) return (t.title || t.textContent || '').trim(); }
    return '';
  }
  document.addEventListener('click', function(e){
    var a = e.target && e.target.closest ? e.target.closest('a[href]') : null;
    if (!a) return;
    var id = idFrom(a.href);
    if (!id) return;
    e.preventDefault(); e.stopPropagation(); e.stopImmediatePropagation();
    if (window.pywebview && window.pywebview.api)
      window.pywebview.api.play_in_mini(a.href, titleFor(a));
  }, true);
  // 클릭 가로채기를 빠져나간 내비게이션(키보드 이동 등) 대비 감시
  setInterval(function(){
    var id = idFrom(location.href);
    if (id && !window.__miniSent){
      window.__miniSent = true;
      if (window.pywebview && window.pywebview.api)
        window.pywebview.api.play_in_mini(location.href,
          document.title.replace(/ - YouTube$/, ''));
    }
  }, 500);
})();
"""

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
  /* iframe 이 마우스 이벤트를 삼키므로, 재생 중 우클릭 메뉴/드래그 이동/
     좌클릭 재생토글용 투명 오버레이를 전체에 깐다 */
  #overlay {
    position: absolute; inset: 0;
    z-index: 15; display: none;
  }
  #menu {
    position: fixed; z-index: 100; display: none;
    background: #1e1e1e; border: 1px solid #444; border-radius: 4px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.6);
    padding: 2px;
    grid-template-columns: 1fr 1fr;
    gap: 1px;
    max-height: calc(100vh - 6px);
    overflow-y: auto;
  }
  .mi {
    font-size: 10px; line-height: 1;
    padding: 4px 7px; border-radius: 3px;
    cursor: pointer; white-space: nowrap;
  }
  .mi:hover { background: #ff5252; }
  #urlbox {
    position: fixed; z-index: 200; display: none;
    top: 50%; left: 50%; transform: translate(-50%, -50%);
    width: calc(100vw - 16px);
    background: #1e1e1e; border: 1px solid #555; border-radius: 4px;
    padding: 5px;
  }
  #urlinput {
    width: 100%;
    background: #111; color: #fff;
    border: 1px solid #444; border-radius: 3px;
    font-size: 10px; padding: 4px 6px;
    outline: none;
  }
  #urlinput:focus { border-color: #ff5252; }
  #toast {
    position: fixed; z-index: 300;
    bottom: 6px; left: 50%; transform: translateX(-50%);
    background: rgba(0,0,0,0.85); color: #fff;
    font-size: 9px; padding: 3px 10px; border-radius: 10px;
    opacity: 0; transition: opacity 0.25s; pointer-events: none;
    white-space: nowrap;
  }
</style>
</head>
<body>
  <div id="list">
    <div id="title"></div>
    <div id="index"></div>
    <div id="hint">클릭 재생 · 휠 이동 · 우클릭 메뉴</div>
  </div>
  <div id="player"></div>
  <div id="overlay"></div>
  <div id="menu"></div>
  <div id="urlbox"><input id="urlinput" placeholder="YouTube URL 또는 영상 ID · Enter"></div>
  <div id="toast"></div>
<script>
  const videos = __VIDEOS__;
  let idx = 0;
  let inPlay = false;
  let playing = false;
  let muted = true;      // 자동재생 정책 때문에 음소거로 시작
  let onTop = true;
  let scale = 1;
  let downX = 0, downY = 0, menuWasOpen = false;

  const $title = document.getElementById('title');
  const $index = document.getElementById('index');
  const $list = document.getElementById('list');
  const $player = document.getElementById('player');
  const $overlay = document.getElementById('overlay');
  const $menu = document.getElementById('menu');
  const $urlbox = document.getElementById('urlbox');
  const $urlinput = document.getElementById('urlinput');
  const $toast = document.getElementById('toast');

  const api = () => (window.pywebview && window.pywebview.api) || null;
  const menuVisible = () => $menu.style.display === 'grid';
  const urlboxVisible = () => $urlbox.style.display === 'block';

  let toastTimer = null;
  function toast(msg) {
    $toast.textContent = msg;
    $toast.style.opacity = '1';
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { $toast.style.opacity = '0'; }, 1800);
  }

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
    $overlay.style.display = 'block';
    loadVideo();
  }

  function stop() {
    inPlay = false;
    playing = false;
    $player.innerHTML = '';
    $player.style.display = 'none';
    $overlay.style.display = 'none';
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
    toast(onTop ? '항상 위: 켜짐' : '항상 위: 꺼짐');
  }

  function toggleScale() {
    scale = scale === 1 ? 2 : 1;
    const a = api(); if (a) a.set_scale(scale);
  }

  function fullscreen() { const a = api(); if (a) a.fullscreen(); }
  function minimize()   { const a = api(); if (a) a.minimize(); }
  function quit()       { const a = api(); if (a) a.quit(); }

  function openBrowser(which) {
    const a = api(); if (a) a.open_browser(which);
  }

  function parseYtId(s) {
    s = (s || '').trim();
    if (/^[A-Za-z0-9_-]{11}$/.test(s)) return s;
    const m = s.match(/(?:youtu\\.be\\/|[?&]v=|shorts\\/|embed\\/|live\\/)([A-Za-z0-9_-]{11})/);
    return m ? m[1] : null;
  }

  function addAndPlay(id, title) {
    const found = videos.findIndex(v => v.id === id);
    if (found >= 0) { idx = found; if (title) videos[found].title = title; }
    else { videos.push({title: title || ('URL \\u00b7 ' + id), id: id}); idx = videos.length - 1; }
    play();
  }

  // 홈/구독 브라우저 창에서 영상 클릭 시 파이썬 쪽에서 호출
  function playFromNative(url, title) {
    const id = parseYtId(url);
    if (!id) { toast('영상 인식 실패'); return; }
    addAndPlay(id, title);
  }

  function openUrlBox() {
    $urlbox.style.display = 'block';
    $urlinput.value = '';
    setTimeout(() => $urlinput.focus(), 50);
  }

  function closeUrlBox() { $urlbox.style.display = 'none'; }

  function grabFromBrowser() {
    const a = api();
    if (!a) return;
    a.browser_url().then(u => {
      if (!u) { toast('열린 브라우저 창이 없어요'); return; }
      const id = parseYtId(u);
      if (!id) { toast('영상 페이지가 아니에요'); return; }
      addAndPlay(id);
    });
  }

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
    items.push(['&#128279; URL 열기', openUrlBox]);
    items.push(['&#127968; YT 홈', () => openBrowser('home')]);
    items.push(['&#128250; 구독 목록', () => openBrowser('subs')]);
    items.push(['&#11015; 브라우저&rarr;미니', grabFromBrowser]);
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
    closeUrlBox();
    showMenu(e.clientX, e.clientY);
  });

  document.addEventListener('mousedown', e => {
    downX = e.clientX; downY = e.clientY;
    menuWasOpen = menuVisible();
  });

  document.addEventListener('click', e => {
    if (!$menu.contains(e.target)) hideMenu();
    if (urlboxVisible() && !$urlbox.contains(e.target)) closeUrlBox();
  });

  // 재생 중 좌클릭 = 재생/일시정지 (드래그·메뉴 닫기 클릭은 제외)
  $overlay.addEventListener('click', e => {
    if (menuWasOpen || urlboxVisible()) return;
    const moved = Math.abs(e.clientX - downX) + Math.abs(e.clientY - downY);
    if (moved > 6) return;
    togglePlay();
  });

  document.addEventListener('wheel', e => {
    if (!inPlay && !menuVisible() && !urlboxVisible())
      (e.deltaY > 0 ? next() : prev());
  });

  $urlinput.addEventListener('keydown', e => {
    e.stopPropagation();
    if (e.key === 'Escape') { closeUrlBox(); return; }
    if (e.key !== 'Enter') return;
    const id = parseYtId($urlinput.value);
    if (!id) { toast('URL 을 인식하지 못했어요'); return; }
    closeUrlBox();
    addAndPlay(id);
  });

  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      if (urlboxVisible()) { closeUrlBox(); return; }
      if (menuVisible()) { hideMenu(); return; }
      if (inPlay) stop();
      return;
    }
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
    # 주의: pywebview 는 js_api 의 공개 속성을 재귀 탐색해 JS 에 노출하므로
    # 창 객체는 반드시 밑줄(_) 접두사 속성에 보관해야 한다.
    # (공개 속성에 두면 window.native... 무한 재귀 오류 발생)
    def __init__(self):
        self._window = None
        self._browser = None

    def set_on_top(self, flag):
        try:
            self._window.on_top = bool(flag)
        except Exception:
            pass

    def set_scale(self, scale):
        self._window.resize(BASE_W * int(scale), BASE_H * int(scale))

    def fullscreen(self):
        self._window.toggle_fullscreen()

    def minimize(self):
        self._window.minimize()

    def quit(self):
        self._window.destroy()

    def open_browser(self, which):
        """YT 홈/구독을 보는 일반 브라우저 창. 이미 열려 있으면 재사용."""
        url = BROWSER_URLS.get(which, BROWSER_URLS["home"])
        if self._browser is not None and self._browser in webview.windows:
            try:
                self._browser.load_url(url)
                self._browser.restore()
                self._browser.show()
                return
            except Exception:
                pass
        self._browser = webview.create_window(
            "YouTube",
            url=url,
            js_api=self,
            width=1000,
            height=650,
            on_top=False,
        )
        # 페이지가 로드될 때마다 클릭 가로채기 스크립트 주입
        try:
            self._browser.events.loaded += self._inject_browser_hook
        except AttributeError:
            self._browser.loaded += self._inject_browser_hook

    def _inject_browser_hook(self, window=None):
        try:
            if self._browser is not None and self._browser in webview.windows:
                self._browser.evaluate_js(BROWSER_HOOK_JS)
        except Exception:
            pass

    def play_in_mini(self, url, title=None):
        """브라우저 창에서 영상 클릭 시: 그 창을 숨기고 미니에서 재생."""
        try:
            if self._browser is not None and self._browser in webview.windows:
                self._browser.hide()
        except Exception:
            pass
        try:
            self._window.restore()
            self._window.evaluate_js(
                "playFromNative(%s, %s)" % (json.dumps(url), json.dumps(title or ""))
            )
        except Exception:
            pass

    def browser_url(self):
        """브라우저 창의 현재 URL (미니로 가져오기용). 없으면 None."""
        if self._browser is not None and self._browser in webview.windows:
            try:
                return self._browser.get_current_url()
            except Exception:
                return None
        return None


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
    api._window = window

    # 로그인 세션(쿠키)을 유지해 홈/구독 창에서 한 번 로그인하면 계속 사용.
    profile_dir = os.path.join(os.path.expanduser("~"), ".yt_mini_profile")
    os.makedirs(profile_dir, exist_ok=True)
    webview.start(http_server=True, private_mode=False, storage_path=profile_dir)


if __name__ == "__main__":
    main()
