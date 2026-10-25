# Muse｜Mac 资源与温控页

## 实现范围（2026-10-25）

新增独立 `feature/mac-resource-monitor` 开发分支，基于 [P9 Draft PR #18](https://github.com/cao772/muse/pull/18) 精确 HEAD `6570be0`。不修改 P9/P8/P7 的 Draft 分支；本轮仅写代码、测试与文档，**未在用户 Mac 上执行资源采集、未烧录实体板**。全部真实状态以精确 HEAD CI 和后续本机实测为准。

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
| CPU | `top -l 1 -n 0` 的 `CPU usage` | 整机占用快照；采集失败显示 -- |
| 总物理内存 | `sysctl -n hw.memsize` | GiB |
| 内存使用估算 | `vm_stat` 的 active+wired+compressor pages，按 page size 折算 | **估计活跃/有线/压缩驻留量**，不是 Activity Monitor 的精确「已使用内存」或内存压力图 |
| 内存压力 | `sysctl kern.memorystatus_vm_pressure_level`，如系统支持 | 1 normal / 2 warning / 4 critical，其余 unknown；不支持时不推断 |
| Swap | `sysctl -n vm.swapusage` | 当前交换空间使用量，不自动判定增长趋势 |
| 磁盘 | `shutil.disk_usage(Path.home())` | Mac 主目录所在卷总量/剩余 GiB |
| 温控 | 可选不提权 Swift `ProcessInfo.thermalState` | nominal/fair/serious/critical/unknown，**不是 °C** |
| 进程 | 显式开启后 `ps -A -o rss= -o %cpu= -o comm=` | 只显示各进程 basename/RSS/CPU 的前3，绝不读命令行参数、用户目录或私有文件；RSS 共享页不适合直接累加当系统占用 |

告警分级：thermal critical / memory pressure critical / 磁盘剩余小于2% 立即 critical；thermal serious / memory pressure warning / CPU≥90% / Swap≥8GiB / 剩余磁盘小于5% / 保守估计活跃内存≥94% 持续3次（约45秒）为 warning；恢复连续3次才解除。为降低骚扰，告警只在屏幕上显示；不自动暂停 Codex，不根据CPU高直接杀进程。

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