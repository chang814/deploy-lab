extends RefCounted
## 引导测试的状态机（纯逻辑，便于单元测试）。步骤来自 data/test_plan.json。
##
## 约定：每次右键 Godot 都必须写一行记录（与基准计数器配对靠时间戳），
## 引导只决定这一行「是否计入进度」以及是否要标为无效。

var steps: Array = []
var done_text: String = ""
var step: int = 0
var rounds_ok: int = 0
var prepared: bool = true
var round_active: bool = false   # 按过中键、还没按右键
var round_step: int = -1          # 本轮在哪一步开始
var round_note: String = ""       # 本轮开始时的步骤 id，写入 CSV 的 note 列
var message: String = ""


func setup(plan_steps: Array, plan_done_text: String) -> void:
	steps = plan_steps
	done_text = plan_done_text
	enter(0)


func enabled() -> bool:
	return not steps.is_empty()


func finished() -> bool:
	return enabled() and step >= steps.size()


func current() -> Dictionary:
	return {} if not enabled() or finished() else steps[step]


func current_id() -> String:
	return str(current().get("id", ""))


## 进入第 i 步。返回 true 表示调用方应释放鼠标（需要准备，或已全部完成）。
func enter(i: int) -> bool:
	step = i
	rounds_ok = 0
	if finished():
		prepared = true
		return true
	prepared = str(current().get("prepare", "")).is_empty()
	return not prepared


## 按 C 锁定鼠标时调用：视为准备完成。
func on_capture() -> void:
	prepared = true


## 中键：开始新一轮，返回本轮的备注。
func on_middle() -> String:
	round_active = true
	round_step = step
	round_note = current_id()
	message = ""
	return round_note


## 右键、写记录之前调用：如果这一行不应计入，返回应写入 CSV 的作废原因。
func invalid_reason_before_log() -> String:
	if not enabled():
		return ""
	if not round_active:
		return "重复记录：没有先按中键开始新一轮"
	if round_step != step:
		return "跨步骤：本轮在上一步开始"
	if finished():
		return "引导已结束"
	return ""


## 右键、写记录之后调用。返回 true 表示调用方应释放鼠标（进入了需要准备的步骤或已完成）。
func on_logged(written: bool, invalid_reason: String, events: int) -> bool:
	var release: bool = false
	if not enabled() or finished():
		round_active = false
		return false
	if not written:
		message = "⚠ 这一轮没写进文件（见左下角），请重来：先按中键"
	elif not round_active:
		message = "⚠ 这一轮已经记录过了。先按中键开始新的一轮"
	elif round_step != step:
		message = "⚠ 这一轮是在上一步开始的，不计入。请按中键重新开始"
	elif not invalid_reason.is_empty():
		message = "⚠ 这一轮作废了（%s），不计入。请按中键重来" % invalid_reason
	elif events == 0:
		message = "⚠ 这一轮没有检测到移动，不计入。按中键后记得移动鼠标"
	else:
		rounds_ok += 1
		message = "✓ 第 %d 轮已记录" % rounds_ok
		if rounds_ok >= int(current()["rounds"]):
			message = "✓ 这一步完成！"
			release = enter(step + 1)
	round_active = false
	return release


## 跳过当前步骤。返回值同 enter()。
func skip() -> bool:
	message = "已跳过上一步"
	return enter(step + 1)
