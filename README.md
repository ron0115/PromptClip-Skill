# PromptClip-Skill

用一句话，把一整个素材文件夹剪成一条高光视频。

PromptClip-Skill 是一个本地优先、Prompt 驱动的视频高光提取工具。它不会修改原始素材，会先建立低分辨率帧索引，再让 Codex 子代理检查带时间戳的分段画面，最后导出一条合并后的高光视频和可继续编辑的结构化产物。

[English README](README.en.md)

![PromptClip-Skill demo flow](assets/demo-flow.svg)

### 公开素材 Demo：从咖啡制作中留下关键变化

![Coffee highlights showcase](assets/coffee-demo.gif)

这是一组用 Wikimedia Commons 公开授权素材制作的 showcase：输入几段咖啡制作视频，Prompt 只保留倒奶、拉花形成和成品展示，过滤等待、重复和无变化镜头。下载 [完整 MP4 预览](examples/coffee/showcase/coffee-highlights.mp4)，或直接查看 [`examples/coffee`](examples/coffee/) 的素材、Prompt 和来源记录。

> 说明：GIF 是为了展示效果而手工选取并拼接的参考结果，不代表已经运行过 Codex 分析；真实运行请按示例 Prompt 执行，并在导出前复查时间线。

仓库地址：https://github.com/ron0115/PromptClip-Skill

> 如果你也有一堆“拍下来却没时间看”的生活视频，欢迎先试用，再给项目一个 Star。Star 会帮助我判断这个方向是否值得继续投入。

## 30 秒判断它是否适合你

适合：手机、运动相机或大疆 Nano 拍了很多宝宝、旅行、宠物、活动碎片，只想留下“真正发生了事情”的片段。

不适合：希望完全不安装本地依赖、直接在线上传素材，或期待自动生成带复杂转场和配乐的成片。

最小体验路径：

```text
1. 安装/启用这个 Skill
2. 指定一个本地视频文件夹
3. 用一句话描述“保留什么”和“过滤什么”
4. 先查看时间戳清单，再导出 highlight-reel.mp4
```

这个项目的核心不是“让 AI 随便剪一条片”，而是把最耗时的第一步变成可复查的筛选：先过滤废片，再决定哪些瞬间值得进入成片。

仓库名是 `PromptClip-Skill`；`video-highlight-extractor` 是稳定的 Codex Skill 名称和 Python 包名，用于兼容已有流程。

## 它解决什么问题

很多视频素材的问题不是“不会剪”，而是“没时间看完”。PromptClip-Skill 试图把最费时间的第一步自动化：从一堆原始视频里找到符合要求的片段，并整理成可以复查、可以导出、可以继续进剪辑软件的结果。

它更像一个“废片过滤器”：先把大段没有信息量的片段筛掉，再把真正值得看的高光留下来。

- 用自然语言描述你想要的画面。
- 原始素材保留在本地，不被改写。
- 导出前可以打开本地 review 页面复查。
- 一次输出高光视频、时间线和 JSON 清单。

## 代表性 demo

最适合展示的场景：手机里有一堆杂乱素材，只想快速挑出适合分享的片段。

比如随手拍宝宝动态、海边遛娃、周末出门这些生活碎片，里面往往有大量时长其实是废片。
PromptClip-Skill 做的事情，就是先过滤掉这些废片，再把真正值得留下的瞬间整理出来。

```text
输入
- /Users/ron0115/Documents/手机视频素材

Prompt
- 保留表情清晰、动作完整、适合直接分享的片段，过滤掉大量废片

输出
- highlight-reel.mp4
- segments.json
- run-report.json
- timeline.fcpxml
```

流程图：

```mermaid
flowchart LR
    A[手机 / 本地文件夹] --> B[扫描并建立低分辨率索引]
    B --> C[生成 storyboard]
    C --> D[Codex 子代理检查分段画面]
    D --> E{fast or precise}
    E -->|fast| F[合并候选片段]
    E -->|precise| G[精修边界]
    F --> H[highlight-reel.mp4]
    G --> H
    H --> I[segments.json]
    H --> J[timeline.fcpxml]
    H --> K[review page]
```

