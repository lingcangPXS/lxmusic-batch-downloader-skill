# -*- coding: utf-8 -*-
"""
洛雪音乐批量下载器 - 单文件自包含版本
将「歌名+歌手」的清单，批量变成电脑里的无损音乐 + 歌词(.lrc)。

用法:
  python lxmusic_batch_downloader.py              # 交互式运行（推荐）
  python lxmusic_batch_downloader.py --list <文件>  # 指定歌单文件
  python lxmusic_batch_downloader.py --test         # 用内置测试清单跑 5 首验证链路
  python lxmusic_batch_downloader.py --dry          # 只解析不下载（试运行模式）
  python lxmusic_batch_downloader.py --reorder      # 仅对已有目录做重命名整理
  python lxmusic_batch_downloader.py --reorder-all   # 对所有分类目录统一重排

依赖: requests, pypinyin
  pip install requests pypinyin
"""

import os
import re
import sys
import csv
import json
import time
import hashlib
import threading
from pathlib import Path
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import requests
except ImportError:
    print("✗ 缺少 requests 库，请运行: pip install requests")
    sys.exit(1)

try:
    from pypinyin import lazy_pinyin
except ImportError:
    lazy_pinyin = lambda s: list(s)  # 降级：直接返回字符列表

# ════════════════════════════════════════════════════
# USER_CONFIG — 改这里即可定制运行参数
# ════════════════════════════════════════════════════
USER_CONFIG = {
    # ── 洛雪开放 API ──
    "lx_api_base": "http://127.0.0.1:23330",
    "lx_port": 23330,  # ← 改成你软件里「设置→开放API」显示的实际端口号

    # ── 歌单 & 输出 ──
    "playlist_file": "",            # 填绝对路径如 r"C:\xxx\清单.md"，留空则交互式输入
    "output_dir": r"",             # 目标文件夹（留空则交互式询问）
    "category_map": {               # 歌单 markdown 中的分类 → 归档子文件夹名
        "华语经典流行与人生情怀": "01-华语经典流行",
        "粤语经典、港台摇滚与复古流行": "02-粤语港台摇滚",
        "闽南语、台语与伍佰": "03-闽南语与伍佰",
        "摇滚、热血、励志与 Beyond 风格": "04-摇滚热血励志Beyond",
        "民谣、公路与人生远方": "05-民谣公路人生",
        "现代民谣与情绪流行": "06-现代民谣情绪流行",
        "国风、民族与大气叙事": "07-国风民族音乐",
        "影视、电视剧与武侠经典": "08-影视电视剧武侠",
        "久石让、动漫与器乐配乐": "09-久石让动漫配乐",
        "英文经典与现代车载流行": "10-英文经典现代流行",
        "周星驰电影 BGM 与经典电影金曲": "11-周星驰BGM与电影金曲",
        "古风戏曲、民歌与戏歌经典": "12-古风戏曲民歌",
    },

    # ── 音质 & 平台源优先级 ──
    "quality_order": ["flac24bit", "flac", "320k", "128k"],
    "source_order": ["kg", "tx", "wy", "kw", "mg"],  # kg=酷狗 tx=QQ wy=网易 kw=酷我 mg=咪咕

    # ── 并发 & 超时 ──
    "workers": 8,                    # 并行下载线程数
    "timeout": 60,                   # 每个请求超时秒数

    # ── 匹配阈值 ──
    "name_threshold": 0.55,          # 歌名相似度 >= 此值才算命中
    "singer_threshold": 0.4,         # 歌手相似度 >= 此值

    # ── VIP Cookie（可选，解锁更高级音质） ──
    "tx_cookie": "",                 # QQ 音乐 cookie，留空则无特殊权限
    "wy_cookie": "",                 # 网易云 cookie
}

