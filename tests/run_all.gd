extends SceneTree
## 测试入口（ADR 0002 §5）。
## 运行：godot --headless --path . -s res://tests/run_all.gd [-- --unit-dir=res://其他目录]
## （CI 中先执行一次 godot --headless --path . --import）
##
## 以下任一情况退出码为 1：
## - 一个测试文件都没发现
## - 测试文件加载失败、不符合接口，或 run() 返回的结果不合法（缺字段、类型不对、计数为负、一项测试都没跑）
## - 有断言失败
## - 运行期间出现任何脚本错误或引擎错误（例如数组越界）：GDScript 遇到运行时错误不会抛异常，
##   而是记录错误后从出错的函数返回，所以必须用 Logger 捕获，否则会被误判为通过
##
## 测试里不要使用 assert()：在 headless 模式下断言失败会卡住进程（实测 4.7.2），
## 一律用 tests/test_case.gd 提供的 ok() / near()。整体超时由 CI 的 timeout 命令控制。

const DEFAULT_UNIT_DIR: String = "res://tests/unit"


class ErrorCatcher extends Logger:
	var errors: PackedStringArray = []

	func _log_error(function: String, file: String, line: int, code: String, rationale: String,
			_editor_notify: bool, _error_type: int, _script_backtraces: Array[ScriptBacktrace]) -> void:
		errors.append("%s:%d %s() %s %s" % [file, line, function, code, rationale])

	func _log_message(_message: String, _error: bool) -> void:
		pass


func _init() -> void:
	var unit_dir: String = DEFAULT_UNIT_DIR
	for arg: String in OS.get_cmdline_user_args():
		if arg.begins_with("--unit-dir="):
			unit_dir = arg.trim_prefix("--unit-dir=")

	var files: PackedStringArray = _discover(unit_dir)
	var passed: int = 0
	var failed: int = 0
	var broken: PackedStringArray = []
	var catcher: ErrorCatcher = ErrorCatcher.new()
	OS.add_logger(catcher)

	for path: String in files:
		var errors_before: int = catcher.errors.size()
		var problem: String = ""
		var r: Dictionary = {}
		var script: Script = load(path) as Script
		if script == null or not script.can_instantiate():
			problem = "加载失败"
		else:
			var inst: Object = script.new()
			if not inst.has_method("run"):
				problem = "没有 run() 方法（应继承 res://tests/test_case.gd）"
			else:
				var raw: Variant = inst.call("run")
				problem = _check_result(raw)
				if problem.is_empty():
					r = raw
		var new_errors: PackedStringArray = catcher.errors.slice(errors_before)
		var expected: int = int(r.get("expected_errors", 0)) if problem.is_empty() else 0
		if problem.is_empty() and new_errors.size() != expected:
			problem = "运行时出现 %d 个错误（测试声明预期 %d 个）" % [new_errors.size(), expected]
		if not problem.is_empty():
			for e: String in new_errors:
				printerr("[%s] 错误：%s" % [path.get_file(), e])
		if not problem.is_empty():
			broken.append("%s：%s" % [path, problem])
			continue
		passed += int(r["passed"])
		failed += int(r["failed"])
		for m: String in r["messages"]:
			printerr("[%s] %s" % [path.get_file(), m])
		print("%-36s 通过 %3d  失败 %d" % [path.get_file(), int(r["passed"]), int(r["failed"])])

	OS.remove_logger(catcher)
	for b: String in broken:
		printerr(b)
	print("合计：%d 个测试文件，通过 %d，失败 %d，无法运行的文件 %d" % [files.size(), passed, failed, broken.size()])
	if files.is_empty():
		printerr("没有发现任何测试文件（%s/test_*.gd）" % unit_dir)
	quit(1 if failed > 0 or not broken.is_empty() or files.is_empty() else 0)


## 检查 run() 的返回值；合法返回空字符串，否则返回原因。
func _check_result(raw: Variant) -> String:
	if typeof(raw) != TYPE_DICTIONARY:
		return "run() 没有返回字典"
	var r: Dictionary = raw
	for key: String in ["passed", "failed", "messages"]:
		if not r.has(key):
			return "run() 的结果缺少字段 %s" % key
	if typeof(r["passed"]) != TYPE_INT or typeof(r["failed"]) != TYPE_INT:
		return "passed / failed 必须是整数"
	if typeof(r["messages"]) != TYPE_PACKED_STRING_ARRAY and typeof(r["messages"]) != TYPE_ARRAY:
		return "messages 必须是数组"
	if int(r["passed"]) < 0 or int(r["failed"]) < 0:
		return "计数不能为负"
	if int(r["passed"]) + int(r["failed"]) == 0:
		return "这个文件一项测试都没有运行"
	if r.has("expected_errors") and (typeof(r["expected_errors"]) != TYPE_INT or int(r["expected_errors"]) < 0):
		return "expected_errors 必须是非负整数"
	return ""


func _discover(unit_dir: String) -> PackedStringArray:
	var out: PackedStringArray = []
	var dir: DirAccess = DirAccess.open(unit_dir)
	if dir == null:
		return out
	for name: String in dir.get_files():
		if name.begins_with("test_") and name.ends_with(".gd"):
			out.append(unit_dir.path_join(name))
	out.sort()
	return out
