"""194x110 항상 위 YouTube 미니 플레이어 (프레임리스).

유튜브 시청 페이지를 그대로 초소형 창에 띄운다. 별도 재생목록 없이
유튜브 자동재생(내 계정 알고리즘)에 따라 다음 영상이 실시간으로 이어진다.

설치:
    pip install pywebview

실행:
    python youtube_mini.py
    (더블클릭 실행 시 콘솔 창은 자동으로 숨겨짐.
     아예 콘솔 없이 띄우려면: pythonw youtube_mini.py,
     또는 파일을 youtube_mini.pyw 로 복사해 더블클릭)

조작법:
  - 우클릭: 커서 위치에 별도 팝업 메뉴 창 (미니 창 크기에 갇히지 않음)
      재생/일시정지, 음소거, 다음/이전 영상, URL 열기,
      YT 홈/구독, 항상 위, 크기, 전체화면, 최소화, 종료, 불투명도 슬라이더
  - 다음 영상: 유튜브 자동재생 알고리즘 그대로 (영상 끝나면 자동 진행)
  - 좌클릭 드래그: 창 이동 (화면 아무 곳이나; 투명 실드가 오동작 차단)
  - 유튜브 자체 컨트롤은 우클릭 메뉴/키보드 단축키(스페이스, m 등)로 조작
  - 크기 조절: 우측 하단 손잡이 드래그 (메뉴 '기본 크기'로 복원)
  - 홈/구독 창에서 영상 클릭: 그 창은 닫히고 미니 플레이어에서 재생
  - 카멜레온 모드: 다른 창(브라우저 등) 위에 올려두고 켜면 그 창과
    현재 탭(창 제목)을 호스트로 기억 — 호스트가 포커스를 잃거나
    브라우저 탭이 바뀌면 같이 숨고, 기억한 창/탭으로 돌아오면 다시
    그 위에 나타난다. 호스트 창을 옮기면 상대 위치를 유지하며
    따라간다 (Windows 전용)

저장:
  창 크기/위치, 항상 위, 불투명도, 마지막 시청 영상이
  ~/.yt_mini_profile/config.json 에 저장되어 재실행 후에도 이어서 사용.

로그인:
  크롬 로그인과는 별개(WebView2 자체 프로필 사용). YT 홈/구독 창에서
  한 번 로그인하면 유지되며, 추천 알고리즘도 계정 기준으로 적용된다.
"""
import ctypes
import json
import os
import re
import threading
import time
from ctypes import wintypes

import webview

BASE_W, BASE_H = 194, 110
# 크기 조절 하한 — 가로/세로 모두 극한까지. 우측 하단 손잡이(16px)를
# 다시 잡아 되돌릴 수 있는 최소한의 크기만 남긴다.
MIN_W, MIN_H = 24, 20
MENU_W, MENU_H = 240, 252
# 라이브 스트림은 종료되면 '실시간 스트림 녹화를 볼 수 없습니다' 오류가
# 나므로 기본 시작 영상은 항상 재생 가능한 일반 영상으로 둔다.
DEFAULT_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"

PROFILE_DIR = os.path.join(os.path.expanduser("~"), ".yt_mini_profile")
CONFIG_PATH = os.path.join(PROFILE_DIR, "config.json")

YT_ID_RE = re.compile(r"(?:youtu\.be/|[?&]v=|shorts/|live/)([A-Za-z0-9_-]{11})")

BROWSER_URLS = {
    "home": "https://www.youtube.com/",
    "subs": "https://www.youtube.com/feed/subscriptions",
}


_USER32 = None


def _user32():
    """Win32 user32 (카멜레온 모드용). Windows 가 아니면 None."""
    global _USER32
    if _USER32 is not None:
        return _USER32
    try:
        u = ctypes.windll.user32
    except AttributeError:
        return None
    u.WindowFromPoint.restype = ctypes.c_void_p
    u.WindowFromPoint.argtypes = [wintypes.POINT]
    u.GetAncestor.restype = ctypes.c_void_p
    u.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    u.GetForegroundWindow.restype = ctypes.c_void_p
    u.IsWindow.argtypes = [ctypes.c_void_p]
    u.IsIconic.argtypes = [ctypes.c_void_p]
    u.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
    u.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.RECT)]
    u.IsWindowVisible.argtypes = [ctypes.c_void_p]
    u.SetWindowPos.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint,
    ]
    u.GetWindowTextLengthW.argtypes = [ctypes.c_void_p]
    u.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
    u.MonitorFromPoint.restype = ctypes.c_void_p
    u.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
    u.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    _USER32 = u
    return u


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


MONITOR_DEFAULTTONEAREST = 2


