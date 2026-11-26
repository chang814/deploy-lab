class_name WeaponConfig
extends RefCounted
## 武器参数（来自 data/weapons/weapons.json）。

const DEFAULT_PATH: String = "res://data/weapons/weapons.json"
const VIEWMODEL_KEYS: PackedStringArray = ["draw_drop_m", "kick_m", "kick_recover_mps", "kick_pitch_deg_per_m", "flash_s"]
const NUM_KEYS: PackedStringArray = ["slot", "draw_s", "fire_interval_s", "magazine", "reload_s", "range_m"]

var tick_rate_hz: float = NAN
var weapons: Array = []
## 第一人称表现参数（见 data/weapons/weapons.json 的 viewmodel）
var viewmodel: Dictionary = {}
var error: String = "尚未加载"


func is_valid() -> bool:
	return error.is_empty()


static func from_json_text(text: String) -> WeaponConfig:
	var c: WeaponConfig = WeaponConfig.new()
	var json: JSON = JSON.new()
	if json.parse(text) != OK:
		c.error = "JSON 解析失败（第 %d 行）：%s" % [json.get_error_line(), json.get_error_message()]
		return c
	if typeof(json.data) != TYPE_DICTIONARY:
		c.error = "不是 JSON 对象"
		return c
	var d: Dictionary = json.data
	if not d.has("tick_rate_hz") or typeof(d["tick_rate_hz"]) not in [TYPE_INT, TYPE_FLOAT] \
			or not is_finite(float(d["tick_rate_hz"])) or float(d["tick_rate_hz"]) <= 0.0:
		c.error = "tick_rate_hz 必须是有限的正数"
		return c
	if not d.has("weapons") or typeof(d["weapons"]) != TYPE_ARRAY or (d["weapons"] as Array).is_empty():
		c.error = "weapons 必须是非空数组"
		return c
	var ids: Dictionary = {}
	var slots: Dictionary = {}
	for w: Variant in d["weapons"]:
		if typeof(w) != TYPE_DICTIONARY:
			c.error = "weapons 里有不是对象的元素"
			return c
		var wd: Dictionary = w
		for key: String in ["id", "name"]:
			if typeof(wd.get(key)) != TYPE_STRING or String(wd[key]).is_empty():
				c.error = "武器缺少 %s" % key
				return c
		for key: String in NUM_KEYS:
			if typeof(wd.get(key)) not in [TYPE_INT, TYPE_FLOAT] or not is_finite(float(wd[key])) or float(wd[key]) < 0.0:
				c.error = "%s 的 %s 必须是有限的非负数" % [wd["id"], key]
				return c
		if typeof(wd.get("automatic")) != TYPE_BOOL:
			c.error = "%s 的 automatic 必须是 true / false" % wd["id"]
			return c
		if float(wd["fire_interval_s"]) <= 0.0 or float(wd["range_m"]) <= 0.0:
			c.error = "%s 的 fire_interval_s、range_m 必须大于 0" % wd["id"]
			return c
		if int(wd["magazine"]) > 0 and float(wd["reload_s"]) <= 0.0:
			c.error = "%s 有弹匣时 reload_s 必须大于 0" % wd["id"]
			return c
		if ids.has(wd["id"]) or slots.has(int(wd["slot"])):
			c.error = "武器 id 或槽位重复：%s" % wd["id"]
			return c
		ids[wd["id"]] = true
		slots[int(wd["slot"])] = true
		c.weapons.append(wd)
	if typeof(d.get("viewmodel")) != TYPE_DICTIONARY:
		c.error = "缺少 viewmodel"
		return c
	for key: String in VIEWMODEL_KEYS:
		var vm: Dictionary = d["viewmodel"]
		if typeof(vm.get(key)) not in [TYPE_INT, TYPE_FLOAT] or not is_finite(float(vm[key])) or float(vm[key]) < 0.0:
			c.error = "viewmodel.%s 必须是有限的非负数" % key
			return c
		c.viewmodel[key] = float(vm[key])
	c.tick_rate_hz = float(d["tick_rate_hz"])
	c.error = ""
	return c


static func load_file(path: String = DEFAULT_PATH) -> WeaponConfig:
	if not FileAccess.file_exists(path):
		var missing: WeaponConfig = WeaponConfig.new()
		missing.error = "找不到参数文件：%s（导出时是否漏掉了 *.json？）" % path
		return missing
	var c: WeaponConfig = from_json_text(FileAccess.get_file_as_string(path))
	if not c.is_valid():
		c.error = "%s：%s" % [path, c.error]
	return c
