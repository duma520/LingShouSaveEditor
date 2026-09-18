@echo off
chcp 65001 >nul
rem 本文件为 UTF-8 编码, 已切到 65001 代码页; 否则含中文文件名的参数会被按 GBK 解析成乱码
rem
rem 打包内容说明:
rem   --include-data-files 里只放"静态库"(8 个 json + icon.ico), 必须与源码一起走;
rem   以下文件是**运行时在 exe 旁自建**的, 不要加进来(源目录没有该文件时 Nuitka 会报
rem   "does not match any files" 打包失败; 也会把个人配置带进 exe):
rem     设置.json / 历史记录.json / 功法黑名单.json / 道具黑名单.json
rem   想把开发目录攒好的黑名单一起带走: 打包完手动把这两个 json 拷到 exe 旁即可。
rem
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
    --include-data-files=蛊虫名.json=蛊虫名.json ^
    --include-data-files=技能名.json=技能名.json ^
    --include-data-files=功法名.json=功法名.json ^
    --include-data-files=icon.ico=icon.ico ^
    --windows-icon-from-ico=icon.ico ^
    LingShouSaveEditor.py

