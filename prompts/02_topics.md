# [topics] 公众号文章选题生成

日期：{{date}}

## 候选资讯（标题｜来源｜热度）
{{digest}}

## 热点问题（来源｜问题｜热度）
{{hot_questions}}

请结合上述素材，生成 3~6 个公众号文章选题，输出严格的 JSON 数组，每个元素字段：

- id: 稳定短 id，如 t-001
- title: 标题候选（悬念 + 信息量，不用标题党）
- angle: 切入角度（一句话说清怎么写）
- core_thesis: 核心论点（一句话，必须可被反驳）
- material_sources: 素材来源数组（引用上面的标题或热点问题）
- priority: S / A / B（S=本周必写，A=值得写，B=备选）
- value_reason: 为什么现在值得写

选题质量用 HKR 自检：
- H（Happy）够有趣、有悬念吗？
- K（Knowledge）有信息量吗？看完能学到新东西吗？
- R（Resonance）能戳中情绪吗？

S 级三项兼备，A 级至少两项，B 级至少一项。只占零项的选题直接丢弃。

只输出 JSON 数组，不要解释文字。