def _work_area_at(x, y):
    """(x, y)가 속한 모니터의 작업영역 (물리 px). 실패 시 None."""
    u = _user32()
    if u is None:
        return None
    try:
        hmon = u.MonitorFromPoint(wintypes.POINT(int(x), int(y)), MONITOR_DEFAULTTONEAREST)
        if not hmon:
            return None
        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(_MONITORINFO)
        if not u.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            return None
        r = mi.rcWork
        return (r.left, r.top, r.right, r.bottom)
    except Exception:
        return None


def _win_title(u, hwnd):
    try:
        n = u.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 2)
        u.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value or ""
    except Exception:
        return ""


def _norm_title(title):
    """탭 식별용 제목 정규화: 알림 카운트 '(3) ' 같은 접두어는 무시."""
    return re.sub(r"^\(\d+\)\s*", "", title or "").strip()


SW_HIDE, SW_SHOWNOACTIVATE, GA_ROOT = 0, 4, 2
HWND_TOPMOST = -1
SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER = 0x0001, 0x0002, 0x0004
SWP_NOACTIVATE, SWP_SHOWWINDOW = 0x0010, 0x0040
MENU_PARK = (-10000, -10000)   # 메뉴 창 '주차' 위치 (화면 밖)


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


def _log_file(msg):
    """콘솔이 숨겨져 있어도 확인할 수 있는 진단 로그 (~/.yt_mini_profile/mini.log)."""
    try:
        os.makedirs(PROFILE_DIR, exist_ok=True)
        with open(os.path.join(PROFILE_DIR, "mini.log"), "a", encoding="utf-8") as f:
            f.write(time.strftime("%H:%M:%S") + " " + str(msg) + "\n")
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


# 미니 창(유튜브 시청 페이지)에 주입: 영상만 보이게 하고 실드/손잡이를 얹는다.
# 주의: 유튜브는 Trusted Types(CSP)를 강제하므로 innerHTML 사용 금지,
# DOM API 로만 구성할 것. 문자는 BMP 범위만 사용.
MINI_HOOK_JS = r"""
(function(){
 try {
  if (window.__miniHooked) return; window.__miniHooked = true;
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
    '#__mini_shield { position:fixed; left:0; top:0; right:0; bottom:0; z-index:9500; }',
    '#__mini_grip { position:fixed; right:0; bottom:0; width:16px; height:16px;',
    '  z-index:10001; cursor:nwse-resize; opacity:0.45; }',
    '#__mini_grip:hover { opacity:1; }',
    '#__mini_grip::before { content:""; position:absolute; right:2px; bottom:2px;',
    '  width:9px; height:9px; border-right:2px solid #ddd; border-bottom:2px solid #ddd; }',
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
  // 투명 실드: 유튜브 플레이어가 마우스 이벤트를 삼키지 못하게 막고
  // 좌클릭 드래그(창 이동)/우클릭(메뉴)을 안정적으로 받는다.
  var shield = document.createElement('div'); shield.id = '__mini_shield';
  var urlbox = document.createElement('div'); urlbox.id = '__mini_url';
  var urlinput = document.createElement('input');
  urlinput.placeholder = 'YouTube URL 또는 영상 ID · Enter';
  urlbox.appendChild(urlinput);
  var toastEl = document.createElement('div'); toastEl.id = '__mini_toast';
  var grip = document.createElement('div'); grip.id = '__mini_grip';
  document.documentElement.appendChild(shield);
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

  function openUrl(){
    urlbox.style.display = 'block'; urlinput.value = '';
    setTimeout(function(){ urlinput.focus(); }, 50);
  }
  function closeUrl(){ urlbox.style.display = 'none'; }

  // 파이썬(팝업 메뉴 창)에서 호출할 수 있게 노출
  window.__mini = {
    togglePlay: togglePlay, toggleMute: toggleMute,
    nextVideo: nextVideo, prevVideo: prevVideo,
    openUrl: openUrl, toast: toast
  };

  // 우클릭 → 커서 위치(물리 좌표)에 별도 팝업 메뉴 창
  document.addEventListener('contextmenu', function(e){
    e.preventDefault(); e.stopPropagation();
    closeUrl();
    var dpr = window.devicePixelRatio || 1;
    var a = api();
    if (a) a.show_menu(Math.round(e.screenX * dpr), Math.round(e.screenY * dpr));
  }, true);

  // 실드 좌클릭 드래그 = 창 이동
  var dragging = false, dgX = 0, dgY = 0, dgLast = 0;
  shield.addEventListener('pointerdown', function(e){
    if (e.button !== 0) return;
    e.preventDefault();
    var a = api(); if (a) a.hide_menu();
    dragging = true; dgX = e.screenX; dgY = e.screenY; dgLast = 0;
    if (a) a.begin_move();
    shield.setPointerCapture(e.pointerId);
  });
  shield.addEventListener('pointermove', function(e){
    if (!dragging) return;
    var now = Date.now();
    if (now - dgLast < 16) return;
    dgLast = now;
    var a = api(); if (a) a.move_delta(e.screenX - dgX, e.screenY - dgY);
  });
  shield.addEventListener('pointerup', function(){ dragging = false; });
  shield.addEventListener('pointercancel', function(){ dragging = false; });

  document.addEventListener('click', function(e){
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
    if (now - rsLast < 33) return;
    rsLast = now;
    var a = api(); if (a) a.resize_to(rsW + (e.screenX - rsX), rsH + (e.screenY - rsY));
  });
  grip.addEventListener('pointerup', function(){ resizing = false; });
  grip.addEventListener('pointercancel', function(){ resizing = false; });

  // 주기 작업: 자동재생(알고리즘 다음 영상) 켜기, 마지막 영상 저장,
  // 재생 불가 감지, 플레이어 리사이즈.
  setInterval(function(){
    var b = document.querySelector('.ytp-autonav-toggle-button');
    if (b && b.getAttribute('aria-checked') === 'false') b.click();

    var errEl = document.querySelector('#movie_player .ytp-error');
    if (errEl && !window.__miniErrToasted){
      window.__miniErrToasted = true;
      toast('재생 불가 영상 — 우클릭 메뉴에서 URL/홈으로 이동');
    }

    if (location.href.indexOf('/watch') >= 0){
      var a = api(); if (a) a.save_ui_state({lastUrl: location.href});
    }
    window.dispatchEvent(new Event('resize'));   // 플레이어 크기 갱신
  }, 2000);
 } catch (err) {
  // 실패 시 가드를 풀어 파이썬 쪽 재주입 루프가 다시 시도하게 한다
  window.__miniHooked = false;
  try {
    if (window.pywebview && window.pywebview.api)
      window.pywebview.api.log('mini hook error: ' + ((err && err.stack) || err));
  } catch (e) {}
 }
})();
"""


