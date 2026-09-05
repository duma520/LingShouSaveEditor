@echo off
chcp 65001 >nul
rem 本文件为 UTF-8 编码, 已切到 65001 代码页; 否则含中文文件名的参数会被按 GBK 解析成乱码
nuitka --standalone ^
    --enable-plugin=pyside6 ^
    --windows-console-mode=disable ^
    --follow-imports ^
    --jobs=4 ^
    --clang ^
    --remove-output ^
    --output-dir=build_output ^
    --include-data-files=地图跳转点.json=地图跳转点.json ^
    --include-data-files=道具名.json=道具名.json ^
    --include-data-files=道具分类.json=道具分类.json ^
    --include-data-files=拼音表.json=拼音表.json ^
    --include-data-files=商店分类.json=商店分类.json ^
    --include-data-files=icon.ico=icon.ico ^
    --windows-icon-from-ico=icon.ico ^
    LingShouSaveEditor.py

