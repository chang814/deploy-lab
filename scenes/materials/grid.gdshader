shader_type spatial;
// 灰盒网格材质：按世界坐标画 1 米细线、5 米粗线，方便在转视角、移动时判断距离和角度。
// 线条只取世界坐标里与表面平行的两个轴（按法线选），不需要 UV。

uniform vec3 base_color : source_color = vec3(0.45, 0.45, 0.47);
uniform vec3 line_color : source_color = vec3(0.30, 0.30, 0.32);
uniform vec3 major_color : source_color = vec3(0.20, 0.20, 0.22);
uniform float line_width = 0.02;
uniform float major_width = 0.04;

varying vec3 world_pos;
varying vec3 world_normal;

void vertex() {
	world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	world_normal = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
}

float grid_line(vec2 p, float period, float width) {
	vec2 d = abs(fract(p / period + 0.5) - 0.5) * period;
	vec2 aa = fwidth(p);
	vec2 l = 1.0 - smoothstep(vec2(width) - aa, vec2(width) + aa, d);
	return max(l.x, l.y);
}

void fragment() {
	vec3 n = abs(world_normal);
	vec2 p = n.y > 0.5 ? world_pos.xz : (n.x > 0.5 ? world_pos.zy : world_pos.xy);
	float minor = grid_line(p, 1.0, line_width);
	float major = grid_line(p, 5.0, major_width);
	vec3 c = mix(base_color, line_color, minor);
	c = mix(c, major_color, major);
	ALBEDO = c;
	ROUGHNESS = 0.9;
}
