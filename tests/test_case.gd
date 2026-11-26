extends RefCounted
## 单元测试基类（ADR 0002 §5）。每个 tests/unit/test_*.gd 继承它并实现 run_tests()。
## 不要在测试里调用 quit()，由 tests/run_all.gd 统一汇总。

var _passed: int = 0
var _failed: int = 0
var _messages: PackedStringArray = []
var _expected_errors: PackedStringArray = []


## 子类实现：在这里调用各个测试函数。
func run_tests() -> void:
	pass


## 由 run_all.gd 调用，返回 {passed, failed, messages, expected_errors}。
func run() -> Dictionary:
	run_tests()
	return {"passed": _passed, "failed": _failed, "messages": _messages, "expected_errors": _expected_errors}


## 声明接下来的代码会故意触发一条**引擎**错误日志，内容包含 substring（例如解析器对非法输入的报错）。
## run_all.gd 的规则：
## - 每条声明必须恰好匹配一条实际错误，多了少了都算失败
## - 只能匹配引擎错误；GDScript 运行时错误（数组越界、空引用等）永远不能被声明掉
func expect_error(substring: String) -> void:
	_expected_errors.append(substring)


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
		_messages.append("失败 %s：实际 %.15f，期望 %.15f，允许误差 %s" % [label, actual, expected, str(tol)])  # GDScript 不支持 %e
