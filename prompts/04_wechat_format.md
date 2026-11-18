# [format] 公众号排版规则（来源：公开 gzh-design / 花叔排版类 skill 规则摘要）

> 说明：本文件为公开 skill 规则的摘要化整理。生产环境建议使用完整组件库 + 校验脚本，本项目内置的是降级校验版。

## 平台红线（必须遵守）
- 禁止：class / id 属性、position:fixed/absolute/sticky、float、@media/@keyframes、display:grid、CSS 变量、外部字体/CSS、script 标签。
- 禁止：可点击外链 `<a href>`（公众号正文外链会被过滤成裸 URL），超链接一律转文末参考资料列表。
- 必须：样式全部内联 `style="..."`；所有文字节点用 `<span>` 包裹（否则粘贴后样式丢失）。
- 可用：display:flex（有限）、linear-gradient、border-radius、box-shadow、p/span/blockquote/img。

## 标点规范
- 正文半角标点统一转全角，英文直引号改弯引号「」或中文引号；代码块、行内代码、URL、代码标识符内保持原样。
- 生成 HTML 时直接写全角标点，不要先写半角再事后替换。

## 视觉层级（3 层递进）
1. 锚点层：产品名/步骤/CTA/核心金句，主色加粗 + 深色底白字引用，全文 ≤ 5 处。
2. 标记层：正文关键词，每段 1~3 处，用下划线或主色加粗。
3. 容器层：引用块、概念标签、长句强调，浅底引用、徽章。

## 字号与字体
- 正文字号 16px 起，小标签 10~13px，标题 17~24px。
- 字体栈：-apple-system,BlinkMacSystemFont,'PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif。
- 文末三连顺序固定为「点赞、转发、推荐」。

## 结构规则
- 章节按 ## 顺序编号，不跳号；结语编号变体只用于末章。
- 签名区有且仅有末尾一个，原文末尾的签名/三连段并入唯一签名区。
- 图片说明只在确有说明文字时生成，`<img>` 用 max-width:100%;height:auto;display:block;margin:0 auto，不用 width:100%。
- 代码/Prompt 必须用代码块组件，不用 white-space:pre。
- 目录只展示精选 3 个核心看点，不是全量章节列表。
- 不用虚线框包标题（除非主题库明确定义）。
- 克制用色，主色全文出现 ≤ 5 处，大部分文字交给灰阶。

## 交付校验
输出 HTML 前跑校验，出现任何 ERROR 必须修复：内联样式、span 包裹、全角标点、无平台红线元素、无残留占位符。
