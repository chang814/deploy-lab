class_name Viewmodels
extends RefCounted
## 第一人称武器模型（原创灰盒造型，用基本形状拼成；不使用任何游戏的素材）。
## 坐标：相机空间，-Z 向前、+X 向右、+Y 向上；返回的 Node3D 原点即握把位置，枪口在 muzzle 子节点。

const METAL: Color = Color(0.16, 0.17, 0.19)
const DARK: Color = Color(0.09, 0.09, 0.10)
const WOOD: Color = Color(0.45, 0.27, 0.13)
const BLADE: Color = Color(0.78, 0.8, 0.83)
const AK_WOOD: Color = Color(0.55, 0.27, 0.1)      # 上漆的桦木 / 胡桃木色
const BAKELITE: Color = Color(0.32, 0.12, 0.06)    # 胶木（深红棕）
const GLOVE: Color = Color(0.17, 0.18, 0.15)       # 战术手套
const SLEEVE: Color = Color(0.27, 0.3, 0.24)       # 袖子


## 手 + 前臂：hand_pos 为手掌中心，前臂从手腕向「下后方」伸出画面（arm_rot_deg 为前臂方向的欧拉角，度）。
## 返回整只手臂的节点（原点在手掌中心），换弹时可以整体移动。
static func _arm(parent: Node3D, hand_pos: Vector3, hand_size: Vector3, arm_rot_deg: Vector3, node_name: String = "") -> Node3D:
	var glove: StandardMaterial3D = _mat(GLOVE, 0.0, 0.85)
	var sleeve: StandardMaterial3D = _mat(SLEEVE, 0.0, 0.9)
	var group: Node3D = Node3D.new()
	if not node_name.is_empty():
		group.name = node_name
	group.position = hand_pos
	parent.add_child(group)
	_box(group, hand_size, Vector3.ZERO, glove)
	var arm: Node3D = Node3D.new()
	arm.rotation_degrees = arm_rot_deg
	group.add_child(arm)
	_box(arm, Vector3(0.05, 0.05, 0.09), Vector3(0, 0, 0.07), glove)       # 手腕 / 护腕
	_box(arm, Vector3(0.07, 0.07, 0.4), Vector3(0, 0, 0.31), sleeve)      # 前臂（袖子）
	return group


## 可单独移动的部件组（弹匣、枪栓等）：原点在 pos，子部件用相对坐标。
static func _part(parent: Node3D, node_name: String, pos: Vector3) -> Node3D:
	var g: Node3D = Node3D.new()
	g.name = node_name
	g.position = pos
	g.set_meta("rest_position", pos)
	parent.add_child(g)
	return g


static func _mat(c: Color, metallic: float = 0.6, rough: float = 0.45) -> StandardMaterial3D:
	var m: StandardMaterial3D = StandardMaterial3D.new()
	m.albedo_color = c
	m.metallic = metallic
	m.roughness = rough
	return m


static func _box(parent: Node3D, size: Vector3, pos: Vector3, mat: Material, rot_deg: Vector3 = Vector3.ZERO) -> MeshInstance3D:
	var mi: MeshInstance3D = MeshInstance3D.new()
	var mesh: BoxMesh = BoxMesh.new()
	mesh.size = size
	mi.mesh = mesh
	mi.position = pos
	mi.rotation_degrees = rot_deg
	mi.material_override = mat
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	parent.add_child(mi)
	return mi


static func _cyl(parent: Node3D, radius: float, length: float, pos: Vector3, mat: Material) -> MeshInstance3D:
	var mi: MeshInstance3D = MeshInstance3D.new()
	var mesh: CylinderMesh = CylinderMesh.new()
	mesh.top_radius = radius
	mesh.bottom_radius = radius
	mesh.height = length
	mi.mesh = mesh
	mi.position = pos
	mi.rotation_degrees = Vector3(90, 0, 0)   # 沿 Z 轴
	mi.material_override = mat
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	parent.add_child(mi)
	return mi


