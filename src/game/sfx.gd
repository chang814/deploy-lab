class_name Sfx
extends RefCounted
## 程序合成的音效（不使用任何外部音频素材）：在运行时生成 16 位单声道 PCM。
## 都是近似的「感觉对」的声音，不是任何真实枪械或游戏的录音。

const RATE_HZ: int = 44100

## 缓存：同一种声音只合成一次
static var _cache: Dictionary = {}


static func get_stream(kind: String) -> AudioStreamWAV:
	if not _cache.has(kind):
		_cache[kind] = _make(kind)
	return _cache[kind]


static func _make(kind: String) -> AudioStreamWAV:
	var rng: RandomNumberGenerator = RandomNumberGenerator.new()
	rng.seed = hash(kind)
	var samples: PackedFloat32Array
	match kind:
		"rifle": samples = _shot(rng, 0.42, 0.055, 62.0, 0.09, 0.9)
		"pistol": samples = _shot(rng, 0.3, 0.035, 115.0, 0.05, 0.75)
		"hit": samples = _tick(1750.0, 0.07, 0.035)
		"swish": samples = _swish(rng, 0.26)
		"mag_out": samples = _click(rng, 0.09, [900.0, 2300.0], 0.018, 0.5)
		"mag_in": samples = _click(rng, 0.11, [520.0, 1500.0, 3100.0], 0.02, 0.8)
		"bolt": samples = _concat(_click(rng, 0.08, [700.0, 2600.0], 0.015, 0.7), _click(rng, 0.12, [450.0, 1900.0], 0.02, 0.85), 0.06)
		_: samples = PackedFloat32Array()
	return _to_wav(samples)


## 枪声：噪声爆音（指数衰减）+ 低频冲击（衰减的正弦）+ 简单一阶低通让声音不刺耳。
static func _shot(rng: RandomNumberGenerator, length_s: float, noise_tau_s: float, thump_hz: float,
		thump_tau_s: float, gain: float) -> PackedFloat32Array:
	var n: int = int(length_s * RATE_HZ)
	var out: PackedFloat32Array = PackedFloat32Array()
	out.resize(n)
	var lp: float = 0.0
	for i: int in n:
		var t: float = float(i) / RATE_HZ
		var noise: float = rng.randf_range(-1.0, 1.0) * exp(-t / noise_tau_s)
		var tail: float = rng.randf_range(-1.0, 1.0) * 0.18 * exp(-t / (noise_tau_s * 4.0))
		lp += (noise + tail - lp) * 0.35
		var thump: float = sin(TAU * thump_hz * t * (1.0 - t * 0.8)) * exp(-t / thump_tau_s)
		out[i] = clampf((lp * 0.8 + thump * 0.7) * gain, -1.0, 1.0)
	return out


## 命中提示音：短促的高音「叮」。
static func _tick(freq_hz: float, length_s: float, tau_s: float) -> PackedFloat32Array:
	var n: int = int(length_s * RATE_HZ)
	var out: PackedFloat32Array = PackedFloat32Array()
	out.resize(n)
	for i: int in n:
		var t: float = float(i) / RATE_HZ
		out[i] = (sin(TAU * freq_hz * t) * 0.6 + sin(TAU * freq_hz * 2.01 * t) * 0.25) * exp(-t / tau_s)
	return out


## 挥刀破风声：噪声经过截止频率先升后降的低通，包络先强后弱。
static func _swish(rng: RandomNumberGenerator, length_s: float) -> PackedFloat32Array:
	var n: int = int(length_s * RATE_HZ)
	var out: PackedFloat32Array = PackedFloat32Array()
	out.resize(n)
	var lp: float = 0.0
	for i: int in n:
		var p: float = float(i) / n
		var cutoff: float = 0.02 + 0.25 * sin(PI * p)
		lp += (rng.randf_range(-1.0, 1.0) - lp) * cutoff
		out[i] = lp * sin(PI * p) * 1.6
	return out


## 金属卡扣声：几个高频正弦 + 一点噪声，快速衰减。
static func _click(rng: RandomNumberGenerator, length_s: float, freqs_hz: Array, tau_s: float, gain: float) -> PackedFloat32Array:
	var n: int = int(length_s * RATE_HZ)
	var out: PackedFloat32Array = PackedFloat32Array()
	out.resize(n)
	for i: int in n:
		var t: float = float(i) / RATE_HZ
		var v: float = rng.randf_range(-1.0, 1.0) * 0.4
		for f: float in freqs_hz:
			v += sin(TAU * f * t) * 0.35
		out[i] = clampf(v * exp(-t / tau_s) * gain, -1.0, 1.0)
	return out


static func _concat(a: PackedFloat32Array, b: PackedFloat32Array, gap_s: float) -> PackedFloat32Array:
	var out: PackedFloat32Array = a.duplicate()
	var gap: PackedFloat32Array = PackedFloat32Array()
	gap.resize(int(gap_s * RATE_HZ))
	out.append_array(gap)
	out.append_array(b)
	return out


static func _to_wav(samples: PackedFloat32Array) -> AudioStreamWAV:
	var bytes: PackedByteArray = PackedByteArray()
	bytes.resize(samples.size() * 2)
	for i: int in samples.size():
		bytes.encode_s16(i * 2, int(clampf(samples[i], -1.0, 1.0) * 32767.0))
	var w: AudioStreamWAV = AudioStreamWAV.new()
	w.format = AudioStreamWAV.FORMAT_16_BITS
	w.mix_rate = RATE_HZ
	w.stereo = false
	w.data = bytes
	return w
