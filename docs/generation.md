# 规则生成说明

## 数据流

```text
上游规则源
    -> .github/workflows/rule-update.yaml
    -> rules/*.list
    -> scripts/convert-list-to-yaml.sh
    -> clash-classic/*.yaml
    -> 根目录 *.ini 订阅入口
```

`rules/` 是规则源目录，`clash-classic/` 是可重复生成的输出目录。生成的 YAML 不应直接手工编辑；需要修改规则时，应修改对应的 `.list` 或 `.MANUAL.list` 文件。

## 上游同步

`scripts/sync-upstream.py` 根据 `config/upstream-sync.json` 从 `upstream` 远程同步规则和订阅入口。配置中的 `include`、`exclude`、`rules_existing_only` 和 `ini_existing_only` 决定哪些内容可以进入本仓库；手工规则、回家规则以及未启用的专用内网规则会被保留或排除。`.MANUAL.list` 的本地规则会重新合入对应 `.list`；`append_rules` 指定额外合入的规则源，当前用于 SERVER 直连规则。合入只补充尚不存在的规则，重复运行不会反复追加。`force_empty` 会把尚未启用的本地规则源恢复为空占位。同步入口还会应用本地策略，例如把苹果服务的默认选项置于 `🚄 本地直连`。

推荐的更新顺序是：

```text
sync-upstream.py -> normalize-rules.py -> convert-list-to-yaml.sh -> validate-rules.py
```

GitHub Actions 的 `Rule-Update` 工作流先同步上游，再执行各个外部规则源的下载步骤。下载结束后使用 `sync-upstream.py --local-only` 再次应用本地合入和空占位策略，然后去重、生成 YAML 并校验；源文件、INI 和生成结果通过同一次提交更新。现有转换工作流也可手动用于重新生成。

## 清单文件

- `config/static-yaml-outputs.txt`：没有对应 `.list` 源文件但仍需保留的静态 YAML。
- `config/allowed-empty-yaml.txt`：允许只有 `payload:` 的空规则集。新增空文件前必须确认用途并登记。

没有源文件且未登记的 YAML 会被转换脚本删除，并会被校验脚本报告为错误。

## 新增规则源

1. 在 `rules/` 下添加 `.list` 文件。
2. 如果需要人工追加内容，使用同名 `.MANUAL.list` 文件，并在更新脚本中确认不会被覆盖。
3. 运行转换和校验脚本。
4. 如果该规则集要对外提供，在对应的根目录 INI 中加入引用。
5. 提交源文件、生成文件和必要的文档变更。

## 校验要求

校验脚本会检查：

- 规则类型是否在支持范围内；
- 生成 YAML 是否包含 `payload:`；
- 空规则集是否已登记；
- 每个源文件是否有对应生成物；
- 是否存在未登记的历史生成物；
- INI 引用的 YAML 是否真实存在。
- 苹果服务组的默认选择是否为本地直连；
- 被排除的专用内网规则是否重新进入入口；
- 节点筛选正则能否编译。

`python3 scripts/test-sync-upstream.py` 用临时仓库验证同步后仍保留本地手工规则、SERVER 规则和空的回家占位，重复执行不会膨胀，并检查过滤是否破坏正则。

GitHub Actions 会在 Pull Request 和 `main` 分支提交时执行校验。规则更新和转换工作流拥有写权限，校验工作流只有读权限。
