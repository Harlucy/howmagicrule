# ownmagicrule

个人使用的 Clash Meta / Mihomo 规则仓库。规则源主要来自：

- [Loyalsoldier/clash-rules](https://github.com/Loyalsoldier/clash-rules)
- [ACL4SSR/ACL4SSR](https://github.com/ACL4SSR/ACL4SSR)
- [blackmatrix7/ios_rule_script](https://github.com/blackmatrix7/ios_rule_script)

## 订阅入口

根目录的 INI 文件是可直接提供给订阅转换服务的入口：

| 文件 | 用途 |
| --- | --- |
| `clash-rule.ini` | 默认规则配置 |
| `clash-rule-black.ini` | 黑名单模式 |
| `clash-rule-general.ini` | 通用精简配置 |
| `clash-rule-gocn.ini` | GoCN 相关配置 |
| `clash-rule-manual.ini` | 手工调整版本 |
| `clash-rule-black-manual.ini` | 黑名单手工调整版本 |
| `clash-rule-manual-test.ini` | 手工规则测试版本 |

例如，使用订阅转换服务时，将下列编码后的地址作为规则配置地址：

```text
https%3A%2F%2Fraw.githubusercontent.com%2FHarlucy%2Fhowmagicrule%2Fmain%2Fclash-rule-general.ini
```

## 目录约定

- `rules/`：规则源文件。`.MANUAL.list` 文件由人工维护，自动更新不会覆盖其内容。
- `clash-classic/`：由 `rules/` 自动转换得到的 YAML 规则集，不应手工编辑。
- `base/`：Clash/Mihomo 与 sing-box 基础配置模板。
- `config/`：生成清单，包括允许保留的静态输出和允许为空的规则集。
- `scripts/`：本地生成和校验脚本。

## 自动更新与本地校验

规则更新工作流每 6 小时运行一次，也可以在 GitHub Actions 中手动触发。规则更新成功后会触发 YAML 转换；转换结果通过校验后才会提交。

本地校验：

```bash
python3 scripts/validate-rules.py
```

本地重新生成 Clash Classic 规则：

```bash
bash scripts/convert-list-to-yaml.sh
python3 scripts/validate-rules.py
```

生成流程和新增规则源的维护方式见 [docs/generation.md](docs/generation.md)。

## 配置注意事项

`base/` 中的配置包含本地运行参数。使用前请根据自己的端口、控制器地址和访问密钥进行调整，不要直接把个人运行配置当作公共默认配置使用。
