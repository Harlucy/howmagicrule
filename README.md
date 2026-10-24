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
| `clash-rule-manual.ini` | 手工调整版本 |
| `clash-rule-black-manual.ini` | 黑名单手工调整版本 |
| `clash-rule-manual-test.ini` | 手工规则测试版本 |
| `clash-rule-ad.ini` | 默认规则 + 广告拦截（`ADDRejectLite`），由 `config/upstream-sync.json` 的 `derived_ini` 生成 |

`clash-rule-ad.ini` 不是手工维护的文件：`scripts/sync-upstream.py` 每次同步或 `--local-only`
都会用 `clash-rule.ini` 重新生成它，只多一行 `ADDRejectLite` 规则集，其余内容与默认入口保持一致。

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

本地模拟一次上游同步：

```bash
python3 scripts/sync-upstream.py
python3 scripts/normalize-rules.py
bash scripts/convert-list-to-yaml.sh
python3 scripts/validate-rules.py
```

`strip_rules` 会从生成后的 `rules/*.list` 中删除匹配行（个人内网域名与重复的 lululucy 后缀规则），
即使上游仍然带着这些条目也不会进入发布结果；`ini_overrides` 则在 sanitize 之后强制覆盖指定 INI 字段（例如回家组测速地址）。
`config/upstream-sync.json` 定义同步边界。同步只覆盖本仓库已经存在的规则源和 INI 入口，保留 `.MANUAL.list` 并把其中的本地规则重新合入对应 `.list`，过滤不启用的专用内网规则。`append_rules` 会把 SERVER 直连规则去重合入主直连规则。`gohome.list` 当前由 `force_empty` 强制保持空占位；硬件和网络准备好后，移除该配置项再填入实际规则。策略组的本地偏好也在该文件中维护，例如苹果服务默认把 `🚄 本地直连` 放在第一项。`scripts/normalize-rules.py` 会删除同一规则源内的完全重复项，避免定时更新不断累积规则。

GitHub Actions 每 6 小时执行一次更新，下载结束后再次应用本地规则，再生成 YAML、校验并一起提交源文件和生成结果。只应用本地规则而不拉取上游时，可运行 `python3 scripts/sync-upstream.py --local-only`。自动化需将这些修改提交并推送后才会使用新流程。

生成流程和新增规则源的维护方式见 [docs/generation.md](docs/generation.md)。

## 本地运行整条流水线

Windows 上用 `scripts/run-local.ps1`（或双击 `scripts/run-local.cmd`）一次跑完
「拉上游 → 策略改写 → 去重 → 转 YAML → 回归测试 → 校验」：

```powershell
scripts\run-local.cmd                    # 跑到校验为止，列出改动
scripts\run-local.cmd -Push              # 校验通过后提交并推送 origin
scripts\run-local.cmd -NoFetch -DryRun   # 只看会执行哪些步骤
scripts\run-local.cmd -Push -Message "sync 2026-10-22"
```

依赖 Python 3 和 Git for Windows 自带的 `bash`（脚本会自动找 `C:\Program Files\Git\bin\bash.exe`）。
它**不重跑** GitHub Actions 里那几十个外部下载步骤：`rules/*.list` 直接继承上游仓库的提交，
上游 CI 每 6 小时刷新一次，本地同步拿到的是同一份结果。需要自己拉外部源时才去跑工作流。

`run-local.ps1` 请保持 UTF-8 with BOM 保存，PowerShell 5.1 对无 BOM 的脚本会按 ANSI 解码，中文注释会导致语法错误。

定时执行（示例，每天 08:30）：

```powershell
schtasks /create /tn "MagicRuleSync" /sc daily /st 08:30 ^
  /tr "powershell -NoProfile -ExecutionPolicy Bypass -File \"D:\Proj\全球访问\ownmagicrule\scripts\run-local.ps1\" -Push"
```

本地流水线和 GitHub Actions 会同时写 `main`，分工是：**日常刷新仍由 workflow 每 6 小时完成**
（上游源下载、MANUAL 合并、派生入口、转换、校验都在 CI 里做），本地这套只在改规则、改策略、
或想先看结果时用。`-Push` 会先 `git pull --rebase origin main` 再推，所以偶尔本地推一次
不会和 CI 的提交打架；CI 那条 push 也做了同样的 rebase 保护。

## 配置注意事项

`base/` 中的配置包含本地运行参数。使用前请根据自己的端口、控制器地址和访问密钥进行调整，不要直接把个人运行配置当作公共默认配置使用。

`rules/gohome.list` 目前只保留空占位，待家庭硬件和网络准备好后再添加实际规则。未启用的专用内网规则源不会纳入生成结果。

## 漏网流量策略

订阅入口按名称区分未命中所有规则时的默认去向：`clash-rule.ini`、`clash-rule-manual.ini` 和 `clash-rule-general.ini` 的“🐟 漏网之鱼”组默认选择代理；`clash-rule-black.ini` 和 `clash-rule-black-manual.ini` 默认选择直连。该组仍是手动选择组，用户可在客户端切换。YamlForge 精修脚本不应再添加 `MATCH` 规则，否则会覆盖入口配置中的 `FINAL` 兜底选择。
