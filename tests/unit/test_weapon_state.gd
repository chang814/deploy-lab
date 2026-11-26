extends "res://tests/test_case.gd"
## WeaponState（切枪 / 开火 / 换弹）与 WeaponConfig 的测试。

const RATE_HZ: float = 64.0


func run_tests() -> void:
	_test_config()
	_test_draw_timing()
	_test_switch_rules()
	_test_wheel()
	_test_fire_modes()
	_test_ammo_and_reload()
	_test_knife()
	_test_knife_animation_poses()
	_test_scene_wiring()


func _make(start: String = "rifle") -> WeaponState:
	var c: WeaponConfig = WeaponConfig.load_file()
	var s: WeaponState = WeaponState.new()
	s.setup(c.weapons, c.tick_rate_hz, start)
	return s


## 推进到开出第一枪，返回用了多少 tick（扳机一直按着）；超过 limit 返回 -1。
func _ticks_to_shot(s: WeaponState, limit: int = 1000) -> int:
	for i: int in range(1, limit + 1):
		if s.tick(true):
			return i
	return -1


func _test_config() -> void:
	var c: WeaponConfig = WeaponConfig.load_file()
	ok("data/weapons/weapons.json 有效（%s）" % c.error, c.is_valid())
	near("64 tick", c.tick_rate_hz, 64.0, 0.0)
	ok("三把武器", c.weapons.size() == 3)
	ok("文件不存在无效", not WeaponConfig.load_file("res://data/weapons/不存在.json").is_valid())
	ok("空数组无效", not WeaponConfig.from_json_text('{"tick_rate_hz": 64, "weapons": []}').is_valid())
	var dup: Dictionary = {"tick_rate_hz": 64, "weapons": [c.weapons[0], c.weapons[0]]}
	ok("重复 id 无效", not WeaponConfig.from_json_text(JSON.stringify(dup)).is_valid())
	var bad: Dictionary = (c.weapons[0] as Dictionary).duplicate()
	bad["fire_interval_s"] = 0
	ok("射击间隔为 0 无效", not WeaponConfig.from_json_text(JSON.stringify({"tick_rate_hz": 64, "weapons": [bad]})).is_valid())
	bad = (c.weapons[0] as Dictionary).duplicate()
	bad["automatic"] = "yes"
	ok("automatic 不是布尔无效", not WeaponConfig.from_json_text(JSON.stringify({"tick_rate_hz": 64, "weapons": [bad]})).is_valid())
	ok("缺 viewmodel 无效", not WeaponConfig.from_json_text(JSON.stringify({"tick_rate_hz": 64, "weapons": c.weapons})).is_valid())
	ok("viewmodel 参数已读入", c.viewmodel.has("kick_m") and c.viewmodel["draw_drop_m"] > 0.0)


func _test_draw_timing() -> void:
	# 切枪在处理它的那个 tick 开始拔出，1.000 s = 64 tick 之后的那个 tick 第一次能开火
	var s: WeaponState = _make("knife")
	s.request_slot(1)
	var n: int = _ticks_to_shot(s)
	ok("切到步枪后第 65 个 tick 开出第一枪（切枪 tick + 64 tick 拔出），实际 %d" % n, n == 65)
	ok("开火时已处于就绪", s.is_ready())
	# 拔出中不能开火
	s = _make("knife")
	s.request_slot(2)
	var fired_early: bool = false
	for i: int in 64:
		fired_early = fired_early or s.tick(true)
	ok("拔出的 64 个 tick 内不开火", not fired_early)
	ok("拔出中状态为 DRAWING", s.state == WeaponState.State.DRAWING)


func _test_switch_rules() -> void:
	var s: WeaponState = _make("rifle")
	s.request_slot(1)
	s.tick(false)
	ok("切到手里这把：不重新拔出", s.is_ready() and s.current == "rifle")
	s.request_slot(2)
	s.tick(false)
	ok("切到手枪", s.current == "pistol" and s.previous == "rifle")
	# 拔出中被打断：切到刀，重新计时
	for i: int in 30:
		s.tick(false)
	s.request_slot(3)
	var n: int = _ticks_to_shot(s)
	ok("拔出中切刀会重新计时（刀第 65 个 tick 可攻击），实际 %d" % n, n == 65)
	# Q：回到上一把（手枪）
	s.request_quick_switch()
	s.tick(false)
	ok("Q 回到上一把", s.current == "pistol" and s.previous == "knife")
	s.request_quick_switch()
	s.tick(false)
	ok("再按 Q 回来", s.current == "knife" and s.previous == "pistol")
	# 没有上一把时 Q 无效
	var fresh: WeaponState = _make("rifle")
	fresh.request_quick_switch()
	fresh.tick(false)
	ok("没有上一把时 Q 无效", fresh.current == "rifle" and fresh.is_ready())


