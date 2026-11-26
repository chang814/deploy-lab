class_name MoveMath
extends RefCounted
## 地面 / 空中移动的纯函数（Source 引擎风格：摩擦 + 朝期望方向加速 + 空中加速上限）。
## 规则（ADR 0002）：core 不读文件、不依赖场景节点。单位：米、秒。只处理水平分量（y 保持不变）。


## 地面摩擦：速度越低按 stop_speed_mps 计算（低速时更快停下）。
static func friction(v: Vector3, friction_per_s: float, stop_speed_mps: float, dt_s: float) -> Vector3:
	var h: Vector2 = Vector2(v.x, v.z)
	var speed: float = h.length()
	if speed < 1e-6:
		return Vector3(0.0, v.y, 0.0)
	var control: float = maxf(speed, stop_speed_mps)
	var new_speed: float = maxf(speed - control * friction_per_s * dt_s, 0.0)
	var k: float = new_speed / speed
	return Vector3(v.x * k, v.y, v.z * k)


## 朝 wish_dir（水平单位向量）加速到 wish_speed_mps。只补足「在该方向上的分量」的差额。
static func accelerate(v: Vector3, wish_dir: Vector3, wish_speed_mps: float, accel_per_s: float, dt_s: float) -> Vector3:
	var current: float = v.x * wish_dir.x + v.z * wish_dir.z
	var add: float = wish_speed_mps - current
	if add <= 0.0:
		return v
	var gain: float = minf(accel_per_s * wish_speed_mps * dt_s, add)
	return Vector3(v.x + gain * wish_dir.x, v.y, v.z + gain * wish_dir.z)


## 空中加速：目标速度被限制在 air_cap_mps（Source 的 30 单位上限），但加速量按原始期望速度计算。
static func air_accelerate(
	v: Vector3, wish_dir: Vector3, wish_speed_mps: float, accel_per_s: float, air_cap_mps: float, dt_s: float
) -> Vector3:
	var capped: float = minf(wish_speed_mps, air_cap_mps)
	var current: float = v.x * wish_dir.x + v.z * wish_dir.z
	var add: float = capped - current
	if add <= 0.0:
		return v
	var gain: float = minf(accel_per_s * wish_speed_mps * dt_s, add)
	return Vector3(v.x + gain * wish_dir.x, v.y, v.z + gain * wish_dir.z)


## 把输入（x = 右，y = 前，各 -1..1）按视角 yaw 转成世界水平方向单位向量。yaw 向右为正（与 LookMath 一致）。
## Godot 前方是 -Z、右方是 +X；yaw_deg 右转为正。无输入时返回零向量。
static func wish_dir(input: Vector2, yaw_deg: float) -> Vector3:
	if input.length_squared() < 1e-12:
		return Vector3.ZERO
	var n: Vector2 = input.normalized()
	var yaw_rad: float = deg_to_rad(yaw_deg)
	var forward: Vector3 = Vector3(sin(yaw_rad), 0.0, -cos(yaw_rad))
	var right: Vector3 = Vector3(cos(yaw_rad), 0.0, sin(yaw_rad))
	return (right * n.x + forward * n.y).normalized()
