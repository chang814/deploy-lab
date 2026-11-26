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
