# Muse｜Mac 资源与温控页

## 实现范围（2026-10-25）

新增独立 `feature/mac-resource-monitor` 开发分支，基于 [P9 Draft PR #18](https://github.com/cao772/muse/pull/18) 精确 HEAD `6570be0`。不修改 P9/P8/P7 的 Draft 分支；最初远程提交只覆盖代码和模拟测试。后续本机集成与验收见文末，原始提交的未验收说明不代表最新状态。

- `integrations/mac_resources.py`：macOS 标准命令采集，Mac 端 15 秒一次、严格 3 秒命令 timeout，数据缓存并通过原有 USB 状态帧到 ESP32。关闭 Mac 端监控配置时固定返回 unavailable，不读取机器资源。
- `gateway/talk.py` 与 `gateway/config.py`：独立异步轮询（`asyncio.to_thread`），没有把高频磁盘/CPU shell 调用塞进语音实时路径，不开放新 HTTP 接口。
- `firmware/esp32/main/muse_audio.[ch]`：有限字段与范围检验，15秒 USB host 断联后的资源状态为不可用，不把陈旧数据当实时状态。
- `firmware/esp32/main/muse_ui.c`：只添加轻量 LVGL 第8页 Resources，原 7 页、十一、农田、USB Voice/Serena80、P8 微信和 P9 Codex 页面保留。首页出现 WARNING/CRITICAL 文字但**不会自动朗读/执行任务/通知微信**。没有新增图集。

## 本机启用

默认关闭，用户需在 Mac 的 Muse 本地 `.env` 中显式配置：

```dotenv
MUSE_MAC_RESOURCES_ENABLED=true
# 可选：仅显示执行文件的basename及CPU/RSS，不上传原始命令行或工作目录
MUSE_MAC_SHOW_PROCESSES=true
# 可选：macOS SDK/Swift 安装后自己编译温控状态辅助程序
MUSE_MAC_THERMAL_HELPER=/ABSOLUTE/PATH/TO/muse-thermal
```

可选编译无需 sudo 或 SMC 授权，仅调用 `Foundation.ProcessInfo.thermalState`：

```sh
swiftc scripts/mac_thermal_state.swift -o "$HOME/muse-thermal"
```

如果需要启用温控状态，配置 `MUSE_MAC_THERMAL_HELPER=/Users/你的用户名/muse-thermal`。未经明确配置或工具不可用，显示 `Thermal unknown`，**绝不冒称获取到了 CPU/GPU 摄氏温度**。

## 指标口径

| 项 | 来源 | 显示/限制 |
| --- | --- | --- |
| CPU | `top -l 2 -s 1 -n 0` 最后一次区间采样 的 `CPU usage` | 整机占用快照；采集失败显示 -- |
| 总物理内存 | `sysctl -n hw.memsize` | GiB |
| 内存使用估算 | `vm_stat` 的 active+wired+compressor pages，按 page size 折算 | **估计活跃/有线/压缩驻留量**，不是 Activity Monitor 的精确「已使用内存」或内存压力图 |
| 内存压力 | `sysctl kern.memorystatus_vm_pressure_level`，如系统支持 | 1 normal / 2 warning / 4 critical，其余 unknown；不支持时不推断 |
| Swap | `sysctl -n vm.swapusage` | 当前使用量与最近30～90秒窗口增长；不足3次采样/30秒时趋势未知 |
| 磁盘 | `shutil.disk_usage(Path.home())` | Mac 主目录所在卷总量/剩余 GiB |
| 温控 | 可选不提权 Swift `ProcessInfo.thermalState` | nominal/fair/serious/critical/unknown，**不是 °C** |
| 进程 | 显式开启后 `ps -A -o rss= -o %cpu= -o comm=` | 只显示各进程 basename/RSS/CPU 的前3，绝不读命令行参数、用户目录或私有文件；RSS 共享页不适合直接累加当系统占用 |

告警分级：thermal critical / memory pressure critical / 磁盘剩余小于2% 立即 critical；thermal serious / memory pressure warning / CPU≥90% / 最近30～90秒Swap增长≥0.3GiB / 剩余磁盘小于5%连续3次采样为warning（每次采集完成后等15秒）；恢复连续3次才解除。单看内存占比或静态Swap高不会报警。告警携带实际触发原因，未知或缺失数据不猜测进程因果；采集失败会打断异常计数。为降低骚扰，告警只在屏幕上显示；不自动暂停 Codex，不根据CPU高直接杀进程。

## 边界与风险

- 固件 2 MiB app 仅余约16%，新增页优先复用 LVGL 原生字体/文本。需精准 CI 编译并检查分区与 BSS；如溢出，先压缩简化显示而不是扩分区。
- 私有程序名可能有敏感性，`MUSE_MAC_SHOW_PROCESSES` 默认 false。设备 USB 状态帧默认没有进程名称；开启后只发进程短名称，不传路径和命令行。
- `MUSE_MAC_RESOURCES_ENABLED` 默认为 false；未启用、非 macOS、采样失败或超过45秒均为 unavailable。串口端大于15秒无心跳也需要退化为不可用。
- 本功能只监控**运行 Muse Gateway 的这台 Mac**，其他 Mac/远端主机需要单独的受控采集器；不宣称读取远程 Codex 主机。
- 若用户需要 CPU/GPU 的实际温度和风扇 RPM，须选用经过授权验证的额外硬件传感器适配器并核实机型兼容性；本轮不调用需 sudo 的 `powermetrics`。

## 验收矩阵

- [x] 新增基础资源采集、状态缓存、阈值抑制、温控状态 Swift helper、USB 协议、LVGL 原生页及单元测试源码
- [ ] 精确 HEAD `pytest/Ruff/format` 通过
- [ ] 固件在锁定 ESP-IDF 5.5.5 / 原 BSP 下构建，内存与分区预算可接受
- [ ] 用户 Mac 真实采集的 CPU、RAM、Swap、磁盘与系统监控工具对比，Swift 热状态可选实测
- [ ] 断联/重连、一次性瞬态和45秒异常稳定性验证
- [ ] 真实板端第8页切换、告警、语音/微信/Codex/十一/农田/NVS全回归
- [ ] Draft PR 总审，无自动合并或擦写全片

任务：[Issue #20](https://github.com/cao772/muse/issues/20)。
## 本机集成复验（2026-10-25）

- 发现远程资源分支基于另一条P9，已在本集成分支接回`14017b3`的17项目/38会话看板、中文子集、即时切换及主任务栈修复；原分支和main未改。资源页置于第8页，保留前7页顺序。
- 可见页面中文，显示内存估算总/已用/可用、CPU、Swap及增长、磁盘剩余/总量、系统温控压力、数据年龄和两个高占用进程短名称。磁盘/内存均GiB，进程RSS为MiB；估算可用不等于可立即分配内存。温度数字始终不可用。
- Swift helper本机编译成功。4次真实采样间隔15秒：CPU15～28%，内存估算11.5～11.6/16GiB，Swap3.3GiB，温控nominal、内存压力normal，采集约1.6～1.8秒；具体指标随负载变化。原CAO容器在Docker关闭时不可用，已恢复既有只读容器并核对17项目/38会话。
- USB行缓冲改为4096字节有界静态空间，保留offset/ACK/SHA与音量80；采集在后台线程，不阻塞录音循环。扩大后的UI快照也移至串行LVGL静态区，避免重演启动栈溢出。
- 真实生产LVGL模拟覆盖正常/危急/断联资源页、P9忙时禁用、确认、十一66帧和农场；图片经人工检查百分号、中文和行布局，无新图集。保留动态项目和资源全部字形。
- 新增编译器栈帧门禁：refresh≤512、muse_ui_start≤512、app_main≤1024字节；本机实测128/176/592字节。仅约束自身栈帧，不替代实机调用深度测试。
- 本机233项测试、Ruff/format、文档校验和ESP-IDF5.5.5构建通过。app1,806,560字节，剩余290,592字节（13.86%），内部BSS35,656/65,536、静态RAM57,716/98,304；未扩分区。
- 仅写app前已备份24KiB NVS并校验烧录哈希。实体页面、启动与语音的最终结果仍需另记，不以模拟图片或构建代替验收。没有真实制造系统危急或高温，异常状态用固定夹具验证。

实体启动已观察MUSE_CONFIG_OK、SPEAKER_READY、AUDIO_READY，未见崩溃标记；常驻模型正在恢复，屏幕与语音体验待用户统一确认。