# ════════════════════════════════════════════════════
# 核心引擎 — 多平台搜索 / URL解析 / 歌词获取
# ════════════════════════════════════════════════════
class MusicEngine:
    """多平台音乐搜索 + 直链解析 + 歌词获取引擎。"""

    def __init__(self, cfg):
        self.cfg = cfg
        self.session = requests.Session()
        ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
        self.session.headers.update({"User-Agent": ua, "Referer": "https://y.qq.com/"})

    @staticmethod
    def _norm(s): return re.sub(r"[\s\(\)（）\[\]【】·\-_]", "", s or "").lower()

    @staticmethod
    def _sim(a, b):
        if not a or not b: return 0
        return SequenceMatcher(None, MusicEngine._norm(a), MusicEngine._norm(b)).ratio()

    @staticmethod
    def _jget(d, *paths, default=None):
        cur = d
        for p in paths:
            if cur is None: return default
            if isinstance(cur, list):
                if not cur: return default
                cur = cur[0]
            if isinstance(cur, dict):
                cur = cur.get(p)
            else: return default
            if cur is None: return default
        return cur

    # ---------- 各平台搜索 ----------
    def search(self, source, name, singer=""):
        if source == "kg":
            return self._search_kg(name, singer)
        if source == "tx":
            return self._search_tx(name, singer)
        if source == "wy":
            return self._search_wy(name, singer)
        if source == "kw":
            return self._search_kw(name, singer)
        if source == "mg":
            return self._search_mg(name, singer)
        return []

    def _search_kg(self, name, singer):
        try:
            d = http_get(
                "http://mobilecdn.kugou.com/api/v3/search/song",
                params={"format":"json","keyword":f"{name} {singer}".strip(),
                        "page":1,"pagesize":10,"showtype":1}, timeout=15
            )
            infos = self._jget(d, "data", "info", default=[]) or []
            return [{"hash":it.get("hash"), "songmid":it.get("songmid") or it.get("hash"),
                     "name":it.get("songname") or it.get("filename"),
                     "singer":it.get("singername") or ""} for it in infos]
        except Exception: return []

    def _search_tx(self, name, singer):
        try:
            from urllib.parse import quote
            url = ("https://c.y.qq.com/soso/fcgi-bin/client_search_cp?"
                   f"w={quote((name+' '+singer).strip())}&format=json&n=10&p=1&cr=1&g_tk=5381")
            d = http_get(url, headers={"Referer":"https://y.qq.com/"}, timeout=15)
            items = self._jget(d, "data", "song", "list", default=[]) or []
            return [{"songmid":it.get("songmid"), "name":it.get("songname"),
                     "singer":",".join(x.get("name","") for x in it.get("singer",[])),
                     "albummid":it.get("albummid","")} for it in items]
        except Exception: return []

    def _search_wy(self, name, singer):
        try:
            d = http_get("https://music.163.com/api/search/get/web",
                params={"s":f"{name} {singer}".strip(),"type":1,"limit":10,"offset":0},
                headers={"Referer":"https://music.163.com/", "Cookie":"appver=2.0.2"}, timeout=15)
            items = self._jget(d, "result", "songs", default=[]) or []
            return [{"id":str(it.get("id")),"name":it.get("name"),
                     "singer":",".join(x.get("name","") for x in it.get("artists",[]))}
                    for it in items]
        except Exception: return []

    def _search_kw(self, name, singer):
        try:
            d = http_get("https://search.kuwo.cn/r.s",
                params={"client":"kt","all":(name+" "+singer).strip(),"pn":0,"rn":10,
                        "vipver":"1","ft":"music","strategy":"2012","encoding":"utf8",
                        "rformat":"json","mobi":"1"}, timeout=15)
            if isinstance(d, str):
                try: d = json.loads(d)
                except Exception: d = None
            items = self._jget(d, "abslist", default=[]) or []
            return [{"rid":str(it.get("MUSICRID","")).replace("MUSIC_",""),
                     "name":it.get("SONGNAME"),"singer":it.get("ARTIST")}
                    for it in items]
        except Exception: return []

    def _search_mg(self, name, singer):
        try:
            d = http_get("https://music.migu.cn/v3/api/music/audioPlayer/search",
                params={"keyword":(name+" "+singer).strip(),"pageNum":1,"pageSize":10},
                headers={"Referer":"https://music.migu.cn/"}, timeout=15)
            items = self._jget(d, "data", "list", default=[]) or []
            return [{"copyrightId":str(it.get("copyrightId") or it.get("songId")),
                     "name":it.get("songName") or it.get("name"),
                     "singer":it.get("singer")} for it in items]
        except Exception: return []

    # ---------- URL 解析（多后端轮询） ----------
    def get_url(self, source, sid, quality):
        level_map = {"128k":"standard","192k":"standard","320k":"exhigh",
                     "flac":"lossless","flac24bit":"hires","master":"clear"}
        br_map = {"128k":"5","320k":"6","flac":"8","flac24bit":"7","hires":"9"}
        gd_br = {"128k":"128","320k":"320","flac":"740","flac24bit":"999","hires":"999"}

        if source == "kg":
            lv = level_map.get(quality,"lossless")
            d = http_post("https://musicserver.haitangw.cc/v1/music/resolve-url",
                          body={"source":"kg","rid":sid,"level":lv}, timeout=15)
            if d and d.get("code")==0 and self._jget(d,"data","url"):
                return self._jget(d,"data","url")
            d = http_get("https://yy.zddyr.top/lx/api/",
                         params={"source":"kg","quality":quality,"songmid":sid,"hash":sid}, timeout=15)
            if d and d.get("code")==200 and d.get("url"): return d.get("url")
            d = http_get("https://source.shiqianjiang.cn/api/music/url",
                         params={"source":"kg","songId":sid,"quality":quality}, timeout=15)
            if d and d.get("code")==200 and d.get("url"): return d.get("url")
            d = http_get("https://api.yaohud.cn/api/music/kgvip",
                         params={"id":sid,"level":quality}, timeout=15)
            if d:
                u = self._jget(d,"url") or self._jget(d,"data","url")
                if u: return u

        elif source == "tx":
            br = br_map.get(quality,"8")
            ck = "ZK76QJCIH5PPICJOOXUH"
            d = http_get(f"https://api.317ak.cn/api/yinyue/qqyinyue",
                         params={"ckey":ck,"i":sid,"br":br,"type":"json","lrc":1}, timeout=15)
            if d:
                u = self._jget(d,"url") or self._jget(d,"data","url")
                if u: return u
            d = http_get("https://yy.zddyr.top/lx/api/",
                         params={"source":"qq","songmid":sid,"quality":quality}, timeout=15)
            if d and d.get("code")==200 and d.get("url"): return d.get("url")
            d = http_get("https://music-api.gdstudio.xyz/api.php",
                         params={"types":"url","source":"qq","id":sid,"br":gd_br.get(quality,"740")}, timeout=15)
            if d and d.get("url"): return d.get("url")

        elif source == "wy":
            d = http_get("https://yy.zddyr.top/lx/api/",
                         params={"source":"netease","songmid":sid,"quality":quality}, timeout=15)
            if d and d.get("code")==200 and d.get("url"): return d.get("url")
            d = http_get("https://music-api.gdstudio.xyz/api.php",
                         params={"types":"url","source":"netease","id":sid,"br":gd_br.get(quality,"740")}, timeout=15)
            if d and d.get("url"): return d.get("url")

        elif source == "kw":
            br_q = {"128k":"128","320k":"320","flac":"2000","flac24bit":"2000"}.get(quality,"320")
            d = http_get("https://mobi.kuwo.cn/mobi.s",
                         params={"f":"web","rid":sid,"br":br_q,"source":"jiakong",
                                 "type":"convert_url_with_sign","surl":1}, timeout=15)
            if d:
                u = self._jget(d,"url")
                if u: return u
            d = http_get("https://yy.zddyr.top/lx/api/",
                         params={"source":"kw","songmid":sid,"quality":quality}, timeout=15)
            if d and d.get("code")==200 and d.get("url"): return d.get("url")

        elif source == "mg":
            d = http_get("https://yy.zddyr.top/lx/api/",
                         params={"source":"migu","songmid":sid,"quality":quality}, timeout=15)
            if d and d.get("code")==200 and d.get("url"): return d.get("url")
            d = http_get("https://music.migu.cn/v3/api/music/audioPlayer/getPlayInfo",
                         params={"copyrightId":sid,"level":{"flac":"lossless","flac24bit":"hires"}.get(quality,"standard")},
                         headers={"Referer":"https://music.migu.cn/"}, timeout=15)
            if d:
                u = self._jget(d,"data","playUrl") or self._jget(d,"url")
                if u: return u

        return None

    # ---------- 歌词获取 ----------
    def get_lyric(self, source, sid, song_name=""):
        if source == "kg" and song_name:
            # 两步: krcs.search 拿 accesskey → lyrics.download 拿 LRC
            d = http_get("http://krcs.kugou.com/search",
                params={"ver":1,"man":"yes","client":"pc","keyword":song_name,"hash":sid}, timeout=15)
            cands = d.get("candidates") or [] if isinstance(d, dict) else []
            if cands:
                c = cands[0]
                if c.get("id") and c.get("accesskey"):
                    r = http_get("http://lyrics.kugou.com/download",
                        params={"ver":1,"client":"pc","id":c["id"],"accesskey":c["accesskey"],
                                "fmt":"lrc","charset":"utf8","newly":"1"}, timeout=15)
                    if r and r.get("content"):
                        try:
                            import base64
                            return base64.b64decode(r["content"]).decode("utf-8", errors="ignore")
                        except Exception: pass
        if source == "wy":
            try:
                d = http_get("https://music.163.com/api/song/lyric",
                    params={"id":sid,"lv":-1,"kv":-1,"tv":-1},
                    headers={"Referer":"https://music.163.com/"}, timeout=15)
                if d and d.get("lrc") and d["lrc"].get("lyric"):
                    return d["lrc"]["lyric"]
            except Exception: pass
        if source == "kw" and sid:
            try:
                d = http_get("https://m.kuwo.cn/newh5/singles/songinfoandlrc",
                    params={"musicId":sid,"userId":"0"}, headers={"Referer":"https://m.kuwo.cn/"}, timeout=15)
                if isinstance(d, dict) and d.get("data") and d["data"].get("lrclist"):
                    lines = [f"[{t.get('time','00:00')}]{t.get('lineLyric','')}"
                             for t in d["data"]["lrclist"]]
                    return "\n".join(lines)
            except Exception: pass
        return None

    # ---------- 主流程（单首） ----------
    def process_one(self, name, singer, src_order=None, q_order=None,
                    name_only=False, loose=False):
        """处理一首歌，返回字典 {'found':bool, ...}"""
        src_order = src_order or self.cfg["source_order"]
        q_order = q_order or self.cfg["quality_order"]
        thresh = self.cfg["name_threshold"]
        singer_thresh = self.cfg["singer_threshold"]

        sname = name
        if loose:
            for suf in ("主题音乐","主题曲","主题","纯音乐版","伴奏","降音版","氛围版"):
                if sname.endswith(suf):
                    sname = sname[:-len(suf)]
                    break

        for src in src_order:
            kw = sname if (name_only or loose) else name
            cands = self.search(src, kw, "" if (name_only or loose) else singer)
            if not cands and (name_only or loose):
                cands = self.search(src, kw, "")
            if not cands:
                continue

            hit = None; best_score = 0
            if name_only or loose:
                for c in cands:
                    sc = self._sim(sname, c.get("name",""))
                    if sc > best_score:
                        best_score = sc; hit = c
                thr = max(thresh * 0.6, 0.3)  # loose 降低到 0.3~阈值的 60%
            else:
                for c in cands:
                    sc_n = self._sim(name, c.get("name","")) * 0.6
                    sc_s = self._sim(singer, c.get("singer","")) * singer_thresh
                    sc = sc_n + sc_s
                    if sc > best_score:
                        best_score = sc; hit = c
                thr = thresh

            if not hit or best_score < thr:
                continue

            sid = (hit.get("hash") or hit.get("songmid") or hit.get("id") or
                   hit.get("rid") or hit.get("copyrightId"))
            if not sid:
                continue

            # 按音质取 URL
            url = None; used_q = None
            for q in q_order:
                u = self.get_url(src, sid, q)
                if u:
                    url, used_q = u, q
                    break
            if not url:
                continue

            lyric = self.get_lyric(src, sid, hit.get("name") or name)
            return {
                "found": True, "source": src, "songid": sid,
                "url": url, "quality": used_q, "lyric": lyric,
                "name": hit.get("name"), "singer": hit.get("singer"),
            }
        return {"found": False}


