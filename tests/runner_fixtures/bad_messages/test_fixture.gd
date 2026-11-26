extends RefCounted
## messages 里有非字符串元素：必须判为失败，而不是在汇总时崩溃
func run() -> Dictionary:
	return {"passed": 1, "failed": 0, "messages": [{}]}
