# 0001 · 引擎选择：Godot 4（GDScript）

- 状态：已接受（待 P0-4 spike 验证）
- 日期：2026-11-25

## 背景
项目由多个 AI agent 协作开发，需要引擎的场景和配置能被 agent 读取、修改和审查；同时对鼠标输入精度要求极高。

## 选项
| 选项 | 优点 | 缺点 |
|---|---|---|
| Godot 4 | 场景/资源是纯文本；开源免费；体积小 | 原始鼠标输入需验证；生态比 Unity 小 |
| Unity | 生态大，教程多 | 场景 YAML 臃肿，难审查；授权条款有变动风险 |
| Unreal | 画面上限高 | 蓝图为二进制，agent 难协作；体积大，迭代慢 |

## 决定
选择 Godot 4 + GDScript。

## 后果
- P0-4 必须验证 Windows 下 `InputEventMouseMotion` 是否为原始计数。若不通过：先尝试 GDExtension 直接读取 Raw Input，再考虑更换引擎（届时新写一份决策记录）。
