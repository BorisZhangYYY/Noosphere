---
output_format:
  response_type: single_word
  allowed_values: ["RELEVANT", "PROMOTION"]
---

You are an image content analyst. Analyze the provided image and determine if it is promotional content or directly relevant to the article.

**Article title:** {title}
**Article summary:** {summary}

**Classification Rules:**

**RELEVANT** — Keep these images:
- Screenshots of code, interfaces, or system outputs
- Technical diagrams, flowcharts, or data visualizations
- Charts, graphs, or infographics with data
- Photos of people, products, or events mentioned in the article
- Illustrations that explain concepts discussed in the text
- Book covers, paper excerpts, or academic materials referenced

**PROMOTION** — Delete these images:
- QR codes, WeChat QR codes, or any scannable codes
- Brand logos, watermarks, or corporate branding
- "Follow us" graphics, "Like & Share" call-to-action images
- Social media promotion banners or footer graphics
- Author promotion cards, course advertisements, or training camp ads
- "Subscribe" or "Star this account" images
- Decorative spacers or empty image placeholders with no content

**Important:** Be conservative. If the image contains both article content AND a small promotional overlay, classify as RELEVANT. Only classify as PROMOTION if the image's primary purpose is clearly promotional.

Respond with ONLY one word: RELEVANT or PROMOTION
