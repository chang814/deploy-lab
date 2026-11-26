extends SceneTree
## 测试入口（ADR 0002 §5）。
## 运行：godot --headless --path . -s res://tests/run_all.gd
## （CI 中先执行一次 godot --headless --path . --import）
##
## 以下任一情况退出码为 1：有断言失败、一个测试都没发现、某个测试文件加载失败或不符合接口。
## 整体超时由 CI 的 timeout-minutes 控制。

const UNIT_DIR: String = "res://tests/unit"


func _init() -> void:
	var files: PackedStringArray = _discover()
	var passed: int = 0
	var failed: int = 0
	var broken: PackedStringArray = []

	for path: String in files:
		var script: Script = load(path) as Script
		if script == null or not script.can_instantiate():
			broken.append("%s：加载失败" % path)
			continue
		var inst: Object = script.new()
		if not inst.has_method("run"):
			broken.append("%s：没有 run() 方法（应继承 res://tests/test_case.gd）" % path)
			continue
		var r: Dictionary = inst.call("run")
		passed += int(r.get("passed", 0))
		failed += int(r.get("failed", 0))
		for m: String in r.get("messages", []):
			printerr("[%s] %s" % [path.get_file(), m])
		print("%-36s 通过 %3d  失败 %d" % [path.get_file(), int(r.get("passed", 0)), int(r.get("failed", 0))])

	for b: String in broken:
		printerr(b)
	print("合计：%d 个测试文件，通过 %d，失败 %d，无法运行的文件 %d" % [files.size(), passed, failed, broken.size()])

	var bad: bool = failed > 0 or not broken.is_empty() or files.is_empty() or passed == 0
	if files.is_empty():
		printerr("没有发现任何测试文件（%s/test_*.gd）" % UNIT_DIR)
	quit(1 if bad else 0)


func _discover() -> PackedStringArray:
	var out: PackedStringArray = []
	var dir: DirAccess = DirAccess.open(UNIT_DIR)
	if dir == null:
		return out
	for name: String in dir.get_files():
		if name.begins_with("test_") and name.ends_with(".gd"):
			out.append(UNIT_DIR.path_join(name))
	out.sort()
	return out
