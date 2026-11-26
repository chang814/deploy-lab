class_name WeaponState
extends RefCounted
## 切枪 / 开火 / 换弹状态机（纯逻辑，按 tick 推进；v0.2）。
##
## 时间模型（临时模拟模型）：模拟以固定 tick 运行（CS2 为 64 tick/s）。输入在两个 tick 之间到达，到下一个
## tick 才被处理，因此「按键 → 生效」有 0–1 个 tick 的等待。P0-5 第一批的切枪时长散布与这个模型吻合，
## 但它仍是待 V 项（正常速度对照）验证的假设（docs/measurement/p0-5-batch1.md）。
## 切枪在处理它的那个 tick 开始拔出，经过 draw_s 后的第一个 tick 才能开火。
##
## 规则：
## - 切到另一把武器（数字键 / Q / 滚轮）立即开始拔出新武器；拔出中、换弹中都可以被切枪打断（换弹作废）
## - 切到手里这把：忽略
## - 非自动武器每次开火后必须松开扳机才能再开；自动武器按 fire_interval_s 连发
## - 弹匣打空后扣扳机自动换弹；R 手动换弹（弹匣不满时）；备弹无限
## - magazine = 0 表示不用弹药（刀）

enum State { DRAWING, READY, RELOADING }

const EPS_S: float = 1e-9

var tick_s: float = 1.0 / 64.0
var weapons: Dictionary = {}     # id → 参数字典（见 data/weapons/weapons.json）
var slot_order: Array = []       # 按槽位排序的 id，用于滚轮
var current: String = ""
var previous: String = ""
var state: State = State.DRAWING
var ammo: Dictionary = {}        # id → 弹匣里的子弹数
var now_s: float = 0.0           # 已处理的 tick 对应的时间
var ready_at_s: float = 0.0      # 拔出完成的时刻
var reload_done_s: float = 0.0
var next_fire_s: float = 0.0
var _trigger_released: bool = true
var _pending_switch: String = "" # 本 tick 之前收到的切枪请求（下一个 tick 处理）
var _pending_reload: bool = false


## weapon_list：参数字典数组；start_id：开局手里的武器（立即可用，不需要拔出）。
func setup(weapon_list: Array, tick_rate_hz: float, start_id: String) -> void:
	tick_s = 1.0 / tick_rate_hz
	weapons.clear()
	ammo.clear()
	for w: Dictionary in weapon_list:
		weapons[w["id"]] = w
		ammo[w["id"]] = int(w["magazine"])
	slot_order = weapons.keys()
	slot_order.sort_custom(func(a: String, b: String) -> bool: return int(weapons[a]["slot"]) < int(weapons[b]["slot"]))
	current = start_id
	previous = ""
	state = State.READY
	now_s = 0.0
	ready_at_s = 0.0
	next_fire_s = 0.0


func id_for_slot(slot: int) -> String:
	for id: String in slot_order:
		if int(weapons[id]["slot"]) == slot:
			return id
	return ""


## 输入（随时可以调用，下一个 tick 生效）。
func request_slot(slot: int) -> void:
	var id: String = id_for_slot(slot)
	if not id.is_empty():
		_pending_switch = id


func request_quick_switch() -> void:
	if not previous.is_empty():
		_pending_switch = previous


## 滚轮：+1 = 下一把（槽位号变大，循环），-1 = 上一把。以「已请求的目标」为基准，连续滚动可以跳过几把。
func request_wheel(direction: int) -> void:
	var base: String = _pending_switch if not _pending_switch.is_empty() else current
	var i: int = slot_order.find(base)
	_pending_switch = slot_order[posmod(i + direction, slot_order.size())]


func request_reload() -> void:
	_pending_reload = true


## 两个 tick 之间扳机松开过（即使 tick 时又按下了）：半自动武器据此允许下一枪。
func release_trigger() -> void:
	_trigger_released = true


func is_ready() -> bool:
	return state == State.READY


## 推进一个 tick。trigger_held：这一 tick 扳机（左键）是否按着。返回这一 tick 是否开火。
func tick(trigger_held: bool) -> bool:
	now_s += tick_s
	if not _pending_switch.is_empty():
		_switch_to(_pending_switch)
		_pending_switch = ""
	var w: Dictionary = weapons[current]
	var uses_ammo: bool = int(w["magazine"]) > 0
	if state == State.DRAWING and now_s >= ready_at_s - EPS_S:
		state = State.READY
	if state == State.RELOADING and now_s >= reload_done_s - EPS_S:
		ammo[current] = int(w["magazine"])
		state = State.READY
	if _pending_reload:
		_pending_reload = false
		if state == State.READY and uses_ammo and ammo[current] < int(w["magazine"]):
			_start_reload()
	if not trigger_held:
		_trigger_released = true
	if state != State.READY or not trigger_held:
		return false
	if uses_ammo and ammo[current] <= 0:
		_start_reload()
		return false
	if not bool(w["automatic"]) and not _trigger_released:
		return false
	if now_s < next_fire_s - EPS_S:
		return false
	if uses_ammo:
		ammo[current] -= 1
	# 连续开火时从「计划时刻」累计，而不是从被 tick 取整后的实际时刻累计，避免射速被 tick 拖慢；
	# 中间停过（实际时刻已晚于计划超过一个 tick）就从现在重新算
	var base_s: float = next_fire_s if now_s - next_fire_s < tick_s - EPS_S else now_s
	next_fire_s = base_s + float(w["fire_interval_s"])
	_trigger_released = false
	return true


func _switch_to(id: String) -> void:
	if id == current:
		return
	previous = current
	current = id
	state = State.DRAWING
	ready_at_s = now_s + float(weapons[id]["draw_s"])
	next_fire_s = ready_at_s
	_trigger_released = true


func _start_reload() -> void:
	state = State.RELOADING
	reload_done_s = now_s + float(weapons[current]["reload_s"])
