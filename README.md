# water-legend 水施 Skill

本仓库包含水施制图规则、天正原生 DWG 图例和固定参照资料。入口为 [SKILL.md](SKILL.md)。制图前将项目建筑底图放在独立项目目录，按本项目条件确定参数。

## 服务器首次安装

在运行 Codex 的服务器账号下安装 Git。为该仓库配置只读 SSH 部署密钥时，在服务器生成密钥对，将公钥添加至 GitHub 仓库 Settings → Deploy keys，保留默认只读权限。私钥留在服务器。

将仓库克隆到该账号的技能目录。下列命令适用于默认的 Codex 用户目录，在 PowerShell 或 Bash 中执行均可。自定义了 Codex 安装目录时，请替换目标路径。

```sh
git clone git@github.com:yx635714505-netizen/water-legend.git "$HOME/.codex/skills/water-legend"
```

开始新的 Codex 会话，调用 `water-legend`。规则和参照资料均从克隆目录读取。索引中的本机绝对路径记录素材来源，四份原图随库放在 `assets/sources/`。

## 更新

本机在 Skill 源目录中核对修改、提交并推送至 `main`。服务器拉取已发布版本：

```sh
git -C "$HOME/.codex/skills/water-legend" pull --ff-only
git -C "$HOME/.codex/skills/water-legend" rev-parse --short HEAD
```

## 原生 DWG 出图环境

原生出图另需可用的 Windows、AutoCAD 与匹配的天正组件及字体。本机已验证的组合为 AutoCAD 2020 与 T20 天正建筑 V8.0。服务器首次出图时，按[后台出图与验证](references/后台出图与验证.md)定位本机模块，在工作副本中保存、重开并试印，核对原生对象、中文和线型。