func _test_wheel() -> void:
	var s: WeaponState = _make("rifle")
	s.request_wheel(1)
	s.tick(false)
	ok("滚轮向下：步枪 → 手枪", s.current == "pistol")
	s.request_wheel(1)
	s.tick(false)
	ok("滚轮向下：手枪 → 刀", s.current == "knife")
	s.request_wheel(1)
	s.tick(false)
	ok("滚轮向下循环：刀 → 步枪", s.current == "rifle")
	s.request_wheel(-1)
	s.tick(false)
	ok("滚轮向上：步枪 → 刀", s.current == "knife")
	# 同一个 tick 内滚两格：跳过一把
	s.request_wheel(1)
	s.request_wheel(1)
	s.tick(false)
	ok("一个 tick 内滚两格：刀 → 手枪", s.current == "pistol")


func _test_fire_modes() -> void:
	# 步枪自动：0.1 s 间隔按计划时刻累计。第 1 发在 tick 1（1/64 s），第 n 发计划在 1/64 + 0.1n 秒，
	# 落到其后第一个 tick：8、14、21、27、33（若从实际开火时刻累计会漂移成 8、15、22、29）
	var s: WeaponState = _make("rifle")
	var fired_at: Array[int] = []
	for i: int in range(1, 34):
		if s.tick(true):
			fired_at.append(i)
	ok("步枪连发节奏：%s" % str(fired_at), fired_at == [1, 8, 14, 21, 27, 33])
	# 1 秒（64 tick）内正好 10 发 = 600 发 / 分钟
	var r: WeaponState = _make("rifle")
	var in_one_s: int = 0
	for i: int in 64:
		if r.tick(true):
			in_one_s += 1
	ok("1 秒 10 发（600 发/分），实际 %d" % in_one_s, in_one_s == 10)
	# 手枪半自动：按住只开一枪，松开再按才开下一枪
	var p: WeaponState = _make("pistol")
	var count: int = 0
	for i: int in 64:
		if p.tick(true):
			count += 1
	ok("手枪按住只开一枪", count == 1)
	p.tick(false)
	var again: bool = false
	for i: int in 20:
		again = again or p.tick(true)
	ok("松开再按开第二枪", again)


func _test_ammo_and_reload() -> void:
	var s: WeaponState = _make("rifle")
	var shots: int = 0
	for i: int in 400:
		if s.tick(true):
			shots += 1
		if s.state == WeaponState.State.RELOADING:
			break
	ok("打空 30 发后自动换弹", shots == 30 and s.ammo["rifle"] == 0)
	var ticks: int = 0
	while s.state == WeaponState.State.RELOADING and ticks < 1000:
		s.tick(false)
		ticks += 1
	ok("换弹约 2.5 s（160 tick），实际 %d" % ticks, ticks == 160)
	ok("换弹后弹匣满", s.ammo["rifle"] == 30)
	# R 手动换弹；切枪打断换弹，弹匣不补
	s.tick(true)
	s.tick(false)
	s.request_reload()
	s.tick(false)
	ok("R 开始换弹", s.state == WeaponState.State.RELOADING)
	s.request_slot(2)
	s.tick(false)
	ok("切枪打断换弹", s.current == "pistol" and s.ammo["rifle"] == 29)
	# 弹匣满时 R 无效
	var full: WeaponState = _make("pistol")
	full.request_reload()
	full.tick(false)
	ok("弹匣满时 R 无效", full.is_ready())


func _test_knife() -> void:
	var s: WeaponState = _make("knife")
	var count: int = 0
	for i: int in 64:
		if s.tick(true):
			count += 1
	ok("刀按住每 0.4 s 挥一次（1 s 内 3 次），实际 %d" % count, count == 3)
	ok("刀不消耗弹药", s.ammo["knife"] == 0 and s.is_ready())
	# 右键重击：每 1.0 s 一次，并标记为副攻击
	var h: WeaponState = _make("knife")
	var heavy: Array[int] = []
	for i: int in range(1, 130):
		if h.tick(false, true):
			ok("重击标记为副攻击", h.last_fire_alt)
			heavy.append(i)
	ok("重击每 1.0 s（64 tick）一次：%s" % str(heavy), heavy == [1, 65, 129])
	# 左右键同时按：左键优先
	var both: WeaponState = _make("knife")
	ok("左右键同时按时轻击优先", both.tick(true, true) and not both.last_fire_alt)
	# 枪没有副攻击
	var gun: WeaponState = _make("rifle")
	var gun_alt: bool = false
	for i: int in 64:
		gun_alt = gun_alt or gun.tick(false, true)
	ok("步枪右键不开火", not gun_alt)


