# -*- coding: utf-8 -*-
"""
灵兽江湖存档修改器 (LingShou Save Editor)
==========================================
作用: 读取 / 粘贴 灵兽江湖的 *.es3 存档文件, 枚举并修改 "ItemHad" 段中所有道具的名称与数量,
      支持一键全部改为 9999、表格内单个直接编辑、新增/删除道具, 其余数据段(装备/武功/地图等)原样保留。

技术要点:
  - es3 是 Unity EasySave 风格的文本序列化格式。本工具只对 "ItemHad" 段做
    「行级解析 + 整段重建」, 不做全文件 JSON 解析, 因此其它段落逐字节保留。
  - 解析/生成逻辑是纯函数(见 find_itemhad_line / parse_itemhad / build_itemhad_lines /
    apply_itemhad_text), 不依赖 GUI, 便于自动化测试与后续扩展。
  - 重建时自动复用原文件的缩进 / 段头 / 段尾 / 换行风格, 兼容不同缩进与 LF/CRLF。
  - 已有道具的 _GetTimeNew 原值保留, 新增道具 _GetTimeNew 记 0; _DressType 恒为 1,
    _LockHp 恒为 0, _Name 与字典键(道具名)保持一致 —— 与游戏存档规律一致。

版本: v2.6.0 (2026-09-05)

新增(v2.6.0): 「新增道具」弹窗改为 左右双栏 —— 左栏 分类树(可勾选): 按 内存所有道具.json 的
            dataset/<大分类>/<小分类>/… 分级, 覆盖 7 大分类(equip装备/item道具/recipe配方/
            bookcontent书籍/kangfu武功秘籍/skillcom技能合成/shanhailu山海录), 每类下按路径段
            多级细分(大→小→细); 勾选某分类=把该分类及全部下级道具纳入右侧候选, 可多选大/小/细
            分类, 勾「大分类」自动包含其所有下级, 展开后反选子分类可精确排除(父分类自动半选)。
            数据源 程序目录/道具分类.json(由 _scaffold/build_item_categories.py 生成); 右栏对
            候选保留 中文/拼音/首字 搜索、Ctrl/Shift 多选、全选、自定义名、「仅显示缺少」, 可
            分类+搜索叠加。**默认不勾选**: 勾某分类(或其中细分类)右侧即只显示该分类道具(直观可见), 空态给引导提示, 未勾选但有搜索词=全库给建议, 「全勾选」=全部。缺 道具分类.json 时自动回退 道具名.json 平铺列表(行为同 v2.5.x)。另支持<b>带引号特殊名</b>(碎“肉”、剑令“地绝”等): 名字含中文弯引号 “ ” 时写入 es3 自动把引号转义为反斜杠+引号(与游戏存储一致), 读回自动还原, 库/界面均存干净名。另「商店NPC」页新增修改 折扣 Discount(默认一键 0.1)/刷新日 RefreshDay(默认一键 1)。

新增(v2.5.1): 「商店NPC」页签左侧新增 地方/门派 分类下拉——分类取自 内存所有道具.json 的
            dataset/shop/<分类>/(anju安居城/guanglin广临城/heishi黑市/hexing禾兴城/linzhou临州城/
            longju龙居城/menpai门派/other其他/wutian吾天城/xianghuocun乡火村/xining息宁城/yuehan
            岳汉城/chapter5第五章秘境等), 由 _scaffold/build_shop_cities.py 生成 商店分类.json;
            可与 NPC 中文/拼音/首字 搜索叠加过滤。
"""
import json
import os
import re
import sys
import threading
import time

__version__ = "2.6.0"
APP_NAME = "灵兽江湖存档修改器"
# 道具数量上限: 21 亿(用户指定 2100000000; 不超过 32 位有符号上限 2147483647)。
# 所有数字框/批量改/校验统一用这个上限。
MAX_ITEM_COUNT = 2100000000

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QToolBar, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QDialog, QLineEdit, QSpinBox, QDoubleSpinBox,
    QPlainTextEdit, QDialogButtonBox, QFileDialog, QMenu, QMessageBox,
    QToolButton, QCheckBox, QComboBox, QListWidget, QListWidgetItem,
    QStatusBar, QGroupBox, QScrollArea, QFormLayout, QTabWidget,
    QTreeWidget, QTreeWidgetItem,
)

# ============================ 核心算法层(纯函数, 不依赖 GUI) ============================

class Es3Item:
    """ItemHad 中的一个道具条目。"""
    __slots__ = ("name", "count", "get_time", "dress_type", "lock_hp")

    def __init__(self, name, count=9999, get_time=None, dress_type=None, lock_hp=None):
        self.name = name          # 道具名(同时作为字典键 与 _Name 字段值)
        self.count = count        # _Count 数量
        self.get_time = get_time      # 原始 _GetTimeNew 文本; None -> 重建为 0
        self.dress_type = dress_type  # 原始 _DressType 文本; None -> 重建为 1
        self.lock_hp = lock_hp        # 原始 _LockHp 文本; None -> 重建为 0

    def __repr__(self):
        return "Es3Item(%r, count=%r, get_time=%r)" % (self.name, self.count, self.get_time)


def find_itemhad_line(lines, key="ItemHad"):
    """返回包含 `"<key>" :` 的行索引(默认 ItemHad; 传 key="SellItems" 可定位商店卖品段); 找不到返回 -1。
    用带引号的完整键名匹配, 可避免误命中 "ItemHadTemp" 等前缀相似的段。"""
    pat = re.compile(r'"%s"\s*:' % re.escape(key))
    for i, ln in enumerate(lines):
        if pat.search(ln):
            return i
    return -1


def parse_itemhad(lines, start_idx, key="ItemHad"):
    """解析「道具字典段」(默认 ItemHad; 传 key="SellItems" 可解析商店卖品段)。

    返回 (items, indent, close_idx); 解析失败返回 (None, None, None)。
      items     : list[Es3Item], 按文件中出现顺序
      indent    : dict, 记录段头前缀/字段缩进/物品闭合缩进/段尾行, 供原样重建
      close_idx : 段尾行所在行索引(含)
    段尾行兼容两种形态: `},`(容器后还有同级字段) 或 `}`(本段即所在对象末尾字段)。
    """
    header = lines[start_idx]
    m = re.search(r'"%s"\s*:\s*\{' % re.escape(key), header)
    if not m:
        return None, None, None
    indent = {
        "header_prefix": header[:m.end()],  # 例如 '\t\t"ItemHad" : {'
        "body_indent": "\t\t\t\t",          # 物品字段行的缩进(解析时会按实际覆盖)
        "close_indent": "\t\t\t",           # 物品闭合 '}' 的缩进(解析时会按实际覆盖)
        "section_close": None,              # 段尾整行 例如 '\t\t},\n'(含换行)
    }
    suffix = header[m.end():]
    items = []
    cur = None

    # 第一件物品的头内联在段头行: "ItemHad" : {"铜钱":{   (regex 已把开头的 `{` 吞进匹配)
    m1 = re.search(r'"([^"{}]+)":\{', suffix)
    if m1:
        cur = Es3Item(_es3_unescape_name(m1.group(1)))
    else:
        # 空段且同一行闭合 "ItemHad" : {} 的情况
        if re.search(r'"%s"\s*:\s*\{\s*\}' % re.escape(key), header):
            leading = header[:header.find('"%s"' % key)]
            indent["section_close"] = leading + "},\n"
            return [], indent, start_idx
        # 空段分多行: "ItemHad" : {\n},\n —— 交给主循环找容器闭合行
        cur = None

    close_idx = None
    i = start_idx + 1
    n = len(lines)
    while i < n:
        ln = lines[i]
        ln_s = ln.rstrip("\r\n")  # 兼容 CRLF/LF
        # 空段(段头无内联物品): 直接遇本容器闭合行('}' 或 '},')即段尾
        if cur is None and re.match(r'^\s*\}[\s,]*$', ln_s):
            indent["section_close"] = ln
            close_idx = i
            break
        # 新物品头: },"名称":{   (同时闭合上一物品)
        m2 = re.match(r'^\s*\},"([^"{}]+)":\{', ln)
        if m2:
            if cur is not None:
                items.append(cur)
            indent["close_indent"] = ln[:ln.index('}')]
            cur = Es3Item(_es3_unescape_name(m2.group(1)))
            i += 1
            continue
        # 最后一件物品闭合: '}'
        if re.match(r'^\s*\}$', ln_s):
            if cur is not None:
                items.append(cur)
            indent["close_indent"] = ln[:ln.index('}')]
            cw = len(ln) - len(ln.lstrip(" \t"))
            # 其后应紧跟本段容器闭合行('}' 或 '},', 缩进不深于物品闭合行)
            j = i + 1
            while j < n:
                lj = lines[j]
                ljs = lj.rstrip("\r\n")
                if not ljs.strip():
                    j += 1
                    continue
                if re.match(r'^\s*\}[\s,]*$', ljs) and \
                        len(lj) - len(lj.lstrip(" \t")) <= cw:
                    indent["section_close"] = lj
                    close_idx = j
                    break
                break
            break
        # 普通字段行
        if cur is not None:
            mc = re.search(r'"_Count"\s*:\s*(\d+)', ln)
            if mc:
                cur.count = int(mc.group(1))
            md = re.search(r'"_DressType"\s*:\s*([0-9.]+)', ln)
            if md:
                cur.dress_type = md.group(1)
            ml = re.search(r'"_LockHp"\s*:\s*([0-9.]+)', ln)
            if ml:
                cur.lock_hp = ml.group(1)
            mg = re.search(r'"_GetTimeNew"\s*:\s*([0-9.]+)', ln)
            if mg:
                cur.get_time = mg.group(1)
            di = ln.find('"_DressType"')
            if di >= 0:
                indent["body_indent"] = ln[:di]
        i += 1

    return items, indent, close_idx


def build_itemhad_lines(items, indent, newline="\n"):
    """按原缩进风格重建 ItemHad 段的行列表(每行含换行)。"""
    header_prefix = indent["header_prefix"]
    body = indent["body_indent"]
    close = indent["close_indent"]
    sec = indent.get("section_close")
    if not sec:
        leading = header_prefix[:header_prefix.find('"ItemHad"')]
        sec = leading + "},\n"
    out = []
    if not items:
        out.append(header_prefix + "}" + newline)
        out.append(sec)
        return out
    # 道具名含中文弯引号( “ ” )时, 写文件要按游戏存储形态加反斜杠(碎“肉” → 碎\“肉\”)
    out.append(header_prefix + '"%s":{' % _es3_escape_name(items[0].name) + newline)
    for k, it in enumerate(items):
        esc = _es3_escape_name(it.name)
        if k > 0:
            out.append(close + '},"%s":{' % esc + newline)
        dt = it.dress_type if it.dress_type is not None else 1
        lh = it.lock_hp if it.lock_hp is not None else 0
        gt = it.get_time if it.get_time is not None else 0
        out.append(body + '"_DressType" : %s,' % dt + newline)
        out.append(body + '"_Count" : %d,' % int(it.count) + newline)
        out.append(body + '"_Name" : "%s",' % esc + newline)
        out.append(body + '"_LockHp" : %s,' % lh + newline)
        out.append(body + '"_GetTimeNew" : %s' % gt + newline)
    out.append(close + '}' + newline)
    out.append(sec)
    return out


def apply_itemhad_text(text, items, newline=None, key="ItemHad"):
    """把新物品列表写回完整 es3 文本(仅替换 key 段, 默认 ItemHad; 传 key="SellItems" 改商店卖品段)。

    text  : 完整 es3 文本
    items : list[Es3Item] 新的物品列表
    返回  : 重建后的完整文本; 其它段落逐字节保留。
    """
    lines = text.splitlines(keepends=True)
    start_idx = find_itemhad_line(lines, key=key)
    if start_idx < 0:
        raise ValueError("未找到 %s 段" % key)
    parsed, indent, close_idx = parse_itemhad(lines, start_idx, key=key)
    if close_idx is None:
        raise ValueError("%s 段解析失败" % key)
    if newline is None:
        newline = "\r\n" if any(l.endswith("\r\n") for l in lines) else "\n"
    block = build_itemhad_lines(items, indent, newline)
    return "".join(lines[:start_idx] + block + lines[close_idx + 1:])


# ============================ 文件读写(UTF-8 / BOM 兼容) ============================

def read_es3_text(path):
    """读取 es3 文件, 返回 (文本, BOM字节)。自动剥离 UTF-8 BOM。"""
    with open(path, "rb") as f:
        raw = f.read()
    bom = b""
    if raw.startswith(b"\xef\xbb\xbf"):
        bom = b"\xef\xbb\xbf"
        raw = raw[3:]
    return raw.decode("utf-8"), bom


def write_es3_text(path, text, bom=b""):
    """把文本写回 es3 文件, 原样补回 BOM。"""
    with open(path, "wb") as f:
        f.write(bom + text.encode("utf-8"))


# ============================ 工具函数(名称校验等) ============================

_NAME_RE = re.compile(r'[^{}"\\\r\n]+')


def _es3_escape_name(name):
    """把含中文弯引号( “ ” )的道具名转成 es3 文件里的形态: 引号前加反斜杠。

    例: 碎“肉” → 碎\\“肉\\”(与游戏存档里这类特殊名的存储一致)。
    仅处理 “ ” 两个弯引号(ASCII 双引号本身在 validate 里不允许, 不影响)。
    """
    return "".join("\\" + c if c in ("\u201c", "\u201d") else c for c in (name or ""))


def _es3_unescape_name(raw):
    """把 es3 文件里读到的道具名还原成显示名: 把 \\“ / \\” (以及 \\") 还原成对应引号。"""
    return re.sub(r"\\([\u201c\u201d\"])", r"\1", raw or "")


def validate_item_name(name):
    """返回 (是否合法, 错误信息)。名称不能为空、不能含 { } " \\ 换行。"""
    if not name:
        return False, "道具名称不能为空"
    if not _NAME_RE.fullmatch(name):
        return False, "道具名称含非法字符(不能含 { } \" \\ 换行)"
    return True, ""


# ============================ 道具名库(道具名.json) ============================

