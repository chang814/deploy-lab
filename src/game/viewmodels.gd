class_name Viewmodels
extends RefCounted
## 第一人称武器模型（原创灰盒造型，用基本形状拼成；不使用任何游戏的素材）。
## 坐标：相机空间，-Z 向前、+X 向右、+Y 向上；返回的 Node3D 原点即握把位置，枪口在 muzzle 子节点。

const METAL: Color = Color(0.16, 0.17, 0.19)
const DARK: Color = Color(0.09, 0.09, 0.10)
const WOOD: Color = Color(0.45, 0.27, 0.13)
const BLADE: Color = Color(0.78, 0.8, 0.83)


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
			_box(root, Vector3(0.05, 0.07, 0.42), Vector3(0, 0.03, -0.12), metal)            # 机匣
			_cyl(root, 0.012, 0.36, Vector3(0, 0.045, -0.5), dark)                           # 枪管
			_box(root, Vector3(0.055, 0.05, 0.2), Vector3(0, 0.02, -0.38), _mat(WOOD, 0.0, 0.8))   # 护木
			_box(root, Vector3(0.04, 0.16, 0.06), Vector3(0, -0.07, -0.16), dark, Vector3(-18, 0, 0))  # 弯弹匣
			_box(root, Vector3(0.035, 0.1, 0.04), Vector3(0, -0.04, 0.02), dark, Vector3(15, 0, 0))   # 握把
			_box(root, Vector3(0.045, 0.06, 0.24), Vector3(0, 0.0, 0.2), _mat(WOOD, 0.0, 0.8))     # 枪托
			_box(root, Vector3(0.01, 0.03, 0.01), Vector3(0, 0.075, -0.62), dark)            # 准星
			_muzzle(root, Vector3(0, 0.045, -0.69))
		"pistol":
			_box(root, Vector3(0.035, 0.045, 0.19), Vector3(0, 0.04, -0.07), metal)          # 套筒
			_box(root, Vector3(0.032, 0.03, 0.15), Vector3(0, 0.005, -0.05), dark)           # 枪身
			_box(root, Vector3(0.03, 0.11, 0.045), Vector3(0, -0.05, 0.0), dark, Vector3(14, 0, 0))  # 握把
			_muzzle(root, Vector3(0, 0.04, -0.17))
		"knife":
			_box(root, Vector3(0.006, 0.035, 0.2), Vector3(0, 0.01, -0.15), _mat(BLADE, 0.9, 0.2))  # 刀身
			_box(root, Vector3(0.03, 0.012, 0.015), Vector3(0, 0.01, -0.045), metal)         # 护手
			_box(root, Vector3(0.022, 0.03, 0.11), Vector3(0, 0.005, 0.02), dark)            # 刀柄
			_muzzle(root, Vector3(0, 0.01, -0.25))
	return root
