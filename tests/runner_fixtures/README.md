# 测试入口的故障样例

每个子目录都是一种**应该让 tests/run_all.gd 返回失败**的情况，CI 会逐个用 `-- --unit-dir=res://tests/runner_fixtures/<目录>` 运行并要求退出码非 0。正常测试只在 `tests/unit` 中发现，不会扫描这里。
