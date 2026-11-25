extends RefCounted
## 视角换算的纯函数，公式见 docs/04-sensitivity-spec.md。
## 单位：角度一律为度（_deg），计数为原始鼠标 count。GDScript 的 float 为 64 位。

const M_YAW_DEFAULT_DEG: float = 0.022
const M_PITCH_DEFAULT_DEG: float = 0.022
const CM_PER_INCH: float = 2.54


## 一次输入事件产生的角度增量（°）。不乘帧间隔。
static func delta_deg(counts: float, sensitivity: float, m_deg_per_count: float) -> float:
	return counts * sensitivity * m_deg_per_count


## 逐事件截断 pitch（项目暂定行为，见规格 4.2）。内部向上为正。
static func apply_pitch(pitch_deg: float, delta_pitch_deg: float, min_deg: float, max_deg: float) -> float:
	return clampf(pitch_deg + delta_pitch_deg, min_deg, max_deg)


## 转一圈需要的 count 数；增益为 0 时返回 INF（无有限值）。
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
