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

版本: v2.13.2 (2026-09-16)

版本: v2.13.3 (2026-09-16)

版本: v2.14.0 (2026-09-16)

版本: v2.14.1 (2026-09-16)

版本: v2.14.2 (2026-09-16)

版本: v2.14.3 (2026-09-16)

版本: v2.14.4 (2026-09-16)

版本: v2.14.5 (2026-09-17)

版本: v2.15.0 (2026-09-17)

新增(v2.15.0 功法黑名单): 用户反馈「部分功法一学就卡死」, 要求能先避开已知的 —— 新增**功法黑名单**
            (工具栏「功法黑名单…」): 列入的功法 ① 「＋ 添加功法…」候选里**完全不显示**,
            ② 主角/队友都不会被添加(手动输入/自定义名也会被主窗拦下并提示),
            ③ 已学列表悬停会标「★ 这门功法在黑名单里」。管理框支持 从功法库批量加入(分类树+搜索+多选/全选,
            已加入的灰显)、批量移出(多选)、清空全部、逐条写**备注**(记卡死现象/猜测原因, 方便以后
            逐条验证是「剧情还没到」还是别的原因), 改动**即时写盘**。数据存程序目录 `功法黑名单.json`
            (程序级, 与存档无关, 换档/重开都生效; 兼容手写的 ["名1","名2"] 简写形式, 损坏/缺失当空)。
            纯函数: `get_kangfu_blacklist_path`/`load_kangfu_blacklist`/`save_kangfu_blacklist`(原子写)/
            `kangfu_blacklist_keys`(归一化名集合)/`filter_cat_data`(复制分类库并剔除黑名单 —— 分类树计数
            与右侧候选同时生效, 不动 _CAT_CACHE); `AddItemDialog` 新增 `hidden_names`(完全不显示的名字,
            含平铺回退过滤与 `_filtered` 兜底 + 统计文案「已隐藏黑名单 N 门」), `KangFuDialog` 透传。
            核心 271/271(新增 15 条)、GUI 313/313(新增 23 条)、e2e 50/50 与 16/16。

新增(v2.14.5 多线程/UI 响应性全面优化): 用户要求「多线程全面优化, 并写进 md 作为后续强制约定」。
            先用新增基准 `_scaffold/bench_ui_ops.py`(offscreen, 真实 8.6MB 档只读)对**全部 GUI 入口**
            逐项计时, 发现真正压在**主线程**上的耗时并逐一根治:
            ① **结构索引加「同型括号配对表」(`_brace_pairs`, 建索引时栈一次算出)**: `_matching_end`
              从「从起点扫到闭括号」变成 **O(1) 查表**(实测大容器 200ms → 0.3ms),
              `_entry_values` 能整块跳过子容器、只遍历顶层字段(大容器 200ms → 18ms) —— 这是
              「打开大档 6 秒」「商店/商店刷新卡一下」的底层根源; 配对表缺失/异常时自动退回原逐
              token/全括号计数实现(语义完全一致)。`_apply_subs` 的索引打补丁同步重建配对表。
            ② **编辑后异步预热索引**: `_mark_dirty` 里 `_preheat_index_async(self._text)` —— 改动后
              新文本的整档索引在后台线程建好(8.6MB 档冷建 ~1.3s), 否则用户「改完角色属性再去点
              商店/地图」就会在主线程冷建而卡一下(实测地图页首次刷新 1.3s 就是这么来的)。
            ③ **字段名唯一的读取走 fast 定位**: 新增 `_unique_field_open`(str.find + 局部括号配平
              `_local_span_end`, 不经整档索引), `get_str_array`/`add_str_array`/`remove_str_array`
              先用它 —— `_ActiveMap` 这类字段全档只出现一次时, `_locate_container(SCOPE_MAP)` 要逐层
              扫大容器(实测 1.7s) → 现在地图刷新/增删 22ms。
            ④ **主线程构建分块 + 进度泵**: 新增 `_pump(msg)`(更新状态栏进度 + `processEvents`,
              期间临时禁用中央区与工具栏防重入); `_reload_table(progress=…)` 大表每 400 行泵一次
              (仅在打开大档这种长流程里传 progress, 普通重建保持最快), `_apply_char_model(progress=True)`
              每 2 页泵一次(状态栏「正在构建角色页 5/23: 队友·xx…」) —— 打开过程中窗口不再假死。
            ⑤ **更多重活后台化**: `_refresh_shop_tab(cache=None)` 大档改走 `_run_bg` 算商店记录、
              店铺列表改批量 `addItems`+后置 `setData`; `_refresh_equip_tab(model=None)`(装备模型
              1.5s)、`_refresh_chong_tab(model=None)`、`_on_organize_names`(道具名库整理) 均改后台;
              `chong_list`/`equip_name_list` 批量建项。
            实测(真实 8.6MB 档): 打开端到端 10.7s → **7.3s**、主线程冻结 5.5s → ~3.3s 且全程有进度;
            `char_model` 6.9s → 2.9s(后台)、地图刷新 1.34s → 0.02s、装备页刷新 366ms → 36ms、
            道具名库整理 174ms → 66ms、大容器扫描 200ms → 18ms。
            核心 256/256、GUI 290/290、`_scaffold/e2e_kangfu.py` 50/50、`_scaffold/e2e_chong_equip.py` 16/16
            (真实档增删往返逐字节一致, 验证配对表改造未改变任何语义)。

新增(v2.14.4 大量添加道具/功法不再卡): 用户反馈「大量添加道具、功法的时候会很卡」——实测(真实
            8.6MB 档 custom0.es3)定位到三处主线程瓶颈并逐一根治:
            ① **对话框「全选」26 秒 → 50 毫秒**(主因): `AddItemDialog._select_all` 原来逐行
              `setSelected(True)`, 每行都触发 itemSelectionChanged → `_update_stat`(每次 O(名库)
              统计 ~3ms), 4565 行的名库上实测 25.9 秒。现改为「连续可选行合并成区间 → 一次性
              `QItemSelection` 提交给 selectionModel」(`_select_enabled_items`), 并用上下文管理器
              `_BulkListEdit` 屏蔽信号 + 暂停重绘, 末尾只刷一次统计; `_select_none`/`_refresh_list`
              /MapJumpDialog 同样处理; 「缺少的道具」结果加缓存(`_missing_names`)。
            ② **添加道具后不再整表重建**: 新增 `_append_rows_local(start)` 只追加新增行, 4000 行的表
              重建 1.1~1.4s → 追加 500 行 0.10s、一键添加全部 4879 个 1.47s → 0.34s; 有搜索过滤时
              仍走“清搜索 + 整表重建”保正确性。
            ③ **功法添加更快**: `kangfu_add` 原来每加一条都重扫整个功法段并整段拼接(O(k²)), 现先拼好
              整块再一次性插入(一次加 300 门 = 220ms); 添加/删除后要重算的列表与已装备信息
              (`kangfu_brief`/`kangfu_dressed`) 移进后台 `_run_bg` 的 worker, 主线程只填列表; 点
              「＋ 添加功法…」时优先复用角色页已算好的缓存(不再每次重扫整档 ~0.45s)。
            核心 256/256、GUI 290/290(新增 6 条性能回归守卫: 全选 1200 行 < 1.5s、统计已刷新、
            清空选择 < 0.5s、全选只选可选行(灰显不选中)、追加 800 行 < 1.5s、追加后行号/计数正确)、
            `_scaffold/e2e_kangfu.py` 50/50、`_scaffold/e2e_chong_equip.py` 16/16。
            基准脚本 `_scaffold/bench_bulk_add.py`(offscreen, 真实档只读)可复测各环节耗时。

新增(v2.14.3 功法等级即时保存): **「添加功法…」对话框的等级框一变就立即写盘**(用户反馈: 不用等
            点确定才记住, 应该输入完就保存供下次使用)。实现: `KangFuDialog` 新增可选回调
            `on_lv_changed`, 构造里把它接到 `count_spin.valueChanged`(`_lv_changed` 直接就回调;
            构造时 `setValue(default_lv)` 发生在 connect 之前, 不会误触发); 主窗新增
            `_remember_kangfu_lv(val)` —— clamp 后与 `self._kangfu_lv` 比较, 变了就**立即
            `_save_settings_now()`**(设置.json 是小文件原子写, 代价极低; 不再用 500ms 防抖,
            避免用户改完立刻关程序丢掉)。于是点「取消」也已记住本次改的值。
            对话框标签改为「等级 _Lv(新增功法的等级; 改一下就记住, 下次打开还是它)」,
            功法区悬停提示与帮助文档措辞同步。核心 256/256、GUI 283/283(新增 4 条:
            「改一下就立即记住(随后点取消也记住)」/「等级已立即写入 设置.json」/
            「真实对话框构造时不误触发回调」/「真实对话框改等级即时回调」)、
            真实 7.9MB 档端到端 `_scaffold/e2e_kangfu.py` 50/50、
            `_scaffold/e2e_chong_equip.py` 16/16。

新增(v2.14.2 功法等级持久记忆): **「添加功法…」对话框里的「等级 _Lv」改过就记住**(用户反馈:
            每次都要手动改, 很烦)。与「批量目标值」「新增蛊虫默认值」同款做法: 存 设置.json 的
            `kangfu_lv` 键, `MainWindow.__init__` 读入到 `self._kangfu_lv`(clamp 到 0..MAX_ITEM_COUNT,
            坏值回退 `KANGFU_DEFAULT_LV`=1), 添加时作 `KangFuDialog(default_lv=self._kangfu_lv)` 的默认值,
            对话框确定后若值变了就更新 `self._kangfu_lv` 并 `_autosave_settings()`(500ms 防抖写盘),
            `_save_settings_now` 同步写入; 取消对话框则不记。(→ **v2.14.3 改为「等级框一变就立即
            `_save_settings_now()`」, 点取消也已记住, 不再用防抖**)
            对话框标签也改为
            「等级 _Lv(新增功法的等级; 改过会记住, 下次打开还是它)」, 功法区「＋ 添加功法…」的
            悬停提示同步说明。GUI 冒烟新增 5 条(默认等级=记住值 / 改后被记住 / 落到 设置.json
            的 kangfu_lv / 重开程序后恢复 / 重开后对话框默认等级也是它)。
            另: `_scaffold/e2e_kangfu.py` 与 `smoke_test.py` 的真实档用例改为**不依赖「库里还有未学过的
            功法」**——本工具用户可能把角色学到接近全库(实测见到主角 998/1045 门、某队友 1003 门),
            原「挑一门未学功法来添加」的写法会选不出名字; 现在主角/队友用例会逐个找合适的角色并容错,
            并新增「删一门已有功法 → 按库归属加回(等级 7) → 再删掉」的通用往返验证。
            核心 256/256、GUI 279/279、真实 7.9MB 档端到端 `_scaffold/e2e_kangfu.py` 50/50。

新增(v2.14.1 已装备的功法不再重复添加): **添加功法时会检查该角色「已装备」的功法, 已装备的一律跳过**。
            用户反馈: 已装备的功法若被重复添加, 会变成同名的两份, 游戏里这门功法就卸不下来。
            实测确认结构(主角字段无前缀 / 队友多一个下划线):
              `DressInKangFuName` 当前装备的内功名(字符串, 没装备时为 null)
              `DressInKangFu`     当前装备的内功对象: `_Name` / `_DressKangFu[]`(已装备的武功) /
                                  `_DressQuickKangFu{1:""…10:""}`(已装备的快捷武功) /
                                  `_DressKangFuQing`(已装备的轻功) / `_DressBigLoop[]` / `_DressSmallLoop[]`
              `DressKangFu` / `DressQuickKangFu` / `DressKangFuQing` 角色下已装备的武功/快捷槽/轻功
            **关键实测: 这些已装备的名字通常不在 InKangFuHad/KangFuHad/KangFuSkillHad/KangFuQingHad 段里**
            (前 5 名角色的 19 个装备名里 0 个出现在对应段内; 全档 18 名队友共 52 个装备名逐个试写也全部不在段中),
            所以原有的「已学过去重」拦不住它们 —— 必须单独读装备字段排除。
            实现: 新增纯函数 `kangfu_dressed(text, container_open)` → `(已装备内功名 or None, {归一化名: 原名})`
            (只扫角色容器**直接**的 `Dress*KangFu*` 字段并取其中的字符串, 空串/纯英文键名(_Lv/_Name/_DressType…)
            不误收; 一次顶层扫描, 很轻); `kangfu_add(...)` 新增 `dressed` 参数(None=内部自动读)并把命中的
            名字与「已学过」一样归入 skipped; `char_model` 的 player/friends 各增 `dressed` 字段(随大档后台线程收集);
            GUI: 添加对话框的 existing 里并入已装备名(灰显)并新增 `existing_tips` 支持 —— 已装备项的鼠标悬停提示
            写明「该角色已装备此功法, 不能重复添加…否则卸不下来」(`AddItemDialog` 增 `existing_tips`,
            `KangFuDialog` 增 `dressed` 参数自动生成提示); 功法区右侧计数改为「已学 N 门 … · 已装备内功: X ·
            已装备功法 M 门(不能重复添加)」, 列表 tooltip 也会标注「当前已装备」; 状态栏把跳过原因拆成
            「已学过自动跳过」与「已装备跳过(同名两份会卸不下来)」; 区里的说明文字与帮助文档同步补上这段规律。
            核心 **256/256**(新增 8 条已装备用例 + 真实档逐队友验证)、GUI **274/274**(新增 5 条)、
            真实 7.9MB 档端到端 `_scaffold/e2e_kangfu.py` **59/59**(含「18 名队友 52 次试写装备名全部写不进去」)。

新增(v2.14.0 功法: 内功/武功/绝技/轻功四段增删): **主角页与每个队友页新增「功法」分组 —— 可批量/
            多选添加或删除该角色已学的功法**。用户观察到的四个段与「不同功法放不同位置」已逐条实测确认:
            <b>InKangFuHad(内功)</b> / <b>KangFuHad(武功)</b> / <b>KangFuSkillHad(绝技)</b> /
            <b>KangFuQingHad(轻功)</b>, 队友的同名段前面多一个下划线(_InKangFuHad / _KangFuHad /
            _KangFuSkillHad / _KangFuQingHad)。
            **判定规律(关键结论): 一门功法进哪一段**只取决于它在游戏数据集里属哪一支**, 与名字无关:
              dataset/kangfu/inkangfu/*          → InKangFuHad      内功(200)
              dataset/kangfu/kangfu/*            → KangFuHad        武功(595)
              dataset/kangfu/uniqueskill/jue/*   → KangFuSkillHad   绝技(177)
              dataset/kangfu/uniqueskill/qing/*  → KangFuQingHad    轻功(73)
            实测 custom0.es3: 主角 KangFuHad 里 211 条名字 100% 落在 dataset/kangfu/kangfu/*;
            KangFuSkillHad 85 条 100% 落在 uniqueskill/jue/*; KangFuQingHad 54 条 100% 落在
            uniqueskill/qing/*; InKangFuHad 66 条 100% 落在 inkangfu/*(无一例外、无跳段)。
            所以本程序**按名字查库自动判定段**再写入, 不会放错; 删/读也同样按段定位。
            新增数据文件 **功法名.json**(1045 门, 由新增 `_scaffold/build_kangfu_names.py` 从
            内存所有道具.json 的 分类.kangfu 生成, 结构同 道具分类.json): 四大类=四段, 每类下按
            来源/门派细分(百灵御/必报山庄/BOSS/皇羽谷/江湖/昆仑神教/鲲鹏教/破道天宫/穹空派/七曜宫/五子寺,
            门派中文名取自 内存采集到的中文内容.json 的门派字样)。
            GUI: 主角页/队友页各新增 `_add_kangfu_section`(QGroupBox「功法(内功/武功/绝技/轻功)」) ——
            列表逐条显示 `[内功]/[武功]/[绝技]/[轻功] 名字`(行首就是所在的段)、顶部计数「已学 N 门 武功X/绝技Y」;
            「＋ 添加功法…」弹 `KangFuDialog`(继承 AddItemDialog, 复用分类树/搜索/多选/全选,「等级 _Lv」用数量框,
            已会的灰显跳过); 「－ 删除选中」多选删除并按「段+名字」精确定位。所有写回走 `_run_bg` 后台线程。
            纯函数(模块级, 便于测试/无 GUI 复用): `kangfu_index`/`kangfu_seg_of_name`(名字→段)、
            `_kangfu_field_open`(在角色容器内定位段, 兼容 _ 前缀)、`_kangfu_entries`(段内条目枚举)、
            `kangfu_records`/`kangfu_brief`、`kangfu_add`(按段分组的局部插入 + 一次性 `_apply_subs`)、
            `kangfu_del`(末条带前逗号/非末条带后逗号地删, 段删空变回 `{\n<缩进>}` 空字典)。
            新增条目的字段模板与实操档逐字节一致(内功 8 字段含 _DressQuickKangFu{1:""..10:""};
            武功 6 字段含 _Exp/_AddLv/HaveShanHaiLu; 绝技/轻功 3 字段)。
            核心 247/247(新增 33 条)、GUI 269/269(新增 19 条)、真实 7.9MB 档端到端 62/62
            (含「增删往返后与原档逐字节一致」「删空→空字典→再添加→再删除一致」等无损校验)。

新增(v2.13.3 技能库只留战斗类): **装备与蛊虫的技能候选排除「生活技能/工具/测试未整理」**。
            技能名.json 原本是 内存所有道具.json 的 dataset/skill 全量(370 条, 含 lifeperkskilltesk
            生活技能天赋 45 / totest 测试未整理 44 / tool 工具 4), 这些名字既不能当被动技能挂,
            也不是战斗效果, 列在候选里只会干扰选择。现改为**只保留 pass(被动/战斗) 与 todu(特殊/临时)
            两组, 共 277 条**。两道保险: ① `_scaffold/build_skill_names.py` 用白名单 KEEP_SUBS=("pass","todu")
            重新生成 技能名.json(2.0: 277 条, 排除项在生成时直接丢弃并打印统计); ② 主程序新增常量
            `SKILL_KEEP_SUBS`/`SKILL_EXCLUDED_SUBS` 并在**读取入口** `load_skill_categories()` 里过滤
            (结果缓存到 `_SKILL_CAT_CACHE`)——这样即便旧版 json 或以后重新生成混入也不会漏到候选。
            影响面: 蛊虫页 _Skill/_Preference 的「＋ 添加状态…」「本只/批量：写入全部技能库」与装备页
            「＋ 添加技能…」的候选(均走 `load_skill_names()`), 以及新增蛊虫对话框的「写入全部技能库」;
            界面文案里写死的「370 项」改为动态数量(新增 `skill_lib_count()`)或描述性说明。
            **存档里已存在的技能(哪怕是被排除类的名字)读取/修改/删除完全不受影响**——排除只作用于候选列表。
            核心 214/214、GUI 250/250。

新增(v2.13.2 装备页改名+逐件列出+增删): **①「装备技能」页签改名为「装备」**(它就是主角的装备清单,
            技能只是装备的一部分属性)。②左侧由「装备名(1 件)」改为**逐件列出**: 同名的多件拆成多行,
            显示 `名字 #序号`, 点哪一行就是哪一件(右侧实例表/技能表即时切到该件), 不再出现「(N 件)」
            这类汇总括号; 顶部计数改为「装备: N 件 · M 种」。③新增 **「＋ 添加装备…」**(复用装备类选择
            对话框, 只列 equip 类; 装备可同名不堆叠, 「件数」= 加几个同名实例) 与 **「－ 删除选中」**
            (可 Ctrl/Shift 多选; 删的是选中的具体某一件, 某名字的最后一件被删时整个条目一并移除;
            全部删光后 EquipHad 变回空字典)。④纯函数新增 `player_equip_entries`(枚举条目: 干净名 +
            键起点 + 数组括号)/`player_del_equips`(按「保留条目原文」重建整段 —— 条目间的原文分隔
            `,\r\n\t\t` 与末条目到 `}` 之间的缩进都原样保留, 其余段落逐字节不动); 修正
            `_on_equip_name_selected` 旧 bug(原来固定把当前实例设为首件, 点重名的第 2 件会看/改到第 1 件)。
            核心 208/208、GUI 247/247。

新增(v2.13.1 默认值+状态灯): **①蛊虫默认值改 9999 + 培养上限可一键**——三项属性 Power/Agility/
            PhysicalPower 的一键默认值由 999 改 **9999**(单只「默认」「本只：三项属性一键」与
            批量「力道/灵气/体魄 =」的数字框默认值全部同步), 新增蛊虫对话框的三项属性默认值也是 9999;
            新增蛊虫的 _FosterMax(培养上限) 默认由 5 改 **9999**, 且属性页新增「默认 9999」按钮与
            「本只：培养上限一键 = 9999」, 批量页新增「培养上限 _FosterMax —— 全部蛊虫」一组
            (目标值框 + 「培养上限 =」+「默认 9999」), 新增蛊虫对话框里也可单独设培养上限并会被记住;
            改培养上限不动 _TotalProperty(只有改三项属性才写 0)。
            **②工具栏状态指示灯**——「打开」按钮左边新增一个圆点(纯展示, 不接收焦点), 颜色直观看当前
            文档状态: <b>绿=已保存 / 红=未保存 / 黄=正在刷新 / 蓝=已刷新 / 灰=未打开</b>(鼠标悬停有颜色
            图例), 与窗口标题里的状态文字同步(都在 `_refresh_title` 里刷新, 故保存/另存/粘贴/重新读取/
            自动刷新/关闭文档全部即时变色)。核心 196/196、GUI 240/240。

新增(v2.13.0 蛊虫+装备技能): **新增「蛊虫(ChongHad)」与「装备技能(EquipHad)」两个页签**。
            ①蛊虫页: 左侧列出存档 ChongHad 的蛊虫, 右侧分「属性 / 技能 _Skill / 偏好 _Preference /
            批量(全部蛊虫)」四页——可改 显示名/_Love/培养值/培养上限 与三项属性 力道 Power/灵气 Agility/
            体魄 PhysicalPower(默认 999, 可自定义), **改这三项后自动把 _TotalProperty 写 0**(游戏会重算,
            留旧值容易出错); _Skill(状态累积值, 如 "着火":500)/_Preference(状态倍率, 1.1=110%) 可逐条改、
            一键 9999 或自定义值, 可一键「补齐全部状态(5 种)」或「写入全部技能库」(v2.13.3 起只含
            pass+todu 共 277 条, 见上一条);
            可批量对全部蛊虫一次性设置, 也可新增(蛊虫名库 108 只, 不堆叠:「只数」= 加几条独立条目,
            同装备; 新增时能设三项属性默认值与技能/偏好默认值, 并可选写全部状态/全部技能库)
            与删除。②装备技能页: 左侧装备名(可搜索), 右上实例表(等级 _Lv/耐久 _Durable 可直接改),
            右下「装备技能 _SkillLv」「词条技能 _ItemSkillLv」两个技能字典(存档形态「技能名 → [等级数组]」),
            可逐条改等级、从技能库添加技能、整行设为目标等级、删除条目(缺字段会自动补写)。
            关键结论(实测 custom0.es3): **蛊虫可用状态只有 5 种 —— 中毒/流血/着火/点穴/冰冻**
            (依据 ChongPotHad 的 5 类虫罐 毒/穴/血/火/冰 与 _BuffName 的 Debuff_* —— 即 4 种 + 冰冻,
            不是按 内存所有道具.json 的 skill 段全量(**v2.13.3 起技能库已只保留 pass+todu 两组**);
            新增蛊虫的图标按名字元素推断
            (冰→bing/毒→du/穴→xue/血→xie/火→huo/银灰→yinhui, 只取游戏 SaveChongIcon 里真实存在的组合)。
            新增两个数据文件: 蛊虫名.json(由 _scaffold/build_chong_names.py 生成)、技能名.json
            (由 _scaffold/build_skill_names.py 生成)。性能: 真实 7.9MB 档上两页的模型全部走整档结构索引/
            按名字重定位(装备模型 1.2s→0.13s, 实例重定位 ~20ms), 且**改动后不再整模重建**——改一条蛊虫只
            重读该条(十几毫秒)、改一个装备实例只按名字重定位实例, 避免“改一下就卡一下”。核心 193/193、
            GUI 231/231、真实 7.9MB 档端到端 11/11。

新增(v2.12.0 剧情变量): **主角页新增「剧情变量(存档 saveDialogue 段)」——可直接读/改「善恶值」**。
            游戏把「善恶值」这类由剧情累计的数值写在 saveDialogue 段的变量表里, 其存储形态不是
            `"善恶值" : 7`, 而是**十进制字节数组**编码(变量名与数值都按字节写, 所以按 UTF-8 直搜「善恶值」
            是搜不到的): 字符串 `83,<长度>,<UTF-8 字节...>`、double `78,<8 字节小端 IEEE754>`、
            bool `66,<1 字节>`、int32 `84,<4 字节小端>`; 实测 custom0.es3 里
            `83,9,229,150,132,230,129,182,229,128,188,78,0,0,0,0,0,0,28,64` 即 善恶值 = 7.0(全档仅 1 处)。
            新增纯函数 `dec_byte_text`(字符串/字节→十进制字节文本)/`dialogue_var_span`(定位变量名后的
            数值记号, 返回区间+类型+值)/`get_dialogue_var`/`set_dialogue_var`(按原类型写回; 值相同或变量
            不存在则原样返回, 不凭空插入新变量) 与常量 `DIALOGUE_VARS`; `char_model` 增 `dialogue` 字段
            (随大档后台线程一并收集); 主角页新增 `_add_dialogue_section`「剧情变量」分组——显示当前值 +
            「默认 0」按钮, 改动经 `_apply_dialogue_var` 写入 `self._text`, 与角色属性一样随「保存/另存为/
            复制结果」落盘; 该存档没有此变量时只显示「变量表中没有…」、不给改。核心 157/157、GUI 198/198。

新增(v2.11.0 标题状态): **窗口标题由「未保存加 *」改为「状态 + 时间戳」显示**——存在未保存修改时标题尾显示
            `[未保存 - HH:MM:SS.ffff]`(24 小时制、秒后 4 位小数毫秒, 每次改动刷新为最近改动时刻); 打开/粘贴/
            保存/另存后(内容与磁盘/来源一致)显示 `[已保存 - HH:MM:SS.ffff]`; 开「文件变化时自动刷新」后, 检测到
            外部改动开始刷新前标题先显示 `[正在刷新]`, 刷新完成(读档成功回到干净基线)显示
            `[已刷新 - HH:MM:SS.ffff]`(读取/解析失败复位回 `[已保存 …]`, 不会停在正在刷新)。实现: 新增 模块级
            `_format_ts()`(HH:MM:SS.ffff) 与 主窗 标题状态 `_title_state`/`_title_state_ts`/`_auto_refreshing`;
            `_mark_dirty`→unsaved、`_mark_clean`→saved 或 refreshed(自动刷新语境, 并复位 `_auto_refreshing`);
            新增 `_set_title_state`/`_clear_title_state`(保存后关闭文档回未打开时清空状态); `_refresh_title` 按状态
            拼 `[未保存|已保存|正在刷新|已刷新 - 时间戳]`; `_on_auto_reload_tick` 触发刷新前置 refreshing、未走到
            clean(失败)复位 saved; `_reset_document_state` 清 `_auto_refreshing`。GUI 冒烟新增标题状态断言
            (读取=已保存/修改=未保存/清脏回已保存/自动刷新完成=已刷新)。核心 131/131、GUI 190/190。

新增(v2.10.0 设置): **新增「设置」对话框与两个“防旧档/忘刷新”开关**——工具栏新增「设置…」(SettingsDialog):
            ①「保存后关闭当前文件」: 点「保存」写回存档后自动清空回到“未打开”状态(`_reset_document_state`), 防游戏再存
            档后编辑器仍停在上一份、再保存把存档“打回上一次”; ②「文件变化时自动刷新」: 每 2s 比对磁盘文件签名
            (mtime_ns,size, `_doc_sig`/`_note_disk_sig`, 读/写成功都更新, 避免把自己刚写当外部变化), 与已打开内容
            不一致时自动按新内容重读(`_open_path(record=False)`, 不刷历史; 无未保存修改直接刷, 有未保存修改仅提示不
            覆盖、按签名去重防刷屏; 忙/大档后台/模态框时不打扰)。两项存 设置.json(`close_on_save`/`auto_reload`),
            进 `_save_settings_now` 持久化, 工具栏可随时改。核心 131/131、GUI 185/185。

新增(v2.9.1): **主角添加装备支持按「件数」加同名多件(装备可同名、不堆叠)**——v2.9.0 曾把主角 EquipHad
            添加限定为「每件 1 实例 + 已有同名灰显跳过」; 现改为与商店 SellEquips 一致: 弹窗不再灰显已有同名,
            「件数」框填 N(默认 1)= 给该装备名追加 N 个同名实例(如填 5 = 5 把斩龙剑; 空档/新名=建 N 实例条目,
            已有同名=数组追加 N 实例)。纯函数 `player_add_equips(text, adds)` 接口改为 (名,件数) 列表 →
            (新文本, 名→件数), 复用 shop_add_equips 的「字段块内多轮局部插副本 + 一次性 _apply_subs」写法
            (`_player_equip_entry_text` 支持 count 实例); `_on_add_player_equip` 取对话框件数并允许重复。
            核心 131/131、GUI 175/175。

新增(v2.9.0 分用途): **装备(equip)与道具(ItemHad)分离——equip 改存 EquipHad, ItemHad 新增排除装备**。
            新增道具(ItemHad)与商店卖品(SellItems)的对话框只列 道具/配方/书籍/武功/山海录 五类, 不再
            显示 equip(装备)与 skillcom(技能合成); 道具页新增「＋ 添加装备…(EquipHad)」把 equip 类写入
            主角 savePlayerData.value 的 EquipHad 段(结构同商店 SellEquips: 装备名→实例数组, 每件 1 个
            实例、前导数字=等级、已在 EquipHad 的同名灰显防重); 商店「＋ 添加装备…(SellEquips)」同样
            只列 equip。「一键添加全部道具」也只进 ItemHad(剔除 equip/skillcom)。纯函数: build_item_cat_nodes
            增 allow_codes、新增 split_names_by_cats/_name_cat_map/_filter_names_by_cats 分类过滤与
            主角装备 _player_had_field_open/player_equip_open/player_equip_records/player_add_equips;
            AddItemDialog 增 allow_codes/show_count(单一分类自动勾选)。核心 131/131、GUI 175/175。

新增(v2.8.4 防御): **批量改 折扣/刷新日 增加数据防损坏保护**——排查确认当前存档上
            批量应用(选中/全部)不会删 _ShopData(纯函数+GUI 双路径复现均 260 店完好、括号平衡);
            为防异常结构存档/未来回归导致大段被误抹, 在 `shop_set_npc_params` 逐店定位后加健全检查
            (闭括号不对 / 跨度非法 / 命中点非店对象(无 abName 头)一律跳过该店不替换),
            并在 `_on_shop_npc_apply` 后台结果返回后校验: 若 `_ShopData` 段丢失或括号失衡,
            则**拒绝采纳结果、存档保持原样**并弹窗警告提示重读。核心 118/118、GUI 168/168。

新增(v2.8.3): **主角 Lv / 队友 _Lv(等级) 一键默认由 99 改为 9999**——
            `PLAYER_DEFAULTS["Lv"]`/`FRIEND_DEFAULTS["_Lv"]` 改为 9999, 主角页/队友页「等级」
            的「默认」按钮与「一键全部按默认」都改为设 9999。核心 118/118、GUI 168/168。

新增(v2.8.2): **主角 UseTalent / 队友 _UseTalent(已用天赋) 一键默认改为 -999(负 999)**——
            数值框范围本就允许负值; 现把二者加入默认表: 主角页「已用天赋 UseTalent」/每个队友页
            「已用天赋 _UseTalent」出现「默认 -999」按钮, 「一键全部按默认」也会把该字段设为 -999
            (负的“已用”可在游戏里把可用天赋拉高)。核心 118/118、GUI 168/168。

新增(v2.8.1): **队友页新增「生活技能经验 _LifeTypeLv」编辑分组(默认一键 999999)**——真实档里每名队友
            (在队/离队)都带 `_LifeTypeLv`(键 0~8 缺 6, 数值=对应生活技能类型经验, 如 {0:10,1:10,2:99,3:10,4:69,5:10,7:23,8:1});
            与主角 生活技能 LifeExp 同款处理: **前面的编号(键)原样不变, 只改冒号后的经验**, 行内可单个直接改,
            顶部「全部 → 999999」一键设满(复用 `_add_dict_section`/`_apply_dict_all`/`set_flat_dict_all`,
            `FRIEND_DICT_FIELDS` 增 `_LifeTypeLv`, 队友页在 武学经验 后新增该分组)。核心 118/118、GUI 168/168。

新增(v2.8.0 性能): **根治「各种操作后卡顿」——整档结构索引改为随改动"打补丁平移"而非每次全量重建**。
            新增 `_apply_subs` 在重建文本时若文本恰为缓存索引所属, 顺带把索引按各替换段位移平移为
            新文本索引(段外结构位置整体平移 delta, 段内替换文本重扫结构字符; 失败仅清缓存下次冷建, 不影响正确性);
            原实现对 6.7MB 真实档每次改动后下一次操作都要冷建整档索引(~1s/次) → 操作后卡顿。
            另新增局部顶层扫描 `_entry_values_local`(写路径在小段上用, 不挤掉全局索引缓存) 与
            快速商店字段定位 `_shop_field_open`(改 `_shop_sell_open` 不再逐层 `_locate_container` 大容器
            结构扫描, 单店定位 ~0.5s→~0.01s); 商店/角色/地图/保存等全部写路径统一走 `_apply_subs` 维护缓存。
            实测(custom9 6.7MB 普通店): 店页刷新 984ms→5ms、加卖品/装备 1.4s/1.1s→约 0.1~0.2s、
            改数量 1.4s→5ms, 且连续多次操作索引全程保持热不再回落到 ~1s。核心 118/118、GUI 168/168。

新增(v2.7.3): 商店 NPC 若没有 SellEquips 装备栏字段, 「＋ 添加装备…」现在会**先自动补一个空 SellEquips 字段**(格式对齐该店缩进/换行, 同 猪姨 等卖装备 NPC), 再照常添加装备;
            新增纯函数 `shop_ensure_sellequips`(缺字段则在该店首字段行前补 `"SellEquips" : { }`, 已存在不重复补),
            状态栏提示「该 NPC 原本没有 SellEquips, 已自动补装备栏字段」。核心 118/118、GUI 168/168。

新增(v2.7.2 修复): 「删除选中卖品/选中改数量/删除选中装备/选中改件数」按钮在打开存档后仍为灰色点不了——
            `_refresh_shop_tab` 无店分支会禁用这组控件 + 批量目标框 `shop_batch_spin`, 但有店分支漏了重新启用;
            已补启用(有店即可用, 未选中时按钮弹提示)。GUI 166/166。

新增(v2.7.1): 「商店NPC」页右侧改为**分类标签页**承载: 顶部 NPC 标题 + 批量目标框(卖品数量/装备件数共用, 自动记忆),
            下方 QTabWidget 分三页 ——「卖品」(卖品表 + 添加卖品 + 删除选中/选中改数量)、「装备」(装备表 +
            添加装备 + 删除选中/选中改件数)、「NPC 参数」(折扣/刷新日 + 批量应用选中/全部), 一屏不再堆满;
            所有控件名/写回逻辑不变(仅布局分组), 批量折扣默认 0.5/刷新日 1 记忆不变。GUI 165/165。

新增(v2.7.0): **道具页 + 商店NPC 多选批量增删改(数量自定义并持久记忆) + 折扣/刷新日一键全部**。
            「道具」页表格新增「选中改为N」按钮: 可 Ctrl/拖动 多选行后把数量一次性改成 右侧目标值
            (尊重「跳过铜钱」, 不整表重建不卡)。商店页: 左侧 NPC 列表可多选; 右侧卖品表/已上架装备表
            (新增 SellEquips 装备表)均支持多选 → 「删除选中」/「选中改数量·件数」(件数目标 0=删整种);
            目标值 spin(_shop_batch_value) 自动记忆; 参数区新增「批量折扣/刷新日」(默认折扣 0.5/刷新日 1,
            可自定义并记忆) + 「应用到选中 NPC」「应用到全部 NPC」, 缺失字段自动补写。纯函数层新增
            shop_del_items/shop_set_item_counts/shop_del_equips/shop_set_equip_counts/shop_set_npc_params
            及局部定位 helper(_local_span_end/_sell_equip_entries_in/_body_set_field 等), 均只做店内小段
            局部操作不触发整档结构索引重建, 大档实时毫秒级; 全部写回走 _run_bg 后台线程。设置新增键
            shop_batch_value/discount_all/refresh_all(与道具 batch_value 分开记忆)。

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
import struct
import sys
import threading
import time
from bisect import bisect_left
from datetime import datetime

__version__ = "2.15.0"
APP_NAME = "灵兽江湖存档修改器"
# 道具数量上限: 21 亿(用户指定 2100000000; 不超过 32 位有符号上限 2147483647)。
# 所有数字框/批量改/校验统一用这个上限。
MAX_ITEM_COUNT = 2100000000

from PySide6.QtCore import Qt, QTimer, QItemSelection, QItemSelectionModel
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


def _format_ts():
    """当前时间戳字符串: 24 小时制 HH:MM:SS + 秒后 4 位小数(毫秒级)。例: 14:23:45.1234"""
    return datetime.now().strftime("%H:%M:%S.%f")[:-2]


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
    # 原 ItemHad 段的字符区间 [s, e) 整段替换(经 _apply_subs 顺带平移缓存结构索引, 保存后不冷建)
    s = sum(len(l) for l in lines[:start_idx])
    e = s + sum(len(l) for l in lines[start_idx:close_idx + 1])
    return _apply_subs(text, [(s, e, "".join(block))])


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
    "Lv": 9999,             # 等级: 一键默认 9999
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
    "UseTalent": -999,      # 已用天赋: 一键默认 -999(负值, 可把可用天赋拉高)
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
    "_Lv": 9999,            # 等级: 一键默认 9999
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
    "_UseTalent": -999,     # 已用天赋: 一键默认 -999(负值)
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

# ---- 大文本结构索引: finditer 逐 token 产生 Python matcher 极慢(真实 6.7MB 档 21 万 token ~11s)。
#      改为一次 C 级 re.split 按字符串切分(字符串段原样跳过), 只在外围文本用单字符正则找结构符,
#      产出「结构单字符的 (位置, 字符) 列表」; 之后 _matching_end/_entry_values 在索引上线性扫描(O(结构数)),
#      同文本多次调用共享缓存(按 str 对象 is 判同), 大档从秒级降到毫秒级。 ----
_SPLIT_SEG_RE = re.compile(r'"(?:\\.|[^"\\])*"')   # 匹配一个完整字符串(用于跳字符串)
_STRUCT_CHAR_RE = re.compile(r"[{}[\],]")
_SCAN_CACHE = [None, None]   # [text对象, (poss, chars, pairs)] 只缓存最近一份文本, 防大档多份滞留
# 「编辑后异步预热结构索引」用: 记已请求预热的文本对象(按 is 比较) + 锁, 避免重复起线程
_PREHEAT_LOCK = threading.Lock()
_PREHEAT_LAST = [None]


def _brace_pairs(chars):
    """同型括号配对表: pairs[i] = 与第 i 个结构符(同型括号)配对的那个的**索引下标**; 无配对 -1。

    每个 opener 只与**同型**的最近未配对 closer 配对(与 `_matching_end` 原逐 token 配平语义一致:
    数组/对象嵌套时可忽略异型)。建索引时用栈一次 O(结构符数) 算好, 之后 `_matching_end` 是
    O(1) 查表、`_entry_values` 能整块跳过子容器 —— 原来两者都要从起点扫到闭括号,
    容器越大越慢(6MB 档单次 ~0.2s, 打开大档时反复调用就是 6 秒的根源)。
    """
    n = len(chars)
    pairs = [-1] * n
    st_c = []      # '{' 栈
    st_s = []      # '[' 栈
    for i in range(n):
        c = chars[i]
        if c == "{":
            st_c.append(i)
        elif c == "[":
            st_s.append(i)
        elif c == "}":
            if st_c:
                j = st_c.pop()
                pairs[j] = i
                pairs[i] = j
        elif c == "]":
            if st_s:
                j = st_s.pop()
                pairs[j] = i
                pairs[i] = j
    return pairs


def _struct_index(text):
    """返回 (poss, chars)——整份文本里『不在字符串内』的全部结构单字符位置与字符, 升序。

    实现(全 C 级快速, 避免 re 逐 matcher 的 ~50µs/token 开销):
      1. 循环 text.find('"') 定位字符串(纯 C); 引号前的「外围文本」原样保留;
      2. 字符串用 _string_end 跳到结束(仅对字符串内部逐字符, 总量小);
      3. str.join 拼出 clean——字符串区被挖成等长空格(保持偏移);
      4. 在 clean 上做**一次**单字符正则 finditer 取全部结构符。
    真实 6.7MB 档一次 ~0.8s; 同一 str 命中 _SCAN_CACHE 后 0 成本。
    """
    chunks = []
    n = len(text)
    i = 0
    while i < n:
        q = text.find('"', i)          # 下一字符串开引号(纯 C)
        if q < 0:
            chunks.append(text[i:])
            break
        if q > i:
            chunks.append(text[i:q])
        e = _string_end(text, q)       # 只对字符串内部逐字符(总量小), 跳过含 \\ 转义
        chunks.append(" " * (e - q))   # 挖成等长空格, 保持偏移
        i = e
    clean = "".join(chunks)
    poss = []
    chars = []
    for m in _STRUCT_CHAR_RE.finditer(clean):
        poss.append(m.start())
        chars.append(m.group(0))
    return poss, chars, _brace_pairs(chars)


def _get_struct_index(text):
    """取 text 的结构索引 (poss, chars, pairs)(同一 str 对象只建一次并缓存)。"""
    if _SCAN_CACHE[0] is text and _SCAN_CACHE[1] is not None:
        return _SCAN_CACHE[1]
    idx = _struct_index(text)
    _SCAN_CACHE[0] = text
    _SCAN_CACHE[1] = idx
    return idx


def _matching_end(text, start):
    """text[start] 为 '{' 或 '['; 返回配对的 '}' / ']' 下标(含)。字符串内括号忽略。找不到返回 len(text)-1。

    只对与 opener 同型的括号配平(数组/对象成对嵌套时可忽略异型), 语义与原 finditer 版一致。
    ★ 走索引里的**配对表 O(1) 查表**(见 `_brace_pairs`); 起点不在索引里(异常输入)才退回逐 token 配平。
    """
    opener = text[start]
    closer = "}" if opener == "{" else "]"
    poss, chars, pairs = _get_struct_index(text)
    np = len(poss)
    i = bisect_left(poss, start)
    if pairs is not None and i < np and poss[i] == start:
        k = pairs[i]
        if k >= 0:
            return poss[k]
    depth = 0
    while i < np:
        c = chars[i]
        if c == opener:
            depth += 1
        elif c == closer:
            depth -= 1
            if depth == 0:
                return poss[i]
        i += 1
    return len(text) - 1


def _string_end(text, i):
    """i 指向开引号; 返回闭引号后一位(排除)。处理 \\ 转义。

    用纯 C str.find 定位下一个 '"'(每字符串通常一次); 仅当该引号被「奇数个反斜杠」转义时
    才继续向后找——比逐字符/逐 matcher 都快(大档扫 10 万字符串从秒级降到亚秒)。
    """
    n = len(text)
    e = text.find('"', i + 1)
    while e >= 0:
        bs = 0
        p = e - 1
        while p > i and text[p] == "\\":
            bs += 1
            p -= 1
        if bs % 2 == 0:
            return e + 1
        e = text.find('"', e + 1)
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

    基于结构索引: 先用**配对表 O(1) 找容器闭**, 再在闭区间内切 0 层逗号(子容器用配对表整块跳过,
    只遍历顶层字段; 配对表缺失/异常时退回原全括号计数实现, 语义完全一致); 大文本远快。
    """
    opener = text[open_i]
    closer = "}" if opener == "{" else "]"
    poss, chars, pairs = _get_struct_index(text)
    np = len(poss)
    # 1) 找容器自己的闭(配对表 O(1); 查不到则退回逐 token 同型配平)
    i0 = bisect_left(poss, open_i)
    close_pi = pairs[i0] if (pairs is not None and i0 < np and poss[i0] == open_i) else -1
    if close_pi >= 0:
        close_i = poss[close_pi]
    else:
        i = i0
        depth0 = 0
        close_i = -1
        while i < np:
            c = chars[i]
            if c == opener:
                depth0 += 1
            elif c == closer:
                depth0 -= 1
                if depth0 == 0:
                    close_i = poss[i]
                    break
            i += 1
        if close_i < 0:
            close_i = len(text) - 1
        close_pi = -1
    # 2) 闭区间内切 0 层逗号
    commas = []
    ok_fast = close_pi >= 0 and pairs is not None
    if ok_fast:
        # 快速路径: 遇到子容器整块跳到它配对的闭括号之后(不再逐 token 计数)
        j = bisect_left(poss, open_i + 1)
        while j < close_pi:
            c = chars[j]
            if c == "{" or c == "[":
                k = pairs[j]
                if k < 0 or k > close_pi:
                    ok_fast = False
                    break
                j = k + 1
                continue
            if c == ",":
                commas.append(poss[j])
            j += 1
    if not ok_fast:
        # 回退: 原全括号计数(任何 { [ +1 / } ] -1, 逗号在 0 层即顶层分隔)
        commas = []
        j = bisect_left(poss, open_i + 1)
        depth = 0
        while j < np and poss[j] < close_i:
            c = chars[j]
            if c == "{" or c == "[":
                depth += 1
            elif c == "}" or c == "]":
                depth -= 1
            elif c == "," and depth == 0:
                commas.append(poss[j])
            j += 1
    bounds = [open_i + 1] + [cc + 1 for cc in commas] + [close_i]
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
                return _apply_subs(text, [(vs, end, val)])
    return text


def _apply_subs(text, subs):
    """把若干 (起点, 终点, 替换文本) 一次性重建文本(只整段复制一次, 避免逐条整文本拼接 O(k·n))。
    subs 的位置必须互不重叠且属于原 text。

    ★ 若 text 正是模块缓存结构索引(`_SCAN_CACHE`)所属文本, 则顺带把索引按各替换段的位移
    「打补丁」成新文本的索引(段外结构位置整体平移 delta, 段内替换文本重扫结构字符)。
    否则每次改动后下一次操作都要在整份大档上冷建结构索引(真实档 ~1s/次) → 「各种操作后卡顿」。
    返回新文本(与纯拼接等价); 打补丁失败仅清空缓存(下次冷建), 不影响正确性。
    """
    if not subs:
        return text
    subs = sorted(subs, key=lambda x: x[0])
    parts = []
    prev = 0
    for s, e, v in subs:
        if s > prev:
            parts.append(text[prev:s])
        parts.append(v)
        prev = e
    parts.append(text[prev:])
    nt = "".join(parts)

    cached = _SCAN_CACHE[0] is text
    old_idx = _SCAN_CACHE[1] if cached else None
    if cached and old_idx is not None:
        try:
            old_poss, old_chars, _old_pairs = old_idx
            new_poss = []
            new_chars = []
            delta = 0
            prev_pos = 0
            for s, e, v in subs:
                # 未被替换区间 [prev_pos, s): 整体平移 delta
                lo = bisect_left(old_poss, prev_pos)
                hi = bisect_left(old_poss, s)
                if lo < hi:
                    segp = old_poss[lo:hi]
                    new_poss.extend([p + delta for p in segp] if delta else segp)
                    new_chars.extend(old_chars[lo:hi])
                # 替换文本 v 自身结构字符(字符串跳过; v 通常很小)
                base = s + delta
                i = 0
                n = len(v)
                while i < n:
                    q = v.find('"', i)
                    if q < 0:
                        for m in _STRUCT_CHAR_RE.finditer(v, i):
                            new_poss.append(base + m.start())
                            new_chars.append(m.group(0))
                        break
                    if q > i:
                        for m in _STRUCT_CHAR_RE.finditer(v, i, q):
                            new_poss.append(base + m.start())
                            new_chars.append(m.group(0))
                    i = _string_end(v, q)
                delta += len(v) - (e - s)
                prev_pos = e
            # 末尾未替换区间
            lo = bisect_left(old_poss, prev_pos)
            if lo < len(old_poss):
                segp = old_poss[lo:]
                new_poss.extend([p + delta for p in segp] if delta else segp)
                new_chars.extend(old_chars[lo:])
            new_pairs = _brace_pairs(new_chars)   # 配对表按新 chars 重建(下标会因插入/删除而变)
            _SCAN_CACHE[0] = nt
            _SCAN_CACHE[1] = (new_poss, new_chars, new_pairs)
        except Exception:  # noqa: BLE001 打补丁失败: 只清缓存, 下次冷建, 保证一致性
            _SCAN_CACHE[0] = nt
            _SCAN_CACHE[1] = None
    elif cached:
        _SCAN_CACHE[0] = nt
    return nt


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
                return _apply_subs(text, [(vs, end, val)])
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


def _unique_field_open(text, field, ch):
    """快速定位「字段名 → 容器/数组」的开括号: 字段名在全档唯一时直接 str.find(毫秒级)。

    ★ 用于 _ActiveMap 这类**字段名全档只出现一次**的读写: 走 `_locate_container(scope)` 要逐层
      扫描大容器(实测 8.6MB 档 saveCustomData 定位 ~1.7s, 地图输入一下就卡住1秒多),
      而 find + 括号配平只要几毫秒。
    返回开括号下标; 字段名不唯一 / 后面不是 `:`+ch → None(调用方回退原容器定位路径)。
    """
    if not field:
        return None
    key = '"%s"' % field
    i = text.find(key)
    if i < 0 or text.find(key, i + 1) >= 0:      # 找不到 或 不唯一
        return None
    j = i + len(key)
    while j < len(text) and text[j] in " \t":
        j += 1
    if j >= len(text) or text[j] != ":":
        return None
    j += 1
    while j < len(text) and text[j] in " \t":
        j += 1
    return j if (j < len(text) and text[j] == ch) else None


def get_str_array(text, scope, field):
    """读 scope 容器内字段 field 的字符串数组元素(如 _ActiveMap 地点名)。返回列表。

    ★ 字段名全档唯一时走 str.find + **局部括号配平**(`_local_span_end`): 不能用 `_matching_end`
      —— 它依赖整档结构索引, 编辑后索引失效要冷建 ~1.3s(实测地图页首次刷新卡 1.3 秒的真因)。
    """
    vs = _unique_field_open(text, field, "[")
    if vs is not None:
        return _quoted_strings(text[vs + 1:_local_span_end(text, vs)])
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
    vs = _unique_field_open(text, field, "[")
    if vs is None:
        c = _locate_container(text, scope)
        if c is None:
            return text
        vs = None
        for key_disp, v2, _ve, _vt in _entry_values(text, c):
            if key_disp == field and text[v2:v2 + 1] == "[":
                vs = v2
                break
        if vs is None:
            return text
    close_i = _local_span_end(text, vs)      # 局部配平, 不走整档索引(见 get_str_array 注释)
    existing = _quoted_strings(text[vs + 1:close_i])
    if any(e == name for e in existing):
        return text
    body = text[vs + 1:close_i]
    rbody = body.rstrip()
    qname = '"' + name + '"'
    if rbody:
        ins = vs + 1 + len(rbody)
        return _apply_subs(text, [(ins, ins, ',' + qname)])
    return _apply_subs(text, [(vs + 1, vs + 1, qname)])


def remove_str_array(text, scope, field, name):
    """从字符串数组删除指定元素(含前缀逗号/空格处理)。返回新文本。"""
    name = (name or "").strip()
    if not name:
        return text
    vs = _unique_field_open(text, field, "[")
    if vs is None:
        c = _locate_container(text, scope)
        if c is None:
            return text
        for key_disp, v2, _ve, _vt in _entry_values(text, c):
            if key_disp == field and text[v2:v2 + 1] == "[":
                vs = v2
                break
        else:
            return text
    close_i = _local_span_end(text, vs)
    pat = re.compile(r',?\s*"' + re.escape(name) + r'"')
    region = text[vs + 1:close_i]
    new_region, n = pat.subn("", region)
    if n:
        # 删后若只剩空白则数组留空
        return _apply_subs(text, [(vs + 1, close_i, new_region)])
    return text


# 主角/队友容器的定位路径
SCOPE_PLAYER = ["savePlayerData", "value"]
SCOPE_MAP = ["saveCustomData", "value"]
SCOPE_FRIENDS = ["saveFriendData", "value", "AddFriends"]
# NPC/商店容器: saveUtilData.value._ShopData.<商店名>{ abName, SellItems{道具...} }
SCOPE_SHOP = ["saveUtilData", "value", "_ShopData"]


# ==================== NPC 商店卖的道具(_ShopData / SellItems) ====================
def shop_records_full(text):
    """一次枚举 _ShopData 全部商店: 返回 [(键, 显示名, SellItems容器开括号 or None, 商店对象开括号)], 顺序同文件。

    显示名优先取对象内 abName(如 '猪姨'), 缺省用字典键; sell_open 供直接读/改该店卖品。
    比 shop_records 多带第 4 项店容器开括号(供免重复定位店内字段)。"""
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
        out.append((kd, ab if ab is not None else kd, sopen, vs))
    return out


def shop_records(text):
    """枚举 _ShopData 全部商店的 (键, 显示名, SellItems容器开括号 or None)(shop_records_full 的前三项)。"""
    return [(k, ab, so) for k, ab, so, _sop in shop_records_full(text)]


def _shop_object_open(text, key):
    """直接定位商店对象开括号: 用 C str.find 找 `"店名"` 第一次「键形出现」——其紧跟 `空格*:空格*{`。

    商店键总是先于同店 abName/其它值出现, 键后为 `:{`(值容器), 而值字符串里引用店名后非 `:{`
    (如 abName 值后是 `,`), 故取首个后随 `:{` 的命中即真键; 找不到回退 _locate_container。
    真实 6.7MB 档单店定位 ~几十毫秒(不再逐层大容器扫)。
    """
    needle = '"%s"' % key
    scan = re.compile(r"[ \t]*:[ \t]*(\{)")   # 不跨换行, 避免 `\s` 吞到远处 `{`
    p = text.find(needle)
    while p >= 0:
        m = scan.match(text, p + len(needle))
        if m:
            return m.start(1)     # re.match 的 group 位置已是相对整串的绝对下标
        p = text.find(needle, p + 1)
    return _locate_container(text, SCOPE_SHOP + [key])


def _shop_field_open(text, o, field):
    """在商店对象 o(开括号)的**直接顶层**找字段 field 的值起点; 找不到返回 None。

    只在键间跳跃: 顶层键(abName/Discount/CoinName/SellEquips/SellItems/…)大多在店首,
    SellItems/SellEquips 之前没有巨型容器, 命中即停——避免旧 `_locate_container` 逐层
    `_entry_values` 在 _ShopData 大容器上整档结构扫描(真实档每次 ~0.5s)。值容器用深度计数跳过。
    """
    j = o + 1
    n = len(text)
    depth = 0
    while j < n:
        c = text[j]
        if c == '"':
            e = _string_end(text, j)
            if depth == 0 and e - j > 2 and text[j + 1:e - 1] == field:
                q = e
                while q < n and text[q] in " \t\r\n":
                    q += 1
                if q < n and text[q] == ":":
                    q += 1
                    while q < n and text[q] in " \t\r\n":
                        q += 1
                    return q
            j = e
            continue
        if c == "{": depth += 1
        elif c == "}":
            depth -= 1
            if depth < 0:
                return None
        elif c == "[": depth += 1
        elif c == "]": depth -= 1
        j += 1
    return None


def _shop_sell_open(text, key):
    """定位商店 key 的 SellItems 容器开括号(快: 键 find + 店首字段早停扫); 找不到返回 None。"""
    o = _shop_object_open(text, key)
    if o is None:
        return None
    vs = _shop_field_open(text, o, "SellItems")
    if vs is not None and text[vs:vs + 1] == "{":
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
    return _apply_subs(nt, [(hs, he, "".join(block))]), [it.name for it in adds2]


def _shop_sell_dict_span(text, sell_open):
    """定位商店 SellItems 整段(键名行行首 hs → dict 闭合行尾 he)与尾部是否有逗号。

    sell_open(_shop_sell_open) 对非空 SellItems 返回的是「首卖品对象」的开括号(inline 于键行内),
    不是 SellItems dict 自身的开括号; 空 SellItems 时 sell_open 才是 dict 开。
    这里从键行内「"SellItems" 后的首个 {」反推真正的 dict 开, 使整段重建括号配平。
    返回 (hs, dict_open, dict_close, he, tail_comma)。
    """
    hs = text.rfind("\n", 0, sell_open) + 1
    kidx = text.find('"SellItems"', hs, sell_open + 1)
    dict_open = -1
    if kidx >= 0:
        dict_open = text.find("{", kidx + 1, sell_open + 1)
    if dict_open < 0:
        dict_open = sell_open
    close = _matching_end(text, dict_open)
    he = text.find("\n", close)
    he = len(text) if he < 0 else he + 1
    tail_comma = text[close + 1:he].lstrip().startswith(",")
    return hs, dict_open, close, he, tail_comma


def _rebuild_sellitems_seg(text, hs, he, block, tail_comma, newline):
    """把 rebuild 输出块写回(处理段尾逗号保留), 返回新文本(段区间外原样)。

    只在块末行缺逗号而原段尾需要逗号时补逗号; 保留各行的换行(不能 rstrip 整块,
    否则块尾(sec 行)换行被吞, 后续同级字段会与 `}` 合并成一行 → 再解析时找不到段尾)。
    """
    if tail_comma:
        last = block[-1].rstrip("\r\n")
        if last and not last.endswith(","):
            block = block[:-1] + [last + "," + newline]
    return _apply_subs(text, [(hs, he, "".join(block))])


def shop_del_items(text, key, names):
    """从商店 SellItems 移除指定道具名(整件下架)。返回 (新文本, 实际删除名列表)。

    行级整段重建(与 shop_add_items 同模板, 段内其余道具字段原样保留); 找不到/全不在返回原文本。
    """
    drop = {n.strip() for n in (names or []) if (n or "").strip()}
    if not drop:
        return text, []
    sell_open = _shop_sell_open(text, key)
    if sell_open is None:
        return text, []
    hs, _do, _dc, he, tail_comma = _shop_sell_dict_span(text, sell_open)
    seg = text[hs:he]
    lines2 = seg.splitlines(keepends=True)
    parsed, ind2, cidx = parse_itemhad(lines2, 0, key="SellItems")
    if cidx is None:
        return text, []
    gone = [it.name for it in parsed if it.name in drop]
    if not gone:
        return text, []
    keep = [it for it in parsed if it.name not in drop]
    newline = "\r\n" if any(l.endswith("\r\n") for l in lines2) else "\n"
    if keep:
        block = build_itemhad_lines(keep, ind2, newline)
    else:
        # 全删光: build_itemhad_lines 对空列表会输出「header_prefix+} 自闭合」再拼 section_close
        # 造成重复闭合括号失配 → 只输出自闭合空 dict 行(尾逗号由 _rebuild_sellitems_seg 补)
        block = [ind2["header_prefix"] + "}" + newline]
    return _rebuild_sellitems_seg(text, hs, he, block, tail_comma, newline), gone


def shop_set_item_counts(text, key, pairs):
    """把商店 SellItems 中指定道具名的数量设为目标值 pairs={名:数量}。

    返回 (新文本, 实际改名数); 行级整段重建(与 add 同模板), 数量未变的店/名不改。找不到返回原文本。
    """
    pairs = {n.strip(): int(v) for n, v in (pairs or {}).items() if (n or "").strip()}
    if not pairs:
        return text, {}
    sell_open = _shop_sell_open(text, key)
    if sell_open is None:
        return text, {}
    hs, _do, _dc, he, tail_comma = _shop_sell_dict_span(text, sell_open)
    seg = text[hs:he]
    lines2 = seg.splitlines(keepends=True)
    parsed, ind2, cidx = parse_itemhad(lines2, 0, key="SellItems")
    if cidx is None:
        return text, {}
    changed = {}
    for it in parsed:
        if it.name in pairs and it.count != pairs[it.name]:
            it.count = pairs[it.name]
            changed[it.name] = pairs[it.name]
    if not changed:
        return text, {}
    newline = "\r\n" if any(l.endswith("\r\n") for l in lines2) else "\n"
    block = build_itemhad_lines(parsed, ind2, newline)
    return _rebuild_sellitems_seg(text, hs, he, block, tail_comma, newline), changed


def _local_span_end(text, i):
    """text[i] 为 '{' 或 '['; 返回配平的同型闭括号下标(字符串整体跳过, 逐字符)。

    只用于「商店单段/小容器」的局部文本操作——避免触发整份文本的结构索引重建(大档 1.4s/次)。
    """
    opener = text[i]
    closer = "}" if opener == "{" else "]"
    depth = 0
    n = len(text)
    j = i
    while j < n:
        c = text[j]
        if c == '"':
            j = _string_end(text, j)
            continue
        if c == opener:
            depth += 1
        elif c == closer:
            depth -= 1
            if depth == 0:
                return j
        j += 1
    return n - 1


def _entry_values_local(text, open_i):
    """局部版 _entry_values: 不触发整份文本结构索引(也不写全局 _SCAN_CACHE)。

    供「写路径」在商店/小容器段上扫描顶层条目——避免对切片建索引把全局缓存挤掉
    (否则下一次操作又得在整份大档上冷建索引 → 卡顿)。语义与 _entry_values 一致:
    把 open_i 处对象/数组体内按 0 层逗号切成条目, 返回
    list[(key_disp, val_start, val_end, val_text)]。open_i 必须指向 '{' 或 '['。
    仅适合中小容器; 超大容器读取仍走整档索引(缓存热, 毫秒级)。
    """
    opener = text[open_i]
    is_obj = opener == "{"
    close = _local_span_end(text, open_i)
    depth = 0
    commas = []
    j = open_i + 1
    while j < close:
        c = text[j]
        if c == '"':
            j = _string_end(text, j)
            continue
        if c in "{[": depth += 1
        elif c in "}]": depth -= 1
        elif c == "," and depth == 0: commas.append(j)
        j += 1
    bounds = [open_i + 1] + [cc + 1 for cc in commas] + [close]
    out = []
    for b in range(len(bounds) - 1):
        a0, a1 = bounds[b], bounds[b + 1]
        seg = text[a0:a1]
        if is_obj:
            kv = _key_value_offset(seg)
            if kv is None:
                continue
            key_raw, voff = kv
            vs = a0 + voff
            while vs < a1 and text[vs] in " \t\r\n":
                vs += 1
            out.append((_key_display(key_raw), vs, a1, text[vs:a1]))
        else:
            vs = a0
            while vs < a1 and text[vs] in " \t\r\n":
                vs += 1
            out.append((None, vs, a1, seg))
    return out


def _sell_equip_entries_in(text, eqo):
    """局部手工枚举 SellEquips 字典(eqo 为 `{`)内的「装备名 → 实例数组」条目。

    返回 [(干净名, 数组开括号, 数组闭括号)]; 字符串跳过、数组/对象成对配平, 不用全文结构索引。
    """
    out = []
    close = _local_span_end(text, eqo)
    j = eqo + 1
    while j < close:
        c = text[j]
        if c == '"':
            k_end = _string_end(text, j)
            name = text[j + 1:k_end - 1]
            q = k_end
            hit = False
            while q < close:
                ch = text[q]
                if ch == '"':            # 值(对象?)里再遇引号一般不会; 保守跳
                    q = _string_end(text, q)
                    continue
                if ch == ":":
                    q += 1
                    while q < close and text[q] in " \t\r\n":
                        q += 1
                    if q < close and text[q] == "[":
                        arr_close = _local_span_end(text, q)
                        out.append((_es3_unescape_name(name), q, arr_close))
                        j = arr_close + 1
                        hit = True
                        break
                    break
                q += 1
            if not hit:
                break
        elif c in " \t\r\n,":
            j += 1
        else:
            j += 1
    return out


def _arr_instance_spans(text, arr_open):
    """局部手工枚举数组(arr_open 为 `[`)内顶层对象实例的 (开, 闭) 区间。"""
    spans = []
    close = _local_span_end(text, arr_open)
    j = arr_open + 1
    while j < close:
        c = text[j]
        if c == '"':
            j = _string_end(text, j)
        elif c == "{":
            e = _local_span_end(text, j)
            spans.append((j, e))
            j = e + 1
        elif c in " \t\r\n,":
            j += 1
        else:
            j += 1
    return spans


def _equip_del_entry(text, key, eqo, nm, arr_open, arr_close):
    """删除 SellEquips 里单个整种装备条目(含其前导逗号/换行; 同文本降序删时其余条目偏移不受影响)。"""
    esc = _es3_escape_name(nm)
    needle = '"%s"' % esc
    ks = text.rfind(needle, eqo, arr_open)
    if ks < 0:
        ks = arr_open - 1
        while ks >= eqo and text[ks] != '"':
            ks -= 1
    k0 = ks
    p = ks - 1
    while p >= eqo and text[p] in " \t\r\n":
        p -= 1
    if p >= eqo and text[p] == ",":      # 非首条: 前导逗号一并删
        k0 = p
    return _apply_subs(text, [(k0, arr_close + 1, "")])


def shop_del_equips(text, key, names):
    """从商店 SellEquips 删除整种装备(名条目移除)。返回 (新文本, 实际删除名列表)。

    逐条按数组开括号降序删除, 同文本内先删后面条目不影响前面偏移; 仅局部段文本操作。
    """
    drop = {n.strip() for n in (names or []) if (n or "").strip()}
    if not drop:
        return text, []
    o = _shop_object_open(text, key)
    if o is None:
        return text, []
    o_close = _local_span_end(text, o)
    body = text[o + 1:o_close]
    eqm = re.search(r'"SellEquips"[ \t]*:[ \t]*(\{)', body)
    if not eqm:
        return text, []
    eqo = o + 1 + eqm.start(1)
    entries = _sell_equip_entries_in(text, eqo)
    gone = [nm for nm, _a, _b in entries if nm in drop]
    if not gone:
        return text, []
    gone_set = set(gone)
    for nm, arr_open, arr_close in sorted(entries, key=lambda e: -e[1]):
        if nm in gone_set:
            text = _equip_del_entry(text, key, eqo, nm, arr_open, arr_close)
    return text, gone


def shop_set_equip_counts(text, key, pairs):
    """把商店 SellEquips 若干装备的实例件数设为目标 pairs={名:件数}(0=删除整种)。

    返回 (新文本, 实际改名→件数)。>当前件数→模板追加副本; <当前件数→删尾部实例(保留至少1,
    需更少则整种删); 仅局部段文本操作(不触发整份结构索引重建)。找不到商店/无 SellEquips 返回原文本。
    """
    pairs = {n.strip(): max(0, int(v)) for n, v in (pairs or {}).items() if (n or "").strip()}
    if not pairs:
        return text, {}
    o = _shop_object_open(text, key)
    if o is None:
        return text, {}
    changed = {}
    # 先定位 SellEquips 值字典
    o_close = _local_span_end(text, o)
    body = text[o + 1:o_close]
    eqm = re.search(r'"SellEquips"[ \t]*:[ \t]*(\{)', body)
    if not eqm:
        return text, {}
    for nm, target in pairs.items():
        if target == 0:
            # 删除整种(不存在也视为完成)
            text, gone = shop_del_equips(text, key, [nm])
            if nm in gone:
                changed[nm] = 0
            continue
        eqo = _shop_object_open(text, key)
        if eqo is None:
            break
        o_close = _local_span_end(text, eqo)
        eqm = re.search(r'"SellEquips"[ \t]*:[ \t]*(\{)', text[eqo + 1:o_close])
        if not eqm:
            break
        eqo = eqo + 1 + eqm.start(1)
        entries = _sell_equip_entries_in(text, eqo)
        en = next((e for e in entries if e[0] == nm), None)
        if en is None:
            # 原本没有该装备: 用追加模板建 target 件
            text, added = shop_add_equips(text, key, [(nm, target)])
            if nm in added:
                changed[nm] = target
            continue
        arr_open = en[1]
        cur = len(_arr_instance_spans(text, arr_open))
        if target > cur:
            text, added = shop_add_equips(text, key, [(nm, target - cur)])
            if nm in added:
                changed[nm] = target
        elif target < cur:
            # 删尾部 (cur-target) 个实例(每次删末尾非首个实例, 保留至少1)
            need_del = cur - target
            for _ in range(need_del):
                o2 = _shop_object_open(text, key)
                o2c = _local_span_end(text, o2)
                eqm2 = re.search(r'"SellEquips"[ \t]*:[ \t]*(\{)', text[o2 + 1:o2c])
                if not eqm2:
                    break
                eqo2 = o2 + 1 + eqm2.start(1)
                en2 = next((e for e in _sell_equip_entries_in(text, eqo2) if e[0] == nm), None)
                if en2 is None:
                    break
                sp = _arr_instance_spans(text, en2[1])
                if len(sp) <= 1:
                    break
                _lo, _lc = sp[-2]
                vo, vc = sp[-1]
                text = _apply_subs(text, [(_lc + 1, vc + 1, "")])   # 去掉前导分隔与最后一个实例
            changed[nm] = target
        # target == cur: 不变
    return text, changed


def _body_field_span(body, field):
    """店 body(局部 str)内找直接字段 field 的值; 返回 (值起点, 值终点) 相对 body; 无返回 None。"""
    m = re.search(r'^[ \t]*"%s"[ \t]*:[ \t]*([^\r\n,}]+)' % re.escape(field), body, re.M)
    if not m:
        return None
    return (m.start(1), m.end(1))


def _body_field_indent(body):
    m = re.search(r'^([ \t]*)".*?":', body, re.M)
    return m.group(1) if m else "\t\t\t"


def _body_set_field(body, field, val, nl, ind):
    """把店 body 内字段 field 设为 val(原样文本); 缺失则在该店首字段行前补写一行。返回新 body。"""
    if val is None:
        return body
    span = _body_field_span(body, field)
    if span:
        s, e = span
        if body[s:e].strip() == val:
            return body
        return body[:s] + val + body[e:]
    m = re.match(r'^([ \t]*\r?\n)', body)
    if m:
        ins = ind + '"%s" : %s,%s' % (field, val, nl)
        return body[:m.end()] + ins + body[m.end():]
    return body


def shop_set_npc_params(text, keys, discount_txt=None, refresh_txt=None):
    """给一批商店同时设 Discount/RefreshDay(值为格式化后的原样文本; None=不改该字段)。缺失字段自动补写。

    每店在本地 body 内改字段(不触发整份结构索引重建), 逐店一次切片; 返回 (新文本, 成功店数)。
    """
    if discount_txt is None and refresh_txt is None:
        return text, 0
    n = 0
    for key in keys:
        o = _shop_object_open(text, key)
        if o is None:
            continue
        close = _local_span_end(text, o)
        # 防御(v2.8.4): 定位/跨度可疑绝不替换——防止异常店铺对象导致误抹大段(如整段 _ShopData)
        if close <= o or close >= len(text) or text[close] != "}":
            continue
        if '"abName"' not in text[o + 1:min(close, o + 513)]:
            continue
        body = text[o + 1:close]
        nl = "\r\n" if "\r\n" in body else "\n"
        ind = _body_field_indent(body)
        nb = _body_set_field(body, "Discount", discount_txt, nl, ind)
        nb = _body_set_field(nb, "RefreshDay", refresh_txt, nl, ind)
        if nb != body:
            text = _apply_subs(text, [(o + 1, close, nb)])
            n += 1
    return text, n


def shop_ensure_sellequips(text, key):
    """确保商店对象有 SellEquips 字段: 没有则补一个空字典(对齐该店缩进/换行, 插在该店首字段行前)。

    用于「没有 SellEquips 装备栏的 NPC 也能添加装备」——先补字段, 再走 shop_add_equips。
    返回 (新文本, 是否补写); 找不到商店返回 (原文本, False)。
    """
    o = _shop_object_open(text, key)
    if o is None:
        return text, False
    close = _local_span_end(text, o)
    body = text[o + 1:close]
    if re.search(r'(?m)^[ \t]*"SellEquips"[ \t]*:', body):
        return text, False
    nl = "\r\n" if "\r\n" in body else "\n"
    ind = _body_field_indent(body)
    ins = ind + '"SellEquips" : {' + nl + ind + '},' + nl
    m = re.match(r'^([ \t]*\r?\n)', body)
    if m:
        nb = body[:m.end()] + ins + body[m.end():]
    else:
        nb = ins + body
    return _apply_subs(text, [(o + 1, close, nb)]), True


def shop_field(text, key, field):
    """读某商店对象内直接数字字段(如 Discount/RefreshDay)的原样字符串; 无该字段返回 None。"""
    c = _shop_object_open(text, key)
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
    c = _shop_object_open(text, key)
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
            return _apply_subs(text, [(vs, end, new_value_text)]), True
    return text, False


def shop_view(text, key, shop_open=None):
    """一次店容器定位收集当前商店页需要的全部数据(GUI 刷新用, 避免多次独立全档定位)。

    shop_open 可传缓存容器开括号(无则 fast 定位); 返回 dict{ab, sell:[(名,件)], equips:[(名,件)],
    discount, refreshday}; 找不到商店返回 None。店内小段扫描, 大档也毫秒级。
    """
    if shop_open is None:
        shop_open = _shop_object_open(text, key)
    if shop_open is None:
        return None
    ab = None
    so = None
    eqo = None
    d = r = None
    for kd, vs, _ve, _vt in _entry_values(text, shop_open):
        if kd == "abName":
            if text[vs:vs + 1] == '"':
                qs = _quoted_strings(text[vs:_ve])
                if qs:
                    ab = qs[0]
        elif kd == "SellItems" and text[vs:vs + 1] == "{":
            so = vs
        elif kd == "SellEquips" and text[vs:vs + 1] == "{":
            eqo = vs
        elif kd == "Discount":
            tok = _num_token(text, vs)
            if tok:
                d = tok[0]
        elif kd == "RefreshDay":
            tok = _num_token(text, vs)
            if tok:
                r = tok[0]
    items = shop_sellitems(text, key, sell_open=so) if so is not None else []
    eqs = []
    if eqo is not None:
        for kd2, vs2, _ve2, _vt2 in _entry_values(text, eqo):
            if text[vs2:vs2 + 1] == "[":
                cnt = sum(1 for _k3, v3, _e3, _t3 in _entry_values(text, vs2)
                          if text[v3:v3 + 1] == "{")
                eqs.append((_es3_unescape_name(kd2), cnt))
    return {"ab": ab or key, "sell": items, "equips": eqs, "discount": d, "refreshday": r}


# ==================== 商店装备(SellEquips): 值=「装备名 → 实例对象数组」 ====================
# SellEquips 排版(与游戏存档一致, 制表符缩进 + CRLF):
#   "SellEquips" : {"1短铁棍":[\r\n\t\t\t\t\t\t{\r\n ... "_Name":"1短铁棍","_Lv":1 ... }
# 值对象字段: _QiItemNames[]/_Name/_Lv/_Durable/_SkillLv{}/_ItemSkillLv{}/_DressType/
#             _GetTimeNew/_IsCanLingHua/_IsFirstGet/_LockDissolve; 同名可多件(数组内多实例)。
def _shop_sellequips_open(text, key):
    """定位商店 key 对象里 SellEquips 字段的字典开括号; 缺失返回 None。"""
    c = _shop_object_open(text, key)
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

    性能: 只在「该商店的 SellEquips 段落」内做所有局部修改(每轮重扫该小段), 最后一次性
    text[:hs]+seg+text[he:] 拼回——避免旧实现对 6.7MB 大档每件全档定位+全文拼接(3 件曾 ~12s)。
    """
    merged = {}
    for nm, cnt in adds:
        nm = (nm or "").strip()
        if not nm:
            continue
        merged[nm] = merged.get(nm, 0) + max(1, int(cnt))
    if not merged:
        return text, {}
    o = _shop_object_open(text, key)
    if o is None:
        return text, {}
    eqo = None
    for kd, vs, _ve, _vt in _entry_values(text, o):
        if kd == "SellEquips" and text[vs:vs + 1] == "{":
            eqo = vs
            break
    if eqo is None:
        return text, {}
    # SellEquips 段落范围: 字段行行首 → 值字典闭合行行尾
    hs = text.rfind("\n", 0, eqo) + 1
    eqclose = _matching_end(text, eqo)
    he = text.find("\n", eqclose)
    he = len(text) if he < 0 else he + 1
    seg = text[hs:he]
    rel = eqo - hs                       # 值字典 `{` 在 seg 内的位置
    nl = "\r\n" if "\r\n" in seg else "\n"
    l0 = re.match(r"[ \t]*", seg).group(0)
    unit = "\t" if "\t" in l0 else (l0[:1] if l0 else "\t")
    l1 = l0 + unit
    l2 = l0 + unit * 2
    l3 = l0 + unit * 3
    l4 = l0 + unit * 4
    result = {}
    for nm, cnt in merged.items():
        mnum = re.match(r"(\d+)", nm)
        lv = int(mnum.group(1)) if mnum else 1
        esc = _es3_escape_name(nm)
        # 当前 seg 的 SellEquips 已有条目(每轮重扫, 因局部插入会移动后续偏移)
        entries = []
        for kd, vs, _ve, _vt in _entry_values_local(seg, rel):
            if seg[vs:vs + 1] == "[":
                entries.append((_es3_unescape_name(kd), vs, _local_span_end(seg, vs)))
        idx = next((i for i, (n, _a, _b) in enumerate(entries) if n == nm), None)
        if idx is not None:
            # 同名已上架: 往其数组里追加副本(定位最后实例对象的闭花括号后插入)
            _n, va, _vacl = entries[idx]
            last = va
            for _k3, v3, _e3, _t3 in _entry_values_local(seg, va):
                if seg[v3:v3 + 1] == "{":
                    last = _local_span_end(seg, v3)
            ap = ""
            for i in range(cnt):
                ap += (",{" if i == 0 else l2 + "},{") + nl
                ap += _equip_fields_text(l3, l4, esc, lv, nl)
            ap += l2 + "}" + nl
            seg = seg[:last + 1] + ap + seg[last + 1:]
        else:
            entry = _equip_new_entry_text(l1, l2, l3, l4, esc, lv, cnt, nl)
            if entries:
                # 插到最后一个条目的数组闭合 ] 后:  ],"新名":[...]
                j = entries[-1][2]
                seg = seg[:j + 1] + "," + entry + seg[j + 1:]
            else:
                # SellEquips 原本为空: 直接在 { 后内联新条目(第一键与 { 同行)
                seg = seg[:rel + 1] + entry + seg[rel + 1:]
        result[nm] = result.get(nm, 0) + cnt
    return _apply_subs(text, [(hs, he, seg)]), result


# ==================== 主角装备 EquipHad(savePlayerData.value 内: 装备名→实例数组) ====================
# EquipHad 与商店 SellEquips 结构一致(装备名→实例数组, 实例字段见下), 只是容器不同:
# savePlayerData.value 下 平级有 ItemHad(道具)/EquipHad(装备)/ItemHadTemp/EquipHadTemp 等。
# v2.9.0: equip 类道具应进 EquipHad 而非 ItemHad——新增对话框在「添加装备(EquipHad)」时只列 equip。
def _player_had_field_open(text, field):
    """定位 savePlayerData.value 内直接字段 field(如 EquipHad)的值容器开括号; 缺失返回 None。

    用 C str.find 找 `"field"` 键形出现后随 `空格*:空格*[或{`(带尾引号精确匹配, 不会命中 ItemHadTemp 等),
    不用整份结构索引(大档也快)。
    """
    needle = '"%s"' % field
    scan = re.compile(r"[ \t]*:[ \t]*([{\[])")
    p = text.find(needle)
    while p >= 0:
        m = scan.match(text, p + len(needle))
        if m:
            return m.start(1)
        p = text.find(needle, p + 1)
    return None


def player_equip_open(text):
    """主角 EquipHad 段(装备名→实例数组字典)的开括号; 缺失返回 None。"""
    o = _player_had_field_open(text, "EquipHad")
    if o is not None and text[o:o + 1] == "{":
        return o
    return None


def player_equip_records(text, count_too=True):
    """读主角 EquipHad 现有装备: count_too=True 返回 [(干净名, 实例件数)], 否则 [名字]。无段返回 []。"""
    o = player_equip_open(text)
    if o is None:
        return []
    out = []
    for nm, arr_open, _ac in _sell_equip_entries_in(text, o):
        if count_too:
            out.append((nm, len(_arr_instance_spans(text, arr_open))))
        else:
            out.append(nm)
    return out


def _player_equip_fields_text(l3, l4, name_esc, lv, nl):
    """主角装备实例字段行(与真实 EquipHad 实例一致: _IsCanLingHua false/_IsFirstGet 1/_GetTimeNew 0)。"""
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
            l3 + '"_IsCanLingHua" : false,' + nl +
            l3 + '"_IsFirstGet" : 1,' + nl +
            l3 + '"_LockDissolve" : false' + nl)


def _player_equip_entry_text(l1, l2, l3, l4, name_esc, lv, count, nl):
    """一个新的 EquipHad 条目:  "名字":[\n<count 个实例>\nL1]\n  (不含外层逗号)。"""
    s = '"' + name_esc + '":[' + nl
    for i in range(count):
        if i == 0:
            s += l2 + "{" + nl
        else:
            s += l2 + "},{" + nl
        s += _player_equip_fields_text(l3, l4, name_esc, lv, nl)
    s += l2 + "}" + nl + l1 + "]"
    return s


def player_add_equips(text, adds):
    """把 (装备名, 件数) 列表写入主角 EquipHad(装备可同名不堆叠: 同名→数组追加件数份实例, 新名→新增条目)。

    返回 (新文本, 实际 名→件数)。名字前导数字=等级(_Lv); 找不到 EquipHad 段返回 (原文本, {})。
    与 shop_add_equips 同法: 只在 EquipHad 字段块内做多次局部修改, 最后一次性 _apply_subs 写回, 维护索引缓存。
    """
    merged = {}
    for nm, cnt in adds:
        nm = (nm or "").strip()
        if not nm:
            continue
        merged[nm] = merged.get(nm, 0) + max(1, int(cnt))
    if not merged:
        return text, {}
    o = player_equip_open(text)
    if o is None:
        return text, {}
    # EquipHad 字段块范围: 键行行首 → 字典闭合行行尾
    hs = text.rfind("\n", 0, o) + 1
    eqclose = _local_span_end(text, o)
    he = text.find("\n", eqclose)
    he = len(text) if he < 0 else he + 1
    seg = text[hs:he]
    rel = o - hs                       # EquipHad 字典 `{` 在 seg 内的位置
    nl = "\r\n" if "\r\n" in seg else "\n"
    l0 = re.match(r"[ \t]*", seg).group(0)
    unit = "\t" if "\t" in l0 else (l0[:1] if l0 else "\t")
    l1 = l0 + unit
    l2 = l0 + unit * 2
    l3 = l0 + unit * 3
    l4 = l0 + unit * 4
    result = {}
    for nm, cnt in merged.items():
        mnum = re.match(r"(\d+)", nm)
        lv = int(mnum.group(1)) if mnum else 1
        esc = _es3_escape_name(nm)
        # 当前 seg 的 EquipHad 已有条目(每轮重扫, 因局部插入会移动后续偏移)
        entries = []
        for kd, vs, _ve, _vt in _entry_values_local(seg, rel):
            if seg[vs:vs + 1] == "[":
                entries.append((_es3_unescape_name(kd), vs, _local_span_end(seg, vs)))
        idx = next((i for i, (n, _a, _b) in enumerate(entries) if n == nm), None)
        if idx is not None:
            # 同名已装备: 往其数组里追加 cnt 份实例(定位最后实例闭花括号后插入)
            _n, va, _vacl = entries[idx]
            last = va
            for _k3, v3, _e3, _t3 in _entry_values_local(seg, va):
                if seg[v3:v3 + 1] == "{":
                    last = _local_span_end(seg, v3)
            ap = ""
            for i in range(cnt):
                ap += (",{" if i == 0 else l2 + "},{") + nl
                ap += _player_equip_fields_text(l3, l4, esc, lv, nl)
            ap += l2 + "}" + nl
            seg = seg[:last + 1] + ap + seg[last + 1:]
        else:
            entry = _player_equip_entry_text(l1, l2, l3, l4, esc, lv, cnt, nl)
            if entries:
                # 插到最后一个条目的数组闭合 `]` 后:  ],"新名":[...]
                j = entries[-1][2]
                seg = seg[:j + 1] + "," + entry + seg[j + 1:]
            else:
                # EquipHad 原本为空: 直接在 `{` 后内联新条目(第一键与 `{` 同行)
                seg = seg[:rel + 1] + entry + seg[rel + 1:]
        result[nm] = result.get(nm, 0) + cnt
    return _apply_subs(text, [(hs, he, seg)]), result


def player_equip_entries(text):
    """枚举主角 EquipHad 的条目(含「键」起点), 供删除时按原文重建。

    返回 [(干净名, 键起点, 数组开括号, 数组闭括号)]; 无 EquipHad 段返回 []。
    """
    eqo = player_equip_open(text)
    if eqo is None:
        return []
    close = _matching_end(text, eqo)
    out = []
    j = eqo + 1
    while j < close:
        if text[j] != '"':
            j += 1
            continue
        k_end = _string_end(text, j)
        name = text[j + 1:k_end - 1]
        q = k_end
        while q < close and text[q] in " \t":
            q += 1
        if q < close and text[q] == ":":
            q += 1
            while q < close and text[q] in " \t":
                q += 1
        if q < close and text[q] == "[":
            ac = _matching_end(text, q)
            out.append((_es3_unescape_name(name), j, q, ac))
            j = ac + 1
            continue
        j = k_end
    return out


def player_del_equips(text, targets):
    """删除主角 EquipHad 里的装备。

    targets: [(装备名, 实例下标)] = 只删该名下的第 idx 个实例(删掉最后一个实例时整个条目移除);
             也接受 纯名字字符串 = 删该装备的整个条目(全部实例)。
    返回 (新文本, 实际删除项 ["名#序号", ...])。

    整段按「保留条目原文」重建(每条 `"名":[实例...]` 用 `,` 连接, 与游戏写法一致),
    实例间的 `},{`、数组闭合的换行缩进都原样保留, 其余段落逐字节不动; 内部自行重新定位
    EquipHad(不依赖调用方缓存的旧偏移)。
    """
    eqo = player_equip_open(text)
    if eqo is None:
        return text, []
    eqclose = _matching_end(text, eqo)
    if eqclose <= eqo:
        return text, []
    ents = player_equip_entries(text)
    if not ents:
        return text, []
    want = {}
    for tg in (targets or []):
        if isinstance(tg, (list, tuple)) and len(tg) >= 2:
            want.setdefault(tg[0], set()).add(int(tg[1]))
        elif isinstance(tg, str) and tg:
            want[tg] = "all"
    if not want:
        return text, []
    nl = "\r\n" if "\r\n" in text else "\n"
    l2 = _line_indent(text, eqo)          # EquipHad 键所在行缩进(空字典时用它收尾)
    # 每条目的「前置分隔」= 上一条目数组闭括号之后到本条目键起点之间的原文(真实档是 `,\r\n\t\t`),
    # 重建时一并保留, 否则后续条目的键会被压到上一行的 `],` 后面(缩进丢失)。
    seps = [""] + [text[ents[i - 1][3] + 1:ents[i][1]] for i in range(1, len(ents))]
    new_ents, gone = [], []               # [(前置分隔, 条目原文)]
    for _i, (nm, ks, ao, ac) in enumerate(ents):
        sep = seps[_i]
        w = want.get(nm)
        if w is None:
            new_ents.append((sep, text[ks:ac + 1]))
            continue
        spans = _arr_spans_indexed(text, ao, ac)
        if w == "all":
            keep = []
            gone.extend("%s#%d" % (nm, i + 1) for i in range(len(spans)))
        else:
            keep = [(i, o, c) for i, (o, c) in enumerate(spans) if i not in w]
            gone.extend("%s#%d" % (nm, i + 1) for i in sorted(w) if 0 <= i < len(spans))
        if not keep:
            continue                       # 实例全删光 → 整个条目移除
        if len(keep) == len(spans):
            new_ents.append((sep, text[ks:ac + 1]))
            continue
        inner = ",".join(text[o:c + 1] for _i2, o, c in keep)
        tail = text[spans[-1][1] + 1:ac + 1]     # 末实例闭括号之后 → 数组闭括号(含换行缩进 `]`)
        new_ents.append((sep, text[ks:ao + 1] + inner + tail))
    if not gone:
        return text, []
    # 首个保留条目不带分隔, 其余各带自己的前置分隔(即使前一条目刚被删掉也依然正确, 因它是原文片段)
    body = "".join(t if i == 0 else sep + t
                   for i, (sep, t) in enumerate(new_ents)) if new_ents else (nl + l2)
    if new_ents:
        body += text[ents[-1][3] + 1:eqclose]   # 末条目 `]` 到字典 `}` 之间的原文(通常是 `\n\t\t`)
    return _apply_subs(text, [(eqo + 1, eqclose, body)]), gone


# ==================== 剧情变量(善恶值等, 存于 saveDialogue 段的自定义变量表) ====================
# 游戏把「善恶值」这类由剧情累计的数值写在 saveDialogue 段的变量表里, 其序列化形态不是
# `"名字" : 数字`, 而是「十进制字节数组」编码(因此直接搜「善恶值」是搜不到的):
#   字符串: 83,<长度>,<UTF-8 字节...>        （83 = 'S'）
#   数值  : 78,<8 字节小端 IEEE754 double>   （78 = 'N'）
#   布尔  : 66,<1 字节 0/1>                  （66 = 'B'）
#   整数  : 84,<4 字节小端 int32>             （84 = 'T'）
# 变量表 = 上述「变量名 + 数值」的成对序列, 例如:
#   83,9,229,150,132,230,129,182,229,128,188,78,0,0,0,0,0,0,28,64   → 善恶值 = 7.0
# 因此改它必须在字节层做: 先定位变量名的字节串, 再把其后 double 的 8 个字节换成新值,
# 同表里的其它变量、以及存档其它任何字节一律不动(不凭空插入不存在的变量)。
_DLG_MARKER = {83: "S", 78: "N", 66: "B", 84: "T"}   # 类型标记(十进制字节) → 类型字符
_DLG_TYPE_LEN = {"N": 8, "B": 1, "T": 4}             # 各数值类型标记之后的字节数(字符串另读长度)
_DEC_BYTE_RE = re.compile(r"\d{1,3}")


def dec_byte_text(data):
    """把字符串/字节转成存档里的「十进制字节」文本。

    例: dec_byte_text("善恶值")            -> '229,150,132,230,129,182,229,128,188'
        dec_byte_text(struct.pack("<d", 7.0)) -> '0,0,0,0,0,0,28,64'
    """
    bs = data.encode("utf-8") if isinstance(data, str) else bytes(data)
    return ",".join(str(b) for b in bs)


def _read_dec_bytes(text, i, count):
    """从 i(指向首个数字)起读 count 个逗号分隔的十进制字节; 返回 (list[int], 结束下标) 或 None。"""
    out = []
    n = len(text)
    for k in range(count):
        m = _DEC_BYTE_RE.match(text, i)
        if not m:
            return None
        v = int(m.group(0))
        if v > 255:
            return None
        out.append(v)
        i = m.end()
        if k < count - 1:
            if i >= n or text[i] != ",":
                return None
            i += 1
    return out, i


def dialogue_var_span(text, name):
    """定位「剧情变量」name(名字以十进制字节写在 saveDialogue 段的变量表里)。

    返回 (val_start, val_end, kind, value):
      val_start/val_end : 数值记号在 text 里的区间(如 '0,0,0,0,0,0,28,64')
      kind              : 'N'(double) / 'B'(bool) / 'T'(int32)
      value             : 解析出的数值
    找不到返回 None。名字之后必须紧跟「,<类型标记>,<字节...>」才算命中, 因此不会误中
    把该名字当作前缀的更长的变量名。
    """
    needle = dec_byte_text(name)
    if not needle:
        return None
    n = len(text)
    p = text.find(needle)
    while p >= 0:
        # 前一字符若是数字, 说明这次命中的是某个更长字节序列的尾部(别的变量名) → 跳过
        if p > 0 and text[p - 1].isdigit():
            p = text.find(needle, p + 1)
            continue
        i = p + len(needle)
        while i < n and text[i] in " \t\r\n":
            i += 1
        if i >= n or text[i] != ",":
            p = text.find(needle, p + 1)
            continue
        i += 1
        got = _read_dec_bytes(text, i, 1)          # 类型标记本身也是一个十进制字节
        if got is None:
            p = text.find(needle, p + 1)
            continue
        mk, i = got
        kind = _DLG_MARKER.get(mk[0])
        if kind not in _DLG_TYPE_LEN:
            p = text.find(needle, p + 1)
            continue
        while i < n and text[i] in " \t\r\n":
            i += 1
        if i < n and text[i] == ",":            # 类型标记与数值之间的分隔逗号
            i += 1
        while i < n and text[i] in " \t\r\n":
            i += 1
        got2 = _read_dec_bytes(text, i, _DLG_TYPE_LEN[kind])
        if got2 is None:
            p = text.find(needle, p + 1)
            continue
        bs, end = got2
        data = bytes(bs)
        if kind == "N":
            val = struct.unpack("<d", data)[0]
        elif kind == "B":
            val = bool(bs[0])
        else:
            val = struct.unpack("<i", data)[0]
        return i, end, kind, val
    return None


def get_dialogue_var(text, name):
    """读剧情变量 name 的值(double/int/bool); 存档里没有该变量返回 None。"""
    r = dialogue_var_span(text, name)
    return None if r is None else r[3]


def set_dialogue_var(text, name, value):
    """把剧情变量 name 的值改为 value(按它原有的类型写: N=double / B=bool / T=int32)。

    返回 (新文本, 是否发生变更); 变量不存在或新旧值相同 → 返回 (原文本, False),
    存档里其它任何字节(含同表的其它变量)原样保留。
    """
    r = dialogue_var_span(text, name)
    if r is None:
        return text, False
    val_start, val_end, kind, _old = r
    if kind == "N":
        new_raw = dec_byte_text(struct.pack("<d", float(value)))
    elif kind == "B":
        new_raw = "1" if value else "0"
    else:
        new_raw = dec_byte_text(struct.pack("<i", int(round(float(value)))))
    if new_raw == text[val_start:val_end]:
        return text, False
    return _apply_subs(text, [(val_start, val_end, new_raw)]), True


def _fmt_dlg_num(v):
    """剧情变量数值的显示文本(整数不带小数尾巴)。"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return str(int(f)) if f == int(f) else ("%g" % f)


# 主角页「剧情变量」区展示/可改的变量: (界面显示名, 存档里的变量名)
# 目前是 善恶值 —— 见喜堂善/恶线委托累计值, 游戏里以「善恶值N」的形式显示。
DIALOGUE_VARS = (("善恶值", "善恶值"),)


# ==================== 蛊虫 ChongHad + 装备技能 _SkillLv(都在 savePlayerData.value 内) ====================
# 存档规律(实测 custom0.es3):
#   savePlayerData.value 内 "ChongHad" : [ {…}, {…} ], 每条固定字段为
#     d_dataname(数据集名) / _CustomName(显示名) / _Foster / _FosterMax /
#     _TotalProperty(培养累计属性) / _Skill({"状态":累积值}) / _Preference({"状态":倍率}) /
#     _Love(bool) / _Icon + path_icon + tou/xiong/fu/chi(外观: 头/胸/腹/翅 四部位色,
#     _Icon = 四部位色 + 序号, 图标文件 = BeastSaga_Data/SaveChongIcon/<_Icon>.png) /
#     Power / Agility / PhysicalPower(力道/灵气/体魄)
#   蛊虫可用的状态种类(由存档 ChongPotHad 的 5 类虫罐 毒/穴/血/火/冰 与 Debuff_* 实测):
#     中毒 / 流血 / 着火 / 点穴 / 冰冻 —— 共 5 种(_Skill 与 _Preference 用的是同一套键)。
#   ★ 改了 Power / Agility / PhysicalPower 之后 _TotalProperty 必须写 0(游戏会重算, 留着旧值容易出错)。
#   装备 EquipHad 的每个实例里 "_SkillLv" / "_ItemSkillLv" 是「技能名 → [等级数组]」
#     (如 "提供真气":[\r\n\t\t\t\t\t\t\t7\r\n\t\t\t\t\t\t]), 技能名取自全局技能库
#     (技能名.json = 内存所有道具.json 的 dataset/skill/*)。
#   ★ v2.13.3 起技能库只保留「pass 被动/战斗」与「todu 特殊/临时」两组: 装备/蛊虫能挂的技能
#     就这两类; 生活技能天赋(lifeperkskilltesk)、工具(tool)、测试/未整理(totest) 全部排除
#     (它们既不能当被动技能挂, 也不是战斗效果, 列在候选里只会干扰选择)。

CHONG_SKILLS = ("中毒", "流血", "着火", "点穴", "冰冻")
CHONG_PROP_FIELDS = ("Power", "Agility", "PhysicalPower")
CHONG_PROP_LABELS = {"Power": "力道", "Agility": "灵气", "PhysicalPower": "体魄"}
CHONG_PROP_DEFAULT = 9999         # Power/Agility/PhysicalPower 默认值(一键默认目标)
CHONG_SKILL_DEFAULT = 9999        # _Skill 各状态默认值
CHONG_PREF_DEFAULT = 9999         # _Preference 各状态默认值
CHONG_FOSTER_MAX_DEFAULT = 9999   # _FosterMax(培养上限) 默认值: 新增蛊虫与「默认」按钮都用它
CHONG_TOTAL_RESET = 0             # 改三项属性后 _TotalProperty 恒写 0
# 外观部位色: (名字关键字, 部位色, _Icon 序号) —— 与游戏 SaveChongIcon 目录里实际存在的图标对应
CHONG_COLORS = (("银灰", "yinhui", 1), ("冰", "bing", 1), ("毒", "du", 0),
                ("穴", "xue", 1), ("血", "xie", 0), ("火", "huo", 0))
CHONG_COLOR_FALLBACK = ("baiban", 1)
# 默认图标路径前缀(与存档里的写法完全一致: 反斜杠 + 正斜杠); 实际新增时自动沿用在档里已有的前缀
CHONG_PATH_PREFIX = "D:\\/GAME_H\\/1_Playing\\/灵兽江湖\\/灵兽江湖\\/BeastSaga_Data\\/SaveChongIcon\\"
# 新增蛊虫时「基础蛊虫」名字里的元素字(去掉后作为 _CustomName)
CHONG_BASE_BODIES = ("爬虫", "螳螂", "飞虫")
EQUIP_SCALAR_FIELDS = ("_Lv", "_Durable")
EQUIP_FIELD_LABELS = {"_Lv": "等级", "_Durable": "耐久",
                      "_SkillLv": "装备技能", "_ItemSkillLv": "词条技能"}
# 技能名库(技能名.json = 内存所有道具.json 的 dataset/skill/<子目录>/<技能名>)**只保留这两组**:
#   pass = 被动/战斗技能, todu = 特殊/临时 —— 装备 _SkillLv/_ItemSkillLv 与蛊虫 _Skill/_Preference
#   能挂的只有这两类; 生活技能天赋(lifeperkskilltesk)、工具(tool)、测试/未整理(totest) 一律排除
#   (v2.13.3, 用户要求)。请在读取入口 `load_skill_categories()` 里过滤, 不要只在生成脚本里过滤——
#   这样旧版 json / 以后重新生成混入时也不会漏出到候选列表。
SKILL_KEEP_SUBS = ("pass", "todu")
SKILL_EXCLUDED_SUBS = {"lifeperkskilltesk": "生活技能天赋", "tool": "工具",
                       "totest": "测试/未整理"}

# ---- 工具栏状态灯(v2.13.1): 打开按钮左边的圆点, 颜色直观看当前文档状态 ----
STATUS_DOT_COLORS = {
    "saved": "#2e7d32",        # 绿: 已保存(内容与磁盘/来源一致)
    "unsaved": "#e53935",      # 红: 有未保存修改
    "refreshed": "#1976d2",    # 蓝: 自动刷新完成(已刷新)
    "refreshing": "#f9a825",   # 黄: 正在刷新
    None: "#9e9e9e",           # 灰: 未打开任何文档
}
STATUS_DOT_LABELS = {
    "saved": "已保存",
    "unsaved": "未保存",
    "refreshed": "已刷新",
    "refreshing": "正在刷新",
    None: "未打开",
}
STATUS_DOT_HINT = ("文档状态指示灯\n"
                   "● 绿 = 已保存(与磁盘/来源一致)\n"
                   "● 红 = 有未保存修改\n"
                   "● 黄 = 正在刷新(文件变化自动刷新中)\n"
                   "● 蓝 = 已刷新(自动刷新完成)\n"
                   "● 灰 = 未打开任何存档")


def _load_cat_json(path):
    """通用分类库读取(蛊虫名.json / 技能名.json, 结构与 道具分类.json 一致), 结果按路径缓存。"""
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
    zh = dict(zh) if isinstance(zh, dict) else {}
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
    if not cats:
        return None
    out = {"version": data.get("version", 1), "zh": zh, "cats": cats}
    _CAT_CACHE[path] = out
    return out


def _cat_all_names(data):
    """把分类库数据摊平成名字列表(跨组去重, 保序)。"""
    out = []
    for cat in (data or {}).get("cats") or []:
        for names in (cat.get("groups") or {}).values():
            for n in names:
                if n not in out:
                    out.append(n)
    return out


def get_chong_categories_path():
    """蛊虫名库路径(程序目录/蛊虫名.json)。"""
    return os.path.join(app_dir(), "蛊虫名.json")


def load_chong_categories(path=None):
    """读 蛊虫名.json(结构同 道具分类.json, 供分类树/搜索复用); 缺失/损坏返回 None。"""
    return _load_cat_json(path or get_chong_categories_path())


def load_chong_names(path=None):
    """蛊虫名扁平列表; 缺失返回 []。"""
    return _cat_all_names(load_chong_categories(path))


def get_skill_categories_path():
    """技能名库路径(程序目录/技能名.json)。"""
    return os.path.join(app_dir(), "技能名.json")


def load_skill_categories(path=None):
    """读 技能名.json(结构同 道具分类.json)并**只保留 SKILL_KEEP_SUBS 两组**; 缺失/损坏返回 None。

    v2.13.3: 装备/蛊虫能挂的技能只有「pass 被动/战斗」与「todu 特殊/临时」两类, 生活技能天赋/
    工具/测试未整理不从候选里出现(过滤放在读取入口, 旧 json 或重新生成混入也不会漏出)。
    """
    p = path or get_skill_categories_path()
    if p in _SKILL_CAT_CACHE:
        return _SKILL_CAT_CACHE[p]
    data = _load_cat_json(p)
    if data is None:
        return None
    keep = set(SKILL_KEEP_SUBS)
    cats = []
    for cat in data.get("cats") or []:
        groups = {k: v for k, v in (cat.get("groups") or {}).items() if k in keep}
        if groups:
            cats.append({"code": cat.get("code", ""), "groups": groups})
    if not cats:
        return None
    # 提示名表同样只留大分类 code 与保留组(被排除组的 "生活技能天赋/工具/测试未整理" 一并去掉)
    codes = {c["code"] for c in cats}
    zh = {k: v for k, v in (data.get("zh") or {}).items() if k in keep or k in codes}
    out = {"version": data.get("version", 1), "zh": zh, "cats": cats}
    _SKILL_CAT_CACHE[p] = out
    return out


def load_skill_names(path=None):
    """全部技能名(pass 被动/战斗 + todu 特殊/临时)扁平列表; 缺失返回 []。"""
    return _cat_all_names(load_skill_categories(path))


def skill_lib_count():
    """当前技能库条数(pass+todu; 库缺失/为空时为 0), 供界面文案动态显示。"""
    return len(load_skill_names())


def chong_visual(name):
    """按名字推断蛊虫外观部位色与 _Icon 序号: 返回 (部位色, 序号)。"""
    nm = name or ""
    for kw, color, idx in CHONG_COLORS:
        if kw and kw in nm:
            return color, idx
    return CHONG_COLOR_FALLBACK


def chong_custom_name(name):
    """由数据集名推一个短显示名(_CustomName): 去 "对战N" / "固定_" 前缀、去尾部数字、去元素首字。"""
    nm = (name or "").strip()
    if not nm:
        return nm
    m = re.match(r"^对战\d+", nm)
    if m:
        nm = nm[m.end():]
    if nm.startswith("固定_"):
        nm = nm[3:]
    nm = re.sub(r"\d+$", "", nm)
    if nm[:1] in ("冰", "毒", "穴", "血", "火") and nm[1:] in CHONG_BASE_BODIES:
        nm = nm[1:]
    return nm or (name or "")


def chong_quoted(s):
    """把一个显示名(字符串字段值)序列化成 es3 里带引号且转义好的文本。

    中文弯引号 “ ” 与 ASCII 双引号 / 反斜杠 一律按存档写法转义成 反斜杠+字符
    (游戏内存/存档里 碎“肉” 就是写成 碎\\“肉\\”)。
    """
    out = []
    for ch in (s or ""):
        out.append("\\" + ch if ch in ('"', "\\", "“", "”") else ch)
    return '"%s"' % "".join(out)


# ---- 局部(小容器)定位工具: ChongHad 很小(实测 4KB), 一律用 *_local 走局部扫描,
#      既不触发整份大档结构索引重建, 也不会把全局索引缓存挤掉。 ----
def _line_indent(text, pos):
    """pos 所在行的前导空白(缩进)。"""
    ls = text.rfind("\n", 0, pos) + 1
    return re.match(r"[ \t]*", text[ls:pos]).group(0)


def _indent_unit(ind):
    """由缩进串推一级缩进单位(制表符优先, 否则 4 空格/单字符)。"""
    if "\t" in ind:
        return "\t"
    return " " * 4 if len(ind) >= 2 else (ind[:1] or "\t")


def _chong_value_end(text, vs):
    """某字段值(数字/字符串/对象/数组/真假)的结束下标。"""
    c = text[vs:vs + 1]
    if c in "{[":
        return _local_span_end(text, vs) + 1
    if c == '"':
        return _string_end(text, vs)
    tok = _num_token(text, vs)
    if tok:
        return tok[1]
    j = vs
    n = len(text)
    while j < n and text[j] not in ",}] \t\r\n":
        j += 1
    return j


def _chong_field_span(text, obj_open, field):
    """对象 obj_open 内字段 field 的值区间 (起, 止); 缺失返回 None。

    走整档结构索引(_entry_values): 索引已热时是二分+线性扫(毫秒级), 冷时构建一次后
    后续全部命中缓存; 蛊虫/装备条目虽小, 但逐字符局部扫描在大档上按“每次字段读一遍”
    累积起来很慢(实测 12 条蛊虫 177ms), 因此这里统一用索引版。
    """
    for k, vs, _ve, _vt in _entry_values(text, obj_open):
        if k == field:
            return vs, _chong_value_end(text, vs)
    return None


def _chong_direct_str(text, obj_open, field):
    """读对象内直接字符串字段(去引号并还原转义); 非字符串/缺失返回 None。"""
    sp = _chong_field_span(text, obj_open, field)
    if sp is None or text[sp[0]:sp[0] + 1] != '"':
        return None
    return _es3_unescape_name(text[sp[0] + 1:sp[1] - 1])


def _chong_dict_text(pairs, indent, nl):
    """按存档形态生成状态字典文本: {"中毒":9999,"流血":9999 + 换行 + 缩进 + }。"""
    body = ",".join('"%s":%s' % (_es3_escape_name(str(k)), v) for k, v in pairs)
    return "{" + body + nl + indent + "}"


# ---------------- 蛊虫: 读 ----------------
def chong_open(text):
    """ChongHad 数组的开括号下标; 缺失返回 None。"""
    o = _player_had_field_open(text, "ChongHad")
    if o is not None and text[o:o + 1] == "[":
        return o
    return None


def chong_records(text):
    """枚举 ChongHad 全部蛊虫: [(序号, 数据集名, 显示名, 对象开括号)]。"""
    out = []
    arr = chong_open(text)
    if arr is None:
        return out
    i = 0
    for _k, vs, _ve, _vt in _entry_values_local(text, arr):
        if text[vs:vs + 1] != "{":
            continue
        dn = _chong_direct_str(text, vs, "d_dataname") or ""
        cn = _chong_direct_str(text, vs, "_CustomName") or ""
        out.append((i, dn, cn or dn, vs))
        i += 1
    return out


def chong_field(text, obj_open, field):
    """读某条蛊虫的字段原值文本; 缺失返回 None。"""
    sp = _chong_field_span(text, obj_open, field)
    return None if sp is None else text[sp[0]:sp[1]]


def chong_entry_open(text, idx):
    """第 idx 条蛊虫的对象开括号(不读字段, 只定位, 大档毫秒级); 越界/无段返回 None。

    文本被改动后条目偏移会整体位移, 因此**每次操作前用它重新定位**, 而不是长期复用旧下标。
    """
    arr = chong_open(text)
    if arr is None or idx < 0:
        return None
    k = 0
    for _key, vs, _ve, _vt in _entry_values_local(text, arr):
        if text[vs:vs + 1] != "{":
            continue
        if k == idx:
            return vs
        k += 1
    return None


def chong_dict_pairs(text, obj_open, field):
    """读某条蛊虫的 _Skill / _Preference: [(状态, 原值文本)]; 字段缺失/非字典返回 []。"""
    sp = _chong_field_span(text, obj_open, field)
    if sp is None or text[sp[0]:sp[0] + 1] != "{":
        return []
    out = []
    for k, vs, _ve, _vt in _entry_values_local(text, sp[0]):
        out.append((k, text[vs:_chong_value_end(text, vs)]))
    return out


def chong_model(text):
    """蛊虫页数据模型(纯计算, 可在后台线程跑): 每条蛊虫的字段 + 技能表。

    返回 [{idx, open, dataname, custom, love, foster, fostermax, total,
           power, agility, physical, skill:[(名,值)], pref:[(名,值)],
           has_skill, has_pref}, ...]
    """
    out = []
    for idx, dn, cn, o in chong_records(text):
        out.append(chong_entry_model(text, o, idx, dn, cn))
    return out


def chong_entry_model(text, obj_open, idx=0, dataname=None, custom=None):
    """读单条蛊虫的完整字段(供“改动后只刷新当前条”用, 不必整模重建)。"""
    if dataname is None:
        dataname = _chong_direct_str(text, obj_open, "d_dataname") or ""
    if custom is None:
        custom = _chong_direct_str(text, obj_open, "_CustomName") or ""
    rec = {"idx": idx, "open": obj_open, "dataname": dataname, "custom": custom,
           "love": (chong_field(text, obj_open, "_Love") or "").strip() == "true",
           "skill": chong_dict_pairs(text, obj_open, "_Skill"),
           "pref": chong_dict_pairs(text, obj_open, "_Preference")}
    for f in ("_Foster", "_FosterMax", "_TotalProperty") + CHONG_PROP_FIELDS:
        rec[f] = chong_field(text, obj_open, f)
    rec["has_skill"] = _chong_field_span(text, obj_open, "_Skill") is not None
    rec["has_pref"] = _chong_field_span(text, obj_open, "_Preference") is not None
    return rec


# ---------------- 蛊虫: 写 ----------------
def chong_entry_edit(text, obj_open, scalars=None, dicts=None):
    """改一条蛊虫。

    scalars: {字段: 已序列化值文本} —— 数字写 "9999"; 字符串用 chong_quoted(s); 布尔写
             "true"/"false"。**只要其中出现 Power/Agility/PhysicalPower 任一, 就自动把
             _TotalProperty 写 0**(游戏会重算培养累计属性, 留旧值容易出错)。
    dicts  : {字段名: {状态: 值文本}} —— 已存在的状态改值, 缺失的状态补写(保持原顺序, 新键追加)。
             字段本身不存在时(如某蛊虫没有 _Preference)会在条目末尾自动补一个新的。
    返回 (新文本, 是否发生变更)。
    """
    o = obj_open
    if o is None:
        return text, False
    nl = "\r\n" if "\r\n" in text else "\n"
    subs = []
    scal = dict(scalars or {})
    # ★ 三项属性: 只有“确实改动”时才把 _TotalProperty 写 0(同值不动, 避免无谓改动)
    _reset_total = False
    for f in CHONG_PROP_FIELDS:
        if f not in scal:
            continue
        sp = _chong_field_span(text, o, f)
        if sp is None or text[sp[0]:sp[1]] != str(scal[f]):
            _reset_total = True
            break
    if _reset_total:
        scal["_TotalProperty"] = str(CHONG_TOTAL_RESET)
    for field, raw in scal.items():
        sp = _chong_field_span(text, o, field)
        if sp is None:                       # 字段不存在: 不凭空补(除 _TotalProperty, 见下)
            continue
        if text[sp[0]:sp[1]] == str(raw):
            continue
        subs.append((sp[0], sp[1], str(raw)))
    # _TotalProperty 缺失时补写一个(改了三项属性必须为 0)
    if scal.get("_TotalProperty") is not None and _chong_field_span(text, o, "_TotalProperty") is None:
        ent = _entry_values_local(text, o)
        if ent:
            _k, vs, _ve, _vt = ent[-1]
            ve = _chong_value_end(text, vs)
            l4 = _line_indent(text, vs)
            subs.append((ve, ve, "," + nl + l4 + '"_TotalProperty" : %d' % CHONG_TOTAL_RESET))
    for field, upd in (dicts or {}).items():
        if not upd:
            continue
        sp = _chong_field_span(text, o, field)
        if sp is not None and text[sp[0]:sp[0] + 1] == "{":
            l4 = _line_indent(text, sp[0])
            pairs = []
            seen = set()
            for k, vs, _ve, _vt in _entry_values_local(text, sp[0]):
                ve = _chong_value_end(text, vs)
                seen.add(k)
                nv = upd.get(k)
                pairs.append((k, str(nv) if nv is not None else text[vs:ve]))
            for k, v in upd.items():
                if k not in seen:
                    pairs.append((k, str(v)))
            new = _chong_dict_text(pairs, l4, nl)
            if new != text[sp[0]:sp[1]]:
                subs.append((sp[0], sp[1], new))
        else:
            ent = _entry_values_local(text, o)
            if not ent:
                continue
            _k, vs, _ve, _vt = ent[-1]
            ve = _chong_value_end(text, vs)
            l4 = _line_indent(text, vs)
            pairs = [(k, str(v)) for k, v in upd.items()]
            subs.append((ve, ve, "," + nl + l4 + '"%s" : %s'
                         % (field, _chong_dict_text(pairs, l4, nl))))
    if not subs:
        return text, False
    return _apply_subs(text, subs), True


def chong_path_prefix(text):
    """沿用在档里已有的 path_icon 前缀(到 SaveChongIcon 后的分隔符为止); 没有则用默认前缀。

    注意: 存档里路径写作 `D:\\/GAME_H\\/...\\/SaveChongIcon\\/xxx.png` —— "SaveChongIcon" 后面是
    **两个**字符(`\\` + `/`), 所以要把后随的一串 `\\`/`/` 全部吃进前缀, 否则拼出的图标路径会少一个斜杠。
    """
    for _i, _dn, _cn, o in chong_records(text):
        p = _chong_direct_str(text, o, "path_icon") or ""
        if "SaveChongIcon" not in p:
            continue
        k = p.index("SaveChongIcon") + len("SaveChongIcon")
        while k < len(p) and p[k] in "\\/":
            k += 1
        return p[:k]
    return CHONG_PATH_PREFIX


def _chong_spec_prop(spec, field):
    """取新增蛊虫 spec 里的三项属性值: 兼容 'Power'/'power'/'physicalpower' 等不同写法。

    (AddChongDialog.spec_options 用小写全名 `physicalpower`, 手写调用常用 `physical` —— 两种都认,
    否则在对话框里改的「体魄」会被静默忽略、仍用默认值。)
    """
    for k in (field, field.lower()):
        if k in spec:
            try:
                return int(spec[k])
            except (TypeError, ValueError):
                return CHONG_PROP_DEFAULT
    return CHONG_PROP_DEFAULT


def _chong_entry_text(spec, l3, l4, nl, first=True):
    """生成一条 ChongHad 条目文本(含开括号前的分隔)。

    first=True : 数组里的第一条 —— 以 换行+缩进+`{` 开头(游戏存档首条即此写法)
    first=False: 后续条目     —— 以 `,{` 开头(游戏存档后续条目写作 `},{`, 逗号紧接花括号)
    结尾统一为 换行+缩进+`}`。
    """
    name = spec.get("name") or ""
    dn = _es3_escape_name(name)
    cn = _es3_escape_name(spec.get("custom") or chong_custom_name(name))
    color, cidx = spec.get("visual") or chong_visual(name)
    icon = color * 4 + str(cidx)
    prefix = spec.get("path_prefix") or CHONG_PATH_PREFIX
    skills = spec.get("skills") or {}
    prefs = spec.get("prefs") or {}
    lines = [
        '"d_dataname" : "%s"' % dn,
        '"_CustomName" : "%s"' % cn,
        '"_Foster" : %d' % int(spec.get("foster", 0)),
        '"_FosterMax" : %d' % int(spec.get("foster_max", CHONG_FOSTER_MAX_DEFAULT)),
        '"_TotalProperty" : %d' % CHONG_TOTAL_RESET,
        '"_Skill" : %s' % _chong_dict_text(list(skills.items()), l4, nl),
        '"_Preference" : %s' % _chong_dict_text(list(prefs.items()), l4, nl),
        '"_Love" : %s' % ("true" if spec.get("love") else "false"),
        '"_Icon" : "%s"' % icon,
        '"path_icon" : "%s"' % (prefix + icon + ".png"),
        '"tou" : "%s"' % color,
        '"xiong" : "%s"' % color,
        '"fu" : "%s"' % color,
        '"chi" : "%s"' % color,
        '"Power" : %d' % _chong_spec_prop(spec, "Power"),
        '"Agility" : %d' % _chong_spec_prop(spec, "Agility"),
        '"PhysicalPower" : %d' % _chong_spec_prop(spec, "PhysicalPower"),
    ]
    head = (nl + l3 + "{") if first else ",{"
    return head + nl + ("," + nl).join(l4 + x for x in lines) + nl + l3 + "}"


def chong_add(text, specs):
    """新增蛊虫(每只 = 一条独立条目, 与装备一样不堆叠)。

    specs: [ {name, count=1, custom, power, agility, physical, foster, foster_max,
              love, skills:{状态:值}, prefs:{状态:值}}, ... ]
    返回 (新文本, {名称: 实际添加只数}); 没有 ChongHad 段返回 (原文本, {})。
    缩进/换行自动沿用存档; 只在 ChongHad 数组段内局部插入, 其余内容原样保留。
    """
    arr = chong_open(text)
    if arr is None:
        return text, {}
    nl = "\r\n" if "\r\n" in text else "\n"
    l2 = _line_indent(text, arr)
    unit = _indent_unit(l2)
    l3 = l2 + unit
    l4 = l3 + unit
    prefix = chong_path_prefix(text)
    ents = []
    added = {}
    for spec in specs:
        nm = (spec.get("name") or "").strip()
        if not nm:
            continue
        cnt = max(1, int(spec.get("count", 1)))
        s2 = dict(spec)
        s2["name"] = nm
        s2["path_prefix"] = prefix
        for _i in range(cnt):
            ents.append(s2)
        added[nm] = added.get(nm, 0) + cnt
    if not ents:
        return text, {}
    objs = [vs for _k, vs, _ve, _vt in _entry_values_local(text, arr) if text[vs:vs + 1] == "{"]
    if objs:
        # 已有条目: 每条新增都以 `,{` 开头(游戏写法), 直接接在最后一条的 `}` 之后
        last = _local_span_end(text, objs[-1])
        ins = "".join(_chong_entry_text(s, l3, l4, nl, first=False) for s in ents)
        return _apply_subs(text, [(last + 1, last + 1, ins)]), added
    # 空数组: 首条用 换行+缩进+`{` 开头(游戏首条写法), 其余仍以 `,{` 接在后面
    ins = _chong_entry_text(ents[0], l3, l4, nl, first=True) + \
        "".join(_chong_entry_text(s, l3, l4, nl, first=False) for s in ents[1:])
    return _apply_subs(text, [(arr + 1, arr + 1, ins)]), added


def chong_del(text, obj_opens):
    """删除若干条蛊虫(obj_opens = 条目对象开括号列表)。返回 (新文本, 实际删除条数)。

    实现: 把整个数组体重建为「保留下来的条目原文」(逐字节保留每条自身的字段文本),
    首条用 换行+缩进+`{` 开头、其余用 `,{`, 避免多条一起删时逗号归属重叠。
    """
    arr = chong_open(text)
    drop = {o for o in (obj_opens or []) if o is not None}
    if arr is None or not drop:
        return text, 0
    recs = chong_records(text)
    if not recs:
        return text, 0
    nl = "\r\n" if "\r\n" in text else "\n"
    l3 = _line_indent(text, recs[0][3])
    kept = []
    for _i, _dn, _cn, o in recs:
        if o in drop:
            continue
        kept.append(text[o:_local_span_end(text, o) + 1])
    gone = len(recs) - len(kept)
    if not gone:
        return text, 0
    last_close = _local_span_end(text, recs[-1][3])
    if kept:
        body = (nl + l3 + kept[0]) + "".join("," + e for e in kept[1:])
    else:
        body = nl + _line_indent(text, arr)      # 空数组: [<换行><缩进>]
    return _apply_subs(text, [(arr + 1, last_close + 1, body)]), gone


# ---------------- 装备技能/属性(EquipHad 实例) ----------------
def equip_index(text):
    """枚举主角 EquipHad: [(装备名, 实例数组开括号, [(实例开, 实例闭), ...])]。"""
    o = player_equip_open(text)
    if o is None:
        return []
    out = []
    for nm, arr_open, _arr_close in _sell_equip_entries_in(text, o):
        out.append((nm, arr_open, _arr_instance_spans(text, arr_open)))
    return out


def equip_skill_pairs(text, inst_open, field):
    """读某装备实例的 _SkillLv / _ItemSkillLv: [(技能名, [等级…])] (值在存档里是数组)。"""
    sp = _chong_field_span(text, inst_open, field)
    if sp is None or text[sp[0]:sp[0] + 1] != "{":
        return []
    out = []
    for k, vs, _ve, _vt in _entry_values_local(text, sp[0]):
        vals = []
        if text[vs:vs + 1] == "[":
            for _k2, vs2, _ve2, _vt2 in _entry_values_local(text, vs):
                tok = _num_token(text, vs2)
                if tok:
                    vals.append(int(float(tok[0])))
        out.append((k, vals))
    return out


def _equip_skill_value_text(vals, indent, unit, nl):
    """按存档形态生成技能等级数组文本。

    真实档写法(字段 "_SkillLv" 行缩进 5 制表符): {"提供真气":[<换行><7 制表符>7<换行><6 制表符>]
    —— 即 值 = 字段缩进+2 级、`]` = 字段缩进+1 级、`}` = 字段缩进(见 _equip_skill_dict_text)。
    """
    ind_v = indent + unit * 2
    ind_b = indent + unit
    body = ("," + nl + ind_v).join(str(int(v)) for v in (vals or []))
    return "[" + nl + ind_v + body + nl + ind_b + "]"


def _equip_skill_dict_text(pairs, indent, unit, nl):
    """按存档形态生成装备技能字典文本: {"提供真气":[<换行>7<换行>] + 换行 + 缩进 + }。"""
    body = ("," + nl + indent).join(
        '"%s":%s' % (_es3_escape_name(k), _equip_skill_value_text(v, indent, unit, nl))
        for k, v in pairs)
    return "{" + body + nl + indent + "}"


def equip_dict_write(text, inst_open, field, pairs):
    """把某装备实例的 field(技能字典)整体写为 pairs(技能名→等级数组)。

    字段缺失时在实例末尾自动补一个。返回 (新文本, 是否变更)。
    """
    o = inst_open
    if o is None:
        return text, False
    nl = "\r\n" if "\r\n" in text else "\n"
    sp = _chong_field_span(text, o, field)
    if sp is not None and text[sp[0]:sp[0] + 1] == "{":
        ind = _line_indent(text, sp[0])
        new = _equip_skill_dict_text(pairs, ind, _indent_unit(ind), nl)
        if new == text[sp[0]:sp[1]]:
            return text, False
        return _apply_subs(text, [(sp[0], sp[1], new)]), True
    ent = _entry_values_local(text, o)
    if not ent:
        return text, False
    _k, vs, _ve, _vt = ent[-1]
    ve = _chong_value_end(text, vs)
    ind = _line_indent(text, vs)
    ins = "," + nl + ind + '"%s" : %s' % (field, _equip_skill_dict_text(
        pairs, ind, _indent_unit(ind), nl))
    return _apply_subs(text, [(ve, ve, ins)]), True


def equip_set_skill(text, inst_open, field, updates):
    """改某装备实例 field 里若干技能的等级(已存在→改; 缺失→新增)。

    updates: {技能名: [等级…] 或 单个等级}; 返回 (新文本, 是否变更)。
    """
    upd = {}
    for k, v in (updates or {}).items():
        if not k:
            continue
        upd[k] = list(v) if isinstance(v, (list, tuple)) else [int(v)]
    if not upd:
        return text, False
    cur = equip_skill_pairs(text, inst_open, field)
    pairs = []
    seen = set()
    for k, vals in cur:
        seen.add(k)
        pairs.append((k, upd[k] if k in upd else vals))
    for k, v in upd.items():
        if k not in seen:
            pairs.append((k, v))
    return equip_dict_write(text, inst_open, field, pairs)


def equip_del_skill(text, inst_open, field, names):
    """删除某装备实例 field 里的若干技能条目。返回 (新文本, 实际删除名列表)。"""
    drop = {n for n in (names or []) if n}
    if not drop:
        return text, []
    cur = equip_skill_pairs(text, inst_open, field)
    pairs = [(k, v) for k, v in cur if k not in drop]
    gone = [k for k, _v in cur if k in drop]
    if not gone:
        return text, []
    nt, _ch = equip_dict_write(text, inst_open, field, pairs)
    return nt, gone


def equip_set_scalar(text, inst_open, field, raw):
    """把某装备实例的数字字段(如 _Lv / _Durable)改为 raw。返回 (新文本, 是否变更)。"""
    if inst_open is None:
        return text, False
    sp = _chong_field_span(text, inst_open, field)
    if sp is None or text[sp[0]:sp[1]] == str(raw):
        return text, False
    return _apply_subs(text, [(sp[0], sp[1], str(raw))]), True


def equip_skill_model(text):
    """装备页数据模型(纯计算, 可在后台线程跑): [(装备名, [(实例开, 实例闭), ...])]。

    走整档结构索引(_matching_end): 真实档 EquipHad 有 500KB / 3000+ 实例,
    逐字符局部扫描一次要 1.3s, 索引热时是毫秒级(打开大档时后台已建好索引)。
    """
    o = player_equip_open(text)
    if o is None:
        return []
    close = _matching_end(text, o)
    out = []
    j = o + 1
    while j < close:
        c = text[j]
        if c != '"':
            j += 1
            continue
        k_end = _string_end(text, j)
        name = text[j + 1:k_end - 1]
        q = k_end
        while q < close and text[q] in " \t":
            q += 1
        if q < close and text[q] == ":":
            q += 1
            while q < close and text[q] in " \t":
                q += 1
        if q < close and text[q] == "[":
            ac = _matching_end(text, q)
            out.append((_es3_unescape_name(name), _arr_spans_indexed(text, q, ac)))
            j = ac + 1
            continue
        j = k_end
    return out


def _arr_spans_indexed(text, arr_open, arr_close):
    """数组(arr_open 为 `[`, arr_close 为其闭方括号)内顶层对象实例的 (开, 闭) 区间。

    用整档结构索引配平每个实例(`_matching_end`), 大数组也快。
    """
    spans = []
    j = arr_open + 1
    while j < arr_close:
        c = text[j]
        if c == '"':
            j = _string_end(text, j)
        elif c == "{":
            e = _matching_end(text, j)
            spans.append((j, e))
            j = e + 1
        else:
            j += 1
    return spans


def equip_name_spans(text, name):
    """按装备名重新定位它的全部实例区间 [(开, 闭)](不整表重建, 大档毫秒级)。

    文本改动后偏移会变, 因此**每次选中/写入前都按名字重定位**, 而不是复用旧坐标。
    """
    arr = _equip_name_array(text, name)
    if arr is None:
        return []
    return _arr_spans_indexed(text, arr, _matching_end(text, arr))


def _equip_name_array(text, name):
    """返回 EquipHad 里某装备名的实例数组 `[` 下标; 找不到返回 None。"""
    eqo = player_equip_open(text)
    if eqo is None:
        return None
    eq_end = _matching_end(text, eqo)
    needle = '"%s"' % _es3_escape_name(name or "")
    p = text.find(needle, eqo, eq_end if eq_end > eqo else len(text))
    if p < 0:
        return None
    q = p + len(needle)
    while q < len(text) and text[q] in " \t":
        q += 1
    if q >= len(text) or text[q] != ":":
        return None
    q += 1
    while q < len(text) and text[q] in " \t":
        q += 1
    if q >= len(text) or text[q] != "[":
        return None
    return q


def equip_instance_open(text, name, idx):
    """按「装备名 + 第几个实例」重新定位实例开括号; 找不到返回 None。"""
    spans = equip_name_spans(text, name)
    if 0 <= idx < len(spans):
        return spans[idx][0]
    return None


# ==================== 主角/队友 功法段(v2.14.0) ====================
# 存档规律(实测 custom0.es3; 主角段在 savePlayerData.value 内, 队友段在 saveFriendData 各角色对象内
# 且段名前面多一个下划线):
#   InKangFuHad    ← dataset/kangfu/inkangfu/*          内功(200)
#   KangFuHad      ← dataset/kangfu/kangfu/*            武功(595)
#   KangFuSkillHad ← dataset/kangfu/uniqueskill/jue/*   绝技(177)
#   KangFuQingHad  ← dataset/kangfu/uniqueskill/qing/*  轻功(73)
# ★ 一个功法属于哪一段**由它在 dataframe 里的目录决定**(即 内存所有道具.json 的 dataset/kangfu/ 下
#   的哪一支), 与名字无关 —— 所以「内功/武功/绝技/轻功」四支各写各的段, 不会混。
#   实测: 主角 KangFuHad 里 211 条名字 100% 落在 dataset/kangfu/kangfu/*;
#         KangFuSkillHad 85 条 100% 落在 uniqueskill/jue/*; KangFuQingHad 54 条 100% 落在 uniqueskill/qing/*;
#         InKangFuHad 66 条 100% 落在 inkangfu/*。
#   字典键名 = 条目里的 _Name = 库里的名字(带前导品级数字, 如 "5大慈大悲千叶手"), 一个键一条。
#   条目之间是 },"下一名":{ (无换行、无缩进); 段闭合在段键行的缩进处(空段形如 {"…" : {\n\t\t},)。
#   条目字段(与段类型一一对应, 新增时按此模板写):
#     InKangFuHad    : _Lv / _Name / _DressType / _DressKangFu[] / _DressQuickKangFu{1:""..10:""} /
#                      _DressBigLoop[] / _DressSmallLoop[] / _DressKangFuQing
#     KangFuHad      : _Lv / _DressType / _Name / _Exp / _AddLv / HaveShanHaiLu[]
#     KangFuSkillHad : _Lv / _DressType / _Name
#     KangFuQingHad  : _Lv / _DressType / _Name
KANGFU_SEGS = (("InKangFuHad", "内功", "inkangfu"),
               ("KangFuHad", "武功", "kangfu"),
               ("KangFuSkillHad", "绝技", "jue"),
               ("KangFuQingHad", "轻功", "qing"))
KANGFU_ADD_CATS = frozenset(c for _s, _t, c in KANGFU_SEGS)
KANGFU_SEG_OF_CODE = {c: s for s, _t, c in KANGFU_SEGS}
KANGFU_TITLE_OF_SEG = {s: t for s, t, _c in KANGFU_SEGS}
KANGFU_SEG_ORDER = tuple(s for s, _t, _c in KANGFU_SEGS)
KANGFU_DEFAULT_LV = 1     # 新增功法的 _Lv 默认值
_KANGFU_NORM_RE = re.compile(r"[\s\u200b-\u200f\ufeff]+")


def _kangfu_norm(name):
    """功法名归一化(去所有空白与零宽字符), 只用于「这条是不是已经学了」的比较。"""
    return _KANGFU_NORM_RE.sub("", name or "")


def get_kangfu_categories_path():
    """功法名库路径(程序目录/功法名.json)。"""
    return os.path.join(app_dir(), "功法名.json")


def load_kangfu_categories(path=None):
    """读 功法名.json(结构同 道具分类.json, 供分类树/搜索复用); 缺失/损坏返回 None。"""
    data = _load_cat_json(path or get_kangfu_categories_path())
    if data is None:
        return None
    cats = [c for c in data.get("cats") or [] if c.get("code") in KANGFU_ADD_CATS]
    if not cats:
        return None
    return {"version": data.get("version", 1), "zh": data.get("zh") or {}, "cats": cats}


def load_kangfu_names(path=None):
    """全部功法名(内功+武功+绝技+轻功)扁平列表; 缺失返回 []。"""
    return _cat_all_names(load_kangfu_categories(path))


def kangfu_lib_count():
    """当前功法库条数(库缺失/为空时为 0), 供界面文案动态显示。"""
    return len(load_kangfu_names())


# ==================== 功法黑名单(功法黑名单.json, v2.15.0) ====================
# 用途: 记录「一学就卡死 / 有问题」的功法(用户实测)。加进去以后:
#   ① 「＋ 添加功法…」的候选里**完全不显示**(眼不见心不烦, 不会手滑选中);
#   ② 主角/队友都不会被添加(即便名字被别处传进来, 也会被拦下);
#   ③ 已学列表里会标注「★ 在黑名单」, 提醒你那是可疑功法。
# 用户意图: 先把已知会卡死的功法列进去避开, 以后有空再逐条验证到底是「剧情还没到」
#   还是别的原因 —— 所以每条可以写备注(现象/猜测), 记在 json 里。
# 数据与存档无关(程序级), 存程序目录, 换档/重开程序都生效。

def get_kangfu_blacklist_path():
    """功法黑名单路径(程序目录/功法黑名单.json)。"""
    return os.path.join(app_dir(), "功法黑名单.json")


def load_kangfu_blacklist(path=None):
    """读功法黑名单: 返回 [{"name": 名, "note": 备注}](保持文件顺序); 缺失/损坏返回 []。

    兼容两种写法: {"items":[{"name":..,"note":..}, ...]} 与 ["名1", "名2"](手写简写)。
    名字按 `_kangfu_norm` 去重(带零宽字符/空白的重复条目只留第一条)。
    """
    path = path or get_kangfu_blacklist_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    items = data.get("items") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    out = []
    seen = set()
    for it in items:
        if isinstance(it, str):
            nm, note = it, ""
        elif isinstance(it, dict):
            nm, note = it.get("name"), it.get("note") or ""
        else:
            continue
        nm = str(nm or "").strip()
        key = _kangfu_norm(nm)
        if not nm or not key or key in seen:
            continue
        seen.add(key)
        out.append({"name": nm, "note": str(note)})
    return out


def save_kangfu_blacklist(items, path=None):
    """把黑名单原子写入 json(临时文件 + os.replace); 返回 (是否成功, 路径或错误消息)。"""
    path = path or get_kangfu_blacklist_path()
    rows = [{"name": str(it.get("name") or "").strip(), "note": str(it.get("note") or "")}
            for it in (items or []) if str(it.get("name") or "").strip()]
    data = {"version": 1, "count": len(rows),
            "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "note": "本文件由程序「功法黑名单…」维护: 列入的功法在添加候选里不显示、不会被加给任何角色。",
            "items": rows}
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except OSError as e:
        return False, str(e)
    return True, path


def kangfu_blacklist_keys(items):
    """黑名单的归一化名集合(判「这门功法在黑名单里吗」用)。"""
    return {_kangfu_norm(it.get("name")) for it in (items or []) if it.get("name")}


def filter_cat_data(data, hidden_keys):
    """复制分类库数据并剔除隐藏名(黑名单): 分类树计数与右侧候选同时生效, 原数据不动。

    返回 (新数据 or None, 被剔除的名字数)。hidden_keys 传归一化名集合(或原名集合)。
    """
    if not data or not hidden_keys:
        return data, 0
    hid = {_kangfu_norm(k) for k in hidden_keys if k}
    cats = []
    dropped = 0
    for cat in data.get("cats") or []:
        groups = {}
        for rel, names in (cat.get("groups") or {}).items():
            keep = [n for n in names if _kangfu_norm(n) not in hid]
            dropped += len(names) - len(keep)
            if keep:
                groups[rel] = keep
        if groups:
            cats.append({"code": cat.get("code"), "groups": groups})
    if not cats:
        return None, dropped
    return {"version": data.get("version", 1), "zh": data.get("zh") or {}, "cats": cats}, dropped


def kangfu_index(data=None):
    """由功法库建「归一化名 → 段字段」与「归一化名 → 原名」两个索引。"""
    d = data if data is not None else load_kangfu_categories()
    seg_of = {}
    raw_of = {}
    for cat in (d or {}).get("cats") or []:
        seg = KANGFU_SEG_OF_CODE.get(cat.get("code"))
        if not seg:
            continue
        for names in cat.get("groups", {}).values():
            for n in names:
                k = _kangfu_norm(n)
                if k and k not in seg_of:
                    seg_of[k] = seg
                    raw_of[k] = n
    return seg_of, raw_of


def kangfu_seg_of_name(name, seg_of=None):
    """某个功法名属于哪一段(InKangFuHad/KangFuHad/KangFuSkillHad/KangFuQingHad); 库中无该名返回 None。"""
    if seg_of is None:
        seg_of = kangfu_index()[0]
    return seg_of.get(_kangfu_norm(name))


def _kangfu_field_open(text, container_open, seg, close=None):
    """在角色容器(container_open 开括号)内定位功法段 seg 的字典 `{`。

    返回 (实际字段名, 开括号下标); 该角色没有这段返回 (None, None)。
    队友用 `_段名`(如 _KangFuHad)、主角用无下划线版, 两个都试 —— 只在**本角色容器内**查找,
    不会定位到别的角色的同名段; 也不用整档 `_entry_values`(段在大容器里, 逐条扫太慢)。
    """
    if close is None:
        close = _matching_end(text, container_open)
    if close <= container_open:
        close = len(text)
    for field in ("_" + seg, seg):
        needle = '"%s"' % field
        p = text.find(needle, container_open, close)
        while p >= 0:
            q = p + len(needle)
            while q < close and text[q] in " \t":
                q += 1
            if q < close and text[q] == ":":
                q += 1
                while q < close and text[q] in " \t":
                    q += 1
            if q < close and text[q] == "{":
                return field, q
            p = text.find(needle, p + 1, close)
    return None, None


def _kangfu_entries(text, open_i):
    """枚举一个功法段字典内的条目: [(干净名, 键起点, 值开括号, 值闭括号)]。

    open_i 必须指向段字典的 `{`。局部扫描(段通常几 KB~几十 KB), 不触发整档索引重建。
    """
    close = _local_span_end(text, open_i)
    out = []
    j = open_i + 1
    while True:
        j = text.find('"', j)
        if j < 0 or j >= close:
            break
        k_end = _string_end(text, j)
        q = k_end
        while q < close and text[q] in " \t":
            q += 1
        if q < close and text[q] == ":":
            q += 1
            while q < close and text[q] in " \t":
                q += 1
            if q < close and text[q] == "{":
                vc = _local_span_end(text, q)
                out.append((_es3_unescape_name(text[j + 1:k_end - 1]), j, q, vc))
                j = vc + 1
                continue
        j = k_end
    return out


def kangfu_records(text, container_open):
    """枚举某角色(container_open 开括号)现有功法。

    返回 [(段字段, 段标题, 干净名, 键起点, 值开括号, 值闭括号)], 按 内功/武功/绝技/轻功 顺序。
    段不存在则跳过。
    """
    out = []
    if container_open is None:
        return out
    close = _matching_end(text, container_open)
    for seg in KANGFU_SEG_ORDER:
        _f, o = _kangfu_field_open(text, container_open, seg, close)
        if o is None:
            continue
        title = KANGFU_TITLE_OF_SEG[seg]
        for nm, ks, vs, ve in _kangfu_entries(text, o):
            out.append((seg, title, nm, ks, vs, ve))
    return out


def kangfu_brief(text, container_open):
    """轻量版: 只要 [(段字段, 段标题, 干净名)], 供建页/统计(不含偏移)。"""
    return [(s, t, n) for s, t, n, _ks, _vs, _ve in kangfu_records(text, container_open)]


# ---- 已装备的功法(装备对象, **不在** 各 *Had 段里; v2.14.1) ----
# 实测 custom0.es3: 角色容器(主角 savePlayerData.value / 队友角色对象)里直接有这几个字段
# (队友带一个下划线前缀, 主角不带):
#   DressInKangFuName  当前装备的内功名(字符串; 没装备时是 null)
#   DressInKangFu      当前装备的内功对象: _Lv / _Name / _DressType / _DressKangFu[] /
#                      _DressQuickKangFu{1:""…10:""} / _DressBigLoop[] / _DressSmallLoop[] / _DressKangFuQing
#                      —— _DressKangFu[] = 该内功上已装备的武功, _DressQuickKangFu = 已装备的快捷武功,
#                         _DressKangFuQing = 已装备的轻功
#   DressKangFu / DressQuickKangFu / DressKangFuQing   已装备的武功 / 快捷槽 / 轻功
# ★ 关键: 这些名字**通常不在** InKangFuHad / KangFuHad / KangFuSkillHad / KangFuQingHad 段里
#   (实测前 5 名角色的 19 个装备名, 0 个出现在对应段内)。往段里再添加同名条目就会变成
#   「同名的两份」→ 游戏里这门功法**卸不下来 / 切不走**(用户实测反馈), 所以添加时必须跳过。
_KANGFU_DRESS_KEY_RE = re.compile(r"^_?Dress[A-Za-z]*KangFu[A-Za-z]*$")
_KANGFU_STR_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')
_KANGFU_PLAIN_ID_RE = re.compile(r"[A-Za-z0-9_]+$")   # 纯英文标识符(字段键名) 不是功法名


def kangfu_dressed(text, container_open):
    """读某角色「已装备」的功法名(内功 / 已装备的武功 / 快捷武功 / 轻功)。

    返回 (已装备的内功名 or None, {归一化名: 原名})。
    只读角色容器**直接**的 Dress*KangFu* 字段(不深入各 *Had 段), 所以很轻(一次顶层扫描)。
    用途: 添加功法前把这些名字排除掉 —— 它们不在段里, 加进去就成了同名的两份, 游戏里卸不下来。
    """
    inner = None
    out = {}
    if container_open is None:
        return inner, out
    for kd, vs, ve, _vt in _entry_values(text, container_open):
        if not _KANGFU_DRESS_KEY_RE.match(kd):
            continue
        key_name = kd.lstrip("_")
        ch = text[vs:vs + 1]
        if ch in "{[":
            seg = text[vs:_local_span_end(text, vs) + 1]
        else:
            seg = text[vs:ve]
        if key_name == "DressInKangFuName":
            m = _KANGFU_STR_RE.search(seg)
            if m:
                inner = _es3_unescape_name(m.group(1)) or None
        elif key_name == "DressInKangFu" and ch == "{":
            nm = _obj_direct_str(text, vs, "_Name")
            if nm and inner is None:
                inner = nm
        for m in _KANGFU_STR_RE.finditer(seg):
            nm = _es3_unescape_name(m.group(1))
            key = _kangfu_norm(nm)
            if not key or _KANGFU_PLAIN_ID_RE.match(nm):
                continue        # 空串 / 纯英文键名(_Lv/_Name/_DressType…) 不是功法名
            out.setdefault(key, nm)
    return inner, out


def _kangfu_fields_text(seg, name_esc, lv, l2, l3, nl):
    """一条功法的字段行(按段类型给不同模板; 与真实存档写法逐字节一致)。缩进: 字段=l2, 数组空行=l3。"""
    if seg == "InKangFuHad":
        return (l2 + '"_Lv" : %d,' % lv + nl +
                l2 + '"_Name" : "' + name_esc + '",' + nl +
                l2 + '"_DressType" : 1,' + nl +
                l2 + '"_DressKangFu" : [' + nl +
                l3 + nl +
                l2 + '],' + nl +
                l2 + '"_DressQuickKangFu" : {1:"",2:"",3:"",4:"",5:"",6:"",7:"",8:"",9:"",10:""' + nl +
                l2 + '},' + nl +
                l2 + '"_DressBigLoop" : [' + nl +
                l3 + nl +
                l2 + '],' + nl +
                l2 + '"_DressSmallLoop" : [' + nl +
                l3 + nl +
                l2 + '],' + nl +
                l2 + '"_DressKangFuQing" : ""' + nl)
    if seg == "KangFuHad":
        return (l2 + '"_Lv" : %d,' % lv + nl +
                l2 + '"_DressType" : 1,' + nl +
                l2 + '"_Name" : "' + name_esc + '",' + nl +
                l2 + '"_Exp" : 0,' + nl +
                l2 + '"_AddLv" : 0,' + nl +
                l2 + '"HaveShanHaiLu" : [' + nl +
                l3 + nl +
                l2 + ']' + nl)
    # 绝技 / 轻功: 只有 _Lv / _DressType / _Name
    return (l2 + '"_Lv" : %d,' % lv + nl +
            l2 + '"_DressType" : 1,' + nl +
            l2 + '"_Name" : "' + name_esc + '"' + nl)


def kangfu_add(text, container_open, adds, data=None, dressed=None):
    """把 [(功法名, 等级)] 写进该角色的对应功法段(段按名字在库里的分支自动判定)。

    返回 (新文本, 实际新增 [(段标题, 名)], 已学过/已装备跳过 [名], 无法判定/该角色缺该段 [名])。
    只在该段字段块内做局部插入, 最后一次性 `_apply_subs` 写回(维护结构索引缓存)。

    dressed: `kangfu_dressed()` 得到的 {归一化名: 原名}(该角色「已装备」的功法); None=内部自动读。
      ★ 已装备的功法一律**不添加** —— 它们存在独立的装备对象里(不在 *Had 段), 段里再出现同名
        会变成「同名的两份」, 游戏里这门功法就卸不下来/切不走了。
    """
    seg_of, raw_of = kangfu_index(data)
    if dressed is None:
        _inner, dressed = kangfu_dressed(text, container_open)
    plan = {}          # 段字段 -> [(名, lv)]
    skipped = []
    unknown = []
    for nm, lv in adds or ():
        key = _kangfu_norm(nm)
        if not key:
            continue
        seg = seg_of.get(key)
        if seg is None:
            unknown.append(nm)
            continue
        plan.setdefault(seg, []).append((raw_of.get(key, nm), int(lv)))
    if not plan:
        return text, [], skipped, unknown
    if container_open is None:
        # 没找到该角色的属性段: 全部归入「无法判定/缺段」(不臆测写哪里)
        for names in plan.values():
            unknown.extend(n for n, _lv in names)
        return text, [], skipped, unknown

    close = _matching_end(text, container_open)
    subs = []
    added = []
    for seg in KANGFU_SEG_ORDER:
        items = plan.get(seg)
        if not items:
            continue
        _f, open_i = _kangfu_field_open(text, container_open, seg, close)
        if open_i is None:
            unknown.extend(n for n, _lv in items)
            continue
        hs = text.rfind("\n", 0, open_i) + 1
        seg_close = _local_span_end(text, open_i)
        he = text.find("\n", seg_close)
        he = len(text) if he < 0 else he + 1
        seg_txt = text[hs:he]
        rel = open_i - hs
        nl = "\r\n" if "\r\n" in seg_txt else "\n"
        l0 = re.match(r"[ \t]*", seg_txt).group(0)
        unit = _indent_unit(l0)
        l1 = l0 + unit
        l2 = l0 + unit * 2
        l3 = l0 + unit * 3
        entries0 = _kangfu_entries(seg_txt, rel)
        have = {_kangfu_norm(n) for n, _ks, _vs, _vc in entries0}
        chunks = []
        for nm, lv in items:
            key = _kangfu_norm(nm)
            if key in have or key in dressed:
                # 已学过 或 已装备(装备对象不在段里, 再塞一份同名会卸不下来) → 跳过
                skipped.append(nm)
                continue
            esc = _es3_escape_name(nm)
            chunks.append('"' + esc + '":{' + nl + _kangfu_fields_text(seg, esc, lv, l2, l3, nl)
                          + l1 + '}')
            have.add(key)
            added.append((KANGFU_TITLE_OF_SEG[seg], nm))
        if chunks:
            # ★ 一次拼好后整块插到段尾: 原来每加一条都重扫一遍该段条目并整段拼接(O(k²),
            #   一次加几百门时会越来越慢); 现在只扫一次/拼一次。
            blob = ",".join(chunks)
            if entries0:
                j = entries0[-1][3]     # 原最后一个条目的值闭括号(新条目都追加在它后面)
                seg_txt = seg_txt[:j + 1] + "," + blob + seg_txt[j + 1:]
            else:
                # 段原本为空(形如 {  + 换行缩进 + }): 首条目内联在 `{` 之后
                seg_txt = seg_txt[:rel + 1] + blob + nl + l0 + seg_txt[seg_close - hs:]
            subs.append((hs, he, seg_txt))
    if not subs:
        return text, added, skipped, unknown
    return _apply_subs(text, subs), added, skipped, unknown


def kangfu_del(text, container_open, targets):
    """删除该角色的功法条目。targets = [(段字段, 干净名)] 或 [干净名](跨段按名字匹配)。

    返回 (新文本, 实际删除 ["[武功]名", ...])。段内条目全部删光时该段变回空字典 `{\\n<缩进>}`;
    其余段落逐字节不动。内部自行重新定位(不依赖调用方缓存的旧偏移)。
    """
    if container_open is None or not targets:
        return text, []
    want = []
    for t in targets:
        if isinstance(t, (tuple, list)) and len(t) >= 2:
            want.append((t[0], _kangfu_norm(t[1])))
        else:
            want.append((None, _kangfu_norm(t)))
    close = _matching_end(text, container_open)
    subs = []
    gone = []
    for seg in KANGFU_SEG_ORDER:
        seg_targets = {n for s, n in want if (s is None or s == seg) and n}
        if not seg_targets:
            continue
        _f, open_i = _kangfu_field_open(text, container_open, seg, close)
        if open_i is None:
            continue
        title = KANGFU_TITLE_OF_SEG[seg]
        seg_close = _local_span_end(text, open_i)
        entries = _kangfu_entries(text, open_i)
        hit = [i for i, (nm, _ks, _vs, _vc) in enumerate(entries)
               if _kangfu_norm(nm) in seg_targets]
        if not hit:
            continue
        if len(hit) == len(entries):
            # 整段删空: 段内内容换成「换行 + 段缩进」, 变成空字典
            l0 = _line_indent(text, open_i)
            nl = "\r\n" if "\r\n" in text[open_i:seg_close + 1] else "\n"
            subs.append((open_i + 1, seg_close, nl + l0))
            gone.extend("[%s]%s" % (title, entries[i][0]) for i in hit)
            continue
        for i in sorted(hit, reverse=True):
            nm, ks, _vs, vc = entries[i]
            if i < len(entries) - 1:
                # 非末条: 连同它后面的逗号一起删掉
                end = vc + 2 if text[vc + 1:vc + 2] == "," else vc + 1
                subs.append((ks, end, ""))
            else:
                # 末条: 连同它前面的逗号一起删掉(保留前面条目与段闭合)
                prev_close = entries[i - 1][3]
                s = prev_close + 1
                while s < len(text) and text[s] in " \t":
                    s += 1
                subs.append((s, vc + 1, ""))
            gone.append("[%s]%s" % (title, nm))
    if not subs:
        return text, []
    return _apply_subs(text, subs), gone


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
_SKILL_CAT_CACHE = {}     # 技能名库(v2.13.3): 过滤掉非战斗子目录后的结果缓存(按 path)


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


def build_item_cat_nodes(data, allow_codes=None):
    """把 load_item_categories 的结果建成「分类树 + 全量道具名」。

    返回 (roots, all_names):
      roots     : 每个大分类一个根节点; 节点 = {"code","zh","own":[直挂名],
                  "children":{段:子节点}, "total":N}。
      all_names : 全部大分类道具名, 跨分类/跨路径去重(顺序=出现顺序), 供统计与无勾选兜底。
    allow_codes: 仅保留这些大分类(v2.9.0, 如新增道具只列 item 或只列 equip); None=全部分类。
    """
    zh = data.get("zh") or {}
    roots = []
    for cat in data.get("cats") or []:
        code = cat.get("code")
        if not code:
            continue
        if allow_codes is not None and code not in allow_codes:
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


# ---- 按用途过滤大分类(v2.9.0) ----
# 装备类(equip)应写入存档 savePlayerData.value 的 EquipHad 段, 不应混入 ItemHad; skillcom(技能合成)全局不显示。
# 「新增道具」对话框按加入目标只显示应进入的类别:
#   ItemHad/商店卖品 = 道具类(item/recipe/bookcontent/kangfu/shanhailu), 排除 equip 与 skillcom;
#   EquipHad/商店SellEquips = 只显示 equip。
ITEM_ADD_CATS = frozenset(("item", "recipe", "bookcontent", "kangfu", "shanhailu"))
EQUIP_ADD_CATS = frozenset(("equip",))


def _name_cat_map(data):
    """把 道具分类.json 数据建成 道具名→所属大分类代码集合 的映射(供按用途过滤名字)。"""
    cmap = {}
    for cat in (data or {}).get("cats") or []:
        code = cat.get("code")
        if not code:
            continue
        for names in (cat.get("groups") or {}).values():
            for n in names:
                if isinstance(n, str) and n:
                    cmap.setdefault(n, set()).add(code)
    return cmap


def _filter_names_by_cats(names, allow_codes, data=None):
    """把名字列表按允许的大分类过滤。未在分类库(自定义名)一律放行; allow_codes=None 全放行。

    data: 道具分类.json 数据(load_item_categories 结果); None 时自动读取。
    """
    if not allow_codes:
        return list(names)
    if data is None:
        data = load_item_categories()
    cmap = _name_cat_map(data)
    allow = set(allow_codes)
    out = []
    for n in names:
        cs = cmap.get(n)
        if cs is None or (cs & allow):
            out.append(n)
    return out


def split_names_by_cats(names, allow_codes, data=None):
    """把用户选定/输入的名字按允许的大分类拆成 (放行, 拦下)。

    用于「新增道具」后的兜底校验: 即使手输了不该进本容器的类别名(如给 ItemHad 输到 equip 装备名),
    也会被拦下并在提示里说明。未在分类库(自定义名)一律放行; allow_codes=None 全放行。
    """
    if not allow_codes:
        return list(names), []
    if data is None:
        data = load_item_categories()
    cmap = _name_cat_map(data)
    allow = set(allow_codes)
    ok, no = [], []
    for n in names:
        cs = cmap.get(n)
        if cs is None or (cs & allow):
            ok.append(n)
        else:
            no.append(n)
    return ok, no


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
# 队友页想要展示成“编号字典分组”的字段(_LifeTypeLv=队友生活技能经验, v2.8.1 新增)
FRIEND_DICT_FIELDS = ("SixProCurrent", "_KongFuTypeLv", "_LifeTypeLv")


def char_model(text):
    """把整份存档里所有角色页需要的数据一次性收集成轻量模型(纯计算, 可在后台线程执行)。

    返回 {
      'player': {scalars, dicts, open, kangfu, dressed} | None,
      'friends': [ {group, key, name, scalars, dicts, open, kangfu, dressed} ... ],
      'maps': [地名...],
      'dialogue': [(显示名, 变量名, 值 or None) ...]   # 剧情变量(善恶值等, 存 saveDialogue 段)
    }
    kangfu  = [(段字段, 段标题, 干净名)] —— 该角色已学的功法(v2.14.0, 内功/武功/绝技/轻功 四段汇总)。
    dressed = (已装备内功名 or None, {归一化名: 原名}) —— 该角色**已装备**的功法(v2.14.1),
              这些名字不在 *Had 段里, 添加时要跳过(否则同名两份会让游戏卸不下来)。
    """
    model = {"player": None, "friends": [], "maps": []}
    po = _locate_container(text, SCOPE_PLAYER)
    if po is not None:
        s, d = collect_page(text, po, PLAYER_DICT_FIELDS)
        model["player"] = {"scalars": s, "dicts": d, "open": po,
                           "kangfu": kangfu_brief(text, po),
                           "dressed": kangfu_dressed(text, po)}
    model["maps"] = get_str_array(text, SCOPE_MAP, "_ActiveMap")
    # 剧情变量(善恶值等): 存于 saveDialogue 段的字节编码变量表; 值 None = 该存档没有这个变量
    model["dialogue"] = [(disp, nm, get_dialogue_var(text, nm)) for disp, nm in DIALOGUE_VARS]
    for group, key, name, fop in friend_blocks(text):
        s, d = collect_page(text, fop, FRIEND_DICT_FIELDS)
        model["friends"].append({"group": group, "key": key, "name": name,
                                  "scalars": s, "dicts": d, "open": fop,
                                  "kangfu": kangfu_brief(text, fop),
                                  "dressed": kangfu_dressed(text, fop)})
    return model


# ============================ GUI 层 ============================

def _select_enabled_items(lst):
    """一次性选中 QListWidget 里所有「可选(未灰显)」项。

    ★ 逐行 setSelected 很慢: 它会逐行触发视图内部的选择变更 + 区域重绘(实测 4565 行要 6~26
      秒, 即使已经 blockSignals 也管不到 view 内部连接)。这里把**连续可选行**合并成若干区间,
      用 `QItemSelection` 一次性交给 selectionModel —— 与 Qt 原生全选同量级(百毫秒级)。
    """
    model = lst.model()
    sel = QItemSelection()
    start = None
    n = lst.count()
    for r in range(n):
        ok = bool(lst.item(r).flags() & Qt.ItemFlag.ItemIsEnabled)
        if ok and start is None:
            start = r
        elif not ok and start is not None:
            sel.select(model.index(start, 0), model.index(r - 1, 0))
            start = None
    if start is not None:
        sel.select(model.index(start, 0), model.index(n - 1, 0))
    lst.selectionModel().select(
        sel, QItemSelectionModel.SelectionFlag.ClearAndSelect
        | QItemSelectionModel.SelectionFlag.Rows)


class _BulkListEdit:
    """批量编辑 QListWidget 的上下文管理器(暂停重绘 + 屏蔽信号, 退出时恢复原状态)。

    上千行的候选列表里逐行 addItem/setSelected 会逐行重绘, 并且会话里每行都发一次
    itemSelectionChanged → 槽里往往做 O(名库) 的统计 —— 实测 4565 行的名库上「全选」要
    **26 秒**(Qt 原生批量选择同一列表只要 0.2 秒)。批量期间屏蔽信号、暂停重绘, 结束后由
    调用方手动刷新一次统计即可。
    """

    def __init__(self, widget):
        self._w = widget

    def __enter__(self):
        self._upd = self._w.updatesEnabled()
        self._blk = self._w.blockSignals(True)
        self._w.setUpdatesEnabled(False)
        return self._w

    def __exit__(self, *exc):
        self._w.blockSignals(bool(self._blk))
        self._w.setUpdatesEnabled(self._upd)
        return False


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
    - allow_codes(可选, v2.9.0): 只保留这些大分类——新增道具(ItemHad)排除 equip/skillcom;
      「添加装备(EquipHad/SellEquips)」只留 equip(此时仅一棵根节点会自动勾选, 右侧直接列候选);
      装备入口的「件数」= 每种加几件同名实例(可同名不堆叠); show_count=False 时隐藏数量/件数行。
    """

    def __init__(self, parent=None, existing=None, default_name="", default_count=9999,
                 allow_codes=None, show_count=True, cat_data=None, fallback_names=None,
                 title=None, count_label=None, extra_builder=None, noun="道具",
                 existing_tips=None, hidden_names=None):
        super().__init__(parent)
        self._existing = set(existing or ())
        # 灰显项的自定义提示(名 → 提示文字): 如功法把「已装备」与「已学过」区分开(v2.14.1)
        self._existing_tips = dict(existing_tips or {})
        # 完全不显示的名单(v2.15.0): 如功法黑名单 —— 这类名字在候选里连灰显都不出现
        self._hidden = {str(n).strip() for n in (hidden_names or ()) if str(n).strip()}
        self._hidden_norm = {_kangfu_norm(n) for n in self._hidden}
        self._pmap = load_pinyin_map()
        self._chosen = None          # 双击/回车确定的单项; None 时按“多选/自定义”取
        self._noun = noun            # 统计文案里的名词(道具/蛊虫/技能)
        self._allow = set(allow_codes) if allow_codes else None   # 仅允许加入这些大分类(v2.9.0)
        self._show_count = show_count
        # 候选数据: 优先 分类库(默认 道具分类.json); 缺失回退 flat 名单(默认 道具名.json 平铺)
        # v2.13.0: cat_data/fallback_names 可注入(蛊虫名.json / 技能名.json 复用同一个弹窗)
        self._cat_data = cat_data if cat_data is not None else load_item_categories()
        if self._hidden and self._cat_data:
            # 剔除隐藏名(黑名单) —— 返回新对象, 不动 _CAT_CACHE 里的分类库
            self._cat_data = filter_cat_data(self._cat_data, self._hidden_norm)[0]
        self._use_cat = bool(self._cat_data and self._cat_data.get("cats"))
        self._cat_roots, self._scope_names = [], None
        self._scope_dirty = False
        if self._use_cat:
            self._cat_roots, self._all_names = build_item_cat_nodes(self._cat_data, allow_codes=self._allow)
        else:
            # 平铺回退: 若能取到分类库则按 allow_codes 过滤(未分类/自定义名放行)
            src = fallback_names if fallback_names is not None else load_item_names()
            self._all_names = [n for n in dict.fromkeys(
                _filter_names_by_cats(src, self._allow, self._cat_data))
                if not self._is_hidden(n)]
        self._cat_building = False
        self._missing_cache = None   # 「缺少的道具」缓存(_existing 构造后不再变)

        self.setWindowTitle(title or "新增道具")
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

        # 数量/件数: 普通道具=统一数量; 装备(equip, 可同名不堆叠)=每种加几件的同名实例
        _is_equip_dlg = (self._allow is not None and set(self._allow) == set(EQUIP_ADD_CATS))
        cnt = QHBoxLayout()
        cnt.addWidget(QLabel(count_label or ("件数(每种装备=加该件数的同名实例):" if _is_equip_dlg
                                             else "数量(本次新增道具统一):")))
        self.count_spin = QSpinBox()
        self.count_spin.setRange(0, MAX_ITEM_COUNT)
        self.count_spin.setValue(default_count)
        cnt.addWidget(self.count_spin)
        cnt.addStretch(1)
        if self._show_count:
            root.addLayout(cnt)

        # 子类/调用方追加的专用设置行(v2.13.0: 蛊虫的默认属性/技能选项等)
        if extra_builder is not None:
            extra_builder(root)

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
        # 只允许单一分类时(如 添加装备 只留 equip)自动勾选, 右侧直接列出该分类候选。
        if self._use_cat and self._cat_root_items and len(self._cat_roots) == 1:
            self._cat_root_items[0].setCheckState(0, Qt.CheckState.Checked)
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
    def _is_hidden(self, nm):
        """是否属于「完全不显示」的名单(如功法黑名单): 候选列表里不会出现这个名字。"""
        return nm in self._hidden or _kangfu_norm(nm) in self._hidden_norm

    def _missing_names(self):
        """全量道具库里个人背包(当前列表)还没有的名字, 即“缺少的道具”。

        结果缓存(_existing 在对话框生命周期内不变); 大库(5000+)上反复调用省几百 ms。
        """
        if self._missing_cache is None:
            self._missing_cache = [n for n in self._all_names if n not in self._existing]
        return self._missing_cache

    def _filtered(self):
        names = filter_item_names(self._current_scope(), self.search.text(),
                                  self._pmap, mode=self.mode_combo.currentIndex())
        if self._hidden:
            names = [n for n in names if not self._is_hidden(n)]   # 黑名单: 兜底再滤一次
        if self.only_missing_check.isChecked():   # 勾选后只列缺少的
            names = [n for n in names if n not in self._existing]
        return names

    def _bulk_list_edit(self):
        """批量改列表(清空/填充/多选)的上下文: 暂停重绘 + 屏蔽信号, 末尾手动刷一次统计。

        ★ 上千行的候选列表里逐行 add/select 会让视图逐行重绘并发 selectionChanged(每行一次
          `_update_stat`, 大库上每次 ~3ms) —— 实测 4565 行「全选」要 26 秒; 批量处理后半秒内。
        用法: `with self._bulk_list_edit(): ...`
        """
        return _BulkListEdit(self.item_list)

    def _refresh_list(self):
        lst = self.item_list
        upd = lst.updatesEnabled()
        lst.setUpdatesEnabled(False)
        lst.blockSignals(True)
        try:
            lst.clear()
            names = self._filtered()
            if names:
                lst.addItems(names)        # C++ 侧批量建项(逐条 QListWidgetItem 建 4000+ 项要 ~0.5s)
            for i, nm in enumerate(names):  # 顺序与原来一致; 已在本列表里的灰显不可选
                if nm in self._existing:
                    it = lst.item(i)
                    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                    it.setToolTip(self._existing_tips.get(nm) or "已在当前列表中(无需重复添加)")
        finally:
            lst.blockSignals(False)
            lst.setUpdatesEnabled(upd)
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
        hid = " · 已隐藏黑名单 %d 门" % len(self._hidden) if self._hidden else ""
        if self._use_cat:
            shown = len(self._current_scope())
            self.stat_label.setText("%s名库 %d · 当前勾选分类含 %d · 已选 %d%s"
                                    % (self._noun, total, shown, sel, hid))
        else:
            self.stat_label.setText("%s名库 %d · 个人已有 %d · 缺少 %d · 已选 %d%s"
                                    % (self._noun, total, total - miss, miss, sel, hid))
        self.btn_ok.setText("添加所选(%d)" % sel if sel else "添加所选")

    def _select_all(self):
        """全选所有「可选」项(一次性区间选择 + 末尾一次统计)。

        ★ 逐行 setSelected 会在 4565 行的名库上卡 26 秒(用户反馈“大量添加时很卡”的主因),
          批量设选择后再单次刷新统计, 实测降到与 Qt 原生全选同量级。
        """
        with self._bulk_list_edit():
            _select_enabled_items(self.item_list)
        self._update_stat()

    def _select_none(self):
        with self._bulk_list_edit():
            self.item_list.clearSelection()
        self._update_stat()

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


class AddChongDialog(AddItemDialog):
    """添加蛊虫(ChongHad)对话框: 复用「新增道具」的分类树/搜索/多选, 再追加蛊虫专用默认值。

    - 候选来自 程序目录/蛊虫名.json(由 _scaffold/build_chong_names.py 从 内存所有道具.json 的
      dataset/chong/* 生成, 108 只): 左树按 冰系/毒系/穴系/血系/火系/固定/对战 分组。
    - 「只数」= 每选中的蛊虫加几条(蛊虫不堆叠, 每只一条独立条目, 同装备)。
    - 三项属性 Power(力道)/Agility(灵气)/PhysicalPower(体魄) 与 培养上限 _FosterMax
      默认都是 9999(可自定义); 新增的每只蛊虫 _TotalProperty 一律写 0。
    - _Skill(状态累积值) / _Preference(状态倍率) 可一键写入「全部状态」
      (中毒/流血/着火/点穴/冰冻 5 种) 或「全部技能库」(技能名.json 里 被动/战斗 pass + 特殊/临时 todu
      两组, 已排除 生活技能/工具/测试未整理), 默认 9999、可自定义。
    """

    def __init__(self, parent=None, defaults=None, title="添加蛊虫(ChongHad)"):
        d = dict(defaults or {})
        self._opts = d
        super().__init__(parent, existing=set(), default_count=d.get("count", 1),
                         cat_data=load_chong_categories(),
                         fallback_names=load_chong_names(),
                         title=title, noun="蛊虫",
                         count_label="只数(每只=一条独立蛊虫条目, 不堆叠):",
                         extra_builder=self._build_extra)

    def _build_extra(self, root):
        """蛊虫专用默认值行: 三项属性 + _Skill/_Preference 一键写入选项。"""
        d = self._opts
        row = QHBoxLayout()
        row.addWidget(QLabel("属性默认(力道/灵气/体魄):"))
        self.prop_spins = {}
        for f in CHONG_PROP_FIELDS:
            sp = QSpinBox()
            sp.setRange(0, MAX_ITEM_COUNT)
            sp.setValue(int(d.get(f.lower(), CHONG_PROP_DEFAULT)))
            sp.setToolTip("%s(%s) 默认值" % (CHONG_PROP_LABELS[f], f))
            row.addWidget(sp)
            self.prop_spins[f] = sp
        row.addSpacing(14)
        row.addWidget(QLabel("培养上限 _FosterMax:"))
        self.fostermax_spin = QSpinBox()
        self.fostermax_spin.setRange(0, MAX_ITEM_COUNT)
        self.fostermax_spin.setValue(int(d.get("foster_max", CHONG_FOSTER_MAX_DEFAULT)))
        self.fostermax_spin.setToolTip("新增蛊虫的 _FosterMax 默认值(默认 %d)"
                                       % CHONG_FOSTER_MAX_DEFAULT)
        _fmb = QPushButton("默认 %d" % CHONG_FOSTER_MAX_DEFAULT)
        _fmb.setToolTip("把培养上限重置为默认 %d" % CHONG_FOSTER_MAX_DEFAULT)
        _fmb.clicked.connect(lambda _=False, s=self.fostermax_spin:
                             s.setValue(CHONG_FOSTER_MAX_DEFAULT))
        row.addWidget(self.fostermax_spin)
        row.addWidget(_fmb)
        row.addStretch(1)
        root.addLayout(row)

        self.chk_skill = QCheckBox("_Skill 写入全部状态 =")
        self.chk_skill.setChecked(bool(d.get("fill_skill", True)))
        self.chk_skill.setToolTip(
            "勾选后: 新增的每只蛊虫 _Skill 会把「全部状态」都写上目标值\n"
            "(中毒/流血/着火/点穴/冰冻 = 存档 ChongPotHad 的 5 类虫罐实测出的蛊虫可用状态)")
        self.skill_spin = QSpinBox()
        self.skill_spin.setRange(0, MAX_ITEM_COUNT)
        self.skill_spin.setValue(int(d.get("skill_value", CHONG_SKILL_DEFAULT)))
        self.chk_skill_all = QCheckBox("改写入全部技能库(%d 项)" % skill_lib_count())
        self.chk_skill_all.setChecked(bool(d.get("fill_all_skill", False)))
        self.chk_skill_all.setToolTip(
            "不勾=只写上面 5 种蛊虫可用状态; 勾上=把 技能名.json 里全部战斗类技能名都写进 _Skill。\n"
            "技能库只含「被动/战斗(pass)」与「特殊/临时(todu)」两组——生活技能天赋/工具/\n"
            "测试未整理已排除(v2.13.3)。\n"
            "注意: 存档体积会明显变大, 且游戏可能忽略不认识的技能名, 建议先只加 1 只试效果。")
        row1 = QHBoxLayout()
        row1.addWidget(self.chk_skill)
        row1.addWidget(self.skill_spin)
        row1.addSpacing(12)
        row1.addWidget(self.chk_skill_all)
        row1.addStretch(1)
        root.addLayout(row1)

        self.chk_pref = QCheckBox("_Preference 写入全部状态 =")
        self.chk_pref.setChecked(bool(d.get("fill_pref", True)))
        self.chk_pref.setToolTip(
            "勾选后: 新增的每只蛊虫 _Preference 会把「全部状态」都写上目标值(可大于 1, 如 9999)")
        self.pref_spin = QSpinBox()
        self.pref_spin.setRange(0, MAX_ITEM_COUNT)
        self.pref_spin.setValue(int(d.get("pref_value", CHONG_PREF_DEFAULT)))
        row2 = QHBoxLayout()
        row2.addWidget(self.chk_pref)
        row2.addWidget(self.pref_spin)
        row2.addStretch(1)
        root.addLayout(row2)

    def spec_options(self):
        """返回用于 chong_add 的公共默认值(dict)。"""
        opts = {f.lower(): self.prop_spins[f].value() for f in CHONG_PROP_FIELDS}
        opts["foster_max"] = self.fostermax_spin.value()
        if self.chk_skill.isChecked():
            keys = list(load_skill_names()) if self.chk_skill_all.isChecked() else list(CHONG_SKILLS)
            opts["skills"] = {k: self.skill_spin.value() for k in keys}
        if self.chk_pref.isChecked():
            opts["prefs"] = {k: self.pref_spin.value() for k in CHONG_SKILLS}
        return opts

    def current_defaults(self):
        """当前对话框设置(供主窗记忆到 设置.json)。"""
        d = {f.lower(): self.prop_spins[f].value() for f in CHONG_PROP_FIELDS}
        d["count"] = self.count_spin.value()
        d["foster_max"] = self.fostermax_spin.value()
        d["fill_skill"] = self.chk_skill.isChecked()
        d["skill_value"] = self.skill_spin.value()
        d["fill_all_skill"] = self.chk_skill_all.isChecked()
        d["fill_pref"] = self.chk_pref.isChecked()
        d["pref_value"] = self.pref_spin.value()
        return d


class KangFuDialog(AddItemDialog):
    """添加功法对话框: 复用「新增道具」的分类树/搜索/多选, 追加「等级 _Lv」。

    - 候选来自 程序目录/功法名.json(由 _scaffold/build_kangfu_names.py 从 内存所有道具.json 的
      分类.kangfu 生成), 4 个大分类与存档段一一对应:
        inkangfu 内功 → InKangFuHad / kangfu 武功 → KangFuHad /
        jue 绝技 → KangFuSkillHad / qing 轻功 → KangFuQingHad(队友同名段前面多一个下划线)。
      大分类下再按来源/门派细分(百灵御/必报山庄/BOSS/皇羽谷/江湖/昆仑神教/鲲鹏教/破道天宫/
      穹空派/七曜宫/五子寺)。
    - 「等级 _Lv」= 写进该功法条目的 _Lv(默认取上次记住的值)。
      ★ v2.14.3: **等级输入框一变就回调 `on_lv_changed`** —— 主窗口据此立即写进 设置.json,
        所以下次打开对话框就是这次改的值(不用先点确定, 点取消也已记住)。
    - 该角色已经学过的功法在右侧灰显跳过(避免重复学同一门)。
    - hidden_names(v2.15.0): **功法黑名单** —— 这些名字在候选里完全不出现(用户先避开已知
      会卡死的功法, 以后有空再逐条验证原因)。
    """

    def __init__(self, parent=None, existing=None, title="添加功法",
                 default_lv=KANGFU_DEFAULT_LV, dressed=None, on_lv_changed=None,
                 hidden_names=None):
        tips = {}
        for nm in (dressed or {}).values():
            tips[nm] = ("该角色已装备此功法, 不能重复添加。\n"
                        "(它存在独立的装备对象里, 段里再出现同名会变成同名两份 → 游戏里卸不下来/切不走)")
        super().__init__(parent, existing=existing, default_count=default_lv,
                         cat_data=load_kangfu_categories(),
                         fallback_names=load_kangfu_names(),
                         title=title, noun="功法",
                         count_label="等级 _Lv(新增功法的等级; 改一下就记住, 下次打开还是它):",
                         existing_tips=tips, hidden_names=hidden_names)
        # 等级框一变就通知主窗立即记住(构造时 setValue 发生在 connect 之前, 不会误触发)
        self._on_lv_changed = on_lv_changed
        if on_lv_changed is not None:
            self.count_spin.valueChanged.connect(self._lv_changed)

    def _lv_changed(self, val):
        """等级框一变就回调(主窗立即写盘, 不用等点确定)。"""
        if self._on_lv_changed is not None:
            self._on_lv_changed(int(val))


class KangFuBlacklistDialog(QDialog):
    """功法黑名单管理(程序目录/功法黑名单.json, v2.15.0)。

    用途: 记录「一学就卡死 / 有问题」的功法。加进黑名单以后:
      ① 「＋ 添加功法…」的候选里**完全不显示**(不会手滑选中);
      ② 主角与队友都不会被添加(即便名字从别处传进来, 主窗也会再拦一道);
      ③ 角色页功法列表里会给它标上「★ 在黑名单」, 提醒你那是可疑功法。
    支持批量加入(功法库多选/全选)、批量移出(多选)、逐条备注(记现象/猜测原因 —— 便于以后
    逐条验证是「剧情还没到」还是别的原因)。改动**即时写盘**, 不用点确定。
    """

    def __init__(self, parent=None, items=None, path=None):
        super().__init__(parent)
        self._path = path
        self.items = [dict(it) for it in (items or [])]
        self.setWindowTitle("功法黑名单(已知会卡死的功法)")
        self.setMinimumSize(720, 480)
        root = QVBoxLayout(self)
        tip = QLabel(
            "黑名单里的功法:「＋ 添加功法…」候选里不会显示, 也不会被加给主角/队友。\n"
            "用途: 把已知会让游戏卡死的功法先记下来避开, 以后有空再逐条确认到底是「剧情还没到」\n"
            "还是别的原因 —— 可在「备注」列写下现象/猜测。改动即时保存到 程序目录/功法黑名单.json,\n"
            "与当前存档无关(换档、重开程序都生效)。")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#666;")
        root.addWidget(tip)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["功法名", "备注(现象 / 猜测原因)"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.verticalHeader().setVisible(False)
        _hdr = self.table.horizontalHeader()
        _hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        _hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setToolTip("可 Ctrl/Shift 多选后「－ 删除选中」; 双击「备注」列可直接编辑")
        self.table.itemChanged.connect(self._on_item_changed)
        root.addWidget(self.table, 1)

        self.count_label = QLabel("")
        row = QHBoxLayout()
        row.addWidget(self.count_label)
        row.addStretch(1)
        b_add = QPushButton("＋ 从功法库添加…")
        b_add.setToolTip("打开功法库(内功/武功/绝技/轻功 分类树 + 中文/拼音搜索)多选/全选加入黑名单;\n"
                         "已在本黑名单里的会灰显跳过")
        b_add.clicked.connect(self._on_add)
        b_del = QPushButton("－ 删除选中")
        b_del.setToolTip("把选中的功法移出黑名单(移出后它又会出现在「添加功法…」候选里)")
        b_del.clicked.connect(self._on_del)
        b_clear = QPushButton("清空全部")
        b_clear.setToolTip("清空整个黑名单(所有功法都会重新出现在「添加功法…」候选里)")
        b_clear.clicked.connect(self._on_clear)
        for b in (b_add, b_del, b_clear):
            row.addWidget(b)
        root.addLayout(row)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.button(QDialogButtonBox.StandardButton.Close).setText("关闭")
        btns.rejected.connect(self.reject)
        root.addWidget(btns)
        self._reload()

    # ---------------- 内部 ----------------
    def _reload(self):
        t = self.table
        t.blockSignals(True)
        try:
            t.setRowCount(len(self.items))
            for r, it in enumerate(self.items):
                c0 = QTableWidgetItem(it.get("name") or "")
                c0.setFlags(c0.flags() & ~Qt.ItemFlag.ItemIsEditable)
                c0.setToolTip("不会出现在「添加功法…」候选里, 也不会被加给任何角色")
                t.setItem(r, 0, c0)
                t.setItem(r, 1, QTableWidgetItem(it.get("note") or ""))
        finally:
            t.blockSignals(False)
        self._update_count()

    def _update_count(self):
        n = len(self.items)
        self.count_label.setText("黑名单: %d 门" % n if n else
                                 "黑名单为空 —— 点右边「＋ 从功法库添加…」把已知会卡死的功法加进来")

    def _on_item_changed(self, item):
        r = item.row()
        if not (0 <= r < len(self.items)):
            return
        if item.column() == 1:
            self.items[r]["note"] = item.text().strip()
        else:
            nm = (item.text() or "").strip()
            if not nm:
                self._reload()          # 名字不允许清空 → 恢复原值
                return
            self.items[r]["name"] = nm
        self._save()

    def _save(self):
        """即时写盘(与项目「设置实时保存」约定一致, 不用点确定)。"""
        ok, info = save_kangfu_blacklist(self.items, self._path)
        if not ok:
            QMessageBox.warning(self, "提示", "写入 功法黑名单.json 失败:\n%s" % info)

    def _on_add(self):
        """从功法库批量加入黑名单(复用「新增道具」的分类树/搜索/多选/全选)。"""
        dlg = AddItemDialog(self, existing={it.get("name") for it in self.items},
                            cat_data=load_kangfu_categories(),
                            fallback_names=load_kangfu_names(),
                            title="加入功法黑名单", noun="功法", show_count=False)
        if not dlg.exec():
            return
        names = list(dict.fromkeys(n for n in dlg.chosen_names() if n))
        have = {_kangfu_norm(it.get("name")) for it in self.items}
        added = 0
        for nm in names:
            k = _kangfu_norm(nm)
            if not k or k in have:
                continue
            have.add(k)
            self.items.append({"name": nm, "note": ""})
            added += 1
        if added:
            self._save()
            self._reload()

    def _on_del(self):
        rows = sorted({i.row() for i in self.table.selectedItems()}, reverse=True)
        if not rows:
            QMessageBox.information(self, "提示",
                                    "请先在列表里选中要移出黑名单的功法(可按住 Ctrl/Shift 多选)")
            return
        names = [self.items[r].get("name") for r in rows if 0 <= r < len(self.items)]
        if QMessageBox.question(
                self, "确认移出",
                "把 %d 门功法移出黑名单?\n%s\n\n(移出后它们会重新出现在「添加功法…」候选里)"
                % (len(names), "、".join(names[:10]))
                + (" 等 %d 门" % len(names) if len(names) > 10 else "")
        ) != QMessageBox.StandardButton.Yes:
            return
        for r in rows:
            if 0 <= r < len(self.items):
                del self.items[r]
        self._save()
        self._reload()

    def _on_clear(self):
        if not self.items:
            return
        if QMessageBox.question(self, "确认清空",
                                "清空整个功法黑名单(共 %d 门)?\n"
                                "清空后这些功法会重新出现在「添加功法…」候选里。"
                                % len(self.items)) != QMessageBox.StandardButton.Yes:
            return
        self.items = []
        self._save()
        self._reload()


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
        lst = self.item_list
        upd = lst.updatesEnabled()
        lst.setUpdatesEnabled(False)
        lst.blockSignals(True)
        try:
            lst.clear()
            for nm in self._filtered():
                it = QListWidgetItem(nm)
                if nm in self._existing:
                    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                    it.setToolTip("已在 _ActiveMap 中(无需重复添加)")
                lst.addItem(it)
        finally:
            lst.blockSignals(False)
            lst.setUpdatesEnabled(upd)
        self._update_stat()

    def _update_stat(self):
        total = len(self._all)
        has = len(set(self._all) & self._existing)   # 库中已在 _ActiveMap 的数量
        sel = len(self.item_list.selectedItems())
        self.stat_label.setText("跳转点库 %d · 已标注 %d · 缺少 %d · 已选 %d"
                                % (total, has, total - has, sel))
        self.btn_ok.setText("添加所选(%d)" % sel if sel else "添加所选")

    def _select_all(self):
        """全选可选跳转点(一次性区间选择 + 末尾一次统计)。"""
        with _BulkListEdit(self.item_list):
            _select_enabled_items(self.item_list)
        self._update_stat()

    def _select_none(self):
        with _BulkListEdit(self.item_list):
            self.item_list.clearSelection()
        self._update_stat()

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


class SettingsDialog(QDialog):
    """程序设置: 「保存后关闭当前文件」与「文件变化时自动刷新」两个开关(v2.10.0)。

    读入当前值供修改, 确定后由主窗口 _open_settings 把新值写回 MainWindow 并自动保存到 设置.json。
    """

    def __init__(self, parent=None, close_on_save=False, auto_reload=False):
        super().__init__(parent)
        self.setWindowTitle("设置 - %s" % APP_NAME)
        self.setMinimumWidth(480)
        lay = QVBoxLayout(self)
        tip = QLabel("两个防“编辑旧档 / 忘了刷新”的选项(改动即自动保存到 设置.json):")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#888;")
        lay.addWidget(tip)

        self.chk_close = QCheckBox("「保存」后关闭当前文件")
        self.chk_close.setChecked(bool(close_on_save))
        self.chk_close.setToolTip(
            "点「保存」把修改写回存档后, 自动清空并回到“未打开”状态。\n"
            "用途: 游戏再存档后编辑器若还停在上一份内容, 再保存就会把存档“打回上一次”;\n"
            "开启后每次保存完强制关闭当前文件, 下次需重新打开(打开上次/最近)拿到最新存档。")
        lay.addWidget(self.chk_close)

        self.chk_auto = QCheckBox("文件变化时自动刷新成新内容")
        self.chk_auto.setChecked(bool(auto_reload))
        self.chk_auto.setToolTip(
            "每 2 秒检查当前打开的文件是否被外部改动(如游戏里又存了档)。\n"
            "若磁盘内容与已打开内容不一致: 当前没有未保存修改 → 自动按新内容刷新;\n"
            "有未保存修改 → 只提示, 不覆盖(可手动「重新读取」丢弃修改)。")
        lay.addWidget(self.chk_auto)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                | QDialogButtonBox.StandardButton.Cancel)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("确定")
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def result_flags(self):
        """返回 (保存后关闭?, 自动刷新?)。"""
        return bool(self.chk_close.isChecked()), bool(self.chk_auto.isChecked())


class MainWindow(QMainWindow):
    # 固定页签: 0=道具 / 1=商店NPC / 2=蛊虫 / 3=装备; 角色页签从 4 开始(读档后动态增删)
    CHAR_TAB_BASE = 4

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
        # 标题状态(窗口标题尾部显示, v2.11.0): None/'saved'/'unsaved'/'refreshing'/'refreshed'
        self._title_state = None
        self._title_state_ts = ""     # 对应状态的 24 小时制 4 位毫秒时间戳(格式见 _format_ts)
        self._history = []   # 最近打开历史(最新在前, 来自 历史记录.json)
        self._sort_col = -1    # 最近排序列(1=名称/2=数量), -1=尚未排序
        self._sort_asc = True  # 最近一次方向: True=升序(小→大)
        self._filter_map = None    # 道具搜索: 表格当前可见行→self._items 索引; None=不过滤
        self._search_timer = None  # 搜索防抖定时器(在 _build_ui 里创建)
        self._busy = False     # 大档后台打开进行中标志(防重入/禁用工具栏)
        self._char_spin_map = {}  # (scope元组, 字段键) -> 数值框, 供「一键全部默认」原地刷新不整档重建
        self._dialogue_spins = {}  # 变量名 -> (数值框, 默认按钮); 主角页「剧情变量」(善恶值等)
        self._kangfu_ui = {}       # scope元组 -> {"list": 功法列表, "brief": [(段,段标题,名)]}; v2.14.0
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
        # 商店相关记忆: 卖品/装备 批量目标数量(默认 999) + 批量 折扣/刷新日 默认值(默认 0.5 / 1)
        try:
            self._shop_batch_value = int(self._settings.get("shop_batch_value", 999))
        except (TypeError, ValueError):
            self._shop_batch_value = 999
        self._shop_batch_value = max(0, min(self._shop_batch_value, MAX_ITEM_COUNT))
        try:
            self._discount_all = float(self._settings.get("discount_all", 0.5))
        except (TypeError, ValueError):
            self._discount_all = 0.5
        self._discount_all = max(0.0, min(1.0, self._discount_all))
        try:
            self._refresh_all = int(self._settings.get("refresh_all", 1))
        except (TypeError, ValueError):
            self._refresh_all = 1
        self._refresh_all = max(0, min(self._refresh_all, MAX_ITEM_COUNT))
        # 新增蛊虫对话框的默认值记忆(三项属性/只数/_Skill/_Preference 目标值; v2.13.0)
        _cd = self._settings.get("chong_add_defaults")
        self._chong_add_defaults = dict(_cd) if isinstance(_cd, dict) else {}
        # 「添加功法…」的等级 _Lv 记忆(v2.14.2; v2.14.3 起在框里改一下就立即写盘):
        # 改过就记住, 下次打开还是这个值, 不用每次重改
        try:
            self._kangfu_lv = int(self._settings.get("kangfu_lv", KANGFU_DEFAULT_LV))
        except (TypeError, ValueError):
            self._kangfu_lv = KANGFU_DEFAULT_LV
        self._kangfu_lv = max(0, min(self._kangfu_lv, MAX_ITEM_COUNT))
        # 功法黑名单(v2.15.0): 程序级数据(功法黑名单.json), 列入的功法在「添加功法…」候选里
        # 不显示、也不会被加给主角/队友 —— 用于先避开已知会卡死的功法, 以后再逐条查原因
        self._kangfu_blacklist = load_kangfu_blacklist()
        # 设置: 「保存后关闭当前文件」/「文件变化时自动刷新」(v2.10.0)
        self._close_on_save = bool(self._settings.get("close_on_save", False))
        self._auto_reload = bool(self._settings.get("auto_reload", False))
        self._auto_refreshing = False     # 自动刷新进行中: 读取成功后 _mark_clean 据此显示 [已刷新 - 时间戳]
        self._last_disk_sig = None        # 最近一次读/写文件时的磁盘签名 (mtime_ns,size)
        self._reload_notified_sig = None  # 自动刷新“有未保存修改不覆盖”提示去重
        self._auto_reload_timer = QTimer(self)   # 文件变化自动刷新轮询(2s; 未开启时 tick 直接返回)
        self._auto_reload_timer.setInterval(2000)
        self._auto_reload_timer.timeout.connect(self._on_auto_reload_tick)
        self._auto_reload_timer.start()
        self._settings_save_timer = QTimer(self)   # 500ms 防抖自动保存
        self._settings_save_timer.setSingleShot(True)
        self._settings_save_timer.setInterval(500)
        self._settings_save_timer.timeout.connect(self._save_settings_now)
        self._refresh_title()   # 初始标题: 未打开文档时不显示保存/刷新状态标记
        self.setWindowIcon(app_icon())
        self.resize(800, 600)
        self._build_ui()
        self._history = load_history()
        self._update_history_ui()

    # ---------------- 脏标记(未保存修改) 与 标题状态(v2.11.0) ----------------
    def _mark_dirty(self):
        """标记存在未保存修改; 标题显示 [未保存 - 时间戳](每次改动刷新为最近改动时刻)。

        同时**后台预热新文本的整档结构索引**: 改动后文本对象变了, 索引缓存失效, 下一次
        `_entry_values`/`_matching_end` 会在主线程冷建(8.6MB 档实测 ~1.3s, 表现为“改完角色
        属性再去点商店/地图就卡一下”)。预热放在后台线程, 用户下一次操作时索引已就绪。
        """
        self._dirty = True
        self._preheat_index_async(self._text)
        self._set_title_state("unsaved")

    @staticmethod
    def _preheat_index_async(text):
        """后台线程预热文本的整档结构索引(已缓存/已请求则立即返回)。"""
        if text is None or len(text) < 600 * 1024:
            return
        with _PREHEAT_LOCK:
            if _PREHEAT_LAST[0] is text:
                return
            _PREHEAT_LAST[0] = text
        threading.Thread(target=_get_struct_index, args=(text,), daemon=True).start()

    def _mark_clean(self):
        """标记内容已与来源同步(打开/粘贴/保存/另存成功)。
        若本次为自动刷新触发的读取, 标题显示 [已刷新 - 时间戳]。"""
        self._dirty = False
        if self._auto_refreshing:
            self._auto_refreshing = False
            self._set_title_state("refreshed")
        else:
            self._set_title_state("saved")

    def _set_title_state(self, state):
        """记录标题状态并即时刷新窗口标题。

        state 取值:
          'saved'      -> [已保存 - 时间戳](内容与磁盘/来源一致)
          'unsaved'    -> [未保存 - 时间戳](存在未保存修改)
          'refreshing' -> [正在刷新](自动刷新开始, 不带时间戳)
          'refreshed'  -> [已刷新 - 时间戳](自动刷新完成)
        """
        self._title_state = state
        self._title_state_ts = "" if state == "refreshing" else _format_ts()
        self._refresh_title()

    def _clear_title_state(self):
        """清空标题状态(未打开任何文档/文档已关闭), 标题回到纯净版本号。"""
        self._title_state = None
        self._title_state_ts = ""
        self._refresh_title()

    def _refresh_title(self):
        state, ts = self._title_state, self._title_state_ts
        if state == "saved":
            seg = "[已保存 - %s]" % ts
        elif state == "unsaved":
            seg = "[未保存 - %s]" % ts
        elif state == "refreshing":
            seg = "[正在刷新]"
        elif state == "refreshed":
            seg = "[已刷新 - %s]" % ts
        else:
            seg = ""
        self.setWindowTitle("%s v%s%s" % (APP_NAME, __version__, (" " + seg) if seg else ""))
        self._update_status_dot()

    # ---------------- 工具栏状态指示灯(v2.13.1) ----------------
    def _update_status_dot(self):
        """把工具栏「打开」左边的圆点刷成当前状态色(未打开=灰)。

        颜色映射见 STATUS_DOT_COLORS: 绿=已保存 / 红=未保存 / 黄=正在刷新 / 蓝=已刷新 / 灰=未打开。
        (在 _build_ui 之前也会被 _refresh_title 调到, 故用 getattr 保护。)
        """
        dot = getattr(self, "status_dot", None)
        if dot is None:
            return
        state = self._title_state if self._title_state in STATUS_DOT_COLORS else None
        color = STATUS_DOT_COLORS[state]
        dot.setStyleSheet("background-color:%s; border-radius:7px;" % color)
        dot.setToolTip("%s\n\n%s" % (STATUS_DOT_HINT,
                                     "当前状态: %s" % STATUS_DOT_LABELS[state]))

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

        # 状态指示灯(v2.13.1): 「打开」左边的圆点, 颜色随状态变(绿=已保存/红=未保存/
        # 黄=正在刷新/蓝=已刷新/灰=未打开), 鼠标悬停有颜色说明 —— 一眼看出当前有没有存盘。
        self.status_dot = QLabel()
        self.status_dot.setFixedSize(14, 14)
        self.status_dot.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.status_dot.setStyleSheet("background-color:%s; border-radius:7px;"
                                      % STATUS_DOT_COLORS[None])
        self.status_dot.setToolTip(STATUS_DOT_HINT)
        self.status_dot.setFocusPolicy(Qt.FocusPolicy.NoFocus)   # 纯展示, 不接收焦点
        toolbar.addWidget(self.status_dot)
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
        _add_act("设置…", self._open_settings)
        # 功法黑名单(v2.15.0): 把已知会卡死的功法记下来避开(程序级数据, 与存档无关)
        self.act_kangfu_black = _add_act("功法黑名单…", self._open_kangfu_blacklist)
        self.act_kangfu_black.setToolTip(
            "列出已知会让游戏卡死的功法: 加入后「＋ 添加功法…」候选里不再显示,\n"
            "也不会被加给主角/队友(先避开, 以后有空再逐条查是剧情没到还是别的原因);\n"
            "可批量加入/移出, 并逐条写备注")

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
        self.btn_sel = QPushButton("选中改为 %d" % self._batch_value)
        self.btn_sel.clicked.connect(self._on_set_selected_value)
        self.btn_sel.setToolTip("把表格里当前选中的道具(可 Ctrl/拖动多选)数量改成右侧目标值; 尊重「跳过铜钱」")
        self.btn_time0 = QPushButton("一键 _GetTimeNew→0")
        self.btn_time0.clicked.connect(self._on_set_get_time_zero)
        row1.addWidget(self.btn_9999)
        row1.addWidget(self.skip_copper_check)
        row1.addSpacing(14)
        row1.addWidget(QLabel("全部改为:"))
        row1.addWidget(self.all_spin)
        row1.addWidget(self.btn_all)
        row1.addWidget(self.btn_sel)
        row1.addSpacing(14)
        row1.addWidget(self.btn_time0)
        row1.addStretch(1)
        tlay.addLayout(row1)

        row2 = QHBoxLayout()
        self.btn_add = QPushButton("＋ 新增道具")
        self.btn_add.clicked.connect(self._on_add)
        self.btn_add_player_equip = QPushButton("＋ 添加装备…(EquipHad)")
        self.btn_add_player_equip.setToolTip(
            "把 装备类(equip, 如 1铁盔/7盟主之冠)加入主角存档的 EquipHad 装备段(equip 不进 ItemHad)。\n"
            "弹窗只显示 equip 分类; 装备可同名不堆叠——右侧「件数」填几就加几个同名实例\n"
            "(如填 5 = 加 5 个斩龙剑; 已有同名也照加, 不跳过; 名字前导数字=等级);\n"
            "点「保存/另存为/复制结果」随存档写回。")
        self.btn_add_player_equip.clicked.connect(self._on_add_player_equip)
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
        row2.addWidget(self.btn_add_player_equip)
        row2.addWidget(self.btn_organize)
        row2.addWidget(self.btn_del)
        row2.addStretch(1)
        row2.addWidget(self.count_label)
        tlay.addLayout(row2)
        self.tabs.addTab(tab_items, "道具")
        # 商店NPC页签(固定 index=1): 读档后由 _refresh_shop_tab 填充 NPC/卖品
        self.tabs.addTab(self._build_shop_tab(), "商店NPC")
        # 蛊虫页签(固定 index=2): 读档后由 _refresh_chong_tab 填充 ChongHad
        self.tabs.addTab(self._build_chong_tab(), "蛊虫")
        # 装备页签(固定 index=3): 读档后由 _refresh_equip_tab 填充 EquipHad 实例
        self.tabs.addTab(self._build_equip_tab(), "装备")

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

    def _reload_table(self, progress=None):
        """按 self._items/当前过滤重建表格。

        progress 非 None 且行数多时: 分块填充 + 泵事件 + 状态栏进度(打开大档时用, 窗口不假死、
        能看到「正在显示道具表 1200/3974…」; 分块有一成左右的时间开销, 所以排序/搜索/增删等
        普通重建不传 progress, 保持最快)。期间用 `_table_reloading` 守卫挡住重入。
        """
        if getattr(self, "_table_reloading", False):
            return
        self._table_reloading = True
        self._loading = True
        t = self.table
        upd = t.updatesEnabled()
        t.setUpdatesEnabled(False)   # 重建期间暂停重绘/信号, 上千行时明显更快(防逐行闪烁)
        t.blockSignals(True)
        try:
            shown = self._build_filter_map()
            t.setRowCount(shown)
            chunk = 400 if (shown > 800 and progress) else 0
            if self._filter_map is None:
                for r, it in enumerate(self._items):
                    self._fill_item_row(r, r, it)
                    if chunk and r and r % chunk == 0:
                        t.setUpdatesEnabled(True)          # 短暂开启重绘, 让进度可见
                        self._pump(progress % (r, shown))
                        t.setUpdatesEnabled(False)
            else:
                fm = self._filter_map
                items = self._items
                for r, real in enumerate(fm):
                    self._fill_item_row(r, real, items[real])
        finally:
            t.blockSignals(False)
            t.setUpdatesEnabled(upd)
            self._loading = False
            self._table_reloading = False
        self._set_count_label()

    def _append_rows_local(self, start):
        """无过滤视图下只追加 [start, len(self._items)) 的新行。

        ★ 添加道具后不要整表重建: 4000 行的表重建要 ~1s(还要重填全部已有行), 而新加的
          往往只有几个/几十个 —— 只建新增行再加一次计数刷新, 添加立即响应。
          有搜索过滤时不能走这里(行号≠数据序), 调用方先清搜索或整表重建。
        """
        t = self.table
        n = len(self._items)
        start = max(0, min(start, n))
        self._loading = True
        upd = t.updatesEnabled()
        t.setUpdatesEnabled(False)
        t.blockSignals(True)
        try:
            t.setRowCount(n)
            items = self._items
            for r in range(start, n):
                self._fill_item_row(r, r, items[r])
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
        self.shop_list.setToolTip("点选 NPC 后右侧显示其 SellItems/装备; 可按住 Ctrl 或拖动多选(配合上方「应用到选中」批量改折扣/刷新日)")
        self.shop_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        lv.addWidget(self.shop_list, 1)
        lv_box = QWidget()
        lv_box.setLayout(lv)
        h.addWidget(lv_box, 1)
        rv = QVBoxLayout()
        # —— 右侧用分类标签页: 卖品 / 装备 / NPC参数 分页承载, 一屏不堆满 ——
        self.shop_title = QLabel("未选 NPC")
        rv.addWidget(self.shop_title)
        # 批量目标(卖品数量/装备件数)放标签页上方, 两页共用且改动自动记忆
        self.shop_batch_spin = QSpinBox()
        self.shop_batch_spin.setRange(0, MAX_ITEM_COUNT)
        self.shop_batch_spin.setValue(self._shop_batch_value)
        self.shop_batch_spin.setMinimumWidth(90)
        self.shop_batch_spin.setToolTip(
            "批量目标值: 卖品「选中改数量」与装备「选中改件数」都用它\n"
            "(装备件数 0 = 删除整种; 修改自动记忆)")
        self.shop_batch_spin.valueChanged.connect(self._on_shop_batch_value_changed)
        _brow = QHBoxLayout()
        _brow.addWidget(QLabel("批量目标(数量/件数):"))
        _brow.addWidget(self.shop_batch_spin)
        _brow.addStretch(1)
        rv.addLayout(_brow)
        self.shop_right_tabs = QTabWidget()

        # ---------- 页「卖品 SellItems」 ----------
        _sp = QWidget()
        _sl = QVBoxLayout(_sp)
        self.shop_items = QTableWidget(0, 2)
        self.shop_items.setHorizontalHeaderLabels(["卖品名称", "数量"])
        self.shop_items.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.shop_items.setColumnWidth(1, 90)
        self.shop_items.verticalHeader().setVisible(False)
        self.shop_items.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.shop_items.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.shop_items.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.shop_items.setToolTip("该 NPC 卖品; 可按住 Ctrl 或拖动多选后 删除/一键改数量")
        _sl.addWidget(self.shop_items, 1)
        self.btn_add_sell = QPushButton("＋ 添加卖品…")
        self.btn_add_sell.setToolTip("从 道具名.json 搜索/多选添加道具到该 NPC 的 SellItems(默认数量 999; 与已有同名自动跳过)")
        self.btn_add_sell.clicked.connect(self._on_shop_add)
        _a1 = QHBoxLayout()
        _a1.addWidget(self.btn_add_sell)
        _a1.addStretch(1)
        _sl.addLayout(_a1)
        self.btn_shop_item_del = QPushButton("删除选中卖品")
        self.btn_shop_item_del.setToolTip("把卖品表选中的道具整件下架(可 Ctrl/拖动多选); 需确认")
        self.btn_shop_item_del.clicked.connect(self._on_shop_item_del)
        self.btn_shop_item_set = QPushButton("选中改数量")
        self.btn_shop_item_set.setToolTip("把卖品表选中道具的数量改成上方「批量目标」数字框的值")
        self.btn_shop_item_set.clicked.connect(self._on_shop_item_set)
        _b1 = QHBoxLayout()
        _b1.addWidget(self.btn_shop_item_del)
        _b1.addWidget(self.btn_shop_item_set)
        _b1.addStretch(1)
        _sl.addLayout(_b1)
        self.shop_right_tabs.addTab(_sp, "卖品")

        # ---------- 页「装备 SellEquips」 ----------
        _ep = QWidget()
        _el = QVBoxLayout(_ep)
        self.equip_table = QTableWidget(0, 2)
        self.equip_table.setHorizontalHeaderLabels(["装备名称", "件数"])
        self.equip_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.equip_table.setColumnWidth(1, 60)
        self.equip_table.verticalHeader().setVisible(False)
        self.equip_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.equip_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.equip_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.equip_table.setToolTip("该 NPC 已上架装备(同名可多件); 可多选后删除或改件数(件数目标=上方「批量目标」框, 0=删除整种)")
        _el.addWidget(self.equip_table, 1)
        self.btn_add_equip = QPushButton("＋ 添加装备…(SellEquips)")
        self.btn_add_equip.setToolTip(
            "把 装备类(equip, 如 1短铁棍/3喵金贵的衣物)加进该 NPC 的 SellEquips 装备栏。\n"
            "在左树勾选 equip 分类后多选; 件数=同名副本数(默认 1)。同名已有→向该名数组追加副本, 新名→新增条目; \n"
            "前导数字=等级(_Lv, 如 1短铁棍→_Lv 1)。")
        self.btn_add_equip.clicked.connect(self._on_shop_add_equip)
        _a2 = QHBoxLayout()
        _a2.addWidget(self.btn_add_equip)
        _a2.addStretch(1)
        _el.addLayout(_a2)
        self.btn_equip_del = QPushButton("删除选中装备")
        self.btn_equip_del.setToolTip("把选中装备整种下架(同名所有件一起删); 需确认")
        self.btn_equip_del.clicked.connect(self._on_shop_equip_del)
        self.btn_equip_set = QPushButton("选中改件数")
        self.btn_equip_set.setToolTip("把选中装备的件数(同名副本数)改成上方「批量目标」框的值; 0=删除整种")
        self.btn_equip_set.clicked.connect(self._on_shop_equip_set)
        _b2 = QHBoxLayout()
        _b2.addWidget(self.btn_equip_del)
        _b2.addWidget(self.btn_equip_set)
        _b2.addStretch(1)
        _el.addLayout(_b2)
        self.shop_right_tabs.addTab(_ep, "装备")

        # ---------- 页「NPC 参数」(折扣/刷新日 + 批量应用) ----------
        _pp = QWidget()
        _pl = QVBoxLayout(_pp)
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
        _pl.addWidget(_g)
        _bg = QGroupBox("批量折扣 / 刷新日(可一键应用到选中或全部 NPC)")
        _bf = QFormLayout(_bg)
        self.discount_all_spin = QDoubleSpinBox()
        self.discount_all_spin.setRange(0.0, 1.0)
        self.discount_all_spin.setSingleStep(0.05)
        self.discount_all_spin.setDecimals(2)
        self.discount_all_spin.setValue(self._discount_all)
        self.discount_all_spin.setToolTip("一键应用时的折扣值(默认 0.5=五折; 修改自动记忆)")
        self.refresh_all_spin = QSpinBox()
        self.refresh_all_spin.setRange(0, MAX_ITEM_COUNT)
        self.refresh_all_spin.setValue(self._refresh_all)
        self.refresh_all_spin.setToolTip("一键应用时的刷新日(默认 1; 修改自动记忆)")
        _bw = QWidget()
        _bl2 = QHBoxLayout(_bw)
        _bl2.setContentsMargins(0, 0, 0, 0)
        _bl2.addWidget(self.discount_all_spin, 1)
        _bl2.addWidget(QLabel("刷新日:"))
        _bl2.addWidget(self.refresh_all_spin, 1)
        _bf.addRow("批量折扣:", _bw)
        self.btn_npc_sel = QPushButton("应用到选中 NPC")
        self.btn_npc_sel.setToolTip("把批量折扣/刷新日应用到左侧选中的 NPC(可 Ctrl 多选; 无选中=当前选中)")
        self.btn_npc_all = QPushButton("应用到全部 NPC")
        self.btn_npc_all.setToolTip("把批量折扣/刷新日一键应用到全部商店 NPC(含没有该字段的店自动补写)")
        self.btn_npc_sel.clicked.connect(lambda: self._on_shop_npc_apply(False))
        self.btn_npc_all.clicked.connect(lambda: self._on_shop_npc_apply(True))
        self.discount_all_spin.valueChanged.connect(self._on_shop_discount_all_changed)
        self.refresh_all_spin.valueChanged.connect(self._on_shop_refresh_all_changed)
        _bbw = QWidget()
        _bbl = QHBoxLayout(_bbw)
        _bbl.setContentsMargins(0, 0, 0, 0)
        _bbl.addWidget(self.btn_npc_sel, 1)
        _bbl.addWidget(self.btn_npc_all, 1)
        _bf.addRow(_bbw)
        _pl.addWidget(_bg)
        _pl.addStretch(1)
        self.shop_right_tabs.addTab(_pp, "NPC 参数")

        rv.addWidget(self.shop_right_tabs, 1)
        rv_box = QWidget()
        rv_box.setLayout(rv)
        h.addWidget(rv_box, 2)
        lay.addLayout(h, 1)
        self._refresh_shop_tab()
        return page

    # ---------------- 蛊虫(ChongHad)页(v2.13.0) ----------------
    def _build_chong_tab(self):
        """蛊虫页: 左=存档里的蛊虫列表, 右=属性 / 技能 _Skill / 偏好 _Preference / 批量 四个分页。"""
        page = QWidget()
        lay = QVBoxLayout(page)
        self._chong_loading = False
        self._chong_model = []
        self._chong_dict_tables = {}
        self._chong_dict_rows = {}
        self._chong_dict_spins = {}

        note = QLabel(
            "蛊虫(ChongHad, 存于 savePlayerData.value)：可新增/删除蛊虫、改 显示名 / 培养值 / "
            "力道·灵气·体魄，以及 _Skill(状态累积值) 与 _Preference(状态倍率)。\n"
            "★ 改了 力道 / 灵气 / 体魄 后，_TotalProperty 会自动写成 0（游戏会重算培养累计属性，"
            "留旧值容易出错）。\n"
            "蛊虫可用状态（实测存档 5 类虫罐 毒/穴/血/火/冰）：中毒 / 流血 / 着火 / 点穴 / 冰冻。"
            "改完点工具栏「保存 / 另存为 / 复制结果」才写回存档。")
        note.setWordWrap(True)
        note.setStyleSheet("color:#888;")
        lay.addWidget(note)

        row = QHBoxLayout()
        self.btn_chong_add = QPushButton("＋ 添加蛊虫…")
        self.btn_chong_add.setToolTip(
            "从 蛊虫名.json（由 _scaffold/build_chong_names.py 从 内存所有道具.json 的 dataset/chong 生成，\n"
            "108 只）里选蛊虫加入 ChongHad；可搜索（中文/拼音）/多选/全选。\n"
            "蛊虫不堆叠：每只都是一条独立条目，「只数」填几就加几条（同装备）。\n"
            "新增时可设默认 力道/灵气/体魄(默认 9999) 与 培养上限(默认 9999)、"
            "_Skill/_Preference 的默认值(默认 9999)，\n"
            "并可选「写入全部状态」或「写入全部技能库(%d 项)」。" % skill_lib_count())
        self.btn_chong_add.clicked.connect(self._on_chong_add)
        self.btn_chong_del = QPushButton("－ 删除选中")
        self.btn_chong_del.setToolTip("删除左列表中选中的蛊虫（可 Ctrl/Shift 多选）")
        self.btn_chong_del.clicked.connect(self._on_chong_del)
        btn_refresh = QPushButton("刷新")
        btn_refresh.setToolTip("按当前存档内容重新读取蛊虫列表")
        btn_refresh.clicked.connect(lambda: self._refresh_chong_tab())
        self.chong_count_label = QLabel("蛊虫: 0")
        row.addWidget(self.btn_chong_add)
        row.addWidget(self.btn_chong_del)
        row.addWidget(btn_refresh)
        row.addStretch(1)
        row.addWidget(self.chong_count_label)
        lay.addLayout(row)

        body = QHBoxLayout()
        self.chong_list = QListWidget()
        self.chong_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.chong_list.setMinimumWidth(250)
        self.chong_list.setToolTip("存档 ChongHad 里的蛊虫；选中一条即可在右侧改它的属性/技能/偏好")
        self.chong_list.itemSelectionChanged.connect(self._on_chong_selected)
        body.addWidget(self.chong_list, 0)
        self.chong_right_tabs = QTabWidget()
        self.chong_right_tabs.addTab(self._chong_build_attr_page(), "属性")
        self.chong_right_tabs.addTab(self._chong_build_dict_page("_Skill", "技能 _Skill(状态累积值)"),
                                     "技能 _Skill")
        self.chong_right_tabs.addTab(self._chong_build_dict_page("_Preference", "偏好 _Preference(状态倍率)"),
                                     "偏好 _Preference")
        self.chong_right_tabs.addTab(self._chong_build_batch_page(), "批量(全部蛊虫)")
        body.addWidget(self.chong_right_tabs, 1)
        lay.addLayout(body, 1)
        return page

    def _chong_build_attr_page(self):
        """蛊虫「属性」分页: 显示名 / _Love / _Foster / _FosterMax / 三项属性 / _TotalProperty。"""
        page = QWidget()
        v = QVBoxLayout(page)
        self.chong_name_label = QLabel("未选择蛊虫（请在左侧点选一条）")
        self.chong_name_label.setStyleSheet("font-weight:bold;")
        v.addWidget(self.chong_name_label)
        tip = QLabel("选中一条蛊虫后可改；改完点「保存/另存为/复制结果」写回存档。")
        tip.setStyleSheet("color:#888;")
        v.addWidget(tip)
        form = QFormLayout()
        self.chong_custom_edit = QLineEdit()
        self.chong_custom_edit.setToolTip("_CustomName：游戏里显示的蛊虫名字（数据集名 d_dataname 不改）")
        self.chong_custom_edit.editingFinished.connect(self._on_chong_custom_changed)
        form.addRow(QLabel("显示名 _CustomName"), self.chong_custom_edit)
        self.chong_love_check = QCheckBox("_Love(喜爱标记)")
        self.chong_love_check.toggled.connect(self._on_chong_love_changed)
        form.addRow(QLabel(""), self.chong_love_check)
        self.chong_foster_spin = QSpinBox()
        self.chong_foster_spin.setRange(0, MAX_ITEM_COUNT)
        self.chong_foster_spin.valueChanged.connect(self._on_chong_foster_changed)
        form.addRow(QLabel("培养值 _Foster"), self.chong_foster_spin)
        self.chong_fostermax_spin = QSpinBox()
        self.chong_fostermax_spin.setRange(0, MAX_ITEM_COUNT)
        self.chong_fostermax_spin.valueChanged.connect(self._on_chong_fostermax_changed)
        self.btn_chong_fostermax_dflt = QPushButton("默认 %d" % CHONG_FOSTER_MAX_DEFAULT)
        self.btn_chong_fostermax_dflt.setToolTip("把培养上限 _FosterMax 一键设为 %d"
                                                 % CHONG_FOSTER_MAX_DEFAULT)
        self.btn_chong_fostermax_dflt.clicked.connect(
            lambda _=False, s=self.chong_fostermax_spin: s.setValue(CHONG_FOSTER_MAX_DEFAULT))
        _fmw = QHBoxLayout()
        _fmw.addWidget(self.chong_fostermax_spin)
        _fmw.addWidget(self.btn_chong_fostermax_dflt)
        _fmw.addStretch(1)
        form.addRow(QLabel("培养上限 _FosterMax"), _fmw)
        v.addLayout(form)

        box = QGroupBox("三项属性（改后 _TotalProperty 自动写 0）")
        f2 = QFormLayout(box)
        self.chong_prop_spins = {}
        for f in CHONG_PROP_FIELDS:
            sp = QSpinBox()
            sp.setRange(0, MAX_ITEM_COUNT)
            btn = QPushButton("默认 %d" % CHONG_PROP_DEFAULT)
            btn.setToolTip("把 %s(%s) 一键设为默认 %d" % (CHONG_PROP_LABELS[f], f, CHONG_PROP_DEFAULT))
            btn.clicked.connect(lambda _=False, s=sp: s.setValue(CHONG_PROP_DEFAULT))
            hb = QHBoxLayout()
            hb.addWidget(sp)
            hb.addWidget(btn)
            hb.addStretch(1)
            sp.valueChanged.connect(lambda val, ff=f: self._on_chong_prop_changed(ff, val))
            f2.addRow(QLabel("%s(%s)" % (CHONG_PROP_LABELS[f], f)), hb)
            self.chong_prop_spins[f] = sp
        self.chong_total_label = QLabel("-")
        self.chong_total_label.setToolTip("存档里的 _TotalProperty；改动三项属性后本程序一律写 0")
        f2.addRow(QLabel("累计属性 _TotalProperty"), self.chong_total_label)
        v.addWidget(box)
        btn_all = QPushButton("本只：三项属性一键 = %d" % CHONG_PROP_DEFAULT)
        btn_all.setToolTip("把本只蛊虫的 力道/灵气/体魄 一起设为 %d（并把 _TotalProperty 写 0）"
                           % CHONG_PROP_DEFAULT)
        btn_all.clicked.connect(self._on_chong_props_default)
        v.addWidget(btn_all)
        btn_fm = QPushButton("本只：培养上限一键 = %d" % CHONG_FOSTER_MAX_DEFAULT)
        btn_fm.setToolTip("把本只蛊虫的培养上限 _FosterMax 设为 %d" % CHONG_FOSTER_MAX_DEFAULT)
        btn_fm.clicked.connect(self._on_chong_fostermax_default)
        v.addWidget(btn_fm)
        v.addStretch(1)
        return page

    def _chong_build_dict_page(self, field, title):
        """蛊虫「技能 _Skill」/「偏好 _Preference」分页: 表格(状态→数值) + 一键按钮。"""
        page = QWidget()
        v = QVBoxLayout(page)
        tip = QLabel(
            ("%s：存档里写成 {\"状态\":数值}。\n"
             "「补齐全部状态」= 把 中毒/流血/着火/点穴/冰冻 5 种都写入(缺的补、有的改成目标值)；\n"
             "「写入全部技能库(%d 项)」= 把 技能名.json 的全部战斗类技能名都写入(只含 被动/战斗 pass\n"
             "与 特殊/临时 todu; 生活技能/工具/测试未整理已排除。存档会变大, 游戏可能忽略不认识的技能名)。")
            % (title, skill_lib_count()))
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#888;")
        v.addWidget(tip)
        row = QHBoxLayout()
        sp = QSpinBox()
        sp.setRange(0, MAX_ITEM_COUNT)
        sp.setValue(CHONG_SKILL_DEFAULT if field == "_Skill" else CHONG_PREF_DEFAULT)
        sp.setToolTip("一键写入的目标值（默认 %d，可自定义）"
                      % (CHONG_SKILL_DEFAULT if field == "_Skill" else CHONG_PREF_DEFAULT))
        row.addWidget(QLabel("目标值:"))
        row.addWidget(sp)
        btn_all = QPushButton("本只：全部 → 目标值")
        btn_all.setToolTip("把本只蛊虫 %s 里的每个状态都改成目标值" % field)
        btn_all.clicked.connect(lambda _=False, f=field: self._chong_set_all(f, self._chong_dict_spins[f].value(),
                                                                            None))
        btn_fill = QPushButton("本只：补齐全部状态(5 种)")
        btn_fill.setToolTip("把 中毒/流血/着火/点穴/冰冻 全部写入（缺的补上、有的设为目标值）")
        btn_fill.clicked.connect(lambda _=False, f=field: self._chong_set_all(f, self._chong_dict_spins[f].value(),
                                                                             list(CHONG_SKILLS)))
        btn_lib = QPushButton("本只：写入全部技能库(%d 项)" % skill_lib_count())
        btn_lib.setToolTip("把 技能名.json 的全部战斗类技能名都写入(只含 被动/战斗 pass 与 特殊/临时 todu;\n"
                           "生活技能/工具/测试未整理已排除)。存档会明显变大, 仅供调试用。")
        btn_lib.clicked.connect(lambda _=False, f=field: self._chong_set_all(
            f, self._chong_dict_spins[f].value(), list(load_skill_names())))
        btn_add = QPushButton("＋ 添加状态…")
        btn_add.setToolTip("从技能库(技能名.json)里挑一条/多条状态名加入本只蛊虫（未选蛊虫时加入候选会提示）")
        btn_add.clicked.connect(lambda _=False, f=field: self._on_chong_add_states(f))
        btn_del = QPushButton("－ 删除选中行")
        btn_del.setToolTip("把本只蛊虫里选中的状态条目删掉（按住 Ctrl 可多选行）")
        btn_del.clicked.connect(lambda _=False, f=field: self._on_chong_del_states(f))
        row.addWidget(btn_all)
        row.addWidget(btn_fill)
        row.addWidget(btn_lib)
        row.addWidget(btn_add)
        row.addWidget(btn_del)
        row.addStretch(1)
        v.addLayout(row)

        t = QTableWidget(0, 2)
        t.setHorizontalHeaderLabels(["状态", "数值"])
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        t.setColumnWidth(1, 140)
        t.verticalHeader().setVisible(False)
        t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        t.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        t.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                          | QAbstractItemView.EditTrigger.EditKeyPressed
                          | QAbstractItemView.EditTrigger.SelectedClicked)
        t.itemChanged.connect(self._on_chong_dict_cell_changed)
        v.addWidget(t, 1)
        self._chong_dict_tables[field] = t
        self._chong_dict_rows[field] = []
        self._chong_dict_spins[field] = sp
        return page

    def _chong_build_batch_page(self):
        """蛊虫「批量(全部蛊虫)」分页: 对存档里所有蛊虫一次性设 _Skill/_Preference/三项属性。"""
        page = QWidget()
        v = QVBoxLayout(page)
        tip = QLabel("以下操作作用于当前存档里的**全部蛊虫**；全部写回后点「保存/另存为/复制结果」落盘。")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#888;")
        v.addWidget(tip)
        self._chong_batch_spins = {}
        for field, label, dflt in (("_Skill", "技能 _Skill", CHONG_SKILL_DEFAULT),
                                   ("_Preference", "偏好 _Preference", CHONG_PREF_DEFAULT)):
            box = QGroupBox("%s —— 全部蛊虫" % label)
            hb = QHBoxLayout(box)
            sp = QSpinBox()
            sp.setRange(0, MAX_ITEM_COUNT)
            sp.setValue(dflt)
            b1 = QPushButton("补齐 5 种状态 =")
            b1.setToolTip("给全部蛊虫补上 中毒/流血/着火/点穴/冰冻（缺的补、有的设为目标值）")
            b1.clicked.connect(lambda _=False, f=field: self._chong_batch(f, False))
            b2 = QPushButton("写入全部技能库 =")
            b2.setToolTip("把 技能名.json 的全部技能名写入全部蛊虫（存档会明显变大）")
            b2.clicked.connect(lambda _=False, f=field: self._chong_batch(f, True))
            b3 = QPushButton("清空")
            b3.setToolTip("把全部蛊虫的该状态字典清空（写成空字典）")
            b3.clicked.connect(lambda _=False, f=field: self._chong_batch(f, None))
            hb.addWidget(sp)
            hb.addWidget(b1)
            hb.addWidget(b2)
            hb.addWidget(b3)
            hb.addStretch(1)
            v.addWidget(box)
            self._chong_batch_spins[field] = sp
        box = QGroupBox("三项属性 —— 全部蛊虫")
        hb = QHBoxLayout(box)
        sp = QSpinBox()
        sp.setRange(0, MAX_ITEM_COUNT)
        sp.setValue(CHONG_PROP_DEFAULT)
        b1 = QPushButton("力道/灵气/体魄 =")
        b1.setToolTip("把全部蛊虫的三项属性设为目标值（并把 _TotalProperty 写 0）")
        b1.clicked.connect(lambda: self._chong_batch_props(sp.value()))
        b2 = QPushButton("默认 %d" % CHONG_PROP_DEFAULT)
        b2.setToolTip("把左侧数字框重置为默认 %d" % CHONG_PROP_DEFAULT)
        b2.clicked.connect(lambda _=False, s=sp: s.setValue(CHONG_PROP_DEFAULT))
        hb.addWidget(sp)
        hb.addWidget(b1)
        hb.addWidget(b2)
        hb.addStretch(1)
        v.addWidget(box)
        box = QGroupBox("培养上限 _FosterMax —— 全部蛊虫")
        hb = QHBoxLayout(box)
        sp2 = QSpinBox()
        sp2.setRange(0, MAX_ITEM_COUNT)
        sp2.setValue(CHONG_FOSTER_MAX_DEFAULT)
        f1 = QPushButton("培养上限 =")
        f1.setToolTip("把全部蛊虫的 _FosterMax 设为目标值")
        f1.clicked.connect(lambda: self._chong_batch_fostermax(sp2.value()))
        f2 = QPushButton("默认 %d" % CHONG_FOSTER_MAX_DEFAULT)
        f2.setToolTip("把左侧数字框重置为默认 %d" % CHONG_FOSTER_MAX_DEFAULT)
        f2.clicked.connect(lambda _=False, s=sp2: s.setValue(CHONG_FOSTER_MAX_DEFAULT))
        hb.addWidget(sp2)
        hb.addWidget(f1)
        hb.addWidget(f2)
        hb.addStretch(1)
        v.addWidget(box)
        v.addStretch(1)
        return page

    # ---- 蛊虫页: 读写 ----
    def _chong_cur(self):
        """当前选中的唯一一条蛊虫的模型项(名称/对象开括号); 未选或多选返回 None。"""
        sel = self.chong_list.selectedItems()
        if len(sel) != 1:
            return None
        r = self.chong_list.row(sel[0])      # QListWidgetItem 无 row(), 必须由列表反查
        if 0 <= r < len(self._chong_model):
            return self._chong_model[r]
        return None

    def _refresh_chong_tab(self, model=None):
        """按当前 self._text 重建蛊虫列表与右侧面板。

        model=None 且当前是大档时, 蛊虫模型计算走后台线程(实测 8.6MB 档 ~0.12s, 一并后台化,
        避免以后蛊虫数量变多后卡 UI; 忙时同步回退)。
        """
        if getattr(self, "chong_list", None) is None:
            return
        if model is None and self._text:
            if len(self._text) >= self._ASYNC_OPEN_MIN:
                t = self._text
                ok, rr = self._run_bg(lambda: chong_model(t), "正在读取蛊虫数据…请稍候")
                model = rr if ok else chong_model(t)
            else:
                model = chong_model(self._text)
        self._chong_model = model if model is not None else []
        keep = [it.text() for it in self.chong_list.selectedItems()]
        self._chong_loading = True
        try:
            self.chong_list.clear()
            for rec in self._chong_model:
                it = QListWidgetItem("%d. %s" % (rec["idx"] + 1, self._chong_line(rec)))
                it.setToolTip(self._chong_tip(rec))
                self.chong_list.addItem(it)
            # 恢复之前的选择(按文本匹配; 顺序不变时即同行)
            for txt in keep:
                for r in range(self.chong_list.count()):
                    if self.chong_list.item(r).text() == txt:
                        self.chong_list.item(r).setSelected(True)
                        break
            self.chong_count_label.setText("蛊虫: %d 只" % len(self._chong_model))
        finally:
            self._chong_loading = False
        self._on_chong_selected()

    def _on_chong_selected(self):
        """列表选中变化: 填充右侧 属性 / _Skill / _Preference 面板(多选或未选则留空)。"""
        if getattr(self, "_chong_loading", False):
            return
        ent = self._chong_cur()
        multi = len(self.chong_list.selectedItems()) > 1
        self._chong_loading = True
        try:
            if ent is None:
                self.chong_name_label.setText("未选择蛊虫（请在左侧点选一条）" if not multi
                                              else "已选中多条蛊虫：属性/技能面板只支持单条修改，"
                                                   "可用右侧「批量(全部蛊虫)」分页")
                self.chong_custom_edit.setText("")
                self.chong_love_check.setChecked(False)
                for sp in (self.chong_foster_spin, self.chong_fostermax_spin):
                    sp.setValue(0)
                for f in CHONG_PROP_FIELDS:
                    self.chong_prop_spins[f].setValue(0)
                self.chong_total_label.setText("-")
                for f in ("_Skill", "_Preference"):
                    self._chong_fill_dict_table(f, [], False)
            else:
                dn = ent.get("dataname") or ""
                self.chong_name_label.setText(
                    "%s　【d_dataname = %s】" % (ent.get("custom") or dn, dn))
                self.chong_custom_edit.setText(ent.get("custom") or "")
                self.chong_love_check.setChecked(bool(ent.get("love")))
                self.chong_foster_spin.setValue(self._chong_int(ent.get("_Foster")))
                self.chong_fostermax_spin.setValue(self._chong_int(ent.get("_FosterMax")))
                for f in CHONG_PROP_FIELDS:
                    self.chong_prop_spins[f].setValue(self._chong_int(ent.get(f)))
                self.chong_total_label.setText(str(ent.get("_TotalProperty") or "-"))
                for f, key in (("_Skill", "skill"), ("_Preference", "pref")):
                    self._chong_fill_dict_table(f, ent.get(key) or [], True)
        finally:
            self._chong_loading = False

    @staticmethod
    def _chong_int(raw):
        """把存档里的数值文本转 int(取不到则 0)。"""
        try:
            return int(float(raw))
        except (TypeError, ValueError):
            return 0

    def _chong_fill_dict_table(self, field, pairs, enabled):
        """填充 _Skill/_Preference 表格(状态 | 数值)。"""
        t = self._chong_dict_tables.get(field)
        if t is None:
            return
        old = self._chong_loading
        self._chong_loading = True
        try:
            t.setRowCount(0)
            for k, val in pairs:
                r = t.rowCount()
                t.insertRow(r)
                it0 = QTableWidgetItem(str(k))
                it0.setFlags(it0.flags() & ~Qt.ItemFlag.ItemIsEditable)
                t.setItem(r, 0, it0)
                it1 = QTableWidgetItem(str(val))
                t.setItem(r, 1, it1)
            t.setEnabled(bool(enabled))
            self._chong_dict_rows[field] = [k for k, _v in pairs]
        finally:
            self._chong_loading = old

    def _chong_sync_model(self):
        """整模重建(仅用于条目集合变化: 新增/删除/批量): 重算模型与列表文字。"""
        if self._text is None:
            return
        self._chong_model = chong_model(self._text)
        self._chong_refresh_list_texts()
        self._on_chong_selected()

    def _chong_refresh_list_texts(self):
        """只把左列表每行的文字/提示按当前模型刷新(不动右侧面板)。"""
        old = self._chong_loading
        self._chong_loading = True
        try:
            for r, rec in enumerate(self._chong_model):
                if r >= self.chong_list.count():
                    break
                it = self.chong_list.item(r)
                it.setText("%d. %s" % (rec["idx"] + 1, self._chong_line(rec)))
                it.setToolTip(self._chong_tip(rec))
            self.chong_count_label.setText("蛊虫: %d 只" % len(self._chong_model))
        finally:
            self._chong_loading = old

    @staticmethod
    def _chong_line(rec):
        """列表一行文字: 显示名  ·  数据集名(两者相同时只显示一个)。"""
        dn = rec.get("dataname") or ""
        cn = rec.get("custom") or dn
        return cn if cn == dn else "%s  ·  %s" % (cn, dn)

    @staticmethod
    def _chong_tip(rec):
        """列表行的悬停提示(数据集名/技能/偏好)。"""
        return ("d_dataname = %s\n_Skill = %s\n_Preference = %s"
                % (rec.get("dataname") or "",
                   "、".join("%s:%s" % kv for kv in rec.get("skill") or []) or "(无)",
                   "、".join("%s:%s" % kv for kv in rec.get("pref") or []) or "(无)"))

    # ---- 文本改动后的偏移刷新 ----
    # 文本每次写回都会改变长度, 缓存里的绝对下标会失效。这里不用「推算位移」(易累积误差),
    # 而是改为**按身份重新定位**: 蛊虫按“第几条”重扫条目表(小, 毫秒级), 装备按“装备名+第几件”
    # 重新定位实例(名字定位 + 局部走一遍实例, 大档也是毫秒级)。
    def _chong_after_edit(self, idx):
        """单条蛊虫改动后: 重定位各条 open + 只重读“当前条”字段 + 刷新面板/列表文字。

        不整模重建(真实 7.9MB 档上整模重建约 0.1s, 这里只需十几毫秒且不会读错偏移)。
        """
        if self._text is None:
            return
        recs = chong_records(self._text)
        if len(recs) == len(self._chong_model):
            for r, (_i, dn, cn, o) in enumerate(recs):
                rec = self._chong_model[r]
                rec["open"] = o
                rec["dataname"] = dn
                rec["custom"] = cn
        else:                      # 条目数变了(理论上不该发生): 退回整模重建
            self._chong_model = chong_model(self._text)
        ent = self._chong_model[idx] if 0 <= idx < len(self._chong_model) else None
        if ent is not None:
            ent.update(chong_entry_model(self._text, ent["open"], ent.get("idx", idx),
                                        ent.get("dataname"), ent.get("custom")))
        self._chong_refresh_list_texts()
        self._on_chong_selected()      # 重填技能/偏好表格与属性面板(数据取自刚重读的当前条)

    def _chong_cur_idx(self):
        """当前选中蛊虫在模型里的下标; 未选/多选返回 None。"""
        sel = self.chong_list.selectedItems()
        if len(sel) != 1:
            return None
        r = self.chong_list.row(sel[0])
        return r if 0 <= r < len(self._chong_model) else None

    def _chong_write(self, scalars=None, dicts=None, msg=None):
        """把改动写到当前选中的蛊虫上(改完置脏 + 状态栏提示)。"""
        ent = self._chong_cur()
        idx = self._chong_cur_idx()
        if ent is None or idx is None or self._text is None:
            QMessageBox.information(self, "提示", "请先在左侧选中一条蛊虫")
            return False
        nt, changed = chong_entry_edit(self._text, ent.get("open"), scalars=scalars, dicts=dicts)
        if changed:
            self._text = nt
            self._mark_dirty()
            self._chong_after_edit(idx)
        if msg:
            self.statusBar().showMessage(msg if changed else "无变化", 3000)
        return changed

    def _on_chong_custom_changed(self):
        ent = self._chong_cur()
        if ent is None or self._text is None or self._chong_loading:
            return
        nm = self.chong_custom_edit.text().strip()
        if not nm:
            self.statusBar().showMessage("显示名不能为空", 3000)
            self._on_chong_selected()
            return
        if nm == (ent.get("custom") or ""):
            return
        self._chong_write(scalars={"_CustomName": chong_quoted(nm)},
                          msg="已把蛊虫显示名改为 %s" % nm)

    def _on_chong_love_changed(self, val):
        if self._chong_loading:
            return
        self._chong_write(scalars={"_Love": "true" if val else "false"})

    def _on_chong_foster_changed(self, val):
        if self._chong_loading:
            return
        self._chong_write(scalars={"_Foster": str(int(val))})

    def _on_chong_fostermax_changed(self, val):
        if self._chong_loading:
            return
        self._chong_write(scalars={"_FosterMax": str(int(val))})

    def _on_chong_prop_changed(self, field, val):
        if self._chong_loading:
            return
        # ★ 改 Power/Agility/PhysicalPower 时 chong_entry_edit 会自动把 _TotalProperty 写 0
        self._chong_write(scalars={field: str(int(val))},
                          msg="已把 %s 改为 %d（_TotalProperty 已写 0）"
                              % (CHONG_PROP_LABELS.get(field, field), int(val)))

    def _on_chong_props_default(self):
        if self._chong_cur() is None:
            QMessageBox.information(self, "提示", "请先在左侧选中一条蛊虫")
            return
        self._chong_loading = True
        try:
            for f in CHONG_PROP_FIELDS:
                self.chong_prop_spins[f].setValue(CHONG_PROP_DEFAULT)
        finally:
            self._chong_loading = False
        self._chong_write(scalars={f: str(CHONG_PROP_DEFAULT) for f in CHONG_PROP_FIELDS},
                          msg="已把三项属性一键设为 %d（_TotalProperty = 0）" % CHONG_PROP_DEFAULT)

    def _on_chong_fostermax_default(self):
        """把本只蛊虫的 培养上限 _FosterMax 一键设为默认 %d。"""
        if self._chong_cur() is None:
            QMessageBox.information(self, "提示", "请先在左侧选中一条蛊虫")
            return
        self._chong_loading = True
        try:
            self.chong_fostermax_spin.setValue(CHONG_FOSTER_MAX_DEFAULT)
        finally:
            self._chong_loading = False
        self._chong_write(scalars={"_FosterMax": str(CHONG_FOSTER_MAX_DEFAULT)},
                          msg="已把培养上限 _FosterMax 一键设为 %d" % CHONG_FOSTER_MAX_DEFAULT)

    def _on_chong_dict_cell_changed(self, item):
        """_Skill/_Preference 表格里手改数值。"""
        if self._chong_loading or self._building_char_page or item is None:
            return
        t = item.tableWidget()
        field = None
        for f, tb in self._chong_dict_tables.items():
            if tb is t:
                field = f
                break
        if field is None or item.column() != 1:
            return
        rows = self._chong_dict_rows.get(field) or []
        r = item.row()
        if r < 0 or r >= len(rows):
            return
        key = rows[r]
        txt = item.text().strip()
        try:
            v = int(float(txt))
        except ValueError:
            v = None
        if v is None or v < 0 or v > MAX_ITEM_COUNT:
            self._chong_loading = True
            item.setText(str(dict((self._chong_cur() or {}).get(
                "skill" if field == "_Skill" else "pref") or []).get(key, 0)))
            self._chong_loading = False
            self.statusBar().showMessage("数值必须是 0~%d 的整数" % MAX_ITEM_COUNT, 3000)
            return
        self._chong_write(dicts={field: {key: str(v)}},
                          msg="已把 %s 的「%s」改为 %d" % (field, key, v))

    def _chong_set_all(self, field, value, keys):
        """把本只蛊虫的 _Skill/_Preference 设成 keys(缺的补上); keys=None 时改现有全部键。"""
        ent = self._chong_cur()
        if ent is None or self._text is None:
            QMessageBox.information(self, "提示", "请先在左侧选中一条蛊虫")
            return
        if keys is None:
            cur = chong_dict_pairs(self._text, ent.get("open"), field)
            if not cur:
                QMessageBox.information(self, "提示", "本只蛊虫的 %s 里没有条目；"
                                        "可点「补齐全部状态」或「＋ 添加状态…」" % field)
                return
            keys = [k for k, _v in cur]
        upd = {k: str(int(value)) for k in keys}
        idx = self._chong_cur_idx()
        if idx is None:
            return
        nt, changed = chong_entry_edit(self._text, ent.get("open"), dicts={field: upd})
        if changed:
            self._text = nt
            self._mark_dirty()
            self._chong_after_edit(idx)
        self.statusBar().showMessage(
            "已把 %s 的 %d 条状态写成 %d" % (field, len(upd), int(value)) if changed else "无变化",
            4000)

    def _on_chong_add_states(self, field):
        """从技能库挑状态名加进本只蛊虫(可多选)。"""
        ent = self._chong_cur()
        if ent is None or self._text is None:
            QMessageBox.information(self, "提示", "请先在左侧选中一条蛊虫，再添加状态")
            return
        names = list(dict.fromkeys(list(CHONG_SKILLS) + list(load_skill_names())))
        cur = {k for k, _v in chong_dict_pairs(self._text, ent.get("open"), field)}
        dlg = AddItemDialog(self, existing=cur, default_count=CHONG_SKILL_DEFAULT,
                            show_count=True, cat_data=load_skill_categories(),
                            fallback_names=names, title="为蛊虫添加 %s 状态" % field,
                            count_label="数值(每条状态统一):", noun="技能")
        if not dlg.exec():
            return
        chosen = [n for n in dlg.chosen_names() if n not in cur]
        if not chosen:
            return
        v = dlg.count_spin.value()
        idx = self._chong_cur_idx()
        if idx is None:
            return
        nt, changed = chong_entry_edit(self._text, ent.get("open"),
                                       dicts={field: {k: str(v) for k in chosen}})
        if changed:
            self._text = nt
            self._mark_dirty()
            self._chong_after_edit(idx)
        self.statusBar().showMessage("已加入 %d 条状态(%s = %d)" % (len(chosen), field, v), 4000)

    def _on_chong_del_states(self, field):
        """删除本只蛊虫 %s 里选中的状态条目。"""
        ent = self._chong_cur()
        t = self._chong_dict_tables.get(field)
        if ent is None or t is None or self._text is None:
            QMessageBox.information(self, "提示", "请先在左侧选中一条蛊虫")
            return
        rows = self._chong_dict_rows.get(field) or []
        keys = sorted({i.row() for i in t.selectedItems() if 0 <= i.row() < len(rows)},
                      reverse=True)
        if not keys:
            QMessageBox.information(self, "提示", "请先在表格里选中要删除的状态行（可 Ctrl 多选）")
            return
        names = [rows[r] for r in keys]
        o = ent.get("open")
        sp = _chong_field_span(self._text, o, field)
        if sp is None:
            return
        # 重建不含这些键的字典(空字典写成 {换行+缩进})
        keep = [(k, v) for k, v in chong_dict_pairs(self._text, o, field) if k not in set(names)]
        l4 = _line_indent(self._text, sp[0])
        nl = "\r\n" if "\r\n" in self._text else "\n"
        nt = _apply_subs(self._text, [(sp[0], sp[1], _chong_dict_text(keep, l4, nl))])
        idx = self._chong_cur_idx()
        self._text = nt
        self._mark_dirty()
        self._chong_after_edit(idx if idx is not None else 0)
        self.statusBar().showMessage("已删除 %d 条状态: %s" % (len(names), "、".join(names)), 4000)

    def _chong_batch(self, field, all_skills):
        """对全部蛊虫写 _Skill/_Preference: all_skills=True 写全部技能库, None 清空, False 补齐 5 种。"""
        if not self._chong_model or self._text is None:
            QMessageBox.information(self, "提示", "请先打开/粘贴含 ChongHad 的存档")
            return
        val = self._chong_batch_spins[field].value()
        if all_skills is None:
            upd = {}          # 清空
            keys = []
        else:
            keys = list(load_skill_names()) if all_skills else list(CHONG_SKILLS)
            upd = {k: str(val) for k in keys}
        text = self._text
        # ★ 按偏移降序处理: 改动只影响该条及其后文本 —— 从后往前改时, 尚未处理的偏移恒有效
        opens = sorted((r["open"] for r in self._chong_model), reverse=True)

        def _work():
            nt = text
            for o in opens:
                if all_skills is None:
                    sp = _chong_field_span(nt, o, field)
                    if sp is None or nt[sp[0]:sp[0] + 1] != "{":
                        continue
                    l4 = _line_indent(nt, sp[0])
                    nl = "\r\n" if "\r\n" in nt else "\n"
                    nt = _apply_subs(nt, [(sp[0], sp[1], _chong_dict_text([], l4, nl))])
                else:
                    nt, _ch = chong_entry_edit(nt, o, dicts={field: upd})
            _get_struct_index(nt)     # 预热新文本索引(避免下一次操作冷建)
            return nt

        ok, r = self._run_bg(_work, "正在批量修改全部蛊虫的 %s…请稍候" % field)
        if not ok:
            self.statusBar().showMessage("批量修改失败: %s" % r, 4000)
            return
        self._text = r
        self._mark_dirty()
        self._refresh_chong_tab()
        if all_skills is None:
            msg = "已清空全部蛊虫的 %s" % field
        else:
            msg = "已把全部蛊虫的 %s 的 %d 条状态写成 %d" % (field, len(keys), val)
        self.statusBar().showMessage(msg, 4000)

    def _chong_batch_props(self, val):
        """把全部蛊虫的 力道/灵气/体魄 设为目标值(_TotalProperty 写 0)。"""
        if not self._chong_model or self._text is None:
            QMessageBox.information(self, "提示", "请先打开/粘贴含 ChongHad 的存档")
            return
        text = self._text
        opens = sorted((r["open"] for r in self._chong_model), reverse=True)
        upd = {f: str(int(val)) for f in CHONG_PROP_FIELDS}

        def _work():
            nt = text
            for o in opens:
                nt, _ch = chong_entry_edit(nt, o, scalars=upd)
            _get_struct_index(nt)
            return nt

        ok, r = self._run_bg(_work, "正在批量修改全部蛊虫的属性…请稍候")
        if not ok:
            self.statusBar().showMessage("批量修改失败: %s" % r, 4000)
            return
        self._text = r
        self._mark_dirty()
        self._refresh_chong_tab()
        self.statusBar().showMessage(
            "已把全部蛊虫的 力道/灵气/体魄 设为 %d（_TotalProperty 均写 0）" % int(val), 4000)

    def _chong_batch_fostermax(self, val):
        """把全部蛊虫的 培养上限 _FosterMax 设为目标值(默认 9999)。"""
        if not self._chong_model or self._text is None:
            QMessageBox.information(self, "提示", "请先打开/粘贴含 ChongHad 的存档")
            return
        text = self._text
        opens = sorted((r["open"] for r in self._chong_model), reverse=True)
        upd = {"_FosterMax": str(int(val))}

        def _work():
            nt = text
            for o in opens:
                nt, _ch = chong_entry_edit(nt, o, scalars=upd)
            _get_struct_index(nt)
            return nt

        ok, r = self._run_bg(_work, "正在批量修改全部蛊虫的培养上限…请稍候")
        if not ok:
            self.statusBar().showMessage("批量修改失败: %s" % r, 4000)
            return
        self._text = r
        self._mark_dirty()
        self._refresh_chong_tab()
        self.statusBar().showMessage(
            "已把全部蛊虫的培养上限 _FosterMax 设为 %d" % int(val), 4000)

    def _on_chong_add(self):
        """添加蛊虫: 从 蛊虫名.json 选(可多选), 按只数往 ChongHad 追加独立条目。"""
        if self._text is None:
            QMessageBox.information(self, "提示", "请先「打开/粘贴」存档，再添加蛊虫(写入 ChongHad 段)")
            return
        if chong_open(self._text) is None:
            QMessageBox.information(self, "提示",
                                    "当前存档里没有 ChongHad 段，无法添加蛊虫\n"
                                    "(请用含蛊虫数据的存档)")
            return
        d = self._chong_add_defaults
        dlg = AddChongDialog(self, defaults=d)
        if not dlg.exec():
            return
        names = list(dict.fromkeys(dlg.chosen_names()))
        if not names:
            return
        self._chong_add_defaults = dlg.current_defaults()
        self._autosave_settings()
        cnt = max(1, dlg.count_spin.value())
        opts = dlg.spec_options()
        specs = [dict(opts, name=n, count=cnt) for n in names]
        text = self._text

        def _work():
            nt, added = chong_add(text, specs)
            if added:
                _get_struct_index(nt)
            return nt, added

        ok, r = self._run_bg(_work, "正在添加蛊虫…请稍候")
        if not ok:
            self.statusBar().showMessage("添加蛊虫失败: %s" % r, 4000)
            return
        nt, added = r
        if added:
            self._text = nt
            self._mark_dirty()
            self._refresh_chong_tab()
        total = sum(added.values())
        self.statusBar().showMessage(
            "已添加 %d 种/%d 只蛊虫" % (len(added), total) if added else "未添加(未选中蛊虫名)", 4000)

    def _on_chong_del(self):
        """删除左列表中选中的蛊虫(多条)。"""
        sel = self.chong_list.selectedItems()
        if not sel or self._text is None:
            QMessageBox.information(self, "提示", "请先在左侧选中要删除的蛊虫（可 Ctrl/Shift 多选）")
            return
        recs = [self._chong_model[self.chong_list.row(i)] for i in sel
                if 0 <= self.chong_list.row(i) < len(self._chong_model)]
        if not recs:
            return
        names = [r.get("custom") or r.get("dataname") or "" for r in recs]
        if QMessageBox.question(self, "确认删除", "确定删除 %d 只蛊虫?\n%s"
                                % (len(recs), "、".join(names))) != QMessageBox.StandardButton.Yes:
            return
        nt, n = chong_del(self._text, [r["open"] for r in recs])
        if n:
            self._text = nt
            self._mark_dirty()
            self._refresh_chong_tab()
        self.statusBar().showMessage("已删除 %d 只蛊虫" % n, 3000)

    # ---------------- 装备(EquipHad)页: 逐件列出 + 实例技能/属性 + 添加/删除(v2.13.0 起, v2.13.2 改名/增删) ----------------
    def _build_equip_tab(self):
        """装备页: 左=主角装备逐件列表(可加/删), 右上=该装备的实例(等级/耐久), 右下=实例的技能字典。"""
        page = QWidget()
        lay = QVBoxLayout(page)
        self._equip_loading = False
        self._equip_model = []
        self._equip_rows = []
        self._equip_spans = []
        self._equip_inst_open = None
        self._equip_skill_rows = {}
        note = QLabel(
            "主角装备 / 技能(EquipHad)：左侧把主角的装备<b>逐件列出</b>(重名用「名字 #序号」区分)，"
            "选一件即可看/改它的属性。每个装备实例可改 _Lv(等级) / _Durable(耐久)，"
            "以及 \"_SkillLv\"(装备技能) 与 \"_ItemSkillLv\"(词条技能)。\n"
            "存档里这两个字段是「技能名 → [等级数组]」（如 \"提供真气\":[7]），技能名取自全局技能库"
            "（技能名.json = 内存所有道具.json 的 dataset/skill 里 被动/战斗 pass + 特殊/临时 todu 两组;\n"
            "生活技能天赋/工具/测试未整理已排除）。\n"
            "可用「＋ 添加装备…」新增装备；「－ 删除选中」删除选中的那一件（该装备名下最后一件被删时整个条目移除）。\n"
            "注意：改 _Lv 不会改名字里的前导数字；改完点「保存/另存为/复制结果」才写回存档。")
        note.setWordWrap(True)
        note.setStyleSheet("color:#888;")
        lay.addWidget(note)
        row = QHBoxLayout()
        self.btn_equip_add = QPushButton("＋ 添加装备…")
        self.btn_equip_add.setToolTip(
            "从装备类(equip)里选装备加入主角存档的 EquipHad(可搜索/多选/全选)。\n"
            "装备可同名不堆叠：「件数」填 N = 加 N 个同名实例(如填 5 = 5 把斩龙剑); 名字前导数字=等级。")
        self.btn_equip_add.clicked.connect(self._on_equip_add_items)
        self.btn_equip_del = QPushButton("－ 删除选中")
        self.btn_equip_del.setToolTip("删除左列表中选中的装备（可 Ctrl/Shift 多选；该装备名下最后一件被删时整个条目移除）")
        self.btn_equip_del.clicked.connect(self._on_equip_del_items)
        btn_refresh = QPushButton("刷新")
        btn_refresh.clicked.connect(lambda: self._refresh_equip_tab())
        self.equip_count_label = QLabel("装备: 0")
        row.addWidget(self.btn_equip_add)
        row.addWidget(self.btn_equip_del)
        row.addWidget(btn_refresh)
        row.addStretch(1)
        row.addWidget(self.equip_count_label)
        lay.addLayout(row)

        body = QHBoxLayout()
        left = QVBoxLayout()
        self.equip_search = QLineEdit()
        self.equip_search.setPlaceholderText("搜索装备名(中文 / 拼音 / 首字母)…")
        self.equip_search.setClearButtonEnabled(True)
        self.equip_search.textChanged.connect(self._filter_equip_list)
        left.addWidget(self.equip_search)
        self.equip_name_list = QListWidget()
        self.equip_name_list.setMinimumWidth(240)
        self.equip_name_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.equip_name_list.setToolTip("主角 EquipHad 里的装备（逐件列出；重名以「名字 #序号」区分）\n"
                                        "选一件即可在右侧看/改它的 等级·耐久·技能")
        self.equip_name_list.itemSelectionChanged.connect(self._on_equip_name_selected)
        left.addWidget(self.equip_name_list, 1)
        body.addLayout(left, 0)

        right = QVBoxLayout()
        right.addWidget(QLabel("实例(点一行看/改它的技能与属性)"))
        self.equip_inst_table = QTableWidget(0, 3)
        self.equip_inst_table.setHorizontalHeaderLabels(["#", "等级 _Lv", "耐久 _Durable"])
        self.equip_inst_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch)
        self.equip_inst_table.setColumnWidth(0, 46)
        self.equip_inst_table.setColumnWidth(1, 110)
        self.equip_inst_table.verticalHeader().setVisible(False)
        self.equip_inst_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.equip_inst_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.equip_inst_table.itemChanged.connect(self._on_equip_inst_changed)
        self.equip_inst_table.setMaximumHeight(180)
        right.addWidget(self.equip_inst_table)
        self.equip_field_tabs = QTabWidget()
        self.equip_field_tabs.addTab(self._equip_build_skill_page("_SkillLv", "装备技能 _SkillLv"),
                                     "装备技能 _SkillLv")
        self.equip_field_tabs.addTab(self._equip_build_skill_page("_ItemSkillLv", "词条技能 _ItemSkillLv"),
                                     "词条技能 _ItemSkillLv")
        right.addWidget(self.equip_field_tabs, 1)
        body.addLayout(right, 1)
        lay.addLayout(body, 1)
        return page

    def _equip_build_skill_page(self, field, title):
        """单个技能字典(_SkillLv / _ItemSkillLv)的编辑页: 表格(技能名|等级) + 加/删按钮。"""
        page = QWidget()
        v = QVBoxLayout(page)
        tip = QLabel("%s：存档里是「技能名 → [等级数组]」；这里改的是数组首个等级值。缺字段时会自动补写。"
                     % title)
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#888;")
        v.addWidget(tip)
        row = QHBoxLayout()
        sp = QSpinBox()
        sp.setRange(0, MAX_ITEM_COUNT)
        sp.setValue(1)
        btn_add = QPushButton("＋ 添加技能…")
        btn_add.setToolTip("从技能库(技能名.json)选一条/多条技能加入本实例（已存在的会改成目标等级）")
        btn_add.clicked.connect(lambda _=False, f=field: self._on_equip_add_skill(f))
        btn_set = QPushButton("选中行 → 目标等级")
        btn_set.setToolTip("把表格里选中的技能行的等级改成右侧目标值")
        btn_set.clicked.connect(lambda _=False, f=field: self._on_equip_set_skill(f, sp.value()))
        btn_del = QPushButton("－ 删除选中")
        btn_del.setToolTip("删除表格里选中的技能条目")
        btn_del.clicked.connect(lambda _=False, f=field: self._on_equip_del_skill(f))
        row.addWidget(QLabel("目标等级:"))
        row.addWidget(sp)
        row.addWidget(btn_add)
        row.addWidget(btn_set)
        row.addWidget(btn_del)
        row.addStretch(1)
        v.addLayout(row)
        t = QTableWidget(0, 2)
        t.setHorizontalHeaderLabels(["技能名", "等级"])
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        t.setColumnWidth(1, 120)
        t.verticalHeader().setVisible(False)
        t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        t.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        t.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                          | QAbstractItemView.EditTrigger.EditKeyPressed
                          | QAbstractItemView.EditTrigger.SelectedClicked)
        t.itemChanged.connect(self._on_equip_skill_cell_changed)
        v.addWidget(t, 1)
        self._equip_skill_tables = getattr(self, "_equip_skill_tables", {})
        self._equip_skill_tables[field] = t
        self._equip_skill_rows[field] = []
        self._equip_target_spins = getattr(self, "_equip_target_spins", {})
        self._equip_target_spins[field] = sp
        return page

    # ---- 装备页: 读写 ----
    def _refresh_equip_tab(self, model=None):
        """按当前 self._text 重建装备列表(每个装备实例直接列一行, 不再显示「(N 件)」括号)。

        模型只留「装备名 + 件数」; 实例的绝对下标每次用时按名字重定位(_equip_current_instance),
        因此文本被改动(含被蛊虫页改动)后也不会读到错位的字段。
        model=None 且当前是大档 → 模型计算(实测 8.6MB 档要 ~1.3s)走后台线程, 不卡 UI。
        """
        if getattr(self, "equip_name_list", None) is None:
            return
        full = model
        if full is None and self._text:
            if len(self._text) >= self._ASYNC_OPEN_MIN:
                t = self._text
                ok, rr = self._run_bg(lambda: equip_skill_model(t), "正在读取装备数据…请稍候")
                full = rr if ok else equip_skill_model(t)
            else:
                full = equip_skill_model(self._text)
        self._equip_model = [(nm, len(spans) if isinstance(spans, list) else int(spans))
                             for nm, spans in (full or [])]
        # 左侧: 逐件展开(名字 + 序号), 方便直接点任意一件看/改它的属性
        self._equip_rows = [(nm, k, cnt > 1) for nm, cnt in self._equip_model
                            for k in range(cnt)]
        keep_row = self.equip_name_list.currentRow()
        self._equip_loading = True
        try:
            self.equip_name_list.clear()
            if self._equip_rows:
                # 逐件行数可能上千(实测 1687 件), 批量建项比逐个快一个数量级
                self.equip_name_list.addItems([
                    "%s #%d" % (nm, k + 1) if dup else nm
                    for nm, k, dup in self._equip_rows])
            self.equip_count_label.setText("装备: %d 件 · %d 种"
                                          % (len(self._equip_rows), len(self._equip_model)))
            if self._equip_rows and keep_row >= 0:
                self.equip_name_list.setCurrentRow(min(keep_row, len(self._equip_rows) - 1))
        finally:
            self._equip_loading = False
        self._filter_equip_list()
        self._on_equip_name_selected()

    def _filter_equip_list(self):
        """按搜索框过滤装备列表(只隐藏, 不影响数据); 同名的多件一起显/隐。"""
        if getattr(self, "equip_name_list", None) is None:
            return
        q = (self.equip_search.text() or "").strip()
        pmap = load_pinyin_map() if q else None
        names = [nm for nm, _c in self._equip_model]
        keep = set(filter_item_names(names, q, pmap)) if q else None
        for r in range(self.equip_name_list.count()):
            it = self.equip_name_list.item(r)
            nm = self._equip_rows[r][0] if r < len(self._equip_rows) else it.text()
            it.setHidden(bool(keep is not None and nm not in keep))

    def _equip_cur(self):
        """当前选中的 (装备名, 实例下标, 是否重名); 未选返回 None。"""
        if getattr(self, "equip_name_list", None) is None:
            return None
        r = self.equip_name_list.currentRow()
        if 0 <= r < len(self._equip_rows):
            return self._equip_rows[r]
        return None

    def _equip_cur_name(self):
        """当前选中的装备名; 未选返回 None。"""
        cur = self._equip_cur()
        return cur[0] if cur else None

    def _on_equip_name_selected(self):
        """装备列表选中变化: 按名字重新定位实例区间, 重填实例表并选中对应的那一件。"""
        if getattr(self, "_equip_loading", False):
            return
        cur = self._equip_cur()
        nm = cur[0] if cur else None
        self._equip_spans = equip_name_spans(self._text or "", nm) if nm else []
        spans = self._equip_spans
        self._equip_loading = True
        try:
            t = self.equip_inst_table
            t.setRowCount(0)
            for i, (o, _c) in enumerate(spans):
                r = t.rowCount()
                t.insertRow(r)
                it0 = QTableWidgetItem(str(i + 1))
                it0.setFlags(it0.flags() & ~Qt.ItemFlag.ItemIsEditable)
                t.setItem(r, 0, it0)
                for col, f in ((1, "_Lv"), (2, "_Durable")):
                    raw = chong_field(self._text or "", o, f)
                    it1 = QTableWidgetItem("" if raw is None else str(raw))
                    if raw is None:
                        it1.setFlags(it1.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    t.setItem(r, col, it1)
            if spans:
                # 选中的那一件(左侧逐件列表点的是第几件, 就在实例表里选第几行)
                t.selectRow(cur[1] if cur and cur[1] < len(spans) else 0)
        finally:
            self._equip_loading = False
        # 当前实例 = 左侧选中的那一件(v2.13.2 修正: 原来固定取首件, 点重名的第 2 件会看/改到第 1 件)
        if spans:
            idx = cur[1] if cur and cur[1] < len(spans) else 0
            self._equip_inst_open = spans[idx][0]
        else:
            self._equip_inst_open = None
        self._fill_equip_skills()

    def _equip_inst_row(self):
        """当前选中实例在 _equip_spans 里的下标; 未选返回 None。"""
        r = self.equip_inst_table.currentRow()
        if r < 0 or r >= len(self._equip_spans):
            return None
        return r

    def _equip_current_instance(self):
        """按「装备名 + 第几个实例」重新定位实例开括号(文本改动后坐标会变, 每次用时重定位最稳)。

        定位失败(名字对不上等)才回退到已缓存的 _equip_inst_open。
        """
        nm = self._equip_cur_name()
        r = self._equip_inst_row()
        if nm is not None and r is not None and self._text is not None:
            o = equip_instance_open(self._text, nm, r)
            if o is not None:
                return o
        return self._equip_inst_open

    # ---- 装备页: 新增/删除装备(v2.13.2) ----
    def _on_equip_add_items(self):
        """往主角 EquipHad 添加装备(equip 类; 可同名多件不堆叠, 「件数」= 加几个同名实例)。"""
        if self._text is None:
            QMessageBox.information(self, "提示",
                                    "请先「打开/粘贴」存档, 再添加装备(写入 EquipHad 段)")
            return
        if player_equip_open(self._text) is None:
            QMessageBox.information(self, "提示",
                                    "当前存档里没有 EquipHad 段, 无法添加装备\n(请用含主角装备数据的存档)")
            return
        dlg = AddItemDialog(self, existing=set(), default_count=1, allow_codes=EQUIP_ADD_CATS)
        dlg.setWindowTitle("添加装备(EquipHad)")
        if not dlg.exec():
            return
        names = list(dict.fromkeys(dlg.chosen_names()))
        if not names:
            return
        cnt = max(1, dlg.count_spin.value())
        text = self._text

        def _work():
            nt, added = player_add_equips(text, [(n, cnt) for n in names])
            if added:
                _get_struct_index(nt)   # 后台线程预热新文本结构索引
            return nt, added

        ok, r = self._run_bg(_work, "正在添加装备…请稍候")
        if not ok:
            self.statusBar().showMessage("添加装备失败: %s" % r, 4000)
            return
        nt, added = r
        if added:
            self._text = nt
            self._mark_dirty()
            self._refresh_equip_tab()
        self.statusBar().showMessage(
            "已添加 %d 种/%d 件装备(写入 EquipHad, 同名=多件实例)"
            % (len(added), sum(added.values())) if added else "未添加(未选中装备名)", 4000)

    def _on_equip_del_items(self):
        """删除左列表中选中的装备(选中的是某一具体实例; 该名字下最后一件被删时整个条目移除)。"""
        if self._text is None:
            QMessageBox.information(self, "提示", "请先「打开/粘贴」存档, 再删除装备")
            return
        rows = sorted({self.equip_name_list.row(i)
                       for i in self.equip_name_list.selectedItems()})
        rows = [r for r in rows if 0 <= r < len(self._equip_rows)]
        if not rows:
            QMessageBox.information(self, "提示",
                                    "请先在左侧选中要删除的装备（可 Ctrl/Shift 多选）")
            return
        targets = [(self._equip_rows[r][0], self._equip_rows[r][1]) for r in rows]
        shown = "、".join("%s #%d" % (self._equip_rows[r][0], self._equip_rows[r][1] + 1)
                          for r in rows[:10])
        if len(rows) > 10:
            shown += " 等 %d 件" % len(rows)
        if QMessageBox.question(self, "确认删除",
                                "确定删除主角的 %d 件装备?\n%s\n\n"
                                "(某件装备名下最后一件被删时, 该装备条目会一并移除)"
                                % (len(rows), shown)) != QMessageBox.StandardButton.Yes:
            return
        text = self._text

        def _work():
            nt, gone = player_del_equips(text, targets)
            if gone:
                _get_struct_index(nt)
            return nt, gone

        ok, r = self._run_bg(_work, "正在删除装备…请稍候")
        if not ok:
            self.statusBar().showMessage("删除装备失败: %s" % r, 4000)
            return
        nt, gone = r
        if gone:
            self._text = nt
            self._mark_dirty()
            self._refresh_equip_tab()
        self.statusBar().showMessage(
            "已删除 %d 件装备: %s" % (len(gone), "、".join(gone[:10])) if gone else "未删除",
            4000)

    def _equip_after_edit(self):
        """装备实例改动后: 按名字重新定位当前装备的实例区间并重填实例表/技能表。

        不用「推算位移」(多次改动会累积误差), 而是按身份重定位 —— 名字定位 + 局部数实例,
        真实档上也只是毫秒级。
        """
        if self._text is None:
            return
        r = self._equip_inst_row()
        nm = self._equip_cur_name()
        self._equip_spans = equip_name_spans(self._text, nm) if nm else []
        if r is not None and r < len(self._equip_spans):
            self._equip_inst_open = self._equip_spans[r][0]
        elif self._equip_spans:
            self._equip_inst_open = self._equip_spans[0][0]
        else:
            self._equip_inst_open = None
        self._fill_equip_skills()
        # 实例表里的 等级/耐久 单元格按最新文本刷新(名称/件数不变, 不整表重建)
        old = self._equip_loading
        self._equip_loading = True
        try:
            t = self.equip_inst_table
            for i, (o, _c) in enumerate(self._equip_spans):
                if i >= t.rowCount():
                    break
                for col, f in ((1, "_Lv"), (2, "_Durable")):
                    raw = chong_field(self._text, o, f)
                    it = t.item(i, col)
                    if it is not None:
                        it.setText("" if raw is None else str(raw))
        finally:
            self._equip_loading = old

    def _fill_equip_skills(self):
        """按当前实例填充 _SkillLv / _ItemSkillLv 表格。"""
        o = self._equip_inst_open
        old = self._equip_loading
        self._equip_loading = True
        try:
            for field, t in (getattr(self, "_equip_skill_tables", {}) or {}).items():
                pairs = equip_skill_pairs(self._text or "", o, field) if o is not None else []
                t.setRowCount(0)
                for k, vals in pairs:
                    r = t.rowCount()
                    t.insertRow(r)
                    it0 = QTableWidgetItem(str(k))
                    it0.setFlags(it0.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    t.setItem(r, 0, it0)
                    t.setItem(r, 1, QTableWidgetItem(str(vals[0]) if vals else ""))
                t.setEnabled(o is not None)
                self._equip_skill_rows[field] = [k for k, _v in pairs]
        finally:
            self._equip_loading = old

    def _on_equip_inst_changed(self, item):
        """实例表里手改 _Lv / _Durable。"""
        if self._equip_loading or item is None or item.column() == 0:
            return
        r = item.row()
        if r < 0 or r >= len(self._equip_spans):
            return
        field = "_Lv" if item.column() == 1 else "_Durable"
        txt = item.text().strip()
        try:
            v = int(float(txt))
        except ValueError:
            v = None
        o = self._equip_current_instance()
        if v is None or v < 0 or v > MAX_ITEM_COUNT or o is None:
            self._equip_loading = True
            item.setText(str(chong_field(self._text or "", o, field) or "")
                         if o is not None else "")
            self._equip_loading = False
            self.statusBar().showMessage("必须是 0~%d 的整数" % MAX_ITEM_COUNT, 3000)
            return
        nt, changed = equip_set_scalar(self._text, o, field, v)
        if changed:
            self._text = nt
            self._mark_dirty()
            self._equip_after_edit()
            self.statusBar().showMessage("已把实例 #%d 的 %s 改为 %d"
                                         % (r + 1, EQUIP_FIELD_LABELS.get(field, field), v), 3000)

    def _on_equip_skill_cell_changed(self, item):
        """技能表里手改等级。"""
        if self._equip_loading or item is None or item.column() != 1:
            return
        t = item.tableWidget()
        field = None
        for f, tb in (getattr(self, "_equip_skill_tables", {}) or {}).items():
            if tb is t:
                field = f
                break
        if field is None or self._equip_inst_open is None:
            return
        rows = self._equip_skill_rows.get(field) or []
        r = item.row()
        if r < 0 or r >= len(rows):
            return
        try:
            v = int(float(item.text().strip()))
        except ValueError:
            v = None
        if v is None or v < 0 or v > MAX_ITEM_COUNT:
            self._equip_loading = True
            item.setText("")
            self._equip_loading = False
            self.statusBar().showMessage("等级必须是 0~%d 的整数" % MAX_ITEM_COUNT, 3000)
            return
        o = self._equip_current_instance()
        if o is None:
            return
        nt, changed = equip_set_skill(self._text, o, field, {rows[r]: [v]})
        if changed:
            self._text = nt
            self._mark_dirty()
            self._equip_after_edit()
            self.statusBar().showMessage("已把 %s 改为 %d" % (rows[r], v), 3000)

    def _equip_selected_skill_names(self, field):
        """技能表里当前选中的技能名列表。"""
        t = (getattr(self, "_equip_skill_tables", {}) or {}).get(field)
        rows = self._equip_skill_rows.get(field) or []
        if t is None:
            return []
        return [rows[i.row()] for i in t.selectedItems()
                if i.column() == 0 and 0 <= i.row() < len(rows)]

    def _on_equip_add_skill(self, field):
        """从技能库选技能加入当前实例。"""
        if self._equip_inst_open is None or self._text is None:
            QMessageBox.information(self, "提示", "请先在左侧选中装备、再选中一个实例")
            return
        cur = {k for k, _v in equip_skill_pairs(self._text, self._equip_inst_open, field)}
        v0 = self._equip_target_spins[field].value()
        dlg = AddItemDialog(self, existing=cur, default_count=v0, show_count=True,
                            cat_data=load_skill_categories(), fallback_names=load_skill_names(),
                            title="添加%s" % EQUIP_FIELD_LABELS.get(field, field),
                            count_label="等级(每条技能统一):", noun="技能")
        if not dlg.exec():
            return
        names = dlg.chosen_names()
        if not names:
            return
        v = dlg.count_spin.value()
        o = self._equip_current_instance()
        if o is None:
            return
        nt, changed = equip_set_skill(self._text, o, field, {n: [v] for n in names})
        if changed:
            self._text = nt
            self._mark_dirty()
            self._equip_after_edit()
        self.statusBar().showMessage("已写入 %d 条技能(%s = %d)" % (len(names), field, v), 4000)

    def _on_equip_set_skill(self, field, value):
        """把选中技能行的等级改成目标值。"""
        names = self._equip_selected_skill_names(field)
        if not names or self._equip_inst_open is None:
            QMessageBox.information(self, "提示", "请先在下方表格里选中技能行（可 Ctrl 多选）")
            return
        o = self._equip_current_instance()
        if o is None:
            return
        nt, changed = equip_set_skill(self._text, o, field, {n: [int(value)] for n in names})
        if changed:
            self._text = nt
            self._mark_dirty()
            self._equip_after_edit()
        self.statusBar().showMessage("已把 %d 条技能等级改为 %d" % (len(names), int(value)), 4000)

    def _on_equip_del_skill(self, field):
        """删除选中技能条目。"""
        names = self._equip_selected_skill_names(field)
        if not names or self._equip_inst_open is None:
            QMessageBox.information(self, "提示", "请先在下方表格里选中要删除的技能行")
            return
        o = self._equip_current_instance()
        if o is None:
            return
        nt, gone = equip_del_skill(self._text, o, field, names)
        if gone:
            self._text = nt
            self._mark_dirty()
            self._equip_after_edit()
        self.statusBar().showMessage("已删除 %d 条技能: %s" % (len(gone), "、".join(gone)), 4000)

    def _refresh_shop_tab(self, cache=None):
        """按 self._text 重建商店缓存、分类下拉与 NPC 列表(读档后/初始化时调用)。

        cache: 可选 shop_records_full 的结果(打开大档已在后台线程算好, 传 4 元组列表避免主线程全档扫);
        为 None 时: 大档改走后台线程算(窗口不卡), 小档/无 _ShopData 直接算。之后商店读取一律
        fast 实时定位, 不依赖缓存偏移。
        """
        text = self._text or ""
        recs = cache
        if recs is None and self._text is not None and len(text) >= self._ASYNC_OPEN_MIN \
                and "_ShopData" in text:
            t = text
            ok, rr = self._run_bg(lambda: shop_records_full(t), "正在读取商店数据…请稍候")
            recs = rr if ok else shop_records_full(t)      # 忙(已有后台任务) → 同步回退
        if recs is None:
            recs = shop_records_full(text) if (self._text is not None and "_ShopData" in text) else []
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
        if self._text is not None and recs:
            # 批量建项(C++ 侧 addItems) 后再逐项 setData: 269 家店逐个 QListWidgetItem 建+设数据
            # 实测 ~1s, 批量后 ~0.1s; setData 不触发视图重绘, 不必泵事件
            names = []
            metas = []
            for k, ab, so, sop in recs:
                self._shop_cache[k] = (ab, so, sop)
                code = self._shop_city_map.get(ab) or self._shop_city_map.get(k) or ""
                if not code:
                    self._shop_has_unmapped = True
                names.append(ab)
                metas.append((k, code))
            self.shop_list.addItems(names)
            for i, (k, code) in enumerate(metas):
                it = self.shop_list.item(i)
                it.setData(Qt.ItemDataRole.UserRole, k)          # 商店键
                it.setData(Qt.ItemDataRole.UserRole + 1, code)   # 分类代码(可空)
        if self._shop_cache:
            if self._shop_has_unmapped:
                self.shop_city_combo.addItem("(未分类)")
                self.shop_city_combo.setItemData(self.shop_city_combo.count() - 1,
                                                 "__none__", Qt.ItemDataRole.UserRole)
            self.shop_search.setEnabled(True)
            self.shop_city_combo.setEnabled(True)
            self.btn_add_sell.setEnabled(True)
            self.btn_add_equip.setEnabled(True)
            self.btn_npc_sel.setEnabled(True)
            self.btn_npc_all.setEnabled(True)
            self.discount_all_spin.setEnabled(True)
            self.refresh_all_spin.setEnabled(True)
            # 卖品/装备 批量操作按钮也要在有店后重新启用(无店分支会禁用, 之前漏了重新启用→灰点不了)
            self.shop_batch_spin.setEnabled(True)
            self.btn_shop_item_del.setEnabled(True)
            self.btn_shop_item_set.setEnabled(True)
            self.btn_equip_del.setEnabled(True)
            self.btn_equip_set.setEnabled(True)
            self.shop_list.setCurrentRow(0)
        else:
            self.shop_search.setEnabled(False)
            self.shop_city_combo.setEnabled(False)
            self.btn_add_sell.setEnabled(False)
            self.btn_add_equip.setEnabled(False)
            self.btn_npc_sel.setEnabled(False)
            self.btn_npc_all.setEnabled(False)
            self.discount_all_spin.setEnabled(False)
            self.refresh_all_spin.setEnabled(False)
            self.shop_batch_spin.setEnabled(False)
            self.btn_shop_item_del.setEnabled(False)
            self.btn_shop_item_set.setEnabled(False)
            self.btn_equip_del.setEnabled(False)
            self.btn_equip_set.setEnabled(False)
            self.equip_table.setRowCount(0)
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
            self.equip_table.setRowCount(0)
            self.shop_title.setText("未选 NPC")
            self._apply_shop_params(None)
            return
        self._show_shop_items()

    def _show_shop_items(self):
        """右侧显示当前 NPC 的 卖品/装备 与 折扣/刷新日(一次 fast 定位, 店内小段扫描)。"""
        key = self._shop_key
        self.shop_items.setRowCount(0)
        self.equip_table.setRowCount(0)
        if key is None or self._text is None:
            self._apply_shop_params(None)
            return
        view = shop_view(self._text, key)
        self._apply_shop_params(view)
        if view is None:
            return
        items = view["sell"]
        eqs = view["equips"]
        eqkinds = len(eqs)
        eqpieces = sum(c for _n, c in eqs)
        self.shop_title.setText("NPC: %s · 卖品 %d 件 · 装备 %d 种/%d 件" % (view["ab"], len(items), eqkinds, eqpieces))
        self.shop_items.setRowCount(len(items))
        for r, (nm, cnt) in enumerate(items):
            i0 = QTableWidgetItem(nm)
            i0.setFlags(i0.flags() & ~Qt.ItemFlag.ItemIsEditable)
            i1 = QTableWidgetItem(str(cnt))
            i1.setFlags(i1.flags() & ~Qt.ItemFlag.ItemIsEditable)
            i1.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.shop_items.setItem(r, 0, i0)
            self.shop_items.setItem(r, 1, i1)
        self.equip_table.setRowCount(len(eqs))
        for r, (nm, cnt) in enumerate(eqs):
            i0 = QTableWidgetItem(nm)
            i0.setFlags(i0.flags() & ~Qt.ItemFlag.ItemIsEditable)
            i1 = QTableWidgetItem(str(cnt))
            i1.setFlags(i1.flags() & ~Qt.ItemFlag.ItemIsEditable)
            i1.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.equip_table.setItem(r, 0, i0)
            self.equip_table.setItem(r, 1, i1)

    # ---------------- 卖品/装备 多选批量操作 ---------------- 
    def _selected_shop_names(self, table):
        """收集 table(卖品/装备表)选中行的第 0 列名称(去重, 保持行序); 未选返回 []。"""
        out = []
        for it in table.selectedItems():
            if it.column() == 0:
                nm = it.text()
                if nm not in out:
                    out.append(nm)
        return out

    def _on_shop_batch_value_changed(self, val):
        """商店批量目标值(卖品数量/装备件数)变化 → 记住并自动保存。"""
        self._shop_batch_value = val
        self._autosave_settings()

    def _on_shop_item_del(self):
        """删除当前 NPC 卖品表中选中的道具(整件下架)。"""
        key = self._shop_key
        if key is None or self._text is None:
            return
        names = self._selected_shop_names(self.shop_items)
        if not names:
            QMessageBox.information(self, "提示", "请先在右侧卖品表选中要删除的道具(可 Ctrl/拖动多选)")
            return
        cache = self._shop_cache.get(key)
        ab = cache[0] if cache else key
        if QMessageBox.question(self, "确认删除卖品",
                                "确定把 %s 的这些卖品整件下架?\n%s" % (ab, "、".join(names))
                                ) != QMessageBox.StandardButton.Yes:
            return
        text = self._text

        def _work():
            nt, gone = shop_del_items(text, key, names)
            if gone:
                _get_struct_index(nt)
            return nt, gone

        ok, r = self._run_bg(_work, "正在删除卖品…请稍候")
        if not ok:
            self.statusBar().showMessage("删除失败: %s" % r, 4000)
            return
        nt, gone = r
        if gone:
            self._text = nt
            self._mark_dirty()
        self._show_shop_items()
        self.statusBar().showMessage("已删除 %s 的 %d 个卖品" % (ab, len(gone)), 3000)

    def _on_shop_item_set(self):
        """把当前 NPC 卖品表中选中道具的数量改成 shop_batch_spin 的目标值。"""
        key = self._shop_key
        if key is None or self._text is None:
            return
        names = self._selected_shop_names(self.shop_items)
        if not names:
            QMessageBox.information(self, "提示", "请先在右侧卖品表选中要改数量的道具(可 Ctrl/拖动多选)")
            return
        v = self.shop_batch_spin.value()
        cache = self._shop_cache.get(key)
        ab = cache[0] if cache else key
        text = self._text

        def _work():
            nt, changed = shop_set_item_counts(text, key, {n: v for n in names})
            if changed:
                _get_struct_index(nt)
            return nt, changed

        ok, r = self._run_bg(_work, "正在改卖品数量…请稍候")
        if not ok:
            self.statusBar().showMessage("改数量失败: %s" % r, 4000)
            return
        nt, changed = r
        if changed:
            self._text = nt
            self._mark_dirty()
        self._show_shop_items()
        self.statusBar().showMessage("已将 %s 的 %d 个卖品数量改为 %d" % (ab, len(changed), v), 3000)

    def _on_shop_equip_del(self):
        """删除当前 NPC 已上架装备中选中的整种装备(同名多件一起下架)。"""
        key = self._shop_key
        if key is None or self._text is None:
            return
        names = self._selected_shop_names(self.equip_table)
        if not names:
            QMessageBox.information(self, "提示", "请先选中要删除的装备(可 Ctrl/拖动多选)")
            return
        cache = self._shop_cache.get(key)
        ab = cache[0] if cache else key
        if QMessageBox.question(self, "确认删除装备",
                                "确定把 %s 上架的这些装备整种下架(同名所有件)?\n%s" % (ab, "、".join(names))
                                ) != QMessageBox.StandardButton.Yes:
            return
        text = self._text

        def _work():
            nt, gone = shop_del_equips(text, key, names)
            if gone:
                _get_struct_index(nt)
            return nt, gone

        ok, r = self._run_bg(_work, "正在删除装备…请稍候")
        if not ok:
            self.statusBar().showMessage("删除装备失败: %s" % r, 4000)
            return
        nt, gone = r
        if gone:
            self._text = nt
            self._mark_dirty()
        self._show_shop_items()
        self.statusBar().showMessage("已删除 %s 的 %d 种装备" % (ab, len(gone)), 3000)

    def _on_shop_equip_set(self):
        """把当前 NPC 已上架装备中选中的装备件数改成 shop_batch_spin 目标值(0=删除整种)。"""
        key = self._shop_key
        if key is None or self._text is None:
            return
        names = self._selected_shop_names(self.equip_table)
        if not names:
            QMessageBox.information(self, "提示", "请先选中要改件数的装备(可 Ctrl/拖动多选)")
            return
        v = self.shop_batch_spin.value()
        cache = self._shop_cache.get(key)
        ab = cache[0] if cache else key
        text = self._text

        def _work():
            nt, changed = shop_set_equip_counts(text, key, {n: v for n in names})
            if changed:
                _get_struct_index(nt)
            return nt, changed

        ok, r = self._run_bg(_work, "正在改装备件数…请稍候")
        if not ok:
            self.statusBar().showMessage("改件数失败: %s" % r, 4000)
            return
        nt, changed = r
        if changed:
            self._text = nt
            self._mark_dirty()
        self._show_shop_items()
        if v == 0:
            self.statusBar().showMessage("已删除 %s 的 %d 种装备(件数 0)" % (ab, len(changed)), 3000)
        else:
            self.statusBar().showMessage("已把 %s 的 %d 种装备件数改为 %d" % (ab, len(changed), v), 3000)

    def _selected_shop_keys(self):
        """批量应用时用的商店键列表: 左列表多选选中项; 无多选时回退当前项。"""
        out = []
        for it in self.shop_list.selectedItems():
            k = it.data(Qt.ItemDataRole.UserRole)
            if k and k not in out:
                out.append(k)
        if not out:
            k = self._current_shop_key()
            if k:
                out.append(k)
        return out

    def _on_shop_discount_all_changed(self, v):
        self._discount_all = round(float(v), 2)
        self._autosave_settings()

    def _on_shop_refresh_all_changed(self, v):
        self._refresh_all = int(round(v))
        self._autosave_settings()

    def _on_shop_npc_apply(self, to_all):
        """把批量 折扣/刷新日 应用到 全部(True) 或 选中/当前(False) NPC。"""
        if self._text is None or not self._shop_cache:
            return
        keys = list(self._shop_cache.keys()) if to_all else self._selected_shop_keys()
        if not keys:
            QMessageBox.information(self, "提示", "请先在左侧选中要应用的 NPC(可 Ctrl 多选)")
            return
        discount_txt = self._fmt_num_text(self.discount_all_spin.value())
        refresh_txt = str(int(round(self.refresh_all_spin.value())))
        text = self._text

        def _work():
            nt, n = shop_set_npc_params(text, keys, discount_txt, refresh_txt)
            if n:
                _get_struct_index(nt)
            return nt, n

        where = "全部 %d 个 NPC" % len(keys) if to_all else "选中 %d 个 NPC" % len(keys)
        ok, r = self._run_bg(_work, "正在批量设置 折扣/刷新日…请稍候")
        if not ok:
            self.statusBar().showMessage("批量设置失败: %s" % r, 4000)
            return
        nt, n = r
        if n:
            # 防御(v2.8.4): 结果异常(商店段丢失/括号失衡)绝不采纳——存档保持原样并提示
            bal = nt.count("{") == nt.count("}")
            if '"_ShopData"' not in nt or not bal:
                QMessageBox.critical(
                    self, "警告",
                    "批量设置结果异常(检测到商店数据可能不完整), 已放弃本次修改, 存档保持原样。\n"
                    "请点「重新读取」以磁盘文件为准刷新后重试; 若反复出现请反馈。")
                self.statusBar().showMessage("批量设置已放弃(结果异常), 存档未改动", 5000)
                return
            self._text = nt
            self._mark_dirty()
        self._show_shop_items()
        self.statusBar().showMessage("已把 %s 的折扣设为 %s、刷新日设为 %s(成功 %d)" %
                                     (where, discount_txt, refresh_txt, n), 4000)

    # ---------------- NPC 参数: Discount(折扣)/RefreshDay(刷新日) ----------------
    def _apply_shop_params(self, view):
        """按 shop_view 结果载入 折扣/刷新日 数字框; view 为 None 或字段缺失时该行禁用。"""
        raw = view if isinstance(view, dict) else {}
        self._shop_loading = True
        try:
            for spin, btn, val, dflt in (
                    (self.discount_spin, self.btn_discount_dflt, raw.get("discount"), 1.0),
                    (self.refresh_spin, self.btn_refresh_dflt, raw.get("refreshday"), 1.0)):
                if val is None:
                    spin.setValue(float(dflt))
                    spin.setEnabled(False)
                    btn.setEnabled(False)
                else:
                    spin.setEnabled(True)
                    btn.setEnabled(True)
                    try:
                        spin.setValue(float(val))
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

    def _preheat_index(self):
        """后台线程预热 self._text 的结构索引(模块缓存), 让主线程随后的 fast 读不触发整档建索引。"""
        txt = self._text
        if txt is None:
            return
        if _SCAN_CACHE[0] is txt and _SCAN_CACHE[1] is not None:
            return
        threading.Thread(target=_get_struct_index, args=(txt,), daemon=True).start()

    def _resync_shop_cache(self):
        """(兼容保留) 商店读取已改为每次 fast 实时定位, 无绝对偏移缓存需失效; 仅预热索引即可。"""
        self._preheat_index()

    def _write_shop_field(self, field, new_text):
        """把当前商店对象的字段写入 self._text(改动即脏); 商店无该字段时只提示不改写。
        实时 fast 定位店内替换(改动极小), 无需全档 resync。"""
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
            self._preheat_index()
            cache = self._shop_cache.get(key)
            ab = cache[0] if cache else key
            self.statusBar().showMessage("已把 %s 的 %s 改为 %s" % (ab, zh, new_text), 3000)

    def _on_shop_add(self):
        """给当前 NPC 的 SellItems 添加卖品(AddItemDialog 搜索/多选, 默认数量 999, 防重)。"""
        key = self._shop_key
        if key is None or self._text is None:
            return
        cache = self._shop_cache.get(key)
        ab = cache[0] if cache else key
        existing = {n for n, _ in shop_sellitems(self._text, key)}
        dlg = AddItemDialog(self, existing=existing, default_count=999,
                            allow_codes=ITEM_ADD_CATS)   # 卖品也是道具形态: 排除 equip(装备类走 SellEquips)
        dlg.setWindowTitle("为 %s 添加卖品" % ab)
        if not dlg.exec():
            return
        names = list(dict.fromkeys(dlg.chosen_names()))
        names, blocked = split_names_by_cats(names, ITEM_ADD_CATS)
        cnt = dlg.count_spin.value()
        if not names:
            if blocked:
                self.statusBar().showMessage(
                    "%d 个装备类已剔除: 商店装备请用「＋ 添加装备…(SellEquips)」" % len(blocked), 4000)
            return
        text = self._text

        def _work():
            nt, added = shop_add_items(text, key, [(n, cnt) for n in names])
            if added:
                _get_struct_index(nt)   # 后台线程预热新文本结构索引
            return nt, added

        ok, r = self._run_bg(_work, "正在添加卖品…请稍候")   # 写回/建索引放后台, 大档不卡 UI
        if not ok:
            self.statusBar().showMessage("添加失败: %s" % r, 4000)
            return
        nt, added = r
        if added:
            self._text = nt
            self._mark_dirty()
        self._show_shop_items()
        dup = len(names) - len(added)
        msg = "已为 %s 添加 %d 个卖品(数量 %d)" % (ab, len(added), cnt)
        if dup:
            msg += " · %d 个已存在自动跳过" % dup
        self.statusBar().showMessage(msg, 4000)

    def _on_shop_add_equip(self):
        """给当前 NPC 的 SellEquips 添加装备类道具(equip, 名内含前导数字=等级)。

        该 NPC 若没有 SellEquips 字段, 先自动补一个空字段(与 猪姨 等卖装备 NPC 一致), 再添加。
        """
        key = self._shop_key
        if key is None or self._text is None:
            return
        cache = self._shop_cache.get(key)
        ab = cache[0] if cache else key
        # 注意: 同名可再追加副本(数组多实例), 故不把已有名灰显
        dlg = AddItemDialog(self, existing=set(), default_count=1,
                            allow_codes=EQUIP_ADD_CATS)   # 商店装备栏只列 equip 类
        dlg.setWindowTitle("为 %s 添加装备(SellEquips)" % ab)
        if not dlg.exec():
            return
        names = list(dict.fromkeys(dlg.chosen_names()))
        cnt = max(1, dlg.count_spin.value())
        if not names:
            return
        text = self._text
        had_field = _shop_sellequips_open(text, key) is not None

        def _work():
            nt = text
            nt, ensured = shop_ensure_sellequips(nt, key)   # 没有 SellEquips 字段→自动补空字段
            nt, added = shop_add_equips(nt, key, [(n, cnt) for n in names])
            if added or ensured:
                _get_struct_index(nt)   # 后台线程预热新文本结构索引
            return nt, added, ensured

        ok, r = self._run_bg(_work, "正在添加装备…请稍候")   # 写回/建索引放后台, 大档不卡 UI
        if not ok:
            self.statusBar().showMessage("添加装备失败: %s" % r, 4000)
            return
        nt, added, ensured = r
        if added or ensured:
            self._text = nt
            self._mark_dirty()
        self._show_shop_items()
        pieces = sum(added.values())
        kinds = len(added)
        auto = "该 NPC 原本没有 SellEquips, 已自动补装备栏字段; " if ensured else ""
        if kinds:
            self.statusBar().showMessage(
                "%s已为 %s 添加装备 %d 件(%d 种, 每种 %d 件; 同名=追加副本)" % (auto, ab, pieces, kinds, cnt), 4000)
        else:
            self.statusBar().showMessage("未添加任何装备%s" % ("(已补 SellEquips 字段)" if ensured else ""), 2000)

    def _refresh_char_tabs(self):
        """按当前 self._text 重建「道具」页之后的主角/队友页签。"""
        cur = self.tabs.currentIndex()
        text = self._text or ""
        model = char_model(text) if text else {"player": None, "friends": [], "maps": []}
        if model["player"] is None and not model["friends"]:
            # 保留 道具(0)+商店NPC(1)+蛊虫(2)+装备(3), 移除之后的旧角色页
            while self.tabs.count() > self.CHAR_TAB_BASE:
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

    def _apply_char_model(self, model, progress=False):
        """由角色模型重建 主角/队友 页签(纯控件构建, 不再扫描大文本); 并预热容器定位缓存。

        progress=True 时每建 2 页泵一次事件 + 状态栏进度(20+ 个页签要 ~2s, 分批后不假死)。
        """
        self._char_spin_map = {}
        self._kangfu_ui = {}       # 角色页重建 → 功法区控件登记一并重来(v2.14.0)
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
        while self.tabs.count() > self.CHAR_TAB_BASE:
            self.tabs.removeTab(self.tabs.count() - 1)
        friends = model.get("friends") or []
        total = len(friends) + (1 if model.get("player") else 0)
        done = 0
        if model.get("player"):
            done += 1
            if progress:
                self._pump("正在构建角色页 %d/%d: 主角…" % (done, total))
            self.tabs.addTab(self._build_player_page(model), "主角")
        for f in friends:
            group = f.get("group", "AddFriends")
            disp = f.get("name") or f.get("key")
            suffix = ""
            if group != "AddFriends":
                suffix = "(%s)" % FRIEND_GROUP_LABELS.get(group, group)
            done += 1
            if progress and done % 2 == 0:
                self._pump("正在构建角色页 %d/%d: %s…" % (done, total, disp))
            self.tabs.addTab(self._build_friend_page(group, f.get("key"), disp,
                                                     f.get("scalars") or [], f.get("dicts") or {},
                                                     f.get("kangfu") or [], f.get("dressed")),
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

    # --- 剧情变量区(善恶值等, 存于 saveDialogue 段的自定义变量表) ---
    def _add_dialogue_section(self, entries):
        """「剧情变量」区: 如 善恶值 —— 值存在 saveDialogue 段的变量表里(十进制字节编码)。

        entries: [(显示名, 变量名, 当前值 or None)]; 值为 None = 该存档没有这个变量(只显示不给改)。
        改动经 `_apply_dialogue_var` 写入 self._text, 与角色属性一样随「保存/另存为/复制结果」落盘。
        """
        self._dialogue_spins = {}
        group = QGroupBox("剧情变量(存档 saveDialogue 段)")
        v = QVBoxLayout(group)
        note = QLabel(
            "游戏把「善恶值」这类剧情累计值写在 saveDialogue 段的变量表里, 其名字与数值都以"
            "“十进制字节”编码, 所以用 \"善恶值\" : 数字 是搜不到的。\n"
            "这里的改动与角色属性一样, 点「保存/另存为/复制结果」才随存档写回; "
            "除该变量那 8 个字节外不改动任何其它内容。")
        note.setWordWrap(True)
        note.setStyleSheet("color:#888;")
        v.addWidget(note)
        form = QFormLayout()
        self._building_char_page = True
        try:
            for disp, name, val in entries:
                if val is None:
                    lab = QLabel("(该存档的变量表中没有「%s」, 无法修改)" % name)
                    lab.setStyleSheet("color:#aaa;")
                    form.addRow(QLabel(disp), lab)
                    continue
                sp = QDoubleSpinBox()
                sp.setDecimals(2)
                sp.setSingleStep(1.0)
                sp.setRange(-99999999.0, 99999999.0)
                sp.setValue(float(val))
                sp.setToolTip("存档里按 double(8 字节小端)保存; 改完点「保存/另存为/复制结果」才落盘")
                btn = QPushButton("默认 0")
                btn.setToolTip("把%s一键设为 0(不偏善也不偏恶)" % disp)
                btn.clicked.connect(lambda _=False, s=sp: s.setValue(0.0))
                hb = QHBoxLayout()
                hb.addWidget(sp)
                hb.addWidget(btn)
                hb.addStretch(1)
                sp.valueChanged.connect(
                    lambda v2, nm=name: None if self._building_char_page
                    else self._apply_dialogue_var(nm, v2))
                form.addRow(QLabel("%s(%s)" % (disp, name)), hb)
                self._dialogue_spins[name] = (sp, btn)
        finally:
            self._building_char_page = False
        v.addLayout(form)
        return group

    def _apply_dialogue_var(self, name, value):
        """把剧情变量 name 改为 value(写进 self._text, 随保存一起落盘; 变量不存在则不改)。"""
        if self._text is None:
            return
        nt, changed = set_dialogue_var(self._text, name, value)
        if changed:
            self._text = nt
            self._mark_dirty()
            self.statusBar().showMessage(
                "已把剧情变量 %s 改为 %s" % (name, _fmt_dlg_num(value)), 3000)

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

    # ==================== 功法区(内功/武功/绝技/轻功, v2.14.0) ====================
    def _add_kangfu_section(self, scope, brief=None, dressed=None):
        """「功法」区: 列出该角色已学功法(标注所在段), 可多选删除 / 从功法名库多选添加。

        存档规律(见模块顶部 KANGFU_SEGS 注释): 内功→InKangFuHad, 武功→KangFuHad,
        绝技→KangFuSkillHad, 轻功→KangFuQingHad; 队友段名前面多一个下划线。
        添加时按功法在数据集里的归属自动写进对应段(不会放错), 删除按「段 + 名字」精确定位。

        dressed = `kangfu_dressed()` 的 (已装备内功名, {归一化名: 原名}); 已装备的功法会被
        灰显并在添加时跳过 —— 它们存在独立的装备对象里(不在 *Had 段), 再添一份同名会让游戏卸不下来。
        """
        key = tuple(scope)
        group = QGroupBox("功法(内功 / 武功 / 绝技 / 轻功)")
        v = QVBoxLayout(group)
        note = QLabel(
            "存档里这四种功法各占一段: 内功 InKangFuHad · 武功 KangFuHad · 绝技 KangFuSkillHad · "
            "轻功 KangFuQingHad(队友的段名前面多一个下划线)。\n"
            "「＋ 添加功法…」按功法在数据集里的归属自动写进对应段, 不会放错; 列表行首的 [内功]/[武功]/"
            "[绝技]/[轻功] 就是它所在的段。改动点工具栏「保存/另存为/复制结果」才写回存档。\n"
            "★ 已经学过、以及**当前已装备**的功法都不会重复添加 —— 已装备的功法存在独立的装备对象里"
            "(不在这些段中), 段里再出现同名会变成同名两份, 进游戏就卸不下来/切不走了。")
        note.setWordWrap(True)
        note.setStyleSheet("color:#888;")
        v.addWidget(note)
        lst = QListWidget()
        lst.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        lst.setToolTip("可按住 Ctrl/Shift 多选; 行首 [类型] = 该功法所在的段")
        v.addWidget(lst)
        row = QHBoxLayout()
        btn_add = QPushButton("＋ 添加功法…")
        btn_add.setToolTip(
            "打开 功法名.json 的 内功/武功/绝技/轻功 四大类(每类下再按门派/来源细分),\n"
            "可搜索(中文/拼音/首字母)/多选/全选一次添加多门;\n"
            "已经学过、以及已装备的功法会灰显跳过(已装备的再添一份会卸不下来)。\n"
            "对话框里的「等级 _Lv」改一下就立即记住(存 设置.json), 下次打开还是这个值。")
        btn_add.clicked.connect(lambda _=False, sc=scope: self._on_kangfu_add(sc))
        btn_del = QPushButton("－ 删除选中")
        btn_del.setToolTip("删除列表中选中的功法(可 Ctrl/Shift 多选); 某一段被删空时该段变回空字典")
        btn_del.clicked.connect(lambda _=False, sc=scope: self._on_kangfu_del(sc))
        row.addWidget(btn_add)
        row.addWidget(btn_del)
        row.addStretch(1)
        cnt = QLabel("")
        cnt.setStyleSheet("color:#888;")
        row.addWidget(cnt)
        v.addLayout(row)
        self._kangfu_ui[key] = {"list": lst, "count": cnt, "dressed": dressed}
        self._fill_kangfu_list(key, brief)
        return group

    def _fill_kangfu_list(self, key=None, brief=None):
        """刷新功法列表(不传 brief 时按当前文本重新定位读取, 保证与实际内容一致)。

        key=None 刷新所有已登记的功法区(角色页重建后调用)。
        """
        keys = [key] if key is not None else list(self._kangfu_ui)
        for k in keys:
            ui = self._kangfu_ui.get(k)
            if not ui:
                continue
            items = brief
            if items is None:
                co = self._loc_cached(list(k))
                items = kangfu_brief(self._text or "", co) if co is not None else []
            items = list(items)
            lst = ui["list"]
            lst.clear()
            if ui.get("dressed") is None:
                # 未由 char_model 提供或文本已改动(置 None) → 按当前文本实时重算已装备信息
                ck = self._loc_cached(list(k))
                ui["dressed"] = kangfu_dressed(self._text or "", ck) if ck is not None else (None, {})
            dressed = ui.get("dressed")
            blk = self._kangfu_blocked()      # 黑名单(归一化名): 已学列表里标出来提醒
            for seg, title, nm in items:
                it = QListWidgetItem("[%s] %s" % (title, nm))
                tip = "所在段: %s(队友为 _%s)" % (seg, seg)
                if dressed and _kangfu_norm(nm) in (dressed[1] or {}):
                    tip += "\n★ 当前已装备(在装备对象里, 不在这段中)"
                if blk and _kangfu_norm(nm) in blk:
                    tip += ("\n★ 这门功法在黑名单里(已知会让游戏卡死)\n"
                            "—— 添加时不会再出现; 要允许添加请到工具栏「功法黑名单…」移出")
                it.setToolTip(tip)
                lst.addItem(it)
            ui["brief"] = items
            cnt = ui.get("count")
            if cnt is not None:
                kinds = {}
                for _s, t, _n in items:
                    kinds[t] = kinds.get(t, 0) + 1
                txt = "已学 %d 门 %s" % (
                    len(items),
                    "/".join("%s%d" % (t, kinds[t]) for s, t, _c in KANGFU_SEGS if t in kinds)
                    if kinds else "")
                if dressed and dressed[0]:
                    txt += " · 已装备内功: %s" % dressed[0]
                if dressed and dressed[1]:
                    txt += " · 已装备功法 %d 门(不能重复添加)" % len(dressed[1])
                cnt.setText(txt)

    def _remember_kangfu_lv(self, val):
        """记住「添加功法…」的等级 _Lv(v2.14.2 起; v2.14.3 改为输入框一变就调)。

        等级框的 valueChanged 直接接到这里 —— 用户一改就**立即**写进 设置.json(小文件原子写,
        代价很低), 不用等点「确定」; 下次打开对话框就是这次的值。返回夹紧后的值。
        """
        try:
            val = max(0, min(int(val), MAX_ITEM_COUNT))
        except (TypeError, ValueError):
            return self._kangfu_lv
        if val != self._kangfu_lv:
            self._kangfu_lv = val
            self._save_settings_now()
        return val

    # ---- 功法黑名单(v2.15.0): 列入的功法不显示在候选、也不会被加给任何角色 ----
    def _kangfu_blocked(self):
        """黑名单的归一化名集合(判「这门功法被拉黑了吗」)。"""
        return kangfu_blacklist_keys(self._kangfu_blacklist)

    def _kangfu_blocked_names(self):
        """黑名单原名列表(传给「添加功法…」对话框, 让它们在候选里完全不显示)。"""
        return [it.get("name") for it in self._kangfu_blacklist if it.get("name")]

    def _open_kangfu_blacklist(self):
        """打开「功法黑名单…」管理框(程序级数据); 关闭后刷新缓存与角色页功法列表的标注。"""
        dlg = KangFuBlacklistDialog(self, items=self._kangfu_blacklist)
        dlg.exec()
        self._kangfu_blacklist = load_kangfu_blacklist()
        if self._text is not None:
            # 已学列表里的「★ 在黑名单」标注要跟着更新(逐角色刷新该区)
            for key in list(self._kangfu_ui):
                self._fill_kangfu_list(key)
        self.statusBar().showMessage(
            "功法黑名单: 共 %d 门 —— 添加功法时不会显示, 也不会被加给主角/队友"
            % len(self._kangfu_blacklist), 6000)

    def _on_kangfu_add(self, scope):
        """从 功法名.json 批量/多选给该角色添加功法(按库归属自动写进对应段)。

        ★ 已学过与**已装备**的功法都会跳过: 已装备的功法存在独立的装备对象里(DressInKangFu 等,
          不在 *Had 段), 段里再添一份同名会变成同名两份 → 游戏里卸不下来/切不走(v2.14.1)。
        """
        if self._text is None:
            QMessageBox.information(self, "提示",
                                    "请先「打开/粘贴」存档, 再添加功法(写入该角色的功法段)")
            return
        if not load_kangfu_categories():
            QMessageBox.information(
                self, "提示",
                "功法名.json 为空或不存在\n"
                "请先用 _scaffold/build_kangfu_names.py 从 内存所有道具.json 生成, "
                "并放到程序目录(打包 exe 时放 exe 旁)。")
            return
        co = self._loc_cached(scope)
        if co is None:
            QMessageBox.information(self, "提示", "未找到该角色的属性段, 无法添加功法")
            return
        # 已学/已装备信息优先复用角色页已算好的缓存(char_model 已算过), 避免每次点按钮都在
        # 主线程重扫整档(~0.45s); 缓存缺失(页未建/文本刚变)时才回退实时计算
        uic = self._kangfu_ui.get(tuple(scope)) or {}
        brief0 = uic.get("brief")
        if brief0:
            learned = {nm for _s, _t, nm in brief0}
        else:
            learned = {nm for _s, _t, nm, _ks, _vs, _vc in kangfu_records(self._text, co)}
        d_pair = uic.get("dressed")        # (已装备内功名, {归一化名: 原名}) 与 char_model 里同结构
        if not d_pair:
            d_pair = kangfu_dressed(self._text, co)
        dressed = d_pair[1]
        existing = learned | set(dressed.values())      # 已学过 + 已装备 都灰显
        bl_names = self._kangfu_blocked_names()          # 黑名单: 候选里连灰显都不出现
        bl = self._kangfu_blocked()                      # 归一化集合(下面还要再拦一道)
        dlg = KangFuDialog(self, existing=existing, dressed=dressed,
                           default_lv=self._kangfu_lv,      # 等级记住上次的值(v2.14.2)
                           on_lv_changed=self._remember_kangfu_lv,
                           hidden_names=bl_names)
        if not dlg.exec():
            return
        raw = list(dict.fromkeys(dlg.chosen_names()))
        # 黑名单拦截(兜底): 手动输入/自定义名也可能撞上黑名单 → 一律不加, 只提示
        names = [n for n in raw if _kangfu_norm(n) not in bl]
        n_blocked = len(raw) - len(names)
        if not names:
            if n_blocked:
                self.statusBar().showMessage(
                    "选中的 %d 门功法都在「功法黑名单」里, 已全部跳过\n"
                    "(卡死的功法先避开; 要重新允许请到工具栏「功法黑名单…」移出)" % n_blocked, 6000)
            return
        lv = self._remember_kangfu_lv(dlg.count_spin.value())
        text = self._text

        def _work():
            nt, added, skipped, unknown = kangfu_add(text, co, [(n, lv) for n in names],
                                                     dressed=dressed)
            brief = dressed2 = None
            if added:
                _get_struct_index(nt)   # 后台线程预热新文本结构索引
                # 文本已变 → 顺手把该角色的功法列表/已装备信息算好(纯计算): 放后台省主线程 ~0.5s
                brief = kangfu_brief(nt, co)
                dressed2 = kangfu_dressed(nt, co)
            return nt, added, skipped, unknown, brief, dressed2

        ok, r = self._run_bg(_work, "正在添加功法…请稍候")
        if not ok:
            self.statusBar().showMessage("添加功法失败: %s" % r, 4000)
            return
        nt, added, skipped, unknown, brief, dressed2 = r
        if added:
            self._text = nt
            self._mark_dirty()
            ui = self._kangfu_ui.get(tuple(scope))
            if ui is not None and dressed2 is not None:
                ui["dressed"] = dressed2     # 后台已算好, 主线程直接填列表
            self._fill_kangfu_list(tuple(scope), brief)
        if not added and not skipped:
            self.statusBar().showMessage("未添加任何功法(未选中名字)", 4000)
            return
        msg = "已添加 %d 门功法" % len(added)
        if added:
            msg += "(" + "、".join("%s%s" % (t, n) for t, n in added[:5])
            msg += "…)" if len(added) > 5 else ")"
        n_dressed = sum(1 for n in skipped if _kangfu_norm(n) in dressed)
        n_learned = len(skipped) - n_dressed
        if n_learned:
            msg += " · %d 门已学过自动跳过" % n_learned
        if n_dressed:
            msg += " · %d 门已装备跳过(同名两份会卸不下来)" % n_dressed
        if unknown:
            msg += " · %d 门未写入(库中无此名或该角色缺对应段)" % len(unknown)
        if n_blocked:
            msg += " · %d 门在黑名单已跳过(已知会卡死)" % n_blocked
        self.statusBar().showMessage(msg, 6000)

    def _on_kangfu_del(self, scope):
        """删除功法列表里选中的功法(按「段 + 名字」精确删条目; 段删空则变回空字典)。"""
        if self._text is None:
            QMessageBox.information(self, "提示", "请先「打开/粘贴」存档, 再删除功法")
            return
        ui = self._kangfu_ui.get(tuple(scope))
        if not ui:
            return
        brief = ui.get("brief") or []
        rows = sorted({ui["list"].row(i) for i in ui["list"].selectedItems()})
        rows = [r for r in rows if 0 <= r < len(brief)]
        if not rows:
            QMessageBox.information(self, "提示", "请先在列表里选中要删除的功法(可 Ctrl/Shift 多选)")
            return
        targets = [(brief[r][0], brief[r][2]) for r in rows]
        shown = "、".join("[%s]%s" % (brief[r][1], brief[r][2]) for r in rows[:8])
        if len(rows) > 8:
            shown += " 等 %d 门" % len(rows)
        if QMessageBox.question(
                self, "确认删除",
                "确定删除该角色的 %d 门功法?\n%s\n\n(某一段的功法被全部删光时, 该段会变回空)"
                % (len(rows), shown)) != QMessageBox.StandardButton.Yes:
            return
        co = self._loc_cached(scope)
        text = self._text

        def _work():
            nt, gone = kangfu_del(text, co, targets)
            brief = dressed2 = None
            if gone:
                _get_struct_index(nt)
                brief = kangfu_brief(nt, co)
                dressed2 = kangfu_dressed(nt, co)
            return nt, gone, brief, dressed2

        ok, r = self._run_bg(_work, "正在删除功法…请稍候")
        if not ok:
            self.statusBar().showMessage("删除功法失败: %s" % r, 4000)
            return
        nt, gone, brief, dressed2 = r
        if gone:
            self._text = nt
            self._mark_dirty()
            ui = self._kangfu_ui.get(tuple(scope))
            if ui is not None and dressed2 is not None:
                ui["dressed"] = dressed2
            self._fill_kangfu_list(tuple(scope), brief)
        self.statusBar().showMessage(
            "已删除 %d 门功法: %s" % (len(gone), "、".join(gone[:8])) if gone else "未删除",
            5000)

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
                            nt = _apply_subs(nt, [(vs2, end, val)])
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
        lay.addWidget(self._add_dialogue_section(model.get("dialogue") or []))
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
        lay.addWidget(self._add_kangfu_section(SCOPE_PLAYER, player.get("kangfu") or [],
                                              player.get("dressed")))
        lay.addWidget(self._add_map_section(model.get("maps") or []))
        return page

    # --- 队友页 ---
    def _build_friend_page(self, group, key, disp, scalars=None, dicts=None, kangfu=None,
                           dressed=None):
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
        lay.addWidget(self._add_dict_section(
            "生活技能经验 _LifeTypeLv", scope, "_LifeTypeLv", LIFEEXP_DEFAULT,
            dicts.get("_LifeTypeLv"),
            note="编号=生活技能类型(0~8, 含缺项), 数值=经验; 编号不变, 默认一键 999999"))
        lay.addWidget(self._add_kangfu_section(scope, kangfu or [], dressed))
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
        self._refresh_chong_tab()
        self._refresh_equip_tab()
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
        self._note_disk_sig()
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

    def _pump(self, msg=None):
        """长任务里的“呼吸”: 更新状态栏进度 + 处理一次待处理事件(窗口不假死、能看到进度)。

        ★ 用于**主线程的 UI 构建/填充**阶段(Qt 控件只能在主线程建, 不能搬后台)。
        泵事件期间会临时禁用中央区与工具栏(防用户在 processEvents 里重入进来), 结束后恢复原状,
        因此可安全地用在任何长主线程任务里(_reload_table / _apply_char_model / 列表批量填充…)。
        """
        if msg:
            self.statusBar().showMessage(msg, 0)
        cw = self.centralWidget()
        cw_was = cw.isEnabled() if cw is not None else None
        tb = getattr(self, "toolbar", None)
        tb_was = tb.isEnabled() if tb is not None else None
        if cw is not None and cw_was:
            cw.setEnabled(False)
        if tb is not None and tb_was:
            tb.setEnabled(False)
        try:
            QApplication.processEvents()
        finally:
            if cw is not None and cw_was:
                cw.setEnabled(True)
            if tb is not None and tb_was:
                tb.setEnabled(True)

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
                    "model": char_model(text), "lib": merge_item_names_from_text(text),
                    "shops": shop_records_full(text) if "_ShopData" in text else [],
                    "chongs": chong_model(text) if "ChongHad" in text else [],
                    "equips": equip_skill_model(text) if "EquipHad" in text else []}

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
        # 主线程 UI 构建分阶段: 每阶段前显示进度并泵一次事件 —— 大档(近万道具/20+ 角色页)
        # 构建要几秒, 分阶段后窗口不假死且能看到「正在构建…」进度(v2.14.5)
        self._set_busy(True)
        try:
            self._reload_table(progress="正在显示道具表 %d/%d…")
            self._apply_char_model(r["model"], progress=True)
            self._pump("正在构建商店列表(%d 家)…" % len(r.get("shops") or []))
            self._refresh_shop_tab(cache=r.get("shops"))
            self._pump("正在构建蛊虫/装备页…")
            self._refresh_chong_tab(model=r.get("chongs"))
            self._refresh_equip_tab(model=r.get("equips"))
        finally:
            self._set_busy(False)
        self._mark_clean()
        self._note_disk_sig()
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

    # ---------------- 设置: 保存后关闭当前文件 / 文件变化自动刷新(v2.10.0) ----------------
    @staticmethod
    def _doc_sig_of(path):
        """磁盘文件签名 (mtime_ns, size); 不存在/读不到返回 None。"""
        try:
            st = os.stat(path)
            return (st.st_mtime_ns, st.st_size)
        except OSError:
            return None

    def _doc_sig(self):
        """当前打开文件的磁盘签名; 未打开/文件不在返回 None。"""
        if not self._file_path:
            return None
        return self._doc_sig_of(self._file_path)

    def _note_disk_sig(self):
        """读/写文件成功后记录当前磁盘签名(自动刷新比对用, 避免把自己刚读写当“外部变化”)。"""
        self._last_disk_sig = self._doc_sig()
        self._reload_notified_sig = None

    def _on_auto_reload_tick(self):
        """自动刷新轮询(每 2s): 当前文件被外部改动且与已打开内容不一致时自动按新内容刷新。"""
        if not getattr(self, "_auto_reload", False):
            return
        if self._busy or self._text is None or not self._file_path:
            return
        if QApplication.activeModalWidget() is not None:   # 有模态框(如另存为对话框)时不打扰
            return
        sig = self._doc_sig()
        if sig is None or sig == self._last_disk_sig:
            return
        if self._dirty:
            # 有未保存修改: 不覆盖, 仅提示一次(去重, 避免每 2s 刷屏)
            if self._reload_notified_sig != sig:
                self._reload_notified_sig = sig
                self.statusBar().showMessage(
                    "检测到文件已在外部变化; 当前有未保存修改, 未自动刷新(处理后可点「重新读取」)", 6000)
            return
        self._reload_notified_sig = None
        # 自动刷新开始: 标题先显示 [正在刷新](大档后台解析期间窗口保持可响应)
        self._auto_refreshing = True
        self._set_title_state("refreshing")
        self.statusBar().showMessage("检测到文件已变化, 正在自动刷新…", 2000)
        self._open_path(self._file_path, record=False)
        if self._auto_refreshing:
            # 读取/解析失败(未走到 _mark_clean): 复位回“已保存”基线, 避免标题停在 [正在刷新]
            self._auto_refreshing = False
            self._set_title_state("saved")

    def _reset_document_state(self, msg=None):
        """清空当前文档回到“未打开”状态(供「保存后关闭当前文件」)。"""
        self._text = None
        self._bom = b""
        self._items = []
        self._indent = None
        self._file_path = None
        self._last_disk_sig = None
        self._reload_notified_sig = None
        self._dirty = False
        self._auto_refreshing = False
        self._filter_map = None
        self._sort_col = -1
        self._sort_asc = True
        self._char_spin_map = {}
        self._char_open_cache = {}
        self._shop_cache = {}
        self._shop_key = None
        if getattr(self, "search_edit", None) is not None:
            self.search_edit.clear()
        self.src_label.setText("源: 未打开(可点「粘贴」直接粘贴存档内容)")
        self.table.setRowCount(0)
        while self.tabs.count() > self.CHAR_TAB_BASE:
            self.tabs.removeTab(self.tabs.count() - 1)
        self._set_count_label()
        self._refresh_chong_tab()
        self._refresh_equip_tab()
        self._refresh_shop_tab()
        self._clear_title_state()   # 回到未打开: 标题不再显示保存/刷新状态
        self.statusBar().showMessage(msg or "已关闭当前文件", 3000)

    def _open_settings(self):
        """打开「设置」对话框: 保存后关闭当前文件 / 文件变化自动刷新。"""
        dlg = SettingsDialog(self, close_on_save=self._close_on_save,
                             auto_reload=self._auto_reload)
        if not dlg.exec():
            return
        cs, ar = dlg.result_flags()
        if cs == self._close_on_save and ar == self._auto_reload:
            return
        self._close_on_save = cs
        self._auto_reload = ar
        self._autosave_settings()
        self.statusBar().showMessage(
            "设置已保存: 「保存后关闭」%s · 「文件变化自动刷新」%s"
            % ("开" if cs else "关", "开" if ar else "关"), 4000)

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
                    "model": char_model(text), "lib": merge_item_names_from_text(text),
                    "shops": shop_records_full(text) if "_ShopData" in text else [],
                    "chongs": chong_model(text) if "ChongHad" in text else [],
                    "equips": equip_skill_model(text) if "EquipHad" in text else []}

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
        self._refresh_shop_tab(cache=r.get("shops"))
        self._refresh_chong_tab(model=r.get("chongs"))
        self._refresh_equip_tab(model=r.get("equips"))
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
        if self._close_on_save:
            # 「保存后关闭当前文件」: 写回后清空回到未打开, 避免之后继续编辑/再保存旧内容
            self._reset_document_state("已保存到 %s · 已按设置关闭当前文件, 下次请打开最新存档" % path)
        else:
            self._note_disk_sig()
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
        self._note_disk_sig()
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
        self.btn_sel.setText("选中改为 %d" % val)
        self._autosave_settings()

    def _autosave_settings(self):
        self._settings_save_timer.start()

    def _save_settings_now(self):
        self._settings["batch_value"] = self._batch_value
        self._settings["shop_batch_value"] = self._shop_batch_value
        self._settings["discount_all"] = self._discount_all
        self._settings["refresh_all"] = self._refresh_all
        self._settings["close_on_save"] = bool(self._close_on_save)
        self._settings["auto_reload"] = bool(self._auto_reload)
        self._settings["chong_add_defaults"] = dict(self._chong_add_defaults)
        self._settings["kangfu_lv"] = self._kangfu_lv
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

    def _on_set_selected_value(self):
        """把表格中选中的道具(去重真实索引)数量改成右侧目标值; 尊重「跳过铜钱」。"""
        rows = []
        for i in self.table.selectedItems():
            r = self._row_to_item_index(i.row())
            if r >= 0 and r not in rows:
                rows.append(r)
        if not rows:
            QMessageBox.information(self, "提示", "请先在表格中选中道具(可按住 Ctrl 或拖动多选)")
            return
        v = self.all_spin.value()
        skip = self.skip_copper_check.isChecked()
        n = 0
        for r in rows:
            it = self._items[r]
            if skip and it.name == "铜钱":
                continue
            it.count = v
            n += 1
        self._sync_visible_counts()   # 只刷数量列, 避免整表重建卡顿
        if n:
            self._mark_dirty()
        self.statusBar().showMessage("已将选中的 %d 个道具数量改为 %d" % (n, v), 3000)

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
        dlg = AddItemDialog(self, existing={it.name for it in self._items},
                            allow_codes=ITEM_ADD_CATS)   # 道具页新增只进 ItemHad, 排除 equip/skillcom
        if not dlg.exec():
            return
        names = dlg.chosen_names()
        count = dlg.count_spin.value()
        names, blocked = split_names_by_cats(names, ITEM_ADD_CATS)   # 兜底: 手输 equip 名也不进 ItemHad
        if not names:
            if blocked:
                QMessageBox.information(
                    self, "提示",
                    "装备类(equip)不进 ItemHad, 请用「＋ 添加装备…(EquipHad)」添加:\n" + "、".join(blocked[:10]))
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
            # 无过滤时只追加新行(整表重建几千行要 ~1s); 有搜索/过滤时清掉搜索并重建
            old = len(self._items) - len(added)
            if self._filter_map is None and not self.search_edit.text():
                self._append_rows_local(old)
            else:
                self._clear_search()   # 清掉搜索过滤, 让新加道具在完整列表末尾可见
            self._mark_dirty()
            self.table.scrollToBottom()
        msg = "已新增 %d 个道具(每个数量 %d)" % (len(added), count)
        if dup:
            msg += "；%d 个已在列表中自动跳过" % len(dup)
        if blocked:
            msg += "；%d 个装备类已剔除(装备请用「＋ 添加装备…(EquipHad)」)" % len(blocked)
        self.statusBar().showMessage(msg, 4000)
        if bad:
            QMessageBox.warning(self, "提示",
                                "以下名称不合法, 未添加:\n" + "\n".join(
                                    "%s (%s)" % (nm, err) for nm, err in bad[:10]))

    def _on_add_player_equip(self):
        """把 equip 类装备加入主角 EquipHad(道具页「＋ 添加装备…(EquipHad)」按钮)。

        equip 不进 ItemHad(道具页新增已排除 equip); 弹窗只列 equip 分类。
        装备可同名、不堆叠: 选好装备名后在「件数」填 N(默认 1), = 给该名追加 N 个同名实例
        (已有同名也照加, 不灰显跳过), 名字前导数字=等级; 写入 savePlayerData.value.EquipHad 段,
        随「保存/另存为/复制结果」与 ItemHad 一起写回存档。
        """
        if self._text is None:
            QMessageBox.information(self, "提示",
                                    "请先「打开/粘贴」存档, 再为主角添加装备(写入 EquipHad 段)")
            return
        dlg = AddItemDialog(self, existing=set(), default_count=1,
                            allow_codes=EQUIP_ADD_CATS)   # 可同名多件: 不灰显已有装备
        dlg.setWindowTitle("为主角添加装备(EquipHad)")
        if not dlg.exec():
            return
        names = list(dict.fromkeys(dlg.chosen_names()))
        if not names:
            return
        cnt = max(1, dlg.count_spin.value())
        text = self._text

        def _work():
            nt, added = player_add_equips(text, [(n, cnt) for n in names])
            if added:
                _get_struct_index(nt)   # 后台线程预热新文本结构索引
            return nt, added

        ok, r = self._run_bg(_work, "正在为主角添加装备…请稍候")
        if not ok:
            self.statusBar().showMessage("添加装备失败: %s" % r, 4000)
            return
        nt, added = r
        if added:
            self._text = nt
            self._mark_dirty()
        msg = "已为主角添加装备 %d 种/%d 件(写入 EquipHad, 同名=多件实例)" % (len(added), sum(added.values()))
        self.statusBar().showMessage(msg, 4000)

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
        raw_names = list(dict.fromkeys(load_item_names()))  # 去重, 防库文件历史重复导致重复添加
        if not raw_names:
            QMessageBox.information(self, "提示",
                                    "道具名库为空\n请先「打开/粘贴」一次存档, 程序会自动把其中的道具名收录到 道具名.json")
            return
        # 一键添加全部只进 ItemHad: 剔除 equip(进 EquipHad)/skillcom(不显示)
        names, blocked_cat = split_names_by_cats(raw_names, ITEM_ADD_CATS)
        if not names:
            QMessageBox.information(self, "提示",
                                    "道具名库 %d 个里没有可加入 ItemHad 的道具\n(装备/技能合成类已排除, 装备请用「＋ 添加装备…(EquipHad)」)"
                                    % len(raw_names))
            return
        existing = {it.name for it in self._items}
        to_add = [n for n in names if n not in existing]
        if not to_add:
            QMessageBox.information(self, "提示", "道具名库中的 %d 个道具均已存在, 无需添加" % len(names))
            return
        tip_cat = "\n(装备/技能合成类 %d 个已排除, 装备请用「＋ 添加装备…(EquipHad)」)" % len(blocked_cat) if blocked_cat else ""
        if QMessageBox.question(self, "确认添加",
                                "将把道具名库中的 %d 个道具追加到列表(每个数量 9999)?\n已有 %d 个自动跳过。%s"
                                % (len(to_add), len(names) - len(to_add), tip_cat)) != QMessageBox.StandardButton.Yes:
            return
        old = len(self._items)
        for n in to_add:
            self._items.append(Es3Item(n, 9999, None))
        # 无过滤时只追加新行(已有几千行不重建); 有搜索/过滤时清掉搜索并整表重建
        if self._filter_map is None and not self.search_edit.text():
            self._append_rows_local(old)
        else:
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
        # 读 5468 行道具名库 + 比对 + 合并写盘(几百 ms)放后台, 不卡 UI
        ok, r = self._run_bg(lambda: merge_item_names(names), "正在整理道具名库…请稍候")
        if not ok:
            QMessageBox.critical(self, "错误", "更新 道具名.json 失败:\n%s" % r)
            return
        new, total = r
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
针对 *.es3 存档的修改工具: <b>道具(ItemHad)</b>、<b>主角/队友属性</b>、<b>地图标注点</b>、
<b>商店NPC(卖品/装备/折扣刷新日)</b>、<b>剧情变量(善恶值)</b>、<b>蛊虫(ChongHad)</b>、
<b>装备(EquipHad)</b>、<b>功法(内功/武功/绝技/轻功)</b>。

<h3>用法</h3>
1. <b>打开</b>: 点「打开」选择 custom0.es3 等存档文件; 之后可点 <b>打开上次</b> 直接重开
   上次文件, 或点 <b>最近 ▾</b> 从「最近打开」历史里点选直接打开(历史最多 10 条,
   存于程序目录/历史记录.json, 菜单里可「清空最近记录」)。也可以点 <b>粘贴</b>
   把整份存档内容粘贴进来。<br>
   <b>状态指示灯</b>: 「打开」左边那个圆圆的小点就是当前文档状态 —— <b>绿=已保存</b>(与磁盘/来源一致)、
   <b>红=有未保存修改</b>、<b>黄=正在刷新</b>(文件变化自动刷新中)、<b>蓝=已刷新</b>(自动刷新完成)、
   <b>灰=未打开任何存档</b>(鼠标悬停有颜色图例); 与窗口标题里的状态文字同步, 一眼就能看出该不该存盘。
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
   <b>分用途显示(v2.9.0)</b>: 道具(ItemHad)/商店卖品(SellItems)的新增框只列 道具/配方/书籍/武功/
   山海录 五类——不再显示 <b>equip(装备)</b> 与 <b>skillcom(技能合成)</b>; 装备(equip)请用道具页的
   「<b>＋ 添加装备…(EquipHad)</b>」或商店装备页的「添加装备(SellEquips)」——那两个入口只显示 equip 类。
   主角装备可同名不堆叠: 选装备名后在「件数」填 N(默认 1) = 加 N 个同名实例(如填 5 = 5 把斩龙剑), 已有同名照加不跳过。
5. <b>保存</b>: 写回原文件; <b>另存为</b>: 存成新文件; <b>复制结果</b>: 把修改后的完整
   内容复制到剪贴板(配合「粘贴」流程使用)。
6. <b>重新读取</b>: 打开文件后若回到游戏又存了档(游戏把文件更新了), 点「重新读取」
   即可再次读取当前文件内容、刷新表格; 若内存里还有未保存的修改, 会先询问是否丢弃。
7. <b>多角色分页</b>: 打开含角色数据的存档后, 主区顶部会多出「主角」与每个「队友·名字」页签
   (v2.0.0 新增; v2.1.0 按 <b>_AbName 枚举全部队友</b>)——每页可逐个直接改 等级/经验/属性/血量/
   特性点/已用点等数值——带「默认」按钮的字段点按钮即一键设默认(也可点「一键全部按默认」);
   主角页另可整组改 <b>武学经验 KongFuTypeLv</b>(默认一键 999999)、<b>生活技能 LifeExp</b>(999999)、
   <b>六维 SixProCurrent</b>(999)、<b>好感度 FriendLoveNum</b>(999, 前面是好友名字);
   每个队友页也有其 六维(999)、武学经验 _KongFuTypeLv(999999) 与 生活技能经验 _LifeTypeLv(999999, v2.8.1 新增)。
   队友按存档里的 _AbName 逐一自动收录: 不论在队(AddFriends)、离队(LeaveFriends, 页签带「离队」)
   还是以后游戏新增的容器/队友, 都会自动出现对应页签, 无需改代码。
   页内「地图标注点(_ActiveMap)」可输入地点名新增/选中删除——输入时会实时过滤下方已有地点便于查重,
   与已有地点同名的添加会被拦截并提示(v2.3.1), 不会重复; 点「从地图跳转点批量添加…」(v2.4.0)可打开
   程序目录 地图跳转点.json(由 _scaffold/build_map_jump_points.py 从 MapJumpTable.bytes 提取),
   搜索(中文/拼音)/多选/全选一次添加多个跳转点(默认只列还没标注的, 与已有重复自动跳过)。
   角色页的修改与道具一样, 点「保存/另存为/复制结果」时随存档一起写回; 只精确替换对应数值,
   其它数据段原样保留。
   <b>剧情变量(善恶值, v2.12.0)</b>: 主角页新增「剧情变量(存档 saveDialogue 段)」分组——游戏把「善恶值」这类
   剧情累计值写在 saveDialogue 段的变量表里, 其存储形态不是 `"善恶值" : 7` 而是<b>十进制字节数组</b>
   (变量名与数值都按字节编码, 所以直接搜「善恶值」是搜不到的): 字符串 `83,<长度>,<UTF-8 字节...>`、
   double `78,<8 字节小端 IEEE754>`、bool `66,<1 字节>`、int32 `84,<4 字节小端>`。此处可直接读/改善恶值
   (「默认 0」按钮=设为 0), 与角色属性一样点「保存/另存为/复制结果」随存档写回, 且除该变量那 8 个字节外
   不改动任何其它内容; 该存档没有此变量时该行显示「变量表中没有…」、不给改(不会凭空插入新变量)。
8. <b>大档后台读取(v2.2.0)</b>: 超过约 600KB 的存档会在<b>后台线程</b>完成解析与角色页数据收集,
   打开/重新读取时窗口保持可操作(忙光标提示, 不会卡死/白屏)。
9. <b>商店NPC卖的道具(v2.5.1)</b>: 主区「商店NPC」页签——左侧列出存档里的 NPC/商店(取自
   saveUtilData.value._ShopData 的 abName), 顶部<b>分类下拉</b>可按 地方/门派 筛选(安居城/禾兴城/黑市/
   门派/临州城/龙居城/…, v2.5.1, 分类来自 内存所有道具.json 的 dataset/shop/*, 已生成 商店分类.json),
   并支持 <b>中文 / 拼音 / 首字</b> 搜索(可与分类叠加); 选中某 NPC 后右侧显示其 SellItems 现有卖品
   (名称/数量); 点「<b>添加卖品…</b>」从 道具名.json 搜索(中文/拼音/首字/数字)或<b>多选</b>一次添加多个
   (数量默认 <b>999</b>, 可在框内改), 与已有同名道具自动跳过, 不重复; 点「保存/另存为/复制结果」时随存档一起写回。

10. <b>蛊虫(ChongHad)页(v2.13.0)</b>: 主区「蛊虫」页签——左侧列出存档 ChongHad 里的蛊虫(显示名 · 数据集名),
    右侧分「属性 / 技能 _Skill / 偏好 _Preference / 批量(全部蛊虫)」四页; 改完点「保存/另存为/复制结果」写回。<br>
    · <b>属性</b>: 改 显示名 _CustomName、_Love、培养值 _Foster / 上限 _FosterMax, 以及三项属性
      <b>力道 Power / 灵气 Agility / 体魄 PhysicalPower</b>(「默认 9999」按钮=一键设为 9999, 可在数字框自定义)。<br>
      ★ <b>改了这三项属性后本程序会把 _TotalProperty(培养累计属性)写 0</b> —— 游戏会按当前数值重算,
      留旧值容易出错(只改培养值/显示名/培养上限时不动 _TotalProperty)。<br>
      培养上限 _FosterMax 也有「默认 9999」按钮与「本只：培养上限一键 = 9999」(新增蛊虫的默认值也是 9999)。<br>
    · <b>技能 _Skill</b> = 各状态的<b>累积值</b>(如 "着火":500 = 着火条目 500);
      <b>偏好 _Preference</b> = 状态<b>倍率</b>(1.1 = 110%%, 可大于 1)。两页都可: 表格内逐条改数值 /
      「本只: 全部 → 目标值」/「本只: 补齐全部状态(5 种)」/「本只: 写入全部技能库」/
      「＋ 添加状态…」(从技能库搜索多选) / 「－ 删除选中行」。目标值框默认 9999, 可自定义。<br>
    · <b>蛊虫可用状态共 5 种: 中毒 / 流血 / 着火 / 点穴 / 冰冻</b> —— 这是实测存档 ChongPotHad 的 5 类虫罐
      (毒/穴/血/火/冰) 与 _BuffName 的 5 个 Debuff 得出的(你猜的 4 种是对的再+冰冻)。<br>
    · <b>技能库范围(v2.13.3)</b>: 蛊虫 _Skill/_Preference 与装备技能共用的 技能名.json 现在<b>只含
      被动/战斗(pass) 与 特殊/临时(todu) 两组(共 277 条)</b>——<b>生活技能天赋、工具、测试/未整理已全部排除</b>,
      候选里不会再出现「伐木大师」「钓竿」「测试」这类不能挂到装备/蛊虫上的名字。
      「写入全部技能库」会把这两组共 277 条技能名都写进去
      (存档会明显变大, 游戏可能忽略不认识的技能名, <b>建议先只加 1 只试效果</b>)。<br>
    · 「<b>批量(全部蛊虫)</b>」分页: 对存档里全部蛊虫一次性 补齐 5 种状态 = 目标值 / 写入全部技能库 = 目标值 /
      清空, 或把三项属性一次设为同一值(目标值框默认 <b>9999</b>, _TotalProperty 同样都写 0),
      或把 <b>培养上限 _FosterMax</b> 一次设为同一值(默认 9999)。<br>
    · 「<b>＋ 添加蛊虫…</b>」: 候选来自 程序目录/蛊虫名.json(由 _scaffold/build_chong_names.py 从
      内存所有道具.json 的 dataset/chong 生成, 共 108 只; 左树按 冰系/毒系/穴系/血系/火系/固定/对战 分组),
      可搜索(中文/拼音首字母)/多选/全选。<b>蛊虫不堆叠</b>——「只数」填几就加几条独立条目(同装备)。
      新增时可设 三项属性默认值(默认 9999)与 培养上限(默认 9999) 与 _Skill/_Preference 目标值(默认 9999, 可自定义), 并可选
      「写入全部状态」或「写入全部技能库」; 这些默认值会记住(存 设置.json)。
      新增蛊虫的 图标/部位色 按名字元素自动选(冰→bing / 毒→du / 穴→xue / 血→xie / 火→huo / 银灰→yinhui,
      只取游戏 SaveChongIcon 里真实存在的图标组合), path_icon 沿用你存档里已有的路径前缀。<br>
    · 「－ 删除选中」删除左列表选中的蛊虫(可 Ctrl/Shift 多选)。<br>
11. <b>装备(EquipHad)页(v2.13.2 改名+逐件列出+增删)</b>: 主区「装备」页签——左侧把主角 EquipHad 里的装备
    <b>逐件列出</b>(同名的多件拆成多行, 显示 <code>名字 #序号</code>, 方便直接点开其中任意一件看/改),
    可搜索(中文/拼音/首字母); 右上列出选中那一件的实例(# / 等级 _Lv / 耐久 _Durable, 可直接双击改),
    右下分两页「装备技能 _SkillLv」与「词条技能 _ItemSkillLv」——存档里它们是「技能名 → [等级数组]」
    (如 "提供真气":[7])。可 表格内逐条改等级 / 「＋ 添加技能…」(从 技能名.json 搜索多选, 统一等级;
    候选同样只含 被动/战斗 pass + 特殊/临时 todu) /
    「选中行 → 目标等级」/ 「－ 删除选中」; 字段不存在时写回会自动补一个。<br>
    · 「＋ 添加装备…」往 EquipHad 加装备(只列 装备类 equip; <b>装备可同名不堆叠</b>——「件数」填 N =
    加 N 个同名实例, 如填 5 = 5 把斩龙剑)。<br>
    · 「－ 删除选中」删除左列表里选中的那一件(可 Ctrl/Shift 多选); 某个名字下<b>最后一件被删时整个条目
    一并移除</b>; 全部删光后 EquipHad 变回空字典。改完点「保存/另存为/复制结果」写回。
12. <b>功法(内功/武功/绝技/轻功) —— 主角/队友页(v2.14.0)</b>: <b>主角页与每个队友页都新增「功法」分组</b>,
    列出该角色已经会的全部功法(行首 <code>[内功]/[武功]/[绝技]/[轻功]</code> 就是它所在的存档段), 可
    <b>多选删除</b> / 从功法名库<b>搜索(中文/拼音/首字母)、多选、全选</b>批量添加。<br>
    · <b>存档规律</b>(实测 custom0.es3): 主角已学的功法分四个段存 —— <b>内功 InKangFuHad</b> /
      <b>武功 KangFuHad</b> / <b>绝技 KangFuSkillHad</b> / <b>轻功 KangFuQingHad</b>; 队友对应的段
      名字前面多一个下划线(<b>_InKangFuHad / _KangFuHad / _KangFuSkillHad / _KangFuQingHad</b>)。<br>
    · <b>怎么判断一门功法该放哪段</b>= 看它在游戏数据集里属哪一支(即 内存所有道具.json 的
      dataset/kangfu/ 下的 <b>inkangfu(内功) / kangfu(武功) / uniqueskill/jue(绝技) / uniqueskill/qing(轻功)</b>),
      与名字无关。所以本程序<b>按功法名自动判定并写进对应段, 不会放错</b>。
      (实测: 存档里每一条已学功法的段归属都与它在 dataset/kangfu 下的分支一一对应, 无一例外。)<br>
    · 「<b>＋ 添加功法…</b>」的候选来自 程序目录/功法名.json(由 _scaffold/build_kangfu_names.py 从
      内存所有道具.json 的 分类.kangfu 生成, 共 1045 门): 左树四个大分类(内功/武功/绝技/轻功)与四个存档段
      一一对应, 每个大分类下再按来源/门派细分(百灵御/必报山庄/BOSS/皇羽谷/江湖/昆仑神教/鲲鹏教/
      破道天宫/穹空派/七曜宫/五子寺), 按门派找功法很方便。<br>
    · 对话框下方「<b>等级 _Lv</b>」= 写进这些新功法条目的等级(默认取上次记住的值);
      <b>在对话框里改一下就立即记住</b>(存 设置.json 的 kangfu_lv, 下次打开对话框就是它;
      连点「取消」也已经记住), 不用每次重改。<b>已经会的功法会灰显跳过</b>,
      不会重复学同一门; 某一段在这名角色身上不存在(比如队友没有轻功段)时那一门会跳过并在状态栏提示。<br>
    · ★ <b>当前已装备的功法也不会被重复添加(v2.14.1)</b>: 角色容器里另有 <code>DressInKangFuName</code>
      (当前装备的内功名)与 <code>DressInKangFu</code> 装备对象(里面有 <code>_DressKangFu</code>=已装备的武功、
      <code>_DressQuickKangFu</code>=已装备的快捷武功、<code>_DressKangFuQing</code>=已装备的轻功;
      队友的这些字段前面多一个下划线)。这些名字<b>通常不在</b>上面那些功法段里(实测装备名 0 个出现在对应段内)——
      如果往段里再添一份同名, 存档里就成了<b>同名的两份</b>, 进游戏后这门功法<b>卸不下来 / 切不走</b>。
      所以本程序在添加时会把这些已装备的功法一律跳过(对话框里灰显, 鼠标悬停有说明),
      功法区右侧计数还会显示「已装备内功: X · 已装备功法 N 门」; 状态栏会提示「N 门已装备跳过」。<br>
    · <b>－ 删除选中</b> 按「段 + 名字」精确定位删除(可 Ctrl/Shift 多选); 某一段的功法被全部删光时
      该段会变回空字典 <code>{ }</code>(与游戏写法一致), 其它段落逐字节不动。
      新增的条目按该段的真实字段模板写(内功含 _DressKangFu/_DressQuickKangFu/_DressKangFuQing 等,
      武功含 _Exp/_AddLv/HaveShanHaiLu, 绝技/轻功只有 _Lv/_DressType/_Name)。<br>
    · <b>改动只写在内存里</b>, 与其它功能一样点工具栏「<b>保存 / 另存为 / 复制结果</b>」才写回存档。

13. <b>功法黑名单 —— 先避开已知会卡死的功法(v2.15.0)</b>: 工具栏「<b>功法黑名单…</b>」打开管理框
    (数据存程序目录 <code>功法黑名单.json</code>, 与存档无关, 换档/重开程序都生效)。<br>
    · 加进黑名单的功法: <b>「＋ 添加功法…」候选里完全不显示</b>(连灰显都不出现, 不会手滑选中),
      并且<b>主角、队友都不会被添加</b>(即便名字是手动输入/自定义的, 主窗也会再拦一道并提示
      「N 门在黑名单已跳过」); 角色页已学功法列表里鼠标悬停会标出「★ 这门功法在黑名单里」。<br>
    · 管理框里可以: <b>「＋ 从功法库添加…」</b>(功法库分类树 + 中文/拼音搜索 + 多选/全选, 批量加入;
      已在本黑名单的灰显跳过) / <b>「－ 删除选中」</b>(多选移出, 移出后它又会出现在添加候选里) /
      <b>「清空全部」</b> / 逐条写<b>备注</b>(记录卡死现象或猜测原因, 方便以后逐条验证)。
      所有改动<b>即时保存</b>到 json, 不用点确定。<br>
    · 用途: 部分功法一学就让游戏卡死, 先把已知的先列进去避开, 以后有空再逐条确认到底是
      「剧情还没到」还是别的原因 —— 备注里可以记下当时的现象与猜测。

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
蛊虫条目按游戏写法重建/追加(首条以换行+缩进+`{` 开头, 后续条目写作 `},{`);
装备/道具等其它段落逐字节保留。

<h3>道具名库(程序目录/道具名.json)</h3>
- 每次「打开/粘贴/重新读取」读档, 会自动把 ItemHad 段道具名与库比对, 新名去重收录到 道具名.json(不重名)。<br>
- <b>一键整理道具列表</b>: 把当前存档(表格)里已有的道具名即时补入 道具名.json——缺失的新增、已收录的跳过
  (手动新增/改名自定义道具名后点它, 即可把最新道具名同步进 json)。<br>
- <b>一键添加全部道具</b>: 把道具名库中当前列表还没有的道具一次性加入(每个数量 9999), 便于补全所有道具。

<h3>其它库文件(程序目录, 均由 _scaffold/ 下脚本生成)</h3>
- <b>道具分类.json</b>(build_item_categories.py): 新增道具框的 大/小/细 分类树与装备/道具分用途过滤。<br>
- <b>商店分类.json</b>(build_shop_cities.py): 商店NPC 页的 地方/门派 分类下拉。<br>
- <b>地图跳转点.json</b>(build_map_jump_points.py): 地图标注点页「从地图跳转点批量添加」。<br>
- <b>蛊虫名.json</b>(build_chong_names.py): 蛊虫页「＋ 添加蛊虫…」的候选(108 只, 含 冰系/毒系/穴系/
  血系/火系/固定/对战 分组), 取自 内存所有道具.json 的 dataset/chong。<br>
- <b>技能名.json</b>(build_skill_names.py): 蛊虫 _Skill/_Preference 与装备技能的技能名库
  —— 内存所有道具.json 的 dataset/skill 里只取 <b>pass 被动/战斗 + todu 特殊/临时 两组(277 条, v2.13.3)</b>,
  生活技能天赋(lifeperkskilltesk)/工具(tool)/测试未整理(totest) 已排除。<br>
- <b>功法名.json</b>(build_kangfu_names.py): 主角/队友页「＋ 添加功法…」的候选
  —— 内存所有道具.json 的 dataset/kangfu 全部 (1045 门), 按 <b>内功 inkangfu / 武功 kangfu /
  绝技 uniqueskill/jue / 轻功 uniqueskill/qing</b> 四大类分组(与四个存档段一一对应), 每类下再按
  门派/来源细分(百灵御/必报山庄/皇羽谷/江湖/昆仑神教/鲲鹏教/破道天宫/穹空派/七曜宫/五子寺/BOSS)。<br>
- <b>功法黑名单.json</b>(v2.15.0, 由工具栏「功法黑名单…」维护, 不需要脚本生成): 已知会让游戏卡死的
  功法名单 —— 列入的功法不出现在添加候选里、也不会被加给主角/队友; 每条可写备注(现象/猜测原因);
  与存档无关, 换档/重开程序都生效。<br>
  打包 exe 时这些 json 会随程序目录一起带上(黑名单文件若不存在, 程序会在 exe 旁自动创建)。

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
