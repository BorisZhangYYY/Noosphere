import type { TFunction } from "i18next";

const platformKeys: Record<string, string> = {
  wechat_mp: "sources.wechat",
  zhihu_zhuanlan: "sources.zhihu",
  xiaoheihe: "sources.xiaoheihe"
};

export function localizedPlatformLabel(platform: string, fallback: string, t: TFunction) {
  if (platform === "x" || platform === "twitter") return "X";
  const key = platformKeys[platform];
  return key ? t(key) : fallback;
}