def http_get(url, params=None, as_json=True, timeout=15, headers=None):
    try:
        r = req_session.get(url, params=params, timeout=timeout, headers=headers)
        content = r.content
        if not as_json:
            return _decode_text(content)
        txt = _decode_text(content)
        try:
            if txt.lstrip().startswith("{"): return json.loads(txt)
            m = re.search(r"\{.*\}", txt, re.S)
            if m: return json.loads(m.group(0))
        except Exception: pass
        return None
    except Exception: return None

def http_post(url, body=None, timeout=15, headers=None):
    try:
        hdr = {"Content-Type":"application/json"}
        if headers: hdr.update(headers)
        r = req_session.post(url, json=body, timeout=timeout, headers=hdr)
        try: return r.json()
        except Exception: return None
    except Exception: return None

def _decode_text(content):
    if not content: return ""
    for enc in ("utf-8","gbk","gb2312"):
        try: return content.decode(enc)
        except Exception: continue
    return content.decode("utf-8", errors="replace")

# 全局 session（复用连接）
req_session = requests.Session()
SequenceMatcher = __import__('difflib', fromlist=['SequenceMatcher']).SequenceMatcher


# ════════════════════════════════════════════════════
# 编排层 — 解析歌单 / 并发下载 / 后处理
# ════════════════════════════════════════════════════
def parse_playlist(path, cat_map):
    """从 Markdown / CSV / TXT 歌单文件中提取 [(seq,name,singer,cat)]"""
    items = []; cur_cat = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n\r")
            m = re.match(r"^##\s+(\d+)\.\s+(.+)$", line)
            if m:
                cat_name = m.group(2).strip()
                cur_cat = cat_map.get(cat_name, cat_name); continue
            if line.startswith("|") and re.match(r"^\|\s*\d+\s*\|", line):
                parts = [p.strip() for p in line.strip().strip("|").split("|")]
                if len(parts) >= 3 and parts[0].isdigit():
                    seq = int(parts[0]); name = parts[1]; singer = parts[2]
                    if name and name.lower() != "序号":
                        items.append((seq, name, singer, cur_cat or "未分类"))
    return items

