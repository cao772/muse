# 宠物页中文子集字库

`muse_pet_zh_18.c` 和 `muse_pet_zh_24.c` 使用 Noto Sans SC 的 500 字重，仅保留宠物页实际文案与计数字符，4 bpp、未压缩的 LVGL 位图。不依赖设备字体或运行时网络。

- 上游：https://github.com/google/fonts/tree/a85815a42757630ce188fdad368c2dfc444d4773/ofl/notosanssc
- 原文件：`NotoSansSC[wght].ttf`
- SHA-256：`a3041811a78c361b1de50f953c805e0244951c21c5bd412f7232ef0d899af0da`
- 许可：SIL Open Font License 1.1，见本目录 `OFL-NotoSansSC.txt`。生成的子集使用新名称 `muse_pet_zh`。
- 生成器：`lv_font_conv@1.5.3`；C 文件开头保留精确参数和字符集合。

重建时下载上述固定版本，校验 SHA-256，通过 `fontTools.varLib.instancer.instantiateVariableFont(font, {'wght': 500})` 生成临时静态 TTF，再使用 C 文件头部的 `lv_font_conv` 参数。源 TTF 约 17 MB，仅放本地忽略目录；固件只编译生成的 C 字库，不把原 TTF 打包进 app。

修改宠物页文案后须重新生成子集并运行 `tests/test_pet_native.py`，避免漏字导致方框。24 px 字库仅用于“小小农场”标题；18 px 用于状态、按钮、田地与数字。
