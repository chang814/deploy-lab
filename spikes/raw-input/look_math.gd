extends RefCounted
## 视角换算的纯函数，公式见 docs/04-sensitivity-spec.md。
## 单位：角度一律为度（_deg），计数为原始鼠标 count。
## 注意：GDScript 的标量 float 是 64 位，但 Vector2/Vector3 是 32 位，
## 所以需要 float64 精度的累计量一律用标量 float 或 PackedFloat64Array。
## 手感参数（m_yaw、pitch 上下限等）不写在代码里，由 data/look_defaults.json 提供。

const CM_PER_INCH: float = 2.54  # 物理单位换算，不是手感参数
const DEFAULTS_PATH: String = "res://data/look_defaults.json"


## 读取视角参数文件；缺字段或读取失败时返回空字典并报错。
static func load_defaults(path: String = DEFAULTS_PATH) -> Dictionary:
	var text: String = FileAccess.get_file_as_string(path)
	var parsed: Variant = JSON.parse_string(text)
	if typeof(parsed) != TYPE_DICTIONARY:
		push_error("无法读取视角参数：%s" % path)
		return {}
	var d: Dictionary = parsed
	for key: String in ["m_yaw_deg", "m_pitch_deg", "pitch_min_deg", "pitch_max_deg", "base_hfov_4x3_deg"]:
		if not d.has(key):
			push_error("视角参数缺少字段：%s" % key)
			return {}
	return d


## 一次输入事件产生的角度增量（°）。不乘帧间隔。
static func delta_deg(counts: float, sensitivity: float, m_deg_per_count: float) -> float:
	return counts * sensitivity * m_deg_per_count


## 逐事件截断 pitch（项目暂定行为，见规格 4.2）。内部向上为正。
static func apply_pitch(pitch_deg: float, delta_pitch_deg: float, min_deg: float, max_deg: float) -> float:
	return clampf(pitch_deg + delta_pitch_deg, min_deg, max_deg)


## 输入适配层：处理一个鼠标事件，返回 [新 yaw_deg, 新 pitch_deg]。
## 鼠标 X 向右为正 → yaw 向右为正；鼠标 Y 向下为正 → pitch 向上为正（取负）。
## X 只使用 m_yaw，Y 只使用 m_pitch。
static func look_step(
	yaw_deg: float, pitch_deg: float,
	counts_x: float, counts_y: float,
	sensitivity: float, m_yaw_deg: float, m_pitch_deg: float,
	pitch_min_deg: float, pitch_max_deg: float
) -> PackedFloat64Array:
	var new_yaw_deg: float = yaw_deg + delta_deg(counts_x, sensitivity, m_yaw_deg)
	var new_pitch_deg: float = apply_pitch(
		pitch_deg, -delta_deg(counts_y, sensitivity, m_pitch_deg), pitch_min_deg, pitch_max_deg
	)
	return PackedFloat64Array([new_yaw_deg, new_pitch_deg])


## 转一圈需要的 count 数；增益为 0 时返回 INF（无有限值）。负增益只改变方向，距离取正值。
static func counts_per_360(sensitivity: float, m_yaw_deg: float) -> float:
	var gain: float = absf(sensitivity * m_yaw_deg)
	if gain == 0.0:
		return INF
	return 360.0 / gain


## 转一圈需要的鼠标位移（cm）；DPI 无效时返回 NAN。
static func cm_per_360(dpi: float, sensitivity: float, m_yaw_deg: float) -> float:
	if dpi <= 0.0:
		return NAN
	return counts_per_360(sensitivity, m_yaw_deg) / dpi * CM_PER_INCH


## 由水平 FOV 和宽高比求垂直 FOV（°）。输入无效时返回 NAN。
static func vfov_from_hfov(hfov_deg: float, aspect: float) -> float:
	if aspect <= 0.0 or hfov_deg <= 0.0 or hfov_deg >= 180.0:
		return NAN
	return rad_to_deg(2.0 * atan(tan(deg_to_rad(hfov_deg) / 2.0) / aspect))


## 由垂直 FOV 和宽高比求水平 FOV（°）。输入无效时返回 NAN。
static func hfov_from_vfov(vfov_deg: float, aspect: float) -> float:
	if aspect <= 0.0 or vfov_deg <= 0.0 or vfov_deg >= 180.0:
		return NAN
	return rad_to_deg(2.0 * atan(tan(deg_to_rad(vfov_deg) / 2.0) * aspect))