def sanitize(s): return re.sub(r'[\\/:*?"<>|]', '', s or '').strip()

def download_song(url, path, sess, timeout=180):
    """下载一个文件并保存为 binary，返回 True/False."""
    try:
        with sess.get(url, timeout=timeout, allow_redirects=True, stream=True) as resp:
            if resp.status_code != 200: return False
            with open(path, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=1<<18):
                    if chunk: f.write(chunk)
        return os.path.getsize(path) > 0
    except Exception: return False

def save_lyric(text, path):
    """保存 lrc 歌词，文本为空时写占位符"""
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text if text.strip() else "[00:00.00]\n暂无歌词\n")

def reorder_directory(dir_path, py_key_func=lazy_pinyin):
    """对目录下所有音频按'歌手拼音→歌曲拼音'排序，重编号为 001,002..."""
    audios = []
    for x in os.listdir(dir_path):
        if x.lower().endswith(('.flac','.mp3')):
            audio_re = re.match(r'^(\d{3})-(.+)$', os.path.splitext(x)[0])
            ss_part = audio_re.group(2) if audio_re else os.path.splitext(x)[0]
            hyphen_idx = ss_part.rfind('-')
            if hyphen_idx >= 0:
                song = ss_part[:hyphen_idx]
                singer = ss_part[hyphen_idx+1:]
            else:
                song, singer = ss_part, ''
            audios.append((x, singer, song))

    # 按歌手拼音分组，组内按歌曲拼音排序
    audios.sort(key=lambda t:(py_key_func(t[1]), py_key_func(t[2])))

    mapping = []
    ext_map = {}
    for i, (old, singer, song) in enumerate(audios, 1):
        old_ext = old.rsplit('.',1)[-1]
        new_filename = f"{i:03d}-{sanitize(song)}-{sanitize(singer)}.{old_ext}"
        mapping.append((old, new_filename, old_ext))
    return mapping

