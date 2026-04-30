# Noosphere

基于 `crawl4ai` 的单篇文章提取与思源导入工具，当前 P0 支持：

- 微信公众号文章
- 知乎专栏文章

## 输出

抓取结果会先写到 `outputs/` 根目录，保留 Markdown 结构。

## 用法

只提取并输出到本地：

```bash
python src/classifier.py --dry-run URL...
```

提取并上传到思源：

```bash
SIYUAN_TOKEN=... python src/classifier.py --upload URL...
```

默认思源目标在 `config.json` 的 `siyuan.default_parent_id` 里配置。

如果要新建配置，先复制 `config.json.example` 再填入自己的真实值。
