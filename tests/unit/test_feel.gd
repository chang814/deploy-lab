extends "res://tests/test_case.gd"
## 换弹动作、合成音效、命中反馈的测试（表现层，不依赖物理世界）。


func run_tests() -> void:
	_test_reload_poses()
	_test_sfx()
	_test_target_reaction()
	_test_model_parts()


func _test_reload_poses() -> void:
	for id: String in ["rifle", "pistol"]:
		var start: Dictionary = WeaponController.reload_pose(0.0, id)
		var finish: Dictionary = WeaponController.reload_pose(1.0, id)
		for key: String in ["mag", "arm", "bolt"]:
			ok("%s 换弹开始时 %s 在原位" % [id, key], (start[key] as Vector3).is_zero_approx())
			ok("%s 换弹结束时 %s 回到原位" % [id, key], (finish[key] as Vector3).is_zero_approx())
		ok("%s 换弹结束时枪回到原位" % id, (finish["gun"][0] as Vector3).is_zero_approx() and (finish["gun"][1] as Vector3).is_zero_approx())
	ok("步枪弹匣中途掉出画面", (WeaponController.reload_pose(0.33, "rifle")["mag"] as Vector3).y < -0.3)
	ok("步枪左手中途去拿弹匣", (WeaponController.reload_pose(0.3, "rifle")["arm"] as Vector3).length() > 0.1)
	ok("步枪后段拉枪栓（向后）", (WeaponController.reload_pose(0.78, "rifle")["bolt"] as Vector3).z > 0.05)
	ok("手枪弹匣中途掉出", (WeaponController.reload_pose(0.33, "pistol")["mag"] as Vector3).y < -0.2)


func _test_sfx() -> void:
	for kind: String in ["rifle", "pistol", "hit", "swish", "mag_out", "mag_in", "bolt"]:
		var w: AudioStreamWAV = Sfx.get_stream(kind)
		ok("音效 %s 已合成" % kind, w != null and w.data.size() > 1000 and w.format == AudioStreamWAV.FORMAT_16_BITS)
	ok("同一种音效只合成一次（缓存）", Sfx.get_stream("rifle") == Sfx.get_stream("rifle"))
	ok("步枪声比手枪声长", Sfx.get_stream("rifle").data.size() > Sfx.get_stream("pistol").data.size())


func _test_target_reaction() -> void:
	var t: Target = Target.new()
	var mesh: MeshInstance3D = MeshInstance3D.new()
	mesh.name = "Mesh"
	t.add_child(mesh)
	t._ready()
	t.on_hit(Vector3(0, 0, -1))
	ok("命中计数", t.hit_count == 1)
	t._physics_process(1.0 / 64.0)
	t._physics_process(1.0 / 64.0)
	ok("命中后靶子倾斜", absf(t._tilt_deg) > 1.0)
	for i: int in 400:
		t._physics_process(1.0 / 64.0)
	ok("一段时间后回正", absf(t._tilt_deg) < 0.5)
	t.on_hit()
	ok("不带方向也能命中（兼容）", t.hit_count == 2)
	t.free()


func _test_model_parts() -> void:
	var ak: Node3D = Viewmodels.build("rifle")
	for n: String in ["Mag", "Bolt", "LeftArm", "Muzzle"]:
		ok("步枪模型有 %s" % n, ak.get_node_or_null(n) != null)
	ok("弹匣记录了原位", ak.get_node("Mag").has_meta("rest_position"))
	ak.free()
	var pistol: Node3D = Viewmodels.build("pistol")
	for n: String in ["Mag", "Slide", "LeftArm"]:
		ok("手枪模型有 %s" % n, pistol.get_node_or_null(n) != null)
	pistol.free()
