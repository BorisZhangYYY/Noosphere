# Noosphere

[English](../README.md) | [简体中文](README.zh-CN.md)

Noosphere 将冗长、充满干扰信息的网页文章，整理成清晰、有结构、便于理解、组织和保存的阅读材料。

采集文章，用 AI 审校或翻译，加入自己的思考，再归档到本地或导入思源笔记。你可以在 Web 工作区中阅读和编辑，通过 MCP 让智能体完成工作流，或使用 CLI 编写脚本与自动化任务。三个入口共享同一份文章和设置。

![英文阅读工作区，展示多层级集合、文章正文、本地图片和来源信息](images/reading-workspace.png)

*在同一个工作区中查看集合、阅读文章和核对来源。截图使用英文界面和演示内容。*

## 主要功能

### 单篇采集与批量处理

从支持的平台提取文章正文，并下载其中的图片。批量采集支持重复检查、进度保存、暂停、取消和失败重试。你可以在工作台中跟踪采集、审校和上传进度，查看实时生成的文章内容与自动保存的任务历史。重新审校也可以随时取消。

![文章采集窗口，可选择审校模式、视角和输出语言](images/article-capture.png)

*采集前，选择文章的审校方式和阅读语言。*

### 按自己的方式审校和翻译

选择内置的“基于原文”或“小白视角”，也可以创建自己的审校视角。在文章模板中，用自然语言描述想要的结构、语言和写作风格。Noosphere 审校完整文章，支持长文处理，不会用摘要替代正文。

原始提取内容始终保留，编辑时来源信息也会受到保护。作者和发布时间缺失时，可以根据采集文章中的证据补充。你可以在设置中配置偏好的 AI 服务商和爬虫。

![审校设置，展示“基于原文”视角和自然语言写作说明](images/review-configuration.png)

*从内置视角开始，或创建自己的审校视角和文章模板。*

### 协调正文与图片

分别配置文本审校和图片审校。AI 会分析每张图片的内容及其对文章的作用，再结合审校后的正文，决定保留、调整位置或移除。被移除的图片仍可恢复；图片审校不可用时，已下载的图片会被保留。

### 阅读、编辑与整理

创建任意深度的集合。每个集合都是一个可点击的索引页面，包含标题、简介和目录；文章可以放在任意层级，也可以保持未归类状态。在侧栏中创建、重命名、嵌套和排序集合，删除后也可以恢复。文章既可以手动归类，也可以交给 AI 分类到已有集合中，并单独调整显示顺序。

通过大纲辅助阅读，或在编辑时移动段落、引文、列表、表格和代码块。折叠标题以管理较长的章节，使用撤销和重做调整内容。全文搜索会高亮已审校文章中的匹配片段，并支持在文章内逐项跳转。

### 记录个人思考与段落批注

在文章旁记录个人思考，也可以请 AI 帮忙润色。确认预览后再应用修改，并逐篇决定是否在上传时附带个人思考。

![个人思考预览，支持 Markdown 编辑和 AI 润色](images/personal-reflections.png)

*独立于文章正文，撰写和预览自己的思考。*

选中一段原文，为它添加 Markdown 解读。已批注的段落会显示下划线，点击即可打开笔记；侧栏支持导航、编辑和删除批注。个人思考和批注均与正文分开保存，不进入搜索索引。段落批注不会包含在上传内容中。

![段落批注，展示原文引句和读者的 Markdown 解读](images/passage-annotations.png)

*让自己的解读始终关联到引发思考的原文段落。*

### 归档与导出

将审校后的文章及其资源保存在本地，或上传到思源笔记。原始提取内容、审校正文、图片和个人笔记会保存在一起，方便日后阅读和复用。

## 支持的平台

| 用途 | 平台 |
|---|---|
| 文章采集 | 微信公众号、知乎专栏、小黑盒帖子 |
| 社交帖子采集 | X（Twitter），目前仅支持文本 |
| 笔记导入 | 思源笔记 |

## 开始使用

### Web 工作区

Docker 部署同时包含 Web 工作区和 MCP 服务。

```bash
git clone https://github.com/BorisZhangYYY/Noosphere.git
cd Noosphere
```

启动前，请按照[凭据配置说明](reliability-upgrade.md)设置 `NOOSPHERE_ACCESS_TOKEN` 和 `NOOSPHERE_DATABASE_PASSWORD`。复用已有 PostgreSQL 数据目录时，请保留原有数据库密码。

```bash
docker compose up -d --build
open http://localhost:8080/app/
```

配置与持久化存储详见[安装与部署](installation.md)。

### MCP

启动上述 Docker 服务后，将 MCP 客户端连接至 `http://localhost:8080/sse`。可用工具和使用方式详见 [MCP 参考](mcp-reference.md)。

你也可以安装可选的、兼容 Codex／Claude 的 Noosphere 技能：

```bash
npx skills add https://github.com/BorisZhangYYY/Noosphere
```

### CLI

需要本地脚本和自动化时，克隆仓库并安装 CLI：

```bash
git clone https://github.com/BorisZhangYYY/Noosphere.git
cd Noosphere
python -m venv .venv
source .venv/bin/activate
pip install -e .
playwright install chromium
cp config.json.example config.json
nsphr --help
```

命令和示例详见 [CLI 参考](cli-reference.md)。

## 许可证

Noosphere 采用 [MIT 许可证](../LICENSE)。
