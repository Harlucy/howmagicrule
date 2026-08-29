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

GitHub Actions 会在 Pull Request 和 `main` 分支提交时执行校验。规则更新和转换工作流拥有写权限，校验工作流只有读权限。
