class_name Cs2Cfg
extends RefCounted
## 只读导入 CS2 的灵敏度（Issue #37）。
##
## 红线：只读文件，绝不写入；不访问 CS2 进程。
## 位置：<Steam>/userdata/<账号>/730/local/cfg/cs2_user_convars_0_slot0.vcfg（CS2 退出时写入）。
## 有多个账号时取最近修改的那个。找不到或解析失败时返回 NAN，由调用方回退到 data/player/settings.json。

const CFG_NAME: String = "cs2_user_convars_0_slot0.vcfg"
const FALLBACK_STEAM_PATHS: PackedStringArray = [
	"C:/Program Files (x86)/Steam", "C:/Program Files/Steam", "D:/Steam", "D:/steam", "E:/Steam",
]

## 最近一次 find_cfg 的结果说明（给界面显示用；不含账号目录名）
var note: String = ""


## 从 vcfg 文本里取某个 convar 的数值；找不到或不是有限数时返回 NAN。
static func parse_convar(text: String, name: String) -> float:
	var re: RegEx = RegEx.create_from_string('"%s"\\s+"([^"]*)"' % name)
	var m: RegExMatch = re.search(text)
	if m == null:
		return NAN
	var s: String = m.get_string(1).strip_edges()
	if not s.is_valid_float():
		return NAN
	var v: float = s.to_float()
	return v if is_finite(v) else NAN


## Steam 安装目录：先查注册表（Windows），再试常见路径。找不到返回空字符串。
static func steam_path() -> String:
	if OS.get_name() == "Windows":
		var out: Array = []
		var code: int = OS.execute("reg", ["query", "HKCU\\Software\\Valve\\Steam", "/v", "SteamPath"], out)
		if code == 0 and not out.is_empty():
			for line: String in str(out[0]).split("\n"):
				var i: int = line.find("REG_SZ")
				if i >= 0:
					var p: String = line.substr(i + 6).strip_edges().replace("\\", "/")
					if DirAccess.dir_exists_absolute(p):
						return p
	for p: String in FALLBACK_STEAM_PATHS:
		if DirAccess.dir_exists_absolute(p + "/userdata"):
			return p
	return ""


## 在 Steam 目录下找最近修改的 CS2 用户 cfg；找不到返回空字符串。
static func find_cfg(steam: String) -> String:
	if steam.is_empty():
		return ""
	var best: String = ""
	var best_time: int = -1
	var root: String = steam + "/userdata"
	if not DirAccess.dir_exists_absolute(root):
		return ""
	for account: String in DirAccess.get_directories_at(root):
		var p: String = "%s/%s/730/local/cfg/%s" % [root, account, CFG_NAME]
		if FileAccess.file_exists(p):
			var t: int = FileAccess.get_modified_time(p)
			if t > best_time:
				best_time = t
				best = p
	return best


## 读取 CS2 的 sensitivity；失败返回 NAN 并在 note 里说明原因。
func read_sensitivity() -> float:
	var cfg: String = find_cfg(steam_path())
	if cfg.is_empty():
		note = "未找到 CS2 配置"
		return NAN
	var v: float = parse_convar(FileAccess.get_file_as_string(cfg), "sensitivity")
	if is_nan(v) or v <= 0.0:
		note = "CS2 配置里没有有效的 sensitivity"
		return NAN
	note = "CS2"
	return v
