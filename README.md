# Yue Studio

Gradio 工作室：显示 YuE2 曲谱与和弦、做翻唱，并管理官方模型/资源（缺失时可下载）。

不修改 YuE2 本体。生成调用本地 [`../YuE`](../YuE) 的 `yue2` 包；音频转谱通过独立的 SheetSage2 环境。

## 安装

需要 Python 3.12 与 [uv](https://docs.astral.io/uv/)。本目录与 `YuE` 仓库应是兄弟目录。

```powershell
cd C:\Users\telesoho\prjs\my\YuE-studio
uv sync --extra test
```

`pyproject.toml` 默认走清华 PyPI 镜像。下载权重再设 Hugging Face 镜像：

```powershell
$env:HF_ENDPOINT = "https://hf-mirror.com"
```

启动：

```powershell
uv run yue-studio
```

浏览器打开终端里给出的本地地址。Gradio 队列并发为 1，同一时刻只跑一个生成任务。

## 模型与资源

「模型与资源」页会探测：

1. `YuE-studio/models/<name>`
2. `YuE/models/<name>`
3. Hugging Face 缓存

缺失时点下载，写入 `YuE-studio/models/`。权重许可是 **CC BY-NC 4.0**（另有创作者条款），与工作室 Apache 2.0 代码许可不同。

| 资源 | 用途 |
|---|---|
| YuE2-3B | 生成 / 翻唱（必需） |
| YuE2-Vae | 聆听解码（必需） |
| YuE2-Vae-legacy | 仅评测协议 |
| SheetSage2 | 音频 → ABC |
| MERT-v2-FullSong | SheetSage2 父编码器（转谱时会自动拉取） |

界面顶部显示探测到的 GPU 名称与显存，并按显存给出 YuE2 调用预设：自动 / 8 GB FP8（≤12 GiB）/ 24 GB BF16（官方）/ CPU。也可改 `memory_budget_gib`、`quantization`、`offload_ar`、`vae_core_frames`。8 GB 路径不是官方 24 GB BF16 音质基线。

## 生成

`style` 写风格/编制/人声/语种/速度，`lyrics` 写段落标签和词。`cot=full` 先规划带和弦的曲谱，再合成；改过的 ABC 会作为新输入，不会改写原来的 `plan.json`。

「历史」页扫描 `outputs/`：可播放已合成的 `audio.flac`、查看规划曲谱，把一条记录载入到生成页，或确认后删除对应本地目录。

## 翻唱

上传音频或直接提供 ABC。默认去掉和弦符号并以 `cot=melody` 生成；勾选「保留原和弦」则用 `cot=full`。

翻唱从音频转谱时，工作室会自动下载 SheetSage2 和它的父编码器 MERT-v2-FullSong（若尚未就绪），并创建独立的 Python 3.11 虚拟环境安装其依赖（与 YuE2 不能共用一套包）。也可在「模型与资源」页预先下载；下载 SheetSage2 后同样会自动配置该环境。可选：`$env:YUE_STUDIO_SHEETSAGE_PYTHON` 指向已有解释器。转谱需要本机 FFmpeg。

## 测试

离线、不下载权重、不需要 GPU：

```powershell
uv run pytest -q
```
