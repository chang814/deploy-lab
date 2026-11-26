extends SceneTree
## 测试入口（ADR 0002 §5）。
## 运行：godot --headless --path . -s res://tests/run_all.gd [-- --unit-dir=res://其他目录]
## （CI 中先执行一次 godot --headless --path . --import）
##
## 以下任一情况退出码为 1：
## - 一个测试文件都没发现
## - 测试文件加载失败、不符合接口，或 run() 返回的结果不合法（缺字段、类型不对、计数为负、一项测试都没跑）
## - 有断言失败
## - 运行期间出现脚本错误或引擎错误（例如数组越界）：GDScript 遇到运行时错误不会抛异常，
##   而是记录错误后从出错的函数返回，所以必须用 Logger 捕获，否则会被误判为通过
## - 测试用 expect_error() 声明的预期错误没有一一对上（见下）
##
## 预期错误的匹配规则：每条声明按内容（子串）恰好消耗一条**引擎**错误；
## GDScript 运行时错误（Logger.ERROR_TYPE_SCRIPT）永远不能被声明消耗，也就不能被掩盖。
##
## 已知边界：只捕获错误日志（push_error、引擎错误、脚本错误）；printerr() 只是普通输出，不算错误。
## 测试里不要使用 assert()：在 headless 模式下断言失败会卡住进程（实测 4.7.2），
## 一律用 tests/test_case.gd 提供的 ok() / near()。整体超时由 CI 的 timeout 命令控制。

const DEFAULT_UNIT_DIR: String = "res://tests/unit"


class ErrorCatcher extends Logger:
	## 每条：{"script": bool, "text": String}
	var errors: Array[Dictionary] = []

	func _log_error(function: String, file: String, line: int, code: String, rationale: String,
			_editor_notify: bool, error_type: int, _script_backtraces: Array[ScriptBacktrace]) -> void:
		errors.append({
			"script": error_type == Logger.ERROR_TYPE_SCRIPT,
			"text": "%s:%d %s() %s %s" % [file, line, function, code, rationale],
		})

	func _log_message(_message: String, _error: bool) -> void:
		pass


## 用预期错误逐条匹配实际错误。返回问题描述；全部对上返回空字符串。
static func match_expected_errors(actual: Array[Dictionary], expected: PackedStringArray) -> String:
	var remaining: Array[Dictionary] = actual.duplicate()
	for pattern: String in expected:
		if pattern.strip_edges().is_empty():
			return "预期错误的内容不能为空（空字符串会匹配任何错误）"
		var hit: int = -1
		for i: int in remaining.size():
			if not remaining[i]["script"] and str(remaining[i]["text"]).contains(pattern):
				hit = i
				break
		if hit < 0:
			return "声明的预期错误没有出现：%s" % pattern
		remaining.remove_at(hit)
	if not remaining.is_empty():
		var kinds: String = "脚本运行时错误" if remaining.any(func(e: Dictionary) -> bool: return e["script"]) else "错误"
		return "运行时出现 %d 条未预期的%s" % [remaining.size(), kinds]
	return ""


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
		var new_errors: Array[Dictionary] = catcher.errors.slice(errors_before)
		if problem.is_empty():
			var expected: PackedStringArray = PackedStringArray(r.get("expected_errors", PackedStringArray()))
			problem = match_expected_errors(new_errors, expected)
		if not problem.is_empty():
			for e: Dictionary in new_errors:
				printerr("[%s] %s：%s" % [path.get_file(), "脚本错误" if e["script"] else "错误", e["text"]])
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
	if not _is_string_list(r["messages"]):
		return "messages 必须是字符串数组"
	if int(r["passed"]) < 0 or int(r["failed"]) < 0:
		return "计数不能为负"
	if int(r["passed"]) + int(r["failed"]) == 0:
		return "这个文件一项测试都没有运行"
	if r.has("expected_errors") and not _is_string_list(r["expected_errors"]):
		return "expected_errors 必须是字符串数组"
	return ""


func _is_string_list(v: Variant) -> bool:
	if typeof(v) == TYPE_PACKED_STRING_ARRAY:
		return true
	if typeof(v) != TYPE_ARRAY:
		return false
	for item: Variant in v:
		if typeof(item) != TYPE_STRING:
			return false
	return true


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
