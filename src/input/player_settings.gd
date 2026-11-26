class_name PlayerSettings
extends RefCounted
## 玩家设置（来自 data/player/settings.json）：目前只有灵敏度。
## 灵敏度是玩家个人设置，不是手感参数；之后会改为从 CS2 的 cfg 只读导入（Issue #37），这个文件作为回退。

const DEFAULT_PATH: String = "res://data/player/settings.json"

var sensitivity: float = NAN
## 灵敏度来自哪里：「设置文件」或「CS2」（界面显示用）
var source: String = "设置文件"
## 读取或校验失败的原因；为空表示有效
var error: String = "尚未加载"


func is_valid() -> bool:
	return error.is_empty()


## 从 JSON 文本解析。sensitivity 必须是有限的正数。
static func from_json_text(text: String) -> PlayerSettings:
	var s: PlayerSettings = PlayerSettings.new()
	var json: JSON = JSON.new()
	if json.parse(text) != OK:
		s.error = "JSON 解析失败（第 %d 行）：%s" % [json.get_error_line(), json.get_error_message()]
		return s
	if typeof(json.data) != TYPE_DICTIONARY:
		s.error = "不是 JSON 对象"
		return s
	var d: Dictionary = json.data
	if not d.has("sensitivity"):
		s.error = "缺少字段：sensitivity"
		return s
	var t: int = typeof(d["sensitivity"])
	if t != TYPE_FLOAT and t != TYPE_INT:
		s.error = "字段不是数字：sensitivity"
		return s
	var v: float = float(d["sensitivity"])
	if not is_finite(v) or v <= 0.0:
		s.error = "sensitivity 必须是有限的正数"
		return s
	s.sensitivity = v
	s.error = ""
	return s


static func load_file(path: String = DEFAULT_PATH) -> PlayerSettings:
	if not FileAccess.file_exists(path):
		var missing: PlayerSettings = PlayerSettings.new()
		missing.error = "找不到设置文件：%s（导出时是否漏掉了 *.json？）" % path
		return missing
	var s: PlayerSettings = from_json_text(FileAccess.get_file_as_string(path))
	if not s.is_valid():
		s.error = "%s：%s" % [path, s.error]
	return s
