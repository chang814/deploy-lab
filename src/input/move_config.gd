class_name MoveConfig
extends RefCounted
## 移动参数（来自 data/move/defaults.json）。全部必须是有限的正数（walk_multiplier 在 (0, 1]）。

const DEFAULT_PATH: String = "res://data/move/defaults.json"
const KEYS: PackedStringArray = [
	"run_speed_mps", "walk_multiplier", "accelerate_per_s", "air_accelerate_per_s", "air_speed_cap_mps",
	"friction_per_s", "stop_speed_mps", "gravity_mps2", "jump_speed_mps", "eye_height_m", "body_height_m",
	"body_radius_m",
]

var values: Dictionary = {}
var error: String = "尚未加载"


func is_valid() -> bool:
	return error.is_empty()


func get_f(key: String) -> float:
	return float(values[key])


static func from_json_text(text: String) -> MoveConfig:
	var c: MoveConfig = MoveConfig.new()
	var json: JSON = JSON.new()
	if json.parse(text) != OK:
		c.error = "JSON 解析失败（第 %d 行）：%s" % [json.get_error_line(), json.get_error_message()]
		return c
	if typeof(json.data) != TYPE_DICTIONARY:
		c.error = "不是 JSON 对象"
		return c
	var d: Dictionary = json.data
	for key: String in KEYS:
		if not d.has(key):
			c.error = "缺少字段：%s" % key
			return c
		var t: int = typeof(d[key])
		if t != TYPE_FLOAT and t != TYPE_INT:
			c.error = "字段不是数字：%s" % key
			return c
		var v: float = float(d[key])
		if not is_finite(v) or v <= 0.0:
			c.error = "字段必须是有限的正数：%s" % key
			return c
		c.values[key] = v
	if c.get_f("walk_multiplier") > 1.0:
		c.error = "walk_multiplier 必须在 (0, 1] 之间"
		return c
	if c.get_f("body_height_m") < 2.0 * c.get_f("body_radius_m"):
		c.error = "body_height_m 不能小于 2 × body_radius_m（胶囊体做不出来）"
		return c
	if c.get_f("eye_height_m") >= c.get_f("body_height_m"):
		c.error = "eye_height_m 必须小于 body_height_m"
		return c
	c.error = ""
	return c


static func load_file(path: String = DEFAULT_PATH) -> MoveConfig:
	if not FileAccess.file_exists(path):
		var missing: MoveConfig = MoveConfig.new()
		missing.error = "找不到参数文件：%s（导出时是否漏掉了 *.json？）" % path
		return missing
	var c: MoveConfig = from_json_text(FileAccess.get_file_as_string(path))
	if not c.is_valid():
		c.error = "%s：%s" % [path, c.error]
	return c