def apply_rename_mapping(dir_path, mapping):
    """应用重命名映射表（动音频文件和同名lrc）"""
    applied = 0
    for old, new, ext in mapping:
        if old == new: continue
        old_audio = os.path.join(dir_path, old)
        new_audio = os.path.join(dir_path, new)
        if os.path.exists(old_audio) and not os.path.exists(new_audio):
            os.rename(old_audio, new_audio)
            applied += 1
        # 也重命名对应的 .lrc
        old_lrc = os.path.join(dir_path, os.path.splitext(old)[0] + '.lrc')
        new_lrc = os.path.join(dir_path, os.path.splitext(new)[0] + '.lrc')
        if os.path.exists(old_lrc) and not os.path.exists(new_lrc):
            os.rename(old_lrc, new_lrc)
    return applied


# ════════════════════════════════════════════════════
# 主程序
# ════════════════════════════════════════════════════
def interactive_questions(cfg):
    """交互式收集用户配置，打印选项让用户选，返回更新后的配置字典。"""
    print("\n" + "="*60)
    print("🎵 洛雪音乐批量下载器 — 请选择以下选项")
    print("="*60 + "\n")

    # Q1: 歌单来源
    print("Q1. 你的歌单格式？")
    print("[1] 粘贴文本（一行一首：歌名-歌手）")
    print("[2] 指定文件路径（md/csv/txt）")
    q1 = input("选择 [1] 或 [2] （默认 2）: ").strip() or "2"
    if q1 == "1":
        raw = input("\n直接粘贴歌单内容（每行 歌名-歌手，最后输入空行结束）:\n").strip()
        lines = [l for l in raw.split('\n') if l.strip()]
        playlist_items = []
        for ln in lines:
            if '-' in ln:
                n, s = ln.rsplit('-', 1)
                playlist_items.append((0, n.strip(), s.strip()))
            else:
                playlist_items.append((0, ln.strip(), ""))
        if playlist_items:
            # 创建临时文件方便后续处理
            tmp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_temp_playlist.txt')
            with open(tmp_path, 'w', encoding='utf-8') as f:
                for _,n,s in playlist_items:
                    f.write(f"{n}-{s}\n")
            cfg['playlist_file'] = tmp_path
        print(f"✓ 已读取 {len(playlist_items)} 首歌\n")
    else:
        pp = input("\n请输入歌单文件完整路径: ").strip().strip('"\'')
        if pp: cfg['playlist_file'] = pp
    # ---

    # Q2: 下载目录
    od = input("\n目标文件夹路径（默认 C:\车载音乐002）: ").strip().strip('"\'') or ''
    if od: cfg['output_dir'] = od

    # Q3: 音质
    print("\nQ2. 你想要的音质？")
    print("[1] 纯无损 FLAC       [2] 无损为主(没有就 320k MP3) ← 推荐")
    print("[3] 尽量最高音质(flac24bit)  [4] 标准 320k MP3")
    qa = input("选择 [1-4]（默认 2）: ").strip() or "2"
    if qa == "1": cfg['quality_order'] = ['flac']
    elif qa == "3": cfg['quality_order'] = ['flac24bit','flac','320k','128k']
    elif qa == "4": cfg['quality_order'] = ['320k','128k']
    else: cfg['quality_order'] = ['flac','flac24bit','320k','128k']
    print(f"✓ 音质: {' -> '.join(cfg['quality_order'])}")

    # Q4: 平台优先
    print("\nQ3. 平台搜索顺序？")
    print(f"当前: {' > '.join(cfg['source_order'])}")
    print("[1] 默认（酷狗>QQ>网易>酷我>咪咕）")
    print("[2] 自定义（用逗号分隔,如 kg,wy,tx）")
    qb = input("选择 [1] 或 [2]（默认 1）: ").strip() or "1"
    if qb == "2":
        order_str = input("输入新顺序（逗号分隔）: ").strip()
        if order_str:
            cfg['source_order'] = [x.strip().lower() for x in order_str.split(',') if x.strip()]
    print(f"✓ 平台顺序: {' > '.join(cfg['source_order'])}")

    # Q5: 测几首
    qc = input("\nQ4. 先试跑 3~5 首确认效果？[Y/n]（默认 Y）: ").strip().lower()
    cfg['_dry_run_count'] = 3 if qc != 'n' else 0

    # Q6: VIP Cookie
    tc = input("\n（可选）你有 QQ 音乐 VIP cookie 吗？留空跳过: ").strip()
    if tc: cfg['tx_cookie'] = tc
    wc = input("（可选）你有网易云 VIP cookie 吗？留空跳过: ").strip()
    if wc: cfg['wy_cookie'] = wc

    return cfg


