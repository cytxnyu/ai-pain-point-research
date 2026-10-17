# 证据台账与校验口径 v1

UTF-8 `research.json` 是摘要台账，不替代原来源。未知用null，真实观察到0才写0。校验器仅Python标准库；确定性JSON输出，exit0通过、exit1不通过。

## 根结构

```json
{"schema_version":1,"observed_at":"2026-10-15","evidence":[],"topics":[]}
```

空数组是结构示意，不是完成调研。日期用ISO日期或带时区时间。可附audience、window、sampling_note、query_log、access_gaps、exclusions、clusters，或将查询日志独立保存。

## evidence 条目

| 字段 | 规则 |
|---|---|
| id | 本轮唯一；同来源不因支持多题复制编号 |
| platform,url | 平台、可定位原链接；去会话令牌，保留定位必需参数 |
| observed_at | 真实读取时间；旧快照保留旧时间 |
| source_type | community_post / community_comment / github_issue / search_card / search_cache / official_index / official_doc |
| read_scope | detail / first_screen_comments / expanded_thread / full_thread / card / cache / index_page / official_doc |
| independence_key | 同帖、追问、同作者重发、已知转载保守合组；不确定同组说明 |
| demand_basis | direct_question / interest_only / none；卡片缓存不作本轮当前直接求助 |
| demand_summary | 人/任务/步骤/失败/目标的摘要；direct_question非空 |
| metrics | 指标数组，无指标可[]，不捏造0 |
| published_at,question_date | 推荐；未知null，编辑日期不替代发布时间 |
| issue_state | issue推荐open / closed / unknown；另存os、version、closure_reason |

推荐补充question_locator（评论/楼层）、record_type（verbatim/paraphrase/inference）、edited_at、updated_at、query、sort_observed、sample_scope、exclusion_note、artifact_ref、independence_note。按需存子评论和匿名作者ID，不存非必要身份。

缓存可说明历史出现了某句话，不能升级已读最新详情。官方文档不作用户求助。读取范围以实际为准。

### metric 对象

| 字段 | 规则 |
|---|---|
| name | 同来源内唯一且明确，例如post_comments、question_likes、关键词搜索指数 |
| kind | engagement / search_index / search_count / relatedness / matched_items |
| status | observed / missing |
| value | number/null；missing必须null，observed真实数值；“1万+”不能伪造精确数 |
| display | 原界面显示；observed必须保留原值，未知null；换算保留显示精度 |
| scope | 对象，如作品全部评论累计、某根评论下第2条追问获赞 |
| window,region | 时间窗和地区；不适用null；次数排行须明确且一致 |

137总评与某问题5赞是两个对象，不能转成137位该问题求助者。search_count须有可核验原定义，不能把指数改名。次数比较需同平台、周期、地区、定义；脚本仅做结构和字段一致检查。

## topics 条目

必填：
- id、title。
- format：large_tutorial / small_blocker。
- evidence_ids：有效、不重复的证据ID。
- demand_status：observed（至少一条直接求助）/ repeated（至少两个独立组的直接求助）/ interest_only。
- priority_basis：editorial / search_volume，默认editorial；只有可比实际搜索次数才能search_volume。
- solution_status：untested / docs_checked / tested。tested须solution_test_ref，指实际记录；docs_checked推荐附官方来源。

search_volume还需search_metric_refs：`[{"evidence_id":"E10","metric_name":"exact_query_searches"}]`；对应指标为已观测search_count，周期/地区/平台/scope一致。词级指数可保存在证据但仍editorial，报告单列指数比较。

每题还应写audience、job、stuck_step、symptom、expected_result、teaching_route、acceptance、independent_groups、query_volume_status、freshness_note、limitations；研究者检查语义，不用脚本代替内容质量。

实测记录含环境/版本、日期、输入材料、操作、实际输出、预期对照、剩余问题；看到他人说有效仅为用户报告。

## 检查与命令

```text
python <Skill目录>/scripts/validate_research.py <研究目录>/research.json
```

脚本查结构、引用、指标缺失、读取层级、独立组、搜索口径、测试凭据字段；不联网验证来源/评论真实性，不确认测试真的通过，不保证样本适合中国大众，跨题排行也需人工核对。

人工闸门：题目具体且有可定位求助？数字日期归属对？读取范围诚实？独立组真实？营销只作兴趣？版本现状已查？大教程走到保存/交付/验收？小卡点只解一个阻塞？原问/摘要/推导/实测分开？报告、台账、日志一致且重开读过？
