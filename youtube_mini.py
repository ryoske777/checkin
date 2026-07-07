"""194x110 항상 위 YouTube 미니 플레이어 (프레임리스).

유튜브 시청 페이지를 그대로 초소형 창에 띄운다. 별도 재생목록 없이
유튜브 자동재생(내 계정 알고리즘)에 따라 다음 영상이 실시간으로 이어진다.

설치:
    pip install pywebview

실행:
    python youtube_mini.py

조작법:
  - 우클릭(화면 어디서나): 메뉴
      재생/일시정지, 음소거, 다음/이전 영상, URL 열기,
      YT 홈/구독 별도 창, 항상 위, 크기, 전체화면, 최소화, 종료
  - 다음 영상: 유튜브 자동재생 알고리즘 그대로 (영상 끝나면 자동 진행)
  - 좌클릭: 영상 클릭에 의한 재생/멈춤 오동작은 차단. 컨트롤바는 사용 가능
  - 창 이동: 영상 영역을 드래그
  - 크기 조절: 우측 하단 손잡이 드래그 (메뉴 '기본 크기'로 복원)
  - 홈/구독 창에서 영상 클릭: 그 창은 닫히고 미니 플레이어에서 재생

저장:
  창 크기/위치, 항상 위, 마지막 시청 영상이 ~/.yt_mini_profile/config.json
  에 저장되어 재실행 후에도 이어서 사용.

로그인:
  크롬 로그인과는 별개(WebView2 자체 프로필 사용). YT 홈/구독 창에서
  한 번 로그인하면 유지되며, 추천 알고리즘도 계정 기준으로 적용된다.
"""
import json
import os
import re
import threading

import webview

BASE_W, BASE_H = 194, 110
DEFAULT_URL = "https://www.youtube.com/watch?v=jfKfPfyJRdk"

PROFILE_DIR = os.path.join(os.path.expanduser("~"), ".yt_mini_profile")
CONFIG_PATH = os.path.join(PROFILE_DIR, "config.json")

YT_ID_RE = re.compile(r"(?:youtu\.be/|[?&]v=|shorts/|live/)([A-Za-z0-9_-]{11})")

BROWSER_URLS = {
    "home": "https://www.youtube.com/",
    "subs": "https://www.youtube.com/feed/subscriptions",
}