func _test_knife_animation_poses() -> void:
	# 轻击 / 重击 / 检视的姿势首尾都回到持刀姿势；轻击左右交替方向相反
	for pose: Array in [WeaponController.slash_pose(0.0, 1.0), WeaponController.slash_pose(1.0, 1.0),
			WeaponController.stab_pose(0.0), WeaponController.stab_pose(1.0)]:
		ok("动作首尾回到原位", (pose[0] as Vector3).is_zero_approx() and (pose[1] as Vector3).is_zero_approx())
	var right: Array = WeaponController.slash_pose(0.2, 1.0)
	var left: Array = WeaponController.slash_pose(0.2, -1.0)
	ok("正手从右上起刀", (right[0] as Vector3).x > 0.0 and (right[0] as Vector3).y > 0.0)
	ok("反手方向相反", is_equal_approx((left[0] as Vector3).x, -(right[0] as Vector3).x))
	var thrust: Array = WeaponController.stab_pose(0.6)
	ok("重击中段向前刺出（-Z）", (thrust[0] as Vector3).z < -0.2)
	var ins_end: Array = WeaponController.inspect_pose(1.0, true)
	ok("刀检视结束位置回到原位", (ins_end[0] as Vector3).is_zero_approx())
	ok("刀检视中途翻面", absf((WeaponController.inspect_pose(0.7, true)[1] as Vector3).z) > 150.0)


func _click(wc: WeaponController, pressed: bool) -> void:
	var mb: InputEventMouseButton = InputEventMouseButton.new()
	mb.button_index = MOUSE_BUTTON_LEFT
	mb.pressed = pressed
	wc._unhandled_input(mb)


func _test_controller_input(wc: WeaponController, root: Node) -> void:
	var look: FpsLook = root.get_node("Player/Look") as FpsLook
	look.captured = true
	# 快速点击：两个 tick 之间按下又松开，下一个 tick 仍然开火
	_click(wc, true)
	_click(wc, false)
	ok("tick 之间的快速点击不会丢", wc.physics_step())
	# 手枪：开一枪后，在同一个 tick 间隔里松开再按下，状态机能看到松开 → 间隔到了就开下一枪
	wc.state.request_slot(2)
	for i: int in 70:
		wc.physics_step()
	_click(wc, true)
	ok("手枪第一枪", wc.physics_step())
	var fired_again: bool = false
	for i: int in 20:
		_click(wc, false)
		_click(wc, true)
		fired_again = fired_again or wc.physics_step()
	ok("手枪快速连点（松开和按下在同一个 tick 间隔里）能继续开火", fired_again)
	# 一直按住手枪不会连发：松开后按住 80 个 tick（1.25 s，射击间隔 0.15 s），只开一枪
	_click(wc, false)
	wc.physics_step()
	_click(wc, true)
	var held_fired: int = 0
	for i: int in 80:
		if wc.physics_step():
			held_fired += 1
	ok("手枪按住只开一枪，实际 %d" % held_fired, held_fired == 1)
	# 暂停时不开火，且暂停前的按下不会留到恢复后
	_click(wc, false)
	look.captured = false
	_click(wc, true)
	ok("暂停时不开火", not wc.physics_step())
	look.captured = true
	ok("恢复后不会补开暂停时的那一下", not wc.physics_step())
	# 检视：就绪时 F 开始，开火打断
	_click(wc, false)
	for i: int in 30:
		wc.physics_step()
	wc.start_inspect()
	ok("就绪时可以检视", wc._inspect_left_s > 0.0)
	_click(wc, true)
	for i: int in 20:
		wc.physics_step()
	ok("开火打断检视", wc._inspect_left_s == 0.0)
	_click(wc, false)
	# 刀：右键重击触发前刺动画
	wc.state.request_slot(3)
	for i: int in 70:
		wc.physics_step()
	var rmb: InputEventMouseButton = InputEventMouseButton.new()
	rmb.button_index = MOUSE_BUTTON_RIGHT
	rmb.pressed = true
	wc._unhandled_input(rmb)
	ok("刀右键重击", wc.physics_step() and wc.state.last_fire_alt)
	ok("重击触发前刺动画", wc._stab_left_s > 0.0 and wc._slash_left_s == 0.0)
	rmb.pressed = false
	wc._unhandled_input(rmb)


func _test_scene_wiring() -> void:
	var root: Node = (load("res://scenes/main.tscn") as PackedScene).instantiate()
	var wc: WeaponController = root.get_node_or_null("Player/Look/Camera3D/Weapons") as WeaponController
	ok("相机下有 WeaponController", wc != null)
	var targets: int = 0
	for n: Node in root.get_node("Range").get_children():
		if n is Target:
			targets += 1
	ok("靶场至少 5 个靶子", targets >= 5)
	ok("物理 tick = 64", int(ProjectSettings.get_setting("physics/common/physics_ticks_per_second")) == 64)
	if wc != null:
		wc.setup(WeaponConfig.load_file())
		ok("开局拿着步枪", wc.state.current == "rifle")
		ok("三把武器都有模型", wc.get_child_count() >= 3)
		_test_controller_input(wc, root)
	root.free()
