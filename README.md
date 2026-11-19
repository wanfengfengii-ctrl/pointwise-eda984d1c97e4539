# 海栈站巡检记录卷

海栈站导入员接收采样端输出的固定卷、验收清单与完整原页。整理员在原盘上调整复核路线，现场员停源后仍能按领票顺序取件。晚班班长凭两班交付的原件核账，按核账号复查原字节、出处和总量。

## 一天的工作

1. 导入员核对卷号、原件身份、出处和整数微应变读数。
2. `accept` 逐件比对清单与原页，写齐新卷并登记接纳回执。
3. 现场员 `ticket` 开票，`page` 先领 A，记下返回的票内位置。
4. 整理员 `reorder` 提交同卷目标 B、C、A 和请求号。
5. 盘面用唯一备用页转存原件后腾挪。中断时按已生效的旧路线仍可领取。
6. 正常页就位、备用页为空后提交生效顺序及成功回执。
7. 晚班按旧票续领 B、C，另开票领 B、C、A。
8. 班长 `close` 核对两张完整清单，各得整数合计 31，重开后凭核账号 `readback`。

样例 `samples/haizhan.json` 含三个原件和可区分的出处，载荷用十六进制转录，读数依次为 7、11、13 微应变。核账按每个应领身份一次求和，保留零读数，空卷合计 0，缺件报错。全程采用精确整数，磁盘上的读数与总量编码为十六进制整数文本。

## 公开 Python 接口

`root` 是调用方选择的卷工作目录。用 `intake.catalog.initialize_catalog(root)` 和 `media.store.initialize_media(root)` 初始化。重复初始化保留卷、重排、票与核账。下列模块可直接导入。

| 模块及入口 | 输入及结果 |
| --- | --- |
| `intake.register.accept(root, manifest, pages)` | `VolumeManifest(volume_id, entries)` 和按清单顺序给出的 `PageImage` 序列。`ManifestEntry` 包含 `original_id, origin, reading, digest`，`PageImage` 包含 `original_id, origin, reading, payload`。`original_digest(payload)` 为原字节 SHA-256。成功返回 `AdmissionReceipt`。 |
| `reorder.request.reorder(root, volume_id, request_id, target)` | `target` 是同卷全部原件号的一次排列。成功返回 `OrderReceipt`。原请求可重投，已生效同参请求返回原回执。 |
| `delivery.ticket.ticket(root, volume_id)` | 返回含 `number` 与 `original_ids` 的 `TicketOrder`，有序名单持久冻结。 |
| `delivery.page.page(root, ticket_number, position, page_size)` | 首次使用位置 0。位置允许到名单长度，页长为正整数。返回 `PageResult(lines, next_position)`，`None` 表示结束。每行含身份、出处、读数和原字节。 |
| `audit.close.close(root, ticket_number, lines)` | `lines` 为该票的全部有序交付行。返回 `AuditResult`，其中 `record` 保存 `number`、票号、卷号、原有序元数据和 `total`，`originals` 为原样交付行。 |
| `audit.history.readback(root, audit_number)` | 返回封存的 `AuditResult`。明细及总量取自封存，按封存身份及校验依据取回原字节。 |

卷号、请求号、原件号及出处使用非空白 UTF-8 文本。卷内原件身份唯一。接纳拒绝缺页、重复身份、读数非法或逐件字段不一致的输入。已接纳卷的重复提交在制备介质前拒绝。接纳中断遗留的未登记盘面不可领取，重新接纳须重新完整校验。接纳回执可通过 `intake.receipts.load_admission_receipt` 在目录事务中查阅。

盘面与目录各自落盘。正常盘位从 1 开始，备用盘位紧随最后一个正常页。单页写入全成或未成。`ReorderInterrupted` 表示本次整理中断，应使用同卷同号同目标重试。`ActivationError` 表示发布未完成。请求在发布前保持未决，仍按旧顺序出票。同卷已有其他未决请求、同号异参或排列非法时，在改盘前拒绝。每次分页使用一个盘面读视图。已有票在暂停、发布及重开后保持原顺序。未知卷或票号、位置非法或整窗中有原件无法核验时，调用报错，调用方保留原位置。核账逐位检查身份并核对每行出处、读数和字节摘要，有任何不符时整单拒绝。历史核账只保存元数据及总量。

## 运行

需要 Python 3.11 标准库。

```text
python3 -B check_project.py
python3 -B demo.py
```

演示使用独立临时卷。它在首次正常页改写生效后暂停并重开，展示旧票续页、重排发布、新票领取、整数核账和核账号重开复查。常规回归覆盖接纳拒绝、页写前失败、写成丢回包、目录提交回滚、分页读失败、空卷和大整数封存。