def app_dir():
    """程序目录(开发=脚本目录, 打包=exe 目录)。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.argv[0]))
    return os.path.dirname(os.path.abspath(__file__))


def app_icon():
    """程序图标(程序目录/icon.ico); 缺失返回空 QIcon(走系统默认图标)。"""
    p = os.path.join(app_dir(), "icon.ico")
    if os.path.exists(p):
        return QIcon(p)
    return QIcon()


def get_item_names_path():
    """道具名库文件路径: 程序目录下 道具名.json。"""
    return os.path.join(app_dir(), "道具名.json")


def extract_item_names(text):
    """从 es3 文本的 ItemHad 段提取全部道具名, 去重。
    只取 ItemHad 段(本工具可编辑的段): 道具名以该段字典键为准,
    避免混入装备/武功/好友/perk 等不可加入 ItemHad 的名字。"""
    lines = text.splitlines(keepends=True)
    start = find_itemhad_line(lines)
    if start < 0:
        return set()
    items, _, close_idx = parse_itemhad(lines, start)
    if close_idx is None:
        return set()
    return {it.name for it in items if it.name}


def load_item_names(path=None):
    """读取道具名库(JSON 字符串数组); 失败返回空列表。名字统一为“干净名”(含弯引号者无转义反斜杠)。"""
    path = path or get_item_names_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [_es3_unescape_name(str(x).strip()) for x in data if str(x).strip()]


def save_item_names(names, path=None):
    """把道具名去重、排序后原子写入 JSON; 返回写入后的列表(弯引号名统一存干净名, 不带转义反斜杠)。"""
    path = path or get_item_names_path()
    clean = sorted({_es3_unescape_name(n.strip()) for n in names if n.strip()})
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(clean, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)
    return clean


def merge_item_names(names, path=None):
    """把一份道具名列表并入 道具名库(自动去重; 库文件存在历史重复一并清洗)。

    返回 (新增名列表, 库去重后总数); 仅在有新增或需清洗时才写盘。
    """
    existing = load_item_names(path)   # 可能含历史重复
    cur = set(existing)
    wanted = {n.strip() for n in names if n and n.strip()}
    new = sorted(wanted - cur)
    merged = sorted(cur | wanted)      # 与库中已有名比对后合并去重
    if new or len(existing) != len(cur):
        save_item_names(merged, path)  # 仅在有新增或需清洗重复时写盘
    return new, len(merged)


def merge_item_names_from_text(text, path=None):
    """每次读取存档都会调用: 把档内 ItemHad 道具名与道具名库比对, 新名才加入(不重名); 库文件存在历史重复会一并清洗。返回(新增名列表, 库去重后总数)。"""
    return merge_item_names(extract_item_names(text), path)


# ============================ 地图跳转点库(地图跳转点.json) ============================

def get_map_jump_path():
    """地图跳转点库文件路径: 程序目录/地图跳转点.json。"""
    return os.path.join(app_dir(), "地图跳转点.json")


def load_map_jump_names(path=None):
    """读取地图跳转点库(JSON 字符串数组); 缺失/损坏返回空列表。"""
    path = path or get_map_jump_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [str(x) for x in data if isinstance(x, str) and x.strip()]


# ============================ 拼音搜索(拼音表.json, 运行时不依赖第三方库) ============================

def get_pinyin_map_path():
    """拼音映射文件路径: 程序目录/拼音表.json({汉字: 拼音...})。"""
    return os.path.join(app_dir(), "拼音表.json")


_PINYIN_CACHE = {}


def load_pinyin_map(path=None):
    """读取 拼音表.json → {汉字: [拼音列表]}; 缺失/损坏返回 {}。"""
    path = path or get_pinyin_map_path()
    if path in _PINYIN_CACHE:
        return _PINYIN_CACHE[path]
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    out = {}
    for ch, val in data.items():
        if not isinstance(ch, str) or not ch:
            continue
        if isinstance(val, str):
            out[ch] = [val]
        elif isinstance(val, list):
            out[ch] = [str(x) for x in val if str(x).strip()]
    _PINYIN_CACHE[path] = out
    return out


def _name_pinyin(name, pmap):
    """返回 (首字母串, 全拼串), 均小写; 数字/字母原样保留, 未收录汉字退回其本身。"""
    initials, full = [], []
    for c in name:
        if "\u4e00" <= c <= "\u9fff":
            ps = pmap.get(c)
            if isinstance(ps, (list, tuple)) and ps:
                p0 = ps[0]              # 值可为 [拼音] 或单拼音字符串
            elif ps:
                p0 = ps
            else:
                p0 = c.lower()          # 未收录汉字: 退回其本身
            initials.append(p0[0])
            full.append(p0)
        else:
            cl = c.lower()
            initials.append(cl)
            full.append(cl)
    return "".join(initials), "".join(full)


def filter_item_names(names, query, pmap=None, mode=0):
    """按 query 过滤道具名列表(保持原顺序)。

    mode: 0=自动(中文子串/拼音全拼/首字母/数字任一命中), 1=仅中文(子串), 2=仅拼音(全拼/首字母)。
    query 为空返回全部; pmap 缺省时自动读 拼音表.json。
    """
    query = (query or "").strip().lower()
    if not query:
        return list(names)
    if pmap is None:
        pmap = load_pinyin_map()
    out = []
    for n in names:
        if not n:
            continue
        nl = n.lower()
        if mode == 1:  # 仅中文/数字子串
            if query in nl:
                out.append(n)
            continue
        _i, _f = _name_pinyin(n, pmap)
        if mode == 2:  # 仅拼音全拼/首字母
            if query in _f or query in _i:
                out.append(n)
            continue
        # 自动: 中文子串 / 拼音全拼 / 首字母 / 数字编号, 任一命中
        if query in nl or query in _f or query in _i:
            out.append(n)
    return out


# ============================ 最近打开历史(历史记录.json) ============================

HISTORY_MAX = 10


def get_history_path():
    """最近打开历史文件路径: 程序目录/历史记录.json。"""
    return os.path.join(app_dir(), "历史记录.json")


def load_history(path=None):
    """读取最近打开历史(字符串数组, 最新在前); 失败/损坏返回 []。"""
    path = path or get_history_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [str(p).strip() for p in data if isinstance(p, str) and str(p).strip()]


def save_history(paths, path=None):
    """把历史列表原子写入 JSON(失败静默, 不阻塞主流程)。"""
    path = path or get_history_path()
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(paths, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except OSError:
        pass


def push_history(path, paths=None, limit=HISTORY_MAX, path_out=None):
    """把 path 提到历史最前(去重)并写盘; 返回更新后的列表。"""
    cur = list(paths) if paths is not None else load_history(path_out)
    apath = os.path.abspath(path)
    norm = os.path.normcase
    cur = [p for p in cur if norm(p) != norm(apath)]
    cur.insert(0, apath)
    cur = cur[:limit]
    save_history(cur, path_out)
    return cur


# ============================ 程序设置(设置.json) ============================

def get_settings_path():
    """程序设置文件路径: 程序目录/设置.json。"""
    return os.path.join(app_dir(), "设置.json")


def load_app_settings(path=None):
    """读取设置 JSON(dict); 缺失/损坏返回 {}。"""
    path = path or get_settings_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_app_settings(data, path=None):
    """把设置 dict 原子写入 JSON(失败静默)。"""
    path = path or get_settings_path()
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except OSError:
        pass


# ============================ 多角色属性(主角/队友)定位与改写(纯函数) ============================
# 说明: es3 其余大段(装备/武功/地图等)不逐字节解析。这里只在「已知容器」内做
#       精确的子串替换: 数值改数字记号、编号字典只把各编号后的数值改掉、数组追加元素,
#       键名/缩进/其余内容一律原样保留, 因此不会误伤其它字段。

# 主角(PlayerData.value) 常用字段的一键默认值(仅这些字段提供“默认”按钮)
PLAYER_DEFAULTS = {
    "Lv": 99,
    "Exp": 100000000,       # 经验: 默认一键 1 亿
    "AddProSpot": 999,
    "UseProSpot": 0,
    "AddLifeSpot": 999,
    "UseLifeSpot": 0,
    "Power": 999,
    "Perception": 999,
    "Agility": 999,
    "PhysicalPower": 999,
    "Channel": 999,
    "BerathSkill": 999,
    "WuXing": 999,
    "Speed": 999,
    "TalentAdd": 999,
    "UseLifePeak": 0,       # 已使用的生活点数
}

# 主角常用字段中文名(仅用于界面展示; 其它标量直接显示键名)
PLAYER_LABELS = {
    "Lv": "等级", "Exp": "经验", "AddProSpot": "总属性", "UseProSpot": "已用属性",
    "AddLifeSpot": "总特性点", "UseLifeSpot": "已用特性点",
    "_BaseHp": "基础血气", "_Hp": "血气", "_MaxHp": "最大血气",
    "Power": "力道", "Perception": "感知", "Agility": "灵气",
    "PhysicalPower": "体魄", "Channel": "经脉", "BerathSkill": "速度",
    "WuXing": "悟性", "Speed": "移动范围", "Talent": "天赋",
    "TalentAdd": "特性点", "UseTalent": "已用天赋", "UseLifePeak": "已用生活点数",
    "FoodItemLimit": "物品栏上限", "_BattleSpeed": "战斗速度",
    "_DifficultyType": "难度", "_TiLiNum": "体力", "_LifeCheck": "生命检测",
    "_TuJian": "图鉴", "_Round": "回合", "_Dlc": "DLC",
}

# 队友(AddFriends 内各角色) 常用字段一键默认值(与主角对应, 键名带下划线)
FRIEND_DEFAULTS = {
    "_Lv": 99,
    "_AddProSpot": 999,
    "_UseProSpot": 0,
    "_Power": 999,
    "_Perception": 999,
    "_Agility": 999,
    "_PhysicalPower": 999,
    "_Channel": 999,
    "_BerathSkill": 999,
    "_WuXing": 999,
    "_Speed": 999,
    "_TalentAdd": 999,
}

# 队友字段中文名
FRIEND_LABELS = {
    "_Lv": "等级", "_AbName": "英文ID", "_Name": "名字", "_Skin": "皮肤",
    "_AddProSpot": "总属性", "_UseProSpot": "已用属性",
    "_BaseHp": "基础血气", "_Hp": "血气", "_MaxHp": "最大血气",
    "_Power": "力道", "_Perception": "感知", "_Agility": "灵气",
    "_PhysicalPower": "体魄", "_Channel": "经脉", "_BerathSkill": "速度",
    "_Speed": "移动范围", "_TalentAdd": "特性点", "_WuXing": "悟性",
    "_UseTalent": "已用天赋", "FoodItemLimit": "物品栏上限",
    "_TuJian": "图鉴", "_ItemCheckDressRongCuo": "熔错校验",
    "_MinLvOriginal": "初始等级下限", "_MaxLvOriginal": "初始等级上限",
    "_PowerOriginal": "初始力道", "_PerceptionOriginal": "初始感知",
    "_AgilityOriginal": "初始灵气", "_PhysicalPowerOriginal": "初始体魄",
    "_ChannelOriginal": "初始经脉", "_BerathSkillOriginal": "初始速度",
    "_TalentAddOriginal": "初始特性点",
}

# 六维编号对应的中文名(主角/队友的 SixProCurrent 与 _Power.._BerathSkill 顺序一致)
SIX_LABELS = {1: "力道", 2: "感知", 3: "灵气", 4: "体魄", 5: "经脉", 6: "速度"}

# 武学/生活技能/好感度等“编号或名字→数值”字典的一键默认值
KONGFU_EXP_DEFAULT = 999999   # 武学经验 KongFuTypeLv / _KongFuTypeLv
LIFEEXP_DEFAULT = 999999      # 生活技能经验 LifeExp
LOVE_DEFAULT = 999            # 好感度 FriendLoveNum
SIXPRO_DEFAULT = 999          # 六维当前值 SixProCurrent

# 结构扫描用 C 级正则(整段跳过引号串; 一次只匹配一个结构字符), 极大提速大文件扫描
_STRUCT_RE = re.compile(r'"(?:\\.|[^"\\])*"|[{}[\],]')
_NUM_RE = re.compile(r"[+-]?[0-9]*\.?[0-9]+(?:[eE][+-]?[0-9]+)?")


def _matching_end(text, start):
    """text[start] 为 '{' 或 '['; 返回配对的 '}' / ']' 下标(含)。字符串内括号忽略。找不到返回 len(text)-1。"""
    opener = text[start]
    closer = "}" if opener == "{" else "]"
    depth = 0
    for m in _STRUCT_RE.finditer(text, start):
        tok = m.group(0)
        if tok[0] == '"':
            continue            # 引号串整体跳过(C 级正则, 不再逐字符/逐引号扫描)
        if tok == opener:
            depth += 1
        elif tok == closer:
            depth -= 1
            if depth == 0:
                return m.start()
    return len(text) - 1


def _string_end(text, i):
    """i 指向开引号; 返回闭引号后一位(排除)。处理 \\ 转义。"""
    i += 1
    n = len(text)
    while i < n:
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == '"':
            return i + 1
        i += 1
    return n


def _key_value_offset(seg):
    """在条目串里找首个“不在引号内”的冒号(键引号里可能含冒号)。
    返回 (键原串, 冒号后一位偏移); 找不到返回 None。"""
    instr = False
    i = 0
    n = len(seg)
    while i < n:
        c = seg[i]
        if c == '"':
            if instr:
                bs = 0
                j = i - 1
                while j >= 0 and seg[j] == "\\":
                    bs += 1
                    j -= 1
                if bs % 2 == 0:
                    instr = False
            else:
                instr = True
        elif c == ":" and not instr:
            return seg[:i], i + 1
        i += 1
    return None


def _key_display(key_raw):
    """把键原串转成展示名: 引号键取引号内原文(不解码转义), 否则去空白。"""
    k = key_raw.strip()
    if k.startswith('"'):
        # 取首引号后到配对的尾引号之间
        end = k.find('"', 1)
        if end < 0:
            return k
        return k[1:end]
    return k


def _quoted_strings(s):
    """提取字符串里所有 "..." 的内容(尊重 \\ 转义)。"""
    out = []
    i = 0
    n = len(s)
    while i < n:
        if s[i] == '"':
            end = _string_end(s, i)
            out.append(s[i + 1:end - 1])
            i = end
        else:
            i += 1
    return out


def _entry_values(text, open_i):
    """把 open_i 处对象/数组体内(不含外层括号)按 0 层逗号切成条目。

    返回 list[(key_disp, val_start, val_end, val_text)]:
      - 对象: key_disp=引号键的引号内文本(未转义); 数组: key_disp=None
      - val_start/val_end: 值文本在 text 的绝对范围(val_text 含尾随空白)
    """
    close_i = _matching_end(text, open_i)
    depth = 0
    commas = []
    for m in _STRUCT_RE.finditer(text, open_i + 1, close_i):
        tok = m.group(0)
        if tok[0] == '"':
            continue            # 引号串整体跳过
        if tok == "{" or tok == "[":
            depth += 1
        elif tok == "}" or tok == "]":
            depth -= 1
        elif tok == "," and depth == 0:
            commas.append(m.start())
    bounds = [open_i + 1] + [c + 1 for c in commas] + [close_i]
    is_obj = text[open_i] == "{"
    out = []
    for b in range(len(bounds) - 1):
        a0, a1 = bounds[b], bounds[b + 1]
        seg = text[a0:a1]
        if is_obj:
            kv = _key_value_offset(seg)
            if kv is None:
                continue
            key_raw, voff = kv
            key_disp = _key_display(key_raw)
            val_start = a0 + voff
            while val_start < a1 and text[val_start] in " \t\r\n":
                val_start += 1
            out.append((key_disp, val_start, a1, text[val_start:a1]))
        else:
            vs = a0
            while vs < a1 and text[vs] in " \t\r\n":
                vs += 1
            out.append((None, vs, a1, seg))
    return out


def _locate_container(text, path):
    """按 key 路径逐层下钻到对象/数组容器; 每层只认“直接子字段”。返回容器开括号下标, 找不到返回 None。

    path 如 ['savePlayerData', 'value'](主角) / ['saveFriendData', 'value', 'AddFriends', 'shexing'](队友)。
    """
    open_i = None
    for j, k in enumerate(path):
        if j == 0:
            m = re.search(r'^[ \t]*"%s"\s*:\s*([{\[])' % re.escape(k), text, re.M)
            if not m:
                return None
            open_i = m.start(1)
        else:
            if open_i is None:
                return None
            cand = None
            for key_disp, vs, _ve, _vt in _entry_values(text, open_i):
                if key_disp == k and text[vs:vs + 1] in "{[":
                    cand = vs
                    break
            if cand is None:
                return None
            open_i = cand
    return open_i


def _num_token(text, val_start):
    """若 val_start 处是数字则返回 (数字记号原串, 记号结束下标); 否则 None。用 pos 免切片提速。"""
    m = _NUM_RE.match(text, val_start)
    if not m:
        return None
    return text[val_start:m.end()], m.end()


def get_scalar(text, scope, field):
    """读 scope 容器内直接数字字段 field 的原样字符串; 不存在返回 None。"""
    c = _locate_container(text, scope)
    if c is None:
        return None
    for key_disp, vs, _ve, _vt in _entry_values(text, c):
        if key_disp == field:
            tok = _num_token(text, vs)
            if tok:
                return tok[0]
    return None


def set_scalar(text, scope, field, new_num):
    """把 scope 容器内直接数字字段 field 的值改为整数; 返回新文本。字段不存在则原样返回。"""
    c = _locate_container(text, scope)
    if c is None:
        return text
    val = str(int(round(float(new_num))))
    for key_disp, vs, _ve, _vt in _entry_values(text, c):
        if key_disp == field:
            tok = _num_token(text, vs)
            if tok:
                raw, end = tok
                if raw == val:
                    return text
                return text[:vs] + val + text[end:]
    return text


def _apply_subs(text, subs):
    """把若干 (起点, 终点, 替换文本) 一次性重建文本(只整段复制一次, 避免逐条整文本拼接 O(k·n))。
    subs 的位置必须互不重叠且属于原 text。"""
    if not subs:
        return text
    parts = []
    prev = 0
    for s, e, v in sorted(subs, key=lambda x: x[0]):
        if s > prev:
            parts.append(text[prev:s])
        parts.append(v)
        prev = e
    parts.append(text[prev:])
    return "".join(parts)


def set_scalar_defaults(text, scope, defaults):
    """单遍把 scope 容器内 defaults 里出现且为数字的全部字段设为默认值。

    只做一次定位 + 一次遍历(不再每字段各定位/扫描一次), 避免「一键全部默认」在大档上卡顿。
    返回新文本; 无变化原样返回。"""
    c = _locate_container(text, scope)
    if c is None:
        return text
    subs = []
    for key_disp, vs, _ve, _vt in _entry_values(text, c):
        d = defaults.get(key_disp)
        if d is None:
            continue
        tok = _num_token(text, vs)
        if not tok:
            continue
        raw, end = tok
        val = str(int(d))
        if raw != val:
            subs.append((vs, end, val))
    if not subs:
        return text
    return _apply_subs(text, subs)


def set_scalar_in(text, container_open, field, new_num):
    """open 版 set_scalar: 直接给容器开括号下标改单个数字字段(免再定位)。"""
    val = str(int(round(float(new_num))))
    for key_disp, vs, _ve, _vt in _entry_values(text, container_open):
        if key_disp == field:
            tok = _num_token(text, vs)
            if tok:
                raw, end = tok
                if raw == val:
                    return text
                return text[:vs] + val + text[end:]
    return text


def set_scalar_defaults_in(text, container_open, defaults):
    """open 版 set_scalar_defaults: 单遍把 defaults 里的数字字段改默认(免再定位容器)。"""
    subs = []
    for key_disp, vs, _ve, _vt in _entry_values(text, container_open):
        d = defaults.get(key_disp)
        if d is None:
            continue
        tok = _num_token(text, vs)
        if not tok:
            continue
        raw, end = tok
        val = str(int(d))
        if raw != val:
            subs.append((vs, end, val))
    if not subs:
        return text
    return _apply_subs(text, subs)


def iter_flat_dict(text, scope, field):
    """读 scope 容器内字段 field 的字典(编号或名字→数值)的条目:
    返回 [(显示键, 原值字符串)]; 找不到返回 []。"""
    c = _locate_container(text, scope)
    if c is None:
        return []
    for key_disp, vs, _ve, _vt in _entry_values(text, c):
        if key_disp == field and text[vs:vs + 1] == "{":
            out = []
            for kd, vs2, _ve2, _vt2 in _entry_values(text, vs):
                tok = _num_token(text, vs2)
                out.append((kd, tok[0] if tok else _vt2.strip()))
            return out
    return []


def set_flat_dict_all(text, scope, field, new_num):
    """把 scope 容器内字段 field 的字典里全部数字值改为整数(编号/名字键不动)。返回新文本。"""
    c = _locate_container(text, scope)
    if c is None:
        return text
    val = str(int(round(float(new_num))))
    for key_disp, vs, _ve, _vt in _entry_values(text, c):
        if key_disp == field and text[vs:vs + 1] == "{":
            # 从后往前替换, 避免下标错位
            subs = []
            for _kd, vs2, _ve2, _vt2 in _entry_values(text, vs):
                tok = _num_token(text, vs2)
                if tok:
                    raw, end = tok
                    if raw != val:
                        subs.append((vs2, end, val))
            return _apply_subs(text, subs)
    return text


def get_str_array(text, scope, field):
    """读 scope 容器内字段 field 的字符串数组元素(如 _ActiveMap 地点名)。返回列表。"""
    c = _locate_container(text, scope)
    if c is None:
        return []
    for key_disp, vs, _ve, _vt in _entry_values(text, c):
        if key_disp == field and text[vs:vs + 1] == "[":
            inner = text[vs + 1:_matching_end(text, vs)]
            return _quoted_strings(inner)
    return []


def add_str_array(text, scope, field, name):
    """把地点名追加到 scope 容器内字段 field 的字符串数组(已存在同名则跳过)。返回新文本。"""
    name = (name or "").strip()
    if not name:
        return text
    c = _locate_container(text, scope)
    if c is None:
        return text
    for key_disp, vs, _ve, _vt in _entry_values(text, c):
        if key_disp == field and text[vs:vs + 1] == "[":
            close_i = _matching_end(text, vs)
            existing = _quoted_strings(text[vs + 1:close_i])
            if any(e == name for e in existing):
                return text
            body = text[vs + 1:close_i]
            rbody = body.rstrip()
            if rbody:
                ins = vs + 1 + len(rbody)
                return text[:ins] + ',' + '"' + name + '"' + text[ins:]
            return text[:vs + 1] + '"' + name + '"' + text[vs + 1:]
    return text


def remove_str_array(text, scope, field, name):
    """从字符串数组删除指定元素(含前缀逗号/空格处理)。返回新文本。"""
    name = (name or "").strip()
    if not name:
        return text
    c = _locate_container(text, scope)
    if c is None:
        return text
    for key_disp, vs, _ve, _vt in _entry_values(text, c):
        if key_disp == field and text[vs:vs + 1] == "[":
            close_i = _matching_end(text, vs)
            pat = re.compile(r',?\s*"' + re.escape(name) + r'"')
            region = text[vs + 1:close_i]
            new_region, n = pat.subn("", region)
            if n:
                # 删后若只剩空白则数组留空
                return text[:vs + 1] + new_region + text[close_i:]
            return text
    return text


# 主角/队友容器的定位路径
SCOPE_PLAYER = ["savePlayerData", "value"]
SCOPE_MAP = ["saveCustomData", "value"]
SCOPE_FRIENDS = ["saveFriendData", "value", "AddFriends"]
# NPC/商店容器: saveUtilData.value._ShopData.<商店名>{ abName, SellItems{道具...} }
SCOPE_SHOP = ["saveUtilData", "value", "_ShopData"]


# ==================== NPC 商店卖的道具(_ShopData / SellItems) ====================
def shop_records(text):
    """一次枚举 _ShopData 全部商店: 返回 [(键, 显示名, SellItems容器开括号 or None)], 顺序同文件。
    显示名优先取对象内 abName(如 '猪姨'), 缺省用字典键; sell_open 供直接读/改该店卖品, 避免重复全量扫描。"""
    c = _locate_container(text, SCOPE_SHOP)
    if c is None:
        return []
    out = []
    for kd, vs, _ve, _vt in _entry_values(text, c):
        if text[vs:vs + 1] != "{":
            continue
        ab = None
        sopen = None
        for k2, v2, _e2, _t2 in _entry_values(text, vs):
            if k2 == "abName":
                if text[v2:v2 + 1] == '"':
                    qs = _quoted_strings(text[v2:_e2])
                    if qs:
                        ab = qs[0]
            elif k2 == "SellItems" and text[v2:v2 + 1] == "{":
                sopen = v2
        out.append((kd, ab if ab is not None else kd, sopen))
    return out


def _shop_sell_open(text, key):
    """定位商店 key 的 SellItems 容器开括号; 找不到返回 None。"""
    c = _locate_container(text, SCOPE_SHOP + [key])
    if c is None:
        return None
    for kd, vs, _ve, _vt in _entry_values(text, c):
        if kd == "SellItems" and text[vs:vs + 1] == "{":
            return vs
    return None


def shop_sellitems(text, key, sell_open=None):
    """读某商店 SellItems 现有道具 [(名称, 数量)], 顺序同文件; 无该段返回 []。
    可传 sell_open(shop_records 第3项) 跳过重复全量定位。"""
    if sell_open is None:
        sell_open = _shop_sell_open(text, key)
    if sell_open is None:
        return []
    out = []
    for kd, vs, _ve, _vt in _entry_values(text, sell_open):
        if text[vs:vs + 1] != "{":
            continue
        cnt = None
        for k2, v2, _e2, _t2 in _entry_values(text, vs):
            if k2 == "_Count":
                tok = _num_token(text, v2)
                if tok:
                    cnt = int(tok[0])
                break
        out.append((kd, cnt if cnt is not None else 0))
    return out


def shop_add_items(text, key, adds, sell_open=None):
    """把 adds(列表[(道具名, 数量)]) 追加到商店 key 的 SellItems; 与已有/本次重名自动跳过。

    返回 (新文本, 实际新增名列表)。找不到商店/SellItems 或全重名时返回原文本。
    可传 sell_open(shop_records 第3项) 跳过重复全量定位。
    """
    nt = text
    if sell_open is None:
        sell_open = _shop_sell_open(nt, key)
    if sell_open is None:
        return nt, []
    # SellItems 段文本范围: 段头行行首 → 容器闭合行行尾
    hs = nt.rfind("\n", 0, sell_open) + 1
    close = _matching_end(nt, sell_open)
    he = nt.find("\n", close)
    he = len(nt) if he < 0 else he + 1
    seg = nt[hs:he]
    lines2 = seg.splitlines(keepends=True)
    parsed, ind2, cidx = parse_itemhad(lines2, 0, key="SellItems")
    if cidx is None:
        return nt, []
    seen = set(it.name for it in parsed)
    adds2 = []
    for nm, cnt in adds:
        nm = (nm or "").strip()
        if not nm or nm in seen:
            continue
        seen.add(nm)
        adds2.append(Es3Item(nm, int(cnt) if cnt is not None else 999, None))
    if not adds2:
        return nt, []
    newline = "\r\n" if any(l.endswith("\r\n") for l in lines2) else "\n"
    block = build_itemhad_lines(parsed + adds2, ind2, newline)
    return nt[:hs] + "".join(block) + nt[he:], [it.name for it in adds2]


def shop_field(text, key, field):
    """读某商店对象内直接数字字段(如 Discount/RefreshDay)的原样字符串; 无该字段返回 None。"""
    c = _locate_container(text, SCOPE_SHOP + [key])
    if c is None:
        return None
    for kd, vs, _ve, _vt in _entry_values(text, c):
        if kd == field:
            tok = _num_token(text, vs)
            if tok:
                return tok[0]
    return None


def shop_set_field(text, key, field, new_value_text):
    """把某商店对象内直接数字字段 field 的值替换为新文本(如 Discount/RefreshDay)。

    返回 (新文本, 是否发生变更); 找不到商店/字段或该字段非数字时返回 (原文本, False)。
    """
    c = _locate_container(text, SCOPE_SHOP + [key])
    if c is None:
        return text, False
    for kd, vs, _ve, _vt in _entry_values(text, c):
        if kd == field:
            tok = _num_token(text, vs)
            if not tok:
                return text, False
            raw, end = tok
            if raw == new_value_text:
                return text, False
            return text[:vs] + new_value_text + text[end:], True
    return text, False


# ==================== 商店装备(SellEquips): 值=「装备名 → 实例对象数组」 ====================
# SellEquips 排版(与游戏存档一致, 制表符缩进 + CRLF):
#   "SellEquips" : {"1短铁棍":[\r\n\t\t\t\t\t\t{\r\n ... "_Name":"1短铁棍","_Lv":1 ... }
# 值对象字段: _QiItemNames[]/_Name/_Lv/_Durable/_SkillLv{}/_ItemSkillLv{}/_DressType/
#             _GetTimeNew/_IsCanLingHua/_IsFirstGet/_LockDissolve; 同名可多件(数组内多实例)。
def _shop_sellequips_open(text, key):
    """定位商店 key 对象里 SellEquips 字段的字典开括号; 缺失返回 None。"""
    c = _locate_container(text, SCOPE_SHOP + [key])
    if c is None:
        return None
    for kd, vs, _ve, _vt in _entry_values(text, c):
        if kd == "SellEquips" and text[vs:vs + 1] == "{":
            return vs
    return None


def shop_equip_names(text, key, count_too=False):
    """读某商店 SellEquips 里已上架的装备名(顺序同文件, 干净名去引号转义)。

    count_too=True 时返回 [(名字, 该名实例件数)]。无 SellEquips 返回 []。
    """
    o = _shop_sellequips_open(text, key)
    if o is None:
        return []
    out = []
    for kd, vs, _ve, _vt in _entry_values(text, o):
        if text[vs:vs + 1] != "[":
            continue
        cnt = 0
        for _k3, v3, _e3, _t3 in _entry_values(text, vs):
            if text[v3:v3 + 1] == "{":
                cnt += 1
        nm = _es3_unescape_name(kd)
        out.append((nm, cnt) if count_too else nm)
    return out


def _equip_fields_text(l3, l4, name_esc, lv, nl):
    """单个装备实例的字段行(不含首尾花括号; 每行带缩进+换行)。"""
    return (l3 + '"_QiItemNames" : [' + nl +
            l4 + nl +
            l3 + '],' + nl +
            l3 + '"_Name" : "' + name_esc + '",' + nl +
            l3 + '"_Lv" : %d,' % lv + nl +
            l3 + '"_Durable" : 100,' + nl +
            l3 + '"_SkillLv" : {' + nl +
            l3 + '},' + nl +
            l3 + '"_ItemSkillLv" : {' + nl +
            l3 + '},' + nl +
            l3 + '"_DressType" : 1,' + nl +
            l3 + '"_GetTimeNew" : 0,' + nl +
            l3 + '"_IsCanLingHua" : true,' + nl +
            l3 + '"_IsFirstGet" : 0,' + nl +
            l3 + '"_LockDissolve" : false' + nl)


def _equip_objects_text(l2, l3, l4, name_esc, lv, count, nl):
    """生成「从零开始」的 count 个实例对象文本(结束不含数组闭合 ], 末尾已闭对象+换行)。"""
    s = ""
    for i in range(count):
        if i == 0:
            s += l2 + "{" + nl
        else:
            s += l2 + "},{" + nl
        s += _equip_fields_text(l3, l4, name_esc, lv, nl)
    s += l2 + "}" + nl
    return s


def _equip_new_entry_text(l1, l2, l3, l4, name_esc, lv, count, nl):
    """一个新 SellEquips 条目(不含外层逗号):  "名字":[\n<实例>L1]\n"""
    return '"' + name_esc + '":[' + nl + _equip_objects_text(l2, l3, l4, name_esc, lv, count, nl) + l1 + "]"


def shop_add_equips(text, key, adds):
    """把装备加入商店 SellEquips: 同名已有→向该名数组追加副本件数; 无此名→新增条目(值=数组)。

    adds: [(装备名, 件数)]; 返回 (新文本, 实际新增名→件数字典)。
    名字里前导数字视为等级(_Lv); SellEquips 缺失返回 (原文本, {})。
    """
    merged = {}
    for nm, cnt in adds:
        nm = (nm or "").strip()
        if not nm:
            continue
        merged[nm] = merged.get(nm, 0) + max(1, int(cnt))
    nt = text
    result = {}
    for nm, cnt in merged.items():
        o = _shop_sellequips_open(nt, key)
        if o is None:
            break
        nl = "\r\n" if nt.find("\r\n", 0, o) >= 0 else "\n"
        ls = nt.rfind("\n", 0, o) + 1
        l0 = re.match(r"[ \t]*", nt[ls:]).group(0)
        unit = "\t" if "\t" in l0 else (l0[:1] if l0 else "\t")
        l1 = l0 + unit
        l2 = l0 + unit * 2
        l3 = l0 + unit * 3
        l4 = l0 + unit * 4
        mnum = re.match(r"(\d+)", nm)
        lv = int(mnum.group(1)) if mnum else 1
        esc = _es3_escape_name(nm)
        # 当前 SellEquips 已有条目(数组): 名 -> (数组开, 数组闭)
        entries = []
        for kd, vs, _ve, _vt in _entry_values(nt, o):
            if nt[vs:vs + 1] == "[":
                entries.append((_es3_unescape_name(kd), vs, _matching_end(nt, vs)))
        idx = next((i for i, (n, _a, _b) in enumerate(entries) if n == nm), None)
        if idx is not None:
            # 同名已上架: 往其数组里追加副本(定位最后实例对象的闭花括号后插入)
            _n, va, va_close = entries[idx]
            last_obj = va
            for _k3, v3, _e3, _t3 in _entry_values(nt, va):
                if nt[v3:v3 + 1] == "{":
                    last_obj = _matching_end(nt, v3)
            ap = ""
            for i in range(cnt):
                ap += ",{" + nl if i == 0 else l2 + "},{" + nl
                ap += _equip_fields_text(l3, l4, esc, lv, nl)
            ap += l2 + "}" + nl
            nt = nt[:last_obj + 1] + ap + nt[last_obj + 1:]
            result[nm] = result.get(nm, 0) + cnt
        else:
            entry = _equip_new_entry_text(l1, l2, l3, l4, esc, lv, cnt, nl)
            if entries:
                # 插到最后一个条目的数组闭合 ] 后:  ],"新名":[...]
                j = entries[-1][2]
                nt = nt[:j + 1] + "," + entry + nt[j + 1:]
            else:
                # SellEquips 原本为空: 直接在 { 后内联新条目(第一键与 { 同行)
                nt = nt[:o + 1] + entry + nt[o + 1:]
            result[nm] = result.get(nm, 0) + cnt
    return nt, result


# ==================== 商店城市/门派分类(商店分类.json) ====================
# 由 _scaffold/build_shop_cities.py 从 内存所有道具.json 的 分类/shop(路径 dataset/shop/<分类>/.../<店名>) 生成
SHOP_CITY_ZH = {
    "anju": "安居城", "guanglin": "广临城", "heishi": "黑市",
    "linzhou": "临州城", "longju": "龙居城", "menpai": "门派",
    "other": "其他", "wutian": "吾天城", "xianghuocun": "乡火村",
    "xining": "息宁城", "yuehan": "岳汉城", "hexing": "禾兴城",
    "chapter5": "第五章秘境",
}


def get_shop_cities_path():
    """商店分类库路径(程序目录/商店分类.json)。"""
    return os.path.join(app_dir(), "商店分类.json")


def load_shop_cities(path=None):
    """读 商店分类.json → (店名→分类代码 dict, 分类顺序 list, 各分类计数 dict)。
    缺失/损坏返回 ({}, [], {})。"""
    path = path or get_shop_cities_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}, [], {}
    if not isinstance(data, dict):
        return {}, [], {}
    m = data.get("map")
    if not isinstance(m, dict):
        return {}, [], {}
    order = data.get("order")
    counts = data.get("counts")
    return m, list(order) if isinstance(order, list) else [], dict(counts) if isinstance(counts, dict) else {}


# ==================== 道具分类库(道具分类.json, v2.6.0) ====================
# 由 _scaffold/build_item_categories.py 从 内存所有道具.json 的
# dataset/<大分类>/<小分类>/…/<道具名> 生成, 供「新增道具」按大/小/细分类浏览+多选添加。
# 覆盖 7 个大分类(与 道具名.json 已并入来源一致)。
ITEM_CAT_ZH = {
    "equip": "装备", "item": "道具", "recipe": "配方", "bookcontent": "书籍",
    "kangfu": "武功秘籍", "skillcom": "技能合成", "shanhailu": "山海录",
}


def get_item_categories_path():
    """道具分类库文件路径: 程序目录/道具分类.json。"""
    return os.path.join(app_dir(), "道具分类.json")


_CAT_CACHE = {}


def load_item_categories(path=None):
    """读取 道具分类.json → dict{version, zh, cats:[{code, groups:{相对路径:[道具名…]}}]}。

    缺失/损坏返回 None(「新增道具」回退旧版 道具名.json 平铺列表)。
    groups 的 key = dataset/<code>/ 之后去掉末段道具名的中间路径, 段间用 / 连接(可多级);
    "" 表示道具名直接在该大分类下。
    """
    path = path or get_item_categories_path()
    if path in _CAT_CACHE:
        return _CAT_CACHE[path]
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("cats"), list):
        return None
    zh = data.get("zh")
    zh = dict(zh) if isinstance(zh, dict) else dict(ITEM_CAT_ZH)
    cats = []
    for cat in data["cats"]:
        if not isinstance(cat, dict) or not cat.get("code"):
            continue
        groups = cat.get("groups")
        if not isinstance(groups, dict):
            continue
        clean = {}
        for rel, names in groups.items():
            if not isinstance(rel, str) or not isinstance(names, list):
                continue
            ns = [str(x).strip() for x in names if str(x).strip()]
            if ns:
                clean[rel] = ns
        cats.append({"code": str(cat["code"]), "groups": clean})
    out = {"version": data.get("version", 1), "zh": zh, "cats": cats}
    _CAT_CACHE[path] = out
    return out


def _cat_node_total(node):
    """递归补算分类树节点 total = 直挂名 + 全部子级名(调用后写回 node["total"])。"""
    t = len(node.get("own") or ())
    for ch in (node.get("children") or {}).values():
        t += _cat_node_total(ch)
    node["total"] = t
    return t


def build_item_cat_nodes(data):
    """把 load_item_categories 的结果建成「分类树 + 全量道具名」。

    返回 (roots, all_names):
      roots     : 每个大分类一个根节点; 节点 = {"code","zh","own":[直挂名],
                  "children":{段:子节点}, "total":N}。
      all_names : 全部大分类道具名, 跨分类/跨路径去重(顺序=出现顺序), 供统计与无勾选兜底。
    """
    zh = data.get("zh") or {}
    roots = []
    for cat in data.get("cats") or []:
        code = cat.get("code")
        if not code:
            continue
        root = {"code": code, "zh": zh.get(code, code),
                "own": [], "children": {}, "total": 0}
        for rel, names in (cat.get("groups") or {}).items():
            node = root
            for seg in rel.split("/"):
                if not seg:
                    continue
                node = node["children"].setdefault(
                    seg, {"code": seg, "zh": zh.get(seg, seg),
                          "own": [], "children": {}, "total": 0})
            node["own"].extend(names)
        roots.append(root)

    all_names = []
    seen = set()

    def _collect(node):
        _cat_node_total(node)
        for n in node["own"]:
            if n not in seen:
                seen.add(n)
                all_names.append(n)
        for ch in node["children"].values():
            _collect(ch)

    for r in roots:
        _collect(r)
    return roots, all_names


def get_str_field(text, scope, field):
    """读 scope 容器内直接字符串字段 field 的内容(去引号); 非字符串/不存在返回 None。"""
    c = _locate_container(text, scope)
    if c is None:
        return None
    return _obj_direct_str(text, c, field)


def _obj_direct_str(text, obj_open, field):
    """读 obj_open(某对象开括号)的直接字符串字段 field 内容(去引号); 非字符串/不存在返回 None。"""
    for key_disp, vs, _ve, _vt in _entry_values(text, obj_open):
        if key_disp == field:
            raw = text[vs:].lstrip()
            if raw.startswith('"'):
                end = _string_end(text, vs)
                return text[vs + 1:end - 1]
            return None
    return None


def list_scalar_fields(text, scope):
    """列出 scope 容器内全部直接数字字段: [(键, 原值字符串)], 按出现顺序。"""
    c = _locate_container(text, scope)
    if c is None:
        return []
    out = []
    for key_disp, vs, _ve, _vt in _entry_values(text, c):
        tok = _num_token(text, vs)
        if tok:
            out.append((key_disp, tok[0]))
    return out


def friend_keys(text):
    """返回当前文本里队友(AddFriends 直接键)列表; 无则 []。"""
    c = _locate_container(text, SCOPE_FRIENDS)
    if c is None:
        return []
    out = []
    for key_disp, vs, _ve, _vt in _entry_values(text, c):
        if text[vs:vs + 1] == "{":
            out.append(key_disp)
    return out


# 队友所在分组显示名(未来新增容器可在这里补中文说明; 枚举本身不依赖此表)
FRIEND_GROUP_LABELS = {"AddFriends": "在队", "LeaveFriends": "离队"}


def friend_records(text):
    """按 _AbName 枚举当前文本里所有队友属性块(在队 AddFriends / 离队 LeaveFriends / 未来新容器)。

    返回 [(容器名, 队友英文键, 中文名或键)]; 找不到返回 []。
    """
    return [(g, k, n) for g, k, n, _o in friend_blocks(text)]


def friend_blocks(text):
    """同 friend_records 但额外带回每名队友对象在 text 里的开括号下标, 供免重复扫描建页。

    返回 [(容器名, 队友英文键, 中文名或键, 对象开括号下标)]。
    """
    out = []
    val = _locate_container(text, ["saveFriendData", "value"])
    if val is None:
        return []
    for group, gs, _ge, _gt in _entry_values(text, val):
        if text[gs:gs + 1] != "{":
            continue
        for key, vs, _ve, _vt in _entry_values(text, gs):
            if text[vs:vs + 1] != "{":
                continue
            has_ab = any(kd == "_AbName" for kd, _x, _y, _z in _entry_values(text, vs))
            if not has_ab:
                continue
            nm = _obj_direct_str(text, vs, "_Name")
            out.append((group, key, nm or key, vs))
    return out


def collect_page(text, container_open, wanted):
    """单遍收集某角色容器(container_open 开括号下标)页面数据:

    - scalars: [(键, 原值字符串)] —— 全部直接数字字段
    - dicts  : {字段名: [(键, 原值字符串), ...]} —— 仅 wanted 里且确为对象的编号/名字字典
    避免原来每个分组各做一次全容器扫描(大档从 ~30s 降到亚秒级)。
    """
    scalars = []
    dicts = {}
    for key_disp, vs, _ve, _vt in _entry_values(text, container_open):
        tok = _num_token(text, vs)
        if tok:
            scalars.append((key_disp, tok[0]))
        elif key_disp in wanted and text[vs:vs + 1] == "{":
            rows = []
            for kd2, vs2, _ve2, _vt2 in _entry_values(text, vs):
                t2 = _num_token(text, vs2)
                rows.append((kd2, t2[0] if t2 else _vt2.strip()))
            dicts[key_disp] = rows
    return scalars, dicts


# 主角页想要展示成“编号字典分组”的字段
PLAYER_DICT_FIELDS = ("KongFuTypeLv", "LifeExp", "SixProCurrent", "FriendLoveNum")
# 队友页想要展示成“编号字典分组”的字段
FRIEND_DICT_FIELDS = ("SixProCurrent", "_KongFuTypeLv")


def char_model(text):
    """把整份存档里所有角色页需要的数据一次性收集成轻量模型(纯计算, 可在后台线程执行)。

    返回 {
      'player': {scalars, dicts} | None,
      'friends': [ {group, key, name, scalars, dicts} ... ],
      'maps': [地名...]
    }
    """
    model = {"player": None, "friends": [], "maps": []}
    po = _locate_container(text, SCOPE_PLAYER)
    if po is not None:
        s, d = collect_page(text, po, PLAYER_DICT_FIELDS)
        model["player"] = {"scalars": s, "dicts": d, "open": po}
    model["maps"] = get_str_array(text, SCOPE_MAP, "_ActiveMap")
    for group, key, name, fop in friend_blocks(text):
        s, d = collect_page(text, fop, FRIEND_DICT_FIELDS)
        model["friends"].append({"group": group, "key": key, "name": name,
                                  "scalars": s, "dicts": d, "open": fop})
    return model


# ============================ GUI 层 ============================

class AddItemDialog(QDialog):
    """新增道具对话框: 左=分类树(可勾选), 右=当前勾选分类下的道具名列表(可多选/全选)。

    - v2.6.0 起数据源为 程序目录/道具分类.json(由 _scaffold/build_item_categories.py 从
      内存所有道具.json 的 dataset/<大分类>/<小分类>/… 生成), 覆盖 7 大分类:
      equip装备 / item道具 / recipe配方 / bookcontent书籍 / kangfu武功秘籍 /
      skillcom技能合成 / shanhailu山海录; 每个大分类下再按路径段多级细分(大→小→细)。
    - 左树: 勾选某分类 = 把该分类及其全部下级道具纳入右侧候选; 可同时勾选多个大/小/细分类。
      勾「大分类」自动包含其所有下级(勾选状态向下传播); 展开后反选某子分类可精确排除
      (父分类自动变「半选」= 仍保留其自身直挂道具 + 其余勾选子级)。
      **默认不勾选分类**——勾某个分类(或其中细分类), 右侧即只显示该分类下的道具(直观可见);
      想一次选全部道具点左下的「全勾选」。
    - 右列表: 对候选支持 中文/拼音全拼/拼音首字母/数字 过滤、Ctrl/Shift 多选、全选;
      已在当前列表中的名字灰显不可选; 双击或回车=加单项; 无匹配输入即自定义名。
    - 找不到 道具分类.json 时自动回退旧版 道具名.json 平铺列表(无左树, 行为同 v2.5.x)。
    """

    def __init__(self, parent=None, existing=None, default_name="", default_count=9999):
        super().__init__(parent)
        self._existing = set(existing or ())
        self._pmap = load_pinyin_map()
        self._chosen = None          # 双击/回车确定的单项; None 时按“多选/自定义”取
        # 候选数据: 优先 道具分类.json(分类浏览); 缺失回退 道具名.json 平铺
        self._cat_data = load_item_categories()
        self._use_cat = bool(self._cat_data and self._cat_data.get("cats"))
        self._cat_roots, self._scope_names = [], None
        self._scope_dirty = False
        if self._use_cat:
            self._cat_roots, self._all_names = build_item_cat_nodes(self._cat_data)
        else:
            self._all_names = list(dict.fromkeys(load_item_names()))
        self._cat_building = False

        self.setWindowTitle("新增道具")
        self.setMinimumSize(880, 560)
        root = QVBoxLayout(self)

        body = QHBoxLayout()
        if self._use_cat:
            body.addWidget(self._build_category_pane())

        # 右侧: 搜索/输入 + 候选列表 + 工具行
        right = QVBoxLayout()
        top = QHBoxLayout()
        top.addWidget(QLabel("搜索/输入:"))
        self.search = QLineEdit(default_name)
        self.search.setPlaceholderText(
            "中文 / 拼音(tongqian) / 首字母(tq) / 数字… 实时过滤; 无匹配时输入即自定义名")
        self.search.textChanged.connect(self._refresh_list)
        self.search.returnPressed.connect(self._on_search_enter)
        top.addWidget(self.search, 1)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["自动匹配", "仅中文", "仅拼音/首字母"])
        self.mode_combo.currentIndexChanged.connect(self._refresh_list)
        top.addWidget(self.mode_combo)
        right.addLayout(top)

        self.item_list = QListWidget()
        self.item_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.item_list.itemSelectionChanged.connect(self._update_stat)
        self.item_list.itemDoubleClicked.connect(self._on_double)
        self.item_list.setToolTip("可按住 Ctrl/Shift 多选; 双击某项 = 直接添加该项")
        right.addWidget(self.item_list, 1)

        # 工具行: 仅显示缺少 / 全选 / 清空选择 + 统计
        mid = QHBoxLayout()
        self.only_missing_check = QCheckBox("仅显示缺少(未在个人背包)")
        self.only_missing_check.setToolTip(
            "勾选后只列出当前勾选分类里你个人背包还没有的道具(无分类时=道具名.json 全部), 便于全选一次补齐")
        self.only_missing_check.toggled.connect(self._refresh_list)
        btn_all = QPushButton("全选")
        btn_all.clicked.connect(self._select_all)
        btn_none = QPushButton("清空选择")
        btn_none.clicked.connect(self._select_none)
        self.stat_label = QLabel("")
        mid.addWidget(self.only_missing_check)
        mid.addWidget(btn_all)
        mid.addWidget(btn_none)
        mid.addStretch(1)
        mid.addWidget(self.stat_label)
        right.addLayout(mid)
        body.addLayout(right, 1)
        root.addLayout(body, 1)

        # 数量
        cnt = QHBoxLayout()
        cnt.addWidget(QLabel("数量(本次新增道具统一):"))
        self.count_spin = QSpinBox()
        self.count_spin.setRange(0, MAX_ITEM_COUNT)
        self.count_spin.setValue(default_count)
        cnt.addWidget(self.count_spin)
        cnt.addStretch(1)
        root.addLayout(cnt)

        # 确定/取消
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.btn_ok = btns.button(QDialogButtonBox.StandardButton.Ok)
        self.btn_ok.setText("添加所选")
        self.btn_ok.setAutoDefault(False)
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

        # 默认不勾选分类(避免“一开就全列表、点了分类却没变化”的困惑)。
        # 勾某分类/子分类 → 右侧即只显示该分类的道具; 想一次全选点左下「全勾选」。
        self._refresh_list()

    # ---------------- 分类树(v2.6.0) ----------------
    def _build_category_pane(self):
        """左栏: 大分类→小分类→细分类 勾选树。"""
        pane = QWidget()
        lay = QVBoxLayout(pane)
        lay.setContentsMargins(0, 0, 0, 0)
        lab = QLabel("分类(勾选=含其全部下级; 可多选)")
        lab.setWordWrap(True)
        lay.addWidget(lab)
        self.cat_tree = QTreeWidget()
        self.cat_tree.setHeaderHidden(True)
        self.cat_tree.setColumnCount(1)
        self.cat_tree.setMinimumWidth(232)
        self.cat_tree.setToolTip(
            "按 内存所有道具.json 的 dataset 路径分级: 大分类 → 小分类 → 细分类。\n"
            "勾选某分类 = 把该分类及全部下级道具纳入右侧候选(可多选大/小/细分类)。\n"
            "勾「大分类」会自动带上其所有下级; 想精确排除某个子分类, 展开后取消它的勾选即可\n"
            "(父分类会变「半选」, 仍保留自身直挂道具与其余勾选子级)。")
        self._cat_building = True
        self._cat_root_items = []
        for rn in self._cat_roots:
            it = self._cat_item(rn)
            self.cat_tree.addTopLevelItem(it)
            self._cat_root_items.append(it)
        self.cat_tree.itemChanged.connect(self._on_cat_changed)
        self._cat_building = False
        self.cat_tree.expandToDepth(0)
        lay.addWidget(self.cat_tree, 1)
        btns = QHBoxLayout()
        b_exp = QPushButton("展开全部")
        b_exp.clicked.connect(self.cat_tree.expandAll)
        b_col = QPushButton("折叠")
        b_col.clicked.connect(self.cat_tree.collapseAll)
        b_all = QPushButton("全勾选")
        b_all.clicked.connect(self._cat_set_all)
        b_no = QPushButton("取消勾选")
        b_no.clicked.connect(self._cat_clear)
        for b in (b_exp, b_col, b_all, b_no):
            btns.addWidget(b)
        lay.addLayout(btns)
        return pane

    def _cat_item(self, node, parent=None):
        """为一个分类节点建 QTreeWidgetItem(带勾选框), 并把 node 挂到 item 上; 递归建其子级。"""
        it = QTreeWidgetItem(parent)
        it._node = node
        it.setText(0, self._cat_label(node))
        it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsUserCheckable)
        it.setCheckState(0, Qt.CheckState.Unchecked)
        for code in sorted(node["children"]):
            self._cat_item(node["children"][code], it)
        return it

    @staticmethod
    def _cat_label(node):
        n = node
        if n.get("zh") and n["zh"] != n["code"]:
            return "%s · %s (%d)" % (n["code"], n["zh"], n["total"])
        return "%s (%d)" % (n["code"], n["total"])

    def _set_subtree_state(self, item, state):
        """把 item 及其全部后代勾选状态统一设为 state(期间触发的 itemChanged 由 _cat_building 屏蔽)。"""
        item.setCheckState(0, state)
        for i in range(item.childCount()):
            self._set_subtree_state(item.child(i), state)

    def _refresh_cat_ancestors(self, item):
        """由改动节点向上刷新父级状态: 子级全勾=Checked / 全不勾=Unchecked / 混合=半选。"""
        p = item.parent()
        while p is not None:
            vals = set()
            for i in range(p.childCount()):
                vals.add(p.child(i).checkState(0))
            if vals == {Qt.CheckState.Checked}:
                ns = Qt.CheckState.Checked
            elif vals == {Qt.CheckState.Unchecked}:
                ns = Qt.CheckState.Unchecked
            else:
                ns = Qt.CheckState.PartiallyChecked
            if p.checkState(0) != ns:
                p.setCheckState(0, ns)
            p = p.parent()

    def _on_cat_changed(self, item, col):
        """勾选变化: 向下传播状态(勾=全选其下级, 取消=去掉其下级), 向上刷新父级半选, 再刷列表。"""
        if col != 0 or self._cat_building or item is None:
            return
        state = item.checkState(0)
        self._cat_building = True
        self._set_subtree_state(item, state)
        self._refresh_cat_ancestors(item)
        self._cat_building = False
        self._scope_dirty = True
        self._refresh_list()

    def _cat_set_all(self):
        """全部大分类勾选(右侧 = 全部道具)。"""
        self._cat_building = True
        for it in self._cat_root_items:
            self._set_subtree_state(it, Qt.CheckState.Checked)
        self._cat_building = False
        self._scope_dirty = True
        self._refresh_list()

    def _cat_clear(self):
        """取消全部勾选(无分类过滤时右侧回全部道具)。"""
        self._cat_building = True
        for it in self._cat_root_items:
            self._set_subtree_state(it, Qt.CheckState.Unchecked)
        self._cat_building = False
        self._scope_dirty = True
        self._refresh_list()

    def _selected_names(self):
        """当前勾选分类覆盖的道具名(跨分类去重, 保持顺序); 全不勾返回 []。"""
        out = []
        seen = set()

        def _add(names):
            for n in names:
                if n not in seen:
                    seen.add(n)
                    out.append(n)

        def _subtree(node):
            _add(node["own"])
            for ch in node["children"].values():
                _subtree(ch)

        def _walk(item):
            st = item.checkState(0)
            node = item._node
            if st == Qt.CheckState.Checked:
                _subtree(node)
            elif st == Qt.CheckState.Unchecked:
                return
            else:                       # 半选: 含自身直挂道具 + 各子级按自己状态
                _add(node["own"])
                for i in range(item.childCount()):
                    _walk(item.child(i))

        for it in self._cat_root_items:
            _walk(it)
        return out

    def _any_checked(self):
        """是否有任一分类被勾选(Checked 或 半选 Partial)。"""
        for it in self._cat_root_items:
            st = it.checkState(0)
            if st != Qt.CheckState.Unchecked:
                return True
        return False

    def _current_scope(self):
        """右侧候选名列表: 分类模式=勾选分类覆盖的名; 全不勾且无搜索=空(提示先勾分类),
        全不勾但有搜索词=全库搜索给建议(便于快速定位/自定义); 非分类模式=全量。"""
        if not self._use_cat:
            return self._all_names
        if not self._any_checked():
            return self._all_names if self.search.text().strip() else []
        if self._scope_dirty:
            self._scope_names = self._selected_names()
            self._scope_dirty = False
        return self._scope_names if self._scope_names is not None else []

    # ---------------- 内部 ----------------
    def _missing_names(self):
        """全量道具库里个人背包(当前列表)还没有的名字, 即“缺少的道具”。"""
        return [n for n in self._all_names if n not in self._existing]

    def _filtered(self):
        names = filter_item_names(self._current_scope(), self.search.text(),
                                  self._pmap, mode=self.mode_combo.currentIndex())
        if self.only_missing_check.isChecked():   # 勾选后只列缺少的
            names = [n for n in names if n not in self._existing]
        return names

    def _refresh_list(self):
        self.item_list.clear()
        for nm in self._filtered():
            it = QListWidgetItem(nm)
            if nm in self._existing:      # 已在当前列表中: 灰显不可选
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                it.setToolTip("已在当前列表中(无需重复添加)")
            self.item_list.addItem(it)
        self._update_stat()

    def _update_stat(self):
        if self._use_cat and not self._any_checked() and not self.search.text().strip():
            # 未勾选分类: 右侧列表为空, 给一句引导, 避免“点了没反应”的困惑
            self.stat_label.setText(
                "未勾选分类: 请在左侧点分类前的方框勾选(可多选大/小/细分类);\n"
                "勾大分类=含其全部下级; 点「全勾选」= 全部道具")
            self.btn_ok.setText("添加所选")
            return
        total = len(self._all_names)
        miss = len(self._missing_names())
        sel = len(self.item_list.selectedItems())
        if self._use_cat:
            shown = len(self._current_scope())
            self.stat_label.setText("道具名库 %d · 当前勾选分类含 %d · 已选 %d"
                                    % (total, shown, sel))
        else:
            self.stat_label.setText("道具名库 %d · 个人已有 %d · 缺少 %d · 已选 %d"
                                    % (total, total - miss, miss, sel))
        self.btn_ok.setText("添加所选(%d)" % sel if sel else "添加所选")

    def _select_all(self):
        self.item_list.clearSelection()
        for r in range(self.item_list.count()):
            it = self.item_list.item(r)
            if it.flags() & Qt.ItemFlag.ItemIsEnabled:
                it.setSelected(True)

    def _select_none(self):
        self.item_list.clearSelection()

    def _on_double(self, item):
        if item.flags() & Qt.ItemFlag.ItemIsEnabled:
            self._chosen = [item.text()]
            self.accept()

    def _on_search_enter(self):
        # 有可选项时添加第一项; 无匹配但输入了文字时当作自定义名
        for r in range(self.item_list.count()):
            it = self.item_list.item(r)
            if it.flags() & Qt.ItemFlag.ItemIsEnabled:
                self._chosen = [it.text()]
                self.accept()
                return
        if self.search.text().strip():
            self._chosen = [self.search.text().strip()]
            self.accept()

    def chosen_names(self):
        """本次要添加的名字列表: 优先双击/回车确定的单项, 否则取多选; 无选择则退回搜索框自定义名。"""
        if self._chosen is not None:
            return list(self._chosen)
        sel = [it.text() for it in self.item_list.selectedItems()]
        names = sel if sel else [self.search.text().strip()]
        return list(dict.fromkeys(n for n in names if n))


class MapJumpDialog(QDialog):
    """从 地图跳转点.json(由 MapJumpTable.bytes 生成)全选/多选添加地图标注点。

    搜索支持 中文/拼音全拼/拼音首字母(复用 filter_item_names); 列表可多选/全选;
    已在 _ActiveMap 的名字灰显不可选; 默认勾选「仅显示未标注」便于一次补齐所有跳转点。
    """

    def __init__(self, parent=None, all_names=(), existing=()):
        super().__init__(parent)
        self._all = list(all_names or ())
        self._existing = set(existing or ())
        self._pmap = load_pinyin_map()
        self._chosen = None
        self.setWindowTitle("批量添加地图标注点")
        self.setMinimumSize(520, 480)
        root = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("搜索:"))
        self.search = QLineEdit()
        self.search.setPlaceholderText(
            "中文 / 拼音(tongqian) / 首字母(tq)… 实时过滤 地图跳转点.json 里的跳转点")
        self.search.textChanged.connect(self._refresh_list)
        top.addWidget(self.search, 1)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["自动匹配", "仅中文", "仅拼音/首字母"])
        self.mode_combo.currentIndexChanged.connect(self._refresh_list)
        top.addWidget(self.mode_combo)
        root.addLayout(top)

        self.item_list = QListWidget()
        self.item_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.item_list.itemSelectionChanged.connect(self._update_stat)
        self.item_list.itemDoubleClicked.connect(self._on_double)
        self.item_list.setToolTip("可按住 Ctrl/Shift 多选; 双击某项 = 直接添加该项")
        root.addWidget(self.item_list, 1)

        mid = QHBoxLayout()
        self.only_missing_check = QCheckBox("仅显示未标注(不在 _ActiveMap)")
        self.only_missing_check.setChecked(True)
        self.only_missing_check.setToolTip(
            "勾选后只列出当前还没添加进 _ActiveMap 的跳转点, 配合「全选」即可一次补齐全部")
        self.only_missing_check.toggled.connect(self._refresh_list)
        btn_all = QPushButton("全选")
        btn_all.clicked.connect(self._select_all)
        btn_none = QPushButton("清空选择")
        btn_none.clicked.connect(self._select_none)
        self.stat_label = QLabel("")
        mid.addWidget(self.only_missing_check)
        mid.addWidget(btn_all)
        mid.addWidget(btn_none)
        mid.addStretch(1)
        mid.addWidget(self.stat_label)
        root.addLayout(mid)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                | QDialogButtonBox.StandardButton.Cancel)
        self.btn_ok = btns.button(QDialogButtonBox.StandardButton.Ok)
        self.btn_ok.setText("添加所选")
        self.btn_ok.setAutoDefault(False)
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

        self._refresh_list()

    # ---------------- 内部 ----------------
    def _filtered(self):
        names = filter_item_names(self._all, self.search.text(),
                                  self._pmap, mode=self.mode_combo.currentIndex())
        if self.only_missing_check.isChecked():
            names = [n for n in names if n not in self._existing]
        return names

    def _refresh_list(self):
        self.item_list.clear()
        for nm in self._filtered():
            it = QListWidgetItem(nm)
            if nm in self._existing:
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                it.setToolTip("已在 _ActiveMap 中(无需重复添加)")
            self.item_list.addItem(it)
        self._update_stat()

    def _update_stat(self):
        total = len(self._all)
        has = len(set(self._all) & self._existing)   # 库中已在 _ActiveMap 的数量
        sel = len(self.item_list.selectedItems())
        self.stat_label.setText("跳转点库 %d · 已标注 %d · 缺少 %d · 已选 %d"
                                % (total, has, total - has, sel))
        self.btn_ok.setText("添加所选(%d)" % sel if sel else "添加所选")

    def _select_all(self):
        self.item_list.clearSelection()
        for r in range(self.item_list.count()):
            it = self.item_list.item(r)
            if it.flags() & Qt.ItemFlag.ItemIsEnabled:
                it.setSelected(True)

    def _select_none(self):
        self.item_list.clearSelection()

    def _on_double(self, item):
        if item.flags() & Qt.ItemFlag.ItemIsEnabled:
            self._chosen = [item.text()]
            self.accept()

    def chosen_names(self):
        """本次要添加的名字: 双击确定的单项优先, 否则取多选; 无选择则退回搜索框文字。"""
        if self._chosen is not None:
            return list(self._chosen)
        sel = [it.text() for it in self.item_list.selectedItems()]
        names = sel if sel else [self.search.text().strip()]
        return list(dict.fromkeys(n for n in names if n))


class PasteDialog(QDialog):
    """粘贴存档内容对话框: 大文本框, 解析后确认。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("粘贴存档内容")
        self.resize(740, 540)
        lay = QVBoxLayout(self)
        tip = QLabel("请把整个 *.es3 文件的内容(用记事本打开全选复制)粘贴到下方:")
        tip.setWordWrap(True)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("在此粘贴 es3 存档全文...")
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("解析")
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(tip)
        lay.addWidget(self.editor, 1)
        lay.addWidget(btns)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._items = []       # list[Es3Item]
        self._indent = None    # 原 ItemHad 段缩进信息
        self._text = None      # 当前完整文本(BOM 已剥离)
        self._bom = b""
        self._file_path = None
        self._loading = False  # 程序化填充表格时置 True, 防止误触发 itemChanged
        self._suppress_change = False  # 回滚单元格文本时防止 itemChanged 死循环
        self._lib_new = []   # 最近一次加载收录的新道具名
        self._lib_total = 0  # 道具名库当前总数
        self._dirty = False  # 自上次读取/保存后是否有未保存修改
        self._history = []   # 最近打开历史(最新在前, 来自 历史记录.json)
        self._sort_col = -1    # 最近排序列(1=名称/2=数量), -1=尚未排序
        self._sort_asc = True  # 最近一次方向: True=升序(小→大)
        self._filter_map = None    # 道具搜索: 表格当前可见行→self._items 索引; None=不过滤
        self._search_timer = None  # 搜索防抖定时器(在 _build_ui 里创建)
        self._busy = False     # 大档后台打开进行中标志(防重入/禁用工具栏)
        self._char_spin_map = {}  # (scope元组, 字段键) -> 数值框, 供「一键全部默认」原地刷新不整档重建
        self._char_open_cache = {}  # scope元组 -> (text对象, 容器开括号); text 替换后自动失效(避免每次整档定位)
        self._shop_cache = {}   # 商店键 -> (abName显示名, SellItems容器开括号); 读档后 _refresh_shop_tab 填充
        self._shop_key = None   # 当前选中商店键
        self._shop_loading = False   # 程序化填充 折扣/刷新日 数字框时置 True, 防误触发写回
        # 设置: 批量改为的目标值(持久保存, 重开仍保留)
        self._settings = load_app_settings()
        try:
            self._batch_value = int(self._settings.get("batch_value", 9999))
        except (TypeError, ValueError):
            self._batch_value = 9999
        self._batch_value = max(0, min(self._batch_value, MAX_ITEM_COUNT))
        self._settings_save_timer = QTimer(self)   # 500ms 防抖自动保存
        self._settings_save_timer.setSingleShot(True)
        self._settings_save_timer.setInterval(500)
        self._settings_save_timer.timeout.connect(self._save_settings_now)
        self.setWindowTitle("%s v%s" % (APP_NAME, __version__))
        self.setWindowIcon(app_icon())
        self.resize(800, 600)
        self._build_ui()
        self._history = load_history()
        self._update_history_ui()

    # ---------------- 脏标记(未保存修改) ----------------
    def _mark_dirty(self):
        """标记存在未保存修改, 并在窗口标题加 *。"""
        if not self._dirty:
            self._dirty = True
            self._refresh_title()

    def _mark_clean(self):
        """清除未保存修改标记(读取/保存成功后)。"""
        if self._dirty:
            self._dirty = False
            self._refresh_title()

    def _refresh_title(self):
        mark = " *" if self._dirty else ""
        self.setWindowTitle("%s v%s%s" % (APP_NAME, __version__, mark))

    # ---------------- UI 构建 ----------------
    def _build_ui(self):
        toolbar = QToolBar("主工具栏", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        self.toolbar = toolbar

        def _add_act(text, slot, key=None):
            """给工具栏加一个文字按钮, 返回 QAction。"""
            a = QAction(text, self)
            if key is not None:
                a.setShortcut(key)
            a.triggered.connect(slot)
            toolbar.addAction(a)
            return a

        _add_act("打开", self._on_open, QKeySequence.StandardKey.Open)
        toolbar.addSeparator()
        # 打开上次的文件
        self.act_open_last = _add_act("打开上次", self._on_open_last)
        self.act_open_last.setToolTip("打开上一次打开过的存档文件")
        # 最近打开历史下拉
        self.recent_btn = QToolButton()
        self.recent_btn.setText("最近 ▾")
        self.recent_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.recent_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.recent_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.recent_btn.setToolTip("最近打开过的存档文件, 点开即可直接打开")
        self.recent_menu = QMenu(self)
        self.recent_menu.aboutToShow.connect(self._rebuild_recent_menu)
        self.recent_btn.setMenu(self.recent_menu)
        toolbar.addWidget(self.recent_btn)
        toolbar.addSeparator()
        # 游戏已存档后再次读取当前文件
        act_reload = _add_act("重新读取", self._on_reload)
        act_reload.setToolTip("游戏已存档后, 再次读取当前文件内容(有未保存修改会先询问)")
        toolbar.addSeparator()
        _add_act("粘贴", self._on_paste)
        _add_act("保存", self._on_save, QKeySequence.StandardKey.Save)
        _add_act("另存为", self._on_save_as)
        _add_act("复制结果", self._on_copy)
        toolbar.addSeparator()
        _add_act("说明", self._on_help)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 多角色分页: 页0=道具(ItemHad); 其余(主角/每个队友)由 _refresh_char_tabs 按读档内容动态添加
        self.tabs = QTabWidget()
        root.addWidget(self.tabs)
        self._building_char_page = False   # 填充角色页控件时置 True, 防误触发写回

        tab_items = QWidget()
        tlay = QVBoxLayout(tab_items)

        self.src_label = QLabel("源: 未打开(可点「粘贴」直接粘贴存档内容)")
        self.src_label.setWordWrap(True)
        tlay.addWidget(self.src_label)

        # 道具搜索过滤(同「新增道具」: 中文/拼音/首字母/数字); 过滤只影响查看/选中行,
        # 双击编辑、删除选中 作用于当前显示行; 清空搜索框即恢复全部。
        row_search = QHBoxLayout()
        row_search.addWidget(QLabel("搜索:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(
            "中文 / 拼音(tongqian) / 首字母(tq) / 数字… 实时过滤当前道具")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setToolTip(
            "按名称过滤当前表格: 支持 中文 / 拼音全拼 / 拼音首字母 / 数字(如 tq/tongqian 找 铜钱)。\n"
            "实时只显示匹配的道具(# 列显示其在完整列表里的原序号); 双击编辑、删除选中 只作用于\n"
            "当前显示行。\n清空搜索框(点 ✕)即恢复显示全部道具。")
        self.search_edit.textChanged.connect(self._on_search_changed)
        row_search.addWidget(self.search_edit, 1)
        self.search_mode_combo = QComboBox()
        self.search_mode_combo.addItems(["自动匹配", "仅中文", "仅拼音/首字母"])
        self.search_mode_combo.setToolTip("搜索匹配方式: 自动 / 仅中文子串 / 仅拼音全拼+首字母")
        self.search_mode_combo.currentIndexChanged.connect(self._on_search_changed)
        row_search.addWidget(self.search_mode_combo)
        tlay.addLayout(row_search)
        self._search_timer = QTimer(self)   # 搜索防抖(大档避免每敲一键就整表重建)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(150)
        self._search_timer.timeout.connect(self._reload_table)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["#", "道具名称", "数量"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 46)
        self.table.setColumnWidth(2, 110)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.itemChanged.connect(self._on_item_changed)
        # 点击表头排序(道具名称/数量): 排序直接作用于 self._items, 表格行序恒等于列表序, 不影响编辑
        self.table.setSortingEnabled(False)
        _hdr = self.table.horizontalHeader()
        _hdr.setSortIndicatorShown(False)
        _hdr.setToolTip("点击列头=升序; 再次点击同一列=反向(降序); 右键表头可直接选 升/降序")
        _hdr.sectionClicked.connect(self._on_header_clicked)
        _hdr.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        _hdr.customContextMenuRequested.connect(self._on_header_menu)
        tlay.addWidget(self.table, 1)

        row1 = QHBoxLayout()
        self.btn_9999 = QPushButton("全部改为 %d" % self._batch_value)
        self.btn_9999.clicked.connect(self._on_set_all_9999)
        self.btn_9999.setToolTip("按记住的目标值一键批量改(可在右侧数字框改成任意数值, 会自动保存)")
        self.skip_copper_check = QCheckBox("跳过「铜钱」")
        self.skip_copper_check.setChecked(True)
        self.all_spin = QSpinBox()
        self.all_spin.setRange(0, MAX_ITEM_COUNT)
        self.all_spin.setValue(self._batch_value)
        self.all_spin.setMinimumWidth(110)
        self.all_spin.setToolTip("批量改的目标值; 修改后自动记住, 左侧按钮与重开后的程序都会用这个值")
        self.all_spin.valueChanged.connect(self._on_batch_value_changed)
        self.btn_all = QPushButton("全部改为")
        self.btn_all.clicked.connect(self._on_set_all_value)
        self.btn_time0 = QPushButton("一键 _GetTimeNew→0")
        self.btn_time0.clicked.connect(self._on_set_get_time_zero)
        row1.addWidget(self.btn_9999)
        row1.addWidget(self.skip_copper_check)
        row1.addSpacing(14)
        row1.addWidget(QLabel("全部改为:"))
        row1.addWidget(self.all_spin)
        row1.addWidget(self.btn_all)
        row1.addSpacing(14)
        row1.addWidget(self.btn_time0)
        row1.addStretch(1)
        tlay.addLayout(row1)

        row2 = QHBoxLayout()
        self.btn_add = QPushButton("＋ 新增道具")
        self.btn_add.clicked.connect(self._on_add)
        self.btn_add_all = QPushButton("一键添加全部道具")
        self.btn_add_all.clicked.connect(self._on_add_all_items)
        self.btn_organize = QPushButton("一键整理道具名")
        self.btn_organize.setToolTip(
            "一键整理道具列表: 把当前存档(表格)里已有的道具名与 道具名.json 比对, 缺失的自动补入\n"
            "(读档时也会自动收录; 手动新增/改名后点它即可把最新道具名同步进 json, 不重名)")
        self.btn_organize.clicked.connect(self._on_organize_names)
        self.btn_del = QPushButton("－ 删除选中")
        self.btn_del.clicked.connect(self._on_delete)
        self.count_label = QLabel("道具总数: 0")
        row2.addWidget(self.btn_add)
        row2.addWidget(self.btn_add_all)
        row2.addWidget(self.btn_organize)
        row2.addWidget(self.btn_del)
        row2.addStretch(1)
        row2.addWidget(self.count_label)
        tlay.addLayout(row2)
        self.tabs.addTab(tab_items, "道具")
        # 商店NPC页签(固定 index=1): 读档后由 _refresh_shop_tab 填充 NPC/卖品
        self.tabs.addTab(self._build_shop_tab(), "商店NPC")

        self.setStatusBar(QStatusBar(self))

        act_del = QAction(self)
        act_del.setShortcut(QKeySequence(Qt.Key.Key_Delete))
        act_del.triggered.connect(self._on_delete)
        self.addAction(act_del)

    # ---------------- 表格 ----------------
    # ---------------- 表格排序(正/反向, 不影响修改) ----------------
    def _sort_items(self, col, reverse):
        """按列(1=名称/2=数量)与方向 reverse 排序 self._items 并刷新表格。

        reverse=True 表示降序(大到小)。排序直接作用于数据列表后整表重建,
        表格行序恒等于列表序, 因此排序后双击改名/改数量、删除选中仍按原行号映射到道具。
        同时把 (col, 方向) 记入 self._sort_col/_sort_asc, 供表头点击往返用。
        """
        if col not in (1, 2):
            return
        self._sort_col = col
        self._sort_asc = not reverse
        hdr = self.table.horizontalHeader()
        hdr.setSortIndicatorShown(True)
        hdr.setSortIndicator(col, Qt.SortOrder.DescendingOrder if reverse
                             else Qt.SortOrder.AscendingOrder)
        if self._items:
            if col == 1:
                self._items.sort(key=lambda it: it.name, reverse=reverse)
            else:
                self._items.sort(key=lambda it: it.count, reverse=reverse)
            self._reload_table()
        self.statusBar().showMessage(
            "已按%s排序 %s" % ("名称" if col == 1 else "数量",
                             "↓降序" if reverse else "↑升序"), 2000)

    def _on_header_clicked(self, col):
        """点击表头: 第一次点击或换列=升序(小→大); 同列再点一次=反向(升<->降)。"""
        if col not in (1, 2):
            return
        if self._sort_col == col:
            reverse = self._sort_asc   # 上次升序 → 本次降序; 上次降序 → 本次升序
        else:
            reverse = False            # 新列默认从升序(小→大)开始
        self._sort_items(col, reverse)

    def _on_header_menu(self, pos):
        """右键表头: 显式选择 名称/数量 × 升序/降序。"""
        hdr = self.table.horizontalHeader()
        menu = QMenu(self)
        a_n1 = menu.addAction("道具名称 · 升序 ↑")
        a_n2 = menu.addAction("道具名称 · 降序 ↓")
        menu.addSeparator()
        a_c1 = menu.addAction("数量 · 升序 ↑")
        a_c2 = menu.addAction("数量 · 降序 ↓")
        act = menu.exec(hdr.mapToGlobal(pos))
        if act is a_n1:
            self._sort_items(1, False)
        elif act is a_n2:
            self._sort_items(1, True)
        elif act is a_c1:
            self._sort_items(2, False)
        elif act is a_c2:
            self._sort_items(2, True)

    # ---------------- 道具搜索过滤(中文/拼音/首字母/数字, 同「新增道具」) ----------------
    def _on_search_changed(self):
        """搜索框/匹配方式变化 → 防抖后刷新表格(避免大档每键整表重建卡顿)。"""
        if self._search_timer is not None:
            self._search_timer.start()

    def _clear_search(self):
        """清空搜索框并立即回到全量视图(新增道具后调用, 保证新行可见)。"""
        if self._search_timer is not None:
            self._search_timer.stop()
        if self.search_edit.text():
            self.search_edit.blockSignals(True)
            self.search_edit.clear()
            self.search_edit.blockSignals(False)
        self._reload_table()

    def _build_filter_map(self):
        """按搜索文字计算可见行映射 self._filter_map(None=无过滤); 返回表格应显示的行数。"""
        q = self.search_edit.text().strip()
        if not q:
            self._filter_map = None
            return len(self._items)
        names = [it.name for it in self._items]
        keep = set(filter_item_names(names, q, mode=self.search_mode_combo.currentIndex()))
        self._filter_map = [i for i, n in enumerate(names) if n in keep]
        return len(self._filter_map)

    def _row_to_item_index(self, row):
        """表格行号 → self._items 索引(考虑当前搜索过滤); 越界返回 -1。"""
        if self._filter_map is not None:
            if 0 <= row < len(self._filter_map):
                return self._filter_map[row]
            return -1
        return row

    def _fill_item_row(self, r, real, it):
        """填充表格第 r 行(数据索引 real, 内容 it); # 列显示完整列表里的原序号 real+1。"""
        i0 = QTableWidgetItem(str(real + 1))
        i0.setFlags(i0.flags() & ~Qt.ItemFlag.ItemIsEditable)
        i0.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        i1 = QTableWidgetItem(it.name)
        i2 = QTableWidgetItem(str(it.count))
        i2.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.table.setItem(r, 0, i0)
        self.table.setItem(r, 1, i1)
        self.table.setItem(r, 2, i2)

    def _reload_table(self):
        self._loading = True
        t = self.table
        upd = t.updatesEnabled()
        t.setUpdatesEnabled(False)   # 重建期间暂停重绘/信号, 上千行时明显更快(防逐行闪烁)
        t.blockSignals(True)
        try:
            shown = self._build_filter_map()
            t.setRowCount(shown)
            if self._filter_map is None:
                for r, it in enumerate(self._items):
                    self._fill_item_row(r, r, it)
            else:
                fm = self._filter_map
                items = self._items
                for r, real in enumerate(fm):
                    self._fill_item_row(r, real, items[real])
        finally:
            t.blockSignals(False)
            t.setUpdatesEnabled(upd)
            self._loading = False
        self._set_count_label()

    def _set_count_label(self):
        """按当前 items/过滤刷新计数标签(不重建表格)。"""
        if self._filter_map is not None:
            self.count_label.setText("道具总数: %d · 显示: %d" % (len(self._items), len(self._filter_map)))
        else:
            self.count_label.setText("道具总数: %d" % len(self._items))

    def _sync_visible_counts(self):
        """只刷新各可见行「数量」列文本(批量改后原地更新, 避免几千行整表重建卡顿)。"""
        self._loading = True
        t = self.table
        t.blockSignals(True)
        try:
            if self._filter_map is None:
                for r, it in enumerate(self._items):
                    self._set_cell_count(t, r, it)
            else:
                items = self._items
                for r, real in enumerate(self._filter_map):
                    self._set_cell_count(t, r, items[real])
        finally:
            t.blockSignals(False)
            self._loading = False

    @staticmethod
    def _set_cell_count(t, r, it):
        c = t.item(r, 2)
        if c is None:
            c = QTableWidgetItem(str(it.count))
            c.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            t.setItem(r, 2, c)
        else:
            c.setText(str(it.count))

    # ---------------- 多角色属性分页(主角/每个队友) ----------------
    # 数据驱动: char_model/collect_page 先一次性把各页需要的数据收集好(纯计算, 可放后台线程),
    # _apply_char_model 只负责建控件, 避免每个分组反复全量扫描大文本(打开大档不再卡十几秒)。
    # ---------------- 商店NPC(卖的道具 SellItems, 容器 saveUtilData.value._ShopData) ----------------
    def _build_shop_tab(self):
        """构建「商店NPC」页签(固定 index=1); 数据由 _refresh_shop_tab 按读档填充。"""
        page = QWidget()
        lay = QVBoxLayout(page)
        tip = QLabel("NPC/商店卖的道具: 左侧选 NPC/商店(abName, 支持中文/拼音/首字搜索), "
                     "右侧可改该 NPC 的 折扣 Discount(1=无折扣/0.5=五折, 范围 0~1, 默认一键 0.1) 与 "
                     "刷新日 RefreshDay(默认一键 1), 并可查看/添加其 SellItems 卖品(默认数量 999, 与已有同名自动跳过)。")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#888;")
        lay.addWidget(tip)
        h = QHBoxLayout()
        lv = QVBoxLayout()
        lv.addWidget(QLabel("NPC/商店(abName):"))
        sch = QHBoxLayout()
        self.shop_city_combo = QComboBox()
        self.shop_city_combo.setToolTip(
            "按地方/门派筛选 NPC(分类来自 内存所有道具.json 的 dataset/shop/<分类>/..., "
            "如 anju=安居城/hexing=禾兴城/menpai=门派)")
        self.shop_city_combo.currentIndexChanged.connect(self._filter_shop_list)
        sch.addWidget(self.shop_city_combo)
        self.shop_search = QLineEdit()
        self.shop_search.setPlaceholderText("搜索 NPC/商店… 中文 / 拼音 / 首字")
        self.shop_search.textChanged.connect(self._filter_shop_list)
        sch.addWidget(self.shop_search, 1)
        lv.addLayout(sch)
        self.shop_list = QListWidget()
        self.shop_list.itemSelectionChanged.connect(self._on_shop_selected)
        self.shop_list.setToolTip("点选 NPC 后右侧显示其 SellItems 卖品")
        lv.addWidget(self.shop_list, 1)
        lv_box = QWidget()
        lv_box.setLayout(lv)
        h.addWidget(lv_box, 1)
        rv = QVBoxLayout()
        # NPC 参数: Discount(折扣)/RefreshDay(刷新日)——选中 NPC 后随其字段刷新, 改动即写入
        _g = QGroupBox("NPC 参数(改动即写入)")
        _gf = QFormLayout(_g)
        self.discount_spin = QDoubleSpinBox()
        self.discount_spin.setRange(0.0, 1.0)
        self.discount_spin.setSingleStep(0.05)
        self.discount_spin.setDecimals(2)
        self.discount_spin.setToolTip("NPC 卖价折扣: 1=无折扣, 0.5=五折, 最小 0(范围 0~1)")
        self.btn_discount_dflt = QPushButton("默认 0.1")
        self.btn_discount_dflt.setToolTip("把折扣一键设为 0.1(一折)")
        self.btn_discount_dflt.clicked.connect(lambda: self.discount_spin.setValue(0.1))
        _dw = QWidget()
        _dl = QHBoxLayout(_dw)
        _dl.setContentsMargins(0, 0, 0, 0)
        _dl.addWidget(self.discount_spin, 1)
        _dl.addWidget(self.btn_discount_dflt)
        self.refresh_spin = QSpinBox()
        self.refresh_spin.setRange(0, MAX_ITEM_COUNT)
        self.refresh_spin.setToolTip("NPC 刷新日(可修改)")
        self.btn_refresh_dflt = QPushButton("默认 1")
        self.btn_refresh_dflt.setToolTip("把刷新日一键设为 1")
        self.btn_refresh_dflt.clicked.connect(lambda: self.refresh_spin.setValue(1))
        _rw = QWidget()
        _rl = QHBoxLayout(_rw)
        _rl.setContentsMargins(0, 0, 0, 0)
        _rl.addWidget(self.refresh_spin, 1)
        _rl.addWidget(self.btn_refresh_dflt)
        _gf.addRow("折扣 Discount:", _dw)
        _gf.addRow("刷新日 RefreshDay:", _rw)
        self.discount_spin.valueChanged.connect(self._on_shop_discount_changed)
        self.refresh_spin.valueChanged.connect(self._on_shop_refresh_changed)
        # 未选 NPC 前: 显示默认值但禁用
        self.discount_spin.setValue(1.0)
        self.refresh_spin.setValue(1)
        self.discount_spin.setEnabled(False)
        self.btn_discount_dflt.setEnabled(False)
        self.refresh_spin.setEnabled(False)
        self.btn_refresh_dflt.setEnabled(False)
        self.shop_title = QLabel("未选 NPC")
        self.shop_items = QTableWidget(0, 2)
        self.shop_items.setHorizontalHeaderLabels(["卖品名称", "数量"])
        self.shop_items.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.shop_items.setColumnWidth(1, 90)
        self.shop_items.verticalHeader().setVisible(False)
        self.shop_items.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.shop_items.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.shop_items.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.btn_add_sell = QPushButton("＋ 添加卖品…")
        self.btn_add_sell.setToolTip("从 道具名.json 搜索/多选添加道具到该 NPC 的 SellItems(默认数量 999; 与已有同名自动跳过)")
        self.btn_add_sell.clicked.connect(self._on_shop_add)
        self.btn_add_equip = QPushButton("＋ 添加装备…(SellEquips)")
        self.btn_add_equip.setToolTip(
            "把 装备类(equip, 如 1短铁棍/3喵金贵的衣物)加进该 NPC 的 SellEquips 装备栏。\n"
            "在左树勾选 equip 分类后多选; 件数=同名副本数(默认 1)。同名已有→向该名数组追加副本, 新名→新增条目; \n"
            "前导数字=等级(_Lv, 如 1短铁棍→_Lv 1)。")
        self.btn_add_equip.clicked.connect(self._on_shop_add_equip)
        rv.addWidget(_g)
        rv.addWidget(self.shop_title)
        rv.addWidget(self.shop_items, 1)
        _arow = QHBoxLayout()
        _arow.addWidget(self.btn_add_sell)
        _arow.addWidget(self.btn_add_equip)
        rv.addLayout(_arow)
        rv_box = QWidget()
        rv_box.setLayout(rv)
        h.addWidget(rv_box, 2)
        lay.addLayout(h, 1)
        self._refresh_shop_tab()
        return page

    def _refresh_shop_tab(self):
        """按 self._text 重建商店缓存、分类下拉与 NPC 列表(读档后/初始化时调用)。"""
        text = self._text or ""
        self._shop_cache = {}
        self._shop_key = None
        try:
            self._shop_city_map, order, _c = load_shop_cities()
        except Exception:  # noqa: BLE001
            self._shop_city_map, order = {}, []
        self._shop_city_order = list(order)
        self._shop_has_unmapped = False
        # 分类下拉: 全部 + 各分类(商店分类.json 顺序)
        self.shop_city_combo.blockSignals(True)
        self.shop_city_combo.clear()
        self.shop_city_combo.addItem("全部")
        self.shop_city_combo.setItemData(0, "", Qt.ItemDataRole.UserRole)
        for code in self._shop_city_order:
            self.shop_city_combo.addItem("%s(%s)" % (SHOP_CITY_ZH.get(code, code), code))
            self.shop_city_combo.setItemData(self.shop_city_combo.count() - 1,
                                             code, Qt.ItemDataRole.UserRole)
        self.shop_city_combo.blockSignals(False)
        self.shop_list.clear()
        if self._text is not None and "_ShopData" in text:
            for k, ab, so in shop_records(text):
                self._shop_cache[k] = (ab, so)
                code = self._shop_city_map.get(ab) or self._shop_city_map.get(k) or ""
                if not code:
                    self._shop_has_unmapped = True
                it = QListWidgetItem(ab)
                it.setData(Qt.ItemDataRole.UserRole, k)          # 商店键
                it.setData(Qt.ItemDataRole.UserRole + 1, code)   # 分类代码(可空)
                self.shop_list.addItem(it)
        if self._shop_cache:
            if self._shop_has_unmapped:
                self.shop_city_combo.addItem("(未分类)")
                self.shop_city_combo.setItemData(self.shop_city_combo.count() - 1,
                                                 "__none__", Qt.ItemDataRole.UserRole)
            self.shop_search.setEnabled(True)
            self.shop_city_combo.setEnabled(True)
            self.btn_add_sell.setEnabled(True)
            self.btn_add_equip.setEnabled(True)
            self.shop_list.setCurrentRow(0)
        else:
            self.shop_search.setEnabled(False)
            self.shop_city_combo.setEnabled(False)
            self.btn_add_sell.setEnabled(False)
            self.btn_add_equip.setEnabled(False)
            self.shop_items.setRowCount(0)
            self.shop_title.setText("请先打开含 NPC 商店(_ShopData)的存档" if self._text is None
                                    else "当前存档没有 NPC 商店数据(_ShopData)")

    def _filter_shop_list(self):
        """NPC 过滤: 分类下拉 + 名字(中文/拼音/首字母), 隐藏不匹配项。"""
        q = self.shop_search.text().strip()
        pm = load_pinyin_map()
        city = ""
        if self.shop_city_combo.count():
            city = self.shop_city_combo.itemData(self.shop_city_combo.currentIndex()) or ""
        for r in range(self.shop_list.count()):
            it = self.shop_list.item(r)
            c = it.data(Qt.ItemDataRole.UserRole + 1) or ""
            okc = True
            if city:
                okc = (not c) if city == "__none__" else (c == city)
            okn = (not q) or bool(filter_item_names([it.text()], q, pm, mode=0))
            it.setHidden(not (okc and okn))
        cur = self.shop_list.currentItem()
        if cur is not None and cur.isHidden():
            self.shop_list.setCurrentItem(None)
            self._on_shop_selected()

    def _current_shop_key(self):
        it = self.shop_list.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it is not None else None

    def _on_shop_selected(self, *_):
        self._shop_key = self._current_shop_key()
        if self._shop_key is None:
            self.shop_items.setRowCount(0)
            self.shop_title.setText("未选 NPC")
            self._refresh_shop_params()
            return
        self._show_shop_items()

    def _show_shop_items(self):
        """右侧显示当前 NPC 的 SellItems 卖品(名称/数量), 并刷新 折扣/刷新日 参数。"""
        key = self._shop_key
        self.shop_items.setRowCount(0)
        self._refresh_shop_params()
        if key is None or self._text is None:
            return
        ab, so = self._shop_cache.get(key, (key, None))
        items = shop_sellitems(self._text, key, sell_open=so)
        eqs = shop_equip_names(self._text, key, count_too=True)
        eqkinds = len(eqs)
        eqpieces = sum(c for _n, c in eqs)
        self.shop_title.setText("NPC: %s · 卖品 %d 件 · 装备 %d 种/%d 件" % (ab, len(items), eqkinds, eqpieces))
        self.shop_items.setRowCount(len(items))
        for r, (nm, cnt) in enumerate(items):
            i0 = QTableWidgetItem(nm)
            i0.setFlags(i0.flags() & ~Qt.ItemFlag.ItemIsEditable)
            i1 = QTableWidgetItem(str(cnt))
            i1.setFlags(i1.flags() & ~Qt.ItemFlag.ItemIsEditable)
            i1.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.shop_items.setItem(r, 0, i0)
            self.shop_items.setItem(r, 1, i1)

    # ---------------- NPC 参数: Discount(折扣)/RefreshDay(刷新日) ----------------
    def _refresh_shop_params(self):
        """按当前选中商店刷新 折扣/刷新日 数字框; 商店没有该字段时禁用(只支持改已存在的字段)。"""
        key = self._shop_key if getattr(self, "_shop_key", None) else None
        text = self._text
        self._shop_loading = True
        try:
            for spin, btn, field, dflt in (
                    (self.discount_spin, self.btn_discount_dflt, "Discount", 1.0),
                    (self.refresh_spin, self.btn_refresh_dflt, "RefreshDay", 1.0)):
                raw = None
                if key and text:
                    raw = shop_field(text, key, field)
                if raw is None:
                    spin.setValue(float(dflt))
                    spin.setEnabled(False)
                    btn.setEnabled(False)
                else:
                    spin.setEnabled(True)
                    btn.setEnabled(True)
                    try:
                        spin.setValue(float(raw))
                    except (TypeError, ValueError):
                        spin.setValue(float(dflt))
        finally:
            self._shop_loading = False

    @staticmethod
    def _fmt_num_text(v):
        """把数值整理成存档那种不带多余 0 的文本: 1.0→'1', 0.5→'0.5', 0.0→'0'。"""
        s = ("%f" % v).rstrip("0").rstrip(".")
        return s if s else "0"

    def _on_shop_discount_changed(self, v):
        self._write_shop_field("Discount", self._fmt_num_text(v))

    def _on_shop_refresh_changed(self, v):
        self._write_shop_field("RefreshDay", str(int(round(v))))

    def _resync_shop_cache(self):
        """文本被改写(会移动后续偏移)后, 用新 shop_records 重算所有商店的 SellItems 容器开括号缓存。"""
        if self._text is None or "_ShopData" not in self._text:
            return
        for k, ab, so in shop_records(self._text):
            self._shop_cache[k] = (ab, so)

    def _write_shop_field(self, field, new_text):
        """把当前商店对象的字段写入 self._text(改动即脏); 商店无该字段时只提示不改写。"""
        if self._shop_loading or self._shop_key is None or self._text is None:
            return
        key = self._shop_key
        zh = {"Discount": "折扣 Discount", "RefreshDay": "刷新日 RefreshDay"}.get(field, field)
        if shop_field(self._text, key, field) is None:
            self.statusBar().showMessage("该 NPC 没有 %s 字段, 无法修改" % zh, 3000)
            return
        nt, changed = shop_set_field(self._text, key, field, new_text)
        if changed:
            self._text = nt
            self._mark_dirty()
            self._resync_shop_cache()
            ab = self._shop_cache.get(key, (key,))[0]
            self.statusBar().showMessage("已把 %s 的 %s 改为 %s" % (ab, zh, new_text), 3000)

    def _on_shop_add(self):
        """给当前 NPC 的 SellItems 添加卖品(AddItemDialog 搜索/多选, 默认数量 999, 防重)。"""
        key = self._shop_key
        if key is None or self._text is None:
            return
        ab, so = self._shop_cache.get(key, (key, None))
        existing = {n for n, _ in shop_sellitems(self._text, key, sell_open=so)}
        dlg = AddItemDialog(self, existing=existing, default_count=999)
        dlg.setWindowTitle("为 %s 添加卖品" % ab)
        if not dlg.exec():
            return
        names = list(dict.fromkeys(dlg.chosen_names()))
        cnt = dlg.count_spin.value()
        if not names:
            return
        nt, added = shop_add_items(self._text, key, [(n, cnt) for n in names], sell_open=so)
        if added:
            self._text = nt
            self._mark_dirty()
            self._resync_shop_cache()
        self._show_shop_items()
        dup = len(names) - len(added)
        msg = "已为 %s 添加 %d 个卖品(数量 %d)" % (ab, len(added), cnt)
        if dup:
            msg += " · %d 个已存在自动跳过" % dup
        self.statusBar().showMessage(msg, 4000)

    def _on_shop_add_equip(self):
        """给当前 NPC 的 SellEquips 添加装备类道具(equip, 名内含前导数字=等级)。"""
        key = self._shop_key
        if key is None or self._text is None:
            return
        ab, _so = self._shop_cache.get(key, (key, None))
        if _shop_sellequips_open(self._text, key) is None:
            QMessageBox.information(self, "提示", "该 NPC 没有 SellEquips 装备栏字段, 无法添加")
            return
        # 注意: 同名可再追加副本(数组多实例), 故不把已有名灰显
        dlg = AddItemDialog(self, existing=set(), default_count=1)
        dlg.setWindowTitle("为 %s 添加装备(SellEquips)" % ab)
        if not dlg.exec():
            return
        names = list(dict.fromkeys(dlg.chosen_names()))
        cnt = max(1, dlg.count_spin.value())
        if not names:
            return
        nt, added = shop_add_equips(self._text, key, [(n, cnt) for n in names])
        if added:
            self._text = nt
            self._mark_dirty()
            self._resync_shop_cache()
        self._show_shop_items()
        pieces = sum(added.values())
        kinds = len(added)
        if kinds:
            self.statusBar().showMessage(
                "已为 %s 添加装备 %d 件(%d 种, 每种 %d 件; 同名=追加副本)" % (ab, pieces, kinds, cnt), 4000)
        else:
            self.statusBar().showMessage("未添加任何装备", 2000)

    def _refresh_char_tabs(self):
        """按当前 self._text 重建「道具」页之后的主角/队友页签。"""
        cur = self.tabs.currentIndex()
        text = self._text or ""
        model = char_model(text) if text else {"player": None, "friends": [], "maps": []}
        if model["player"] is None and not model["friends"]:
            # 保留 道具(index0)+商店NPC(index1), 移除之后的旧角色页
            while self.tabs.count() > 2:
                self.tabs.removeTab(self.tabs.count() - 1)
            empty = QWidget()
            lay = QVBoxLayout(empty)
            lab = QLabel("未在存档中找到角色属性段(savePlayerData / saveFriendData)。\n"
                         "请打开含角色数据的 *.es3 存档后查看(仅含 ItemHad 的样本无角色页)。")
            lab.setWordWrap(True)
            lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(lab)
            self.tabs.addTab(empty, "角色属性")
            return
        self._apply_char_model(model)
        if cur < self.tabs.count():
            self.tabs.setCurrentIndex(cur)

    def _apply_char_model(self, model):
        """由角色模型重建 主角/队友 页签(纯控件构建, 不再扫描大文本); 并预热容器定位缓存。"""
        self._char_spin_map = {}
        # 用模型里已知的容器开括号预热定位缓存: 打开后第一次点「一键全部默认」也不用再整档定位
        self._char_open_cache = {}
        txt = self._text
        if txt is not None:
            p = model.get("player")
            if p and p.get("open"):
                self._char_open_cache[tuple(SCOPE_PLAYER)] = (txt, p["open"])
            for f in model.get("friends") or []:
                if f.get("open"):
                    self._char_open_cache[("saveFriendData", "value",
                                           f.get("group"), f.get("key"))] = (txt, f["open"])
        while self.tabs.count() > 2:
            self.tabs.removeTab(self.tabs.count() - 1)
        if model.get("player"):
            self.tabs.addTab(self._build_player_page(model), "主角")
        for f in model.get("friends") or []:
            group = f.get("group", "AddFriends")
            disp = f.get("name") or f.get("key")
            suffix = ""
            if group != "AddFriends":
                suffix = "(%s)" % FRIEND_GROUP_LABELS.get(group, group)
            self.tabs.addTab(self._build_friend_page(group, f.get("key"), disp,
                                                     f.get("scalars") or [], f.get("dicts") or {}),
                             "队友·%s%s" % (disp, suffix))

    def _friend_display(self, key):
        """队友页签显示名: 优先中文 _Name, 否则英文键。"""
        scope = SCOPE_FRIENDS + [key]
        nm = get_str_field(self._text or "", scope, "_Name")
        return nm or key

    @staticmethod
    def _mk_value_spin(raw, span=1.0):
        """按原始值做一个 QDoubleSpinBox(数值/小数位/范围都贴近原值)。"""
        sp = QDoubleSpinBox()
        try:
            v = float(raw)
        except (TypeError, ValueError):
            v = 0.0
        dec = 3 if "." in str(raw) else 0
        sp.setDecimals(dec)
        sp.setSingleStep(span)
        bound = max(1e15, abs(v) * 4)
        sp.setRange(-bound, bound)
        sp.setValue(v)
        return sp

    def _char_page_scroll(self):
        """返回一个装进 QScrollArea 的空白容器页, 用于在其上堆积属性分组。"""
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(8, 8, 8, 8)
        inner = QWidget()
        self._char_inner_lay = QVBoxLayout(inner)
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setWidget(inner)
        lay.addWidget(area)
        return page

    # --- 写回入口(全部走 self._text, 点「保存」时随 ItemHad 一起落盘) ---
    def _loc_cached(self, scope):
        """带缓存的容器定位: 文本对象没变就复用上次开括号(改动后文本被替换, 自动失效重定位)。"""
        key = tuple(scope)
        ent = self._char_open_cache.get(key)
        if ent is not None and ent[0] is self._text:
            return ent[1]
        op = _locate_container(self._text or "", scope)
        self._char_open_cache[key] = (self._text, op)
        return op

    def _apply_scalar(self, scope, field, value):
        """把某角色容器内数字字段设为 value(带定位缓存, 编辑不重复整档扫描)。"""
        if self._text is None:
            return
        op = self._loc_cached(scope)
        if op is None:
            return
        nt = set_scalar_in(self._text, op, field, value)
        if nt is not self._text:
            self._text = nt
            self._mark_dirty()

    def _apply_dict_all(self, scope, field, value, spins):
        """把某角色内 编号/名字→数值 字典的全部值设为 value, 并同步已建 spin。"""
        if self._text is None:
            return
        nt = set_flat_dict_all(self._text, scope, field, value)
        if nt is not self._text:
            self._text = nt
            self._mark_dirty()
        self._building_char_page = True
        try:
            for s in spins:
                s.setValue(float(value))
        finally:
            self._building_char_page = False

    def _apply_char_defaults(self, scope, defaults):
        """把容器内“默认表里出现且当前为数字字段”的全部字段设成默认值(一键按默认)。

        带缓存定位 + 单遍替换; 之后只就地刷新该页数值框, 不再整档重建(避免卡顿)。
        """
        if self._text is None:
            return
        op = self._loc_cached(scope)
        if op is None:
            return
        nt = set_scalar_defaults_in(self._text, op, defaults)
        if nt is not self._text:
            self._text = nt
            self._mark_dirty()
        self._sync_char_spins(scope, defaults)

    def _sync_char_spins(self, scope, defaults):
        """点「一键全部默认」后只把本页对应数值框同步到默认值(不整档重建)。
        若该页没有已注册控件(未显示或已被重建), 才回退整档重建。"""
        key_t = tuple(scope)
        matched = [k for k in defaults if (key_t, k) in self._char_spin_map]
        if not matched:
            self._refresh_char_tabs()
            return
        self._building_char_page = True
        try:
            for k in matched:
                self._char_spin_map[(key_t, k)].setValue(float(defaults[k]))
        finally:
            self._building_char_page = False

    # --- 标量区(数据驱动: 直接吃 char_model 收集好的 [(键,原值)] ---
    def _add_scalar_section(self, title, scope, defaults, labels, data_scalars=None):
        """把某角色全部数字字段(预收集 data_scalars)排成 名称+当前值+默认按钮 行; 顶部一键全部默认。"""
        if data_scalars is None:
            data_scalars = list_scalar_fields(self._text or "", scope)
        group = QGroupBox(title)
        v = QVBoxLayout(group)
        top = QHBoxLayout()
        btn_all = QPushButton("一键全部按默认")
        btn_all.setToolTip("把本角色右侧标了默认值的字段一次性全部设成默认值")
        btn_all.clicked.connect(lambda: self._apply_char_defaults(scope, defaults))
        top.addWidget(btn_all)
        top.addStretch(1)
        tip = QLabel("可直接改数字; 带「默认」按钮的字段可点按钮一键恢复默认")
        tip.setStyleSheet("color:#888;")
        top.addWidget(tip)
        v.addLayout(top)
        form = QFormLayout()
        self._building_char_page = True
        try:
            for key, raw in data_scalars:
                lab = labels.get(key) or key
                labtxt = "%s(%s)" % (lab, key) if lab != key else key
                hb = QHBoxLayout()
                sp = self._mk_value_spin(raw)
                self._char_spin_map[(tuple(scope), key)] = sp
                dflt = defaults.get(key)
                if dflt is not None:
                    b = QPushButton("默认 %d" % int(dflt))
                    b.setToolTip("把 %s 一键改回默认 %d" % (labtxt, int(dflt)))
                    b.clicked.connect(lambda _=False, s=sp, dd=dflt: s.setValue(float(dd)))
                    hb.addWidget(sp)
                    hb.addWidget(b)
                    hb.addStretch(1)
                else:
                    hb.addWidget(sp)
                    hb.addStretch(1)
                def _onv(val, sc=scope, f=key):
                    if not self._building_char_page:
                        self._apply_scalar(sc, f, val)
                sp.valueChanged.connect(_onv)
                form.addRow(QLabel(labtxt), hb)
        finally:
            self._building_char_page = False
        v.addLayout(form)
        return group

    # --- 编号/名字字典区(数据驱动) ---
    def _add_dict_section(self, title, scope, field, default, data_entries=None,
                          key_labels=None, note=""):
        """把某角色的 {编号/名字: 数值} 字典(预收集 data_entries)显示成行, 提供「全部→默认值」按钮。"""
        if data_entries is None:
            data_entries = iter_flat_dict(self._text or "", scope, field)
        group = QGroupBox(title)
        v = QVBoxLayout(group)
        if note:
            n = QLabel(note)
            n.setStyleSheet("color:#888;")
            v.addWidget(n)
        if not data_entries:
            lab = QLabel("(存档中不存在 %s 或为空)" % field)
            lab.setStyleSheet("color:#aaa;")
            v.addWidget(lab)
            return group
        top = QHBoxLayout()
        btn_all = QPushButton("全部 → %s" % default)
        spins = []
        top.addWidget(btn_all)
        top.addStretch(1)
        cnt = QLabel("共 %d 项" % len(data_entries))
        cnt.setStyleSheet("color:#888;")
        top.addWidget(cnt)
        v.addLayout(top)
        form = QFormLayout()
        self._building_char_page = True
        try:
            for k, raw in data_entries:
                disp = (key_labels or {}).get(k)
                if disp is None:
                    disp = k if k else "(?)"
                sp = self._mk_value_spin(raw)
                spins.append(sp)
                def _onv(val, sc=scope, f=field, kk=k):
                    if not self._building_char_page:
                        self._apply_dict_one(sc, f, kk, val)
                sp.valueChanged.connect(_onv)
                form.addRow(QLabel(disp), sp)
        finally:
            self._building_char_page = False
        v.addLayout(form)
        btn_all.clicked.connect(lambda: self._apply_dict_all(scope, field, default, spins))
        return group

    # --- 地图标注点(_ActiveMap)区 ---
    def _add_map_section(self, names=None):
        if names is None:
            names = get_str_array(self._text or "", SCOPE_MAP, "_ActiveMap")
        group = QGroupBox("地图标注点(_ActiveMap)")
        v = QVBoxLayout(group)
        note = QLabel("已到过的地点列表(在 saveCustomData 段)。可添加新地名让游戏里出现对应标注。")
        note.setWordWrap(True)
        note.setStyleSheet("color:#888;")
        v.addWidget(note)
        self._map_list = QListWidget()
        self._map_list.addItems(names)
        v.addWidget(self._map_list)
        row = QHBoxLayout()
        self._map_edit = QLineEdit()
        self._map_edit.setPlaceholderText("输入要新增的地点名…(输入即搜索已有, 相同的不重复添加)")
        self._map_edit.setToolTip(
            "输入地点名时实时过滤下方已有地点列表, 便于查看该地点是否已存在(过滤只是隐藏显示);\n"
            "输入与已有地点同名再点「添加地点」会被拦截并提示, 不会重复添加。")
        self._map_edit.textChanged.connect(self._map_filter)
        self._map_edit.returnPressed.connect(self._map_add)
        btn_add = QPushButton("添加地点")
        btn_add.setToolTip("把输入框的地点加入列表; 与已有地点同名会被拦截(不重复添加)")
        btn_add.clicked.connect(self._map_add)
        btn_many = QPushButton("从地图跳转点批量添加…")
        btn_many.setToolTip(
            "打开 地图跳转点.json(由 MapJumpTable.bytes 提取生成)里的全部地图跳转点候选,\n"
            "可搜索(中文/拼音)/多选/全选一次添加多个; 默认只列出当前还没标注的跳转点,\n"
            "与 _ActiveMap 已有的重复项自动跳过。\n(缺失库可用 _scaffold/build_map_jump_points.py 生成)")
        btn_many.clicked.connect(self._on_add_maps)
        btn_del = QPushButton("删除选中")
        btn_del.clicked.connect(self._map_del)
        row.addWidget(self._map_edit, 1)
        row.addWidget(btn_add)
        row.addWidget(btn_many)
        row.addWidget(btn_del)
        v.addLayout(row)
        return group

    def _map_filter(self):
        """输入地点名时实时过滤下方 _map_list(只显示包含关键字的行), 便于查看/避免重复。

        过滤只是把不匹配的行 setHidden(True), 不影响数据与删除; 清空输入即恢复全部。
        """
        if getattr(self, "_map_list", None) is None:
            return
        q = (self._map_edit.text() or "").strip().lower()
        for r in range(self._map_list.count()):
            it = self._map_list.item(r)
            it.setHidden(bool(q) and q not in (it.text() or "").lower())

    def _map_refresh(self):
        if getattr(self, "_map_list", None) is not None:
            self._map_list.clear()
            self._map_list.addItems(get_str_array(self._text or "", SCOPE_MAP, "_ActiveMap"))
            self._map_filter()

    def _map_add(self):
        name = (self._map_edit.text() or "").strip()
        if not name:
            QMessageBox.information(self, "提示", "请输入要新增的地点名")
            return
        if self._text is None:
            return
        # 与已有地点相同 → 不重复添加: 状态栏提示 + 清空(恢复显示全部) + 定位到已存在项
        if name in get_str_array(self._text, SCOPE_MAP, "_ActiveMap"):
            self.statusBar().showMessage("地点已存在: %s(未重复添加)" % name, 3000)
            self._map_edit.clear()
            self._map_filter()
            for r in range(self._map_list.count()):
                it = self._map_list.item(r)
                if it.text() == name:
                    self._map_list.setCurrentItem(it)
                    self._map_list.scrollToItem(it)
                    break
            return
        nt = add_str_array(self._text, SCOPE_MAP, "_ActiveMap", name)
        if nt is not self._text:
            self._text = nt
            self._mark_dirty()
        self._map_edit.clear()
        self._map_refresh()
        self.statusBar().showMessage("已添加地点: %s" % name, 2000)

    def _map_del(self):
        items = self._map_list.selectedItems()
        if not items:
            QMessageBox.information(self, "提示", "请先选中要删除的地点")
            return
        if self._text is None:
            return
        for it in items:
            nt = remove_str_array(self._text, SCOPE_MAP, "_ActiveMap", it.text())
            if nt is not self._text:
                self._text = nt
                self._mark_dirty()
        self._map_refresh()

    def _on_add_maps(self):
        """从 地图跳转点.json 批量/全选添加地图标注点(与 _ActiveMap 已有重复自动跳过)。"""
        if self._text is None:
            return
        names = load_map_jump_names()
        if not names:
            QMessageBox.information(
                self, "提示",
                "地图跳转点.json 为空或不存在\n"
                "请先用 _scaffold/build_map_jump_points.py 从 MapJumpTable.bytes 生成, "
                "并放到程序目录(打包 exe 时放 exe 旁)。")
            return
        existing = set(get_str_array(self._text, SCOPE_MAP, "_ActiveMap"))
        dlg = MapJumpDialog(self, all_names=names, existing=existing)
        if not dlg.exec():
            return
        chosen = dlg.chosen_names()
        if not chosen:
            return
        added = []
        nt = self._text
        for nm in dict.fromkeys(chosen):
            nt2 = add_str_array(nt, SCOPE_MAP, "_ActiveMap", nm)
            if nt2 is not nt:
                nt = nt2
                added.append(nm)
        if added:
            self._text = nt
            self._mark_dirty()
        self._map_edit.clear()
        self._map_refresh()
        skipped = len(chosen) - len(added)
        msg = "已添加 %d 个地图标注点" % len(added)
        if skipped:
            msg += " · %d 个已存在自动跳过" % skipped
        self.statusBar().showMessage(msg, 4000)

    # --- 单行写某编号/名字字典的某个键的值 ---
    def _apply_dict_one(self, scope, field, key, value):
        """把字典 field 中键 key 的值改为 value(其余键不动)。"""
        if self._text is None:
            return
        val = str(int(round(float(value))))
        nt = self._text
        c = _locate_container(nt, scope)
        if c is None:
            return
        for key_disp, vs, _ve, _vt in _entry_values(nt, c):
            if key_disp == field and nt[vs:vs + 1] == "{":
                for kd, vs2, _ve2, _vt2 in _entry_values(nt, vs):
                    if kd == key:
                        tok = _num_token(nt, vs2)
                        if tok:
                            raw, end = tok
                            if raw == val:
                                return
                            nt = nt[:vs2] + val + nt[end:]
                break
        if nt is not self._text:
            self._text = nt
            self._mark_dirty()

    # --- 主角页 ---
    def _build_player_page(self, model=None):
        page = self._char_page_scroll()
        lay = self._char_inner_lay
        head = QLabel("主角属性(savePlayerData.value)：修改后点工具栏「保存/另存为/复制结果」与道具一起写回存档。")
        head.setWordWrap(True)
        head.setStyleSheet("font-weight:bold;")
        lay.addWidget(head)
        if not model:
            model = char_model(self._text or "")
        player = model.get("player") or {}
        scalars = player.get("scalars") or []
        dicts = player.get("dicts") or {}
        lay.addWidget(self._add_scalar_section("基础属性", SCOPE_PLAYER, PLAYER_DEFAULTS,
                                                PLAYER_LABELS, scalars))
        lay.addWidget(self._add_dict_section(
            "武学经验 KongFuTypeLv", SCOPE_PLAYER, "KongFuTypeLv", KONGFU_EXP_DEFAULT,
            dicts.get("KongFuTypeLv"),
            note="编号=武学类型, 数值=经验; 前面的编号不变, 只改数值(默认一键 999999)"))
        lay.addWidget(self._add_dict_section(
            "生活技能经验 LifeExp", SCOPE_PLAYER, "LifeExp", LIFEEXP_DEFAULT,
            dicts.get("LifeExp"),
            note="编号=生活技能, 数值=经验; 编号不变, 默认一键 999999"))
        lay.addWidget(self._add_dict_section(
            "六维当前值 SixProCurrent", SCOPE_PLAYER, "SixProCurrent", SIXPRO_DEFAULT,
            dicts.get("SixProCurrent"),
            key_labels={str(k): SIX_LABELS[k] for k in SIX_LABELS},
            note="1~6 对应 力道/感知/灵气/体魄/经脉/速度 当前值(默认一键 999)"))
        lay.addWidget(self._add_dict_section(
            "好友好感度 FriendLoveNum", SCOPE_PLAYER, "FriendLoveNum", LOVE_DEFAULT,
            dicts.get("FriendLoveNum"),
            note="前面是好友名字, 后面是好感度; 名字不变, 默认一键 999"))
        lay.addWidget(self._add_map_section(model.get("maps") or []))
        return page

    # --- 队友页 ---
    def _build_friend_page(self, group, key, disp, scalars=None, dicts=None):
        scope = ["saveFriendData", "value", group, key]
        page = self._char_page_scroll()
        lay = self._char_inner_lay
        gtag = FRIEND_GROUP_LABELS.get(group, group) if group != "AddFriends" else ""
        head = QLabel("队友：%s(%s)%s  · 修改后点「保存/另存为/复制结果」写回存档。"
                      % (disp, key, ("·%s" % gtag) if gtag else ""))
        head.setWordWrap(True)
        head.setStyleSheet("font-weight:bold;")
        lay.addWidget(head)
        if scalars is None or dicts is None:
            _scal, _dct = collect_page(self._text or "",
                                       _locate_container(self._text or "", scope),
                                       FRIEND_DICT_FIELDS)
            if scalars is None:
                scalars = _scal
            if dicts is None:
                dicts = _dct
        lay.addWidget(self._add_scalar_section("队友属性", scope, FRIEND_DEFAULTS,
                                                FRIEND_LABELS, scalars))
        lay.addWidget(self._add_dict_section(
            "六维当前值 SixProCurrent", scope, "SixProCurrent", SIXPRO_DEFAULT,
            dicts.get("SixProCurrent"),
            key_labels={str(k): SIX_LABELS[k] for k in SIX_LABELS},
            note="1~6 对应 力道/感知/灵气/体魄/经脉/速度 当前值(默认一键 999)"))
        lay.addWidget(self._add_dict_section(
            "武学经验 _KongFuTypeLv", scope, "_KongFuTypeLv", KONGFU_EXP_DEFAULT,
            dicts.get("_KongFuTypeLv"),
            note="编号不变, 只改经验数值(默认一键 999999)"))
        return page

    def _on_item_changed(self, item):
        if self._loading or self._suppress_change:
            return
        row, col = item.row(), item.column()
        real = self._row_to_item_index(row)   # 考虑搜索过滤: 行号→self._items 真实索引
        if real < 0:
            return
        if col == 1:  # 名称
            new_name = item.text().strip()
            ok, err = validate_item_name(new_name)
            if not ok:
                self._suppress_change = True
                item.setText(self._items[real].name)
                self._suppress_change = False
                self.statusBar().showMessage(err, 3000)
                return
            for k, it in enumerate(self._items):
                if k != real and it.name == new_name:
                    self._suppress_change = True
                    item.setText(self._items[real].name)
                    self._suppress_change = False
                    self.statusBar().showMessage("道具名称重复: %s" % new_name, 3000)
                    return
            if self._items[real].name != new_name:
                self._mark_dirty()
            self._items[real].name = new_name
            self.statusBar().showMessage("已修改名称 -> %s" % new_name, 2000)
        elif col == 2:  # 数量
            txt = item.text().strip()
            try:
                v = int(txt)
            except ValueError:
                v = -1
            if v < 0 or v > MAX_ITEM_COUNT:
                self._suppress_change = True
                item.setText(str(self._items[real].count))
                self._suppress_change = False
                self.statusBar().showMessage("数量必须是 0~%d 的整数" % MAX_ITEM_COUNT, 3000)
                return
            if self._items[real].count != v:
                self._mark_dirty()
            self._items[real].count = v
            self.statusBar().showMessage("已修改数量 -> %d" % v, 2000)

    # ---------------- 数据加载 ----------------
    def _load_text(self, text, bom=b""):
        lines = text.splitlines(keepends=True)
        start_idx = find_itemhad_line(lines)
        if start_idx < 0:
            QMessageBox.warning(self, "提示", "未找到 ItemHad 段, 无法解析该内容")
            return False
        items, indent, close_idx = parse_itemhad(lines, start_idx)
        if close_idx is None:
            QMessageBox.warning(self, "提示", "ItemHad 段解析失败, 请确认内容完整")
            return False
        self._text = text
        self._bom = bom
        self._items = items
        self._indent = indent
        self._file_path = None
        self._reload_table()
        try:
            self._lib_new, self._lib_total = merge_item_names_from_text(text)
        except Exception:  # noqa: BLE001
            self._lib_new, self._lib_total = [], 0
        self._refresh_char_tabs()
        self._refresh_shop_tab()
        self._mark_clean()  # 新读入的内容作为干净基线
        return True

    def _lib_status(self, msg):
        """在状态消息后附加道具名库收录情况。"""
        if self._lib_total:
            if self._lib_new:
                msg += " · 道具名库 +%d 共 %d" % (len(self._lib_new), self._lib_total)
            else:
                msg += " · 道具名库共 %d(无新增)" % self._lib_total
        return msg

    def _on_open(self):
        path, _ = QFileDialog.getOpenFileName(self, "打开 es3 存档", "",
                                              "es3 存档 (*.es3);;所有文件 (*.*)")
        if not path:
            return
        self._open_path(path)

    _ASYNC_OPEN_MIN = 600 * 1024   # 存档文本超过该字节数时, 打开改走后台线程(避免卡顿); 小文件/测试仍同步

    def _open_path(self, path, record=True):
        """打开指定路径的存档文件: 读取 -> 解析 -> 刷新表格。

        大档(>~600KB)由 `_open_big` 在后台线程完成 读取后解析+角色模型收集,
        期间主线程泵事件、忙光标保持窗口可响应; 小文件/测试走同步路径。
        record=True 时, 成功打开会记入「最近打开」历史。返回是否成功。
        """
        try:
            text, bom = read_es3_text(path)
        except FileNotFoundError:
            if record:
                self._remove_history(path)
            QMessageBox.warning(self, "提示", "文件不存在, 已从最近记录移除:\n%s" % path)
            return False
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "错误", "读取文件失败:\n%s" % e)
            return False
        if len(text) >= self._ASYNC_OPEN_MIN and not getattr(self, "_force_sync", False):
            return self._open_big(path, text, bom, record)
        if not self._load_text(text, bom):
            return False
        self._file_path = path
        self.src_label.setText("源: %s" % path)
        self.statusBar().showMessage(
            self._lib_status("已打开 %s · 共 %d 个道具" % (path, len(self._items))), 4000)
        if record:
            self._record_history(path)
        return True

    # ---- 大档后台打开: 解析/角色模型放子线程, 主线程泵事件保持响应(多线程避免卡顿) ----
    def _set_busy(self, busy):
        """忙状态: 等待光标 + 禁用工具栏, 防止重入。"""
        if busy:
            self._busy = True
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        else:
            self._busy = False
            QApplication.restoreOverrideCursor()
        if getattr(self, "toolbar", None) is not None:
            for a in self.toolbar.actions():
                a.setEnabled(not busy)
        if getattr(self, "recent_btn", None) is not None:
            self.recent_btn.setEnabled(not busy)
        if busy:
            self.statusBar().showMessage("正在读取存档…请稍候", 0)

    def _run_bg(self, work, busy_msg="正在处理…请稍候"):
        """在后台线程跑 work()(纯计算/文件 IO), 期间忙光标 + 禁用工具栏 + 主线程泵事件保持窗口可响应。

        与 _open_big 同一套「后台线程 + done 标志 + 主线程泵事件」模式, 供 大档粘贴/保存/另存/复制
        等耗时入口复用。work 抛异常 → 返回 (False, 异常消息); 正常 → (True, 返回值); 忙时 → (False, 提示)。
        """
        if getattr(self, "_busy", False):
            return (False, "程序正忙, 请稍候")
        self._set_busy(True)
        self.statusBar().showMessage(busy_msg, 0)
        res = {}
        done = []

        def _run():
            try:
                res["val"] = work()
            except Exception as e:  # noqa: BLE001
                res["err"] = str(e)
            finally:
                done.append(1)

        threading.Thread(target=_run, daemon=True).start()
        app = QApplication.instance()
        while not done:
            app.processEvents()
            time.sleep(0.005)
        self._set_busy(False)
        if "err" in res:
            return (False, res["err"])
        return (True, res["val"])

    def _open_big(self, path, text, bom, record):
        """大档: 后台线程做纯解析 + 角色模型收集; 完成后主线程建 UI。"""
        if getattr(self, "_busy", False):
            return False

        def _work():
            lines = text.splitlines(keepends=True)
            si = find_itemhad_line(lines)
            if si < 0:
                raise ValueError("未找到 ItemHad 段, 无法解析该内容")
            items, indent, ci = parse_itemhad(lines, si)
            if ci is None:
                raise ValueError("ItemHad 段解析失败, 请确认内容完整")
            return {"items": items, "indent": indent,
                    "model": char_model(text), "lib": merge_item_names_from_text(text)}

        ok, r = self._run_bg(_work, "正在读取存档…请稍候")
        if not ok:
            QMessageBox.warning(self, "提示", r)
            return False
        self._text = text
        self._bom = bom
        self._items = r["items"]
        self._indent = r["indent"]
        self._file_path = path
        self._lib_new, self._lib_total = r["lib"]
        self._reload_table()
        self._apply_char_model(r["model"])
        self._refresh_shop_tab()
        self._mark_clean()
        self.src_label.setText("源: %s" % path)
        self.statusBar().showMessage(
            self._lib_status("已打开 %s · 共 %d 个道具" % (path, len(self._items))), 4000)
        if record:
            self._record_history(path)
        return True

    def _on_open_last(self):
        """打开上一次打开过的存档文件(历史第一条)。"""
        if not self._history:
            QMessageBox.information(self, "提示", "暂无最近打开记录\n请先用「打开」选择一次存档文件")
            return
        self._open_path(self._history[0])

    def _on_reload(self):
        """游戏已存档后, 再次读取当前文件内容。

        以磁盘文件为准重新读入并刷新表格; 若内存中有未保存修改则先询问。
        """
        if not self._file_path:
            QMessageBox.information(self, "提示",
                                    "请先打开一个存档文件\n可点「打开上次」或「最近 ▾」快速打开")
            return
        if self._dirty:
            ret = QMessageBox.question(
                self, "重新读取",
                "当前有未保存的修改(尚未点「保存」)。\n"
                "重新读取会丢弃这些修改、以磁盘文件为准。\n\n是否继续?")
            if ret != QMessageBox.StandardButton.Yes:
                return
        self._open_path(self._file_path)

    # ---------------- 最近打开历史 ----------------
    def _update_history_ui(self):
        """按 self._history 刷新「打开上次」按钮可用性。"""
        self.act_open_last.setEnabled(bool(self._history))

    def _record_history(self, path):
        """成功打开后把路径记入历史(最新在前, 去重, 最多 HISTORY_MAX 条)。"""
        try:
            self._history = push_history(path, self._history)
        except Exception:  # noqa: BLE001 历史写盘失败不影响主流程
            norm = os.path.normcase
            self._history = [p for p in [path] + self._history
                             if norm(p) != norm(path)][:HISTORY_MAX]
        self._update_history_ui()

    def _remove_history(self, path):
        """把某条路径从历史移除(如文件已不存在), 并同步写盘。"""
        norm = os.path.normcase
        self._history = [p for p in self._history if norm(p) != norm(path)]
        save_history(self._history)
        self._update_history_ui()

    def _clear_history(self):
        """清空最近打开历史。"""
        self._history = []
        save_history([])
        self._update_history_ui()

    def _rebuild_recent_menu(self):
        """每次展开「最近 ▾」前重建菜单(反映最新历史)。"""
        menu = self.recent_menu
        menu.clear()
        if not self._history:
            a = menu.addAction("（暂无最近记录）")
            a.setEnabled(False)
            return
        for i, p in enumerate(self._history, 1):
            a = menu.addAction("%d. %s" % (i, os.path.basename(p)))
            a.setToolTip(p)
            a.triggered.connect(lambda checked=False, pp=p: self._open_path(pp))
        menu.addSeparator()
        act_clear = menu.addAction("清空最近记录")
        act_clear.triggered.connect(lambda: self._clear_history())

    def _on_paste(self):
        dlg = PasteDialog(self)
        if not dlg.exec():
            return
        text = dlg.editor.toPlainText()
        if not text.strip():
            QMessageBox.warning(self, "提示", "粘贴内容为空")
            return
        if len(text) >= self._ASYNC_OPEN_MIN:
            # 大段粘贴: 解析/角色模型/收录 放后台线程(同大档打开), 避免整份解析卡 UI
            if not self._paste_big(text):
                return
        elif not self._load_text(text):
            return
        self.src_label.setText("源: 粘贴内容(未保存为文件)")
        self.statusBar().showMessage(
            self._lib_status("已解析粘贴内容 · 共 %d 个道具" % len(self._items)), 4000)

    def _paste_big(self, text):
        """粘贴大段内容: 解析 + 角色模型 + 道具名收录 放后台线程, 完成回主线程建表/建页(不卡 UI)。返回是否成功。"""
        def _work():
            lines = text.splitlines(keepends=True)
            si = find_itemhad_line(lines)
            if si < 0:
                raise ValueError("未找到 ItemHad 段, 无法解析该内容")
            items, indent, ci = parse_itemhad(lines, si)
            if ci is None:
                raise ValueError("ItemHad 段解析失败, 请确认内容完整")
            return {"items": items, "indent": indent,
                    "model": char_model(text), "lib": merge_item_names_from_text(text)}

        ok, r = self._run_bg(_work, "正在解析粘贴内容…请稍候")
        if not ok:
            QMessageBox.warning(self, "提示", r)
            return False
        self._text = text
        self._bom = b""
        self._items = r["items"]
        self._indent = r["indent"]
        self._file_path = None
        self._lib_new, self._lib_total = r["lib"]
        self._reload_table()
        self._apply_char_model(r["model"])
        self._refresh_shop_tab()
        self._mark_clean()
        return True

    # ---------------- 保存 / 导出 ----------------
    def _generate(self):
        """根据当前物品列表重建完整文本。"""
        if self._text is None:
            raise RuntimeError("尚未加载任何存档内容")
        return apply_itemhad_text(self._text, self._items)

    def _on_save(self):
        if self._text is None:
            QMessageBox.warning(self, "提示", "请先打开或粘贴存档内容")
            return
        if not self._file_path:
            self._on_save_as()
            return
        path, text, bom = self._file_path, self._text, self._bom

        def _work():
            new_text = apply_itemhad_text(text, list(self._items))
            write_es3_text(path, new_text, bom)
            return new_text

        ok, r = self._run_bg(_work, "正在保存存档…请稍候")   # 重建+写盘放后台, 大档不卡 UI
        if not ok:
            QMessageBox.critical(self, "错误", "保存失败:\n%s" % r)
            return
        self._text = r
        self._mark_clean()
        self.statusBar().showMessage("已保存到 %s" % path, 3000)

    def _on_save_as(self):
        if self._text is None:
            QMessageBox.warning(self, "提示", "请先打开或粘贴存档内容")
            return
        path, _ = QFileDialog.getSaveFileName(self, "另存为 es3 存档", "",
                                              "es3 存档 (*.es3);;所有文件 (*.*)")
        if not path:
            return
        if not path.lower().endswith(".es3"):
            path += ".es3"
        text, bom = self._text, self._bom

        def _work():
            new_text = apply_itemhad_text(text, list(self._items))
            write_es3_text(path, new_text, bom)
            return new_text

        ok, r = self._run_bg(_work, "正在另存存档…请稍候")     # 重建+写盘放后台, 大档不卡 UI
        if not ok:
            QMessageBox.critical(self, "错误", "写入文件失败:\n%s" % r)
            return
        self._text = r
        self._file_path = path
        self._mark_clean()
        self.src_label.setText("源: %s" % path)
        self.statusBar().showMessage("已另存为 %s" % path, 3000)

    def _on_copy(self):
        if self._text is None:
            QMessageBox.warning(self, "提示", "请先打开或粘贴存档内容")
            return
        text = self._text

        def _work():
            return apply_itemhad_text(text, list(self._items))

        ok, r = self._run_bg(_work, "正在生成结果…请稍候")       # 大档重建放后台
        if not ok:
            QMessageBox.critical(self, "错误", "生成内容失败:\n%s" % r)
            return
        new_text = r
        QApplication.clipboard().setText(new_text)   # 剪贴板须在主线程
        self.statusBar().showMessage("已把修改后的完整内容复制到剪贴板(可粘贴回存档文件)", 4000)

    # ---------------- 设置(批量目标值持久化) ----------------
    def _on_batch_value_changed(self, val):
        """右侧「全部改为」目标值变化 → 记住并自动保存; 同步左侧快捷按钮文字。"""
        self._batch_value = val
        self.btn_9999.setText("全部改为 %d" % val)
        self._autosave_settings()

    def _autosave_settings(self):
        self._settings_save_timer.start()

    def _save_settings_now(self):
        self._settings["batch_value"] = self._batch_value
        save_app_settings(self._settings)

    def closeEvent(self, event):
        try:
            self._settings_save_timer.stop()
            self._save_settings_now()
        except Exception:  # noqa: BLE001
            pass
        super().closeEvent(event)

    # ---------------- 编辑操作 ----------------
    def _on_set_all_9999(self):
        self.all_spin.setValue(self._batch_value)  # 与按钮文字一致(记住的目标值)
        self._on_set_all_value()

    def _on_set_all_value(self):
        if not self._items:
            self.statusBar().showMessage("当前无道具", 2000)
            return
        v = self.all_spin.value()
        skip = self.skip_copper_check.isChecked()
        n = 0
        for it in self._items:
            if skip and it.name == "铜钱":
                continue
            it.count = v
            n += 1
        self._sync_visible_counts()   # 只刷数量列文本, 不整表重建(上千行时避免卡顿)
        if n:
            self._mark_dirty()
        self.statusBar().showMessage("已将 %d 个道具数量改为 %d" % (n, v), 3000)

    def _on_set_get_time_zero(self):
        if not self._items:
            self.statusBar().showMessage("当前无道具", 2000)
            return
        changed = [it for it in self._items if it.get_time not in (None, "0", 0)]
        if not changed:
            self.statusBar().showMessage("全部道具的 _GetTimeNew 已是 0", 3000)
            return
        if QMessageBox.question(self, "确认",
                                "将把 ItemHad 全部道具的 _GetTimeNew 改为 0(共 %d 个)?\n点「保存」后才写入文件。"
                                % len(changed)) != QMessageBox.StandardButton.Yes:
            return
        for it in changed:
            it.get_time = None  # None -> 重建为 0
        self._mark_dirty()
        self.statusBar().showMessage("已将 %d 个道具的 _GetTimeNew 改为 0" % len(changed), 3000)

    def _on_add(self):
        dlg = AddItemDialog(self, existing={it.name for it in self._items})
        if not dlg.exec():
            return
        names = dlg.chosen_names()
        count = dlg.count_spin.value()
        if not names:
            return
        existing = {it.name for it in self._items}
        added, dup, bad = [], [], []
        for nm in names:
            ok, err = validate_item_name(nm)
            if not ok:
                bad.append((nm, err))
                continue
            if nm in existing:
                dup.append(nm)
                continue
            existing.add(nm)
            self._items.append(Es3Item(nm, count, None))
            added.append(nm)
        if not added and not dup and not bad:
            return
        if added:
            self._clear_search()   # 清掉搜索过滤, 让新加道具在完整列表末尾可见
            self._mark_dirty()
            self.table.scrollToBottom()
        msg = "已新增 %d 个道具(每个数量 %d)" % (len(added), count)
        if dup:
            msg += "；%d 个已在列表中自动跳过" % len(dup)
        self.statusBar().showMessage(msg, 4000)
        if bad:
            QMessageBox.warning(self, "提示",
                                "以下名称不合法, 未添加:\n" + "\n".join(
                                    "%s (%s)" % (nm, err) for nm, err in bad[:10]))

    def _on_delete(self):
        # 选中行号→真实索引(过滤视图下 selectedItems 只含可见行, 映射后按真实索引降序删)
        rows = []
        for i in self.table.selectedItems():
            r = self._row_to_item_index(i.row())
            if r >= 0 and r not in rows:
                rows.append(r)
        rows.sort(reverse=True)
        if not rows:
            QMessageBox.information(self, "提示", "请先选中要删除的道具(可按住 Ctrl 多选)")
            return
        names = [self._items[r].name for r in rows]
        if QMessageBox.question(self, "确认删除", "确定删除 %d 个道具?\n%s"
                                % (len(rows), "、".join(names))) != QMessageBox.StandardButton.Yes:
            return
        if self._filter_map is None:
            # 无过滤(大表最常见): 局部 removeRow 只删该行, 其余行 item 对象保留, 仅顺延 # 号文本——避免整表重建卡顿
            self._delete_rows_local(rows)
        else:
            # 过滤视图通常行少, 整表重建最稳(同步 filter_map 与 # 列/计数标签)
            for r in rows:
                del self._items[r]
            self._reload_table()
        self._mark_dirty()
        self.statusBar().showMessage("已删除 %d 个道具" % len(rows), 3000)

    def _delete_rows_local(self, rows):
        """无过滤视图下局部删除: 数据按真实索引降序删; 表格 removeRow 逐行移除(其余行 item 对象复用),
        再给受影响后缀行的 # 列顺延重编号(不重建整表, 大表删一行也立即响应)。"""
        min_del = rows[-1]                       # rows 降序, 末尾=最小索引
        for r in rows:
            del self._items[r]
        t = self.table
        t.blockSignals(True)
        try:
            for r in rows:                       # 降序先删大号, 前序行号不受影响
                t.removeRow(r)
            self._loading = True
            for r in range(min_del, t.rowCount()):
                c = t.item(r, 0)
                if c is not None:
                    c.setText(str(r + 1))
        finally:
            self._loading = False
            t.blockSignals(False)
        self._set_count_label()

    def _on_add_all_items(self):
        names = list(dict.fromkeys(load_item_names()))  # 去重, 防库文件历史重复导致重复添加
        if not names:
            QMessageBox.information(self, "提示",
                                    "道具名库为空\n请先「打开/粘贴」一次存档, 程序会自动把其中的道具名收录到 道具名.json")
            return
        existing = {it.name for it in self._items}
        to_add = [n for n in names if n not in existing]
        if not to_add:
            QMessageBox.information(self, "提示", "道具名库中的 %d 个道具均已存在, 无需添加" % len(names))
            return
        if QMessageBox.question(self, "确认添加",
                                "将把道具名库中的 %d 个道具追加到列表(每个数量 9999)?\n已有 %d 个自动跳过。"
                                % (len(to_add), len(names) - len(to_add))) != QMessageBox.StandardButton.Yes:
            return
        for n in to_add:
            self._items.append(Es3Item(n, 9999, None))
        self._clear_search()   # 清掉搜索过滤, 让新加道具在完整列表末尾可见
        self._mark_dirty()
        self.table.scrollToBottom()
        self.statusBar().showMessage("已新增 %d 个道具(每个 9999)" % len(to_add), 4000)

    def _on_organize_names(self):
        """一键整理道具列表: 把当前存档(表格)里已有的道具名补入 道具名.json。

        读档(打开/粘贴/上次/最近/重新读取)时已自动收录; 本按钮适合在手动
        新增/改名自定义道具名后, 把表格里最新得到的道具名也同步进 json(不重名)。
        """
        if not self._items:
            QMessageBox.information(self, "提示",
                                    "请先打开/粘贴存档(表格中有道具), 再点「一键整理道具列表」")
            return
        names = [it.name for it in self._items if it.name]
        try:
            new, total = merge_item_names(names)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "错误", "更新 道具名.json 失败:\n%s" % e)
            return
        if new:
            shown = "、".join(new[:10])
            if len(new) > 10:
                shown += " 等 %d 个" % len(new)
            QMessageBox.information(
                self, "整理完成",
                "已按当前存档道具名更新 道具名.json:\n新增 %d 个(道具名库现共 %d 个)。\n新增: %s"
                % (len(new), total, shown))
        else:
            self.statusBar().showMessage(
                "整理完成: 道具名库共 %d 个 · 存档里的道具名均已收录(无新增)" % total, 4000)

    # ---------------- 帮助 ----------------
    def _on_help(self):
        QMessageBox.information(self, "说明 - %s" % APP_NAME, _HELP_TEXT)