## 把 xy 平面上的轮廓挤出成厚度为 depth 的薄片：轮廓 x 轴对齐武器的前方（-Z），y 轴向上，厚度沿 X 居中。
static func _prism(parent: Node3D, outline: PackedVector2Array, depth: float, mat: Material) -> void:
	var p: CSGPolygon3D = CSGPolygon3D.new()
	p.polygon = outline
	p.depth = depth
	p.material = mat
	p.rotation_degrees = Vector3(0, 90, 0)   # 轮廓 x → -Z（前方），挤出方向 → X
	p.position = Vector3(depth / 2.0, 0, 0)  # 厚度居中
	parent.add_child(p)


static func _muzzle(parent: Node3D, pos: Vector3) -> void:
	var m: Marker3D = Marker3D.new()
	m.name = "Muzzle"
	m.position = pos
	parent.add_child(m)


static func build(id: String) -> Node3D:
	var root: Node3D = Node3D.new()
	root.name = id
	var metal: StandardMaterial3D = _mat(METAL)
	var dark: StandardMaterial3D = _mat(DARK, 0.3, 0.7)
	match id:
		"rifle":
			# AK-47 造型：按现实枪械的结构特征用基本形状自建（不使用任何游戏模型）。
			# 冲压机匣 + 防尘盖、上下木护木、导气管与导气箍、斜切枪口、前准星、表尺座、向前弯的弹匣、胶木握把、木枪托
			var wood: StandardMaterial3D = _mat(AK_WOOD, 0.0, 0.55)
			var bakelite: StandardMaterial3D = _mat(BAKELITE, 0.0, 0.6)
			_box(root, Vector3(0.046, 0.058, 0.30), Vector3(0, 0.028, -0.10), metal)             # 机匣
			_box(root, Vector3(0.042, 0.02, 0.27), Vector3(0, 0.066, -0.09), dark)               # 防尘盖
			var bolt: Node3D = _part(root, "Bolt", Vector3(0.026, 0.04, -0.13))
			_box(bolt, Vector3(0.012, 0.016, 0.03), Vector3.ZERO, dark)                          # 拉机柄
			_box(root, Vector3(0.034, 0.026, 0.045), Vector3(0, 0.072, -0.27), metal)            # 表尺座
			_box(root, Vector3(0.052, 0.046, 0.17), Vector3(0, 0.026, -0.335), wood)             # 下护木
			_box(root, Vector3(0.038, 0.026, 0.14), Vector3(0, 0.066, -0.33), wood)              # 上护木
			_cyl(root, 0.011, 0.13, Vector3(0, 0.068, -0.465), metal)                            # 导气管
			_box(root, Vector3(0.03, 0.045, 0.03), Vector3(0, 0.055, -0.545), dark)              # 导气箍
			_cyl(root, 0.0105, 0.29, Vector3(0, 0.036, -0.56), dark)                             # 枪管
			_box(root, Vector3(0.012, 0.05, 0.02), Vector3(0, 0.07, -0.675), dark)               # 前准星座
			_cyl(root, 0.014, 0.05, Vector3(0, 0.036, -0.725), dark)                             # 斜切枪口
			var mag: Node3D = _part(root, "Mag", Vector3(0, -0.005, -0.19))
			_box(mag, Vector3(0.036, 0.10, 0.065), Vector3(0, -0.04, 0.0), dark, Vector3(8, 0, 0))         # 弹匣上段
			_box(mag, Vector3(0.034, 0.10, 0.06), Vector3(0, -0.12, -0.035), dark, Vector3(30, 0, 0))      # 弹匣下段（向前弯）
			_box(root, Vector3(0.008, 0.008, 0.07), Vector3(0, -0.012, -0.06), dark)             # 扳机护圈
			_box(root, Vector3(0.03, 0.09, 0.038), Vector3(0, -0.045, 0.0), bakelite, Vector3(-18, 0, 0))  # 握把
			_box(root, Vector3(0.04, 0.062, 0.22), Vector3(0, -0.012, 0.15), wood, Vector3(-7, 0, 0))       # 枪托（向后下倾）
			_muzzle(root, Vector3(0, 0.036, -0.755))
			_arm(root, Vector3(0.004, -0.045, 0.01), Vector3(0.05, 0.075, 0.065), Vector3(28, 8, 0))     # 右手握把
			_arm(root, Vector3(-0.004, -0.012, -0.33), Vector3(0.06, 0.05, 0.08), Vector3(22, -38, 0), "LeftArm").set_meta("rest_position", Vector3(-0.004, -0.012, -0.33))  # 左手托护木
		"pistol":
			var slide: Node3D = _part(root, "Slide", Vector3(0, 0.04, -0.07))
			_box(slide, Vector3(0.035, 0.045, 0.19), Vector3.ZERO, metal)                    # 套筒
			var pmag: Node3D = _part(root, "Mag", Vector3(0, -0.05, 0.0))
			_box(pmag, Vector3(0.026, 0.1, 0.035), Vector3.ZERO, dark, Vector3(14, 0, 0))     # 弹匣（藏在握把里，底板露出）
			_box(pmag, Vector3(0.032, 0.012, 0.045), Vector3(0.0, -0.056, 0.014), metal)      # 弹匣底板
			_box(root, Vector3(0.032, 0.03, 0.15), Vector3(0, 0.005, -0.05), dark)           # 枪身
			_box(root, Vector3(0.03, 0.11, 0.045), Vector3(0, -0.05, 0.0), dark, Vector3(14, 0, 0))  # 握把
			_muzzle(root, Vector3(0, 0.04, -0.17))
			_arm(root, Vector3(0.002, -0.045, 0.005), Vector3(0.05, 0.075, 0.06), Vector3(26, 6, 0))     # 右手握把
			_arm(root, Vector3(-0.03, -0.06, 0.02), Vector3(0.045, 0.06, 0.06), Vector3(24, -30, 0), "LeftArm").set_meta("rest_position", Vector3(-0.03, -0.06, 0.02))     # 左手托底
		"knife":
			# 战术直刀（原创造型）：用 2D 轮廓挤出成形。轮廓坐标 (x = 沿刀身向前, y = 向上)，单位米；
			# 刀刃在下（-Y）、刀背在上；刃口带弧度上挑到刀尖，刀背前段斜切（clip point）
			var steel: StandardMaterial3D = _mat(BLADE, 0.95, 0.18)
			var bevel: StandardMaterial3D = _mat(Color(0.9, 0.92, 0.95), 1.0, 0.08)
			var grip: StandardMaterial3D = _mat(Color(0.12, 0.13, 0.12), 0.0, 0.9)
			_prism(root, PackedVector2Array([          # 刀身
				Vector2(0.0, 0.016), Vector2(0.135, 0.016), Vector2(0.205, 0.003), Vector2(0.19, -0.004),
				Vector2(0.165, -0.012), Vector2(0.12, -0.0165), Vector2(0.0, -0.0165)]), 0.0035, steel)
			_prism(root, PackedVector2Array([          # 开刃磨面（沿刃口的一条亮带）
				Vector2(0.008, -0.009), Vector2(0.12, -0.009), Vector2(0.162, -0.005), Vector2(0.19, 0.0),
				Vector2(0.19, -0.004), Vector2(0.165, -0.012), Vector2(0.12, -0.0165), Vector2(0.008, -0.0165)]), 0.0042, bevel)
			_prism(root, PackedVector2Array([          # 护手
				Vector2(-0.006, 0.024), Vector2(0.004, 0.024), Vector2(0.004, -0.028), Vector2(-0.006, -0.028)]), 0.02, metal)
			_prism(root, PackedVector2Array([          # 刀柄（带指凹）
				Vector2(-0.006, 0.015), Vector2(-0.11, 0.013), Vector2(-0.12, 0.004), Vector2(-0.115, -0.014),
				Vector2(-0.09, -0.016), Vector2(-0.075, -0.012), Vector2(-0.06, -0.017), Vector2(-0.045, -0.013),
				Vector2(-0.03, -0.018), Vector2(-0.006, -0.017)]), 0.022, grip)
			_muzzle(root, Vector3(0, 0.003, -0.205))
			_arm(root, Vector3(0, 0.0, 0.05), Vector3(0.048, 0.056, 0.085), Vector3(30, 5, 0))       # 右手握刀柄
	return root
