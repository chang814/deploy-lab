extends "res://tests/test_case.gd"
## Cs2Cfg（只读导入 CS2 灵敏度）的测试。只测解析与查找逻辑，不依赖本机是否装了 CS2。

const SAMPLE: String = '"config"\n{\n\t"convars"\n\t{\n\t\t"m_pitch"\t\t"0.022"\n\t\t"m_yaw"\t\t"0.022"\n\t\t"sensitivity"\t\t"1.25"\n\t\t"zoom_sensitivity_ratio"\t\t"1"\n\t}\n}\n'


func run_tests() -> void:
	near("读出 sensitivity", Cs2Cfg.parse_convar(SAMPLE, "sensitivity"), 1.25, 0.0)
	near("读出 m_yaw", Cs2Cfg.parse_convar(SAMPLE, "m_yaw"), 0.022, 0.0)
	ok("不会把 zoom_sensitivity_ratio 当成 sensitivity",
		is_equal_approx(Cs2Cfg.parse_convar('"zoom_sensitivity_ratio"  "3"\n"sensitivity"  "2"', "sensitivity"), 2.0))
	ok("缺字段 → NAN", is_nan(Cs2Cfg.parse_convar(SAMPLE, "volume")))
	ok("非数字 → NAN", is_nan(Cs2Cfg.parse_convar('"sensitivity"  "abc"', "sensitivity")))
	ok("空字符串 → NAN", is_nan(Cs2Cfg.parse_convar('"sensitivity"  ""', "sensitivity")))
	ok("Steam 目录为空时找不到 cfg", Cs2Cfg.find_cfg("").is_empty())
	ok("不存在的目录找不到 cfg", Cs2Cfg.find_cfg("res://不存在的目录").is_empty())

	# FpsLook 用 CS2 的值覆盖设置文件，并标明来源
	var root: Node = (load("res://scenes/main.tscn") as PackedScene).instantiate()
	var look: FpsLook = root.get_node("Player/Look") as FpsLook
	look.apply_mouse_mode = func(_m: Input.MouseMode) -> void: pass
	look.read_cs2_sensitivity = func(_c: Cs2Cfg) -> float: return 1.25
	look._ready()
	near("用了 CS2 的灵敏度", look.settings.sensitivity, 1.25, 0.0)
	ok("来源标为 CS2", look.settings.source == "CS2")
	look._exit_tree()
	root.free()
	# 读不到 CS2 时回退到设置文件
	root = (load("res://scenes/main.tscn") as PackedScene).instantiate()
	look = root.get_node("Player/Look") as FpsLook
	look.apply_mouse_mode = func(_m: Input.MouseMode) -> void: pass
	look.read_cs2_sensitivity = func(_c: Cs2Cfg) -> float: return NAN
	look._ready()
	near("回退到设置文件", look.settings.sensitivity, PlayerSettings.load_file().sensitivity, 0.0)
	ok("来源标为设置文件", look.settings.source != "CS2")
	look._exit_tree()
	root.free()