想用没有隐私风险的素材演示，可以直接参考 [`examples/skatepark`](examples/skatepark/)：准备一组包含成功动作、失败动作、重复拍摄和空镜头的公开授权素材，再用 Prompt 让工具筛出真正完成的动作。仓库不携带第三方视频，避免把作者素材或许可证误打包进来。

仓库还提供了已下载的公开授权咖啡素材 Demo：[`examples/coffee`](examples/coffee/)。它用拉花和咖啡制作过程展示“保留关键变化、过滤等待和重复镜头”，并在 `SOURCES.md` 中记录作者与许可证。

## Codex Skill 用法

在 Codex 里使用：

```text
/video-highlight-extractor
```

然后提供一个本地视频文件夹和你的筛选要求。它不绑定某个固定题材：宝宝、旅行、宠物、运动、活动、采访、课程片段都可以，只要你能用 Prompt 描述想保留什么。

默认模式是 `fast`：只做 storyboard 语义分析，直接导出带 padding 的候选片段，适合快速得到一个可看的结果。  
当 Prompt 明确要求“精剪、精准边界、逐帧、每一帧必须满足”时，使用 `precise`：它会在候选片段上追加精修判断，只导出被接受的片段。

如果用户没有指定导出目录，结果会默认写到原素材目录旁边：

```text
PromptClip-Highlights/<run-id>/
```

内部扫描缓存可以放在 `work/video-highlight/runs`，但用户真正需要的 `highlight-reel.mp4`、`segments.json`、`run-report.json` 和 `timeline.fcpxml` 会留在容易找到的位置。

## 命令行快速体验

```bash
python3 -m video_highlight process \
  --input "/Users/ron0115/Documents/手机视频素材" \
  --output work/runs \
  --prompt "保留表情清晰、动作完整、和家人互动的片段" \
  --provider mock \
  --export-output "/Users/ron0115/Documents/手机视频素材/PromptClip-Highlights/run-demo" \
  --export-profile platform \
  --include-pending \
  --limit 3
```

`mock` provider 是用于自动化测试的确定性实现，不理解真实视频内容，不建议用于面向用户的结果。

启动本地 review 页面：

```bash
python3 -m video_highlight review --run work/runs/<run-id>
```

## 输出产物

```text
PromptClip-Highlights/<run-id>/
  highlight-reel.mp4   # 合并后的高光视频
  segments.json        # 片段来源、时间戳、导出策略
  run-report.json      # 本次运行报告
  timeline.fcpxml      # 可导入剪辑软件的时间线
```

## Smart Export

导出阶段会根据素材和切点自动选择策略：

- `stream_copy`：素材流参数兼容，切点也在关键帧上，尽量保留原始视频/音频流。
- `single_transcode`：素材参数兼容，但切点需要帧级解码，只对最终时间线做一次转码。
- `compatibility_transcode`：素材参数不一致或普通拼接失败时，归一化为更通用的 H.264/AAC MP4。

`segments.json` 会记录 `export_strategy`、`export_profile`、`target_audio_bitrate`、`target_audio_sample_rate`、`target_audio_channels`、`analysis_prompt`、`prompt_presets`、`source_preserved` 和 `reencoded`，方便复查和二次处理。

## Prompt Presets

当前内置的分析提示增强：

- `leading-obstruction-trim`：提示模型避开开头明显被遮挡的片段。

可以通过环境变量关闭：

```bash
export PROMPTCLIP_DISABLED_PROMPT_PRESETS=leading-obstruction-trim
```

Preset 只影响分析 Prompt，不会额外扫描视频，也不会改变导出阶段的 Smart Export 策略。

## 适合贡献的方向

- 更好的 storyboard 采样策略
- 更强的本地质量预筛选
- 更多垂直场景 Prompt preset
- 更好看的 review 页面
- 更完整的导出格式支持
- 针对中文视频素材的评测样例

## 开发说明

- `fast` 是日常高光提取的默认模式。
- `precise` 用于明确要求精准切点的任务。
- 原始素材不会被改写。
- 第一次扫描会在 run 目录下创建 `run.json` 和 `frames/`。
- 相同素材重新运行时会复用已提取的帧。
- 扫描和导出默认最多使用两个 worker，可通过 `--workers` 调整。
