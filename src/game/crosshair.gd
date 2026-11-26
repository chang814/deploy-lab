extends Control
## 屏幕中心十字准星（v0.1 的固定样式；之后可做成可配置）。

const COLOR: Color = Color(0.3, 1.0, 0.3, 0.95)
const LENGTH_PX: float = 6.0
const GAP_PX: float = 3.0
const THICKNESS_PX: float = 2.0
const PAUSE_LINES: PackedStringArray = ["PAUSED", "Click to resume", "Press Esc again to quit"]


func _ready() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	resized.connect(queue_redraw)


func _draw() -> void:
	var c: Vector2 = size / 2.0
	for dir: Vector2 in [Vector2.RIGHT, Vector2.LEFT, Vector2.UP, Vector2.DOWN]:
		draw_line(c + dir * GAP_PX, c + dir * (GAP_PX + LENGTH_PX), COLOR, THICKNESS_PX)
	# 命中标记：命中后在准星周围显示一个短暂的 X
	var wc: WeaponController = get_tree().current_scene.get_node_or_null("Player/Look/Camera3D/Weapons") as WeaponController if is_inside_tree() else null
	if wc != null and wc.hit_marker_left_s > 0.0:
		var a: float = clampf(wc.hit_marker_left_s / 0.15, 0.0, 1.0)
		for d: Vector2 in [Vector2(1, 1), Vector2(-1, 1), Vector2(1, -1), Vector2(-1, -1)]:
			draw_line(c + d.normalized() * 7.0, c + d.normalized() * 15.0, Color(1, 1, 1, a), 2.0)
	# 左下角显示朝向（用于「转一圈要移动多少厘米」的对比测试）
	var look: FpsLook = get_tree().current_scene.get_node_or_null("Player/Look") as FpsLook if is_inside_tree() else null
	if look != null and not look.captured:
		# 暂停提示
		draw_rect(Rect2(Vector2.ZERO, size), Color(0, 0, 0, 0.45))
		var font: Font = get_theme_default_font()
		for i: int in PAUSE_LINES.size():
			var fs: int = 40 if i == 0 else 22
			var w: float = font.get_string_size(PAUSE_LINES[i], HORIZONTAL_ALIGNMENT_LEFT, -1.0, fs).x
			draw_string(font, Vector2((size.x - w) / 2.0, size.y / 2.0 - 30.0 + i * 44.0), PAUSE_LINES[i],
				HORIZONTAL_ALIGNMENT_LEFT, -1.0, fs, Color(1, 1, 1, 0.95))
	if look != null:
		var text: String = "yaw %.1f°  pitch %.1f°  sens %s (%s)" % [
			fposmod(look.yaw_deg, 360.0), look.pitch_deg,
			str(look.settings.sensitivity) if look.settings != null else "?",
			"CS2" if look.settings != null and look.settings.source == "CS2" else "file"]
		text += "   %d fps" % Engine.get_frames_per_second()
		draw_string(get_theme_default_font(), Vector2(12.0, size.y - 14.0), text,
			HORIZONTAL_ALIGNMENT_LEFT, -1.0, 16, Color(1, 1, 1, 0.8))


	var weapons: WeaponController = get_tree().current_scene.get_node_or_null("Player/Look/Camera3D/Weapons") as WeaponController if is_inside_tree() else null
	if weapons != null and weapons.cfg != null:
		var st: WeaponState = weapons.state
		var w: Dictionary = st.weapons[st.current]
		var ammo_text: String = "%d / inf" % st.ammo[st.current] if int(w["magazine"]) > 0 else "-"
		var status: String = ["DRAWING", "", "RELOADING"][st.state]
		var line1: String = "%s  %s  %s" % [w["name"], ammo_text, status]
		var line2: String = "hits %d / shots %d" % [weapons.hits, weapons.shots]
		var font: Font = get_theme_default_font()
		for i: int in 2:
			var t: String = [line1, line2][i]
			var fs: int = 26 if i == 0 else 16
			var tw: float = font.get_string_size(t, HORIZONTAL_ALIGNMENT_LEFT, -1.0, fs).x
			draw_string(font, Vector2(size.x - tw - 16.0, size.y - 46.0 + i * 26.0), t,
				HORIZONTAL_ALIGNMENT_LEFT, -1.0, fs, Color(1, 1, 1, 0.9))


func _process(_delta_s: float) -> void:
	queue_redraw()
