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

版本: v1.3.0 (2026-09-03)

新增(v1.3.0): 「打开上次」+「最近 ▾」历史一键重开上次/历史文件(历史记录.json);
            「重新读取」在游戏再次存档后重新读取当前文件内容(有未保存修改先询问)。
"""
import json
import os
import re
import sys

__version__ = "1.9.0"
APP_NAME = "灵兽江湖存档修改器"

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QToolBar, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QDialog, QLineEdit, QSpinBox, QPlainTextEdit,
    QDialogButtonBox, QFileDialog, QMenu, QMessageBox, QToolButton,
    QCheckBox, QComboBox, QListWidget, QListWidgetItem, QStatusBar,
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


def find_itemhad_line(lines):
    """返回包含 `"ItemHad" :` 的行索引; 找不到返回 -1。
    用带引号的完整键名匹配, 可避免误命中 "ItemHadTemp" 等前缀相似的段。"""
    for i, ln in enumerate(lines):
        if re.search(r'"ItemHad"\s*:', ln):
            return i
    return -1


def parse_itemhad(lines, start_idx):
    """解析 ItemHad 段。

    返回 (items, indent, close_idx); 解析失败返回 (None, None, None)。
      items     : list[Es3Item], 按文件中出现顺序
      indent    : dict, 记录段头前缀/字段缩进/物品闭合缩进/段尾行, 供原样重建
      close_idx : 段尾 `},` 所在行索引(含)
    """
    header = lines[start_idx]
    m = re.search(r'"ItemHad"\s*:\s*\{', header)
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

    # 第一件物品的头内联在 ItemHad 行: "ItemHad" : {"铜钱":{
    # 注意: 前面 regex 已把开头的 `{` 吞进匹配, 故此处从物品名引号开始匹配
    m1 = re.search(r'"([^"{}]+)":\{', suffix)
    if m1:
        cur = Es3Item(m1.group(1))
    else:
        # 空段且同一行闭合 "ItemHad" : {} 的情况
        if re.search(r'"ItemHad"\s*:\s*\{\s*\}', header):
            leading = header[:header.find('"ItemHad"')]
            indent["section_close"] = leading + "},\n"
            return [], indent, start_idx
        # 空段分多行: "ItemHad" : {\n},\n —— 交给主循环找 '},' 闭合
        cur = None

    close_idx = None
    i = start_idx + 1
    n = len(lines)
    while i < n:
        ln = lines[i]
        ln_s = ln.rstrip("\r\n")  # 兼容 CRLF/LF
        # 段尾闭合(空段或多行空段的 '},')
        if re.match(r'^\s*\},$', ln_s):
            indent["section_close"] = ln
            close_idx = i
            if cur is not None:
                items.append(cur)
            break
        # 新物品头: },"名称":{   (同时闭合上一物品)
        m2 = re.match(r'^\s*\},"([^"{}]+)":\{', ln)
        if m2:
            if cur is not None:
                items.append(cur)
            indent["close_indent"] = ln[:ln.index('}')]
            cur = Es3Item(m2.group(1))
            i += 1
            continue
        # 最后一件物品闭合: '}'
        if re.match(r'^\s*\}$', ln_s):
            if cur is not None:
                items.append(cur)
            indent["close_indent"] = ln[:ln.index('}')]
            # 其后应紧跟段尾 '},'
            j = i + 1
            while j < n:
                lj = lines[j]
                if re.match(r'^\s*\},$', lj.rstrip("\r\n")):
                    indent["section_close"] = lj
                    close_idx = j
                    break
                elif lj.strip():
                    break
                j += 1
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
    out.append(header_prefix + '"%s":{' % items[0].name + newline)
    for k, it in enumerate(items):
        if k > 0:
            out.append(close + '},"%s":{' % it.name + newline)
        dt = it.dress_type if it.dress_type is not None else 1
        lh = it.lock_hp if it.lock_hp is not None else 0
        gt = it.get_time if it.get_time is not None else 0
        out.append(body + '"_DressType" : %s,' % dt + newline)
        out.append(body + '"_Count" : %d,' % int(it.count) + newline)
        out.append(body + '"_Name" : "%s",' % it.name + newline)
        out.append(body + '"_LockHp" : %s,' % lh + newline)
        out.append(body + '"_GetTimeNew" : %s' % gt + newline)
    out.append(close + '}' + newline)
    out.append(sec)
    return out


def apply_itemhad_text(text, items, newline=None):
    """把新物品列表写回完整 es3 文本(仅替换 ItemHad 段)。

    text  : 完整 es3 文本
    items : list[Es3Item] 新的物品列表
    返回  : 重建后的完整文本; 其它段落逐字节保留。
    """
    lines = text.splitlines(keepends=True)
    start_idx = find_itemhad_line(lines)
    if start_idx < 0:
        raise ValueError("未找到 ItemHad 段")
    parsed, indent, close_idx = parse_itemhad(lines, start_idx)
    if close_idx is None:
        raise ValueError("ItemHad 段解析失败")
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
    """读取道具名库(JSON 字符串数组); 失败返回空列表。"""
    path = path or get_item_names_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [str(x).strip() for x in data if str(x).strip()]


def save_item_names(names, path=None):
    """把道具名去重、排序后原子写入 JSON; 返回写入后的列表。"""
    path = path or get_item_names_path()
    clean = sorted({n.strip() for n in names if n.strip()})
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


# ============================ 拼音搜索(拼音表.json, 运行时不依赖第三方库) ============================

def get_pinyin_map_path():
    """拼音映射文件路径: 程序目录/拼音表.json({汉字: 拼音...})。"""
    return os.path.join(app_dir(), "拼音表.json")


def load_pinyin_map(path=None):
    """读取 拼音表.json → {汉字: [拼音列表]}; 缺失/损坏返回 {}。"""
    path = path or get_pinyin_map_path()
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


# ============================ GUI 层 ============================

class AddItemDialog(QDialog):
    """新增道具对话框: 从 道具名.json 搜索/多选添加, 也可直接输入自定义名。

    搜索支持 中文 / 拼音全拼 / 拼音首字母 / 数字(见 filter_item_names);
    列表可 Ctrl/Shift 多选、全选; 已在当前列表中的名字灰显不可选; 双击或回车=加单项。
    """

    def __init__(self, parent=None, existing=None, default_name="", default_count=9999):
        super().__init__(parent)
        self._existing = set(existing or ())
        self._pmap = load_pinyin_map()
        self._chosen = None          # 双击/回车确定的单项; None 时按“多选/自定义”取
        self.setWindowTitle("新增道具")
        self.setMinimumSize(560, 520)
        root = QVBoxLayout(self)

        # 顶部: 搜索/输入 + 匹配方式
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
        root.addLayout(top)

        # 中间: 候选列表(来自 道具名.json)
        self.item_list = QListWidget()
        self.item_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.item_list.itemSelectionChanged.connect(self._update_stat)
        self.item_list.itemDoubleClicked.connect(self._on_double)
        self.item_list.setToolTip("可按住 Ctrl/Shift 多选; 双击某项 = 直接添加该项")
        root.addWidget(self.item_list, 1)

        # 工具行: 仅显示缺少 / 全选 / 清空选择 + 统计
        mid = QHBoxLayout()
        self.only_missing_check = QCheckBox("仅显示缺少(未在个人背包)")
        self.only_missing_check.setToolTip(
            "勾选后只列出 道具名.json 里你当前个人背包还没有的道具, 便于全选一次补齐")
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

        # 数量
        cnt = QHBoxLayout()
        cnt.addWidget(QLabel("数量(本次新增道具统一):"))
        self.count_spin = QSpinBox()
        self.count_spin.setRange(0, 999999999)
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

        # 候选数据: 道具名库全部名字(去重, 顺序不变)
        self._all_names = list(dict.fromkeys(load_item_names()))
        self._refresh_list()

    # ---------------- 内部 ----------------
    def _missing_names(self):
        """道具名.json 里个人背包(当前列表)还没有的名字, 即“缺少的道具”。"""
        return [n for n in self._all_names if n not in self._existing]

    def _filtered(self):
        names = filter_item_names(self._all_names, self.search.text(),
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
        total = len(self._all_names)
        miss = len(self._missing_names())
        sel = len(self.item_list.selectedItems())
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
        # 设置: 批量改为的目标值(持久保存, 重开仍保留)
        self._settings = load_app_settings()
        try:
            self._batch_value = int(self._settings.get("batch_value", 9999))
        except (TypeError, ValueError):
            self._batch_value = 9999
        self._batch_value = max(0, min(self._batch_value, 999999999))
        self._settings_save_timer = QTimer(self)   # 500ms 防抖自动保存
        self._settings_save_timer.setSingleShot(True)
        self._settings_save_timer.setInterval(500)
        self._settings_save_timer.timeout.connect(self._save_settings_now)
        self.setWindowTitle("%s v%s" % (APP_NAME, __version__))
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

        self.src_label = QLabel("源: 未打开(可点「粘贴」直接粘贴存档内容)")
        self.src_label.setWordWrap(True)
        root.addWidget(self.src_label)

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
        root.addWidget(self.table, 1)

        row1 = QHBoxLayout()
        self.btn_9999 = QPushButton("全部改为 %d" % self._batch_value)
        self.btn_9999.clicked.connect(self._on_set_all_9999)
        self.btn_9999.setToolTip("按记住的目标值一键批量改(可在右侧数字框改成任意数值, 会自动保存)")
        self.skip_copper_check = QCheckBox("跳过「铜钱」")
        self.skip_copper_check.setChecked(True)
        self.all_spin = QSpinBox()
        self.all_spin.setRange(0, 999999999)
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
        root.addLayout(row1)

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
        root.addLayout(row2)

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

    def _reload_table(self):
        self._loading = True
        self.table.setRowCount(len(self._items))
        for r, it in enumerate(self._items):
            i0 = QTableWidgetItem(str(r + 1))
            i0.setFlags(i0.flags() & ~Qt.ItemFlag.ItemIsEditable)
            i0.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            i1 = QTableWidgetItem(it.name)
            i2 = QTableWidgetItem(str(it.count))
            i2.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(r, 0, i0)
            self.table.setItem(r, 1, i1)
            self.table.setItem(r, 2, i2)
        self._loading = False
        self.count_label.setText("道具总数: %d" % len(self._items))

    def _on_item_changed(self, item):
        if self._loading or self._suppress_change:
            return
        row, col = item.row(), item.column()
        if row < 0 or row >= len(self._items):
            return
        if col == 1:  # 名称
            new_name = item.text().strip()
            ok, err = validate_item_name(new_name)
            if not ok:
                self._suppress_change = True
                item.setText(self._items[row].name)
                self._suppress_change = False
                self.statusBar().showMessage(err, 3000)
                return
            for k, it in enumerate(self._items):
                if k != row and it.name == new_name:
                    self._suppress_change = True
                    item.setText(self._items[row].name)
                    self._suppress_change = False
                    self.statusBar().showMessage("道具名称重复: %s" % new_name, 3000)
                    return
            if self._items[row].name != new_name:
                self._mark_dirty()
            self._items[row].name = new_name
            self.statusBar().showMessage("已修改名称 -> %s" % new_name, 2000)
        elif col == 2:  # 数量
            txt = item.text().strip()
            try:
                v = int(txt)
            except ValueError:
                v = -1
            if v < 0 or v > 999999999:
                self._suppress_change = True
                item.setText(str(self._items[row].count))
                self._suppress_change = False
                self.statusBar().showMessage("数量必须是 0~999999999 的整数", 3000)
                return
            if self._items[row].count != v:
                self._mark_dirty()
            self._items[row].count = v
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

    def _open_path(self, path, record=True):
        """打开指定路径的存档文件: 读取 -> 解析 -> 刷新表格。

        record=True 时, 成功打开会记入「最近打开」历史(最新在前);
        文件不存在时会从历史中移除该条。返回是否成功。
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
        if not self._load_text(text, bom):
            return False
        self._file_path = path
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
        if self._load_text(text):
            self.src_label.setText("源: 粘贴内容(未保存为文件)")
            self.statusBar().showMessage(
                self._lib_status("已解析粘贴内容 · 共 %d 个道具" % len(self._items)), 4000)

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
        try:
            new_text = self._generate()
            write_es3_text(self._file_path, new_text, self._bom)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "错误", "保存失败:\n%s" % e)
            return
        self._text = new_text
        self._mark_clean()
        self.statusBar().showMessage("已保存到 %s" % self._file_path, 3000)

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
        try:
            new_text = self._generate()
            write_es3_text(path, new_text, self._bom)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "错误", "写入文件失败:\n%s" % e)
            return
        self._text = new_text
        self._file_path = path
        self._mark_clean()
        self.src_label.setText("源: %s" % path)
        self.statusBar().showMessage("已另存为 %s" % path, 3000)

    def _on_copy(self):
        if self._text is None:
            QMessageBox.warning(self, "提示", "请先打开或粘贴存档内容")
            return
        try:
            new_text = self._generate()
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "错误", "生成内容失败:\n%s" % e)
            return
        QApplication.clipboard().setText(new_text)
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
        self._reload_table()
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
            self._reload_table()
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
        rows = sorted({i.row() for i in self.table.selectedItems()}, reverse=True)
        if not rows:
            QMessageBox.information(self, "提示", "请先选中要删除的道具(可按住 Ctrl 多选)")
            return
        names = [self._items[r].name for r in rows]
        if QMessageBox.question(self, "确认删除", "确定删除 %d 个道具?\n%s"
                                % (len(rows), "、".join(names))) != QMessageBox.StandardButton.Yes:
            return
        for r in rows:
            del self._items[r]
        self._reload_table()
        self._mark_dirty()
        self.statusBar().showMessage("已删除 %d 个道具" % len(rows), 3000)

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
        self._reload_table()
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
3. <b>全部改为 9999</b>: 一键按目标值批量改(可勾选「跳过铜钱」保留铜钱原值); 目标值可在右侧
   「全部改为:」数字框改成任意数值后点「全部改为」——改后程序会<b>自动记住</b>, 左侧按钮文字同步
   显示该值, 重开程序仍保留(设置存 程序目录/设置.json)。
4. <b>新增道具</b>: 打开选择窗口, 从 <b>道具名.json</b> 的全部道具名中 <b>搜索</b>(支持中文、
   拼音全拼、拼音首字母、数字, 如输入 tq / tongqian 找 铜钱; 顶部可切「仅中文 / 仅拼音」)
   并 <b>多选 / 全选</b> 一次添加多个(数量统一); 也可在搜索框直接输入自定义道具名后回车;
   勾选 <b>仅显示缺少(未在个人背包)</b> 即自动跟 道具名.json 比对, 只列出你个人背包还缺的
   道具(底部实时显示 库总数/个人已有/缺少/已选), 配合「全选」即可一次补齐全部缺少的道具;
   <b>删除选中</b>: 删除选中行。
5. <b>保存</b>: 写回原文件; <b>另存为</b>: 存成新文件; <b>复制结果</b>: 把修改后的完整
   内容复制到剪贴板(配合「粘贴」流程使用)。
6. <b>重新读取</b>: 打开文件后若回到游戏又存了档(游戏把文件更新了), 点「重新读取」
   即可再次读取当前文件内容、刷新表格; 若内存里还有未保存的修改, 会先询问是否丢弃。

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
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