def load_config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg):
    try:
        os.makedirs(PROFILE_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# 홈/구독 창에 주입: 영상 링크 클릭을 가로채 미니 플레이어로 넘긴다.
BROWSER_HOOK_JS = r"""
(function(){
  if (window.__miniHooked) return; window.__miniHooked = true;
  function idFrom(href){
    var m = (href||'').match(/(?:youtu\.be\/|[?&]v=|shorts\/|live\/)([A-Za-z0-9_-]{11})/);
    return m ? m[1] : null;
  }
  document.addEventListener('click', function(e){
    var a = e.target && e.target.closest ? e.target.closest('a[href]') : null;
    if (!a) return;
    var id = idFrom(a.href);
    if (!id) return;
    e.preventDefault(); e.stopPropagation(); e.stopImmediatePropagation();
    if (window.pywebview && window.pywebview.api)
      window.pywebview.api.play_in_mini(a.href);
  }, true);
  // 클릭 가로채기를 빠져나간 내비게이션(키보드 이동 등) 대비 감시
  setInterval(function(){
    var id = idFrom(location.href);
    if (id && !window.__miniSent){
      window.__miniSent = true;
      if (window.pywebview && window.pywebview.api)
        window.pywebview.api.play_in_mini(location.href);
    }
  }, 500);
})();
"""


# 미니 창(유튜브 시청 페이지)에 주입: 영상만 보이게 하고 자체 UI 를 얹는다.
MINI_HOOK_JS = r"""
(function(){
  if (window.__miniHooked) return; window.__miniHooked = true;
  var cfg = __CFG__;
  var onTop = cfg.onTop !== false;
  var api = function(){ return (window.pywebview && window.pywebview.api) || null; };

  // ---- 영상만 꽉 차게 보이도록 CSS ----
  var st = document.createElement('style');
  st.textContent = [
    'ytd-masthead, #masthead-container, #secondary, #below, #comments,',
    '#guide, tp-yt-app-drawer, ytd-mini-guide-renderer { display:none !important; }',
    'body { overflow:hidden !important; }',
    '#page-manager { margin:0 !important; }',
    '#movie_player { position:fixed !important; left:0 !important; top:0 !important;',
    '  width:100vw !important; height:100vh !important; z-index:9000 !important; background:#000; }',
    '#__mini_grip { position:fixed; right:0; bottom:0; width:16px; height:16px;',
    '  z-index:10001; cursor:nwse-resize; opacity:0.45; }',
    '#__mini_grip:hover { opacity:1; }',
    '#__mini_grip::before { content:""; position:absolute; right:2px; bottom:2px;',
    '  width:9px; height:9px; border-right:2px solid #ddd; border-bottom:2px solid #ddd; }',
    '#__mini_menu { position:fixed; z-index:10002; display:none;',
    '  background:#1e1e1e; border:1px solid #444; border-radius:4px;',
    '  box-shadow:0 2px 8px rgba(0,0,0,0.6); padding:2px;',
    '  grid-template-columns:1fr 1fr; gap:1px;',
    '  max-height:calc(100vh - 6px); overflow-y:auto;',
    '  font-family:"Segoe UI","Malgun Gothic",sans-serif; }',
    '#__mini_menu .mi { font-size:10px; line-height:1; padding:4px 7px;',
    '  border-radius:3px; cursor:pointer; white-space:nowrap; color:#fff; }',
    '#__mini_menu .mi:hover { background:#ff5252; }',
    '#__mini_url { position:fixed; z-index:10003; display:none; top:50%; left:50%;',
    '  transform:translate(-50%,-50%); width:calc(100vw - 16px);',
    '  background:#1e1e1e; border:1px solid #555; border-radius:4px; padding:5px; }',
    '#__mini_url input { width:100%; background:#111; color:#fff; border:1px solid #444;',
    '  border-radius:3px; font-size:10px; padding:4px 6px; outline:none; }',
    '#__mini_toast { position:fixed; z-index:10004; bottom:6px; left:50%;',
    '  transform:translateX(-50%); background:rgba(0,0,0,0.85); color:#fff;',
    '  font-size:9px; padding:3px 10px; border-radius:10px; opacity:0;',
    '  transition:opacity 0.25s; pointer-events:none; white-space:nowrap; }'
  ].join('\n');
  document.documentElement.appendChild(st);

  // ---- 자체 UI 요소 ----
  var menu = document.createElement('div'); menu.id = '__mini_menu';
  var urlbox = document.createElement('div'); urlbox.id = '__mini_url';
  var urlinput = document.createElement('input');
  urlinput.placeholder = 'YouTube URL 또는 영상 ID · Enter';
  urlbox.appendChild(urlinput);
  var toastEl = document.createElement('div'); toastEl.id = '__mini_toast';
  var grip = document.createElement('div'); grip.id = '__mini_grip';
  document.documentElement.appendChild(menu);
  document.documentElement.appendChild(urlbox);
  document.documentElement.appendChild(toastEl);
  document.documentElement.appendChild(grip);

  var toastTimer = null;
  function toast(m){
    toastEl.textContent = m; toastEl.style.opacity = '1';
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function(){ toastEl.style.opacity = '0'; }, 1800);
  }

  function vid(){ return document.querySelector('video'); }
  function menuVisible(){ return menu.style.display === 'grid'; }
  function urlVisible(){ return urlbox.style.display === 'block'; }

  function togglePlay(){ var v = vid(); if (!v) return; v.paused ? v.play() : v.pause(); }
  function toggleMute(){
    var v = vid(); if (!v) return;
    v.muted = !v.muted;
    toast(v.muted ? '음소거' : '소리 켜짐');
  }
  function nextVideo(){ var b = document.querySelector('.ytp-next-button'); if (b) b.click(); }
  function prevVideo(){ history.back(); }

  function toWatchUrl(s){
    s = (s || '').trim();
    if (/^[A-Za-z0-9_-]{11}$/.test(s)) return 'https://www.youtube.com/watch?v=' + s;
    var m = s.match(/(?:youtu\.be\/|[?&]v=|shorts\/|live\/)([A-Za-z0-9_-]{11})/);
    if (m) return 'https://www.youtube.com/watch?v=' + m[1];
    if (/^https?:\/\/(www\.|m\.)?youtube\.com\//.test(s)) return s;
    return null;
  }

  function toggleOnTop(){
    onTop = !onTop;
    var a = api(); if (a){ a.set_on_top(onTop); a.save_ui_state({onTop: onTop}); }
    toast(onTop ? '항상 위: 켜짐' : '항상 위: 꺼짐');
  }

  function openUrl(){
    urlbox.style.display = 'block'; urlinput.value = '';
    setTimeout(function(){ urlinput.focus(); }, 50);
  }
  function closeUrl(){ urlbox.style.display = 'none'; }

  function buildMenu(){
    var v = vid();
    var items = [
      [(v && v.paused) ? '▶ 재생' : '⏸ 일시정지', togglePlay],
      [(v && v.muted) ? '🔊 소리 켜기' : '🔇 음소거', toggleMute],
      ['⏭ 다음 영상', nextVideo],
      ['⏮ 이전 영상', prevVideo],
      ['🔗 URL 열기', openUrl],
      ['🏠 YT 홈', function(){ var a = api(); if (a) a.open_browser('home'); }],
      ['📺 구독 목록', function(){ var a = api(); if (a) a.open_browser('subs'); }],
      [(onTop ? '✓ ' : '') + '항상 위', toggleOnTop],
      ['크기 2배', function(){ var a = api(); if (a) a.set_scale(2); }],
      ['기본 크기', function(){ var a = api(); if (a) a.set_scale(1); }],
      ['전체화면', function(){ var a = api(); if (a) a.fullscreen(); }],
      ['— 최소화', function(){ var a = api(); if (a) a.minimize(); }],
      ['✕ 종료', function(){ var a = api(); if (a) a.quit(); }]
    ];
    menu.innerHTML = '';
    items.forEach(function(it){
      var d = document.createElement('div');
      d.className = 'mi'; d.textContent = it[0];
      d.onclick = function(){ hideMenu(); it[1](); };
      menu.appendChild(d);
    });
  }

  function showMenu(x, y){
    buildMenu();
    menu.style.display = 'grid';
    var mw = menu.offsetWidth, mh = menu.offsetHeight;
    menu.style.left = Math.max(0, Math.min(x, innerWidth - mw)) + 'px';
    menu.style.top  = Math.max(0, Math.min(y, innerHeight - mh)) + 'px';
  }
  function hideMenu(){ menu.style.display = 'none'; }

  document.addEventListener('contextmenu', function(e){
    e.preventDefault(); e.stopPropagation();
    closeUrl();
    if (menuVisible()){ hideMenu(); return; }   // 우클릭 다시 누르면 닫기
    showMenu(e.clientX, e.clientY);
  }, true);

  // 영상 좌클릭 재생/멈춤(유튜브 기본 동작)을 차단 — 드래그 오동작 방지.
  // 컨트롤바 버튼 등은 target 이 video 가 아니므로 그대로 동작한다.
  ['click', 'dblclick'].forEach(function(t){
    document.addEventListener(t, function(e){
      var el = e.target;
      if (el && (el.tagName === 'VIDEO' ||
          (el.classList && el.classList.contains('html5-video-container')))){
        e.preventDefault(); e.stopPropagation();
      }
    }, true);
  });

  document.addEventListener('click', function(e){
    if (!menu.contains(e.target)) hideMenu();
    if (urlVisible() && !urlbox.contains(e.target)) closeUrl();
  });

  urlinput.addEventListener('keydown', function(e){
    e.stopPropagation();
    if (e.key === 'Escape'){ closeUrl(); return; }
    if (e.key !== 'Enter') return;
    var u = toWatchUrl(urlinput.value);
    if (!u){ toast('URL 을 인식하지 못했어요'); return; }
    closeUrl();
    location.href = u;
  });

  // 우측 하단 손잡이 드래그로 창 크기 조절
  var resizing = false, rsX = 0, rsY = 0, rsW = 0, rsH = 0, rsLast = 0;
  grip.addEventListener('mousedown', function(e){
    // easy_drag(창 이동)로 이벤트가 넘어가지 않게 차단
    e.preventDefault(); e.stopPropagation();
  });
  grip.addEventListener('pointerdown', function(e){
    if (e.button !== 0) return;
    e.preventDefault(); e.stopPropagation();
    resizing = true;
    rsX = e.screenX; rsY = e.screenY;
    rsW = innerWidth; rsH = innerHeight;
    grip.setPointerCapture(e.pointerId);
  });
  grip.addEventListener('pointermove', function(e){
    if (!resizing) return;
    var now = Date.now();
    if (now - rsLast < 33) return;   // 호출 폭주 방지
    rsLast = now;
    var a = api(); if (a) a.resize_to(rsW + (e.screenX - rsX), rsH + (e.screenY - rsY));
  });
  grip.addEventListener('pointerup', function(){ resizing = false; });
  grip.addEventListener('pointercancel', function(){ resizing = false; });

  // 주기 작업: 자동재생(알고리즘 다음 영상) 켜기, 마지막 영상 저장,
  // 컨트롤바에서는 창 이동(easy_drag)이 발동하지 않게 차단, 플레이어 리사이즈.
  setInterval(function(){
    var b = document.querySelector('.ytp-autonav-toggle-button');
    if (b && b.getAttribute('aria-checked') === 'false') b.click();

    var mp = document.querySelector('#movie_player');
    if (mp && !mp.__miniNoDrag){
      mp.__miniNoDrag = true;
      mp.addEventListener('mousedown', function(e){
        if (e.target.closest &&
            e.target.closest('.ytp-chrome-bottom,.ytp-settings-menu,.ytp-popup'))
          e.stopPropagation();
      });
    }

    if (location.href.indexOf('/watch') >= 0){
      var a = api(); if (a) a.save_ui_state({lastUrl: location.href});
    }
    window.dispatchEvent(new Event('resize'));   // 플레이어 크기 갱신
  }, 2000);
})();
"""


class Api:
    # 주의: pywebview 는 js_api 의 공개 속성을 재귀 탐색해 JS 에 노출하므로
    # 창 객체는 반드시 밑줄(_) 접두사 속성에 보관해야 한다.
    # (공개 속성에 두면 window.native... 무한 재귀 오류 발생)
    def __init__(self, config=None):
        self._window = None
        self._browser = None
        self._config = config if isinstance(config, dict) else {}
        self._save_timer = None

    def _persist_later(self, delay=0.5):
        if self._save_timer is not None:
            self._save_timer.cancel()
        self._save_timer = threading.Timer(delay, save_config, args=(self._config,))
        self._save_timer.daemon = True
        self._save_timer.start()

    def save_ui_state(self, state):
        """JS 쪽 설정(항상 위, 마지막 영상 등) 저장."""
        if isinstance(state, dict):
            self._config.update(state)
            self._persist_later()

    def on_geometry_change(self, *args):
        """창 크기/위치 변경 시 저장 (resized/moved 이벤트)."""
        try:
            self._config.update({
                "width": self._window.width,
                "height": self._window.height,
                "x": self._window.x,
                "y": self._window.y,
            })
            self._persist_later()
        except Exception:
            pass

    def set_on_top(self, flag):
        try:
            self._window.on_top = bool(flag)
        except Exception:
            pass

    def set_scale(self, scale):
        w, h = BASE_W * int(scale), BASE_H * int(scale)
        self._window.resize(w, h)
        self._config.update({"width": w, "height": h})
        self._persist_later()

    def resize_to(self, w, h):
        """우측 하단 손잡이 드래그로 크기 조절."""
        try:
            w, h = max(100, int(w)), max(60, int(h))
            self._window.resize(w, h)
            self._config.update({"width": w, "height": h})
            self._persist_later()
        except Exception:
            pass

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

    def _inject_mini_hook(self, window=None):
        try:
            js = MINI_HOOK_JS.replace(
                "__CFG__",
                json.dumps({"onTop": bool(self._config.get("onTop", True))}),
            )
            self._window.evaluate_js(js)
        except Exception:
            pass

    def play_in_mini(self, url, title=None):
        """브라우저 창에서 영상 클릭 시: 그 창을 숨기고 미니에서 재생."""
        m = YT_ID_RE.search(url or "")
        if m:
            url = "https://www.youtube.com/watch?v=" + m.group(1)
        try:
            if self._browser is not None and self._browser in webview.windows:
                self._browser.hide()
        except Exception:
            pass
        try:
            self._window.restore()
            self._window.load_url(url)
            self._config.update({"lastUrl": url})
            self._persist_later()
        except Exception:
            pass


def main():
    # 사용자 클릭 없이도 소리 있는 자동재생을 허용 (WebView2 전용 플래그)
    os.environ.setdefault(
        "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS",
        "--autoplay-policy=no-user-gesture-required",
    )

    cfg = load_config()
    start_url = cfg.get("lastUrl") or DEFAULT_URL

    api = Api(cfg)
    window = webview.create_window(
        "YT Mini",
        url=start_url,
        js_api=api,
        width=int(cfg.get("width", BASE_W)),
        height=int(cfg.get("height", BASE_H)),
        x=cfg.get("x"),
        y=cfg.get("y"),
        on_top=bool(cfg.get("onTop", True)),
        resizable=True,
        min_size=(100, 60),
        frameless=True,
        easy_drag=True,
    )
    api._window = window
    # 시청 페이지가 로드될 때마다 미니 UI(CSS/메뉴/손잡이) 주입
    try:
        window.events.loaded += api._inject_mini_hook
    except AttributeError:
        window.loaded += api._inject_mini_hook
    # 창 크기/위치 변경을 저장 (구버전 pywebview 는 moved 이벤트가 없을 수 있음)
    for event_name in ("resized", "moved"):
        try:
            event = getattr(window.events, event_name)
            event += api.on_geometry_change
        except Exception:
            pass

    # 로그인 세션(쿠키)을 유지해 홈/구독 창에서 한 번 로그인하면 계속 사용.
    os.makedirs(PROFILE_DIR, exist_ok=True)
    webview.start(private_mode=False, storage_path=PROFILE_DIR)


if __name__ == "__main__":
    main()
