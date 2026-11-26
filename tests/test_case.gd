extends RefCounted
## 单元测试基类（ADR 0002 §5）。每个 tests/unit/test_*.gd 继承它并实现 run_tests()。
## 不要在测试里调用 quit()，由 tests/run_all.gd 统一汇总。

var _passed: int = 0
var _failed: int = 0
var _messages: PackedStringArray = []
var _expected_errors: int = 0


## 子类实现：在这里调用各个测试函数。
func run_tests() -> void:
	pass


## 由 run_all.gd 调用，返回 {passed, failed, messages, expected_errors}。
func run() -> Dictionary:
	run_tests()
	return {"passed": _passed, "failed": _failed, "messages": _messages, "expected_errors": _expected_errors}


## 声明接下来的代码会故意触发 n 条引擎错误日志（例如喂给解析器非法输入）。
## run_all.gd 要求实际捕获到的错误数与声明的总数**完全相等**，多了少了都算失败。
func expect_errors(n: int) -> void:
	_expected_errors += n


func ok(label: String, cond: bool) -> void:
	if cond:
		_passed += 1
	else:
		_failed += 1
		_messages.append("失败 %s" % label)


func near(label: String, actual: float, expected: float, tol: float) -> void:
	if absf(actual - expected) <= tol:
		_passed += 1
	else:
		_failed += 1
		_messages.append("失败 %s：实际 %.15f，期望 %.15f，允许误差 %e" % [label, actual, expected, tol])