# 팝업 메뉴 창(자체 페이지 — 유튜브 CSP 제약 없음)
MENU_HTML = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: #1e1e1e; color: #fff;
    font: 12px -apple-system, "Segoe UI", "Malgun Gothic", sans-serif;
    border: 1px solid #444; border-radius: 6px;
    overflow: hidden; user-select: none;
    width: 240px;   /* CSS 기준 고정폭 — 창 크기는 배율 곱해서 맞춘다 */
  }
  #g { display: grid; grid-template-columns: 1fr 1fr; gap: 2px; padding: 5px; }
  .mi { padding: 6px 9px; border-radius: 4px; cursor: pointer; white-space: nowrap; }
  .mi:hover { background: #ff5252; }
  #op { grid-column: 1 / span 2; padding: 4px 9px 6px; }
  #op label { font-size: 11px; opacity: 0.8; display: block; margin-bottom: 2px; }
  input[type=range] { width: 100%; }
</style>
</head>
<body>
<div id="g"></div>
<script>
  var api = function(){ return (window.pywebview && window.pywebview.api) || null; };
  var st = { playing: false, muted: false, onTop: true, opacity: 100, cham: false };
  var items = [
    ['play',       function(){ return st.playing ? '⏸ 일시정지' : '▶ 재생'; }],
    ['mute',       function(){ return st.muted ? '소리 켜기' : '음소거'; }],
    ['next',       function(){ return '⏭ 다음 영상'; }],
    ['prev',       function(){ return '⏮ 이전 영상'; }],
    ['url',        function(){ return 'URL 열기'; }],
    ['home',       function(){ return 'YT 홈'; }],
    ['subs',       function(){ return '구독 목록'; }],
    ['ontop',      function(){ return (st.onTop ? '✓ ' : '') + '항상 위'; }],
    ['cham',       function(){ return (st.cham ? '✓ ' : '') + '카멜레온 모드'; }],
    ['scale2',     function(){ return '크기 2배'; }],
    ['scale1',     function(){ return '기본 크기'; }],
    ['fullscreen', function(){ return '전체화면'; }],
    ['minimize',   function(){ return '— 최소화'; }],
    ['quit',       function(){ return '✕ 종료'; }]
  ];
  var g = document.getElementById('g');
  items.forEach(function(it){
    var d = document.createElement('div');
    d.className = 'mi'; d.id = 'mi_' + it[0];
    d.onclick = function(){ var a = api(); if (a) a.menu_action(it[0]); };
    g.appendChild(d);
  });
  var op = document.createElement('div'); op.id = 'op';
  var lb = document.createElement('label');
  var rg = document.createElement('input');
  rg.type = 'range'; rg.min = 20; rg.max = 100; rg.value = 100;
  rg.addEventListener('input', function(){
    lb.textContent = '불투명도 ' + rg.value + '%';
    var a = api(); if (a) a.set_opacity(parseInt(rg.value, 10));
  });
  op.appendChild(lb); op.appendChild(rg); g.appendChild(op);

  function refresh(){
    items.forEach(function(it){
      document.getElementById('mi_' + it[0]).textContent = it[1]();
    });
    rg.value = st.opacity;
    lb.textContent = '불투명도 ' + st.opacity + '%';
  }
  function setState(s){ st = Object.assign(st, s || {}); refresh(); }
  window.setState = setState;
  refresh();

  // Windows 디스플레이 배율(DPI) 때문에 창 물리 크기와 CSS 크기가 달라
  // 메뉴가 잘릴 수 있다 → 콘텐츠 크기 x 배율로 창 크기를 맞춘다.
  function reportSize(){
    var a = api(); if (!a) return false;
    var dpr = window.devicePixelRatio || 1;
    var h = g.offsetHeight + 4;
    a.menu_resize(Math.ceil(242 * dpr), Math.ceil(h * dpr));
    return true;
  }
  var sizeTimer = setInterval(function(){
    if (reportSize()) clearInterval(sizeTimer);
  }, 200);

  // 메뉴 밖으로 마우스가 나가면 잠시 후 닫기, Esc 로도 닫기
  var leaveTimer = null;
  document.addEventListener('mouseleave', function(){
    leaveTimer = setTimeout(function(){ var a = api(); if (a) a.hide_menu(); }, 600);
  });
  document.addEventListener('mouseenter', function(){ clearTimeout(leaveTimer); });
  document.addEventListener('keydown', function(e){
    if (e.key === 'Escape'){ var a = api(); if (a) a.hide_menu(); }
  });
  document.addEventListener('contextmenu', function(e){ e.preventDefault(); });
</script>
</body>
</html>
"""


class Api:
    # 주의: pywebview 는 js_api 의 공개 속성을 재귀 탐색해 JS 에 노출하므로
    # 창 객체는 반드시 밑줄(_) 접두사 속성에 보관해야 한다.
    # (공개 속성에 두면 window.native... 무한 재귀 오류 발생)
    def __init__(self, config=None):
        self._window = None
        self._browser = None
        self._menu = None
        self._menu_open = False
        self._menu_w, self._menu_h = MENU_W, MENU_H
        self._config = config if isinstance(config, dict) else {}
        self._save_timer = None
        # 카멜레온 모드: 호스트 창을 따라 보이고/숨고/이동
        self._cham_host = None          # 호스트 창 HWND
        self._cham_title = None         # 켤 당시 호스트 창 제목(=탭 식별)
        self._cham_offset = (0, 0)      # 호스트 기준 상대 위치
        self._cham_visible = True
        self._cham_last_set = None      # 감시 스레드가 마지막으로 지정한 위치
        self._cham_thread = None

    def _persist_later(self, delay=0.5):
        if self._save_timer is not None:
            self._save_timer.cancel()
        self._save_timer = threading.Timer(delay, save_config, args=(self._config,))
        self._save_timer.daemon = True
        self._save_timer.start()

    def save_ui_state(self, state):
        """JS 쪽 설정(마지막 영상 등) 저장."""
        if isinstance(state, dict):
            self._config.update(state)
            self._persist_later()

    def log(self, msg):
        """주입 스크립트의 오류를 콘솔·로그 파일에서 확인할 수 있게 출력."""
        print("[mini]", msg)
        _log_file(msg)

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

    def _on_ui_thread(self, fn):
        """WinForms UI 스레드에서 실행 (창 속성은 UI 스레드 전용)."""
        try:
            native = getattr(self._window, "native", None)
            if native is not None and hasattr(native, "BeginInvoke"):
                import System  # pythonnet (Windows)
                native.BeginInvoke(System.Action(fn))
                return True
        except Exception:
            pass
        return False

    def set_on_top(self, flag):
        flag = bool(flag)
        self._config.update({"onTop": flag})
        self._persist_later()
        native = getattr(self._window, "native", None)
        if self._on_ui_thread(lambda: setattr(native, "TopMost", flag)):
            return
        try:
            self._window.on_top = flag
        except Exception:
            pass

    def set_opacity(self, pct):
        """불투명도 슬라이더 (20~100%)."""
        try:
            pct = max(20, min(100, int(pct)))
        except Exception:
            return
        self._config.update({"opacity": pct})
        self._persist_later()
        self._apply_opacity(pct)

    def _apply_opacity(self, pct):
        native = getattr(self._window, "native", None)
        if native is None:
            return
        self._on_ui_thread(lambda: setattr(native, "Opacity", pct / 100.0))

    def begin_move(self):
        """실드 드래그 시작: 창의 시작 위치를 기억."""
        try:
            self._drag_origin = (self._window.x, self._window.y)
        except Exception:
            self._drag_origin = (0, 0)

    def move_delta(self, dx, dy):
        """실드 드래그 중: 시작 위치 + 마우스 이동량으로 창 이동."""
        try:
            ox, oy = getattr(self, "_drag_origin", (self._window.x, self._window.y))
            nx, ny = int(ox + dx), int(oy + dy)
            # UI 스레드(Invoke)를 거치지 않는 SetWindowPos 로 이동 —
            # UI 스레드가 바빠도/꼬여도 드래그는 항상 동작한다.
            u = _user32()
            mh = self._hwnd_of(self._window)
            if u is not None and mh:
                u.SetWindowPos(mh, None, nx, ny, 0, 0,
                               SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
            else:
                self._window.move(nx, ny)
            self._config.update({"x": nx, "y": ny})
            self._persist_later()
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
            w, h = max(MIN_W, int(w)), max(MIN_H, int(h))
            u = _user32()
            mh = self._hwnd_of(self._window)
            if u is not None and mh:
                u.SetWindowPos(mh, None, 0, 0, w, h,
                               SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE)
            else:
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
        for w in (self._menu, self._browser):
            try:
                if w is not None and w in webview.windows:
                    w.destroy()
            except Exception:
                pass
        self._window.destroy()

    # ---- 카멜레온 모드 ----

    def _hwnd_of(self, w):
        try:
            handle = w.native.Handle
            try:
                return int(handle.ToInt64())
            except Exception:
                return int(handle)
        except Exception:
            return None

    def _toast(self, msg):
        try:
            self._window.evaluate_js(
                "window.__mini && __mini.toast(%s)" % json.dumps(msg, ensure_ascii=False)
            )
        except Exception:
            pass

    def toggle_chameleon(self):
        u = _user32()
        if u is None:
            self._toast("카멜레온 모드는 Windows 전용이에요")
            return
        if self._cham_host:
            # 해제
            self._cham_host = None
            self._cham_title = None
            mini = self._hwnd_of(self._window)
            if mini:
                u.ShowWindow(mini, SW_SHOWNOACTIVATE)
            self._cham_visible = True
            self._toast("카멜레온 모드: 꺼짐")
            return
        # 미니 창 중심점 아래에 있는 최상위 창을 호스트로 지정
        try:
            mini = self._hwnd_of(self._window)
            cx = self._window.x + self._window.width // 2
            cy = self._window.y + self._window.height // 2
            u.ShowWindow(mini, SW_HIDE)   # 자기 자신이 잡히지 않게 잠깐 숨김
            try:
                hwnd = u.WindowFromPoint(wintypes.POINT(cx, cy))
                host = u.GetAncestor(hwnd, GA_ROOT) if hwnd else None
            finally:
                u.ShowWindow(mini, SW_SHOWNOACTIVATE)
            host = int(host) if host else 0
            ours = {self._hwnd_of(w) for w in (self._window, self._menu, self._browser) if w}
            if not host or host in ours:
                self._toast("아래에 붙을 창이 없어요 — 다른 창 위에 올려두고 켜주세요")
                return
            rect = wintypes.RECT()
            u.GetWindowRect(host, ctypes.byref(rect))
            self._cham_offset = (self._window.x - rect.left, self._window.y - rect.top)
            self._cham_last_set = None
            # 현재 창 제목(=브라우저 탭)을 기억 — 탭이 바뀌면 제목이 바뀐다
            self._cham_title = _norm_title(_win_title(u, host))
            self._cham_host = host
            self._cham_visible = True
            if self._cham_thread is None or not self._cham_thread.is_alive():
                self._cham_thread = threading.Thread(target=self._cham_loop, daemon=True)
                self._cham_thread.start()
            self._toast("카멜레온 모드: 켜짐 — 이 창/탭을 기억했어요")
        except Exception:
            self._cham_host = None
            self._toast("카멜레온 모드를 켤 수 없어요")

    def _cham_loop(self):
        """호스트 창의 포커스/위치를 따라 미니 창을 보이고·숨기고·이동."""
        u = _user32()
        while True:
            time.sleep(0.25)
            host = self._cham_host
            if not host:
                continue
            try:
                mini = self._hwnd_of(self._window)
                if not mini:
                    continue
                if not u.IsWindow(host):
                    # 호스트가 닫힘 → 모드 해제하고 다시 표시
                    self._cham_host = None
                    u.ShowWindow(mini, SW_SHOWNOACTIVATE)
                    self._cham_visible = True
                    self._toast("호스트 창이 닫혀 카멜레온 모드를 껐어요")
                    continue

                fg = u.GetForegroundWindow()
                fg_root = int(u.GetAncestor(fg, GA_ROOT) or 0) if fg else 0
                ours = {h for h in (
                    self._hwnd_of(self._window),
                    self._hwnd_of(self._menu) if self._menu else None,
                    self._hwnd_of(self._browser) if self._browser else None,
                ) if h}
                visible = (fg_root == host) or (fg_root in ours)
                if u.IsIconic(host):
                    visible = False
                # 같은 창이라도 탭(창 제목)이 바뀌면 숨기고,
                # 기억한 탭으로 돌아오면 다시 표시
                if visible and self._cham_title:
                    if _norm_title(_win_title(u, host)) != self._cham_title:
                        visible = False

                # 플래그가 아니라 실제 표시 상태 기준으로 동기화 —
                # 한 번 어긋나도 다음 주기(0.25s)에 반드시 복구된다.
                mini_shown = bool(u.IsWindowVisible(mini))
                if visible:
                    rect = wintypes.RECT()
                    u.GetWindowRect(host, ctypes.byref(rect))
                    cur = (self._window.x, self._window.y)
                    # 유저가 미니를 직접 옮겼으면 상대 위치 재계산
                    if (mini_shown and self._cham_last_set is not None
                            and cur != self._cham_last_set):
                        self._cham_offset = (cur[0] - rect.left, cur[1] - rect.top)
                    expect = (rect.left + self._cham_offset[0],
                              rect.top + self._cham_offset[1])
                    if not mini_shown or cur != expect:
                        # 표시 + 위치 + 최상위 z순서를 한 번에 복구 (포커스는 안 뺏음)
                        u.SetWindowPos(mini, HWND_TOPMOST, expect[0], expect[1], 0, 0,
                                       SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)
                    self._cham_last_set = expect
                elif mini_shown:
                    self.hide_menu()
                    u.ShowWindow(mini, SW_HIDE)
                self._cham_visible = visible
            except Exception:
                pass

    # ---- 팝업 메뉴 창 ----

    def _ensure_menu(self):
        """메뉴 창 생성 — 반드시 webview.start 전(main)에 호출할 것.

        실행 중(runtime) 생성은 WebView2 초기화가 꼬여 UI 스레드가 멈추고
        드래그(창 이동)까지 죽는 사고가 있었다. 시작 전에 '숨김 없이'
        화면 밖 좌표에 만들어 두면 초기화가 정상 완료되고, 화면 밖이라
        보이지도 않는다. 이후 표시/숨김은 창을 커서 위치로 가져오거나
        다시 화면 밖으로 '주차'하는 이동으로만 처리한다.
        """
        if self._menu is not None and self._menu in webview.windows:
            return
        try:
            kwargs = dict(
                html=MENU_HTML,
                js_api=self,
                width=MENU_W,
                height=MENU_H,
                x=MENU_PARK[0],
                y=MENU_PARK[1],
                frameless=True,
                on_top=True,
                resizable=False,
            )
            try:
                self._menu = webview.create_window("menu", focus=False, **kwargs)
            except TypeError:   # 구버전: focus 파라미터 없음
                self._menu = webview.create_window("menu", **kwargs)
        except Exception as e:
            self._menu = None
            _log_file("menu create failed: %r" % (e,))
            return
        # 작업표시줄에 'menu' 항목이 생기지 않게 (네이티브 준비 후 적용)
        for delay in (0.5, 2.0):
            t = threading.Timer(delay, self._menu_no_taskbar)
            t.daemon = True
            t.start()

    def _menu_no_taskbar(self):
        try:
            native = getattr(self._menu, "native", None)
            if native is not None and hasattr(native, "BeginInvoke"):
                import System  # pythonnet (Windows)
                native.BeginInvoke(
                    System.Action(lambda: setattr(native, "ShowInTaskbar", False))
                )
        except Exception as e:
            _log_file("menu_no_taskbar failed: %r" % (e,))

    def menu_resize(self, w, h):
        """메뉴 페이지가 측정한 실제 필요 크기(물리 px)로 창 크기 보정."""
        try:
            self._menu_w, self._menu_h = int(w), int(h)
            if self._menu is not None and self._menu in webview.windows:
                self._menu.resize(self._menu_w, self._menu_h)
        except Exception:
            pass

    def _menu_pos(self, x, y):
        """커서 기준 메뉴 위치. 공간이 부족한 쪽은 네이티브 메뉴처럼
        커서 반대편(왼쪽/위쪽)으로 뒤집고, 모니터 작업영역 안으로 보정."""
        w, h = self._menu_w, self._menu_h
        area = _work_area_at(x, y)
        if area is None:
            # Windows API 를 못 쓰면 주 화면 크기로 근사
            try:
                s = webview.screens[0]
                area = (0, 0, s.width, s.height)
            except Exception:
                return x, y
        left, top, right, bottom = area
        if x + w > right:
            x = x - w          # 오른쪽 공간 부족 → 커서 왼쪽으로
        if y + h > bottom:
            y = y - h          # 아래 공간 부족 → 커서 위쪽으로
        x = max(left, min(x, right - w))
        y = max(top, min(y, bottom - h))
        return x, y

    def show_menu(self, sx, sy):
        """커서 위치(물리 좌표)에 팝업 메뉴 표시. 열려 있으면 닫기(토글)."""
        if self._menu_open:
            self.hide_menu()
            return
        try:
            self._ensure_menu()
        except Exception as e:
            _log_file("ensure_menu failed: %r" % (e,))
        if self._menu is None or self._menu not in webview.windows:
            _log_file("show_menu: menu window unavailable")
            return
        state = {
            "onTop": bool(self._config.get("onTop", True)),
            "opacity": int(self._config.get("opacity", 100)),
            "cham": bool(self._cham_host),
        }
        try:
            r = self._window.evaluate_js(
                "(function(){var v=document.querySelector('video');"
                "return v ? ((v.paused?'0':'1')+(v.muted?'1':'0')) : '00';})()"
            )
            state["playing"] = bool(r and r[0] == "1")
            state["muted"] = bool(r and len(r) > 1 and r[1] == "1")
        except Exception:
            pass
        try:
            x, y = self._menu_pos(int(sx), int(sy))
            try:
                self._menu.evaluate_js(
                    "window.setState && setState(%s)" % json.dumps(state, ensure_ascii=False)
                )
            except Exception:
                pass
            self._menu_open = True
            # 창은 항상 '표시' 상태 — 커서 위치로 이동시키는 것만으로 나타난다.
            # (위치+크기+최상위+표시를 SetWindowPos 한 번으로, 포커스 안 뺏음)
            u = _user32()
            mh = self._hwnd_of(self._menu)
            if u is not None and mh:
                u.SetWindowPos(mh, HWND_TOPMOST, x, y, self._menu_w, self._menu_h,
                               SWP_NOACTIVATE | SWP_SHOWWINDOW)
            else:
                try:
                    self._menu.resize(self._menu_w, self._menu_h)
                except Exception:
                    pass
                self._menu.move(x, y)
        except Exception as e:
            self._menu_open = False
            _log_file("show_menu failed: %r" % (e,))

    def hide_menu(self):
        self._menu_open = False
        try:
            if self._menu is not None and self._menu in webview.windows:
                # 숨기는 대신 화면 밖으로 '주차' — 표시 상태를 안 건드려
                # WinForms/WebView2 상태 꼬임이 없다.
                u = _user32()
                mh = self._hwnd_of(self._menu)
                if u is not None and mh:
                    u.SetWindowPos(mh, HWND_TOPMOST, MENU_PARK[0], MENU_PARK[1], 0, 0,
                                   SWP_NOSIZE | SWP_NOACTIVATE)
                else:
                    self._menu.move(MENU_PARK[0], MENU_PARK[1])
        except Exception:
            pass

    def menu_action(self, name):
        """팝업 메뉴 항목 실행."""
        self.hide_menu()
        page_calls = {
            "play": "window.__mini && __mini.togglePlay()",
            "mute": "window.__mini && __mini.toggleMute()",
            "next": "window.__mini && __mini.nextVideo()",
            "prev": "window.__mini && __mini.prevVideo()",
            "url": "window.__mini && __mini.openUrl()",
        }
        try:
            if name in page_calls:
                self._window.evaluate_js(page_calls[name])
            elif name in ("home", "subs"):
                self.open_browser(name)
            elif name == "ontop":
                self.set_on_top(not self._config.get("onTop", True))
            elif name == "cham":
                self.toggle_chameleon()
            elif name == "scale2":
                self.set_scale(2)
            elif name == "scale1":
                self.set_scale(1)
            elif name == "fullscreen":
                self.fullscreen()
            elif name == "minimize":
                self.minimize()
            elif name == "quit":
                self.quit()
        except Exception:
            pass

    # ---- 홈/구독 브라우저 창 ----

    def _browser_geometry(self, bw=1000, bh=650):
        """미니 창 바로 아래(공간 없으면 위)에 붙는 위치 계산."""
        try:
            mx, my = self._window.x, self._window.y
            mh = self._window.height
            x, y = mx, my + mh + 6
            try:
                s = webview.screens[0]
                sw, sh = s.width, s.height
                x = max(0, min(x, sw - bw))
                if y + bh > sh:
                    y = my - bh - 6          # 아래 공간이 없으면 위로
                if y < 0:
                    y = max(0, sh - bh)
            except Exception:
                pass
            return int(x), int(y)
        except Exception:
            return None, None

    def open_browser(self, which):
        """YT 홈/구독을 보는 일반 브라우저 창. 이미 열려 있으면 재사용."""
        url = BROWSER_URLS.get(which, BROWSER_URLS["home"])
        bw, bh = 1000, 650
        x, y = self._browser_geometry(bw, bh)
        if self._browser is not None and self._browser in webview.windows:
            try:
                self._browser.load_url(url)
                if x is not None:
                    self._browser.move(x, y)
                self._browser.restore()
                self._browser.show()
                return
            except Exception:
                pass
        self._browser = webview.create_window(
            "YouTube",
            url=url,
            js_api=self,
            width=bw,
            height=bh,
            x=x,
            y=y,
            on_top=False,
        )
        # 페이지가 로드될 때마다 클릭 가로채기 스크립트 주입
        try:
            self._browser.events.loaded += self._inject_browser_hook
        except AttributeError:
            self._browser.loaded += self._inject_browser_hook
        # 생성 시 지정한 좌표가 무시되는 경우가 있어 잠시 후 한 번 더 이동
        if x is not None:
            browser = self._browser

            def _reposition():
                try:
                    if browser in webview.windows:
                        browser.move(x, y)
                except Exception:
                    pass

            t = threading.Timer(0.8, _reposition)
            t.daemon = True
            t.start()

    def _inject_browser_hook(self, window=None):
        try:
            if self._browser is not None and self._browser in webview.windows:
                self._browser.evaluate_js(BROWSER_HOOK_JS)
        except Exception:
            pass

    def _inject_mini_hook(self, window=None):
        try:
            self._window.evaluate_js(MINI_HOOK_JS)
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


def _hide_own_console():
    """더블클릭 실행으로 생긴 전용 콘솔 창만 숨긴다.

    기존 터미널(cmd/PowerShell)에서 실행한 경우에는 그 터미널까지 숨기면
    안 되므로, 이 콘솔을 쓰는 프로세스가 우리 하나뿐일 때만 숨긴다.
    (아예 콘솔 없이 실행하려면 pythonw youtube_mini.py 또는 .pyw 확장자 사용)
    """
    try:
        k = ctypes.windll.kernel32
    except AttributeError:
        return  # Windows 가 아님
    try:
        k.GetConsoleWindow.restype = ctypes.c_void_p
        hwnd = k.GetConsoleWindow()
        if not hwnd:
            return
        procs = (wintypes.DWORD * 4)()
        n = k.GetConsoleProcessList(procs, 4)
        if n == 1:
            ctypes.windll.user32.ShowWindow(ctypes.c_void_p(hwnd), SW_HIDE)
    except Exception:
        pass


def _keep_mini_injected(api):
    """미니 UI 주입 자가치유 루프.

    loaded 이벤트를 놓치거나 주입 스크립트가 실패해도 2초마다 재시도한다.
    스크립트 자체가 __miniHooked 가드로 멱등이라 중복 주입은 무해하다.
    """
    # 시작 시 저장된 불투명도 적용
    try:
        api._apply_opacity(int(api._config.get("opacity", 100)))
    except Exception as e:
        _log_file("apply_opacity failed: %r" % (e,))
    while True:
        try:
            api._inject_mini_hook()
        except Exception:
            pass
        time.sleep(2)


def main():
    # 더블클릭 실행 시 뜨는 콘솔 창 숨김
    _hide_own_console()
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
        min_size=(MIN_W, MIN_H),
        frameless=True,
        # 창 이동은 주입한 실드가 begin_move/move_delta 로 직접 처리
        # (유튜브 플레이어가 이벤트를 삼켜 easy_drag 는 동작하지 않음)
        easy_drag=False,
    )
    api._window = window
    # 팝업 메뉴 창은 반드시 시작 전에 생성 (화면 밖 좌표라 보이지 않음).
    # 실행 중 생성은 WebView2 초기화가 꼬여 드래그까지 죽는 사고가 있었다.
    api._ensure_menu()
    # 시청 페이지가 로드될 때마다 미니 UI(CSS/실드/손잡이) 주입
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
    webview.start(_keep_mini_injected, (api,), private_mode=False, storage_path=PROFILE_DIR)


if __name__ == "__main__":
    main()
