# question.yaml —— 待澄清假设登记契约

落实"文档不清先提问"的可追踪形式。任何一侧发现文档缺口、歧义，或验证侧
在例外情况下从 RTL 推断出的行为，都登记在这里，**逐条推进到关闭**。
假设不是污点，但**未登记的假设是**——凭猜测直接实现是违规。

## 总规则

1. **先登记，后动手**：凡是影响实现选择的理解，先写成假设条目。
2. **阻塞门禁**：`blocking: true`（假设对错会改变 checker 判定）时，
   验证侧**不得编写对应 checker**，先把 `question` 发给设计侧；设计侧
   答复并回写 `answer` 后才解除阻塞。
3. **每条假设必须有关闭路径**：`answered`（设计答复）、`confirmed`（新
   版 spec 吸收）、`obsolete`（场景已不存在）。不允许永久 open。
4. **关闭要留痕**：关闭时必须写明依据（答复人、文档版本号）。验证侧定期
   清零 review：每次回归前扫一遍 open/blocking 条目。
5. **例外场景标记**：无设计文档/无设计角色时验证侧读 RTL 得出的结论，
   `source: rtl_inference`，默认 blocking=true（未经设计口径确认前，
   一律按可能影响 checker 处理）。

## 字段规范

```yaml
schema_version: 1
questions:
  - id: QUE-001
    topic: interface            # interface | function | timing | register | other
    related: "SPEC-<模块名> v0.3 / IF-IN"   # 关联的契约条目或接口
    statement: "假设：连续两个请求的最低间隔为 1 拍"
    basis: "文档未写明间隔要求；按 valid-ready 惯例推断"
    source: ambiguity           # ambiguity 文档歧义 | rtl_inference RTL 推断
                                # （例外场景专用）；文档缺失转 gap.yaml，不入本文件
    blocking: true              # 假设错了会不会改变 checker 判定？会 = true
    risk: "若实际要求 ≥2 拍间隔，正在编写的反压 checker 会误报"
    question: "连续两个请求是否允许背靠背（间隔 0 拍）？"
    status: question_sent       # open | question_sent | answered | confirmed | obsolete
    opened_at: 2026-08-15
    opened_by: 验证侧
    answer:                     # 设计侧答复后填写
      text: "允许背靠背"
      by: 设计侧
      date: 2026-08-16
    resolution:                 # 最终关闭依据
      status_ref: "SPEC-<模块名> v0.4 contract 新增第 4 条"  # confirmed 必填
    closed_at: 2026-08-17
```

## 状态流转

```
open → question_sent → answered ──▶ confirmed（新版契约吸收，填 status_ref）
                     └─▶ confirmed（口头/邮件答复也算，answer 必填，仍建议落契约）
open ──▶ obsolete（场景消失，注明原因）
```

- 口头/即时消息答复有效，但 `answer` 必须当天回填；理想终点是答复被吸收进
  下一版 `spec.yaml`（confirmed + status_ref），否则同一个问题
  下个版本还会再问一遍。
- `blocking` 判定原则：**宁可标 true**。拿不准是否影响 checker 时按 true
  处理，先发问再写码。
