extends Control
## 屏幕中心十字准星（v0.1 的固定样式；之后可做成可配置）。

const COLOR: Color = Color(0.3, 1.0, 0.3, 0.95)
const LENGTH_PX: float = 6.0
const GAP_PX: float = 3.0
const THICKNESS_PX: float = 2.0


func _ready() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	resized.connect(queue_redraw)


func _draw() -> void:
	var c: Vector2 = size / 2.0
	for dir: Vector2 in [Vector2.RIGHT, Vector2.LEFT, Vector2.UP, Vector2.DOWN]:
		draw_line(c + dir * GAP_PX, c + dir * (GAP_PX + LENGTH_PX), COLOR, THICKNESS_PX)
	# 左下角显示朝向（用于「转一圈要移动多少厘米」的对比测试）
	var look: FpsLook = get_tree().current_scene.get_node_or_null("Player") as FpsLook if is_inside_tree() else null
	if look != null:
		var text: String = "yaw %.1f°  pitch %.1f°  sens %s" % [
			fposmod(look.yaw_deg, 360.0), look.pitch_deg,
			str(look.settings.sensitivity) if look.settings != null else "?"]
		draw_string(get_theme_default_font(), Vector2(12.0, size.y - 14.0), text,
			HORIZONTAL_ALIGNMENT_LEFT, -1.0, 16, Color(1, 1, 1, 0.8))


func _process(_delta: float) -> void:
	queue_redraw()
