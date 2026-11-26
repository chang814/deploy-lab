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
			_box(root, Vector3(0.012, 0.016, 0.03), Vector3(0.026, 0.04, -0.13), dark)           # 拉机柄
			_box(root, Vector3(0.034, 0.026, 0.045), Vector3(0, 0.072, -0.27), metal)            # 表尺座
			_box(root, Vector3(0.052, 0.046, 0.17), Vector3(0, 0.026, -0.335), wood)             # 下护木
			_box(root, Vector3(0.038, 0.026, 0.14), Vector3(0, 0.066, -0.33), wood)              # 上护木
			_cyl(root, 0.011, 0.13, Vector3(0, 0.068, -0.465), metal)                            # 导气管
			_box(root, Vector3(0.03, 0.045, 0.03), Vector3(0, 0.055, -0.545), dark)              # 导气箍
			_cyl(root, 0.0105, 0.29, Vector3(0, 0.036, -0.56), dark)                             # 枪管
			_box(root, Vector3(0.012, 0.05, 0.02), Vector3(0, 0.07, -0.675), dark)               # 前准星座
			_cyl(root, 0.014, 0.05, Vector3(0, 0.036, -0.725), dark)                             # 斜切枪口
			_box(root, Vector3(0.036, 0.10, 0.065), Vector3(0, -0.045, -0.19), dark, Vector3(8, 0, 0))     # 弹匣上段
			_box(root, Vector3(0.034, 0.10, 0.06), Vector3(0, -0.125, -0.225), dark, Vector3(30, 0, 0))    # 弹匣下段（向前弯）
			_box(root, Vector3(0.008, 0.008, 0.07), Vector3(0, -0.012, -0.06), dark)             # 扳机护圈
			_box(root, Vector3(0.03, 0.09, 0.038), Vector3(0, -0.045, 0.0), bakelite, Vector3(-18, 0, 0))  # 握把
			_box(root, Vector3(0.04, 0.062, 0.22), Vector3(0, -0.012, 0.15), wood, Vector3(-7, 0, 0))       # 枪托（向后下倾）
			_muzzle(root, Vector3(0, 0.036, -0.755))
		"pistol":
			_box(root, Vector3(0.035, 0.045, 0.19), Vector3(0, 0.04, -0.07), metal)          # 套筒
			_box(root, Vector3(0.032, 0.03, 0.15), Vector3(0, 0.005, -0.05), dark)           # 枪身
			_box(root, Vector3(0.03, 0.11, 0.045), Vector3(0, -0.05, 0.0), dark, Vector3(14, 0, 0))  # 握把
			_muzzle(root, Vector3(0, 0.04, -0.17))
		"knife":
			# 战术直刀：刀刃在下（-Y），刀背在上；刀尖用两段斜切的薄片收窄
			var steel: StandardMaterial3D = _mat(BLADE, 0.9, 0.2)
			_box(root, Vector3(0.005, 0.034, 0.15), Vector3(0, 0.012, -0.125), steel)                    # 刀身
			_box(root, Vector3(0.005, 0.026, 0.05), Vector3(0, 0.006, -0.212), steel, Vector3(-16, 0, 0))  # 刀尖下斜（刃口上挑）
			_box(root, Vector3(0.005, 0.014, 0.04), Vector3(0, 0.022, -0.222), steel, Vector3(14, 0, 0))   # 刀尖上斜（假刃）
			_box(root, Vector3(0.0055, 0.004, 0.12), Vector3(0, 0.02, -0.12), _mat(DARK, 0.6, 0.4))        # 血槽
			_box(root, Vector3(0.036, 0.016, 0.012), Vector3(0, 0.01, -0.046), metal)                     # 护手
			_box(root, Vector3(0.024, 0.032, 0.1), Vector3(0, 0.006, 0.01), dark)                         # 刀柄
			_box(root, Vector3(0.026, 0.026, 0.014), Vector3(0, 0.006, 0.066), metal)                     # 柄尾
			_muzzle(root, Vector3(0, 0.01, -0.24))
	return root