_HELP_TEXT = """\
<b>灵兽江湖存档修改器 v%s</b><br>
针对 *.es3 存档的 <b>"ItemHad"</b> 段道具数量修改工具。

<h3>用法</h3>
1. <b>打开</b>: 点「打开」选择 custom0.es3 等存档文件; 之后可点 <b>打开上次</b> 直接重开
   上次文件, 或点 <b>最近 ▾</b> 从「最近打开」历史里点选直接打开(历史最多 10 条,
   存于程序目录/历史记录.json, 菜单里可「清空最近记录」)。也可以点 <b>粘贴</b>
   把整份存档内容粘贴进来。
2. 表格会枚举出 ItemHad 里全部道具的 <b>名称</b> 和 <b>数量</b>, 可直接双击单元格修改;
   点击表头「道具名称 / 数量」可按名称或数量排序(点击=升序, 同列再点一次=降序反向),
   右键表头可直接选「升序/降序」, 排序不影响修改。
   <b>搜索道具(v2.3.0)</b>: 表格上方搜索框支持 <b>中文 / 拼音全拼 / 拼音首字母 / 数字</b>
   (如输入 tq / tongqian 找 铜钱; 右侧可切「仅中文 / 仅拼音」), 输入即<b>实时过滤</b>当前道具,
   便于快速定位要改/要删的道具(# 列显示其在完整列表里的原序号); 此时 <b>双击编辑、删除选中</b>
   只作用于当前显示(过滤后)的行; 点搜索框右侧 ✕ / 清空文字即恢复显示全部道具。
3. <b>全部改为 9999</b>: 一键按目标值批量改(可勾选「跳过铜钱」保留铜钱原值); 目标值可在右侧
   「全部改为:」数字框改成任意数值后点「全部改为」——改后程序会<b>自动记住</b>, 左侧按钮文字同步
   显示该值, 重开程序仍保留(设置存 程序目录/设置.json)。
4. <b>新增道具</b>: 打开选择窗口, 左栏为 <b>分类树(v2.6.0)</b> —— 按 内存所有道具.json 的
   dataset 路径分级: 大分类(equip装备/item道具/recipe配方/bookcontent书籍/kangfu武功秘籍/
   skillcom技能合成/shanhailu山海录) → 小分类 → 细分类, 数据来自 程序目录/道具分类.json
   (由 _scaffold/build_item_categories.py 生成)。<b>勾选某分类</b> = 把该分类及其全部下级道具
   纳入右侧候选; 可多选大/小/细分类; 勾「大分类」自动带上其所有下级, 想精确排除某子分类可展开后
   取消勾选(父分类变「半选」)。<b>默认不勾选</b>: 点左侧分类前的方框勾选, 右侧即<b>只显示该分类
   的道具</b>(未勾选时右侧为空并提示; 此时在搜索框输入仍会<b>全库给出建议</b>); 想一次选全部点左下
   「全勾选」。右栏对候选可 <b>搜索</b>(中文、拼音全拼、拼音首字母、数字, 如输入
   tq / tongqian 找 铜钱; 顶部可切「仅中文 / 仅拼音」) 并 <b>多选 / 全选</b> 一次添加多个(数量统一);
   也可在搜索框直接输入自定义道具名后回车; 勾选 <b>仅显示缺少(未在个人背包)</b> 即只列出当前勾选
   分类里个人背包还缺的道具(底部实时显示 库总数/个人已有/缺少/已选), 配合「全选」一次补齐;
   找不到 道具分类.json 时自动回退 道具名.json 平铺列表。 <b>删除选中</b>: 删除选中行。
5. <b>保存</b>: 写回原文件; <b>另存为</b>: 存成新文件; <b>复制结果</b>: 把修改后的完整
   内容复制到剪贴板(配合「粘贴」流程使用)。
6. <b>重新读取</b>: 打开文件后若回到游戏又存了档(游戏把文件更新了), 点「重新读取」
   即可再次读取当前文件内容、刷新表格; 若内存里还有未保存的修改, 会先询问是否丢弃。
7. <b>多角色分页</b>: 打开含角色数据的存档后, 主区顶部会多出「主角」与每个「队友·名字」页签
   (v2.0.0 新增; v2.1.0 按 <b>_AbName 枚举全部队友</b>)——每页可逐个直接改 等级/经验/属性/血量/
   特性点/已用点等数值——带「默认」按钮的字段点按钮即一键设默认(也可点「一键全部按默认」);
   主角页另可整组改 <b>武学经验 KongFuTypeLv</b>(默认一键 999999)、<b>生活技能 LifeExp</b>(999999)、
   <b>六维 SixProCurrent</b>(999)、<b>好感度 FriendLoveNum</b>(999, 前面是好友名字);
   每个队友页也有其 六维(999) 与 武学经验 _KongFuTypeLv(999999)。
   队友按存档里的 _AbName 逐一自动收录: 不论在队(AddFriends)、离队(LeaveFriends, 页签带「离队」)
   还是以后游戏新增的容器/队友, 都会自动出现对应页签, 无需改代码。
   页内「地图标注点(_ActiveMap)」可输入地点名新增/选中删除——输入时会实时过滤下方已有地点便于查重,
   与已有地点同名的添加会被拦截并提示(v2.3.1), 不会重复; 点「从地图跳转点批量添加…」(v2.4.0)可打开
   程序目录 地图跳转点.json(由 _scaffold/build_map_jump_points.py 从 MapJumpTable.bytes 提取),
   搜索(中文/拼音)/多选/全选一次添加多个跳转点(默认只列还没标注的, 与已有重复自动跳过)。
   角色页的修改与道具一样, 点「保存/另存为/复制结果」时随存档一起写回; 只精确替换对应数值,
   其它数据段原样保留。
8. <b>大档后台读取(v2.2.0)</b>: 超过约 600KB 的存档会在<b>后台线程</b>完成解析与角色页数据收集,
   打开/重新读取时窗口保持可操作(忙光标提示, 不会卡死/白屏)。
9. <b>商店NPC卖的道具(v2.5.1)</b>: 主区「商店NPC」页签——左侧列出存档里的 NPC/商店(取自
   saveUtilData.value._ShopData 的 abName), 顶部<b>分类下拉</b>可按 地方/门派 筛选(安居城/禾兴城/黑市/
   门派/临州城/龙居城/…, v2.5.1, 分类来自 内存所有道具.json 的 dataset/shop/*, 已生成 商店分类.json),
   并支持 <b>中文 / 拼音 / 首字</b> 搜索(可与分类叠加); 选中某 NPC 后右侧显示其 SellItems 现有卖品
   (名称/数量); 点「<b>添加卖品…</b>」从 道具名.json 搜索(中文/拼音/首字/数字)或<b>多选</b>一次添加多个
   (数量默认 <b>999</b>, 可在框内改), 与已有同名道具自动跳过, 不重复; 点「保存/另存为/复制结果」时随存档一起写回。

<h3>写入规律(与游戏存档一致)</h3>
每个道具重建为固定 5 字段, 例如「2纯铜矿」×9999:<br>
<pre>},"2纯铜矿":{
    "_DressType" : 1,
    "_Count" : 9999,
    "_Name" : "2纯铜矿",
    "_LockHp" : 0,
    "_GetTimeNew" : 0</pre>
其中: 道具名既是字典键也是 _Name 值; 已有道具的 _DressType / _LockHp / _GetTimeNew 保留原值,
新增道具分别记 1 / 0 / 0。其余段落(装备/武功/地图等)逐字节保留。
名字含中文弯引号(如 碎“肉”、剑令“地绝”)时, 写入会自动把 “ ” 转义成 \“ \”(与游戏存档一致),
读回自动还原为干净名, 因此可正常搜索/添加这类特殊道具(共 6 个)。

<h3>道具名库(程序目录/道具名.json)</h3>
- 每次「打开/粘贴/重新读取」读档, 会自动把 ItemHad 段道具名与库比对, 新名去重收录到 道具名.json(不重名)。<br>
- <b>一键整理道具列表</b>: 把当前存档(表格)里已有的道具名即时补入 道具名.json——缺失的新增、已收录的跳过
  (手动新增/改名自定义道具名后点它, 即可把最新道具名同步进 json)。<br>
- <b>一键添加全部道具</b>: 把道具名库中当前列表还没有的道具一次性加入(每个数量 9999), 便于补全所有道具。

<h3>建议</h3>
修改前请先备份原存档; 修改后如进游戏报错, 用备份还原即可。
""" % __version__


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    ic = app_icon()
    if not ic.isNull():
        QApplication.setWindowIcon(ic)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
