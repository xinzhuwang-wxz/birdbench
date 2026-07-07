# data/taxonomy — vendored 快照来源

- **来源仓**：https://github.com/xinzhuwang-wxz/bird-taxonomy
- **pinned commit**：`87d5735cd36baeacb5833689ab5bf9558c3824b3`
- **拉取日期**：2026-07-08
- **重拉**：`scripts/sync-taxonomy.sh`（改 SHA 即换版本）

| 文件 | 行数 | 用途 |
|---|---|---|
| `species.jsonl` | 11,167 | 身份真源（`ebird_code` 主键 + 科属种）；科属种 join |
| `rollup.jsonl` | 4,120 | 细码（亚种/issf/form）→ `reports_as_ebird_code`（种） |
| `avibase_map.jsonl` | 8,785 | `ebird_code → avibase_id` 概念锚（同义构建辅助） |
| `raw/ebird_taxonomy.2026-07-04.jsonl` | 17,891 | 解析主索引（`speciesCode`+`comName`+`sciName`+缩写码） |

## License

分类学数据 = 事实性标识符映射（物种码 ↔ 学名/俗名/科属目），不可版权。源出 eBird/Clements taxonomy，
经 bird-taxonomy 仓的 stdlib fetcher 采集。本仓仅用于**身份解析**（名字 → speciesCode）。
`avibase_id` 经 Wikidata(CC0, P3444×P2026) 回填。**对外再分发**须核 eBird taxonomy 条款 + Avibase 概念表限制（铁律 #6 → 人审）。
