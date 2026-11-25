extends SceneTree
## 运行：godot --headless --path spikes/raw-input -s res://tests/test_guide_state.gd

const GuideState = preload("res://guide_state.gd")

var _passed: int = 0
var _failed: int = 0


func _init() -> void:
	_test_counts_and_advances()
	_test_duplicate_right_click_is_invalid()
	_test_cross_step_round_is_invalid()
	_test_skip_mid_round_marks_row_invalid()
	_test_invalid_or_empty_or_unwritten_not_counted()
	_test_prepare_step_requests_release()
	_test_finished()
	_test_plan_file_is_valid()
	print("结果：通过 %d，失败 %d" % [_passed, _failed])
	quit(1 if _failed > 0 else 0)


func _ok(label: String, cond: bool) -> void:
	if cond:
		_passed += 1
	else:
		_failed += 1
		printerr("失败 %s" % label)


func _plan() -> Array:
	return [
		{"id": "A", "prepare": "", "do": "x", "rounds": 2},
		{"id": "B", "prepare": "去改设置", "do": "y", "rounds": 1},
	]


func _round(g: GuideState, events: int = 10, invalid: String = "") -> bool:
	g.on_middle()
	var reason: String = g.invalid_reason_before_log()
	return g.on_logged(true, reason if invalid.is_empty() else invalid, events)


func _test_counts_and_advances() -> void:
	var g: GuideState = GuideState.new()
	g.setup(_plan(), "完成")
	_ok("初始在第 0 步且无需准备", g.step == 0 and g.prepared)
	_ok("中键返回当前步骤 id 作为备注", g.on_middle() == "A")
	_ok("有效轮写入前无作废原因", g.invalid_reason_before_log() == "")
	g.on_logged(true, "", 5)
	_ok("计入 1 轮", g.rounds_ok == 1 and g.step == 0)
	var release: bool = _round(g)
	_ok("满 2 轮进入第 1 步", g.step == 1 and g.rounds_ok == 0)
	_ok("第 1 步需要准备，要求释放鼠标", release and not g.prepared)


func _test_duplicate_right_click_is_invalid() -> void:
	var g: GuideState = GuideState.new()
	g.setup(_plan(), "完成")
	_round(g)
	var reason: String = g.invalid_reason_before_log()
	_ok("重复右键给出作废原因", reason.begins_with("重复记录"))
	g.on_logged(true, reason, 10)
	_ok("重复右键不计入", g.rounds_ok == 1)


func _test_cross_step_round_is_invalid() -> void:
	var g: GuideState = GuideState.new()
	g.setup([{"id": "A", "prepare": "", "do": "x", "rounds": 1}, {"id": "B", "prepare": "", "do": "y", "rounds": 1}], "完成")
	g.on_middle()
	g.on_logged(true, "", 10)  # A 完成，自动进入 B（无需准备，不释放鼠标）
	_ok("自动进入无需准备的下一步", g.step == 1 and g.prepared)
	var reason: String = g.invalid_reason_before_log()
	_ok("换步后未按中键直接右键：作废", reason.begins_with("重复记录"))


func _test_skip_mid_round_marks_row_invalid() -> void:
	var g: GuideState = GuideState.new()
	g.setup([{"id": "A", "prepare": "", "do": "x", "rounds": 3}, {"id": "B", "prepare": "", "do": "y", "rounds": 1}], "完成")
	_ok("备注为 A", g.on_middle() == "A")
	g.skip()
	_ok("跳过后本轮备注仍为 A", g.round_note == "A")
	var reason: String = g.invalid_reason_before_log()
	_ok("跨步骤的轮作废", reason.begins_with("跨步骤"))
	g.on_logged(true, reason, 10)
	_ok("跨步骤不计入 B", g.rounds_ok == 0 and g.step == 1)


func _test_invalid_or_empty_or_unwritten_not_counted() -> void:
	var g: GuideState = GuideState.new()
	g.setup(_plan(), "完成")
	_round(g, 10, "释放了鼠标")
	_ok("作废轮不计入", g.rounds_ok == 0)
	_round(g, 0)
	_ok("无移动不计入", g.rounds_ok == 0)
	g.on_middle()
	g.on_logged(false, "", 10)
	_ok("写入失败不计入", g.rounds_ok == 0 and g.message.contains("没写进文件"))


func _test_prepare_step_requests_release() -> void:
	var g: GuideState = GuideState.new()
	_ok("没有步骤时 enter 不要求释放", g.enter(0) == false)
	g.steps = [{"id": "P", "prepare": "改设置", "do": "x", "rounds": 1}]
	_ok("需要准备", g.enter(0) and not g.prepared)
	g.on_capture()
	_ok("按 C 后准备完成", g.prepared)


func _test_finished() -> void:
	var g: GuideState = GuideState.new()
	g.setup([{"id": "A", "prepare": "", "do": "x", "rounds": 1}], "完成")
	var release: bool = _round(g)
	_ok("最后一步完成后结束并要求释放", g.finished() and release)
	_ok("结束后右键作废", g.invalid_reason_before_log() == "重复记录：没有先按中键开始新一轮")
	g.on_middle()
	_ok("结束后再开一轮也作废", g.invalid_reason_before_log() == "引导已结束")


func _test_plan_file_is_valid() -> void:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/test_plan.json"))
	_ok("test_plan.json 可解析", typeof(parsed) == TYPE_DICTIONARY)
	if typeof(parsed) != TYPE_DICTIONARY:
		return
	var ids: Dictionary = {}
	for s: Dictionary in parsed["steps"]:
		_ok("步骤 %s 字段齐全" % s.get("id", "?"), s.has("id") and s.has("prepare") and s.has("do") and int(s.get("rounds", 0)) >= 5)
		ids[s["id"]] = true
	_ok("步骤 id 不重复", ids.size() == (parsed["steps"] as Array).size())
