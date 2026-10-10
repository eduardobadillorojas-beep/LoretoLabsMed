import { n as e } from "./rolldown-runtime-BsTNS5n0.js";
//#region node_modules/@cornerstonejs/dicom-image-loader/dist/esm/codecs/jpeg.js
function t(e, t) {
	for (var n = 0, r = [], i, a, o = 16; o > 0 && !e[o - 1];) o--;
	r.push({
		children: [],
		index: 0
	});
	var s = r[0], c;
	for (i = 0; i < o; i++) {
		for (a = 0; a < e[i]; a++) {
			for (s = r.pop(), s.children[s.index] = t[n]; s.index > 0;) s = r.pop();
			for (s.index++, r.push(s); r.length <= i;) r.push(c = {
				children: [],
				index: 0
			}), s.children[s.index] = c.children, s = c;
			n++;
		}
		i + 1 < o && (r.push(c = {
			children: [],
			index: 0
		}), s.children[s.index] = c.children, s = c);
	}
	return r[0].children;
}
function n(e, t, n) {
	return 64 * ((e.blocksPerLine + 1) * t + n);
}
function r(e, t, r, i, a, o, s, l, u) {
	r.precision, r.samplesPerLine, r.scanLines;
	var d = r.mcusPerLine, f = r.progressive;
	r.maxH, r.maxV;
	var p = t, m = 0, h = 0;
	function g() {
		if (h > 0) return h--, m >> h & 1;
		if (m = e[t++], m == 255) {
			var n = e[t++];
			if (n) throw "unexpected marker: " + (m << 8 | n).toString(16);
		}
		return h = 7, m >>> 7;
	}
	function _(e) {
		for (var t = e, n; (n = g()) !== null;) {
			if (t = t[n], typeof t == "number") return t;
			if (typeof t != "object") throw "invalid huffman sequence";
		}
		return null;
	}
	function v(e) {
		for (var t = 0; e > 0;) {
			var n = g();
			if (n === null) return;
			t = t << 1 | n, e--;
		}
		return t;
	}
	function y(e) {
		var t = v(e);
		return t >= 1 << e - 1 ? t : t + (-1 << e) + 1;
	}
	function b(e, t) {
		var n = _(e.huffmanTableDC), r = n === 0 ? 0 : y(n);
		e.blockData[t] = e.pred += r;
		for (var i = 1; i < 64;) {
			var a = _(e.huffmanTableAC), o = a & 15, s = a >> 4;
			if (o === 0) {
				if (s < 15) break;
				i += 16;
			} else {
				i += s;
				var l = c[i];
				e.blockData[t + l] = y(o), i++;
			}
		}
	}
	function x(e, t) {
		var n = _(e.huffmanTableDC), r = n === 0 ? 0 : y(n) << u;
		e.blockData[t] = e.pred += r;
	}
	function S(e, t) {
		e.blockData[t] |= g() << u;
	}
	var C = 0;
	function w(e, t) {
		if (C > 0) C--;
		else for (var n = o, r = s; n <= r;) {
			var i = _(e.huffmanTableAC), a = i & 15, l = i >> 4;
			if (a === 0) {
				if (l < 15) {
					C = v(l) + (1 << l) - 1;
					break;
				}
				n += 16;
			} else {
				n += l;
				var d = c[n];
				e.blockData[t + d] = y(a) * (1 << u), n++;
			}
		}
	}
	var T = 0, E;
	function D(e, t) {
		for (var n = o, r = s, i = 0; n <= r;) {
			var a = c[n];
			switch (T) {
				case 0:
					var l = _(e.huffmanTableAC), d = l & 15;
					if (i = l >> 4, d === 0) i < 15 ? (C = v(i) + (1 << i), T = 4) : (i = 16, T = 1);
					else {
						if (d !== 1) throw "invalid ACn encoding";
						E = y(d), T = i ? 2 : 3;
					}
					continue;
				case 1:
				case 2:
					e.blockData[t + a] ? e.blockData[t + a] += g() << u : (i--, i === 0 && (T = T == 2 ? 3 : 0));
					break;
				case 3:
					e.blockData[t + a] ? e.blockData[t + a] += g() << u : (e.blockData[t + a] = E << u, T = 0);
					break;
				case 4: e.blockData[t + a] && (e.blockData[t + a] += g() << u);
			}
			n++;
		}
		T === 4 && (C--, C === 0 && (T = 0));
	}
	function O(e, t, r, i, a) {
		var o = r / d | 0, s = r % d;
		t(e, n(e, o * e.v + i, s * e.h + a));
	}
	function k(e, t, r) {
		t(e, n(e, r / e.blocksPerLine | 0, r % e.blocksPerLine));
	}
	var A = i.length, j, M, N, P, F, I = f ? o === 0 ? l === 0 ? x : S : l === 0 ? w : D : b, L = 0, R, z = A == 1 ? i[0].blocksPerLine * i[0].blocksPerColumn : d * r.mcusPerColumn;
	a || (a = z);
	for (var B, V; L < z;) {
		for (M = 0; M < A; M++) i[M].pred = 0;
		if (C = 0, A == 1) for (j = i[0], F = 0; F < a; F++) k(j, I, L), L++;
		else for (F = 0; F < a; F++) {
			for (M = 0; M < A; M++) for (j = i[M], B = j.h, V = j.v, N = 0; N < V; N++) for (P = 0; P < B; P++) O(j, I, L, N, P);
			L++;
		}
		if (h = 0, R = e[t] << 8 | e[t + 1], R <= 65280) throw "marker was not found";
		if (R >= 65488 && R <= 65495) t += 2;
		else break;
	}
	return t - p;
}
function i(e, t, n) {
	for (var r = e.quantizationTable, i, a, o, s, c, _, v, y, b, x = 0; x < 64; x++) n[x] = e.blockData[t + x] * r[x];
	for (x = 0; x < 8; ++x) {
		var S = 8 * x;
		n[1 + S] === 0 && n[2 + S] === 0 && n[3 + S] === 0 && n[4 + S] === 0 && n[5 + S] === 0 && n[6 + S] === 0 && n[7 + S] === 0 ? (b = h * n[0 + S] + 512 >> 10, n[0 + S] = b, n[1 + S] = b, n[2 + S] = b, n[3 + S] = b, n[4 + S] = b, n[5 + S] = b, n[6 + S] = b, n[7 + S] = b) : (i = h * n[0 + S] + 128 >> 8, a = h * n[4 + S] + 128 >> 8, o = n[2 + S], s = n[6 + S], c = g * (n[1 + S] - n[7 + S]) + 128 >> 8, y = g * (n[1 + S] + n[7 + S]) + 128 >> 8, _ = n[3 + S] << 4, v = n[5 + S] << 4, b = i - a + 1 >> 1, i = i + a + 1 >> 1, a = b, b = o * m + s * p + 128 >> 8, o = o * p - s * m + 128 >> 8, s = b, b = c - v + 1 >> 1, c = c + v + 1 >> 1, v = b, b = y + _ + 1 >> 1, _ = y - _ + 1 >> 1, y = b, b = i - s + 1 >> 1, i = i + s + 1 >> 1, s = b, b = a - o + 1 >> 1, a = a + o + 1 >> 1, o = b, b = c * f + y * d + 2048 >> 12, c = c * d - y * f + 2048 >> 12, y = b, b = _ * u + v * l + 2048 >> 12, _ = _ * l - v * u + 2048 >> 12, v = b, n[0 + S] = i + y, n[7 + S] = i - y, n[1 + S] = a + v, n[6 + S] = a - v, n[2 + S] = o + _, n[5 + S] = o - _, n[3 + S] = s + c, n[4 + S] = s - c);
	}
	for (x = 0; x < 8; ++x) {
		var C = x;
		n[8 + C] === 0 && n[16 + C] === 0 && n[24 + C] === 0 && n[32 + C] === 0 && n[40 + C] === 0 && n[48 + C] === 0 && n[56 + C] === 0 ? (b = h * n[x + 0] + 8192 >> 14, n[0 + C] = b, n[8 + C] = b, n[16 + C] = b, n[24 + C] = b, n[32 + C] = b, n[40 + C] = b, n[48 + C] = b, n[56 + C] = b) : (i = h * n[0 + C] + 2048 >> 12, a = h * n[32 + C] + 2048 >> 12, o = n[16 + C], s = n[48 + C], c = g * (n[8 + C] - n[56 + C]) + 2048 >> 12, y = g * (n[8 + C] + n[56 + C]) + 2048 >> 12, _ = n[24 + C], v = n[40 + C], b = i - a + 1 >> 1, i = i + a + 1 >> 1, a = b, b = o * m + s * p + 2048 >> 12, o = o * p - s * m + 2048 >> 12, s = b, b = c - v + 1 >> 1, c = c + v + 1 >> 1, v = b, b = y + _ + 1 >> 1, _ = y - _ + 1 >> 1, y = b, b = i - s + 1 >> 1, i = i + s + 1 >> 1, s = b, b = a - o + 1 >> 1, a = a + o + 1 >> 1, o = b, b = c * f + y * d + 2048 >> 12, c = c * d - y * f + 2048 >> 12, y = b, b = _ * u + v * l + 2048 >> 12, _ = _ * l - v * u + 2048 >> 12, v = b, n[0 + C] = i + y, n[56 + C] = i - y, n[8 + C] = a + v, n[48 + C] = a - v, n[16 + C] = o + _, n[40 + C] = o - _, n[24 + C] = s + c, n[32 + C] = s - c);
	}
	for (x = 0; x < 64; ++x) {
		var w = t + x, T = n[x];
		T = T <= -2056 / e.bitConversion ? 0 : T >= 2024 / e.bitConversion ? 255 / e.bitConversion : T + 2056 / e.bitConversion >> 4, e.blockData[w] = T;
	}
}
function a(e, t) {
	var r = t.blocksPerLine, a = t.blocksPerColumn;
	r << 3;
	for (var o = /* @__PURE__ */ new Int32Array(64), s = 0; s < a; s++) for (var c = 0; c < r; c++) i(t, n(t, s, c), o);
	return t.blockData;
}
function o(e) {
	return e <= 0 ? 0 : e >= 255 ? 255 : e | 0;
}
var s, c, l, u, d, f, p, m, h, g, _;
//#endregion
e((() => {
	s = {
		Unkown: 0,
		Grayscale: 1,
		AdobeRGB: 2,
		RGB: 3,
		CYMK: 4
	}, c = new Int32Array([
		0,
		1,
		8,
		16,
		9,
		2,
		3,
		10,
		17,
		24,
		32,
		25,
		18,
		11,
		4,
		5,
		12,
		19,
		26,
		33,
		40,
		48,
		41,
		34,
		27,
		20,
		13,
		6,
		7,
		14,
		21,
		28,
		35,
		42,
		49,
		56,
		57,
		50,
		43,
		36,
		29,
		22,
		15,
		23,
		30,
		37,
		44,
		51,
		58,
		59,
		52,
		45,
		38,
		31,
		39,
		46,
		53,
		60,
		61,
		54,
		47,
		55,
		62,
		63
	]), l = 4017, u = 799, d = 3406, f = 2276, p = 1567, m = 3784, h = 5793, g = 2896, _ = class {
		constructor() {}
		load(e) {
			var t = function(e) {
				this.parse(e), this.onload && this.onload();
			}.bind(this);
			if (e.indexOf("data:") > -1) {
				for (var n = e.indexOf("base64,") + 7, r = atob(e.substring(n)), i = new Uint8Array(r.length), a = r.length - 1; a >= 0; a--) i[a] = r.charCodeAt(a);
				t(r);
			} else {
				var o = new XMLHttpRequest();
				o.open("GET", e, !0), o.responseType = "arraybuffer", o.onload = function() {
					t(new Uint8Array(o.response));
				}.bind(this), o.send(null);
			}
		}
		parse(e) {
			function n() {
				var t = e[l] << 8 | e[l + 1];
				return l += 2, t;
			}
			function i() {
				var t = n(), r = e.subarray(l, l + t - 2);
				return l += r.length, r;
			}
			function o(e) {
				for (var t = Math.ceil(e.samplesPerLine / 8 / e.maxH), n = Math.ceil(e.scanLines / 8 / e.maxV), r = 0; r < e.components.length; r++) {
					V = e.components[r];
					var i = Math.ceil(Math.ceil(e.samplesPerLine / 8) * V.h / e.maxH), a = Math.ceil(Math.ceil(e.scanLines / 8) * V.v / e.maxV), o = t * V.h, s = 64 * (n * V.v) * (o + 1);
					V.blockData = new Int16Array(s), V.blocksPerLine = i, V.blocksPerColumn = a;
				}
				e.mcusPerLine = t, e.mcusPerColumn = n;
			}
			var l = 0;
			e.length;
			var u = null, d = null, f, p, m = [], h = [], g = [], _ = n();
			if (_ != 65496) throw "SOI not found";
			for (_ = n(); _ != 65497;) {
				var v, y, b;
				switch (_) {
					case 65504:
					case 65505:
					case 65506:
					case 65507:
					case 65508:
					case 65509:
					case 65510:
					case 65511:
					case 65512:
					case 65513:
					case 65514:
					case 65515:
					case 65516:
					case 65517:
					case 65518:
					case 65519:
					case 65534:
						var x = i();
						_ === 65504 && x[0] === 74 && x[1] === 70 && x[2] === 73 && x[3] === 70 && x[4] === 0 && (u = {
							version: {
								major: x[5],
								minor: x[6]
							},
							densityUnits: x[7],
							xDensity: x[8] << 8 | x[9],
							yDensity: x[10] << 8 | x[11],
							thumbWidth: x[12],
							thumbHeight: x[13],
							thumbData: x.subarray(14, 14 + 3 * x[12] * x[13])
						}), _ === 65518 && x[0] === 65 && x[1] === 100 && x[2] === 111 && x[3] === 98 && x[4] === 101 && x[5] === 0 && (d = {
							version: x[6],
							flags0: x[7] << 8 | x[8],
							flags1: x[9] << 8 | x[10],
							transformCode: x[11]
						});
						break;
					case 65499:
						for (var S = n() + l - 2; l < S;) {
							var C = e[l++], w = /* @__PURE__ */ new Int32Array(64);
							if (!(C >> 4)) for (y = 0; y < 64; y++) {
								var T = c[y];
								w[T] = e[l++];
							}
							else if (C >> 4 == 1) for (y = 0; y < 64; y++) {
								var E = c[y];
								w[E] = n();
							}
							else throw "DQT: invalid table spec";
							m[C & 15] = w;
						}
						break;
					case 65472:
					case 65473:
					case 65474:
						if (f) throw "Only single frame JPEGs supported";
						n(), f = {}, f.extended = _ === 65473, f.progressive = _ === 65474, f.precision = e[l++], f.scanLines = n(), f.samplesPerLine = n(), f.components = [], f.componentIds = {};
						var D = e[l++], O, k = 0, A = 0;
						for (v = 0; v < D; v++) {
							O = e[l];
							var j = e[l + 1] >> 4, M = e[l + 1] & 15;
							k < j && (k = j), A < M && (A = M);
							var N = e[l + 2];
							b = f.components.push({
								h: j,
								v: M,
								quantizationTable: m[N],
								quantizationTableId: N,
								bitConversion: 255 / ((1 << f.precision) - 1)
							}), f.componentIds[O] = b - 1, l += 3;
						}
						f.maxH = k, f.maxV = A, o(f);
						break;
					case 65476:
						var P = n();
						for (v = 2; v < P;) {
							var F = e[l++], I = /* @__PURE__ */ new Uint8Array(16), L = 0;
							for (y = 0; y < 16; y++, l++) L += I[y] = e[l];
							var R = new Uint8Array(L);
							for (y = 0; y < L; y++, l++) R[y] = e[l];
							v += 17 + L, (F >> 4 ? h : g)[F & 15] = t(I, R);
						}
						break;
					case 65501:
						n(), p = n();
						break;
					case 65498:
						n();
						var z = e[l++], B = [], V;
						for (v = 0; v < z; v++) {
							var H = f.componentIds[e[l++]];
							V = f.components[H];
							var U = e[l++];
							V.huffmanTableDC = g[U >> 4], V.huffmanTableAC = h[U & 15], B.push(V);
						}
						var W = e[l++], G = e[l++], K = e[l++], q = r(e, l, f, B, p, W, G, K >> 4, K & 15);
						l += q;
						break;
					case 65535:
						e[l] !== 255 && l--;
						break;
					default:
						if (e[l - 3] == 255 && e[l - 2] >= 192 && e[l - 2] <= 254) {
							l -= 3;
							break;
						}
						throw "unknown JPEG marker " + _.toString(16);
				}
				_ = n();
			}
			switch (this.width = f.samplesPerLine, this.height = f.scanLines, this.jfif = u, this.adobe = d, this.components = [], f.components.length) {
				case 1:
					this.colorspace = s.Grayscale;
					break;
				case 3:
					this.colorspace = this.adobe ? s.AdobeRGB : s.RGB;
					break;
				case 4:
					this.colorspace = s.CYMK;
					break;
				default: this.colorspace = s.Unknown;
			}
			for (var v = 0; v < f.components.length; v++) {
				var V = f.components[v];
				!V.quantizationTable && V.quantizationTableId !== null && (V.quantizationTable = m[V.quantizationTableId]), this.components.push({
					output: a(f, V),
					scaleX: V.h / f.maxH,
					scaleY: V.v / f.maxV,
					blocksPerLine: V.blocksPerLine,
					blocksPerColumn: V.blocksPerColumn,
					bitConversion: V.bitConversion
				});
			}
		}
		getData16(e, t) {
			if (this.components.length !== 1) throw "Unsupported color mode";
			var r = this.width / e, i = this.height / t, a, o, s, c, l, u, d = 0, f = this.components.length, p = e * t * f, m = new Uint16Array(p), h = new Uint16Array((this.components[0].blocksPerLine << 3) * this.components[0].blocksPerColumn * 8);
			for (u = 0; u < f; u++) {
				a = this.components[u];
				for (var g = a.blocksPerLine, _ = a.blocksPerColumn, v = g << 3, y, b, x = 0, S = 0; S < _; S++) for (var C = S << 3, w = 0; w < g; w++) {
					var T = n(a, S, w), d = 0, E = w << 3;
					for (y = 0; y < 8; y++) {
						var x = (C + y) * v;
						for (b = 0; b < 8; b++) h[x + E + b] = a.output[T + d++];
					}
				}
				o = a.scaleX * r, s = a.scaleY * i, d = u;
				var D, O, k;
				for (l = 0; l < t; l++) for (c = 0; c < e; c++) O = 0 | l * s, D = 0 | c * o, k = O * v + D, m[d] = h[k], d += f;
			}
			return m;
		}
		getData(e, t) {
			var r = this.width / e, i = this.height / t, a, s, c, l, u, d, f = 0, p, m, h, g, _, v, y, b, x, S = this.components.length, C = e * t * S, w = new Uint8Array(C), T = new Uint8Array((this.components[0].blocksPerLine << 3) * this.components[0].blocksPerColumn * 8);
			for (d = 0; d < S; d++) {
				a = this.components[d];
				for (var E = a.blocksPerLine, D = a.blocksPerColumn, O = E << 3, k, A, j = 0, M = 0; M < D; M++) for (var N = M << 3, P = 0; P < E; P++) {
					var F = n(a, M, P), f = 0, I = P << 3;
					for (k = 0; k < 8; k++) {
						var j = (N + k) * O;
						for (A = 0; A < 8; A++) T[j + I + A] = a.output[F + f++] * a.bitConversion;
					}
				}
				s = a.scaleX * r, c = a.scaleY * i, f = d;
				var L, R, z;
				for (u = 0; u < t; u++) for (l = 0; l < e; l++) R = 0 | u * c, L = 0 | l * s, z = R * O + L, w[f] = T[z], f += S;
			}
			switch (S) {
				case 1:
				case 2: break;
				case 3:
					if (x = !0, this.adobe && this.adobe.transformCode ? x = !0 : this.colorTransform !== void 0 && (x = !!this.colorTransform), x) for (d = 0; d < C; d += S) p = w[d], m = w[d + 1], h = w[d + 2], v = o(p - 179.456 + 1.402 * h), y = o(p + 135.459 - .344 * m - .714 * h), b = o(p - 226.816 + 1.772 * m), w[d] = v, w[d + 1] = y, w[d + 2] = b;
					break;
				case 4:
					if (!this.adobe) throw "Unsupported color mode (4 components)";
					if (x = !1, this.adobe && this.adobe.transformCode ? x = !0 : this.colorTransform !== void 0 && (x = !!this.colorTransform), x) for (d = 0; d < C; d += S) p = w[d], m = w[d + 1], h = w[d + 2], g = o(434.456 - p - 1.402 * h), _ = o(119.541 - p + .344 * m + .714 * h), p = o(481.816 - p - 1.772 * m), w[d] = g, w[d + 1] = _, w[d + 2] = p;
					break;
				default: throw "Unsupported color mode";
			}
			return w;
		}
	};
}))();
export { _ as default };
