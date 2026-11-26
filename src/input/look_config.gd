class_name LookConfig
extends RefCounted
## 视角参数（来自 data/look/defaults.json）。读文件属于输入层的职责，core 只接收这里解析好的值。

const DEFAULT_PATH: String = "res://data/look/defaults.json"
const REQUIRED_KEYS: PackedStringArray = [
	"m_yaw_deg", "m_pitch_deg", "pitch_min_deg", "pitch_max_deg", "base_hfov_4x3_deg",
]

var m_yaw_deg: float = NAN
var m_pitch_deg: float = NAN
var pitch_min_deg: float = NAN
var pitch_max_deg: float = NAN
var base_hfov_4x3_deg: float = NAN
## 读取或校验失败的原因；为空表示有效
var error: String = ""


func is_valid() -> bool:
	return error.is_empty()


## 从 JSON 文本解析。字段缺失、类型不对或数值不合理时 error 非空。
static func from_json_text(text: String) -> LookConfig:
	var c: LookConfig = LookConfig.new()
	var json: JSON = JSON.new()  # 用实例解析：出错时只返回错误码，不往控制台打印
	if json.parse(text) != OK:
		c.error = "JSON 解析失败（第 %d 行）：%s" % [json.get_error_line(), json.get_error_message()]
		return c
	var parsed: Variant = json.data
	if typeof(parsed) != TYPE_DICTIONARY:
		c.error = "不是 JSON 对象"
		return c
	var d: Dictionary = parsed
	for key: String in REQUIRED_KEYS:
		if not d.has(key):
			c.error = "缺少字段：%s" % key
			return c
		var t: int = typeof(d[key])
		if t != TYPE_FLOAT and t != TYPE_INT:
			c.error = "字段不是数字：%s" % key
			return c
	c.m_yaw_deg = float(d["m_yaw_deg"])
	c.m_pitch_deg = float(d["m_pitch_deg"])
	c.pitch_min_deg = float(d["pitch_min_deg"])
	c.pitch_max_deg = float(d["pitch_max_deg"])
	c.base_hfov_4x3_deg = float(d["base_hfov_4x3_deg"])
	if c.pitch_min_deg >= c.pitch_max_deg:
		c.error = "pitch_min_deg 必须小于 pitch_max_deg"
	elif c.base_hfov_4x3_deg <= 0.0 or c.base_hfov_4x3_deg >= 180.0:
		c.error = "base_hfov_4x3_deg 必须在 (0, 180) 之间"
	return c


## 从文件读取；文件不存在（例如导出时没有打包 JSON，见 ADR 0002 §7）时 error 非空。
static func load_file(path: String = DEFAULT_PATH) -> LookConfig:
	if not FileAccess.file_exists(path):
		var missing: LookConfig = LookConfig.new()
		missing.error = "找不到参数文件：%s（导出时是否漏掉了 *.json？）" % path
		return missing
	var c: LookConfig = from_json_text(FileAccess.get_file_as_string(path))
	if not c.is_valid():
		c.error = "%s：%s" % [path, c.error]
	return c