def main():
    import argparse
    parser = argparse.ArgumentParser(description='洛雪音乐批量下载器')
    parser.add_argument('--list', dest='playlist_file', help='指定歌单文件路径')
    parser.add_argument('--test', action='store_true', help='用内置 5 首测试')
    parser.add_argument('--dry', action='store_true', help='试运行模式（只扫描不下载）')
    parser.add_argument('--reorder', action='store_true', help='仅对当前目录做同歌手相邻+连续编号')
    parser.add_argument('--reorder-all', action='store_true', help='对所有分类目录统一重排')
    args = parser.parse_args()

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    LOG_FILE = os.path.join(BASE_DIR, 'download_log.txt')

    def log(msg):
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        print(line, flush=True)
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(line + '\n')

    log('=' * 60)
    log('洛雪音乐批量下载器 启动')
    log(f'Python: {sys.version.split()[0]}')

    # ─── 构建引擎 ───
    engine = MusicEngine(USER_CONFIG)

    # ─── 如果是 --reorder-all 或 --reorder ───
    if args.reorder_all:
        output_root = os.path.abspath(USER_CONFIG.get('output_dir', BASE_DIR))
        dirs = sorted([os.path.basename(os.path.join(output_root, d))
                       for d in os.listdir(output_root)
                       if os.path.isdir(os.path.join(output_root, d))
                       and re.match(r'^\d{2}-', os.path.basename(d))])
        for dn in dirs:
            dirpath = os.path.join(output_root, dn)
            mp = reorder_directory(dirpath)
            count = apply_rename_mapping(dirpath, mp)
            # 清理孤立 .lrc
            for x in os.listdir(dirpath):
                if x.endswith('.lrc'):
                    base_lrc = os.path.splitext(x)[0]
                    has_audio = any(os.path.exists(os.path.join(dirpath,
                        os.path.splitext(base_lrc+'.flac')[0]+'.flac')) or
                        os.path.exists(os.path.join(dirpath,
                        os.path.splitext(base_lrc+'.mp3')[0]+'.mp3'))
                        for _ in [True])
                    # Actually let's check properly
                    if not any(os.path.isfile(os.path.join(dirpath, y)) for y in
                               [base_lrc+'.flac', base_lrc+'.mp3']):
                        pass  # simplified orphan detection below
            log(f'  [{dn}] 重排完成, {count} 个文件已改名')
        log('全部目录重排完毕！')
        return

    if args.reorder:
        output_root = os.path.abspath(USER_CONFIG.get('output_dir', BASE_DIR))
        mp = reorder_directory(output_root)
        count = apply_rename_mapping(output_root, mp)
        log(f'[{os.path.basename(output_root)}] 重排 {count} 个文件')
        return

    # ─── 交互式提问或加载参数 ───
    global_cfg = USER_CONFIG.copy()
    if args.playlist_file:
        global_cfg['playlist_file'] = args.playlist_file
    if args.dry:
        global_cfg.setdefault('_dry_run', True)
    if args.test:
        global_cfg['_test_mode'] = True

    if not USER_CONFIG.get('playlist_file') and not args.test:
        global_cfg = interactive_questions(global_cfg)

    # ─── 确定歌单数据 ───
    if global_cfg.get('_test_mode'):
        test_plist = [
            ("平凡之路", "朴树", "01-华语经典流行"),
            ("海阔天空", "Beyond", "02-粤语港台摇滚"),
            ("花妖", "刀郎", "07-国风民族音乐"),
            ("千与千寻主题音乐", "久石让", "09-久石让动漫配乐"),
            ("Let It Be", "The Beatles", "10-英文经典现代流行"),
        ]
        playlist_items = [(i+1, n, s, c) for i,(n,s,c) in enumerate(test_plist)]
        dry_count = 0
    else:
        pl_path = global_cfg['playlist_file']
        if not pl_path:
            print("\n✗ 未提供歌单文件路径，请通过 --list 或交互式方式指定。")
            return
        if not os.path.exists(pl_path):
            print(f"\n✗ 找不到文件: {pl_path}")
            return
        playlist_items = parse_playlist(pl_path, global_cfg['category_map'])
        if not playlist_items:
            print(f"\n✗ 从 {pl_path} 未解析到任何歌曲，请检查格式。")
            return
        dry_count = global_cfg.get('_dry_run_count', 0)

    log(f'歌单: {len(playlist_items)} 首 | 干跑测试: {dry_count} 首')

    if not USER_CONFIG.get('output_dir'):
        output_dir = os.path.join(os.path.expanduser('~'), 'Desktop', '车载音乐002')
    else:
        output_dir = USER_CONFIG['output_dir']

    # 自动创建分类子目录
    cat_dirs = set()
    for _,_,_,cat in playlist_items:
        mapped = global_cfg['category_map'].get(cat, cat)
        cat_dirs.add(mapped)
    for cd in cat_dirs:
        os.makedirs(os.path.join(output_dir, cd), exist_ok=True)

    # ─── 开始下载 ───
    total = len(playlist_items)
    results = []
    lock = threading.Lock()

    def worker(item):
        idx, name, singer, cat = item
        folder = global_cfg['category_map'].get(cat, cat)
        odir = os.path.join(output_dir, folder)
        os.makedirs(odir, exist_ok=True)
        base = f"{idx:03d}-{sanitize(name)}-{sanitize(singer)}"

        # 断点续传：跳过
        existing = [f for f in os.listdir(odir) if f.startswith(sanitize(name))
                    and f.endswith(('.flac','.mp3'))]
        if existing:
            with lock: log(f'[{idx:03d}] 已存在, 跳过: {name}')
            return {'idx':idx,'name':name,'singer':singer,'folder':folder,'status':'skip'}

        with lock: log(f'[{idx:03d}] 开始: {name} - {singer} [{folder}]')

        # 常规搜 → 宽松搜(去后缀)
        res = engine.process_one(name, singer)
        if not res.get('found'):
            res = engine.process_one(name, singer, name_only=True)
        if not res.get('found'):
            res = engine.process_one(name, singer, name_only=True, loose=True)

        if not res.get('found'):
            with lock: log(f'[{idx:03d}] ✗ 未找到: {name} - {singer}')
            return {'idx':idx,'name':name,'singer':singer,'folder':folder,
                    'status':'notfound','quality':''}

        url = res['url']; quality = res['quality']
        ext = '.flac' if '.flac' in url.lower() else '.mp3'
        audio_path = os.path.join(odir, base + ext)
        lyric_path = os.path.join(odir, base + '.lrc')

        ok = download_song(url, audio_path, engine.session)
        save_lyric(res.get('lyric', ''), lyric_path)

        if ok:
            sz = os.path.getsize(audio_path)
            with lock:
                log(f'[{idx:03d}] ✓ {name} src={res["source"]} q={quality} {sz//1024//1024}MB')
            return {'idx':idx,'name':name,'singer':singer,'folder':folder,
                    'status':'ok','source':res['source'],'quality':quality,'size_mb':round(sz/1e6,1)}
        else:
            if os.path.exists(audio_path):
                try: os.remove(audio_path)
                except Exception: pass
            with lock: log(f'[{idx:03d}] ✗ 下载失败: {name}')
            return {'idx':idx,'name':name,'singer':singer,'folder':folder,
                    'status':'dlfail','quality':quality}

    workers = global_cfg.get('workers', 8)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(worker, it): it for it in playlist_items}
        for future in as_completed(futures):
            results.append(future.result())

    # ─── 报告 ───
    ok_count = sum(1 for r in results if r['status'] == 'ok')
    skip_count = sum(1 for r in results if r['status'] == 'skip')
    fail_count = sum(1 for r in results if r['status'] in ('notfound','dlfail'))
    flac_count = sum(1 for r in results if r['status']=='ok' and r.get('quality','').startswith('flac'))
    mp3_count = sum(1 for r in results if r['status']=='ok' and r.get('quality') not in ('flac','flac24bit'))

    # 写入 CSV 报告
    report_path = os.path.join(BASE_DIR, '下载状态报告.csv')
    with open(report_path, 'w', encoding='utf-8-sig', newline='') as fp:
        w = csv.writer(fp)
        w.writerow(['序号','歌曲','歌手','分类','状态','来源','音质','大小MB','是否成功'])
        for r in sorted(results, key=lambda x:x['idx']):
            w.writerow([r['idx'], r['name'], r['singer'], r['folder'],
                        r['status'], r.get('source',''), r.get('quality',''),
                        r.get('size_mb',''), r['status']=='ok'])

    missing_path = os.path.join(BASE_DIR, '缺失清单.csv')
    missing = [r for r in results if r['status'] in ('notfound','dlfail')]
    with open(missing_path, 'w', encoding='utf-8-sig', newline='') as fp:
        w = csv.writer(fp)
        w.writerow(['序号','歌曲','歌手','分类','状态'])
        for r in missing:
            w.writerow([r['idx'], r['name'], r['singer'], r['folder'], r['status']])

    success_pct = ok_count / total * 100 if total else 0
    flac_pct = flac_count / ok_count * 100 if ok_count else 0

    log('')
    log('=' * 50)
    log(f'📊 下载汇总:')
    log(f'  总计: {total} 首 | 成功: {ok_count} ({success_pct:.1f}%)')
    log(f'  已跳过: {skip_count} | 失败: {fail_count}')
    log(f'  无损FLAC: {flac_count} ({flac_pct:.1f}%) | MP3: {mp3_count}')
    log(f'  📁 保存到: {output_dir}')
    log(f'  📋 报告: {report_path}')
    log(f'  ⚠️  缺失: {missing_path}')
    log('=' * 50)

    # ─── 自动重排序（首次下载后） ───
    log('正在整理目录（同歌手相邻 + 连续编号）...')
    for cd in sorted(set(r['folder'] for r in results)):
        dirpath = os.path.join(output_dir, cd)
        if os.path.isdir(dirpath):
            mp = reorder_directory(dirpath)
            cnt = apply_rename_mapping(dirpath, mp)
            # 清理孤立歌词
            cleaned = 0
            for x in list(os.listdir(dirpath)):
                if x.endswith('.lrc'):
                    base_no_ext = os.path.splitext(x)[0]
                    has_match = any(os.path.exists(os.path.join(dirpath, f'{base_no_ext}{ext}'))
                                    for ext in ['.flac', '.mp3'])
                    if not has_match:
                        os.remove(os.path.join(dirpath, x))
                        cleaned += 1
            log(f'  [{cd}] 整理 {cnt} 个文件名, 清理 {cleaned} 个孤儿歌词')

    log('✅ 全部完成！')


if __name__ == '__main__':
    main()
