# Supported Platforms Reference

## Article platforms

| Platform | URL patterns | Notes |
|---|---|---|
| WeChat Public Account | `mp.weixin.qq.com/s/...` | Full article extraction with image download; GIFs are preserved when Firecrawl is primary. |
| Zhihu Zhuanlan | `zhuanlan.zhihu.com/p/...` | Article extraction with image download. |
| Xiaoheihe | `xiaoheihe.cn/bbs/post_share?...`, `xiaoheihe.cn/app/bbs/link/...`, `api.xiaoheihe.cn/v3/bbs/app/api/web/share` | Share URLs are automatically resolved to canonical link URLs before crawling. |

## Social-post platforms

| Platform | URL patterns | Notes |
|---|---|---|
| X (Twitter) | `x.com/...`, `twitter.com/...` | Text-only MVP via oEmbed; images and videos are not downloaded. |

## Note-taking / archive targets

| Target | Command | Notes |
|---|---|---|
| SiYuan | `nsphr upload ARTICLE_ID` or `nsphr upload ARTICLE_ID --target siyuan` | Requires `siyuan` config. |
| Local archive | `nsphr upload ARTICLE_ID --target local` | Requires `local_archive` config. |

## Platform-specific extraction notes

- **WeChat MP**: duplicate cover banners are detected generically (image-only heading followed by a short publisher heading) and removed for any publisher.
- **Xiaoheihe**: share URLs redirect to canonical links; this resolution happens automatically before the crawler runs.
- **X**: content is treated as a social post; the AI review prompt is overridden per `platform_prompts.x.rewrite_prompt_path`.
