extends "res://tests/test_case.gd"
## 声明预期 2 条错误，实际只触发 1 条：必须判为失败
func run_tests() -> void:
	expect_errors(2)
	ok("前置", true)
	push_error("故意触发的一条错误")
